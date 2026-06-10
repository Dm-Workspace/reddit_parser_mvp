/**
 * Trend Intelligence Hub — Mini App v6.1
 * UX improvements: i18n labels, form hints, storage info, support contacts
 */

// ── Global labels (loaded from /api/labels) ────────────────────────────────────
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

  // Load labels first (fail-safe: use defaults if API unavailable)
  try {
    const fetched = await API.getLabels();
    if (fetched) LABELS = fetched;
  } catch {}

  // Load all tabs in parallel
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
  document.querySelectorAll(".tab-content").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach((el) => el.classList.remove("active"));
  const tab = document.getElementById("tab-" + name);
  if (tab) tab.classList.add("active");
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  if (btn) btn.classList.add("active");
}

// ── Label helpers ──────────────────────────────────────────────────────────────
function labelRunMode(id) {
  return (LABELS.run_modes[id] || {}).label || id;
}
function labelSchedule(id) {
  return (LABELS.schedules[id] || {}).label || id;
}
function labelStatus(id) {
  return (LABELS.statuses[id] || {}).label || id;
}
function statusBadgeClass(status) {
  const map = { completed: "badge-ok", failed: "badge-err", completed_with_warning: "badge-warn", running: "badge-run", queued: "badge-run" };
  return map[status] || "badge-run";
}
function statusIcon(status) {
  const map = { completed: "✅", completed_with_warning: "⚠️", failed: "❌", running: "⚙️", queued: "📋" };
  return map[status] || "❓";
}

// ── Dashboard ──────────────────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [projects, runs, status] = await Promise.all([
      API.listProjects().catch(() => []),
      API.listRuns({ limit: 5 }).catch(() => []),
      API.getStatus().catch(() => ({})),
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
    const dbEl = document.getElementById("stat-db");
    dbEl.querySelector(".stat-num").textContent = status.database === "connected" ? "✅" : "❌";

    const recentEl = document.getElementById("recent-runs-list");
    if (runs.length === 0) {
      recentEl.innerHTML = '<div class="empty-state"><div class="empty-icon">🕐</div><div class="empty-text">Запусков ещё нет</div><div class="empty-sub">Создайте проект, настройте монитор и запустите первый сбор трендов</div></div>';
    } else {
      recentEl.innerHTML = runs.map(renderRunCard).join("");
    }
  } catch (e) {
    showToast("Ошибка загрузки дашборда");
  }
}

// ── Projects ───────────────────────────────────────────────────────────────────
async function loadProjects() {
  const el = document.getElementById("projects-list");
  el.innerHTML = '<div class="loading">Загрузка…</div>';
  try {
    const projects = await API.listProjects();
    state.projects = projects;

    const hintEl = document.getElementById("projects-hint");
    if (hintEl) {
      hintEl.textContent = projects.length === 0
        ? "На старте можно создать до 3 проектов."
        : `У вас ${projects.length} проект${projects.length === 1 ? "" : projects.length < 5 ? "а" : "ов"}.`;
    }

    if (projects.length === 0) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-icon">📁</div>
        <div class="empty-text">Нет проектов</div>
        <div class="empty-sub">Нажмите «Создать проект», чтобы начать. Например: Нутрициология, Психология, Маркетинг услуг.</div>
      </div>`;
      return;
    }
    el.innerHTML = projects.map((p) => `
      <div class="card" onclick="openProjectDetail('${p.id}')">
        <div class="card-title">${esc(p.name)}</div>
        <div class="card-meta">
          <span>${esc(p.niche || "—")}</span>
          <span class="card-badge badge-ok">${p.output_language.toUpperCase()}</span>
        </div>
      </div>`
    ).join("");

    const sel = document.getElementById("runs-filter-project");
    if (sel) {
      sel.innerHTML = '<option value="">Все проекты</option>' +
        projects.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
      sel.onchange = () => loadRuns(sel.value);
    }
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>`;
  }
}

function openCreateProject() {
  document.getElementById("proj-name").value = "";
  document.getElementById("proj-desc").value = "";
  document.getElementById("proj-niche").value = "";
  document.getElementById("proj-lang").value = "en";
  openModal("modal-project-create");
}

