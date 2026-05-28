/* Command Palette — ⌘K / Ctrl+K global search & navigation */

let _cmdOpen = false;
let _cmdSelected = 0;
let _cmdResults = [];
let _cmdSearchTimeout = null;

const CMD_ACTIONS = [
  { type: 'nav',    label: 'Go to Overview',    sub: 'Dashboard & charts',   icon: '⊞', action: () => { window.location.hash = '#/';        cmdClose(); } },
  { type: 'nav',    label: 'Go to EV Jobs',      sub: 'Active & monitored',   icon: '≡', action: () => { window.location.hash = '#/jobs';     cmdClose(); } },
  { type: 'nav',    label: 'Go to Archive',      sub: 'Archived jobs',        icon: '◫', action: () => { window.location.hash = '#/archive';  cmdClose(); } },
  { type: 'nav',    label: 'Go to Scrape Runs',  sub: 'History & logs',       icon: '○', action: () => { window.location.hash = '#/runs';     cmdClose(); } },
  { type: 'nav',    label: 'Go to Settings',     sub: 'Config & sources',     icon: '⊙', action: () => { window.location.hash = '#/settings'; cmdClose(); } },
  { type: 'action', label: 'Run Scrape',          sub: 'Trigger immediately',  icon: '↻', action: () => { cmdClose(); triggerScrape(); } },
  { type: 'action', label: 'Export EV Jobs CSV',  sub: 'Download spreadsheet', icon: '↓', action: () => { cmdClose(); API.exportEVJobs(); } },
  { type: 'action', label: 'Toggle Theme',        sub: 'Dark / light mode',    icon: '◐', action: () => {
    const cur = document.documentElement.dataset.theme;
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('theme', next);
    cmdClose();
  }},
];

function cmdOpen() {
  if (_cmdOpen) return;
  _cmdOpen = true;
  const overlay = document.getElementById('cmdOverlay');
  const input   = document.getElementById('cmdInput');
  overlay.classList.add('open');
  input.value = '';
  _cmdSelected = 0;
  _cmdSearchTimeout = null;
  _renderCmdResults('', []);
  requestAnimationFrame(() => input.focus());
}

function cmdClose() {
  if (!_cmdOpen) return;
  _cmdOpen = false;
  document.getElementById('cmdOverlay').classList.remove('open');
  clearTimeout(_cmdSearchTimeout);
}

// ── Input handler ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('cmdInput');
  if (!input) return;

  input.addEventListener('input', (e) => {
    clearTimeout(_cmdSearchTimeout);
    const q = e.target.value.trim();
    if (!q) {
      _renderCmdResults('', []);
      return;
    }
    _cmdSearchTimeout = setTimeout(() => _cmdSearch(q), 200);
  });

  input.addEventListener('keydown', (e) => {
    const items = document.querySelectorAll('#cmdResults .cmd-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _cmdSelected = Math.min(_cmdSelected + 1, items.length - 1);
      _highlightCmd(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _cmdSelected = Math.max(_cmdSelected - 1, 0);
      _highlightCmd(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      items[_cmdSelected]?.click();
    } else if (e.key === 'Escape') {
      cmdClose();
    }
  });
});

function _highlightCmd(items) {
  items.forEach((el, i) => el.classList.toggle('selected', i === _cmdSelected));
  items[_cmdSelected]?.scrollIntoView({ block: 'nearest' });
}

async function _cmdSearch(query) {
  const q = query.toLowerCase();

  // Filter static actions
  const matchedActions = CMD_ACTIONS.filter(a =>
    a.label.toLowerCase().includes(q) || a.sub.toLowerCase().includes(q)
  );

  // Search jobs via API
  let jobResults = [];
  try {
    const data = await API.jobs({ search: query, ev_only: 'true', page: 1, page_size: 8, status: 'active' });
    jobResults = data.items || [];
  } catch { /* ignore */ }

  _renderCmdResults(query, matchedActions, jobResults);
}

function _renderCmdResults(query, actions = [], jobs = []) {
  const container = document.getElementById('cmdResults');
  _cmdSelected = 0;

  if (!query) {
    // Default: show all actions
    container.innerHTML = `
      <div class="cmd-group-label">Actions</div>
      ${CMD_ACTIONS.map((a, i) => cmdItem(a.icon, a.label, a.sub, `_cmdExec(${i})`, i === 0)).join('')}
    `;
    _cmdResults = CMD_ACTIONS.map((_, i) => ({ type: 'action', idx: i }));
  } else {
    let html = '';

    if (jobs.length > 0) {
      html += `<div class="cmd-group-label">Jobs</div>`;
      html += jobs.map((j, i) => {
        const score = j.ev_score ?? 0;
        const dept = j.department ? escHtml(j.department) : '';
        const loc  = j.location   ? escHtml(j.location)   : '';
        const meta = [dept, loc].filter(Boolean).join(' · ');
        return cmdItem(
          `<span class="cmd-score ${score >= 60 ? 'high' : 'mid'}">${score}</span>`,
          escHtml(j.title || '–'),
          meta,
          `_cmdOpenJob(${j.id})`,
          i === 0 && actions.length === 0
        );
      }).join('');
    }

    if (actions.length > 0) {
      html += `<div class="cmd-group-label">Actions</div>`;
      html += actions.map((a, i) => {
        const globalIdx = CMD_ACTIONS.indexOf(a);
        return cmdItem(a.icon, a.label, a.sub, `_cmdExec(${globalIdx})`, i === 0 && jobs.length === 0);
      }).join('');
    }

    if (!html) {
      html = `<div class="cmd-empty">No results for "${escHtml(query)}"</div>`;
    }

    container.innerHTML = html;
    _cmdResults = [
      ...jobs.map(j => ({ type: 'job', id: j.id })),
      ...actions.map(a => ({ type: 'action', idx: CMD_ACTIONS.indexOf(a) })),
    ];
  }

  // Highlight first
  const items = container.querySelectorAll('.cmd-item');
  items.forEach((el, i) => el.classList.toggle('selected', i === 0));
}

function cmdItem(icon, label, sub, onclick, selected = false) {
  return `
    <div class="cmd-item${selected ? ' selected' : ''}" onclick="${onclick}">
      <span class="cmd-item-icon">${icon}</span>
      <span class="cmd-item-body">
        <span class="cmd-item-label">${label}</span>
        ${sub ? `<span class="cmd-item-sub">${sub}</span>` : ''}
      </span>
    </div>
  `;
}

function _cmdExec(i) {
  CMD_ACTIONS[i]?.action();
}

function _cmdOpenJob(id) {
  cmdClose();
  openJobModal(id);
}

// ── Global keyboard shortcut ───────────────────────────────────────────────────

document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    _cmdOpen ? cmdClose() : cmdOpen();
  }
  if (e.key === 'Escape' && _cmdOpen) cmdClose();
});

// Close on overlay click
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('cmdOverlay')?.addEventListener('click', (e) => {
    if (e.target === document.getElementById('cmdOverlay')) cmdClose();
  });
});
