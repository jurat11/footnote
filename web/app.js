// Footnote static demo: loads pre-computed, verified report bundles and renders them.
// No server, no API key. The bundles are the exact deterministic output of the pipeline.

const $ = (sel) => document.querySelector(sel);

marked.setOptions({ gfm: true, breaks: false });

function fmtMoney(v) {
  const s = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}K`;
  return `${s}$${a.toFixed(0)}`;
}
function fmtValue(v, unit) {
  if (v === null || v === undefined) return "n/a";
  const u = (unit || "").toLowerCase();
  if (u === "%") return `${(v * 100).toFixed(1)}%`;
  if (u === "x" || u === "ratio") return `${v.toFixed(2)}x`;
  if (u === "usd") return fmtMoney(v);
  if (u.startsWith("usd/")) return `$${v.toFixed(2)}`;
  return `${v.toLocaleString()}`;
}

async function loadTicker(t) {
  const base = `data/${t}`;
  const [md, ledger, footnotes, verification] = await Promise.all([
    fetch(`${base}/report.md`).then((r) => r.text()),
    fetch(`${base}/ledger.json`).then((r) => r.json()),
    fetch(`${base}/footnotes.json`).then((r) => r.json()),
    fetch(`${base}/verification.json`).then((r) => r.json()),
  ]);

  // Badge
  const badge = $("#badge");
  if (verification.ok) {
    badge.textContent = `verified · ${verification.token_count} numbers cited`;
    badge.style.display = "";
  } else {
    badge.textContent = "verification failed";
  }

  // Render report markdown, then make [n] markers clickable.
  const fnById = {}; // token_id -> number
  const idByNum = {}; // number -> token_id
  footnotes.forEach((fn) => {
    fnById[fn.token_id] = fn.number;
    idByNum[fn.number] = fn.token_id;
  });

  let html = marked.parse(md);
  // Wrap [n] markers (but not inside code) with clickable spans.
  html = html.replace(/\[(\d+)\]/g, (m, n) => {
    if (idByNum[n]) return `<span class="fn" data-id="${idByNum[n]}" data-n="${n}">[${n}]</span>`;
    return m;
  });
  $("#report").innerHTML = html;

  // Build ledger table.
  const tbody = $("#ledger tbody");
  tbody.innerHTML = "";
  const addRow = (id, kind, metric, fy, valueText, source, sourceHref) => {
    const tr = document.createElement("tr");
    tr.className = kind;
    tr.dataset.id = id;
    const srcCell = sourceHref
      ? `<a href="${sourceHref}" target="_blank" rel="noopener">${source}</a>`
      : source;
    tr.innerHTML = `<td>${metric}</td><td>${fy}</td><td class="val">${valueText}</td><td class="src">${srcCell}</td>`;
    tbody.appendChild(tr);
  };

  const facts = Object.values(ledger.facts).sort(
    (a, b) => a.label.localeCompare(b.label) || b.fiscal_year - a.fiscal_year
  );
  facts.forEach((f) =>
    addRow(f.id, "fact", f.label, `FY${f.fiscal_year}`, fmtValue(f.value, f.unit),
      `${f.form} · us-gaap:${f.xbrl_tag}`, f.source_url)
  );
  const ratios = Object.values(ledger.ratios).sort(
    (a, b) => a.label.localeCompare(b.label) || b.fiscal_year - a.fiscal_year
  );
  ratios.forEach((r) =>
    addRow(r.id, "ratio", r.label, `FY${r.fiscal_year}`,
      r.value === null ? "n/a" : fmtValue(r.value, r.unit), r.formula, null)
  );

  wireFootnotes();
}

let activeFn = null;
function wireFootnotes() {
  const report = $("#report");
  report.querySelectorAll(".fn").forEach((el) => {
    el.addEventListener("click", () => highlight(el.dataset.id, el));
  });
}

function highlight(id, el) {
  document.querySelectorAll("#ledger tbody tr.hl").forEach((r) => r.classList.remove("hl"));
  document.querySelectorAll(".fn.active").forEach((f) => f.classList.remove("active"));
  const row = document.querySelector(`#ledger tbody tr[data-id="${CSS.escape(id)}"]`);
  if (row) {
    row.classList.add("hl");
    row.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  if (el) el.classList.add("active");
  activeFn = id;
}

async function init() {
  const tickers = await fetch("data/index.json").then((r) => r.json());
  const sel = $("#ticker");
  tickers.forEach((t) => {
    const o = document.createElement("option");
    o.value = t;
    o.textContent = t;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => loadTicker(sel.value));
  await loadTicker(tickers[0]);
}

init().catch((e) => {
  $("#report").textContent = "Failed to load: " + e.message;
});
