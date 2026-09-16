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
computable without it.

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
