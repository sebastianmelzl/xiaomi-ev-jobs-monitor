/* EV Jobs page — sectioned by department group */

const DEPT_ORDER = ['Engineering & R&D', 'Product & Design', 'Business & Operations'];
const DEPT_ICONS = {
  'Engineering & R&D':     '⚙️',
  'Product & Design':      '🎯',
  'Business & Operations': '📊',
};

const NEW_POST_DAYS = 14;

let jobsState = {
  search: '', status: 'active',
  newOnly: false,
  collapsed: {},
  viewMode: localStorage.getItem('jobsViewMode') || 'list',
};

// Live-update poller
let _jobsPoller = null;
let _pollScrapeWasRunning = false;

function _startPoller() {
  _stopPoller();
  _jobsPoller = setInterval(async () => {
    if (!document.getElementById('jobsSections')) { _stopPoller(); return; }
    try {
      const status = await API.scrapeStatus();
      const running = status.is_running;
      if (running) {
        _pollScrapeWasRunning = true;
        await _silentRefresh();
      } else if (_pollScrapeWasRunning) {
        // Scrape just finished — do one final refresh
        _pollScrapeWasRunning = false;
        await _silentRefresh();
        showToast('Scrape finished — job list updated', 'success');
      }
    } catch { /* ignore poll errors */ }
  }, 8000);
}

function _stopPoller() {
  if (_jobsPoller) { clearInterval(_jobsPoller); _jobsPoller = null; }
}

// Refresh without showing a loading spinner (keeps current content visible)
async function _silentRefresh() {
  const wrap = document.getElementById('jobsSections');
  if (!wrap) return;
  try {
    const params = {
      page: 1, page_size: 500,
      sort_by: 'posted_date_normalized', sort_dir: 'desc',
      ev_only: 'true',
    };
    if (jobsState.search) params.search = jobsState.search;
    if (jobsState.status) params.status = jobsState.status;
    const data = await API.jobs(params);
    _renderJobsInto(wrap, data.items);
  } catch { /* keep old content on error */ }
}

function jobNewness(job) {
  if (job.is_reposted) return 'reposted';
  const posted = job.posted_date_normalized ? new Date(job.posted_date_normalized).getTime() : null;
  if (posted !== null && (Date.now() - posted) / 86_400_000 <= NEW_POST_DAYS) return 'new';
  return null;
}

async function renderJobs() {
  setPageTitle('EV Jobs', 'Active & monitored roles');
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="section">
      <div class="filters-bar">
        <input type="text" class="search-input" id="jobSearch" placeholder="Search title, location…" value="${jobsState.search}" />
        <select class="filter-select" id="jobStatus">
          <option value="active"  ${jobsState.status === 'active'  ? 'selected' : ''}>Active</option>
          <option value="missing" ${jobsState.status === 'missing' ? 'selected' : ''}>Missing</option>
          <option value=""        ${jobsState.status === ''        ? 'selected' : ''}>All statuses</option>
        </select>
        <button class="btn btn-sm ${jobsState.newOnly ? 'btn-primary' : 'btn-secondary'}" id="btnNewOnly" onclick="toggleNewOnly()">
          New Posts
        </button>
        <div class="filters-spacer"></div>
        <div class="view-toggle" id="viewToggle">
          <button class="view-toggle-btn ${jobsState.viewMode === 'list' ? 'active' : ''}" onclick="setJobsView('list')" title="List view">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 3h12M1 7h12M1 11h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
          </button>
          <button class="view-toggle-btn ${jobsState.viewMode === 'cards' ? 'active' : ''}" onclick="setJobsView('cards')" title="Card view">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/></svg>
          </button>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="API.exportEVJobs()">↓ Export CSV</button>
      </div>
      <div id="jobsSections">${loadingHtml()}</div>
    </div>
  `;

  let searchTimeout;
  document.getElementById('jobSearch').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => { jobsState.search = e.target.value; loadJobsSections(); }, 300);
  });
  document.getElementById('jobStatus').addEventListener('change', (e) => {
    jobsState.status = e.target.value; loadJobsSections();
  });

  loadJobsSections();
  _startPoller();
}

function toggleNewOnly() {
  jobsState.newOnly = !jobsState.newOnly;
  const btn = document.getElementById('btnNewOnly');
  if (btn) btn.className = `btn btn-sm ${jobsState.newOnly ? 'btn-primary' : 'btn-secondary'}`;
  loadJobsSections();
}

function setJobsView(mode) {
  jobsState.viewMode = mode;
  localStorage.setItem('jobsViewMode', mode);
  document.querySelectorAll('#viewToggle .view-toggle-btn').forEach((btn, i) => {
    btn.classList.toggle('active', (i === 0 && mode === 'list') || (i === 1 && mode === 'cards'));
  });
  const wrap = document.getElementById('jobsSections');
  if (wrap && wrap.querySelector('.dept-section,.job-cards-grid')) {
    // Re-render with new view mode without full reload
    const existingCount = wrap.querySelector('.dept-section,  .job-cards-grid');
    if (existingCount) loadJobsSections();
  }
}

async function loadJobsSections() {
  const wrap = document.getElementById('jobsSections');
  if (!wrap) return;
  wrap.innerHTML = loadingHtml();
  try {
    const params = {
      page: 1, page_size: 500,
      sort_by: 'posted_date_normalized', sort_dir: 'desc',
      ev_only: 'true',
    };
    if (jobsState.search) params.search = jobsState.search;
    if (jobsState.status) params.status = jobsState.status;
    const data = await API.jobs(params);
    _renderJobsInto(wrap, data.items);
  } catch (err) {
    wrap.innerHTML = errorHtml(err.message);
  }
}

function _renderJobsInto(wrap, allItems) {
  const items = jobsState.newOnly
    ? allItems.filter(j => jobNewness(j) === 'new')
    : allItems;

  if (items.length === 0) {
    wrap.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <div class="empty-state-title">${jobsState.newOnly ? 'No new posts in the last 14 days' : 'No jobs found'}</div>
        <div class="empty-state-sub">${jobsState.newOnly ? 'Try turning off the New Posts filter' : 'Try adjusting filters or run a scrape'}</div>
      </div>`;
    return;
  }

  const groups = {};
  for (const job of items) {
    const dept = DEPT_ORDER.includes(job.department) ? job.department : 'Other';
    if (!groups[dept]) groups[dept] = [];
    groups[dept].push(job);
  }
  const order = [...DEPT_ORDER.filter(d => groups[d]), ...(groups['Other'] ? ['Other'] : [])];

  const countLine = `<div class="jobs-count-line">${items.length} job${items.length !== 1 ? 's' : ''}${jobsState.newOnly ? ' · New Posts filter active' : ''}</div>`;

  if (jobsState.viewMode === 'cards') {
    wrap.innerHTML = countLine + order.map(dept => renderDeptSectionCards(dept, groups[dept])).join('');
    wrap.querySelectorAll('.job-card').forEach(card => {
      card.addEventListener('click', () => openJobModal(parseInt(card.dataset.id)));
    });
  } else {
    wrap.innerHTML = countLine + order.map(dept => renderDeptSection(dept, groups[dept])).join('');
    wrap.querySelectorAll('.job-item').forEach(item => {
      item.addEventListener('click', () => openJobModal(parseInt(item.dataset.id)));
    });
  }
}

