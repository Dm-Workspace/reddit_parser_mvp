/**
 * API client for Trend Intelligence Hub backend.
 */

const API_BASE = window.location.origin + "/api";

window.API = (function () {
  async function request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const initData = window.TG ? window.TG.getInitData() : "";
    if (initData) {
      headers["X-Telegram-Init-Data"] = initData;
    }
    const opts = { method, headers };
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(API_BASE + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try { const j = await res.json(); detail = j.detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  }

  return {
    // Status
    getStatus: () => request("GET", "/status"),

    // Labels
    getLabels: () => request("GET", "/labels"),

    // Me
    getMe: () => request("GET", "/me"),

    // Projects
    listProjects: () => request("GET", "/projects"),
    getProject: (id) => request("GET", `/projects/${id}`),
    createProject: (data) => request("POST", "/projects", data),
    updateProject: (id, data) => request("PATCH", `/projects/${id}`, data),
    archiveProject: (id) => request("POST", `/projects/${id}/archive`),

    // Monitors
    listMonitors: (projectId) => request("GET", `/monitors${projectId ? "?project_id=" + projectId : ""}`),
    getMonitor: (id) => request("GET", `/monitors/${id}`),
    createMonitor: (data) => request("POST", "/monitors", data),
    archiveMonitor: (id) => request("POST", `/monitors/${id}/archive`),
    runMonitor: (id) => request("POST", `/monitors/${id}/run`),

    // Runs
    listRuns: (params) => {
      const qs = new URLSearchParams(params || {}).toString();
      return request("GET", `/runs${qs ? "?" + qs : ""}`);
    },
    getRun: (id) => request("GET", `/runs/${id}`),
    getDownloadUrl: (runId, fmt) => `${API_BASE}/runs/${runId}/download/${fmt}`,

    // Presets
    listSubredditPresets: () => request("GET", "/presets/subreddits"),
    listKeywordPresets: () => request("GET", "/presets/keywords"),

    // Sources
    listSources: () => request("GET", "/sources"),
  };
})();
