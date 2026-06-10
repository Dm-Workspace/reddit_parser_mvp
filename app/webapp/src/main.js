/**
 * Trend Intelligence Hub — Mini App v6.2
 * Source-aware presets: Reddit + YouTube-ready architecture
 */

// ── Global labels ──────────────────────────────────────────────────────────────
let LABELS = {
  run_modes: {
    hot_last_7d:  { label: "Горячие обсуждения за 7 дней" },
    rising_24h:   { label: "Быстро растущие темы за 24 часа" },
    top_week:     { label: "Лучшее за неделю" },
    top_month:    { label: "Лучшее за месяц" },
  },
  schedules: {
    manual:   { label: "Только ручной запуск" },
    weekly:   { label: "1 раз в неделю" },
    biweekly: { label: "1 раз в 2 недели" },
    monthly:  { label: "1 раз в месяц" },
    disabled: { label: "Отключено" },
  },
  statuses: {
    running:                { label: "Выполняется",               color: "blue"   },
    completed:              { label: "Завершён",                  color: "green"  },
    completed_with_warning: { label: "Завершён с предупреждением", color: "yellow" },
    failed:                 { label: "Ошибка",                    color: "red"    },
    queued:                 { label: "В очереди",                 color: "gray"   },
  },
};

// ── State ──────────────────────────────────────────────────────────────────────
let state = {
  projects: [],
  srPresets: [],
  kwPresets: [],
  presetPacks: [],
  currentSource: "reddit",
  currentPresetPack: null,
  currentProjectId: null,
  currentMonitorId: null,
  currentRunId: null,
};

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  window.TG.init();
  document.body.classList.add(window.TG.themeClass());

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  document.getElementById("btn-create-project").addEventListener("click", openCreateProject);
  document.getElementById("btn-save-project").addEventListener("click", saveProject);
  document.getElementById("btn-save-monitor").addEventListener("click", saveMonitor);

  // Load labels (fallback to defaults on failure)
  try { const l = await API.getLabels(); if (l) LABELS = l; } catch {}

  await Promise.all([
    loadDashboard(),
    loadProjects(),
    loadRuns(),
    loadStatus(),
    loadPresets(),
  ]);
});

// ── Tab navigation ─────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById("tab-" + name)?.classList.add("active");
  document.querySelector(`.tab-btn[data-tab="${name}"]`)?.classList.add("active");
}

// ── Label helpers ──────────────────────────────────────────────────────────────
const labelRunMode  = id => (LABELS.run_modes?.[id] || {}).label  || id;
const labelSchedule = id => (LABELS.schedules?.[id] || {}).label  || id;
const labelStatus   = id => (LABELS.statuses?.[id]  || {}).label  || id;

function statusBadgeClass(s) {
  return { completed: "badge-ok", failed: "badge-err", completed_with_warning: "badge-warn", running: "badge-run", queued: "badge-run" }[s] || "badge-run";
}
function statusIcon(s) {
  return { completed: "✅", completed_with_warning: "⚠️", failed: "❌", running: "⚙️", queued: "📋" }[s] || "❓";
}

// ── Dashboard ──────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [projects, runs] = await Promise.all([
      API.listProjects().catch(() => []),
      API.listRuns({ limit: 5 }).catch(() => []),
    ]);
    state.projects = projects;
    let totalMonitors = 0;
    for (const p of projects) {
      const mons = await API.listMonitors(p.id).catch(() => []);
      totalMonitors += mons.length;
    }
    document.getElementById("stat-projects").querySelector(".stat-num").textContent = projects.length;
    document.getElementById("stat-monitors").querySelector(".stat-num").textContent = totalMonitors;
    document.getElementById("stat-runs").querySelector(".stat-num").textContent = runs.length;

    const recentEl = document.getElementById("recent-runs-list");
    recentEl.innerHTML = runs.length === 0
      ? '<div class="empty-state"><div class="empty-icon">🕐</div><div class="empty-text">Запусков ещё нет</div><div class="empty-sub">Создайте проект, настройте монитор и запустите первый сбор трендов</div></div>'
      : runs.map(renderRunCard).join("");
  } catch {}
}