function renderDeptSection(dept, jobs) {
  const icon = DEPT_ICONS[dept] || '📁';
  const isCollapsed = jobsState.collapsed[dept] || false;
  const sectionId = `sect-${dept.replace(/[^a-z]/gi, '-')}`;

  const fresh    = jobs.filter(j => !j.is_reposted);
  const reposted = jobs.filter(j =>  j.is_reposted);

  const repostedBlock = reposted.length === 0 ? '' : `
    <div class="job-list-divider">↩ Reposted <span>${reposted.length}</span></div>
    ${reposted.map(job => jobItem(job, true)).join('')}
  `;

  return `
    <div class="dept-section" id="${sectionId}">
      <div class="dept-header" onclick="toggleDeptSection('${dept}', '${sectionId}')">
        <span class="dept-icon">${icon}</span>
        <span class="dept-name">${escHtml(dept)}</span>
        <span class="dept-count">${jobs.length}</span>
        <span class="dept-chevron ${isCollapsed ? 'collapsed' : ''}">▾</span>
      </div>
      <div class="dept-body ${isCollapsed ? 'collapsed' : ''}">
        <div class="job-list">
          ${fresh.map(job => jobItem(job)).join('')}
          ${repostedBlock}
        </div>
      </div>
    </div>
  `;
}

function toggleDeptSection(dept, sectionId) {
  jobsState.collapsed[dept] = !jobsState.collapsed[dept];
  const section = document.getElementById(sectionId);
  if (!section) return;
  section.querySelector('.dept-body').classList.toggle('collapsed', jobsState.collapsed[dept]);
  section.querySelector('.dept-chevron').classList.toggle('collapsed', jobsState.collapsed[dept]);
}

function newnessHtml(job) {
  const n = jobNewness(job);
  if (n === 'reposted') return '<span class="newness-badge newness-reposted">Reposted</span>';
  if (n === 'new')      return '<span class="newness-badge newness-new">New</span>';
  return '';
}

