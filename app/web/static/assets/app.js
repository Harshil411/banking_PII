// Mortgage PII Service — demo page.
//
// Rendering rules this file keeps:
//  * Pasted text is never parsed as HTML. Every node is built with
//    createElement/textContent, and the page's CSP forbids inline script as a
//    backstop.
//  * Highlighting trusts the offsets the server reports. Nothing is re-found
//    client side, so the page and the API cannot disagree about a span.
//  * Tier is never conveyed by colour alone: underline pattern, badge text and
//    icon carry it too.

const $ = (selector, root = document) => root.querySelector(selector);

const TIER = {
  1: { name: "Tier 1", short: "arithmetic proof", cls: "t1",
       blurb: "A checksum or issuing rule can prove the value impossible, so a pass is strong evidence." },
  2: { name: "Tier 2", short: "structural rule", cls: "t2",
       blurb: "A deterministic rule rejects values the pattern accepts: prefixes, ranges, closed sets." },
  3: { name: "Tier 3", short: "context only", cls: "t3",
       blurb: "No rule can confirm it. The evidence is the surrounding text, or a language model." },
};
const ICON = {
  1: "M5 12.5l4.2 4.2L19 7",
  2: "M4 7h16M4 12h16M4 17h10",
  3: "M5 7h14M5 12h9M5 17h12",
  rej: "M6.5 6.5l11 11M17.5 6.5l-11 11",
  outranked: "M12 5v14M6 13l6 6 6-6",
};

const state = { ready: false, samples: [], taxonomy: null, result: null, text: "", view: "highlight", selected: null };

