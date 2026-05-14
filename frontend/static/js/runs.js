/* Scrape runs history page */
let _logPollInterval = null;

async function renderRuns() {
  setPageTitle('Scrape Runs', 'History of all scrape executions');
  const content = document.getElementById('content');
  content.innerHTML = loadingHtml();

  if (_logPollInterval) {
    clearInterval(_logPollInterval);
    _logPollInterval = null;
  }

  try {
    const [runs, status] = await Promise.all([API.runs(50), API.scrapeStatus()]);
    const activeRunId = status.active_run_id;

    content.innerHTML = `
      <div class="section">
        <div class="section-header">
          <span class="section-title">Recent Runs</span>
          <span style="font-size:12px;color:var(--text-muted)">${runs.length} shown</span>
        </div>
        <div id="runsTableContainer">
          ${runsTableHtml(runs)}
        </div>
      </div>
      ${activeRunId ? liveLogSectionHtml(activeRunId) : ''}
    `;

    if (activeRunId) {
      _startLogPolling(activeRunId);
    }
  } catch (err) {
    content.innerHTML = errorHtml(err.message);
  }
}

function liveLogSectionHtml(runId) {
  return `
    <div class="section" id="liveLogSection">
      <div class="section-header">
        <span class="section-title">Live Log — Run #${runId}</span>
        <span class="badge badge-running" id="liveLogBadge" style="font-size:11px">● running</span>
      </div>
      <div id="liveLogContainer" class="log-output"></div>
    </div>
  `;
}

function runsTableHtml(runs) {
  if (runs.length === 0) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">⏱</div>
        <div class="empty-state-title">No scrape runs yet</div>
        <div class="empty-state-sub">Click "Run Scrape" in the top bar to start your first run</div>
      </div>
    `;
  }
  return `
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
  `;
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
      <td class="text-muted">${run.jobs_archived_count}</td>
      <td class="${run.errors_count > 0 ? '' : 'text-muted'}" style="${run.errors_count > 0 ? 'color:var(--red)' : ''}">${run.errors_count}</td>
    </tr>
  `;
}

function _startLogPolling(runId) {
  let lastCount = 0;

  async function tick() {
    try {
      const data = await API.runLogs(runId);
      const logs = data.logs || [];

      const container = document.getElementById('liveLogContainer');
      if (container && logs.length > lastCount) {
        const newEntries = logs.slice(lastCount);
        newEntries.forEach(entry => {
          const line = document.createElement('div');
          line.className = `log-line log-${entry.level.toLowerCase()}`;
          line.innerHTML =
            `<span class="log-ts">${entry.ts.slice(11, 19)}</span>` +
            ` <span class="log-lvl">${entry.level}</span>` +
            ` ${escHtml(entry.msg)}`;
          container.appendChild(line);
        });
        container.scrollTop = container.scrollHeight;
        lastCount = logs.length;
      }

      const status = await API.scrapeStatus();
      if (!status.is_running) {
        clearInterval(_logPollInterval);
        _logPollInterval = null;

        const badge = document.getElementById('liveLogBadge');
        if (badge) badge.remove();

        const title = document.querySelector('#liveLogSection .section-title');
        if (title) title.textContent = `Log — Run #${runId}`;

        const runs = await API.runs(50);
        const tableContainer = document.getElementById('runsTableContainer');
        if (tableContainer) tableContainer.innerHTML = runsTableHtml(runs);
      }
    } catch (_) {}
  }

  tick();
  _logPollInterval = setInterval(tick, 2000);
}

function formatDuration(ms) {
  if (ms < 0) return '–';
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}
