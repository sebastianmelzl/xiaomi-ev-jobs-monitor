/* API client — all fetch calls go through here */
const API_BASE = '';

async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + '/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    const msg = Array.isArray(detail)
      ? detail.map(e => e.msg || JSON.stringify(e)).join('; ')
      : (typeof detail === 'string' ? detail : `HTTP ${res.status}`);
    throw new Error(msg);
  }
  return res.json();
}

const API = {
  overview: () => apiFetch('/overview'),
  jobs: (params = {}) => apiFetch('/jobs?' + new URLSearchParams(params)),
  jobDepartments: () => apiFetch('/jobs/departments'),
  job: (id) => apiFetch(`/jobs/${id}`),
  jobApplicants: (id) => apiFetch(`/jobs/${id}/applicants-history`),
  jobChanges: (id) => apiFetch(`/jobs/${id}/changes`),
  archive: (params = {}) => apiFetch('/archive?' + new URLSearchParams(params)),
  runs: (limit = 50) => apiFetch(`/scrape/runs?limit=${limit}`),
  run: (id) => apiFetch(`/scrape/runs/${id}`),
  runLogs: (id) => apiFetch(`/scrape/runs/${id}/logs`),
  hideJob: (id) => apiFetch(`/jobs/${id}/hide`, { method: 'POST' }),
  unhideJob: (id) => apiFetch(`/jobs/${id}/hide`, { method: 'DELETE' }),
  toggleReposted: (id) => apiFetch(`/jobs/${id}/reposted`, { method: 'PATCH' }),
  hiddenJobs: () => apiFetch('/jobs/hidden'),
  scrapeStatus: () => apiFetch('/scrape/status'),
  triggerScrape: (sourceNames = null) => apiFetch('/scrape/run', {
    method: 'POST',
    body: JSON.stringify({ source_names: sourceNames }),
  }),
  chartsEvOverTime: (days = 90) => apiFetch(`/charts/ev-jobs-over-time?days=${days}`),
  chartsArchivedOverTime: (days = 90) => apiFetch(`/charts/archived-over-time?days=${days}`),
  chartsTopGrowth: () => apiFetch('/charts/top-applicant-growth'),
  chartsScoreDistribution: () => apiFetch('/charts/ev-score-distribution'),
  chartsJobsByDepartment: () => apiFetch('/charts/jobs-by-department'),
  exportEVJobs: () => window.open('/api/export/ev-jobs.csv', '_blank'),
  resetAllData: () => apiFetch('/admin/reset', { method: 'POST' }),
  enrichMissing: () => apiFetch('/admin/enrich-missing', { method: 'POST' }),
};