// ------------------------------------------------------------------ helpers

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function svg(path, cls = "") {
  const ns = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(ns, "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  if (cls) icon.setAttribute("class", cls);
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", path);
  icon.append(p);
  return icon;
}

const pct = (x) => `${(x * 100).toFixed(1)}%`;
const f3 = (x) => Number(x).toFixed(3);
const overlaps = (a, b) => a.start < b.end && b.start < a.end;

async function getJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || `${url} returned HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

// ------------------------------------------------------------------ segments
//
// Pure: turns the source text plus server-reported spans into an ordered list
// of plain-text runs and marked runs. tests/test_demo_page.py re-implements
// this walk in Python and asserts that joining the runs reproduces the text.

export function segments(text, entities, dropped) {
  const kept = [...entities].sort((a, b) => a.start - b.start || a.end - b.end);

  // Spans a validator rejected are drawn too, so a near-miss is visible in the
  // document -- unless a kept entity already occupies those characters.
  const failed = dropped
    .filter((d) => d.validation_status === "fail" && !kept.some((k) => overlaps(k, d)))
    .sort((a, b) => a.start - b.start || a.tier - b.tier);

  const marks = [];
  for (const entity of kept) marks.push({ primary: entity, rejected: false });
  for (const candidate of failed) {
    const existing = marks.find((m) => m.rejected && overlaps(m.primary, candidate));
    if (!existing) marks.push({ primary: candidate, rejected: true });
  }
  marks.sort((a, b) => a.primary.start - b.primary.start);

  for (const mark of marks) {
    mark.alternatives = dropped.filter((d) => d !== mark.primary && overlaps(d, mark.primary));
  }

  const runs = [];
  let cursor = 0;
  for (const mark of marks) {
    const { start, end } = mark.primary;
    if (start < cursor) continue;
    if (start > cursor) runs.push({ text: text.slice(cursor, start) });
    runs.push({ text: text.slice(start, end), mark });
    cursor = end;
  }
  if (cursor < text.length) runs.push({ text: text.slice(cursor) });
  return runs;
}

// ------------------------------------------------------------------ theme

function initTheme() {
  $("#theme").addEventListener("click", () => {
    const root = document.documentElement;
    const current = root.dataset.theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (_) { /* not persisted */ }
  });
}

// ------------------------------------------------------------------ status

function setStatus(message, isError = false) {
  const box = $("#status");
  box.hidden = !message;
  box.classList.toggle("error", isError);
  $("#status-text").textContent = message || "";
}

async function waitForReady() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await fetch("readyz");
      if (response.ok) {
        const body = await response.json();
        $("#engine").textContent = `engine ${body.engine}`;
        $("#version").textContent = `taxonomy ${body.taxonomy_version}`;
        setStatus("");
        return true;
      }
      const body = await response.json().catch(() => ({}));
      if (body.detail && !/warming|starting/i.test(body.detail)) {
        setStatus(`The service failed to start: ${body.detail}`, true);
        return false;
      }
    } catch (_) { /* server not accepting connections yet */ }
    setStatus("Starting the service and loading the language model — a cold start takes a few seconds…");
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  setStatus("The service did not become ready. Try reloading the page.", true);
  return false;
}

// ------------------------------------------------------------------ document panel

function renderSamples() {
  const group = $("#samples");
  group.replaceChildren(...state.samples.map((sample, index) =>
    el("button", {
      type: "button", class: "chip", "aria-pressed": index === 0 ? "true" : "false",
      onclick: (event) => loadSample(index, event.currentTarget),
    }, sample.label, sample.split === "held_out" ? el("span", { class: "tag", text: "held-out" }) : null),
  ));
}

function loadSample(index, button) {
  for (const chip of $("#samples").children) chip.setAttribute("aria-pressed", String(chip === button));
  $("#text").value = state.samples[index].text;
  updateCount();
  analyze();
}

function updateCount() {
  const n = $("#text").value.length;
  $("#char-count").textContent = n ? `${n.toLocaleString()} chars` : "";
}

// ------------------------------------------------------------------ analysis

async function analyze() {
  const text = $("#text").value;
  if (!text.trim()) {
    $("#summary").textContent = "Enter or pick a document first.";
    return;
  }
  if (!state.ready) return;

  const button = $("#analyze");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  $(".btn-label", button).textContent = "Analyzing…";
  $("#out").classList.add("loading");
  $("#result-card").setAttribute("aria-busy", "true");

  try {
    const result = await getJSON("v1/anonymize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    state.result = result;
    state.text = text;
    state.selected = null;
    renderResult();
    selectDefault();
  } catch (error) {
    state.result = null;
    $("#out").replaceChildren(el("p", { class: "empty", role: "alert", text: `Analysis failed: ${error.message}` }));
    $("#summary").textContent = "";
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    $(".btn-label", button).textContent = "Analyze";
    $("#out").classList.remove("loading");
    $("#result-card").removeAttribute("aria-busy");
  }
}

function renderResult() {
  const r = state.result;
  const failedChecks = r.dropped.filter((d) => d.validation_status === "fail").length;
  $("#summary").replaceChildren(
    el("strong", { text: r.entities.length }), " entities · ",
    el("strong", { text: failedChecks }), " failed a check · ",
    el("strong", { text: `${r.timing_ms.total.toFixed(1)} ms` }),
  );
  renderOutput();
  renderBreakdown();
  renderDropped();
}

function renderOutput() {
  const out = $("#out");
  if (!state.result) return;

  $(".legend").hidden = state.view === "redact";
  $("#policy-note").hidden = state.view !== "redact";
  if (state.view === "redact") {
    // Styling only: tokens are recognised in the server's redacted text to
    // draw them as blocks. The redaction itself was done server side.
    // split() with a capture group puts the matched tokens at odd indices.
    const parts = state.result.redacted.split(/(\[[A-Z_]+\]|\*{3,}[A-Za-z0-9]{0,4})/);
    out.replaceChildren(...parts.map((part, i) =>
      i % 2 === 1 ? el("span", { class: "redaction", text: part }) : document.createTextNode(part)));
    return;
  }

  const runs = segments(state.text, state.result.entities, state.result.dropped);
  out.replaceChildren(...runs.map((run) => {
    if (!run.mark) return document.createTextNode(run.text);
    const { primary, rejected } = run.mark;
    const cls = rejected ? "rej" : TIER[primary.tier].cls;
    const label = rejected
      ? `${primary.entity_type}, rejected: ${primary.reason}`
      : `${primary.entity_type}, ${TIER[primary.tier].name}, ${primary.validation_status.replace("_", " ")}`;
    const mark = el("mark", {
      class: `ent ${cls}`, tabindex: "0", role: "button", "aria-pressed": "false", "aria-label": label,
      onclick: () => select(run.mark, mark),
      onkeydown: (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(run.mark, mark); }
      },
    }, run.text);
    run.mark.node = mark;
    return mark;
  }));
}

function selectDefault() {
  if (state.view !== "highlight") return;
  const runs = [...$("#out").querySelectorAll(".ent")];
  const preferred = runs.find((n) => n.classList.contains("rej")) ||
                    runs.find((n) => n.classList.contains("t1")) || runs[0];
  if (preferred) preferred.click();
  else renderInspector(null);
}

function select(mark, node) {
  for (const other of $("#out").querySelectorAll(".ent[aria-pressed='true']")) other.setAttribute("aria-pressed", "false");
  node.setAttribute("aria-pressed", "true");
  state.selected = mark;
  renderInspector(mark);
}

// ------------------------------------------------------------------ inspector

function tierBadge(tier) {
  const t = TIER[tier];
  return el("span", { class: `badge ${t.cls}` }, svg(ICON[tier]), `${t.name} · ${t.short}`);
}

function statusBadge(entity, rejected) {
  if (rejected) return el("span", { class: "badge rej" }, svg(ICON.rej), "Rejected");
  if (entity.validation_status === "pass") return el("span", { class: "badge neutral" }, svg(ICON[1]), "Check passed");
  return el("span", { class: "badge neutral", text: "No rule applies" });
}

function outcomeOf(candidate) {
  if (candidate.validation_status === "fail") return { cls: "fail", icon: ICON.rej, label: "Failed check" };
  if (candidate.reason.startsWith("fragment")) return { cls: "outranked", icon: ICON.outranked, label: "Fragment" };
  return { cls: "outranked", icon: ICON.outranked, label: "Outranked" };
}

function renderInspector(mark) {
  const box = $("#inspector");
  if (!mark) {
    box.replaceChildren(el("p", { class: "empty", text: "Select a highlighted span to see which rule confirmed it — or rejected it." }));
    return;
  }
  const { primary: e, rejected, alternatives } = mark;
  const cls = rejected ? "rej" : TIER[e.tier].cls;
  const facts = [
    ["Value", el("span", { class: "mono", text: e.text })],
    ["Validator", e.validator ? el("span", { class: "mono", text: e.validator }) : "none — tier 3 has no rule to run"],
    ["Found by", e.source === "presidio" ? "spaCy NER via Presidio" : "taxonomy pattern"],
    ["Score", e.source === "presidio" ? e.score.toFixed(2) : "n/a (pattern match)"],
    ["Offsets", el("span", { class: "mono", text: `${e.start}–${e.end}` })],
  ];

  const children = [
    el("div", { class: "inspector-head" },
      el("span", { class: "inspector-type", text: e.entity_type }), tierBadge(e.tier), statusBadge(e, rejected)),
    el("dl", { class: "facts" }, facts.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, v)])),
    el("p", { class: `reason ${cls}` },
      el("strong", { text: rejected ? "Why it was rejected: " : "Evidence: " }), e.reason),
  ];

  if (alternatives.length) {
    children.push(el("p", { class: "alternatives-title", text: "Also considered for these characters" }));
    children.push(el("ul", { class: "alternatives" }, alternatives.map((alt) => {
      const outcome = outcomeOf(alt);
      return el("li", {},
        el("span", {}, el("span", { class: "mono", text: alt.entity_type }),
          el("span", { class: "alt-reason", text: alt.reason })),
        el("span", { class: `outcome ${outcome.cls}` }, svg(outcome.icon), outcome.label));
    })));
  }
  box.replaceChildren(...children);
}

// ------------------------------------------------------------------ breakdown

function renderBreakdown() {
  const r = state.result;
  const counts = [1, 2, 3].map((t) => r.counts_by_tier[`tier_${t}`] || 0);
  const total = counts.reduce((a, b) => a + b, 0);
  const bar = el("div", { class: "bar", role: "img",
    "aria-label": `Tier 1: ${counts[0]}, tier 2: ${counts[1]}, tier 3: ${counts[2]}` });
  counts.forEach((n, i) => {
    const part = el("span", { class: `t${i + 1}` });
    part.style.width = total ? `${(n / total) * 100}%` : "0";  // CSSOM, permitted by the CSP
    bar.append(part);
  });

  const failed = r.dropped.filter((d) => d.validation_status === "fail").length;
  const row = (key, label, value) =>
    el("div", { class: "stat-row" }, el("dt", {}, key ? el("span", { class: `key ${key}` }) : null, label), el("dd", { text: value }));

  $("#breakdown").replaceChildren(
    bar,
    el("dl", { class: "stat-rows" },
      row("t1", "Tier 1 · arithmetic proof", counts[0]),
      row("t2", "Tier 2 · structural rule", counts[1]),
      row("t3", "Tier 3 · context only", counts[2]),
      row("rej", "Failed a validator", failed),
      row(null, "Outranked or fragment", r.dropped.length - failed),
      row(null, "Detect / arbitrate", `${r.timing_ms.detect.toFixed(1)} / ${r.timing_ms.arbitrate.toFixed(2)} ms`),
    ),
  );
}

// ------------------------------------------------------------------ discarded table

function renderDropped() {
  const dropped = state.result.dropped;
  $("#dropped-card").hidden = dropped.length === 0;
  $("#dropped-count").textContent = `${dropped.length}`;
  $("#dropped tbody").replaceChildren(...dropped.map((d) => {
    const outcome = outcomeOf(d);
    return el("tr", {},
      el("td", { class: "mono", text: d.entity_type }),
      el("td", { class: "mono", text: d.text }),
      el("td", {}, el("span", { class: `outcome ${outcome.cls}` }, svg(outcome.icon), outcome.label)),
      el("td", { text: d.reason }));
  }));
}

// ------------------------------------------------------------------ how it works

function renderTiers() {
  if (!state.taxonomy) return;
  $("#tiers").replaceChildren(...[1, 2, 3].map((tier) => {
    const names = state.taxonomy.entities.filter((e) => e.tier === tier).map((e) => e.name);
    return el("article", { class: `card tier ${TIER[tier].cls}` },
      el("h3", {}, tierBadge(tier)),
      el("p", { text: TIER[tier].blurb }),
      el("ul", { class: "type-list", "aria-label": `${TIER[tier].name} types` }, names.map((n) => el("li", { text: n }))));
  }));
}

// ------------------------------------------------------------------ evaluation

function renderEvaluation(report) {
  const splits = report.splits;
  const held = splits.held_out;
  const tuning = splits.in_distribution;

  $("[data-kpi=heldF1]").textContent = f3(held.strict.micro.f1);
  $("[data-kpi=inF1]").textContent = f3(tuning.strict.micro.f1);
  $("[data-kpi=claims]").textContent = pct(held.distractors.claim_rate);
  if (state.taxonomy) $("[data-kpi=types]").textContent = `${state.taxonomy.entities.length} · 3`;
  $("#kpi-source").textContent =
    `From the committed CI baseline (commit ${report.commit}, ${report.date}). Synthetic documents this project generated — a ceiling, not a guarantee.`;

  const card = (key, title) => {
    const s = splits[key];
    const row = (label, value) => el("div", { class: "stat-row" }, el("dt", { text: label }), el("dd", { text: value }));
    return el("article", { class: "card split" },
      el("h3", { class: "split-title", text: title }),
      el("p", { class: "split-sub", text: `${s.documents} documents from ${s.corpus.templates.length} templates · ${s.corpus.spans.toLocaleString()} labelled spans` }),
      el("p", { class: "split-big", text: f3(s.strict.micro.f1) }),
      el("p", { class: "split-big-label", text: "strict micro-F1 (type and exact offsets)" }),
      el("dl", { class: "stat-rows" },
        row("Precision / recall", `${f3(s.strict.micro.precision)} / ${f3(s.strict.micro.recall)}`),
        row("Relaxed micro-F1 (any overlap)", f3(s.relaxed.micro.f1)),
        row("Macro-F1 across types", f3(s.strict.macro_f1)),
        row("Distractors wrongly claimed", `${pct(s.distractors.claim_rate)} of ${s.distractors.total}`),
        row("Near-misses redacted under another label", `${s.adversarial.relabelled} of ${s.adversarial.total}`),
        row("Latency p50 / p95 (in-process)", `${s.latency_ms.p50} / ${s.latency_ms.p95} ms`)));
  };
  $("#splits").replaceChildren(card("in_distribution", "Tuning templates"), card("held_out", "Held-out templates"));

  const tierOf = Object.fromEntries((state.taxonomy?.entities || []).map((e) => [e.name, e.tier]));
  const types = [...new Set([...Object.keys(tuning.per_type), ...Object.keys(held.per_type)])]
    .sort((a, b) => (tierOf[a] || 9) - (tierOf[b] || 9) || a.localeCompare(b));

  const f1Cell = (row) => {
    if (!row || !row.support) return el("td", { class: "num" }, el("span", { class: "empty", text: "—" }));
    const weak = row.f1 < 0.9;
    const fill = el("span");
    fill.style.width = `${row.f1 * 100}%`;
    return el("td", { class: "num" },
      el("span", { class: `f1${weak ? " weak" : ""}` },
        weak ? el("span", { class: "weak-tag", text: "weak" }) : null,
        el("span", { class: "f1-bar", "aria-hidden": "true" }, fill), f3(row.f1)));
  };

  $("#types tbody").replaceChildren(...types.map((name) => {
    const a = tuning.per_type[name];
    const b = held.per_type[name];
    const tier = tierOf[name];
    return el("tr", {},
      el("td", { class: "mono", text: name }),
      el("td", {}, tier ? el("span", { class: `badge ${TIER[tier].cls}`, text: `T${tier}` }) : ""),
      f1Cell(a), f1Cell(b),
      el("td", { class: "num mono", text: `${a?.support ?? 0} / ${b?.support ?? 0}` }));
  }));

  $("#eval-source").textContent =
    "Near-miss rejection is 100% on both splits by construction — the generator only emits values a test proves the " +
    "validator rejects — so it verifies wiring and is not presented as a score. F1 below 0.90 is marked weak.";
}

// ------------------------------------------------------------------ boot

async function boot() {
  initTheme();
  $("#text").addEventListener("input", updateCount);
  $("#text").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); analyze(); }
  });
  $("#analyze").addEventListener("click", analyze);
  $("#clear").addEventListener("click", () => {
    $("#text").value = "";
    updateCount();
    state.result = null;
    $("#out").replaceChildren();
    $("#summary").textContent = "";
    $("#dropped-card").hidden = true;
    renderInspector(null);
    $("#breakdown").replaceChildren(el("p", { class: "empty", text: "Run an analysis to see how the entities split across tiers." }));
    for (const chip of $("#samples").children) chip.setAttribute("aria-pressed", "false");
    $("#text").focus();
  });
  for (const button of document.querySelectorAll(".seg-btn")) {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      for (const b of document.querySelectorAll(".seg-btn")) b.setAttribute("aria-pressed", String(b === button));
      renderOutput();
      if (state.view === "highlight" && state.selected) {
        const again = [...$("#out").querySelectorAll(".ent")].find((n) => n.textContent === state.selected.primary.text);
        if (again) again.setAttribute("aria-pressed", "true");
      }
    });
  }

  try {
    state.samples = await getJSON("assets/samples.json");
    renderSamples();
    if (state.samples.length) { $("#text").value = state.samples[0].text; updateCount(); }
  } catch (_) { /* the page still works with pasted text */ }

  state.ready = await waitForReady();
  if (!state.ready) return;

  const [taxonomy, evaluation] = await Promise.allSettled([getJSON("v1/taxonomy"), getJSON("v1/evaluation")]);
  if (taxonomy.status === "fulfilled") { state.taxonomy = taxonomy.value; renderTiers(); }
  if (evaluation.status === "fulfilled") renderEvaluation(evaluation.value);
  else $("#splits").replaceChildren(el("p", { class: "empty", text: "No evaluation baseline is loaded on this deployment." }));

  if ($("#text").value.trim()) analyze();
}

boot();
