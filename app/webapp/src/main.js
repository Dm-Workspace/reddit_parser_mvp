/**
 * Trend Intelligence Hub — Mini App main logic.
 */

// ── State ──────────────────────────────────────────────────────────────────────
let state = {
  projects: [],
  monitors: [],
  runs: [],
  srPresets: [],
  kwPresets: [],
  currentProjectId: null,
  currentMonitorId: null,
  currentRunId: null,
};

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  window.TG.init();
  document.body.classList.add(window.TG.themeClass());

  // Tab navigation
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  // Project create button
  document.getElementById("btn-create-project").addEventListener("click", openCreateProject);
  document.getElementById("btn-save-project").addEventListener("click", saveProject);
  document.getElementById("btn-save-monitor").addEventListener("click", saveMonitor);

  loadDashboard();
  loadProjects();
  loadRuns();
  loadStatus();
  loadPresets();
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
    if (runs.length === 0) {
      recentEl.innerHTML = '<div class="empty-state"><div class="empty-icon">🕐</div><div class="empty-text">Запусков ещё нет</div></div>';
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
    if (projects.length === 0) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-icon">📁</div>
        <div class="empty-text">Нет проектов</div>
        <div class="empty-sub">Создайте первый проект</div>
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
    // also update runs filter
    const sel = document.getElementById("runs-filter-project");
    sel.innerHTML = '<option value="">Все проекты</option>' +
      projects.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
    sel.onchange = () => loadRuns(sel.value);
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
  if (!name) { showToast("Введите название"); return; }
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
      <div class="info-row"><span class="info-key">ID</span><span class="info-val"><code>${esc(project.id)}</code></span></div>
      <div class="info-row"><span class="info-key">Ниша</span><span class="info-val">${esc(project.niche || "—")}</span></div>
      <div class="info-row"><span class="info-key">Язык</span><span class="info-val">${project.output_language.toUpperCase()}</span></div>
      <div class="info-row"><span class="info-key">Мониторов</span><span class="info-val">${monitors.length}</span></div>
      <div class="monitor-list-in-proj">
        <b>Мониторы:</b>
        ${monitors.length === 0 ? "<div class='empty-sub' style='margin-top:8px'>Нет мониторов</div>" :
          monitors.map((m) => `
            <div class="monitor-item" onclick="openMonitorDetail('${m.id}')">
              <span>${m.enabled && !m.archived ? "🟢" : "🔴"} ${esc(m.name)}</span>
              <span style="font-size:11px;color:var(--tg-theme-hint-color,#888)">${m.run_mode}</span>
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

  const srSel = document.getElementById("mon-sr-preset");
  srSel.innerHTML = '<option value="">Выберите пресет</option>' +
    state.srPresets.map((p) => `<option value="${p.id}">${esc(p.name)} (${p.subreddits.length} sub)</option>`).join("");

  const kwSel = document.getElementById("mon-kw-preset");
  kwSel.innerHTML = '<option value="">Выберите пресет</option>' +
    state.kwPresets.map((p) => `<option value="${p.id}">${esc(p.name)} (${p.keywords.length} kw)</option>`).join("");

  openModal("modal-monitor-create");
}

async function saveMonitor() {
  const name = document.getElementById("mon-name").value.trim();
  const projectId = document.getElementById("mon-project-id").value;
  if (!name) { showToast("Введите название монитора"); return; }

  const btn = document.getElementById("btn-save-monitor");
  btn.disabled = true;
  try {
    const monitor = await API.createMonitor({
      project_id: projectId,
      name,
      description: document.getElementById("mon-desc").value.trim(),
      source: "reddit",
      subreddit_preset_id: document.getElementById("mon-sr-preset").value || null,
      keyword_preset_id: document.getElementById("mon-kw-preset").value || null,
      custom_subreddits: [],
      custom_keywords: [],
      run_mode: document.getElementById("mon-run-mode").value,
      schedule_mode: document.getElementById("mon-schedule-mode").value,
    });
    closeModal();
    showToast("✅ Монитор создан");
    window.TG.haptic("success");
    loadDashboard();
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
      <div class="info-row"><span class="info-key">ID</span><span class="info-val"><code>${esc(monitor.id)}</code></span></div>
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(monitor.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Режим</span><span class="info-val">${esc(monitor.run_mode)}</span></div>
      <div class="info-row"><span class="info-key">Расписание</span><span class="info-val">${esc(monitor.schedule_mode)}</span></div>
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${monitor.enabled && !monitor.archived ? "🟢 Активен" : "🔴 Неактивен"}</span></div>
      <div style="margin-top:12px"><b>Последние запуски:</b></div>
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
    showToast(`✅ Готово! Постов: ${result.total_posts}, Комментариев: ${result.total_comments}`);
    window.TG.haptic("success");
    loadRuns();
    loadDashboard();
  } catch (e) {
    showToast("Ошибка запуска: " + e.message);
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
    state.runs = runs;
    if (runs.length === 0) {
      el.innerHTML = '<div class="empty-state"><div class="empty-icon">🕐</div><div class="empty-text">Нет запусков</div></div>';
      return;
    }
    el.innerHTML = runs.map(renderRunCard).join("");
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
  }
}

function renderRunCard(r) {
  const icons = { completed: "✅", completed_with_warning: "⚠️", failed: "❌", running: "⚙️", queued: "📋" };
  const icon = icons[r.status] || "❓";
  const badgeClass = r.status === "completed" ? "badge-ok" :
    r.status === "failed" ? "badge-err" :
    r.status === "completed_with_warning" ? "badge-warn" : "badge-run";
  return `<div class="card" onclick="openRunDetail('${r.id}')">
    <div class="card-title">${icon} ${esc(r.monitor_id)}</div>
    <div class="card-meta">
      <span class="card-badge ${badgeClass}">${r.status}</span>
      <span>${r.total_posts}п / ${r.total_comments}к</span>
      <span>${(r.started_at || "").substring(0, 16)}</span>
    </div>
  </div>`;
}

async function openRunDetail(runId) {
  state.currentRunId = runId;
  try {
    const run = await API.getRun(runId);
    const icons = { completed: "✅", completed_with_warning: "⚠️", failed: "❌", running: "⚙️", queued: "📋" };
    const icon = icons[run.status] || "❓";

    let downloadsHtml = "";
    if (run.exports && run.exports.length > 0) {
      const fmtLabels = { xlsx: "📊 Excel", json: "📄 JSON", handoff_json: "🤖 Handoff JSON" };
      downloadsHtml = '<div style="margin-top:12px"><b>Скачать:</b></div><div class="download-links">';
      for (const exp of run.exports) {
        if (exp.file_path || exp.drive_web_view_link) {
          const label = fmtLabels[exp.format] || exp.format;
          const fmt = exp.format === "handoff_json" ? "handoff" : exp.format;
          if (exp.drive_web_view_link) {
            downloadsHtml += `<a class="download-link" href="${exp.drive_web_view_link}" target="_blank">${label} ☁️</a>`;
          } else {
            downloadsHtml += `<a class="download-link" href="${API.getDownloadUrl(run.id, fmt)}" target="_blank">${label}</a>`;
          }
        }
      }
      downloadsHtml += "</div>";
    }

    document.getElementById("run-detail-body").innerHTML = `
      <div class="info-row"><span class="info-key">Статус</span><span class="info-val">${icon} ${esc(run.status)}</span></div>
      <div class="info-row"><span class="info-key">Монитор</span><span class="info-val">${esc(run.monitor_id)}</span></div>
      <div class="info-row"><span class="info-key">Проект</span><span class="info-val">${esc(run.project_id)}</span></div>
      <div class="info-row"><span class="info-key">Постов</span><span class="info-val">${run.total_posts}</span></div>
      <div class="info-row"><span class="info-key">Комментариев</span><span class="info-val">${run.total_comments}</span></div>
      <div class="info-row"><span class="info-key">Запущен</span><span class="info-val">${(run.started_at || "—").substring(0, 16)}</span></div>
      ${run.warning_message ? `<div class="info-row"><span class="info-key">⚠️</span><span class="info-val">${esc(run.warning_message)}</span></div>` : ""}
      ${run.error_message ? `<div class="info-row"><span class="info-key">❌</span><span class="info-val">${esc(run.error_message.substring(0, 100))}</span></div>` : ""}
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
    document.getElementById("stat-db").querySelector(".stat-num").textContent =
      s.database === "connected" ? "✅" : "❌";

    const rows = [
      ["Версия", s.app_version || "—", ""],
      ["База данных", s.database, s.database === "connected" ? "status-ok" : "status-err"],
      ["Reddit mode", s.reddit_access_mode, ""],
      ["Telegram bot", s.telegram_bot_configured ? "✅ настроен" : "⚠️ не задан", s.telegram_bot_configured ? "status-ok" : "status-warn"],
      ["Google Drive", s.drive_configured ? "✅ настроен" : "⚠️ не настроен", s.drive_configured ? "status-ok" : "status-warn"],
      ["Dev mode", s.miniapp_dev_mode ? "🔧 включён" : "выключен", ""],
    ];
    el.innerHTML = rows.map(([k, v, cls]) => `
      <div class="status-row">
        <span class="status-key">${esc(k)}</span>
        <span class="status-val ${cls}">${esc(String(v))}</span>
      </div>`
    ).join("");
  } catch (e) {
    el.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки статуса</div></div>';
  }
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
