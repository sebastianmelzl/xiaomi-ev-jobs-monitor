/* EV Jobs page — sectioned by department group */

const DEPT_ORDER = ['Engineering & R&D', 'Product & Design', 'Business & Operations'];
const DEPT_ICONS = {
  'Engineering & R&D':     '⚙️',
  'Product & Design':      '🎯',
  'Business & Operations': '📊',
};

let jobsState = {
  search: '', status: 'active',
  collapsed: {},   // dept → true/false
};

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
        <div class="filters-spacer"></div>
        <button class="btn btn-secondary btn-sm" onclick="API.exportEVJobs()">↓ Export CSV</button>
      </div>
      <div id="jobsSections">${loadingHtml()}</div>
    </div>
  `;

  let searchTimeout;
  document.getElementById('jobSearch').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      jobsState.search = e.target.value;
      loadJobsSections();
    }, 300);
  });
  document.getElementById('jobStatus').addEventListener('change', (e) => {
    jobsState.status = e.target.value;
    loadJobsSections();
  });

  loadJobsSections();
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
    if (jobsState.search)  params.search = jobsState.search;
    if (jobsState.status)  params.status = jobsState.status;

    const data = await API.jobs(params);

    if (data.items.length === 0) {
      wrap.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <div class="empty-state-title">No jobs found</div>
          <div class="empty-state-sub">Try adjusting filters or run a scrape</div>
        </div>`;
      return;
    }

    // Group by department
    const groups = {};
    for (const job of data.items) {
      const dept = DEPT_ORDER.includes(job.department) ? job.department : 'Other';
      if (!groups[dept]) groups[dept] = [];
      groups[dept].push(job);
    }

    // Render sections in fixed order, then "Other" if present
    const order = [...DEPT_ORDER.filter(d => groups[d]), ...(groups['Other'] ? ['Other'] : [])];

    wrap.innerHTML = `
      <div style="font-size:12px;color:var(--text-muted);padding:0 0 12px 0">${data.total} job${data.total !== 1 ? 's' : ''}</div>
      ${order.map(dept => renderDeptSection(dept, groups[dept])).join('')}
    `;

    // Row click → modal
    wrap.querySelectorAll('.job-row').forEach(row => {
      row.addEventListener('click', () => openJobModal(parseInt(row.dataset.id)));
    });

  } catch (err) {
    wrap.innerHTML = errorHtml(err.message);
  }
}

function renderDeptSection(dept, jobs) {
  const icon = DEPT_ICONS[dept] || '📁';
  const isCollapsed = jobsState.collapsed[dept] || false;
  const sectionId = `sect-${dept.replace(/[^a-z]/gi, '-')}`;

  return `
    <div class="dept-section" id="${sectionId}">
      <div class="dept-header" onclick="toggleDeptSection('${dept}', '${sectionId}')">
        <span class="dept-icon">${icon}</span>
        <span class="dept-name">${escHtml(dept)}</span>
        <span class="dept-count">${jobs.length}</span>
        <span class="dept-chevron ${isCollapsed ? 'collapsed' : ''}">▾</span>
      </div>
      <div class="dept-body ${isCollapsed ? 'collapsed' : ''}">
        <div class="table-wrap">
          <table class="data-table dept-table">
            <thead>
              <tr>
                <th style="width:80px">Score</th>
                <th>Title</th>
                <th>Location</th>
                <th>Posted</th>
                <th>Applicants</th>
                <th>24h Δ</th>
                <th>Status</th>
                <th style="width:32px"></th>
              </tr>
            </thead>
            <tbody>
              ${jobs.map(job => jobRow(job)).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function toggleDeptSection(dept, sectionId) {
  jobsState.collapsed[dept] = !jobsState.collapsed[dept];
  const section = document.getElementById(sectionId);
  if (!section) return;
  const body    = section.querySelector('.dept-body');
  const chevron = section.querySelector('.dept-chevron');
  body.classList.toggle('collapsed', jobsState.collapsed[dept]);
  chevron.classList.toggle('collapsed', jobsState.collapsed[dept]);
}

function jobRow(job) {
  const score = job.ev_score ?? 0;
  const scoreClass = score >= 60 ? 'high' : 'mid';

  const applicants = job.applicant_count_current;
  const applicantDisplay = applicants != null
    ? `${applicants}${job.applicant_count_quality === 'lower_bound' ? '+' : ''}`
    : '<span class="text-muted">–</span>';

  const delta24h = job.applicant_delta_24h;
  const deltaHtml = delta24h != null
    ? `<span class="delta ${delta24h > 0 ? 'positive' : delta24h < 0 ? 'negative' : 'neutral'}">${delta24h > 0 ? '+' : ''}${delta24h}</span>`
    : '<span class="text-muted">–</span>';

  return `
    <tr class="job-row" data-id="${job.id}">
      <td>
        <div class="score-bar">
          <div class="score-track"><div class="score-fill ${scoreClass}" style="width:${score}%"></div></div>
          <span class="score-num">${score}</span>
        </div>
      </td>
      <td><span class="truncate" title="${escHtml(job.title || '')}">${escHtml(job.title || '–')}</span></td>
      <td><span class="truncate" title="${escHtml(job.location || '')}">${escHtml(job.location || '–')}</span></td>
      <td class="text-muted">${job.posted_date_normalized ? formatDate(job.posted_date_normalized) : escHtml(job.posted_text_raw || '–')}</td>
      <td>${applicantDisplay}</td>
      <td>${deltaHtml}</td>
      <td><span class="badge badge-${job.status}">${job.status}</span></td>
      <td><button class="hide-job-btn" title="Permanently hide this job" onclick="hideJob(event, ${job.id})">✕</button></td>
    </tr>
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
