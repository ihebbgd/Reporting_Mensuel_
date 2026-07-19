"use strict";

const $ = id => document.getElementById(id);
const money = value => new Intl.NumberFormat("fr-FR", {maximumFractionDigits: 2}).format(value);
const statusText = {pending: "En attente", processing: "En cours", completed: "Terminé", failed: "Échec"};
let token = sessionStorage.getItem("reporting-key") || "";
let reports = [], selectedId = "", detail = null, chart = null, page = 0, deletion = null;
let refreshBusy = false, refreshingRequested = false;
let activeView = "dashboard", activeTab = "overview", sessionInfo = null;

function icons() { lucide.createIcons(); }
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function iconButton(icon, label, action) {
  const button = node("button", undefined, "icon-button");
  button.title = label; button.setAttribute("aria-label", label);
  const symbol = node("i"); symbol.dataset.lucide = icon;
  button.append(symbol); button.addEventListener("click", action); return button;
}
function showError(id, error) {
  $(id).textContent = error.message || String(error); $(id).hidden = false;
}
function notice(message) { $("notice").textContent = message; $("notice").hidden = !message; }
function lock() {
  token = ""; sessionStorage.removeItem("reporting-key");
  reports = []; detail = null; selectedId = "";
  $("report-content").hidden = true; $("empty").hidden = false;
  $("history-rows").replaceChildren(); $("comparison-result").hidden = true;
  $("comparison-empty").hidden = false;
  if (!$("login-dialog").open) $("login-dialog").showModal();
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...options.headers, Authorization: "Bearer " + token}});
  if (response.status === 401) {
    lock();
    throw new Error("Clé d'accès incorrecte ou expirée.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message = Array.isArray(payload.detail) ? payload.detail.map(x => x.msg).join(". ") : payload.detail;
    throw new Error(message || "Le serveur ne répond pas. Réessayer.");
  }
  if (options.binary) return response.blob();
  return response.status === 204 ? null : response.json();
}
async function saveBlob(path, filename) {
  const blob = await api(path, {binary: true});
  const url = URL.createObjectURL(blob);
  const link = node("a"); link.href = url; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function populate(id, items, placeholder) {
  const select = $(id), previous = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  for (const report of items) select.add(new Option(report.year + " · " + report.filename, report.task_id));
  if (items.some(x => x.task_id === previous)) select.value = previous;
}
function updateOptions() {
  const completed = reports.filter(r => r.status === "completed");
  populate("selected-report", reports, "Choisir un rapport");
  $("selected-report").value = selectedId;
  populate("previous-report", completed, "Choisir la référence");
  populate("current-report", completed, "Choisir l'exercice suivant");
  populate("baseline-report", completed.filter(r => r.year === Number($("import-year").value) - 1), "Sans comparaison");
}
function switchView(view) {
  activeView = view;
  for (const name of ["dashboard", "history", "compare"]) $(name + "-view").hidden = name !== view;
  document.querySelectorAll("[data-view]").forEach(b => {
    b.classList.toggle("active", b.dataset.view === view);
    if (b.dataset.view === view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  $("page-title").textContent = {dashboard: "Vue d'ensemble", history: "Rapports", compare: "Comparaison"}[view];
  if (view === "dashboard" && detail?.result) drawChart();
}
function switchTab(name, focus = false) {
  activeTab = name;
  document.querySelectorAll("[data-tab]").forEach(b => {
    const active = b.dataset.tab === name;
    b.setAttribute("aria-selected", String(active)); b.tabIndex = active ? 0 : -1;
    $("panel-" + b.dataset.tab).hidden = !active;
    if (active && focus) b.focus();
  });
  if (name === "overview") drawChart();
}
function drawChart() {
  if (activeView !== "dashboard" || activeTab !== "overview" || !detail?.result) return;
  const k = detail.result.kpis;
  if (chart) chart.destroy();
  Chart.defaults.font.family = "Segoe UI, Arial, sans-serif";
  Chart.defaults.color = "#68766d";
  chart = new Chart($("activity-chart"), {
    type: "bar",
    data: {
      labels: Object.keys(k.ca_mensuel).map(m => m.slice(0, 3)),
      datasets: [
        {label: "Chiffre d'affaires", data: Object.values(k.ca_mensuel), backgroundColor: "#258466", borderRadius: 2, maxBarThickness: 23},
        {label: "Charges", data: Object.values(k.charges_mensuelles), backgroundColor: "#8fafbf", borderRadius: 2, maxBarThickness: 23}
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {duration: 220},
      plugins: {legend: {position: "bottom", align: "start", labels: {boxWidth: 8, boxHeight: 8, padding: 20, font: {size: 11}}},
        tooltip: {callbacks: {label: ctx => ctx.dataset.label + " : " + money(ctx.parsed.y) + " TND"}}},
      scales: {x: {grid: {display: false}, border: {display: false}, ticks: {font: {size: 10}, maxRotation: 0}},
        y: {grid: {color: "#e7ede9"}, border: {display: false}, ticks: {font: {size: 10}, callback: value => money(value / 1000) + " k"}, beginAtZero: true}}
    }
  });
}
function renderDetail() {
  const ready = detail?.status === "completed" && detail.result;
  const running = detail && ["pending", "processing"].includes(detail.status);
  $("report-content").hidden = !ready;
  $("empty").hidden = Boolean(ready || running);
  $("pending").hidden = !running;
  $("download").disabled = !ready;
  if (running) {
    $("pending-label").textContent = statusText[detail.status] + " · " + detail.filename;
    $("pending-percent").textContent = detail.progress + " %";
    $("progress").value = detail.progress;
  }
  if (detail?.status === "failed") notice(detail.error);
  if (!ready) return;
  const {kpis: k, analysis: a, warnings} = detail.result;
  $("report-filename").textContent = detail.filename;
  $("report-mode").textContent = a.used_model === "local" ? "Synthèse locale" : a.is_fallback ? "Synthèse de secours" : "Analyse Gemini";
  $("ca").textContent = money(k.ca_annuel);
  $("charges").textContent = money(k.charges_annuelles);
  $("resultat").textContent = money(k.resultat_exploitation_annuel);
  $("marge").textContent = k.ca_annuel ? money(k.marge_brute_annuelle) + " %" : "N/D";
  $("year-label").textContent = k.annee;
  $("best-month").textContent = k.mois_plus_fort;
  $("worst-month").textContent = k.mois_plus_faible;
  $("personnel").textContent = money(k.charges_personnel_pourcentage) + " %";
  $("alert-count").textContent = k.anomalies_detectees.length + warnings.length;
  $("monthly-rows").replaceChildren(...Object.keys(k.ca_mensuel).map(month => {
    const row = node("tr");
    for (const value of [month, money(k.ca_mensuel[month]), money(k.charges_mensuelles[month]),
      money(k.resultat_exploitation_mensuel[month]), k.ca_mensuel[month] ? money(k.marge_brute_mensuelle[month]) : "N/D"]) row.append(node("td", value));
    return row;
  }));
  $("warnings").replaceChildren(...warnings.map(w => node("li", w)));
  $("anomaly-rows").replaceChildren(...k.anomalies_detectees.map(a => {
    const row = node("tr");
    for (const value of [a.compte, a.libelle, a.previous_month + " → " + a.month, money(a.variation_pct) + " %"]) row.append(node("td", value));
    return row;
  }));
  if (!k.anomalies_detectees.length) {
    const row = node("tr"), cell = node("td", "Aucune variation dépassant le seuil configuré."); cell.colSpan = 4; row.append(cell); $("anomaly-rows").append(row);
  }
  $("analysis-note").textContent = $("report-mode").textContent + " · " + new Date(a.generated_at).toLocaleString("fr-FR");
  $("analysis-summary").textContent = a.resume;
  $("analysis-trends").textContent = a.tendances;
  $("analysis-actions").textContent = a.recommandations;
  drawChart();
}
function renderHistory() {
  const pages = Math.max(1, Math.ceil(reports.length / 20));
  page = Math.min(page, pages - 1);
  $("report-count").textContent = reports.length;
  $("history-total").textContent = reports.length + " rapport(s)";
  $("history-rows").replaceChildren(...reports.slice(page * 20, (page + 1) * 20).map(report => {
    const row = node("tr"), name = node("td", undefined, "file-name");
    name.append(node("span", report.filename), node("small", report.task_id.slice(0, 8)));
    row.append(name, node("td", report.year), node("td", new Date(report.created_at).toLocaleDateString("fr-FR")));
    const status = node("td"), actions = node("td");
    status.append(node("span", statusText[report.status], "status " + report.status));
    actions.append(iconButton("arrow-up-right", "Ouvrir " + report.filename, () => selectReport(report.task_id).catch(error => notice(error.message))));
    if (report.status === "completed") actions.append(iconButton("download", "Télécharger " + report.filename, () => saveBlob("/download/" + report.task_id, "rapport_" + report.year + ".pdf").catch(error => notice(error.message))));
    if (["failed", "completed"].includes(report.status)) actions.append(iconButton("trash-2", "Supprimer " + report.filename, () => {
      deletion = report; $("delete-filename").textContent = report.filename; $("delete-dialog").showModal();
    }));
    row.append(status, actions); return row;
  }));
  if (!reports.length) {
    const row = node("tr"), cell = node("td", "Aucun rapport enregistré."); cell.colSpan = 5; row.append(cell); $("history-rows").append(row);
  }
  $("page-info").textContent = "Page " + (page + 1) + " / " + pages;
  $("prev-page").disabled = page === 0; $("next-page").disabled = page === pages - 1;
  icons();
}
async function selectReport(id) {
  selectedId = id; $("selected-report").value = id; notice("");
  detail = id ? await api("/reports/" + id) : null;
  renderDetail(); switchView("dashboard");
}
async function refresh() {
  if (!token) return;
  if (refreshBusy) { refreshingRequested = true; return; }
  refreshBusy = true;
  try {
    let result, offset = 0, all = [];
    do {
      result = await api("/reports?limit=100&offset=" + offset);
      all = all.concat(result.items); offset += result.items.length;
    } while (offset < result.total && result.items.length);
    reports = all;
    if (!selectedId || !reports.some(r => r.task_id === selectedId)) selectedId = reports[0]?.task_id || "";
    updateOptions(); renderHistory();
    if (selectedId) {
      const summary = reports.find(r => r.task_id === selectedId);
      if (!detail || detail.task_id !== selectedId || detail.updated_at !== summary.updated_at) {
        detail = await api("/reports/" + selectedId); renderDetail();
      }
    } else { detail = null; renderDetail(); }
  } finally {
    refreshBusy = false;
    if (refreshingRequested) { refreshingRequested = false; await refresh(); }
  }
}
async function unlock() {
  sessionInfo = await api("/session");
  sessionStorage.setItem("reporting-key", token);
  $("login-dialog").close();
  $("access-key").value = "";
  $("use-ai").disabled = !sessionInfo.ai_available;
  $("ai-availability").textContent = sessionInfo.ai_available ? "" : "Gemini non configuré. Synthèse locale disponible.";
  await refresh();
}
function openImport() { $("import-error").hidden = true; updateOptions(); $("import-dialog").showModal(); }

$("login-form").addEventListener("submit", async event => {
  event.preventDefault(); $("login-error").hidden = true;
  token = $("access-key").value.trim();
  const button = event.submitter; button.disabled = true;
  try { await unlock(); } catch (error) { showError("login-error", error); } finally { button.disabled = false; }
});
$("login-dialog").addEventListener("cancel", e => e.preventDefault());
$("logout").addEventListener("click", lock);
$("open-import").addEventListener("click", openImport);
$("empty-import").addEventListener("click", openImport);
$("close-import").addEventListener("click", () => $("import-dialog").close());
$("import-year").addEventListener("input", updateOptions);
$("csv-file").addEventListener("change", () => {
  const match = $("csv-file").files[0]?.name.match(/(?:^|[_ -])((?:19|20)\d{2})(?=[_. -]|$)/);
  if (match) { $("import-year").value = match[1]; updateOptions(); }
});
document.querySelectorAll("[data-view]").forEach(b => b.addEventListener("click", () => switchView(b.dataset.view)));
document.querySelectorAll("[data-tab]").forEach(b => {
  b.addEventListener("click", () => switchTab(b.dataset.tab));
  b.addEventListener("keydown", event => {
    const tabs = [...document.querySelectorAll("[data-tab]")];
    let index = tabs.indexOf(b);
    if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") index = (index + tabs.length - 1) % tabs.length;
    else if (event.key === "Home") index = 0;
    else if (event.key === "End") index = tabs.length - 1;
    else return;
    event.preventDefault(); switchTab(tabs[index].dataset.tab, true);
  });
});
$("selected-report").addEventListener("change", () => selectReport($("selected-report").value).catch(error => notice(error.message)));
$("refresh").addEventListener("click", () => refresh().catch(error => notice(error.message)));
$("download").addEventListener("click", () => saveBlob("/download/" + selectedId, "rapport_" + detail.year + ".pdf").catch(error => notice(error.message)));
$("prev-page").addEventListener("click", () => { page--; renderHistory(); });
$("next-page").addEventListener("click", () => { page++; renderHistory(); });
document.querySelectorAll("[data-example]").forEach(b => b.addEventListener("click", () => saveBlob("/examples/" + b.dataset.example, "demo_" + b.dataset.example + ".csv").catch(error => showError("import-error", error))));
$("import-form").addEventListener("submit", async event => {
  event.preventDefault(); $("import-error").hidden = true;
  const file = $("csv-file").files[0]; if (!file) return;
  if (file.size > sessionInfo.max_upload_size_mb * 1024 * 1024) return showError("import-error", new Error("Fichier trop volumineux."));
  const body = new FormData(); body.append("file", file); body.append("year", $("import-year").value);
  body.append("use_ai", $("use-ai").checked); body.append("baseline_id", $("baseline-report").value);
  $("submit-import").disabled = true;
  try {
    const result = await api("/upload", {method: "POST", body});
    selectedId = result.task_id; detail = null; $("import-dialog").close(); $("import-form").reset();
    switchView("dashboard"); notice("Import validé. Génération du rapport en cours."); await refresh();
  } catch (error) { showError("import-error", error); } finally { $("submit-import").disabled = false; }
});
$("compare-form").addEventListener("submit", async event => {
  event.preventDefault(); $("compare-error").hidden = true; $("comparison-result").hidden = true;
  try {
    const result = await api("/compare?previous_id=" + $("previous-report").value + "&current_id=" + $("current-report").value);
    $("comparison-title").textContent = result.previous_year + " → " + result.current_year;
    const labels = {ca_annuel: "Chiffre d'affaires (TND)", charges_annuelles: "Charges (TND)", resultat_exploitation_annuel: "Solde produits − charges (TND)", marge_brute_annuelle: "Marge brute (%)"};
    $("comparison-rows").replaceChildren(...Object.entries(result.indicators).map(([key, value]) => {
      const row = node("tr");
      const variation = key === "marge_brute_annuelle" ? "—" : value.variation_pct === null ? "N/D" : money(value.variation_pct) + " %";
      for (const text of [labels[key], money(value.previous), money(value.current), money(value.difference) + (key === "marge_brute_annuelle" ? " pts" : ""), variation]) row.append(node("td", text));
      return row;
    }));
    $("comparison-empty").hidden = true; $("comparison-result").hidden = false;
  } catch (error) { showError("compare-error", error); }
});
$("cancel-delete").addEventListener("click", () => $("delete-dialog").close());
$("confirm-delete").addEventListener("click", async () => {
  if (!deletion) return;
  $("confirm-delete").disabled = true;
  try {
    await api("/reports/" + deletion.task_id, {method: "DELETE"});
    if (selectedId === deletion.task_id) { selectedId = ""; detail = null; }
    $("delete-dialog").close(); notice("Rapport supprimé."); deletion = null; await refresh();
  } catch (error) { $("delete-dialog").close(); notice(error.message); }
  finally { $("confirm-delete").disabled = false; }
});
setInterval(() => {
  if (token && !document.hidden && reports.some(r => ["pending", "processing"].includes(r.status))) refresh().catch(error => notice(error.message));
}, 1800);
icons();
if (token) unlock().catch(error => { lock(); showError("login-error", error); }); else lock();
