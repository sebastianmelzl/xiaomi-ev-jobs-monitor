/* Overview page */
async function renderOverview() {
  setPageTitle('Overview', 'Xiaomi EV Jobs Dashboard');

  const content = document.getElementById('content');
  content.innerHTML = loadingHtml();

  try {
    const [overview, evTime, locations, scoreDist] = await Promise.all([
      API.overview(),
      API.chartsEvOverTime(90),
      Promise.resolve(null),
      API.chartsScoreDistribution(),
    ]);

    const lastUpdate = overview.last_scrape_at
      ? formatRelTime(overview.last_scrape_at)
      : 'Never';

    content.innerHTML = `
      <div class="kpi-grid">
        ${kpiCard('Active EV Jobs', overview.ev_jobs_count, 'accent', `As of ${lastUpdate}`)}
        ${kpiCard('New (last run)', overview.new_jobs_since_last_run, overview.new_jobs_since_last_run > 0 ? 'accent' : '', '')}
        ${kpiCard('Missing', overview.missing_jobs_count, overview.missing_jobs_count > 0 ? 'yellow' : '', 'not seen recently')}
        ${kpiCard('Archived', overview.archived_jobs_count, '', 'no longer listed')}
        ${kpiCard('Last Scrape', '', '', formatStatusBadge(overview.last_scrape_status), true)}
      </div>

      <div class="chart-grid">
        <div class="chart-card">
          <div class="chart-title">New EV Jobs per Week</div>
          <div class="chart-container" id="chartWeekly" style="height:200px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Top Locations</div>
          <div class="chart-container" id="chartLocations" style="height:200px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">EV Score Distribution</div>
          <div class="chart-container" id="chartScores" style="height:200px"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-header">
          <span class="section-title">Top EV Locations</span>
          <a href="#/jobs" class="btn btn-ghost btn-sm">View all jobs →</a>
        </div>
        <div class="section-body" id="topLocationsTable">
          ${overview.top_locations.length
            ? overview.top_locations.map(l =>
                `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
                  <span>${escHtml(l.location)}</span>
                  <span class="badge badge-core-ev">${l.count}</span>
                </div>`
              ).join('')
            : '<p class="text-muted">No location data yet</p>'}
        </div>
      </div>
    `;

    // Render charts
    if (evTime.length > 0) {
      renderEVOverTime(document.getElementById('chartWeekly'), evTime);
    } else {
      document.getElementById('chartWeekly').innerHTML = emptyChartHtml('No weekly data yet');
    }
    if (overview.top_locations.length > 0) {
      renderTopLocations(document.getElementById('chartLocations'), overview.top_locations);
    } else {
      document.getElementById('chartLocations').innerHTML = emptyChartHtml('No location data yet');
    }
    if (scoreDist.length > 0) {
      renderScoreDistribution(document.getElementById('chartScores'), scoreDist);
    } else {
      document.getElementById('chartScores').innerHTML = emptyChartHtml('Run a scrape to see score distribution');
    }

    // Update nav badge
    const badge = document.getElementById('navBadgeJobs');
    if (overview.ev_jobs_count > 0) {
      badge.textContent = overview.ev_jobs_count;
      badge.classList.add('visible');
    }

  } catch (err) {
    content.innerHTML = errorHtml(err.message);
  }
}

function kpiCard(label, value, colorClass, sub, rawValue = false) {
  const displayValue = rawValue ? sub : value;
  return `
    <div class="kpi-card">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value ${colorClass}">${displayValue}</div>
      ${!rawValue ? `<div class="kpi-sub">${sub}</div>` : ''}
    </div>
  `;
}

function evLabelStat(label, count, cls) {
  return `
    <div style="display:flex;flex-direction:column;gap:4px">
      <span class="badge badge-${cls}">${label}</span>
      <span style="font-size:22px;font-weight:700">${count}</span>
    </div>
  `;
}

function formatStatusBadge(status) {
  if (!status) return '<span class="text-muted">–</span>';
  const cls = { success: 'success', partial: 'partial', failed: 'failed', running: 'running' }[status] || '';
  return `<span class="badge badge-${cls}">${status}</span>`;
}

function emptyChartHtml(msg) {
  return `<div class="empty-state" style="height:200px;"><p class="text-muted">${msg}</p></div>`;
}