// ── Projects ───────────────────────────────────────────────────────────────────
async function loadProjects() {
  const el = document.getElementById("projects-list");
  el.innerHTML = '<div class="loading">Загрузка…</div>';
  try {
    const projects = await API.listProjects();
    state.projects = projects;
    const hintEl = document.getElementById("projects-hint");
    if (hintEl) hintEl.textContent = projects.length === 0 ? "На старте можно создать до 3 проектов." : `У вас ${projects.length} проект${projects.length === 1 ? "" : projects.length < 5 ? "а" : "ов"}.`;

    if (projects.length === 0) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">📁</div><div class="empty-text">Нет проектов</div><div class="empty-sub">Нажмите «Создать проект». Например: Нутрициология, Психология, Маркетинг услуг.</div></div>`;
      return;
    }
    el.innerHTML = projects.map(p => `
      <div class="card" onclick="openProjectDetail('${p.id}')">
        <div class="card-title">${esc(p.name)}</div>
        <div class="card-meta"><span>${esc(p.niche||"—")}</span><span class="card-badge badge-ok">${p.output_language.toUpperCase()}</span></div>
      </div>`).join("");

    const sel = document.getElementById("runs-filter-project");
    if (sel) {
      sel.innerHTML = '<option value="">Все проекты</option>' + projects.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
      sel.onchange = () => loadRuns(sel.value);
    }
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>`;
  }
}

function openCreateProject() {
  ["proj-name","proj-desc","proj-niche"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("proj-lang").value = "en";
  openModal("modal-project-create");
}

async function saveProject() {
  const name = document.getElementById("proj-name").value.trim();
  if (!name) { showToast("Введите название проекта"); return; }
  const btn = document.getElementById("btn-save-project");
  btn.disabled = true;
  try {
    await API.createProject({ name, description: document.getElementById("proj-desc").value.trim(), niche: document.getElementById("proj-niche").value.trim(), output_language: document.getElementById("proj-lang").value });
    closeModal(); showToast("✅ Проект создан"); window.TG.haptic("success");
    loadProjects(); loadDashboard();
  } catch (e) { showToast("Ошибка: " + e.message); }
  finally { btn.disabled = false; }
}

async function openProjectDetail(projectId) {
  state.currentProjectId = projectId;
  try {
    const [project, monitors] = await Promise.all([API.getProject(projectId), API.listMonitors(projectId)]);
    document.getElementById("proj-detail-name").textContent = project.name;
    document.getElementById("proj-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Ниша</span><span class="info-val">${esc(project.niche||"—")}</span></div>
      <div class="info-row"><span class="info-key">Язык</span><span class="info-val">${project.output_language.toUpperCase()}</span></div>
      <div class="info-row"><span class="info-key">Мониторов</span><span class="info-val">${monitors.length}</span></div>
      <div class="monitor-list-in-proj">
        <b style="font-size:13px;display:block;margin-top:12px;margin-bottom:6px">Мониторы:</b>
        ${monitors.length === 0 ? "<div class='empty-sub'>Нет мониторов — создайте первый ниже</div>" :
          monitors.map(m => {
            const srcIcon = m.source === "youtube" ? "🔴" : "🟠";
            const enIcon  = m.enabled && !m.archived ? "🟢" : "⚫";
            return `<div class="monitor-item" onclick="openMonitorDetail('${m.id}')">
              <span>${enIcon} ${esc(m.name)} <span style="font-size:10px">${srcIcon}</span></span>
              <span style="font-size:11px;color:var(--tg-theme-hint-color,#888)">${labelRunMode(m.run_mode)}</span>
            </div>`;
          }).join("")
        }
      </div>`;
    document.getElementById("btn-create-monitor-for-proj").onclick = () => { closeModal(); openCreateMonitor(projectId); };
    openModal("modal-project-detail");
  } catch { showToast("Ошибка загрузки проекта"); }
}

