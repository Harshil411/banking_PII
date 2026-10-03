# Decisions

One entry per real choice: what was decided, what was rejected, and why. Dated,
because the reasoning was true given what was known then and some of it will
stop being true.

---

## 2026-09-15 — Rebuild on US mortgage data rather than repair the Indian v1

The project targets US bank and GSE roles, and an interviewer there has to
mentally translate Aadhaar, PAN and IFSC before they can evaluate anything.

The switch was cheap because there was nothing to preserve. Both HuggingFace
models were gitignored and absent from disk; there was no evaluation set, no
scoring script and no notebook anywhere in six commits of history. The headline
0.866 micro-F1 had no reproducible trail at all.

More importantly, every regex in v1's detection layer was double-escaped inside
a Python raw string, so `r'\\d{4}'` compiled to a literal backslash followed by
`d` and matched nothing. 76 of them, across three files. The patterns in
`data_schema.json` were fine because JSON unescapes them — which is why the
*validation* layer worked while the *detection* layer silently no-op'd, and why
the reported F1 came entirely from the model plus the JSON-side validators.

Rejected: repairing v1 in place. Of roughly 4,000 lines of Python, about 120
were worth keeping.

## 2026-09-15 — Presidio for candidate generation only

Presidio does two jobs. Its recognizers generate candidates, which is useful.
Its `AnalyzerEngine` also arbitrates overlapping spans by score and deletes
anything a recognizer's `validate_result()` rejects.

That second job is the one this project exists to own. `validate_result()`
returns a bool and drops the loser — no tier, no reason, no rejected candidate
surfaced. "This routing number was rejected because its mod-10 checksum does
not hold" is the entire thesis, and the library destroys it for convenience.

Its US coverage also does not overlap tier 1. `UsSsnRecognizer` is regex and a
score with no area/group/serial arithmetic, and there is no ABA, MERS, NMLS or
loan-number recognizer at all. Adopting it wholesale would have simultaneously
hidden the validation layer and failed to replace it.

Its stock output on one servicing sentence: `US_SSN` at 0.4, `US_BANK_NUMBER`
and `US_PASSPORT` at 0.05 on the same nine digits, `US_DRIVER_LICENSE` at 0.01,
`DATE_TIME` over a credit card number, `ORGANIZATION` over the literal word
"SSN". The registry is trimmed to the spaCy recognizer and a test asserts none
of the rest reaches arbitration.

Honest cost: roughly half of Presidio's value, its recognizer catalogue, goes
unused. Deliberate, not an oversight.

Rejected: a fine-tuned HuggingFace token classifier. 800MB–1.5GB of image and
seconds of cold start for tier-3 labels only, and cross-label span arbitration
would still have had to be written by hand.

## 2026-09-15 — Tier means strength of evidence, not kind of detector

Stated explicitly because an interviewer will find the seam otherwise. A tier-3
entity may come from a regex — `CREDIT_SCORE` does — and a tier-2 entity may
come from a model.

This is what lets `MONEY` sit in tier 2: a currency symbol plus correct
thousands grouping is deterministic evidence, and the validator rejects
malformed grouping and sub-cent precision that the pattern accepts.
`CREDIT_SCORE` stays tier 3 under the same definition, because every
three-digit number in 300–850 passes its range check — the range is a filter,
not evidence.

`US_STATE` is tier 2 rather than 3 because closed-set membership is a real
deterministic rule, and because something has to disambiguate spaCy's `GPE`,
which covers cities and states alike.

## 2026-09-15 — Tier-1 rules are not equally strong, so SSN is context-gated

The surprise of the build. Luhn rejects about 90% of digit strings and the ABA
checksum roughly as many. The SSA's rules bar area 000, 666 and 900–999, group
00 and serial 0000 — about a quarter of the space. So "passes SSN validation"
on a bare nine-digit run is weak evidence.

Ungated, `SSN` claimed every routing and account number in the corpus: precision
0.164, and `ABA_ROUTING` recall fell to 0.022 because SSN won ties on
declaration order. Gating it on a nearby label took `ABA_ROUTING` to F1 1.000.

