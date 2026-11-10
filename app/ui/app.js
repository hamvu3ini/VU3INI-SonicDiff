/* VU3INI SonicDiff — interface logic (plain JavaScript, no build step, all libraries local). */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 3) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (typeof v !== "number") return esc(v);
  if (Number.isInteger(v)) return String(v);
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(Math.max(0, d - 1 - Math.floor(Math.log10(a))));
  if (a >= 0.001) return v.toFixed(d);
  return v.toExponential(1);
};
const sec = (v) => (v == null ? "–" : `${Number(v).toFixed(1)} s`);

const state = { study: null, info: null, samples: [], tab: "project", labels: {}, sysinfo: null };

// ---------------------------------------------------------------- helpers
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "bad" ? 7000 : 3500);
}

async function api(method, url, body, opts = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(url, init); } catch (e) { toast("The SonicDiff engine is not responding. Is it still running?", "bad"); throw e; }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const msg = (data && data.error) || `${r.status} ${r.statusText}`;
    if (!opts.quiet) toast(msg, "bad");
    throw new Error(msg);
  }
  return data;
}
const S = (path) => `/api/studies/${encodeURIComponent(state.study)}${path}`;

function table(el, cols, rows, opts = {}) {
  const host = typeof el === "string" ? $(el) : el;
  if (!rows.length) { host.innerHTML = `<p class="muted small">${opts.empty || "Nothing yet."}</p>`; return; }
  const head = cols.map((c) => `<th${c.num ? ' style="text-align:right"' : ""}>${esc(c.h)}</th>`).join("");
  const body = rows.map((r, i) => `<tr data-i="${i}" class="${opts.onClick ? "click" : ""} ${opts.selected && opts.selected(r) ? "sel" : ""}">` +
    cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.html ? c.html(r) : esc(r[c.k])}</td>`).join("") + "</tr>").join("");
  host.innerHTML = `<table class="t"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  if (opts.onClick) $$("tbody tr", host).forEach((tr) => tr.addEventListener("click", (e) => {
    if (e.target.closest("button,select,input,a")) return;
    opts.onClick(rows[+tr.dataset.i], tr);
  }));
}
const chip = (s, label) => `<span class="chip ${esc(s)}">${esc(label ?? s)}</span>`;

async function pollJob(job, progEl, msgEl) {
  for (;;) {
    const j = await api("GET", `/api/jobs/${job.id}`, undefined, { quiet: true });
    if (progEl) progEl.style.width = `${Math.round((j.progress || 0) * 100)}%`;
    if (msgEl) msgEl.textContent = j.message || "";
    updateJobBadge();
    if (j.status === "done") return j.result;
    if (j.status === "error") { toast(j.error || "Job failed", "bad"); throw new Error(j.error); }
    await new Promise((r) => setTimeout(r, 700));
  }
}

async function updateJobBadge() {
  try {
    const js = await api("GET", "/api/jobs", undefined, { quiet: true });
    const active = js.filter((j) => j.status === "running" || j.status === "queued");
    const b = $("#jobBadge");
    if (active.length) { b.classList.remove("hidden"); b.textContent = `${active.length} job${active.length > 1 ? "s" : ""} running · ${active[0].label}`; }
    else b.classList.add("hidden");
  } catch (e) { /* engine busy */ }
}

function plotTheme() {
  const cs = getComputedStyle(document.documentElement);
  const ink = cs.getPropertyValue("--ink").trim(), grid = cs.getPropertyValue("--border").trim();
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: ink, family: "Segoe UI, Noto Sans, sans-serif", size: 12 },
    xaxis: { gridcolor: grid, zerolinecolor: grid }, yaxis: { gridcolor: grid, zerolinecolor: grid },
    margin: { l: 60, r: 20, t: 30, b: 45 }, legend: { orientation: "h", y: -0.2 },
  };
}
const PALETTE = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];
const groupColor = (g, all) => PALETTE[Math.max(0, all.indexOf(g)) % PALETTE.length];

// ---------------------------------------------------------------- theme
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  $("#themeLight").setAttribute("aria-pressed", t === "light");
  $("#themeDark").setAttribute("aria-pressed", t === "dark");
  try { localStorage.setItem("sd-theme", t); } catch (e) { /* storage may be off */ }
  api("PUT", "/api/settings", { theme: t }, { quiet: true }).catch(() => {});
  if (waves.seg) waves.seg.setOptions(waveColors());
  if (waves.rh) waves.rh.setOptions(waveColors());
  $$(".plot").forEach((p) => { if (p.data) Plotly.relayout(p, plotTheme()); });
}
$("#themeLight").onclick = () => applyTheme("light");
$("#themeDark").onclick = () => applyTheme("dark");

// ---------------------------------------------------------------- tabs
function showTab(name) {
  if (state.tab === "segment" && name !== "segment" && waves.seg) { waves.seg.destroy(); waves.seg = null; }
  if (state.tab === "rhythm" && name !== "rhythm" && waves.rh) { waves.rh.destroy(); waves.rh = null; rhRegions = null; }
  state.tab = name;
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `p-${name}`));
  const fn = loaders[name];
  if (fn) fn().catch((e) => console.error(e));
}
$$("#nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function updateNav() {
  $$("#nav button[data-needs=study]").forEach((b) => (b.disabled = !state.study));
}

// ---------------------------------------------------------------- study selection
async function loadStudies() {
  const list = await api("GET", "/api/studies");
  const sel = $("#studyPick");
  sel.innerHTML = `<option value="">— none —</option>` + list.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  sel.value = state.study || "";
  const host = $("#studyList");
  if (!list.length) host.innerHTML = `<p class="muted">No studies yet. Create one, or load the demo study.</p>`;
  else table(host, [
    { h: "Study", html: (r) => `<b>${esc(r.name)}</b>` },
    { h: "Samples", k: "samples", num: true },
    { h: "Constants", html: (r) => (r.locked ? chip("ok", "locked") : chip("neutral", "editable")) },
    { h: "", html: (r) => `<button class="btn sm" data-open="${esc(r.id)}">Open</button>` },
  ], list, { selected: (r) => r.id === state.study });
  $$("[data-open]", host).forEach((b) => (b.onclick = () => openStudy(b.dataset.open)));
  return list;
}
$("#studyPick").onchange = (e) => openStudy(e.target.value || null);

async function openStudy(id) {
  state.study = id;
  try { localStorage.setItem("sd-study", id || ""); } catch (e) { /* ignore */ }
  updateNav();
  $("#studyPick").value = id || "";
  if (!id) { $("#studyDetail").classList.add("hidden"); return; }
  await refreshStudy();
  if (state.tab === "project") await loaders.project();
}

async function refreshStudy() {
  state.info = await api("GET", S(""));
  state.samples = await api("GET", S("/samples"));
  $("#singerList").innerHTML = state.info.singers.map((s) => `<option value="${esc(s.code)}">${esc(s.name || "")}</option>`).join("");
}

function sampleOptions(sel, filter = () => true, keep = true) {
  const old = sel.value;
  const rows = state.samples.filter(filter);
  sel.innerHTML = rows.length ? rows.map((r) => `<option value="${r.id}">${esc(r.code)} · ${esc(r.filename)}${r.qc_status === "reject" ? " (rejected)" : ""}</option>`).join("")
    : `<option value="">no samples</option>`;
  if (keep && rows.some((r) => String(r.id) === old)) sel.value = old;
}