// ── Monitors / Create ──────────────────────────────────────────────────────────
async function loadPresets() {
  try {
    const [sr, kw, packs] = await Promise.all([
      API.listSubredditPresets(),
      API.listKeywordPresets(),
      API.listPresetPacks(),
    ]);
    state.srPresets = sr;
    state.kwPresets = kw;
    state.presetPacks = packs;
  } catch {}
}

function openCreateMonitor(projectId) {
  document.getElementById("mon-project-id").value = projectId;
  ["mon-name","mon-desc","mon-custom-subs","mon-custom-kws"].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = "";
  });
  const qa = document.getElementById("mon-custom-queries"); if (qa) qa.value = "";
  document.getElementById("mon-run-mode").value = "hot_last_7d";
  document.getElementById("mon-schedule-mode").value = "manual";
  state.currentSource = "reddit";
  state.currentPresetPack = null;

  _populatePresetPackSelect("reddit");
  selectSource("reddit");
  openModal("modal-monitor-create");
}

function _populatePresetPackSelect(source) {
  const sel = document.getElementById("mon-preset-pack");
  const packs = state.presetPacks.filter(p => p.sources && p.sources.includes(source));
  sel.innerHTML = '<option value="">— Выберите нишевой пресет —</option>' +
    packs.map(p => `<option value="${p.id}">${esc(p.label)}</option>`).join("");
  sel.onchange = () => onPresetPackChange();
  document.getElementById("preset-summary").classList.add("hidden");
  document.getElementById("preset-summary").innerHTML = "";
  state.currentPresetPack = null;
}

function selectSource(source) {
  state.currentSource = source;
  // Update tab buttons
  document.querySelectorAll(".source-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.source === source);
  });
  // Update hint text
  const hints = { reddit: "Reddit — анализ живых обсуждений, болей и вопросов аудитории.", youtube: "YouTube — анализ видео, форматов, заголовков и комментариев." };
  document.getElementById("source-hint").textContent = hints[source] || "";
  // Show/hide source panels
  document.getElementById("reddit-settings").style.display = source === "reddit" ? "block" : "none";
  document.getElementById("youtube-settings").style.display = source === "youtube" ? "block" : "none";
  // Repopulate presets
  _populatePresetPackSelect(source);
}