Cost: an unlabelled SSN in a bare table column is missed. In servicing
correspondence they are essentially always labelled.

"last four" is deliberately *not* an SSN context word. It applies equally to
cards and accounts, and including it gated SSN in beside every wire instruction.

## 2026-09-15 — Arbitration precedence, chosen by measurement

Tier, then span length, then context gating and proximity, then score, then
declaration order. Three arrangements scored against 300 documents:

| ordering | micro-F1 |
|---|---|
| tier, length, gating, proximity | **0.948** |
| length, tier, gating, proximity | 0.945 |
| length, gating, bucketed proximity, tier | 0.936 |

Putting length or proximity ahead of tier lets spaCy's long `LOCATION` spans
swallow validated ZIPs and states, and lets `US_ACCOUNT_NUM` claim spans
belonging to narrower types — its precision fell to 0.526 in the third.

Two rules within that chain earned their place separately:

A **tier-1 FAIL leaves contention entirely** rather than shadowing the span. A
nine-digit run failing the SSA rules is not an SSN, but it may still be an
account number, and suppressing that reading because a stronger type looked
first would lose a real entity.

A **span strictly inside a longer pattern-derived match is a fragment**, not an
entity. `NMLS_ID`'s four-to-seven digit pattern matches the year inside
`10/13/2021` and the tail of an EIN. Restricted to pattern-derived containers
on purpose: letting model-carried spans absorb validated ones measured worse.

Documented cost: in "credit account 483920117" the account number is labelled
`SSN`. The span is still redacted so the privacy outcome is unaffected, but the
label is wrong, and it is most of why `US_ACCOUNT_NUM` sits at F1 0.778.

## 2026-09-15 — `redact_failed_tier1` defaults to False

When a validator proves a nine-digit string is not a valid SSN, the default is
to leave it in place. Redacting text we have positive evidence is *not* the
entity is exactly the false-positive behaviour this design exists to avoid.

The cost is real and worth saying before being asked: a genuine SSN mistyped by
one digit stays in the output. A privacy pipeline handling real borrower files
probably should set the flag to True and accept the over-redaction. It is a
per-request option rather than a build-time decision for that reason.

## 2026-09-15 — Synthetic identifiers are checksum-correct, with a separate adversarial set

The instinct is to make every synthetic identifier deliberately invalid so the
data is provably not real. That is wrong once the validators do arithmetic, and
it fails quietly: every tier-1 validator would reject every true positive,
recall would collapse, and it would look like a detection bug for a day.

So values are structurally valid and randomly generated with no linkage to any
person, and a *separate* class of adversarial values — passing the pattern,
failing the validator — carries the burden of proving the validators work. A
third class, distractors, is servicing text that is PII-shaped but is not PII.
Without distractors a precision number means very little, because the cheapest
way to score well on synthetic data is to claim every digit run on the page.