function jobItem(job, dimmed = false) {
  const score      = job.ev_score ?? 0;
  const scoreClass = score >= 60 ? 'high' : score >= 35 ? 'mid' : 'low';

  const n      = job.is_reposted ? null : jobNewness(job);
  const nBadge = n === 'new' ? '<span class="newness-badge newness-new">New</span>' : '';

  const applicants = job.applicant_count_current;
  const appStr = applicants != null
    ? `${applicants}${job.applicant_count_quality === 'lower_bound' ? '+' : ''}`
    : null;

  const delta24h  = job.applicant_delta_24h;
  const deltaHtml = delta24h != null
    ? `<span class="delta ${delta24h > 0 ? 'positive' : delta24h < 0 ? 'negative' : 'neutral'}" style="font-size:11px">${delta24h > 0 ? '+' : ''}${delta24h}</span>`
    : '';

  const postedStr = job.posted_date_normalized
    ? formatDate(job.posted_date_normalized)
    : escHtml(job.posted_text_raw || '–');

  const meta = [job.department, job.location].filter(Boolean).map(escHtml).join(' · ');

  return `
    <div class="job-item${dimmed ? ' job-item-dimmed' : ''}" data-id="${job.id}">
      <div class="job-item-score ${scoreClass}">${score}</div>
      <div class="job-item-body">
        <div class="job-item-title">${escHtml(job.title || '–')}${nBadge}</div>
        ${meta ? `<div class="job-item-meta">${meta}</div>` : ''}
      </div>
      <div class="job-item-right">
        <span class="badge badge-${job.status}" style="font-size:11px">${job.status}</span>
        ${appStr ? `<span class="job-item-appcount">${appStr}${deltaHtml ? ' ' + deltaHtml : ''}</span>` : ''}
        <span class="job-item-date">${postedStr}</span>
        <button class="hide-job-btn" title="Hide job" onclick="hideJob(event, ${job.id})">✕</button>
      </div>
    </div>
  `;
}

function renderDeptSectionCards(dept, jobs) {
  const icon = DEPT_ICONS[dept] || '📁';
  const isCollapsed = jobsState.collapsed[dept] || false;
  const sectionId = `sect-cards-${dept.replace(/[^a-z]/gi, '-')}`;

  return `
    <div class="dept-section" id="${sectionId}">
      <div class="dept-header" onclick="toggleDeptSection('${dept}', '${sectionId}')">
        <span class="dept-icon">${icon}</span>
        <span class="dept-name">${escHtml(dept)}</span>
        <span class="dept-count">${jobs.length}</span>
        <span class="dept-chevron ${isCollapsed ? 'collapsed' : ''}">▾</span>
      </div>
      <div class="dept-body ${isCollapsed ? 'collapsed' : ''}">
        <div class="job-cards-grid">
          ${jobs.map(j => jobCard(j)).join('')}
        </div>
      </div>
    </div>
  `;
}

function jobCard(job) {
  const score   = job.ev_score ?? 0;
  const scoreClass = score >= 60 ? 'high' : 'mid';
  const n       = jobNewness(job);
  const nBadge  = n === 'reposted'
    ? '<span class="newness-badge newness-reposted">Reposted</span>'
    : n === 'new'
    ? '<span class="newness-badge newness-new">New</span>'
    : '';

  const applicants = job.applicant_count_current;
  const appStr = applicants != null
    ? `${applicants}${job.applicant_count_quality === 'lower_bound' ? '+' : ''} applicants`
    : null;

  const delta24h = job.applicant_delta_24h;
  const deltaHtml = delta24h != null
    ? `<span class="delta ${delta24h > 0 ? 'positive' : delta24h < 0 ? 'negative' : 'neutral'}" style="font-size:12px">${delta24h > 0 ? '+' : ''}${delta24h}</span>`
    : '';

  const postedStr = job.posted_date_normalized
    ? formatDate(job.posted_date_normalized)
    : escHtml(job.posted_text_raw || '–');

  return `
    <div class="job-card${job.is_reposted ? ' job-card-reposted' : ''}" data-id="${job.id}">
      <div class="job-card-top">
        <div class="job-card-score-wrap">
          <div class="job-card-score ${scoreClass}">${score}</div>
        </div>
        <div class="job-card-badges">
          ${nBadge}
          <span class="badge badge-${job.status}">${job.status}</span>
        </div>
        <button class="hide-job-btn" title="Hide job" onclick="hideJob(event, ${job.id})">✕</button>
      </div>
      <div class="job-card-title">${escHtml(job.title || '–')}</div>
      <div class="job-card-meta">
        ${job.location ? `<span>${escHtml(job.location)}</span>` : ''}
        ${appStr ? `<span>${escHtml(appStr)}${deltaHtml ? ' ' + deltaHtml : ''}</span>` : ''}
      </div>
      <div class="job-card-footer">
        <span class="job-card-date">${postedStr}</span>
      </div>
    </div>
  `;
}

async function hideJob(event, jobId) {
  event.stopPropagation();
  try {
    await API.hideJob(jobId);
    const row = document.querySelector(`.job-row[data-id="${jobId}"]`);
    if (row) {
      row.style.transition = 'opacity .25s, transform .25s';
      row.style.opacity = '0';
      row.style.transform = 'translateX(12px)';
      setTimeout(() => row.remove(), 260);
    }
    showToast('Job hidden — manage in Settings', 'info');
  } catch (err) {
    showToast('Could not hide job: ' + err.message, 'error');
  }
}