async function onPresetPackChange() {
  const packId = document.getElementById("mon-preset-pack").value;
  const summaryEl = document.getElementById("preset-summary");
  const redditCustom = document.getElementById("reddit-custom-inputs");
  const ytCustom = document.getElementById("youtube-custom-inputs");

  if (!packId) {
    summaryEl.classList.add("hidden");
    summaryEl.innerHTML = "";
    state.currentPresetPack = null;
    if (redditCustom) redditCustom.style.display = "none";
    if (ytCustom) ytCustom.style.display = "none";
    return;
  }

  if (packId === "custom_manual") {
    summaryEl.classList.add("hidden");
    state.currentPresetPack = { id: "custom_manual" };
    if (redditCustom) redditCustom.style.display = state.currentSource === "reddit" ? "block" : "none";
    if (ytCustom) ytCustom.style.display = state.currentSource === "youtube" ? "block" : "none";
    return;
  }

  if (redditCustom) redditCustom.style.display = "none";
  if (ytCustom) ytCustom.style.display = "none";

  try {
    const pack = await API.getPresetPack(packId);
    state.currentPresetPack = pack;

    if (state.currentSource === "reddit" && pack.reddit) {
      const subs = (pack.reddit.subreddits || []).slice(0, 8).join(", ") + (pack.reddit.subreddits.length > 8 ? "…" : "");
      const kws  = (pack.reddit.keywords || []).slice(0, 8).join(", ") + (pack.reddit.keywords.length > 8 ? "…" : "");
      summaryEl.innerHTML = `
        <div class="preset-summary-row"><b>Сообщества Reddit:</b> <span class="preset-tags">${esc(subs)}</span></div>
        <div class="preset-summary-row"><b>Ключевые слова:</b> <span class="preset-tags">${esc(kws)}</span></div>`;
      if (pack.reddit.default_run_mode) {
        document.getElementById("mon-run-mode").value = pack.reddit.default_run_mode;
      }
    } else if (state.currentSource === "youtube" && pack.youtube) {
      const queries = (pack.youtube.search_queries || []).slice(0, 5).map(q => `<li>${esc(q)}</li>`).join("");
      const channels = pack.youtube.channels && pack.youtube.channels.length > 0
        ? pack.youtube.channels.join(", ")
        : "Поиск по всему YouTube";
      summaryEl.innerHTML = `
        <div class="preset-summary-row"><b>Поисковые запросы:</b><ul class="preset-query-list">${queries}</ul></div>
        <div class="preset-summary-row"><b>Каналы:</b> <span>${esc(channels)}</span></div>`;
      // Pre-fill YouTube settings from pack
      if (pack.youtube.published_period) {
        const p = document.getElementById("yt-period"); if (p) p.value = pack.youtube.published_period;
      }
      if (pack.youtube.min_views) {
        const v = document.getElementById("yt-min-views"); if (v) v.value = String(pack.youtube.min_views);
      }
    }
    summaryEl.classList.remove("hidden");
  } catch { summaryEl.classList.add("hidden"); }
}

async function saveMonitor() {
  const name = document.getElementById("mon-name").value.trim();
  const projectId = document.getElementById("mon-project-id").value;
  if (!name) { showToast("Введите название монитора"); return; }

  const source = state.currentSource;
  const packId = state.currentPresetPack?.id || document.getElementById("mon-preset-pack").value || null;
  const isCustom = packId === "custom_manual" || !packId;

  // Build source_config
  let sourceConfig = {};
  if (source === "reddit") {
    const pack = (state.currentPresetPack?.reddit) ? state.currentPresetPack : null;
    let subs = pack?.reddit?.subreddits || [];
    let kws  = pack?.reddit?.keywords   || [];
    if (isCustom) {
      const rawSubs = document.getElementById("mon-custom-subs")?.value || "";
      const rawKws  = document.getElementById("mon-custom-kws")?.value || "";
      subs = rawSubs.split(",").map(s => s.trim()).filter(Boolean);
      kws  = rawKws.split(",").map(s => s.trim()).filter(Boolean);
    }
    sourceConfig = { preset_pack_id: packId, subreddits: subs, keywords: kws, run_mode: document.getElementById("mon-run-mode").value };
  } else if (source === "youtube") {
    const pack = (state.currentPresetPack?.youtube) ? state.currentPresetPack : null;
    let queries  = pack?.youtube?.search_queries || [];
    let channels = pack?.youtube?.channels || [];
    if (isCustom) {
      const rawQ = document.getElementById("mon-custom-queries")?.value || "";
      queries = rawQ.split("\n").map(s => s.trim()).filter(Boolean);
      const rawC = document.getElementById("mon-custom-channels")?.value || "";
      channels = rawC.split(",").map(s => s.trim()).filter(Boolean);
    }
    const period   = document.getElementById("yt-period")?.value    || "last_90d";
    const minViews = parseInt(document.getElementById("yt-min-views")?.value) || 500;
    const fmt      = document.getElementById("yt-format")?.value    || "no_shorts";
    const maxComs  = parseInt(document.getElementById("yt-comments")?.value) || 20;
    sourceConfig = {
      preset_pack_id: packId, search_queries: queries, channels,
      published_period: period, min_views: minViews,
      include_shorts: fmt === "include_shorts" || fmt === "only_shorts",
      only_shorts: fmt === "only_shorts",
      include_comments: maxComs > 0,
      max_comments_per_video: maxComs,
      language: "en", region: "US",
    };
  }

  const scheduleEl = source === "reddit"
    ? document.getElementById("mon-schedule-mode")
    : document.getElementById("yt-schedule-mode");

  const btn = document.getElementById("btn-save-monitor");
  btn.disabled = true;
  try {
    await API.createMonitor({
      project_id: projectId, name,
      description: document.getElementById("mon-desc").value.trim(),
      source,
      preset_pack_id: packId,
      source_config: JSON.stringify(sourceConfig),
      subreddit_preset_id: null,
      keyword_preset_id: null,
      custom_subreddits: source === "reddit" ? (sourceConfig.subreddits || []) : [],
      custom_keywords:   source === "reddit" ? (sourceConfig.keywords   || []) : [],
      run_mode: source === "reddit" ? (sourceConfig.run_mode || "hot_last_7d") : "hot_last_7d",
      schedule_mode: scheduleEl?.value || "manual",
    });
    closeModal(); showToast("✅ Монитор создан"); window.TG.haptic("success");
    loadDashboard(); loadProjects();
  } catch (e) { showToast("Ошибка: " + e.message); }
  finally { btn.disabled = false; }
}