async function saveProject() {
  const name = document.getElementById("proj-name").value.trim();
  if (!name) { showToast("Введите название проекта"); return; }
  const btn = document.getElementById("btn-save-project");
  btn.disabled = true;
  try {
    await API.createProject({
      name,
      description: document.getElementById("proj-desc").value.trim(),
      niche: document.getElementById("proj-niche").value.trim(),
      output_language: document.getElementById("proj-lang").value,
    });
    closeModal();
    showToast("✅ Проект создан");
    window.TG.haptic("success");
    loadProjects();
    loadDashboard();
  } catch (e) {
    showToast("Ошибка: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function openProjectDetail(projectId) {
  state.currentProjectId = projectId;
  try {
    const [project, monitors] = await Promise.all([
      API.getProject(projectId),
      API.listMonitors(projectId),
    ]);
    document.getElementById("proj-detail-name").textContent = project.name;
    document.getElementById("proj-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Ниша</span><span class="info-val">${esc(project.niche || "—")}</span></div>
      <div class="info-row"><span class="info-key">Язык</span><span class="info-val">${project.output_language.toUpperCase()}</span></div>
      <div class="info-row"><span class="info-key">Мониторов</span><span class="info-val">${monitors.length}</span></div>
      <div class="monitor-list-in-proj">
        <b style="font-size:13px;display:block;margin-top:12px;margin-bottom:6px">Мониторы:</b>
        ${monitors.length === 0 ? "<div class='empty-sub'>Нет мониторов — создайте первый ниже</div>" :
          monitors.map((m) => `
            <div class="monitor-item" onclick="openMonitorDetail('${m.id}')">
              <span>${m.enabled && !m.archived ? "🟢" : "🔴"} ${esc(m.name)}</span>
              <span style="font-size:11px;color:var(--tg-theme-hint-color,#888)">${labelRunMode(m.run_mode)}</span>
            </div>`
          ).join("")
        }
      </div>
    `;
    document.getElementById("btn-create-monitor-for-proj").onclick = () => {
      closeModal();
      openCreateMonitor(projectId);
    };
    openModal("modal-project-detail");
  } catch (e) {
    showToast("Ошибка загрузки проекта");
  }
}

// ── Monitors ───────────────────────────────────────────────────────────────────
async function loadPresets() {
  try {
    const [sr, kw] = await Promise.all([
      API.listSubredditPresets(),
      API.listKeywordPresets(),
    ]);
    state.srPresets = sr;
    state.kwPresets = kw;
  } catch {}
}

function openCreateMonitor(projectId) {
  document.getElementById("mon-project-id").value = projectId;
  document.getElementById("mon-name").value = "";
  document.getElementById("mon-desc").value = "";
  document.getElementById("mon-run-mode").value = "hot_last_7d";
  document.getElementById("mon-schedule-mode").value = "manual";

  // Populate preset selectors with human-readable labels
  const srSel = document.getElementById("mon-sr-preset");
  srSel.innerHTML = '<option value="">— Выберите пресет —</option>' +
    state.srPresets.map((p) => {
      const label = p.label || p.name;
      const count = p.subreddits_count || (p.subreddits || []).length;
      return `<option value="${p.id}">${esc(label)}${count ? " (" + count + " sub)" : ""}</option>`;
    }).join("") +
    '<option value="__custom__">✍️ Ручная настройка</option>';

  const kwSel = document.getElementById("mon-kw-preset");
  kwSel.innerHTML = '<option value="">— Выберите пресет —</option>' +
    state.kwPresets.map((p) => {
      const label = p.label || p.name;
      const count = p.keywords_count || (p.keywords || []).length;
      return `<option value="${p.id}">${esc(label)}${count ? " (" + count + " kw)" : ""}</option>`;
    }).join("") +
    '<option value="__custom__">✍️ Ручная настройка</option>';

  // Show/hide custom inputs on preset change
  srSel.onchange = () => toggleCustomFields();
  kwSel.onchange = () => toggleCustomFields();
  toggleCustomFields();

  openModal("modal-monitor-create");
}

function toggleCustomFields() {
  const srVal = document.getElementById("mon-sr-preset").value;
  const kwVal = document.getElementById("mon-kw-preset").value;
  const customDiv = document.getElementById("custom-inputs");
  if (!customDiv) return;
  customDiv.style.display = (srVal === "__custom__" || kwVal === "__custom__") ? "block" : "none";
}

async function saveMonitor() {
  const name = document.getElementById("mon-name").value.trim();
  const projectId = document.getElementById("mon-project-id").value;
  if (!name) { showToast("Введите название монитора"); return; }

  const srVal = document.getElementById("mon-sr-preset").value;
  const kwVal = document.getElementById("mon-kw-preset").value;

  let customSubs = [];
  let customKws = [];
  if (srVal === "__custom__") {
    const raw = (document.getElementById("mon-custom-subs") || {}).value || "";
    customSubs = raw.split(",").map(s => s.trim()).filter(Boolean);
  }
  if (kwVal === "__custom__") {
    const raw = (document.getElementById("mon-custom-kws") || {}).value || "";
    customKws = raw.split(",").map(s => s.trim()).filter(Boolean);
  }

  const btn = document.getElementById("btn-save-monitor");
  btn.disabled = true;
  try {
    await API.createMonitor({
      project_id: projectId,
      name,
      description: document.getElementById("mon-desc").value.trim(),
      source: "reddit",
      subreddit_preset_id: (srVal && srVal !== "__custom__") ? srVal : null,
      keyword_preset_id: (kwVal && kwVal !== "__custom__") ? kwVal : null,
      custom_subreddits: customSubs,
      custom_keywords: customKws,
      run_mode: document.getElementById("mon-run-mode").value,
      schedule_mode: document.getElementById("mon-schedule-mode").value,
    });
    closeModal();
    showToast("✅ Монитор создан");
    window.TG.haptic("success");
    loadDashboard();
    loadProjects(); // refresh monitor counts
  } catch (e) {
    showToast("Ошибка: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function openMonitorDetail(monitorId) {
  state.currentMonitorId = monitorId;
  try {
    const [monitor, runs] = await Promise.all([
      API.getMonitor(monitorId),
      API.listRuns({ monitor_id: monitorId, limit: 5 }),
    ]);
    document.getElementById("mon-detail-name").textContent = monitor.name;
    document.getElementById("mon-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(monitor.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Режим</span><span class="info-val">${labelRunMode(monitor.run_mode)}</span></div>
      <div class="info-row"><span class="info-key">Расписание</span><span class="info-val">${labelSchedule(monitor.schedule_mode)}</span></div>
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${monitor.enabled && !monitor.archived ? "🟢 Активен" : "🔴 Неактивен"}</span></div>
      <div style="margin-top:12px;font-size:13px;font-weight:600">Последние запуски:</div>
      ${runs.length === 0 ? "<div class='empty-sub' style='margin-top:8px'>Запусков ещё нет</div>" :
        runs.map(renderRunCard).join("")}
    `;
    const runBtn = document.getElementById("btn-run-monitor-now");
    runBtn.onclick = () => triggerRun(monitorId);
    openModal("modal-monitor-detail");
  } catch (e) {
    showToast("Ошибка загрузки монитора");
  }
}

async function triggerRun(monitorId) {
  const btn = document.getElementById("btn-run-monitor-now");
  btn.disabled = true;
  btn.textContent = "⏳ Запускается…";
  showToast("⏳ Запуск монитора… Это займёт 5–10 минут");
  try {
    const result = await API.runMonitor(monitorId);
    closeModal();
    const statusLabel = labelStatus(result.status);
    showToast(`${statusIcon(result.status)} ${statusLabel}! Постов: ${result.total_posts}, Комментариев: ${result.total_comments}`, 5000);
    window.TG.haptic("success");
    loadRuns();
    loadDashboard();
  } catch (e) {
    showToast("Ошибка запуска: " + e.message, 5000);
    window.TG.haptic("error");
  } finally {
    btn.disabled = false;
    btn.textContent = "▶️ Запустить сейчас";
  }
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
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
  }
}

function renderRunCard(r) {
  const icon = statusIcon(r.status);
  const badgeClass = statusBadgeClass(r.status);
  const statusLabel = labelStatus(r.status);
  return `<div class="card" onclick="openRunDetail('${r.id}')">
    <div class="card-title">${icon} ${esc(r.monitor_id)}</div>
    <div class="card-meta">
      <span class="card-badge ${badgeClass}">${statusLabel}</span>
      <span>${r.total_posts}п / ${r.total_comments}к</span>
      <span>${(r.started_at || "").substring(0, 16).replace("T", " ")}</span>
    </div>
  </div>`;
}

async function openRunDetail(runId) {
  state.currentRunId = runId;
  try {
    const run = await API.getRun(runId);
    const icon = statusIcon(run.status);
    const statusLabel = labelStatus(run.status);

    let alertHtml = "";
    if (run.status === "failed" && run.error_message) {
      alertHtml = `<div class="alert-block alert-error"><b>❌ Ошибка:</b><br>${esc(run.error_message.substring(0, 400))}</div>`;
    } else if (run.status === "completed_with_warning" && run.warning_message) {
      alertHtml = `<div class="alert-block alert-warn"><b>⚠️ Предупреждение:</b><br>${esc(run.warning_message.substring(0, 300))}</div>`;
    }

    let downloadsHtml = "";
    if (run.exports && run.exports.length > 0) {
      const fmtInfo = {
        xlsx:         { label: "📊 Excel",        hint: "Для таблиц и ручного анализа" },
        json:         { label: "📄 JSON",          hint: "Для технической обработки" },
        handoff_json: { label: "🤖 Handoff JSON",  hint: "Для AI-агента" },
      };
      downloadsHtml = '<div class="downloads-header">Скачать:</div><div class="download-links">';
      for (const exp of run.exports) {
        if (exp.file_path || exp.drive_web_view_link) {
          const info = fmtInfo[exp.format] || { label: exp.format, hint: "" };
          const fmt = exp.format === "handoff_json" ? "handoff" : exp.format;
          const href = exp.drive_web_view_link || API.getDownloadUrl(run.id, fmt);
          downloadsHtml += `<a class="download-link" href="${href}" target="_blank" title="${info.hint}">${info.label}${exp.drive_web_view_link ? " ☁️" : ""}</a>`;
        }
      }
      downloadsHtml += "</div>";
      downloadsHtml += `<div class="hint-text" style="margin-top:8px">Excel/JSON-файлы не хранятся в базе данных — база хранит только метаданные и ссылки на файлы.</div>`;
    }

    document.getElementById("run-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${icon} ${statusLabel}</span></div>
      <div class="info-row"><span class="info-key">Монитор</span><span class="info-val">${esc(run.monitor_id)}</span></div>
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(run.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Постов</span><span class="info-val">${run.total_posts}</span></div>
      <div class="info-row"><span class="info-key">Комментариев</span><span class="info-val">${run.total_comments}</span></div>
      <div class="info-row"><span class="info-key">Запущен</span><span class="info-val">${(run.started_at || "—").substring(0, 16).replace("T", " ")}</span></div>
      ${alertHtml}
      ${downloadsHtml}
    `;
    openModal("modal-run-detail");
  } catch (e) {
    showToast("Ошибка загрузки запуска");
  }
}

// ── Status ─────────────────────────────────────────────────────────────────────
async function loadStatus() {
  const el = document.getElementById("status-info");
  try {
    const s = await API.getStatus();

    const storageLabel = {
      local: "Локально",
      google_drive: "Google Drive",
      s3: "Amazon S3",
      r2: "Cloudflare R2",
      railway_bucket: "Railway Storage",
    }[s.storage_provider] || s.storage_provider || "Локально";

    el.innerHTML = `
      <div class="status-section-title">Система</div>
      ${statusRow("Версия", s.app_version || "—", "")}
      ${statusRow("База данных", s.database, s.database === "connected" ? "status-ok" : "status-err")}
      ${statusRow("Reddit", s.reddit_access_mode || "—", "")}
      ${statusRow("Telegram bot", s.telegram_bot_configured ? "✅ настроен" : "⚠️ не задан", s.telegram_bot_configured ? "status-ok" : "status-warn")}
      ${statusRow("Google Drive", s.drive_configured ? "✅ настроен" : "⚠️ не настроен", s.drive_configured ? "status-ok" : "status-warn")}

      <div class="status-section-title" style="margin-top:16px">Хранение отчётов</div>
      ${statusRow("Провайдер", storageLabel, "")}
      ${statusRow("Хранить файлы", s.export_retention_days + " дней", "")}
      ${statusRow("Авто-очистка", s.cleanup_local_files ? "включена" : "выключена", "")}
      <div class="hint-text">PostgreSQL хранит только метаданные запусков (статус, счётчики, ссылки). Полные данные находятся в Excel/JSON-файлах.</div>

      <div class="status-section-title" style="margin-top:16px">Поддержка</div>
      <div class="status-row">
        <span class="status-key">🌐 Сайт</span>
        <a href="https://up-level.pro" target="_blank" class="status-link">up-level.pro</a>
      </div>
      <div class="status-row">
        <span class="status-key">💬 Telegram</span>
        <a href="https://t.me/kdm_app" target="_blank" class="status-link">@kdm_app</a>
      </div>
    `;
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки статуса</div></div>';
  }
}

function statusRow(key, val, cls) {
  return `<div class="status-row">
    <span class="status-key">${esc(key)}</span>
    <span class="status-val ${cls}">${esc(String(val))}</span>
  </div>`;
}

// ── Modals ─────────────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById(id).classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function showToast(msg, duration) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add("hidden"), duration || 3000);
}
