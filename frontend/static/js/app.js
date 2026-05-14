/* Main app — router, navigation, shared utilities */

const ROUTES = {
  '': renderOverview,
  '/': renderOverview,
  '/jobs': renderJobs,
  '/archive': renderArchive,
  '/runs': renderRuns,
  '/settings': renderSettings,
};

// ── Router ────────────────────────────────────────────────────────────────────

function router() {
  const hash = window.location.hash.replace('#', '') || '/';
  // Job detail via hash param like #/jobs?detail=123
  const [path] = hash.split('?');
  const renderer = ROUTES[path] || renderOverview;

  // Update active nav item
  document.querySelectorAll('.nav-item').forEach(el => {
    const route = el.dataset.route;
    const isActive = (path === '/' || path === '') && route === 'overview'
      || path === `/jobs` && route === 'jobs'
      || path === `/archive` && route === 'archive'
      || path === `/runs` && route === 'runs'
      || path === `/settings` && route === 'settings';
    el.classList.toggle('active', isActive);
  });

  renderer();
}

window.addEventListener('hashchange', router);
window.addEventListener('load', () => {
  initTheme();
  router();
  pollScrapeStatus();
});

// ── Theme ─────────────────────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.dataset.theme = saved;
}

document.getElementById('themeToggle')?.addEventListener('click', () => {
  const current = document.documentElement.dataset.theme;
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('theme', next);
});

// ── Sidebar toggle ─────────────────────────────────────────────────────────────

document.getElementById('sidebarToggle')?.addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('collapsed');
});

// ── Scrape trigger ─────────────────────────────────────────────────────────────

async function triggerScrape() {
  const btn = document.getElementById('scrapeBtn');
  btn.disabled = true;
  btn.querySelector('span').textContent = 'Starting…';

  try {
    const res = await API.triggerScrape();
    showToast(`Scrape started (run #${res.run_id})`, 'success');
    pollScrapeStatus();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.querySelector('span').textContent = 'Run Scrape';
  }
}

// ── Scrape status polling ──────────────────────────────────────────────────────

let _statusInterval = null;

async function pollScrapeStatus() {
  const dot = document.getElementById('scrapeStatusDot');
  try {
    const s = await API.scrapeStatus();
    if (s.is_running) {
      dot.className = 'scrape-status-dot running';
      dot.title = `Scrape running (run #${s.active_run_id})`;
      if (!_statusInterval) {
        _statusInterval = setInterval(pollScrapeStatus, 5000);
      }
    } else {
      dot.className = 'scrape-status-dot';
      dot.title = 'Idle';
      if (_statusInterval) {
        clearInterval(_statusInterval);
        _statusInterval = null;
      }
    }
  } catch {
    dot.className = 'scrape-status-dot error';
    dot.title = 'API unreachable';
  }
}

// ── Shared utilities ──────────────────────────────────────────────────────────

function setPageTitle(title, subtitle = '') {
  document.getElementById('pageTitle').textContent = title;
  document.getElementById('pageSubtitle').textContent = subtitle;
  document.title = `${title} · Xiaomi EV Jobs`;
}

function loadingHtml() {
  return `<div class="loading-screen"><div class="spinner"></div><p>Loading…</p></div>`;
}

function errorHtml(msg) {
  return `
    <div class="empty-state">
      <div class="empty-state-icon">⚠️</div>
      <div class="empty-state-title">Something went wrong</div>
      <div class="empty-state-sub">${escHtml(msg)}</div>
    </div>
  `;
}

function escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatDateTime(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatRelTime(iso) {
  if (!iso) return '–';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function paginationHtml(total, page, pageSize, changeFn = 'jobsChangePage') {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return '';
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  const pages = [];
  const maxVisible = 5;
  const startPage = Math.max(1, Math.min(page - 2, totalPages - maxVisible + 1));
  for (let i = startPage; i < startPage + maxVisible && i <= totalPages; i++) {
    pages.push(i);
  }

  return `
    <div class="pagination">
      <span>${start}–${end} of ${total}</span>
      <div class="pagination-controls">
        <button class="page-btn" onclick="${changeFn}(${page - 1})" ${page <= 1 ? 'disabled' : ''}>‹</button>
        ${pages.map(p => `<button class="page-btn ${p === page ? 'active' : ''}" onclick="${changeFn}(${p})">${p}</button>`).join('')}
        <button class="page-btn" onclick="${changeFn}(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>›</button>
      </div>
    </div>
  `;
}

function formatEVLabel(label) {
  return { core_ev: 'Core EV', likely_ev: 'Likely EV', maybe_ev: 'Maybe EV', non_ev: 'Non-EV' }[label] || label;
}
