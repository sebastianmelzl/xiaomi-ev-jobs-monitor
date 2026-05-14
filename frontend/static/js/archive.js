/* Archive page */
let archiveState = { page: 1, pageSize: 50, evOnly: false };

async function renderArchive() {
  setPageTitle('Archive', 'Inactive jobs — missing threshold reached');
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="section">
      <div class="filters-bar">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-secondary);cursor:pointer">
          <input type="checkbox" id="archiveEvOnly" ${archiveState.evOnly ? 'checked' : ''} />
          EV jobs only
        </label>
        <div class="filters-spacer"></div>
        <button class="btn btn-secondary btn-sm" onclick="API.exportEVJobs()">↓ Export CSV (incl. archived)</button>
      </div>
      <div id="archiveTableWrap">${loadingHtml()}</div>
    </div>
  `;

  document.getElementById('archiveEvOnly').addEventListener('change', (e) => {
    archiveState.evOnly = e.target.checked;
    archiveState.page = 1;
    loadArchiveTable();
  });

  loadArchiveTable();
}

async function loadArchiveTable() {
  const wrap = document.getElementById('archiveTableWrap');
  if (!wrap) return;
  wrap.innerHTML = loadingHtml();

  try {
    const data = await API.archive({ page: archiveState.page, page_size: archiveState.pageSize, ev_only: archiveState.evOnly });

    if (data.items.length === 0) {
      wrap.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📦</div>
          <div class="empty-state-title">No archived jobs yet</div>
          <div class="empty-state-sub">Jobs disappear from LinkedIn after ${3} consecutive missed runs</div>
        </div>
      `;
      return;
    }

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data-table" id="archiveTable">
          <thead>
            <tr>
              <th>EV Label</th>
              <th>Score</th>
              <th>Title</th>
              <th>Location</th>
              <th>Archived At</th>
              <th>First Seen</th>
              <th>Peak Applicants</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            ${data.items.map(job => archiveRow(job)).join('')}
          </tbody>
        </table>
      </div>
      ${paginationHtml(data.total, archiveState.page, archiveState.pageSize, 'archiveChangePage')}
    `;

    document.querySelectorAll('#archiveTable tbody tr').forEach(row => {
      row.addEventListener('click', () => openJobModal(parseInt(row.dataset.id)));
    });

  } catch (err) {
    wrap.innerHTML = errorHtml(err.message);
  }
}

function archiveRow(job) {
  const evLabel = job.ev_label || 'non_ev';
  const score = job.ev_score ?? 0;
  const scoreClass = score >= 60 ? 'high' : score >= 35 ? 'mid' : score >= 15 ? 'low' : 'none';
  const peak = job.applicant_count_current;

  return `
    <tr data-id="${job.id}">
      <td><span class="badge badge-${evLabel.replace('_', '-')}">${formatEVLabel(evLabel)}</span></td>
      <td>
        <div class="score-bar">
          <div class="score-track"><div class="score-fill ${scoreClass}" style="width:${score}%"></div></div>
          <span class="score-num">${score}</span>
        </div>
      </td>
      <td><span class="truncate" title="${escHtml(job.title || '')}">${escHtml(job.title || '–')}</span></td>
      <td class="text-muted">${escHtml(job.location || '–')}</td>
      <td class="text-muted">${job.archived_at ? formatDate(job.archived_at) : '–'}</td>
      <td class="text-muted">${formatDate(job.first_seen_at)}</td>
      <td class="text-muted">${peak != null ? peak + (job.applicant_count_quality === 'lower_bound' ? '+' : '') : '–'}</td>
      <td><span class="tag">missing threshold</span></td>
    </tr>
  `;
}

function archiveChangePage(p) {
  archiveState.page = p;
  loadArchiveTable();
}