// ---------------------------------------------------------------- 1 PROJECT
const loaders = {};
loaders.project = async () => {
  await loadStudies();
  if (!state.study) { $("#studyDetail").classList.add("hidden"); return; }
  $("#studyDetail").classList.remove("hidden");
  const inf = state.info;
  const counts = {};
  for (const s of state.samples) counts[s.group_id] = (counts[s.group_id] || 0) + 1;
  const singersBy = await groupSingerCounts();
  table("#groupTable", [
    { h: "Group", k: "name" }, { h: "Role", html: (r) => chip(r.role === "study" ? "neutral" : "flag", r.role) },
    { h: "Samples", html: (r) => counts[r.id] || 0, num: true },
    { h: "Singers", html: (r) => singersBy[r.name] || 0, num: true },
    { h: "Statistics level", html: (r) => levelChip(singersBy[r.name] || 0) },
    { h: "", html: (r) => `<button class="btn sm danger" data-delg="${r.id}">Remove</button>` },
  ], inf.groups, { empty: "No groups." });
  $$("[data-delg]").forEach((b) => (b.onclick = async () => { await api("DELETE", S(`/groups/${b.dataset.delg}`)); await refreshStudy(); loaders.project(); }));
  table("#singerTable", [
    { h: "ID", k: "code" }, { h: "Name", k: "name" }, { h: "Voice", k: "voice_type" }, { h: "Segments", k: "n_segments", num: true },
    { h: "", html: (r) => `<button class="btn sm danger" data-dels="${r.id}">Remove</button>` },
  ], inf.singers, { empty: "No singers yet." });
  $$("[data-dels]").forEach((b) => (b.onclick = async () => { await api("DELETE", S(`/singers/${b.dataset.dels}`)); await refreshStudy(); loaders.project(); }));
  renderConstants(inf.constants, inf.locked);
};
function levelChip(n) {
  if (n >= 8) return chip("pass", "inferential");
  if (n >= 3) return chip("flag", "exploratory");
  return chip("neutral", "case study");
}
async function groupSingerCounts() {
  const segs = await api("GET", S("/segments"));
  const bySample = Object.fromEntries(state.samples.map((s) => [s.id, s]));
  const sets = {};
  for (const g of segs) {
    const smp = bySample[g.sample_id];
    if (!smp || !g.singer_code) continue;
    (sets[smp.group_name] = sets[smp.group_name] || new Set()).add(g.singer_code);
  }
  // samples with a default singer but no segments yet
  for (const s of state.samples) if (s.meta.singer_id) (sets[s.group_name] = sets[s.group_name] || new Set()).add(s.meta.singer_id);
  return Object.fromEntries(Object.entries(sets).map(([k, v]) => [k, v.size]));
}
function renderConstants(c, locked) {
  $("#lockState").className = "chip " + (locked ? "ok" : "neutral");
  $("#lockState").textContent = locked ? "locked" : "editable";
  ["#saveConst", "#lockConst", "#resetConst"].forEach((s) => ($(s).disabled = !!locked));
  const host = $("#constForm");
  host.innerHTML = Object.entries(c).map(([sec_, vals]) =>
    `<div style="margin-top:10px"><div class="small" style="font-weight:600;text-transform:capitalize">${esc(sec_)}</div><div class="formgrid">` +
    Object.entries(vals).map(([k, v]) => `<label class="f">${esc(k.replace(/_/g, " "))}<input data-c="${esc(sec_)}.${esc(k)}" value="${esc(v)}" ${locked ? "disabled" : ""}></label>`).join("") +
    "</div></div>").join("");
}
$("#saveConst").onclick = async () => {
  const c = JSON.parse(JSON.stringify(state.info.constants));
  for (const inp of $$("[data-c]")) {
    const [a, b] = inp.dataset.c.split(".");
    const v = Number(inp.value);
    if (Number.isNaN(v)) { toast(`${b}: not a number`, "bad"); return; }
    c[a][b] = v;
  }
  await api("PUT", S("/constants"), c); toast("Constants saved", "good"); await refreshStudy(); loaders.project();
};
$("#resetConst").onclick = async () => { await api("POST", S("/constants/reset")); await refreshStudy(); loaders.project(); };
$("#lockConst").onclick = async () => {
  if (!confirm("Lock the constants? They cannot be changed afterwards in this study.")) return;
  await api("POST", S("/lock")); await refreshStudy(); loaders.project();
};
$("#createStudy").onclick = async () => {
  const groups = $("#newGroups").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const [n, role] = l.split("|").map((x) => x.trim());
    return { name: n, role: ["archival", "test"].includes(role) ? role : "study" };
  });
  const r = await api("POST", "/api/studies", { name: $("#newName").value, description: $("#newDesc").value, groups });
  toast("Study created", "good");
  $("#newName").value = "";
  await openStudy(r.id);
};
$("#addGroup").onclick = async () => {
  await api("POST", S("/groups"), { name: $("#gName").value, role: $("#gRole").value });
  $("#gName").value = ""; await refreshStudy(); loaders.project();
};
$("#addSinger").onclick = async () => {
  await api("POST", S("/singers"), { code: $("#sgCode").value, name: $("#sgName").value, voice_type: $("#sgVoice").value });
  $("#sgCode").value = ""; $("#sgName").value = ""; await refreshStudy(); loaders.project();
};
$("#demoBtn").onclick = async () => {
  toast("Building the demo study (about a minute)…");
  const r = await api("POST", "/api/demo");
  const res = await pollJob(r);
  await openStudy(res.study);
  toast("Demo study ready: try Analyse, then Compare and Report.", "good");
};