`value_kind` is recorded per span at generation time because it cannot be
recovered afterwards, and "94.4% of regex-passing near-misses rejected" is not
computable without it. *(Corrected 2026-09-16: that figure turned out to be
largely true by construction — see "The near-miss rejection rate is not a
score".)*

## 2026-09-15 — Generator and validator must be able to disagree

Check digits are constructed forward: `luhn_check_digit` computes the digit
directly, and the ABA weighted sum is computed inline in the provider. Nothing
in `synth/` calls a validator to search for a check digit.

If both sides derived their answer from one routine they would agree by
construction, and a misreading of a specification would be invisible in both.
Validators are tested against externally sourced vectors — published Federal
Reserve routing numbers, published processor test cards, the SSA's never-issued
ranges, the IRS unassigned prefix table — for the same reason.

`MERS_MIN` is the exception and is flagged in the taxonomy. There is no
convenient public corpus of known-good MINs, so it carries more specification
risk than its siblings: if this reading of the MERS manual is wrong, tier-1
precision looks perfect on synthetic data and collapses on anything real.

## 2026-09-15 — Gold spans recorded during construction, never by searching

Documents are assembled by appending fragments and recording offsets as they
go. Rendering a template and then locating each value with `str.find` is the
trap, and it fails silently — a borrower's name appears in the letterhead and
again in the body, `find` returns the first for every later one, and the
evaluation set becomes subtly wrong in a way that reads as a model-quality
problem for a week.

A test asserts the corpus actually contains repeated values, so the alignment
check is guarding something real rather than a hypothetical.

## 2026-09-15 — Patterns live in YAML, in scanner form only

JSON has no comments, and every regex here needs a sentence explaining why it is
shaped the way it is — NANP's first-digit rule, ITIN's group ranges, the IRS
prefix set. Config-as-code in `.py` was rejected because Python string literals
are exactly where v1's double-escape bug lived.

Patterns are authored in scanner form; the anchored validator form is derived at
load time. Authoring both by hand is how they drift apart.

Scanners are deliberately permissive — recall is their job and precision is the
validator's. An earlier `MONEY` pattern encoded correct thousands grouping
itself, which meant a malformed amount was never matched whole ("$5,57.02"
matched only as "$5") and the validator's grouping rule was unreachable.

## 2026-09-15 — The loader raises; it does not degrade

v1 guarded every file read with `.exists()` and fell back to an empty dict, so a
misconfigured deployment returned `{"schema": null}` and looked like a service
that found nothing. A taxonomy that cannot be loaded is not a degraded service.

Startup failures are recorded and surfaced through `/readyz` rather than
swallowed. `/healthz` and `/readyz` are separate endpoints because an
orchestrator must not restart a container that is merely still loading the
model, and must not route traffic to one whose first request would carry
model initialisation — which would also make every latency percentile measured
afterwards a fiction.

## 2026-09-15 — The React frontend was deleted for one static HTML file

Both v1 result panels built a single concatenated string rather than JSX, so per
entity tier badges needed a rewrite regardless. Nothing in the app ever read a
span offset. Keeping `react-scripts` 5.0.1 would have put `npm ci` and a build
stage into both the Docker image and the CI pipeline.

The replacement is one file with no build step that does the thing the old one
could not: render the original text with each span marked by tier, from the
offsets the server reported.

Building it found a real bug. The redacted payoff statement read
`Prepared for: [NAME] number: ...` because spaCy's `PERSON` span ran across a
newline into the next field. Truncating model-carried spans at the first line
break moved `PERSON_NAME` from F1 0.748 to 0.947 and overall micro-F1 from
0.948 to 0.974. That is the argument for building the UI.

## 2026-09-15 — Instrumentation that exists before it is needed

Taxonomy version in every response, per-stage timings, a request id, a
batch-shaped `analyze()` signature, `value_kind` on every gold span, and the
validator rejection rate. None is used yet.

Each is there because retrofitting it is worse than carrying it. Timings added
after benchmarking has begun mean re-running every measurement. A drift
comparison across a changed label space is silently meaningless rather than
detectably stale without the version. Throughput measured one request at a time
is a latency number in costume.

The rejection rate is the one unique to this design: a rise in validator
rejections signals an input-distribution change *before* the label mix visibly
moves, so drift monitoring can watch something better than PSI over labels.

## 2026-09-16 — A held-out split, because the headline number was in-distribution

Every detection rule — the 32-character context window, the gating word lists,
the arbitration order — was tuned by measuring documents built from ten
templates, and the frozen corpus used to report results was built from the same
ten. A different seed does not make a different distribution. Reporting that
number alone would have been grading the rules on the phrasing they were fitted
to.

Four new templates were written before any result on them was seen, in phrasing
the tuning set never uses: a first-person hardship letter ("her Social Security
number is"), an escrow email thread with a quoted reply ("ABA …, acct …"), a
bankruptcy referral memo, and a title curative note. The corpus built from them
is report-only. A test asserts the two template sets share nothing.

Result: strict micro-F1 0.977 on both. The aggregate generalises; individual
types do not uniformly — `LOAN_NUMBER` recall falls to 0.747, while
`US_ACCOUNT_NUM` rises from 0.778 to 0.941.

The honest weakness: the same person wrote the rules and the held-out templates,
and knew the context-word lists while writing. A held-out set written by someone
who had not read the rules would be stronger.

Rejected: a random document-level split of one corpus. Documents from the same
template share sentence structure almost exactly, so that split would leak just
as badly as having none.

## 2026-09-16 — The near-miss rejection rate is not a score

The README previously led with "94.4% of adversarial near-misses rejected" as
the number worth reading. Rebuilding the scorer properly showed two problems.

The old probe counted a near-miss as rejected only if *nothing* was kept at its
exact span, which mixed two different outcomes. Separated — rejected as its own
type, versus kept under a different label — rejection is 100% on both splits.

And 100% is guaranteed. The generator only emits adversarial values that
`test_adversarial_spans_fail_their_validators` proves the validator rejects, so
the rate cannot fall unless that test is broken. It verifies the pipeline is
wired correctly; it does not measure detection skill. It stays in the CI gate,
where catching mis-wiring is exactly its job, and comes off the list of results.

The numbers now reported are the ones the generator does not control: how often
PII-shaped distractors get claimed (2.6% tuning, 0.0% held-out), and how many
rejected near-misses were still redacted under a different label (11 of 161,
15 of 149).

## 2026-09-16 — Strict and relaxed matching are both reported

Strict matching requires identical offsets; relaxed accepts any overlap with the
same type, one-to-one. Strict is the headline because redaction that misses a
character leaks it.

Relaxed is reported alongside because the gap diagnoses the failure. Held-out
`PERSON_NAME` is 0.948 strict and 0.978 relaxed: the model finds the names and
draws the boundaries wrong, which calls for span trimming, not a better NER
model. A single number would hide which problem exists.

Predictions that land on a near-miss or a distractor count as false positives
for whatever type was predicted — conservative, since a relabelled near-miss
routing number is arguably a reasonable account-number reading.

## 2026-09-16 — The CI gate: tight tolerances, per-type floors, refuse changed corpora

Strict micro-F1 may not drop more than 0.005 on either split; any type with
support of 20 or more may not lose more than 0.02 F1; rejection may not fall and
distractor claims may not rise. Tolerances are tight because every gated number
is deterministic — they exist to let a small deliberate trade-off through, not to
absorb noise that does not exist.

Per-type floors exist because v1's "improved" run lifted the aggregate while one
type lost 37 points of precision. Types under 20 spans are not gated
individually: one document moves them several points, and a gate that fires on
that is a gate people learn to ignore.

If a corpus's SHA-256 has changed, the gate refuses to compare at all rather than
comparing numbers from different data. Rebaselining is a deliberate `make
baseline`, committed separately so the baseline's recorded commit is the code
that produced it.

## 2026-09-16 — Template prose reflowed; a distractor renamed

Template paragraphs were hard-wrapped mid-sentence, which no servicing system
produces and which made the demo read raggedly. Reflowed, keeping structural
breaks — headers, address blocks, `label: value` lines, tables. Measured before
and after: true positives 1896 → 1897, micro-F1 unchanged at 0.977. A
readability fix, not a hidden metric change.

The distractor "Tier 2" became "Priority 2". It is exactly the kind of thing a
distractor should be, but it collided with the demo's own tier vocabulary and
made the page harder to read.

## 2026-09-16 — Demo redesign: evidence first, strict sandbox, self-hosted type

The first page worked but read as a prototype, opened on a sample with nothing
rejected, and conveyed tier by colour alone with rejection reasons hidden in
hover tooltips — unreachable by keyboard or touch.

Design direction came from the ui-ux-pro-max skill's retrieval over its style,
palette and typography data: Swiss minimalism, slate neutrals, IBM Plex Sans with
JetBrains Mono. Its page-pattern suggestion ("documentation landing") did not fit
an interactive tool and was not used.

- **Tier is carried by underline pattern** — solid, dashed, dotted, struck — as
  well as hue, and by badge text. Selecting any span opens an evidence panel:
  validator, reason, source, and every other reading of those characters that
  was considered and why it lost.
- **Samples are chosen by running the pipeline**, keeping only documents that
  show at least one tier-1 proof and one rejection.
- **Fonts are self-hosted** (SIL OFL, licences committed) instead of loaded from
  Google Fonts, so the page makes no third-party request and works behind a
  bank's egress controls.
- **A strict CSP** with no `unsafe-inline`. That forced a real structural choice:
  no inline script or `style` attributes, so the theme bootstrap is a separate
  blocking file and bar widths are set through the CSSOM. The page renders text
  people paste; the CSP is the backstop if escaping is ever got wrong.
- **Numbers on the page come from `/v1/evaluation`**, the same baseline CI gates
  on, rather than figures typed into HTML.

Verified with axe-core against WCAG 2.2 AA in both themes (0 violations after
fixing one: a tag using `opacity: .75` measured 4.0:1 contrast) and by keyboard.
Neither replaces a screen-reader pass, which has not been done.

Rejected: reintroducing a component framework. The page is one screen of
interaction; a build step would put Node into Docker and CI for no user-visible
gain.

## 2026-10-03 — Over-redaction merges overlapping spans instead of rejecting them

A review found that `redact_failed_tier1=True` returned HTTP 500 on ordinary
input. The cause was two correct rules meeting. Arbitration rule 2 takes a
failed SSN out of contention so that an account number can claim the same
digits; the anonymiser refuses overlapping spans because replacing both would
garble the text. The over-redact policy handed it both. The tests passed only
because every fixture for the flag had a failed SSN with nothing competing for
its characters — the one shape the flag never meets in a real document.

Three resolutions were considered. *Raise* is what it did, and makes the policy
unusable. *Skip any failed span that overlaps something kept* fixes an exact
overlap, but on a partial overlap it leaves the uncovered digits in the output,
under the one policy whose purpose is never to do that. **Merge** was chosen:
the failed tier-1 spans the policy adds are swept together with arbitration's
output into non-overlapping regions, each covering the union of what overlaps.
The overlap guard still applies, unchanged, to arbitration's own output; the
exemption covers only the spans the policy adds.

What a region becomes, as settled over three review passes:

- **A region that is exactly one kept entity** is rewritten as it always was,
  last-four masking included. With nothing else touching it, the policy
  changes nothing.
- **Every other region is never masked.** It contains a failed reading, and
  its last four characters belong, or may belong, to a span a validator
  rejected: "credit to account 666121234" beside an SSN label used to come out
  as `*****1234`, four digits of what may be a mistyped SSN. That includes a
  lone failed card, which becomes `[CARD]` rather than `…1112`.
- **A token names a type for every character it replaces**, so a region is
  typed only when that is true of all of it. A kept entity spanning the whole
  region names it, whatever failed readings lie inside — arbitration's answer
  outranks a rejected one, so a failed SSN exactly under a kept account gives
  `[ACCOUNT]`. Otherwise one type shared by every member names it. Otherwise
  it is `[REDACTED]`: a failed SSN running past the end of a kept address is
  not an address, and two ZIPs bridged by a failed span are not one ZIP.
  Joining the labels (`[ZIP][PHONE]`) was considered and rejected; it implies
  a boundary between two values that the merged region does not have.

A property test asserts that, for arbitrary candidates, exactly the characters
no target touched survive. The output is assembled in one forward pass from
slices of the untouched original, rather than by editing the string back to
front as v1 did: equally offset-safe, and linear.

What this does **not** cover, recorded rather than fixed: a *passing* reading
that loses a partial overlap is dropped whole (arbitration rule 7), so any of
its characters outside the winner stay in the output under every policy, this
one included. That is older and broader than this change, and redacting
overlap losers would change what the default policy does; it needs measuring
before deciding.

## 2026-10-03 — Rejection rate counts validator failures, and nothing else

The response's `rejection_rate` was documented as the share of candidates a
validator rejected, and computed as `dropped / (kept + dropped)`. But `dropped`
also holds valid candidates that lost an overlap or were fragments of a longer
match. "Loan number 0012345678 and account 483920117." reported 0.33 with no
validation failure at all. This is the number pitched as the design's drift
signal — rejections rise when the input moves, before label mix does — and as
computed it tracked how densely number formats overlap instead.

It is now failed readings over readings a validator ran on. Excluded from
both halves: tier-3 readings, which have no validator, so including them would
let a document with more names look like one with fewer rejections; and
fragments of a longer match that survived, which are artefacts rather than
readings — "0165" ending a valid phone number fails the NMLS rules only
because it is a piece of something else, and that happens eleven times in the
frozen corpus. The demo page draws the same line.
Arbitration now also deduplicates failed readings, as it always did passing
ones, so two detectors reporting one failure is one rejection for every
consumer of `dropped`, not just this rate.

It is counted **per reading, not per string**, and that was a choice. "Credit
to account 666121234" beside an SSN label is one failed SSN reading and one
passing account reading: 0.5. Counted per string it would be 0.0, because the
account reading survived — and the failed SSN reading, which is precisely the
signal worth watching, would disappear. The cost is that the denominator
still grows with how many readings overlap a value. Per-type failure rates
would remove that, and are the better metric to build when drift monitoring
is built. The evaluation report's near-miss rejection rate is a different,
gold-labelled measure and was not affected.

The field's meaning changed without a version marker in the response. That
was weighed and left: the service has never been deployed, so no stored
series exists for the change to break. Once one does, a definition change
like this needs a marker.

## 2026-10-03 — How a fragment is reported depends on whether its container survived

Arbitration sets aside a span strictly inside a longer validated match — the
"2021" of a date, the "0165" ending a phone number — before ranking, because
the shorter pattern would otherwise win on tier. But a container can still
lose an overlap afterwards, and then nothing in the output covers the
fragment's characters.

**A fragment is an artefact if and only if a kept, pattern-derived entity
strictly contains it**, and is named after that entity; a failed one keeps
its validator's reason after that, so the arithmetic that rejected it is not
lost (it used to be overwritten). Kept entities never
overlap, so there is at most one, and the reason no longer depends on detector
order as "the first container found" did; the order-independence property test
now covers `dropped` and its reasons. Otherwise **a failed fragment is
reported as an ordinary rejection**. It used to be reported as a fragment
regardless, so a failed SSN inside an address that lost to an EIN was neither
counted in the rejection rate nor redacted under the over-redact policy, and
the demo called it a fragment of something not in the output. This changes
only how a dropped reading is reported, never what is kept, so it cannot
disturb precedence.

Whether a *model* span may vouch for a fragment went back and forth in review,
and the answer is no. Model spans are not trusted as containers anywhere in
arbitration, and allowing one here made a failed SSN an artefact when an
unrelated address candidate existed and a rejection when it did not.

**A passing fragment that nothing kept contains is still dropped, and its
characters still reach the output.** That predates this work, and the attempt
to fix it here was withdrawn after review. Letting such orphans contend after
the first ranking pass broke precedence in two reproduced ways: a tier-1 SSN
orphan lost to a tier-3 name that had been kept only because the SSN was not
yet competing, and nested fragments escaped the fragment rule, so the "2021"
of an orphaned date outranked the date. "What would have won had the fragment
not been set aside" is a fixpoint question; the right fix resolves fragments
inside the single ranked pass, and belongs in its own change. Until then the
reason says so plainly — "inside a longer STREET_ADDRESS match …, which lost
an overlap; dropped with it", naming a container that actually contended — and
the reading carries no fragment marker, so the rejection rate counts it as the
validated, passing reading it is. None of the 133 fragments in either corpus
has a container that lost, so no score moved either way.

Fragment status reaches the rejection rate, the over-redact policy and the
demo page through one helper, `is_rejection`, and on the page through a prefix
of the reason text, which the page copies as a JavaScript constant and a test
pins to the Python one. A structured `outcome` field on each dropped entity
would be sturdier and was deferred rather than rejected: it changes the API
schema that the page and any client read, which deserves its own change.

## 2026-10-03 — Context words stay prefixes, knowingly

Context words match as prefixes, so "tin" opens the SSN gate on "Tina" and
"aba" opens the routing gate on "abandoned". A review flagged it, and three
fixes were tried and reviewed in turn. Each traded that over-detection for
misses on real labels:

| Rule tried | What it lost |
|---|---|
| Whole-word, every context word | "Loans", "Remittance", "Deposited", "SS#457551275" |
| Whole-word for words of ≤ 4 characters | "wired", "loaned", "noted", "ACCT_NO", "FICO8"; and quadratic search time, 6 s on 108 KB |
| Whole-word for abbreviations (written in capitals) | "NMLSR ID" — the industry's standard originator label — "AcctNo", "SSNum", "FICOScore"; and "Abas", "Tins" still matched |

The two sides are not symmetric. Over-detection redacts digits that were not
the gated type; a miss leaves PII in the output. For a redactor the second is
the failure that matters, so **prefix matching stays**, and "Tina" is a known,
accepted over-detection. The first fix was also justified by "no context word
occurs in either corpus as a prefix", which is the same blind spot as the
original bug: the synthetic corpus cannot contain what its templates never
wrote, so it measures neither side. Deciding this properly needs evaluation
text with real field labels, inflections and names, which does not exist yet.
Parametrised tests pin the recall side, and a timing test guards the bounded
window search.

## 2026-10-03 — Context matching reads the original text, with ASCII-only folding

The detector lowercased the document and searched the copy using offsets from
the original. Lowercasing is not length-preserving — `"İ"` becomes two
characters — so the copy drifted one character per such letter, and a Turkish
borrower name was enough to change a reported context distance, which is an
arbitration tiebreak. Context words are now matched case-insensitively against
the original. Rejected: keeping the lowercased copy with an offset map back to
the original, which is more code to get wrong for the same result; and plain
`re.IGNORECASE`, which was the first fix and folds Unicode lookalikes, so
"ſſn" (long s) opened the SSN gate where lowercasing never had. The folding is
scoped as `(?ai:...)`, ASCII-only, which keeps `\b` Unicode-aware so "éssn"
still is not "ssn". Unlike prefix matching, neither change trades anything
away. Scores on both corpora are byte-identical before and after: the
synthetic names never contain these letters, which is why the evaluation could
not have caught it.

## 2026-10-03 — The gate compares like with like, or refuses

The gate already refused a changed corpus. It now also refuses a different
engine or taxonomy version. Scoring the regex-only engine against the presidio
baseline used to report PERSON_NAME and CITY as collapsing — true, and not a
regression — and a taxonomy bump over an unchanged corpus would have compared
two label spaces. Rejected: reporting the per-type differences with a warning,
because a gate that prints failures it does not mean teaches people to ignore
it. One function holds the rule and both call sites ask it.

A plain `--check` refuses before loading a model or scoring anything; with
`--out` the report is written first, because it was asked for. `--check` and
`--write-baseline` are now mutually exclusive. Together they compared a run
with the baseline it had just written, which always passes; the alternative,
comparing against the previous baseline before overwriting it, makes one
command both record and judge, and recording a baseline is meant to be a
separate, deliberate commit.

## 2026-10-03 — Also from the review

- **Package data is globbed recursively.** `web/static/*` built a wheel holding
  `index.html` without its CSS, JavaScript, fonts or font licences. The Docker
  image was unaffected, because it copies `app/` rather than installing it.
- **Arbitration is quadratic in the number of candidates, and is not fixed
  here.** The review measured 4.7 s for a crafted 199 KB document, within the
  200 KB request limit, so the size limit does not bound worker time. (The
  detector's window search was always bounded; a version written during this
  review briefly was not, and a timing test now guards against that.) Both of its loops scan everything
  kept so far; an interval structure would make them logarithmic. It predates
  this work and touches the core ranking, so it is recorded for its own change.
- **A multi-word context word shrinks its own window, and is not fixed here.**
  The window search requires a context word to lie wholly inside it, so
  "Social Security" 18 characters before an SSN opens no gate while "SSN" at
  the same distance does. Starting the search earlier would fix it, and would
  change context distances, which are an arbitration tiebreak; it predates
  this work and needs measuring.
- **The container was first built by CI on 2026-10-02**: 546 MB, ready 3 s
  after a cold start with networking disabled. That is over the 400 MB the
  plan set as a target, and where the size goes has not been broken down yet.
