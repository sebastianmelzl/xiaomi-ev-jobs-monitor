/* EV Jobs table page */
let jobsState = {
  page: 1, pageSize: 50, total: 0,
  search: '', status: 'active', evLabel: '', department: '',
  sortBy: 'department', sortDir: 'asc',
};

async function renderJobs() {
  setPageTitle('EV Jobs', 'Active & monitored roles');
  const content = document.getElementById('content');

  // Fetch departments for filter dropdown
  let departments = [];
  try { departments = await API.jobDepartments(); } catch (_) {}

  const deptOptions = departments.map(d =>
    `<option value="${escHtml(d)}" ${jobsState.department === d ? 'selected' : ''}>${escHtml(d)}</option>`
  ).join('');

  content.innerHTML = `
    <div class="section">
      <div class="filters-bar">
        <input type="text" class="search-input" id="jobSearch" placeholder="Search title, location…" value="${jobsState.search}" />
        <select class="filter-select" id="jobDept">
          <option value="" ${jobsState.department === '' ? 'selected' : ''}>All departments</option>
          ${deptOptions}
        </select>
        <select class="filter-select" id="jobStatus">
          <option value="active" ${jobsState.status === 'active' ? 'selected' : ''}>Active</option>
          <option value="missing" ${jobsState.status === 'missing' ? 'selected' : ''}>Missing</option>
          <option value="" ${jobsState.status === '' ? 'selected' : ''}>All statuses</option>
        </select>
        <div class="filters-spacer"></div>
        <button class="btn btn-secondary btn-sm" onclick="API.exportEVJobs()">↓ Export CSV</button>
      </div>
      <div id="jobsTableWrap">
        ${loadingHtml()}
      </div>
    </div>
  `;

  let searchTimeout;
  document.getElementById('jobSearch').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      jobsState.search = e.target.value;
      jobsState.page = 1;
      loadJobsTable();
    }, 300);
  });
  document.getElementById('jobDept').addEventListener('change', (e) => {
    jobsState.department = e.target.value;
    jobsState.page = 1;
    loadJobsTable();
  });
  document.getElementById('jobStatus').addEventListener('change', (e) => {
    jobsState.status = e.target.value;
    jobsState.page = 1;
    loadJobsTable();
  });

  loadJobsTable();
}

async function loadJobsTable() {
  const wrap = document.getElementById('jobsTableWrap');
  if (!wrap) return;
  wrap.innerHTML = loadingHtml();

  try {
    const params = {
      page: jobsState.page,
      page_size: jobsState.pageSize,
      sort_by: jobsState.sortBy,
      sort_dir: jobsState.sortDir,
    };
    if (jobsState.search) params.search = jobsState.search;
    if (jobsState.status) params.status = jobsState.status;
    if (jobsState.department) params.department = jobsState.department;
    params.ev_only = 'true';

    const data = await API.jobs(params);
    jobsState.total = data.total;

    if (data.items.length === 0) {
      wrap.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <div class="empty-state-title">No jobs found</div>
          <div class="empty-state-sub">Try adjusting filters or run a scrape</div>
        </div>
      `;
      return;
    }

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data-table" id="jobsTable">
          <thead>
            <tr>
              <th data-col="ev_score" class="${jobsState.sortBy === 'ev_score' ? 'sort-' + jobsState.sortDir : ''}">Score</th>
              <th data-col="title">Title</th>
              <th data-col="location">Location</th>
              <th data-col="department" class="${jobsState.sortBy === 'department' ? 'sort-' + jobsState.sortDir : ''}">Department</th>
              <th data-col="posted_date_normalized" class="${jobsState.sortBy === 'posted_date_normalized' ? 'sort-' + jobsState.sortDir : ''}">Posted</th>
              <th data-col="applicant_count_current">Applicants</th>
              <th data-col="delta_24h">24h Δ</th>
              <th data-col="status">Status</th>
              <th data-col="first_seen_at" class="${jobsState.sortBy === 'first_seen_at' ? 'sort-' + jobsState.sortDir : ''}">First Seen</th>
            </tr>
          </thead>
          <tbody>
            ${data.items.map(job => jobRow(job)).join('')}
          </tbody>
        </table>
      </div>
      ${paginationHtml(data.total, jobsState.page, jobsState.pageSize)}
    `;

    // Sort handlers
    document.querySelectorAll('#jobsTable th[data-col]').forEach(th => {
      th.addEventListener('click', () => {
        const col = th.dataset.col;
        const sortable = ['ev_score', 'department', 'first_seen_at', 'last_seen_at', 'posted_date_normalized'];
        if (!sortable.includes(col)) return;
        if (jobsState.sortBy === col) {
          jobsState.sortDir = jobsState.sortDir === 'desc' ? 'asc' : 'desc';
        } else {
          jobsState.sortBy = col;
          jobsState.sortDir = 'desc';
        }
        loadJobsTable();
      });
    });

    // Row click
    document.querySelectorAll('#jobsTable tbody tr').forEach(row => {
      row.addEventListener('click', () => openJobModal(parseInt(row.dataset.id)));
    });

  } catch (err) {
    wrap.innerHTML = errorHtml(err.message);
  }
}

function jobRow(job) {
  const evLabel = job.ev_label || 'non_ev';
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
    <tr data-id="${job.id}">
      <td>
        <div class="score-bar">
          <div class="score-track"><div class="score-fill ${scoreClass}" style="width:${score}%"></div></div>
          <span class="score-num">${score}</span>
        </div>
      </td>
      <td><span class="truncate" title="${escHtml(job.title || '')}">${escHtml(job.title || '–')}</span></td>
      <td><span class="truncate" title="${escHtml(job.location || '')}">${escHtml(job.location || '–')}</span></td>
      <td><span class="truncate text-muted">${escHtml(job.department || '–')}</span></td>
      <td class="text-muted">${job.posted_date_normalized ? formatDate(job.posted_date_normalized) : escHtml(job.posted_text_raw || '–')}</td>
      <td>${applicantDisplay}</td>
      <td>${deltaHtml}</td>
      <td><span class="badge badge-${job.status}">${job.status}</span></td>
      <td class="text-muted">${formatDate(job.first_seen_at)}</td>
    </tr>
  `;
}

function paginationHtml(total, page, pageSize) {
  const totalPages = Math.ceil(total / pageSize);
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return `
    <div class="pagination">
      <span>${start}–${end} of ${total} jobs</span>
      <div class="pagination-controls">
        <button class="page-btn" onclick="jobsChangePage(${page - 1})" ${page <= 1 ? 'disabled' : ''}>‹ Prev</button>
        ${Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
          const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
          return `<button class="page-btn ${p === page ? 'active' : ''}" onclick="jobsChangePage(${p})">${p}</button>`;
        }).join('')}
        <button class="page-btn" onclick="jobsChangePage(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>Next ›</button>
      </div>
    </div>
  `;
}

function jobsChangePage(p) {
  jobsState.page = p;
  loadJobsTable();
}

function formatEVLabel(label) {
  return { core_ev: 'Core EV', likely_ev: 'Likely EV', maybe_ev: 'Maybe EV', non_ev: 'Non-EV' }[label] || label;
}