async function openMonitorDetail(monitorId) {
  state.currentMonitorId = monitorId;
  try {
    const [monitor, runs] = await Promise.all([API.getMonitor(monitorId), API.listRuns({ monitor_id: monitorId, limit: 5 })]);
    document.getElementById("mon-detail-name").textContent = monitor.name;
    const srcIcon = monitor.source === "youtube" ? "🔴 YouTube" : "🟠 Reddit";
    document.getElementById("mon-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Источник</span><span class="info-val">${srcIcon}</span></div>
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(monitor.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Режим</span><span class="info-val">${labelRunMode(monitor.run_mode)}</span></div>
      <div class="info-row"><span class="info-key">Расписание</span><span class="info-val">${labelSchedule(monitor.schedule_mode)}</span></div>
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${monitor.enabled && !monitor.archived ? "🟢 Активен" : "⚫ Неактивен"}</span></div>
      ${monitor.preset_pack_id ? `<div class="info-row"><span class="info-key">Пресет</span><span class="info-val">${esc(monitor.preset_pack_id)}</span></div>` : ""}
      ${monitor.source === "youtube" ? '<div class="alert-block alert-warn" style="margin-top:8px"><b>🔴 YouTube не активен</b><br>Запуск будет доступен после подключения YouTube Core.</div>' : ""}
      <div style="margin-top:12px;font-size:13px;font-weight:600">Последние запуски:</div>
      ${runs.length === 0 ? "<div class='empty-sub' style='margin-top:8px'>Запусков ещё нет</div>" : runs.map(renderRunCard).join("")}`;
    const runBtn = document.getElementById("btn-run-monitor-now");
    if (monitor.source === "youtube") {
      runBtn.disabled = true;
      runBtn.textContent = "🔴 YouTube не активен";
    } else {
      runBtn.disabled = false;
      runBtn.textContent = "▶️ Запустить сейчас";
      runBtn.onclick = () => triggerRun(monitorId);
    }
    openModal("modal-monitor-detail");
  } catch { showToast("Ошибка загрузки монитора"); }
}

async function triggerRun(monitorId) {
  const btn = document.getElementById("btn-run-monitor-now");
  btn.disabled = true; btn.textContent = "⏳ Запускается…";
  showToast("⏳ Запуск монитора… Это займёт 5–10 минут");
  try {
    const result = await API.runMonitor(monitorId);
    closeModal();
    showToast(`${statusIcon(result.status)} ${labelStatus(result.status)}! Постов: ${result.total_posts}, Комментариев: ${result.total_comments}`, 5000);
    window.TG.haptic("success"); loadRuns(); loadDashboard();
  } catch (e) { showToast("Ошибка запуска: " + e.message, 5000); window.TG.haptic("error"); }
  finally { btn.disabled = false; btn.textContent = "▶️ Запустить сейчас"; }
}

// ── Runs ───────────────────────────────────────────────────────────────────────
async function loadRuns(projectId) {
  const el = document.getElementById("runs-list");
  el.innerHTML = '<div class="loading">Загрузка…</div>';
  try {
    const params = { limit: 30 };
    if (projectId) params.project_id = projectId;
    const runs = await API.listRuns(params);
    if (runs.length === 0) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">🕐</div><div class="empty-text">Нет запусков</div><div class="empty-sub">Запустите монитор, чтобы начать сбор данных</div></div>';
      return;
    }
    el.innerHTML = runs.map(renderRunCard).join("");
  } catch { el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>'; }
}

function renderRunCard(r) {
  const icon = statusIcon(r.status); const badgeClass = statusBadgeClass(r.status);
  return `<div class="card" onclick="openRunDetail('${r.id}')">
    <div class="card-title">${icon} ${esc(r.monitor_id)}</div>
    <div class="card-meta">
      <span class="card-badge ${badgeClass}">${labelStatus(r.status)}</span>
      <span>${r.total_posts}п / ${r.total_comments}к</span>
      <span>${(r.started_at||"").substring(0,16).replace("T"," ")}</span>
    </div>
  </div>`;
}

async function openRunDetail(runId) {
  state.currentRunId = runId;
  try {
    const run = await API.getRun(runId);
    let alertHtml = "";
    if (run.status === "failed" && run.error_message) {
      alertHtml = `<div class="alert-block alert-error"><b>❌ Ошибка:</b><br>${esc(run.error_message.substring(0,400))}</div>`;
    } else if (run.status === "completed_with_warning" && run.warning_message) {
      alertHtml = `<div class="alert-block alert-warn"><b>⚠️ Предупреждение:</b><br>${esc(run.warning_message.substring(0,300))}</div>`;
    }
    let downloadsHtml = "";
    if (run.exports && run.exports.length > 0) {
      const fmtInfo = { xlsx: { label: "📊 Excel", hint: "Для ручного анализа" }, json: { label: "📄 JSON", hint: "Для интеграций" }, handoff_json: { label: "🤖 Handoff", hint: "Для AI-агента" } };
      downloadsHtml = '<div class="downloads-header">Скачать:</div><div class="download-links">';
      for (const exp of run.exports) {
        if (exp.file_path || exp.drive_web_view_link) {
          const info = fmtInfo[exp.format] || { label: exp.format, hint: "" };
          const fmt = exp.format === "handoff_json" ? "handoff" : exp.format;
          const href = exp.drive_web_view_link || API.getDownloadUrl(run.id, fmt);
          downloadsHtml += `<a class="download-link" href="${href}" target="_blank" title="${info.hint}">${info.label}${exp.drive_web_view_link?" ☁️":""}</a>`;
        }
      }
      downloadsHtml += `</div><div class="hint-text" style="margin-top:8px">База данных хранит только метаданные запуска и ссылки на файлы.</div>`;
    }
    document.getElementById("run-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${statusIcon(run.status)} ${labelStatus(run.status)}</span></div>
      <div class="info-row"><span class="info-key">Монитор</span><span class="info-val">${esc(run.monitor_id)}</span></div>
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(run.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Постов</span><span class="info-val">${run.total_posts}</span></div>
      <div class="info-row"><span class="info-key">Комментариев</span><span class="info-val">${run.total_comments}</span></div>
      <div class="info-row"><span class="info-key">Запущен</span><span class="info-val">${(run.started_at||"—").substring(0,16).replace("T"," ")}</span></div>
      ${alertHtml}${downloadsHtml}`;
    openModal("modal-run-detail");
  } catch { showToast("Ошибка загрузки запуска"); }
}

// ── Status ─────────────────────────────────────────────────────────────────────
async function loadStatus() {
  const el = document.getElementById("status-info");
  try {
    const [s, sources] = await Promise.all([API.getStatus(), API.listSources().catch(() => [])]);
    const storageLabel = { local: "Локально", google_drive: "Google Drive", s3: "Amazon S3", r2: "Cloudflare R2", railway_bucket: "Railway Storage" }[s.storage_provider] || s.storage_provider || "Локально";
    const srcStatusIcon = { active: "✅", prepared: "🔵", coming_soon: "⏳", disabled: "⚫" };
    const srcStatusLabel = { active: "Активен", prepared: "Подготовлен", coming_soon: "Скоро", disabled: "Отключён" };

    const sourcesHtml = sources.map(src => {
      const stIcon  = srcStatusIcon[src.status]  || "❓";
      const stLabel = srcStatusLabel[src.status] || src.status;
      let extra = "";
      if (src.integration_branch) {
        extra = `<div class="hint-text" style="margin-top:2px">Branch: ${esc(src.integration_branch)} · Tag: ${esc(src.integration_tag||"")}</div>`;
      }
      return `<div class="status-row" style="flex-direction:column;align-items:flex-start">
        <div style="display:flex;justify-content:space-between;width:100%">
          <span class="status-key">${src.icon||""} ${esc(src.label)}</span>
          <span class="status-val">${stIcon} ${stLabel}</span>
        </div>
        ${extra}
      </div>`;
    }).join("");

    el.innerHTML = `
      <div class="status-section-title">Система</div>
      ${statusRow("Версия", s.app_version||"—", "")}
      ${statusRow("База данных", s.database, s.database==="connected"?"status-ok":"status-err")}
      ${statusRow("Telegram bot", s.telegram_bot_configured?"✅ настроен":"⚠️ не задан", s.telegram_bot_configured?"status-ok":"status-warn")}
      ${statusRow("Google Drive", s.drive_configured?"✅ настроен":"⚠️ не настроен", s.drive_configured?"status-ok":"status-warn")}

      <div class="status-section-title" style="margin-top:16px">Источники данных</div>
      ${sourcesHtml || statusRow("Reddit", "загрузка…", "")}

      <div class="status-section-title" style="margin-top:16px">Хранение отчётов</div>
      ${statusRow("Провайдер", storageLabel, "")}
      ${statusRow("Хранить файлы", (s.export_retention_days||30)+" дней", "")}
      ${statusRow("Авто-очистка", s.cleanup_local_files?"включена":"выключена", "")}
      <div class="hint-text">PostgreSQL хранит только метаданные (статус, счётчики, ссылки). Полные данные — в Excel/JSON-файлах.</div>

      <div class="status-section-title" style="margin-top:16px">Поддержка</div>
      <div class="status-row"><span class="status-key">🌐 Сайт</span><a href="https://up-level.pro" target="_blank" class="status-link">up-level.pro</a></div>
      <div class="status-row"><span class="status-key">💬 Telegram</span><a href="https://t.me/kdm_app" target="_blank" class="status-link">@kdm_app</a></div>`;
  } catch { el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки статуса</div></div>'; }
}

function statusRow(key, val, cls) {
  return `<div class="status-row"><span class="status-key">${esc(key)}</span><span class="status-val ${cls}">${esc(String(val))}</span></div>`;
}

// ── Modals ─────────────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById(id).classList.remove("hidden");
}
function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  document.querySelectorAll(".modal").forEach(m => m.classList.add("hidden"));
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function esc(s) { return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function showToast(msg, dur) {
  const t = document.getElementById("toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(t._timer); t._timer = setTimeout(() => t.classList.add("hidden"), dur||3000);
}
