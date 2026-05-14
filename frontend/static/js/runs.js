/* Scrape runs history page */
async function renderRuns() {
  setPageTitle('Scrape Runs', 'History of all scrape executions');
  const content = document.getElementById('content');
  content.innerHTML = loadingHtml();

  try {
    const runs = await API.runs(50);

    if (runs.length === 0) {
      content.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">⏱</div>
          <div class="empty-state-title">No scrape runs yet</div>
          <div class="empty-state-sub">Click "Run Scrape" in the top bar to start your first run</div>
        </div>
      `;
      return;
    }

    content.innerHTML = `
      <div class="section">
        <div class="section-header">
          <span class="section-title">Recent Runs</span>
          <span style="font-size:12px;color:var(--text-muted)">${runs.length} shown</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Source</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Seen</th>
                <th>New</th>
                <th>Updated</th>
                <th>Archived</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              ${runs.map(run => runRow(run)).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

  } catch (err) {
    content.innerHTML = errorHtml(err.message);
  }
}

function runRow(run) {
  const duration = run.finished_at
    ? formatDuration(new Date(run.finished_at) - new Date(run.started_at))
    : run.status === 'running' ? '⏳ running…' : '–';

  const statusCls = { success: 'success', failed: 'failed', partial: 'partial', running: 'running' }[run.status] || '';

  return `
    <tr>
      <td class="text-mono text-muted">${run.id}</td>
      <td><span class="truncate" title="${escHtml(run.source_name || '')}" style="max-width:160px">${escHtml(run.source_name || '–')}</span></td>
      <td class="text-muted">${formatDateTime(run.started_at)}</td>
      <td class="text-muted text-mono">${duration}</td>
      <td><span class="badge badge-${statusCls}">${run.status}</span></td>
      <td>${run.jobs_seen_count}</td>
      <td class="${run.jobs_inserted_count > 0 ? '' : 'text-muted'}">${run.jobs_inserted_count}</td>
      <td class="text-muted">${run.jobs_updated_count}</td>
      <td class="${run.jobs_archived_count > 0 ? 'text-muted' : 'text-muted'}">${run.jobs_archived_count}</td>
      <td class="${run.errors_count > 0 ? '' : 'text-muted'}" style="${run.errors_count > 0 ? 'color:var(--red)' : ''}">${run.errors_count}</td>
    </tr>
  `;
}

function formatDuration(ms) {
  if (ms < 0) return '–';
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}
