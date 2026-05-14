/* Overview page */
async function renderOverview() {
  setPageTitle('Overview', 'Xiaomi EV Jobs Dashboard');

  const content = document.getElementById('content');
  content.innerHTML = loadingHtml();

  try {
    const [overview, evTime, deptData] = await Promise.all([
      API.overview(),
      API.chartsEvOverTime(90),
      API.chartsJobsByDepartment(),
    ]);

    const lastUpdate = overview.last_scrape_at
      ? formatRelTime(overview.last_scrape_at)
      : 'Never';

    content.innerHTML = `
      <div class="kpi-grid">
        ${kpiCard('Active EV Jobs', overview.ev_jobs_count, 'accent', `as of ${lastUpdate}`)}
        ${kpiCard('Posted this week', overview.posted_this_week, overview.posted_this_week > 0 ? 'accent' : '', 'by LinkedIn posted date')}
        ${kpiCard('Missing', overview.missing_jobs_count, overview.missing_jobs_count > 0 ? 'yellow' : '', 'not seen recently')}
        ${kpiCard('Last Scrape', '', '', formatStatusBadge(overview.last_scrape_status, lastUpdate), true)}
      </div>

      <div class="chart-grid">
        <div class="chart-card">
          <div class="chart-title">EV Jobs posted per Week <span style="font-size:11px;color:var(--text-muted)">(last 90 days · by posted date)</span></div>
          <div class="chart-container" id="chartWeekly" style="height:200px"></div>
        </div>
        <div class="chart-card">
          <div class="chart-title">Top Locations</div>
          <div class="chart-container" id="chartLocations" style="height:200px"></div>
        </div>
        <div class="chart-card chart-card--wide">
          <div class="chart-title">Jobs by Department</div>
          <div class="chart-container" id="chartDepts" style="height:260px"></div>
        </div>
      </div>

      <div class="section">
        <div class="section-header">
          <span class="section-title">Recently Posted</span>
          <a href="#/jobs" class="btn btn-ghost btn-sm">View all →</a>
        </div>
        <div id="recentJobsList">${loadingHtml()}</div>
      </div>
    `;

    // Update nav badge
    const badge = document.getElementById('navBadgeJobs');
    if (overview.ev_jobs_count > 0) {
      badge.textContent = overview.ev_jobs_count;
      badge.classList.add('visible');
    }

    // Weekly chart
    if (evTime.length > 0) {
      renderEVOverTime(document.getElementById('chartWeekly'), evTime);
    } else {
      document.getElementById('chartWeekly').innerHTML = emptyChartHtml('No posted-date data yet — run a scrape');
    }

    // Top locations
    if (overview.top_locations.length > 0) {
      renderTopLocations(document.getElementById('chartLocations'), overview.top_locations);
    } else {
      document.getElementById('chartLocations').innerHTML = emptyChartHtml('No location data yet');
    }

    // Department chart
    if (deptData.length > 0) {
      renderJobsByDepartment(document.getElementById('chartDepts'), deptData);
    } else {
      document.getElementById('chartDepts').innerHTML = emptyChartHtml('No department data yet');
    }

    // Recently posted jobs (last 8 by posted date)
    try {
      const recent = await API.jobs({
        ev_only: 'true',
        status: 'active',
        sort_by: 'posted_date_normalized',
        sort_dir: 'desc',
        page: 1,
        page_size: 8,
      });
      const el = document.getElementById('recentJobsList');
      if (!el) return;
      if (recent.items.length === 0) {
        el.innerHTML = '<div class="section-body"><p class="text-muted">No jobs yet — run a scrape.</p></div>';
        return;
      }
      el.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:0">
          ${recent.items.map(j => `
            <div class="recent-job-row" onclick="openJobModal(${j.id})" style="cursor:pointer">
              <div style="flex:1;min-width:0">
                <div style="font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtml(j.title || '–')}</div>
                <div style="font-size:12px;color:var(--text-muted);margin-top:2px">
                  ${escHtml(j.department || '')}${j.department && j.location ? ' · ' : ''}${escHtml(j.location || '')}
                </div>
              </div>
              <div style="flex-shrink:0;text-align:right;font-size:12px;color:var(--text-muted)">
                ${j.posted_date_normalized ? formatDate(j.posted_date_normalized) : escHtml(j.posted_text_raw || '–')}
              </div>
            </div>
          `).join('')}
        </div>
      `;
    } catch (_) {
      const el = document.getElementById('recentJobsList');
      if (el) el.innerHTML = '<div class="section-body"><p class="text-muted">Could not load recent jobs.</p></div>';
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

function formatStatusBadge(status, time) {
  if (!status) return '<span class="text-muted">–</span>';
  const cls = { success: 'success', partial: 'partial', failed: 'failed', running: 'running' }[status] || '';
  return `<span class="badge badge-${cls}">${status}</span><br/><span style="font-size:11px;color:var(--text-muted)">${time}</span>`;
}

function emptyChartHtml(msg) {
  return `<div class="empty-state" style="height:160px;"><p class="text-muted">${msg}</p></div>`;
}