// ---------------------------------------------------------------- 2 IMPORT
const META_FIELDS = [
  ["tradition", "Tradition"], ["piece", "Piece title"], ["raga_or_work", "Raga + tala, or work + key"], ["performer", "Performer"],
  ["singer_id", "Singer ID (default)"], ["voice_type", "Voice type", ["", "male", "female", "other"]], ["age_band", "Age band"],
  ["recording_date", "Recording date"], ["venue", "Venue / room"], ["recorder", "Recorder and mic"], ["mic_distance_m", "Mic distance (m)"],
  ["source", "Source", ["", "studio recording", "field recording", "archive", "commercial", "open dataset"]],
  ["source_ref", "URL / catalogue no."], ["accompaniment", "Accompaniment"], ["rights", "Licence / consent"],
];
function metaForm(host, values = {}, prefix = "md") {
  host.innerHTML = META_FIELDS.map(([k, label, opts]) => opts
    ? `<label class="f">${esc(label)}<select data-${prefix}="${k}">${opts.map((o) => `<option ${values[k] === o ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`
    : `<label class="f">${esc(label)}<input data-${prefix}="${k}" value="${esc(values[k] || "")}"></label>`).join("");
}
function readMeta(host, prefix = "md") {
  const m = {};
  $$(`[data-${prefix}]`, host).forEach((i) => { if (i.value.trim()) m[i.dataset[prefix]] = i.value.trim(); });
  return m;
}
loaders.import = async () => {
  await refreshStudy();
  if (!$("#metaDefaults").children.length) metaForm($("#metaDefaults"));
  $("#impGroup").innerHTML = state.info.groups.map((g) => `<option value="${g.id}">${esc(g.name)}</option>`).join("");
  renderSamples();
};
function renderSamples() {
  const rows = state.samples;
  const c = { pass: 0, flag: 0, reject: 0 };
  rows.forEach((r) => (c[r.qc_status] = (c[r.qc_status] || 0) + 1));
  $("#qcSummary").textContent = `${rows.length} samples · ${c.pass} pass · ${c.flag} flagged · ${c.reject} rejected`;
  table("#sampleTable", [
    { h: "Code", k: "code" }, { h: "File", k: "filename" }, { h: "Group", k: "group_name" },
    { h: "Length", html: (r) => sec(r.duration), num: true },
    { h: "QC", html: (r) => chip(r.qc_status) + (r.meta.qc_override ? ' <span class="small muted">override</span>' : "") },
    { h: "Metadata", html: (r) => (r.meta_missing.length ? `<span class="small" style="color:var(--warn)">missing: ${esc(r.meta_missing.join(", "))}</span>` : chip("ok", "complete")) },
    { h: "Prepared", html: (r) => (r.prepared ? chip("ok", "yes") : chip("neutral", "no")) },
    { h: "Tonic", html: (r) => (r.tonic_hz ? `${fmt(r.tonic_hz, 5)} Hz ${r.tonic_confirmed ? "✓" : "?"}` : "–") },
    { h: "Segments", k: "n_segments", num: true },
  ], rows, { empty: "No samples yet.", onClick: (r) => showSample(r.id) });
}
async function showSample(id) {
  const r = await api("GET", S(`/samples/${id}`));
  const host = $("#sampleDetail");
  host.classList.remove("hidden");
  host.innerHTML = `<div class="row"><h3 style="margin:0">${esc(r.code)} · ${esc(r.filename)}</h3>${chip(r.qc_status)}<div class="spacer"></div>
    <button class="btn sm" id="sdClose">Close</button></div>
    <div class="grid2" style="margin-top:10px"><div>
      <h3>Quality checks</h3><div id="sdChecks"></div>
      <dl class="kv" style="margin-top:8px">${Object.entries(r.qc.info || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}<dt>SHA-256</dt><dd class="mono" style="word-break:break-all">${esc(r.sha256)}</dd></dl>
      <h3 style="margin-top:12px">Override QC</h3>
      <div class="row"><select id="sdOv"><option value="">no override</option><option>pass</option><option>flag</option><option>reject</option></select>
      <input id="sdOvReason" placeholder="reason (goes to the exclusion log)" style="flex:1" value="${esc(r.meta.qc_override_reason || "")}"><button class="btn sm" id="sdOvSave">Apply</button></div>
    </div><div>
      <h3>Metadata</h3><div class="formgrid" id="sdMeta"></div>
      <label class="f" style="margin-top:8px">Group<select id="sdGroup">${state.info.groups.map((g) => `<option value="${g.id}" ${g.id === r.group_id ? "selected" : ""}>${esc(g.name)}</option>`).join("")}</select></label>
      <div class="row" style="margin-top:10px"><button class="btn primary" id="sdSave">Save metadata</button><button class="btn danger" id="sdDel">Delete sample</button></div>
    </div></div>`;
  table("#sdChecks", [{ h: "Check", k: "check" }, { h: "Result", html: (c) => chip(c.status) },
    { h: "Value", html: (c) => `${fmt(c.value, 4)} ${esc(c.unit || "")}` }, { h: "Meaning", k: "message" }], r.qc.checks || []);
  metaForm($("#sdMeta"), r.meta, "sm");
  $("#sdOv").value = r.meta.qc_override || "";
  $("#sdClose").onclick = () => host.classList.add("hidden");
  $("#sdSave").onclick = async () => {
    await api("PUT", S(`/samples/${id}`), { ...readMeta($("#sdMeta"), "sm"), group_id: +$("#sdGroup").value });
    toast("Saved", "good"); await refreshStudy(); renderSamples();
  };
  $("#sdOvSave").onclick = async () => {
    await api("POST", S(`/samples/${id}/qc_override`), { status: $("#sdOv").value || null, reason: $("#sdOvReason").value });
    await refreshStudy(); renderSamples(); showSample(id);
  };
  $("#sdDel").onclick = async () => {
    if (!confirm("Delete this sample and its segments and audio copies?")) return;
    await api("DELETE", S(`/samples/${id}`)); host.classList.add("hidden"); await refreshStudy(); renderSamples();
  };
  host.scrollIntoView({ behavior: "smooth" });
}
async function uploadFiles(files) {
  if (!files.length) return;
  const fd = new FormData();
  fd.append("group_id", $("#impGroup").value);
  fd.append("meta", JSON.stringify(readMeta($("#metaDefaults"))));
  for (const f of files) fd.append("files", f, f.name);
  $("#impResult").textContent = `Importing ${files.length} file(s) and running quality control…`;
  const res = await api("POST", S("/samples"), fd);
  showImportResult(res);
}
function showImportResult(res) {
  $("#impResult").innerHTML = res.map((x) => x.error ? `<div style="color:var(--bad)">✗ ${esc(x.file)}: ${esc(x.error)}</div>`
    : `<div>✓ ${esc(x.file)} → ${chip(x.status)}</div>`).join("");
  refreshStudy().then(renderSamples);
}
const drop = $("#drop");
drop.onclick = () => $("#fileIn").click();
drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") $("#fileIn").click(); };
$("#fileIn").onchange = (e) => uploadFiles([...e.target.files]).finally(() => (e.target.value = ""));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); uploadFiles([...e.dataTransfer.files]); });
$("#impPathBtn").onclick = async () => {
  $("#impResult").textContent = "Importing…";
  const res = await api("POST", S("/samples/import_path"), { path: $("#impPath").value, group_id: +$("#impGroup").value, meta: readMeta($("#metaDefaults")) });
  showImportResult(res);
};

// ---------------------------------------------------------------- 3 PREPARE
const biasPairs = [];
loaders.prepare = async () => {
  await refreshStudy();
  const sep = state.sysinfo?.separation || (await api("GET", "/api/info")).separation;
  $("#sepStatus").innerHTML = sep.ok ? `Voice separation available on <b>${esc(sep.device)}</b> · models: ${esc(sep.models.join(", "))}`
    : `Voice separation is not installed: ${esc(sep.reason)} Preparation still works; use solo or sparse passages for voice-quality segments.`;
  $("#sepStatus").className = "banner " + (sep.ok ? "good" : "warn");
  $("#prepSep").disabled = !sep.ok;
  table("#prepTable", [
    { h: "Code", k: "code" }, { h: "Group", k: "group_name" }, { h: "QC", html: (r) => chip(r.qc_status) },
    { h: "Prepared", html: (r) => (r.prepared ? chip("ok", "yes") : chip("neutral", "no")) },
    { h: "Separated", html: (r) => (r.separated ? chip("ok", "yes") : "–") },
    { h: "Measure values from", html: (r) => `<select data-mf="${r.id}" ${r.separated ? "" : "disabled"}><option ${r.meta.measure_from !== "vocal stem" ? "selected" : ""}>measurement copy</option><option ${r.meta.measure_from === "vocal stem" ? "selected" : ""}>vocal stem</option></select>` },
    { h: "", html: (r) => `<button class="btn sm" data-prep="${r.id}" ${r.qc_status === "reject" ? "disabled" : ""}>${r.prepared ? "Prepare again" : "Prepare"}</button>` },
  ], state.samples, { empty: "Import samples first." });
  $$("[data-prep]").forEach((b) => (b.onclick = async () => {
    b.disabled = true; b.textContent = "Working…";
    const j = await api("POST", S(`/samples/${b.dataset.prep}/prepare`), { separate: $("#prepSep").checked });
    try { await pollJob(j); toast("Prepared", "good"); } finally { loaders.prepare(); }
  }));
  $$("[data-mf]").forEach((s) => (s.onchange = () => api("PUT", S(`/samples/${s.dataset.mf}`), { measure_from: s.value })));
  sampleOptions($("#listenSample"));
  const segs = await api("GET", S("/segments"));
  $("#biasVowel").innerHTML = segs.filter((g) => g.kind === "vowel").map((g) => `<option value="${g.id}">vowel #${g.id} (sample ${g.sample_id}, ${g.start.toFixed(1)} s)</option>`).join("") || "<option value=''>no held-vowel segments</option>";
  $("#biasAcc").innerHTML = state.samples.filter((s) => s.prepared).map((s) => `<option value="${s.id}">accompaniment: ${esc(s.code)}</option>`).join("");
  const bias = await api("GET", S("/bias"));
  table("#biasTable", [{ h: "Feature", html: (r) => esc(state.labels[r.feature]?.label || r.feature) }, { h: "Mean shift", html: (r) => fmt(r.mean_shift), num: true },
    { h: "SD", html: (r) => fmt(r.sd_shift), num: true }, { h: "Unit", k: "unit" }, { h: "Pairs", k: "n", num: true }], bias, { empty: "No remix test yet." });
};
$("#prepAll").onclick = async () => {
  const js = await api("POST", S("/prepare_all"), { separate: $("#prepSep").checked });
  if (!js.length) { toast("Every usable sample is already prepared."); return; }
  toast(`${js.length} samples queued`);
  for (const j of js) { try { await pollJob(j); } catch (e) { /* shown */ } }
  loaders.prepare();
};
function setListen() {
  const id = $("#listenSample").value; if (!id) return;
  $("#listenAudio").src = S(`/samples/${id}/audio?which=preview:${$("#listenWhich").value}`);
}
$("#listenSample").onchange = setListen; $("#listenWhich").onchange = setListen;
$("#biasAdd").onclick = () => {
  if (!$("#biasVowel").value || !$("#biasAcc").value) return;
  biasPairs.push([+$("#biasVowel").value, +$("#biasAcc").value]);
  $("#biasPairs").textContent = "Pairs: " + biasPairs.map((p) => `vowel #${p[0]} + sample ${p[1]}`).join("; ");
};
$("#biasRun").onclick = async () => {
  if (!biasPairs.length) { toast("Add at least one pair.", "bad"); return; }
  const j = await api("POST", S("/bias"), { pairs: biasPairs });
  await pollJob(j); toast("Remix test finished", "good"); loaders.prepare();
};

// ---------------------------------------------------------------- 4 TONIC
let toneCtx = null, toneNodes = [];
loaders.tonic = async () => {
  await refreshStudy();
  sampleOptions($("#tonicSample"), (r) => r.prepared);
  await tonicLoad();
};
async function tonicLoad() {
  const id = $("#tonicSample").value;
  if (!id) { $("#tonicState").innerHTML = '<span class="muted small">Prepare samples first.</span>'; return; }
  const r = state.samples.find((s) => String(s.id) === id);
  $("#tonicHz").value = r.tonic_hz || "";
  $("#tonicState").innerHTML = r.tonic_hz ? (r.tonic_confirmed ? chip("ok", "confirmed") : chip("flag", "proposed, not confirmed")) : chip("neutral", "not set");
  $("#tonicAudio").src = S(`/samples/${id}/audio?which=preview:measure`);
  await drawPitch(id, "#tonicPlot", r.tonic_hz);
}
async function drawPitch(id, el, tonic) {
  try {
    const p = await api("GET", S(`/samples/${id}/pitch?start=0&end=600`), undefined, { quiet: true });
    const useC = !!p.tonic;
    const y = useC ? p.cents : p.hz;
    const lay = { ...plotTheme(), title: { text: useC ? "Pitch relative to tonic" : "Pitch (Hz)", font: { size: 13 } },
      yaxis: { ...plotTheme().yaxis, title: useC ? "cents re tonic" : "Hz" }, xaxis: { ...plotTheme().xaxis, title: "time (s)" } };
    Plotly.react($(el), [{ x: p.t, y, mode: "markers", marker: { size: 2.5, color: "#2563eb" }, type: "scattergl", name: "F0" }], lay, { displaylogo: false, responsive: true });
  } catch (e) { $(el).innerHTML = `<p class="muted small">${esc(e.message)}</p>`; }
}
$("#tonicSample").onchange = tonicLoad;
$("#tonicPropose").onclick = async () => {
  const id = $("#tonicSample").value; if (!id) return;
  $("#tonicState").innerHTML = '<span class="muted small">Analysing…</span>';
  const r = await api("POST", S(`/samples/${id}/tonic/propose`), { method: $("#tonicMethod").value || null });
  $("#tonicHz").value = r.hz;
  $("#tonicAlts").innerHTML = `Method: ${esc(r.method)}${r.key ? " · key " + esc(r.key) : ""} · score ${fmt(r.score)}` +
    (r.alternatives?.length ? " · alternatives: " + r.alternatives.map((a) => `<a href="#" data-alt="${a.hz}">${a.hz} Hz</a>`).join(", ") : "");
  $$("[data-alt]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); $("#tonicHz").value = a.dataset.alt; restartTone(); }));
  await refreshStudy(); await tonicLoad();
};
$$("[data-nudge]").forEach((b) => (b.onclick = () => { const v = +$("#tonicHz").value; if (v) { $("#tonicHz").value = (v * 2 ** (+b.dataset.nudge / 1200)).toFixed(2); restartTone(); } }));
$$("[data-oct]").forEach((b) => (b.onclick = () => { const v = +$("#tonicHz").value; if (v) { $("#tonicHz").value = (v * +b.dataset.oct).toFixed(2); restartTone(); } }));
function stopTone() { toneNodes.forEach((n) => { try { n.stop(); } catch (e) { /* stopped */ } }); toneNodes = []; $("#tonePlay").textContent = "▶ Reference tone"; }
function startTone() {
  const f = +$("#tonicHz").value; if (!f) return;
  toneCtx = toneCtx || new AudioContext();
  const g = toneCtx.createGain(); g.gain.value = 0.06; g.connect(toneCtx.destination);
  for (const [mult, amp] of [[1, 1], [2, 0.5], [3, 0.25], [1.5, 0.35]]) {   // Sa, Sa', Pa'' and Pa: a simple drone
    const o = toneCtx.createOscillator(); const og = toneCtx.createGain();
    o.frequency.value = f * mult; og.gain.value = amp; o.connect(og).connect(g); o.start(); toneNodes.push(o);
  }
  $("#tonePlay").textContent = "■ Stop tone";
}
function restartTone() { if (toneNodes.length) { stopTone(); startTone(); } }
$("#tonePlay").onclick = () => (toneNodes.length ? stopTone() : startTone());
$("#tonicConfirm").onclick = async () => {
  const id = $("#tonicSample").value;
  await api("POST", S(`/samples/${id}/tonic/confirm`), { hz: +$("#tonicHz").value });
  toast("Tonic confirmed", "good"); stopTone(); await refreshStudy(); await tonicLoad();
};
$("#driftBtn").onclick = async () => {
  const id = $("#tonicSample").value;
  if (!confirm("Re-time the measurement copy so the drone stays at constant pitch? (Logged; the original file is untouched.)")) return;
  const r = await api("POST", S(`/samples/${id}/drift`));
  toast(`Drift corrected: ${r.drift_span_cents.toFixed(1)} cents across ${r.points} windows`, "good"); tonicLoad();
};

// ---------------------------------------------------------------- 5 SEGMENT
const waves = {};
let segRegions = null, segSel = null, segSuggestions = [];
function waveColors() {
  const cs = getComputedStyle(document.documentElement);
  return { waveColor: cs.getPropertyValue("--wave").trim(), progressColor: cs.getPropertyValue("--wave-progress").trim(), cursorColor: cs.getPropertyValue("--ink").trim() };
}
const KIND_COLOR = { phrase: "rgba(37,99,235,0.18)", vowel: "rgba(5,150,105,0.25)", rhythm: "rgba(217,119,6,0.22)", suggest: "rgba(120,120,120,0.12)" };
loaders.segment = async () => {
  await refreshStudy();
  sampleOptions($("#segSample"), (r) => r.prepared);
  await segLoad();
  loadReview();
};
async function segLoad() {
  const id = $("#segSample").value;
  if (waves.seg) { waves.seg.destroy(); waves.seg = null; }
  $("#segSpec").innerHTML = "";
  if (!id) { $("#segWave").innerHTML = '<p class="muted small">Prepare samples first.</p>'; return; }
  const r = state.samples.find((s) => String(s.id) === id);
  segRegions = WaveSurfer.Regions.create();
  const plugins = [segRegions, WaveSurfer.Timeline.create()];
  if ((r.duration || 0) <= 900) plugins.push(WaveSurfer.Spectrogram.create({ container: "#segSpec", labels: true, height: 160, frequencyMax: 8000, fftSamples: 1024 }));
  else $("#segSpec").innerHTML = '<p class="muted small">Spectrogram hidden for recordings over 15 minutes.</p>';
  waves.seg = WaveSurfer.create({ container: "#segWave", height: 90, url: S(`/samples/${id}/audio?which=preview:${$("#segWhich").value}`),
    minPxPerSec: +$("#segZoom").value, plugins, ...waveColors() });
  segRegions.enableDragSelection({ color: KIND_COLOR.phrase });
  segRegions.on("region-created", (reg) => {
    if (reg._loaded) return;
    segSel = { id: null, start: reg.start, end: reg.end, kind: $("#sfKind").value || "phrase", section: "free", singer_code: r.meta.singer_id || "", region: reg };
    fillSegForm(segSel);
  });
  segRegions.on("region-updated", (reg) => {
    if (segSel && segSel.region === reg) { $("#sfStart").value = reg.start.toFixed(2); $("#sfEnd").value = reg.end.toFixed(2); }
  });
  segRegions.on("region-clicked", (reg, e) => { e.stopPropagation(); if (reg._seg) selectSeg(reg._seg, reg); });
  waves.seg.on("decode", () => drawSegRegions());
  drawPitch(id, "#segPitch", r.tonic_hz);
}
async function drawSegRegions() {
  const id = $("#segSample").value;
  const segs = await api("GET", S(`/segments?sample=${id}`));
  segRegions.clearRegions();
  for (const g of segs) {
    const reg = segRegions.addRegion({ start: g.start, end: g.end, color: g.excluded ? "rgba(180,35,24,0.15)" : KIND_COLOR[g.kind], drag: true, resize: true, content: `${g.kind}${g.singer_code ? " · " + g.singer_code : ""}` });
    reg._loaded = true; reg._seg = g;
  }
  for (const sgg of segSuggestions) {
    const reg = segRegions.addRegion({ start: sgg.start, end: sgg.end, color: KIND_COLOR.suggest });
    reg._loaded = true; reg._sugg = sgg;
    reg.on("click", () => { segSel = { id: null, ...sgg, section: "free", singer_code: state.samples.find((s) => String(s.id) === id).meta.singer_id || "", region: reg }; fillSegForm(segSel); });
  }
  table("#segTable", [
    { h: "Start", html: (g) => g.start.toFixed(2), num: true }, { h: "End", html: (g) => g.end.toFixed(2), num: true },
    { h: "Kind", k: "kind" }, { h: "Section", k: "section" }, { h: "Singer", html: (g) => esc(g.singer_code || "—") },
    { h: "Label", k: "label" }, { h: "", html: (g) => (g.excluded ? chip("reject", "excluded") : "") },
  ], segs, { empty: "No segments yet. Drag on the waveform or use Suggest segments.", onClick: (g) => selectSeg(g), selected: (g) => segSel && segSel.id === g.id });
}
function selectSeg(g, reg) {
  segSel = { ...g, region: reg || segRegions.getRegions().find((x) => x._seg && x._seg.id === g.id) };
  fillSegForm(segSel);
  if (waves.seg) waves.seg.setTime(g.start);
  loadOrnaments(g.id);
}
function fillSegForm(g) {
  $("#segFormHint").textContent = g.id ? `Segment #${g.id}` : "New segment (not saved yet)";
  $("#sfStart").value = (+g.start).toFixed(2); $("#sfEnd").value = (+g.end).toFixed(2);
  $("#sfKind").value = g.kind || "phrase"; $("#sfSection").value = g.section || "free";
  $("#sfSinger").value = g.singer_code || ""; $("#sfVowel").value = g.vowel || ""; $("#sfLabel").value = g.label || ""; $("#sfNotes").value = g.notes || "";
  $("#sfExclude").textContent = g.excluded ? "Include again" : "Exclude";
  if (!g.id) $("#ornList").innerHTML = "";
}
$("#sfSave").onclick = async () => {
  if (!segSel) { toast("Drag on the waveform to create a segment first.", "bad"); return; }
  const body = { start: +$("#sfStart").value, end: +$("#sfEnd").value, kind: $("#sfKind").value, section: $("#sfSection").value,
    singer_code: $("#sfSinger").value.trim() || null, vowel: $("#sfVowel").value, label: $("#sfLabel").value, notes: $("#sfNotes").value };
  const id = $("#segSample").value;
  if (segSel.id) await api("PUT", S(`/segments/${segSel.id}`), body);
  else { const r = await api("POST", S(`/samples/${id}/segments`), body); segSel.id = r.id; }
  if (body.notes.trim()) await api("POST", S("/notes"), { text: body.notes, segment_id: segSel.id }).catch(() => {});
  if (segSel.region && segSel.region._sugg) segSuggestions = segSuggestions.filter((x) => x !== segSel.region._sugg);
  toast("Segment saved", "good"); await refreshStudy(); drawSegRegions();
};
$("#sfDelete").onclick = async () => {
  if (!segSel) return;
  if (segSel.id) await api("DELETE", S(`/segments/${segSel.id}`));
  else if (segSel.region) segSel.region.remove();
  segSel = null; drawSegRegions();
};
$("#sfExclude").onclick = async () => {
  if (!segSel?.id) return;
  const reason = segSel.excluded ? "" : prompt("Reason for excluding this segment (goes to the exclusion log):", "two voices overlap");
  if (!segSel.excluded && reason === null) return;
  await api("PUT", S(`/segments/${segSel.id}`), { excluded: segSel.excluded ? 0 : 1, notes: reason || segSel.notes || "" });
  segSel.excluded = !segSel.excluded; drawSegRegions();
};
$("#sfOrn").onclick = async () => {
  if (!segSel?.id) { toast("Save the segment first.", "bad"); return; }
  $("#ornList").innerHTML = '<span class="muted small">Analysing pitch oscillations…</span>';
  await api("POST", S(`/segments/${segSel.id}/ornaments`)); loadOrnaments(segSel.id); loadReview();
};
async function loadOrnaments(segId) {
  const all = await api("GET", S("/ornaments"));
  const rows = all.filter((o) => o.segment_id === segId);
  table("#ornList", [{ h: "Time", html: (o) => `${o.start.toFixed(1)}–${o.end.toFixed(1)} s` }, { h: "Rate", html: (o) => `${fmt(o.rate_hz)} Hz` },
    { h: "Extent", html: (o) => `±${fmt(o.extent_cents)} ¢` }, { h: "Regularity", html: (o) => fmt(o.regularity) },
    { h: "Label", html: (o) => chip(o.final_label || "review", o.final_label || "review") }], rows, { empty: "No oscillations analysed for this segment." });
}
async function loadReview() {
  if (!state.study) return;
  const rows = await api("GET", S("/ornaments?review_only=true"));
  table("#reviewQueue", [{ h: "Sample", k: "code" }, { h: "Time", html: (o) => `${o.start.toFixed(1)}–${o.end.toFixed(1)} s` },
    { h: "Rate", html: (o) => `${fmt(o.rate_hz)} Hz` }, { h: "Extent", html: (o) => `±${fmt(o.extent_cents)} ¢` }, { h: "Regularity", html: (o) => fmt(o.regularity) },
    { h: "Decide", html: (o) => ["vibrato", "ornament", "neither"].map((l) => `<button class="btn sm" data-rv="${o.id}" data-l="${l}">${l}</button>`).join(" ") }],
  rows, { empty: "Nothing waiting for review." });
  $$("[data-rv]").forEach((b) => (b.onclick = async () => { await api("PUT", S(`/ornaments/${b.dataset.rv}`), { label: b.dataset.l }); loadReview(); }));
}
$("#segSample").onchange = () => { segSuggestions = []; segSel = null; segLoad(); };
$("#segWhich").onchange = segLoad;
$("#segZoom").oninput = (e) => waves.seg && waves.seg.zoom(+e.target.value);
$("#segPlay").onclick = () => waves.seg && waves.seg.playPause();
$("#segSuggest").onclick = async () => {
  const id = $("#segSample").value; if (!id) return;
  segSuggestions = await api("GET", S(`/samples/${id}/suggest`));
  toast(`${segSuggestions.length} suggestions (grey). Click one to edit, or accept all.`);
  $("#segAcceptAll").classList.toggle("hidden", !segSuggestions.length);
  drawSegRegions();
};
$("#segAcceptAll").onclick = async () => {
  const id = $("#segSample").value;
  const smp = state.samples.find((s) => String(s.id) === id);
  for (const g of segSuggestions) await api("POST", S(`/samples/${id}/segments`), { start: g.start, end: g.end, kind: g.kind, section: "free", singer_code: smp.meta.singer_id || null });
  segSuggestions = []; $("#segAcceptAll").classList.add("hidden"); toast("Suggestions saved. Check singer and section labels.", "good");
  await refreshStudy(); drawSegRegions();
};

// ---------------------------------------------------------------- 6 RHYTHM
let rhRegions = null, rhTaps = [], rhBeats = [];
loaders.rhythm = async () => {
  await refreshStudy();
  sampleOptions($("#rhSample"), (r) => r.prepared);
  await rhLoad();
};
async function rhLoad() {
  const id = $("#rhSample").value;
  if (waves.rh) { waves.rh.destroy(); waves.rh = null; }
  if (!id) { $("#rhWave").innerHTML = '<p class="muted small">Prepare samples first.</p>'; return; }
  rhRegions = WaveSurfer.Regions.create();
  waves.rh = WaveSurfer.create({ container: "#rhWave", height: 110, url: S(`/samples/${id}/audio?which=preview:measure`), minPxPerSec: 30,
    plugins: [rhRegions, WaveSurfer.Timeline.create()], ...waveColors() });
  const marks = await api("GET", S(`/samples/${id}/marks`));
  rhTaps = marks.filter((m) => m.kind === "cycle" && m.source === "manual").map((m) => m.t);
  rhBeats = marks.filter((m) => m.kind === "beat");
  waves.rh.on("decode", drawMarks);
}
function drawMarks() {
  if (!rhRegions) return;
  rhRegions.clearRegions();
  for (const b of rhBeats) rhRegions.addRegion({ start: b.t, color: b.source === "manual" ? "rgba(5,150,105,0.6)" : "rgba(120,120,120,0.45)", drag: false });
  for (const t of rhTaps) rhRegions.addRegion({ start: t, color: "rgba(219,39,119,0.95)", drag: false, content: "◆" });
  const nb = rhBeats.filter((b) => b.source === "manual").length;
  $("#rhInfo").textContent = `${rhTaps.length} cycle marks (pink) · ${rhBeats.length - nb} proposed beats (grey) · ${nb} confirmed beats (green)`;
  if (rhTaps.length >= 2) {
    const s = [...rhTaps].sort((a, b) => a - b);
    const x = s.slice(0, -1), y = s.slice(1).map((t, i) => 60 / (t - s[i]));
    Plotly.react($("#rhPlot"), [{ x, y, mode: "lines+markers", line: { color: "#db2777" }, name: "cycles per minute" }],
      { ...plotTheme(), title: { text: "Tempo per cycle", font: { size: 13 } }, xaxis: { ...plotTheme().xaxis, title: "time (s)" }, yaxis: { ...plotTheme().yaxis, title: "cycles per minute" } },
      { displaylogo: false, responsive: true });
  } else $("#rhPlot").innerHTML = '<p class="muted small">Tap at least two cycle starts to see the tempo curve.</p>';
}
$("#rhSample").onchange = rhLoad;
$("#rhPlay").onclick = () => waves.rh && waves.rh.playPause();
function tap() { if (!waves.rh) return; rhTaps.push(+waves.rh.getCurrentTime().toFixed(3)); drawMarks(); }
$("#rhTap").onclick = tap;
document.addEventListener("keydown", (e) => {
  if (state.tab === "rhythm" && e.code === "Space" && !e.target.closest("input,textarea,select")) { e.preventDefault(); tap(); }
});
$("#rhUndo").onclick = () => { rhTaps.pop(); drawMarks(); };
$("#rhClear").onclick = () => { if (confirm("Clear all cycle marks for this sample?")) { rhTaps = []; drawMarks(); } };
$("#rhSave").onclick = async () => { await api("PUT", S(`/samples/${$("#rhSample").value}/marks`), { times: rhTaps, kind: "cycle" }); toast("Cycles saved", "good"); };
$("#rhPropose").onclick = async () => {
  $("#rhInfo").textContent = "Proposing beats…";
  const r = await api("POST", S(`/samples/${$("#rhSample").value}/beats`));
  toast(`${r.beats.length} beats proposed (${r.method}, from the ${r.source_audio})`);
  rhBeats = r.beats.map((t) => ({ t, kind: "beat", source: "proposed" })); drawMarks();
};
$("#rhAccept").onclick = async () => { await api("POST", S(`/samples/${$("#rhSample").value}/marks/accept`)); toast("Proposed beats confirmed", "good"); rhLoad(); };

// ---------------------------------------------------------------- 7 ANALYSE
let resRows = [];
loaders.analyse = async () => {
  await refreshStudy();
  const segs = await api("GET", S("/segments"));
  const usable = state.samples.filter((s) => s.qc_status !== "reject");
  const prepared = usable.filter((s) => s.prepared).length;
  const tonic = usable.filter((s) => s.tonic_confirmed).length;
  const kinds = { phrase: 0, vowel: 0, rhythm: 0 };
  segs.filter((g) => !g.excluded).forEach((g) => (kinds[g.kind] = (kinds[g.kind] || 0) + 1));
  const nolab = segs.filter((g) => !g.singer_code && !g.excluded).length;
  const card = (n, label, warn) => `<div class="card"><div class="stat" style="${warn ? "color:var(--warn)" : ""}">${n}</div><div class="muted">${label}</div></div>`;
  $("#readiness").innerHTML = card(`${prepared}/${usable.length}`, "usable samples prepared", prepared < usable.length) +
    card(`${tonic}/${usable.length}`, "tonics confirmed (needed for cents measures)", tonic < usable.length) +
    card(`${kinds.phrase} · ${kinds.vowel} · ${kinds.rhythm}`, "phrases · held vowels · rhythm segments", !segs.length) +
    (nolab ? card(nolab, "segments without a singer ID (each counted as a separate singer)", true) : "");
  await loadResults();
};
async function loadResults() {
  resRows = await api("GET", S(`/results?kind=${$("#resKind").value}`));
  renderResults();
}
function renderResults() {
  const f = $("#resFilter").value.toLowerCase();
  const rows = resRows.filter((r) => !f || r.feature.includes(f) || (state.labels[r.feature]?.label || "").toLowerCase().includes(f)).slice(0, 2000);
  table("#resTable", [{ h: "Sample", k: "sample_code" }, { h: "Group", k: "group" }, { h: "Singer", k: "singer" }, { h: "Seg", k: "segment" },
    { h: "Kind", k: "kind" }, { h: "Feature", html: (r) => esc(state.labels[r.feature]?.label || r.feature) },
    { h: "Value", html: (r) => fmt(r.value, 4), num: true }, { h: "Unit", k: "unit" }], rows, { empty: "No results yet. Run the analysis." });
}
$("#resKind").onchange = loadResults;
$("#resFilter").oninput = renderResults;
$("#runAnalyse").onclick = async () => {
  $("#runAnalyse").disabled = true;
  try {
    const j = await api("POST", S("/analyse"));
    const r = await pollJob(j, $("#anProg"), $("#anMsg"));
    toast(`Measured ${r.segments} segments${r.skipped.length ? `; ${r.skipped.length} skipped (see activity log)` : ""}`, r.skipped.length ? "" : "good");
    await refreshStudy(); loaders.analyse();
  } finally { $("#runAnalyse").disabled = false; }
};

// ---------------------------------------------------------------- 8 COMPARE
let cmpData = null;
loaders.compare = async () => {
  await refreshStudy();
  const gs = state.info.groups.filter((g) => g.role === "study");
  $("#cmpGroups").innerHTML = gs.map((g) => `<label class="small"><input type="checkbox" data-cg="${esc(g.name)}" checked> ${esc(g.name)}</label>`).join(" ");
};
$("#cmpRun").onclick = async () => {
  const groups = $$("[data-cg]").filter((c) => c.checked).map((c) => c.dataset.cg);
  const q = new URLSearchParams({ groups: groups.join(","), kind: $("#cmpKind").value, section: $("#cmpSection").value });
  cmpData = await api("GET", S(`/compare?${q}`));
  state.labels = cmpData.labels || state.labels;
  const lv = cmpData.level;
  $("#cmpLevel").innerHTML = `<div class="banner ${lv === "inferential" ? "good" : lv === "exploratory" ? "warn" : "info"}"><b>Statistics level: ${esc(lv)}.</b> ${esc(cmpData.level_text)}
    <span class="small"> Singers per group: ${Object.entries(cmpData.n_singers).map(([g, n]) => `${esc(g)} ${n}`).join(" · ")}</span></div>`;
  const feats = [...new Set(cmpData.describe.map((d) => d.feature))];
  const order = Object.keys(cmpData.labels);
  feats.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  $("#cmpFeature").innerHTML = feats.map((f) => `<option value="${f}">${esc(cmpData.labels[f]?.group || "")} · ${esc(cmpData.labels[f]?.label || f)}</option>`).join("");
  drawFeature();
  const eff = cmpData.pairwise.filter((r) => r.hedges_g != null || lv === "case study").sort((a, b) => Math.abs(b.hedges_g || 0) - Math.abs(a.hedges_g || 0));
  table("#cmpEffects", [{ h: "Feature", html: (r) => esc(cmpData.labels[r.feature]?.label || r.feature) }, { h: "Groups", html: (r) => `${esc(r.group_a)} vs ${esc(r.group_b)}` },
    { h: "Means", html: (r) => `${fmt(r.mean_a)} / ${fmt(r.mean_b)} ${esc(r.unit)}` }, { h: "g", html: (r) => fmt(r.hedges_g, 2), num: true },
    { h: "95 % CI", html: (r) => (r.ci_low != null ? `[${fmt(r.ci_low, 2)}, ${fmt(r.ci_high, 2)}]` : "–") },
    { h: "Sep. bias", html: (r) => (r.bias_mean != null ? `${fmt(r.bias_mean, 2)} ± ${fmt(r.bias_sd, 2)}` : "–") }], eff, { empty: "No pairwise comparison possible." });
  table("#cmpTests", [{ h: "Feature", html: (r) => esc(cmpData.labels[r.feature]?.label || r.feature) }, { h: "Test", k: "test" },
    { h: "p", html: (r) => fmt(r.p, 3), num: true }, { h: "q (FDR)", html: (r) => fmt(r.q_fdr, 3), num: true },
    { h: "", html: (r) => (r.significant_fdr ? chip("pass", "q < 0.05") : "") }], [...cmpData.tests].sort((a, b) => (a.q_fdr ?? 1) - (b.q_fdr ?? 1)),
  { empty: lv === "case study" ? "No group tests at case-study level." : "No tests." });
  const p = cmpData.pca;
  if (p) {
    const gs = cmpData.groups;
    Plotly.react($("#cmpPca"), gs.map((g) => ({ x: p.points.filter((x) => x.group === g).map((x) => x.pc1), y: p.points.filter((x) => x.group === g).map((x) => x.pc2),
      text: p.points.filter((x) => x.group === g).map((x) => x.singer), mode: "markers", type: "scatter", name: g, marker: { size: 10, color: groupColor(g, gs) } })),
    { ...plotTheme(), xaxis: { ...plotTheme().xaxis, title: `PC1 (${(p.explained[0] * 100).toFixed(0)} %)` }, yaxis: { ...plotTheme().yaxis, title: `PC2 (${(p.explained[1] * 100).toFixed(0)} %)` } },
    { displaylogo: false, responsive: true });
  } else $("#cmpPca").innerHTML = '<p class="muted small">Needs at least three singers.</p>';
};
async function drawFeature() {
  if (!cmpData) return;
  const f = $("#cmpFeature").value;
  const rows = await api("GET", S(`/results?kind=${$("#cmpKind").value}&section=${$("#cmpSection").value}`));
  const gs = cmpData.groups;
  const bySinger = {};
  rows.filter((r) => r.feature === f && gs.includes(r.group)).forEach((r) => { const k = r.group + "|" + r.singer; (bySinger[k] = bySinger[k] || []).push(r.value); });
  const traces = gs.map((g) => {
    const pts = Object.entries(bySinger).filter(([k]) => k.startsWith(g + "|"));
    return { type: "box", name: g, y: pts.map(([, v]) => v.reduce((a, b) => a + b, 0) / v.length), text: pts.map(([k]) => k.split("|")[1]),
      boxpoints: "all", jitter: 0.4, pointpos: 0, marker: { color: groupColor(g, gs), size: 8 }, line: { color: groupColor(g, gs) }, hoverinfo: "y+text" };
  });
  const lab = cmpData.labels[f] || {};
  Plotly.react($("#cmpPlot"), traces, { ...plotTheme(), title: { text: `${lab.label || f} — one point per singer`, font: { size: 13 } },
    yaxis: { ...plotTheme().yaxis, title: lab.unit || "" }, showlegend: false }, { displaylogo: false, responsive: true });
}
$("#cmpFeature").onchange = drawFeature;

// ---------------------------------------------------------------- 9 REPORT
loaders.report = async () => {
  await refreshStudy();
  const styles = state.sysinfo?.citation_styles || ["IEEE", "ACS", "AIP", "APA 7", "MLA 9"];
  $("#repStyle").innerHTML = styles.map((s) => `<option ${s === state.info.citation_style ? "selected" : ""}>${s}</option>`).join("");
  $("#repGroups").innerHTML = '<span class="small muted">Groups:</span> ' + state.info.groups.filter((g) => g.role === "study").map((g) => `<label class="small"><input type="checkbox" data-rg="${esc(g.name)}" checked> ${esc(g.name)}</label>`).join(" ");
  await listReports(); previewRefs();
};
async function previewRefs() {
  const r = await api("GET", `/api/citations?style=${encodeURIComponent($("#repStyle").value)}`);
  $("#refPreview").innerHTML = r.references.map((x) => `<p>${esc(x).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\*([^*]+)\*/g, "<i>$1</i>")}</p>`).join("");
}
$("#repStyle").onchange = async () => { await api("PUT", S("/style"), { style: $("#repStyle").value }); previewRefs(); };
async function listReports() {
  const r = await api("GET", S("/reports"));
  const host = $("#repList");
  if (!r.reports.length && !r.archives.length) { host.innerHTML = '<p class="muted small">No reports yet.</p>'; return; }
  host.innerHTML = r.reports.map((rep) => {
    const main = rep.files.filter((f) => !f.startsWith("figures/"));
    const figs = rep.files.filter((f) => f.startsWith("figures/") && f.endsWith(".png"));
    const link = (f) => `<a href="${S(`/reports/${rep.name}/${f}`)}" download>${esc(f.replace("figures/", ""))}</a>`;
    return `<div style="margin-bottom:12px"><b>${esc(rep.name)}</b><div class="small">${main.map(link).join(" · ")}</div>
      <details class="small"><summary>${figs.length} figures</summary>${figs.map(link).join(" · ")}</details></div>`;
  }).join("") + (r.archives.length ? `<div class="small"><b>Study archives:</b> ${r.archives.map((a) => `<a href="${S(`/archives/${a}`)}" download>${esc(a)}</a>`).join(" · ")}</div>` : "");
}
$("#repBuild").onclick = async () => {
  $("#repBuild").disabled = true;
  try {
    const groups = $$("[data-rg]").filter((c) => c.checked).map((c) => c.dataset.rg);
    const j = await api("POST", S("/report"), { groups, style: $("#repStyle").value, kind: $("#repKind").value, section: $("#repSection").value });
    const r = await pollJob(j, $("#repProg"), $("#repMsg"));
    toast(`Report ready (${r.figures.length} figures, level: ${r.level})`, "good");
    if (Object.keys(r.figure_errors || {}).length) toast("Some figures were skipped: " + Object.keys(r.figure_errors).join(", "));
    listReports();
  } finally { $("#repBuild").disabled = false; }
};
$("#repArchive").onclick = async () => { const r = await api("POST", S("/archive")); toast(`Archive written: ${r.file}`, "good"); listReports(); };

// ---------------------------------------------------------------- 10 SETTINGS
loaders.settings = async () => {
  const i = await api("GET", "/api/info");
  state.sysinfo = i;
  $("#sysInfo").innerHTML = [["Version", i.version], ["Hardware", i.hardware.device + (i.hardware.gpu ? ` · ${i.hardware.gpu} (${i.hardware.vram_gb} GB)` : "")],
    ["Voice separation", i.separation.ok ? `available (${i.separation.device})` : i.separation.reason], ["Projects folder", i.projects]]
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  showSelftest(await api("GET", "/api/selftest/last"));
  if (state.study) {
    const ex = await api("GET", S("/exclusions"));
    table("#exclLog", [{ h: "When", html: (e) => new Date(e.time * 1000).toLocaleString() }, { h: "Action", k: "action" },
      { h: "Detail", html: (e) => esc(Object.entries(e).filter(([k]) => !["time", "action"].includes(k)).map(([k, v]) => `${k}: ${v}`).join("; ")) }], ex, { empty: "Nothing excluded." });
    const lg = await api("GET", S("/log"));
    table("#actLog", [{ h: "When", html: (e) => new Date(e.t * 1000).toLocaleTimeString() }, { h: "Action", k: "action" }, { h: "Detail", html: (e) => esc(String(e.detail).slice(0, 160)) }], lg);
  }
};
function showSelftest(r) {
  if (!r) { $("#stSummary").innerHTML = '<span class="muted small">Not run yet on this computer.</span>'; $("#stTable").innerHTML = ""; return; }
  $("#stSummary").innerHTML = `<div class="banner ${r.passed === r.total ? "good" : "bad"}"><b>${r.passed} of ${r.total} checks passed</b> · version ${esc(r.version)} · ${new Date(r.time * 1000).toLocaleString()}</div>`;
  table("#stTable", [{ h: "Check", k: "test" }, { h: "Result", html: (t) => chip(t.pass ? "pass" : "reject", t.pass ? "pass" : "fail") }, { h: "Detail", k: "detail" }, { h: "s", k: "seconds", num: true }], r.tests);
}
$("#stopApp").onclick = async () => {
  if (!confirm("Stop SonicDiff? Running jobs will resume next time you start it.")) return;
  await api("POST", "/api/shutdown").catch(() => {});
  document.body.innerHTML = '<div style="padding:40px;font:16px sans-serif">SonicDiff has stopped. You can close this tab.</div>';
};
$("#stRun").onclick = async () => {
  $("#stRun").disabled = true;
  try { const j = await api("POST", "/api/selftest"); showSelftest(await pollJob(j, $("#stProg"))); } finally { $("#stRun").disabled = false; }
};

// ---------------------------------------------------------------- start
(async function init() {
  let theme = document.documentElement.dataset.theme || "light";
  try { const s = await api("GET", "/api/settings", undefined, { quiet: true }); if (!localStorage.getItem("sd-theme") && s.theme) theme = s.theme; } catch (e) { /* default */ }
  applyTheme(theme);
  try {
    const i = await api("GET", "/api/info");
    state.sysinfo = i;
    const b = $("#hwBadge");
    if (i.hardware.device === "CUDA") { b.textContent = `GPU · ${i.hardware.gpu}`; b.classList.add("gpu"); }
    else b.textContent = "CPU mode";
    $("#footRight").textContent = `v${i.version}`;
  } catch (e) { $("#hwBadge").textContent = "engine offline"; }
  const list = await loadStudies();
  let last = null;
  try { last = localStorage.getItem("sd-study"); } catch (e) { /* ignore */ }
  if (last && list.some((s) => s.id === last)) await openStudy(last); else updateNav();
  try { state.labels = (await api("GET", "/api/labels", undefined, { quiet: true })) || {}; } catch (e) { /* optional */ }
  setInterval(updateJobBadge, 4000);
  const beat = () => fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
  beat(); setInterval(beat, 20000);
})();
