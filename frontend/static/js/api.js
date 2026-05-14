/* API client — all fetch calls go through here */
const API_BASE = '';

async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + '/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const API = {
  overview: () => apiFetch('/overview'),
  jobs: (params = {}) => apiFetch('/jobs?' + new URLSearchParams(params)),
  job: (id) => apiFetch(`/jobs/${id}`),
  jobApplicants: (id) => apiFetch(`/jobs/${id}/applicants-history`),
  jobChanges: (id) => apiFetch(`/jobs/${id}/changes`),
  archive: (params = {}) => apiFetch('/archive?' + new URLSearchParams(params)),
  runs: (limit = 50) => apiFetch(`/scrape/runs?limit=${limit}`),
  run: (id) => apiFetch(`/scrape/runs/${id}`),
  runLogs: (id) => apiFetch(`/scrape/runs/${id}/logs`),
  scrapeStatus: () => apiFetch('/scrape/status'),
  triggerScrape: (sourceNames = null) => apiFetch('/scrape/run', {
    method: 'POST',
    body: JSON.stringify({ source_names: sourceNames }),
  }),
  chartsEvOverTime: (days = 90) => apiFetch(`/charts/ev-jobs-over-time?days=${days}`),
  chartsArchivedOverTime: (days = 90) => apiFetch(`/charts/archived-over-time?days=${days}`),
  chartsTopGrowth: () => apiFetch('/charts/top-applicant-growth'),
  chartsScoreDistribution: () => apiFetch('/charts/ev-score-distribution'),
  exportEVJobs: () => window.open('/api/export/ev-jobs.csv', '_blank'),
};
