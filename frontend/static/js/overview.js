/* Overview page — Intelligence Brief redesign */

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

    const lastUpdate = overview.last_scrape_at ? formatRelTime(overview.last_scrape_at) : 'Never';
    const scrapeStatus = overview.last_scrape_status || null;

    // Build signal banner
    const signals = _buildSignals(overview);
    const signalBanner = signals.length > 0
      ? `<div class="signal-banner">
           <span class="signal-banner-icon">⚡</span>
           <div class="signal-banner-items">
             ${signals.map(s => `<span class="signal-item signal-${s.type}">${s.text}</span>`).join('<span class="signal-sep">·</span>')}
           </div>
         </div>`
      : '';

    content.innerHTML = `
      ${signalBanner}

      <!-- KPI strip -->
      <div class="ov-stats">
        <div class="ov-stat">
          <div class="ov-stat-label">Active EV Jobs</div>
          <div class="ov-stat-value is-accent">${overview.ev_jobs_count}</div>
          <div class="ov-stat-sub">monitored roles</div>
        </div>
        <div class="ov-stat">
          <div class="ov-stat-label">Posted this Week</div>
          <div class="ov-stat-value ${overview.posted_this_week > 0 ? 'is-green' : ''}">${overview.posted_this_week}</div>
          <div class="ov-stat-sub">by LinkedIn posted date</div>
        </div>
        <div class="ov-stat">
          <div class="ov-stat-label">Missing</div>
          <div class="ov-stat-value ${overview.missing_jobs_count > 0 ? 'is-yellow' : ''}">${overview.missing_jobs_count}</div>
          <div class="ov-stat-sub">not seen last scrape</div>
        </div>
        <div class="ov-stat ov-stat--last">
          <div class="ov-stat-label">Last Scrape</div>
          ${scrapeStatus
            ? `<div class="ov-stat-badge"><span class="badge badge-${scrapeStatus}">${scrapeStatus}</span></div>`
            : `<div class="ov-stat-value">–</div>`}
          <div class="ov-stat-sub">${lastUpdate}</div>
        </div>
      </div>

      <!-- Two-column: signal feed + weekly chart -->
      <div class="ov-main-row">
        <div class="ov-col-feed">
          <div class="ov-card">
            <div class="ov-card-head">
              <span class="ov-card-title">Recently Posted</span>
              <a href="#/jobs" class="btn btn-ghost btn-sm">View all →</a>
            </div>
            <div id="recentJobsList"><div class="ov-card-body">${loadingHtml()}</div></div>
          </div>
        </div>
        <div class="ov-col-chart">
          <div class="ov-card">
            <div class="ov-card-head">
              <span class="ov-card-title">EV Jobs per Week</span>
              <span class="ov-card-hint">last 90 days</span>
            </div>
            <div class="ov-card-body">
              <div id="chartWeekly" class="ov-chart-area"></div>
            </div>
          </div>
          <div class="ov-card ov-card--mt">
            <div class="ov-card-head">
              <span class="ov-card-title">Top Locations</span>
            </div>
            <div class="ov-card-body">
              <div id="chartLocations" class="ov-chart-area"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Department breakdown: full width -->
      <div class="ov-card ov-card--mb">
        <div class="ov-card-head">
          <span class="ov-card-title">Jobs by Department</span>
          <span class="ov-card-hint">active core EV jobs</span>
        </div>
        <div class="ov-card-body">
          <div id="chartDepts" class="ov-chart-area ov-chart-area--dept"></div>
        </div>
      </div>
    `;

    // Update nav badge
    const badge = document.getElementById('navBadgeJobs');
    if (overview.ev_jobs_count > 0) {
      badge.textContent = overview.ev_jobs_count;
      badge.classList.add('visible');
    }

    // Weekly chart
    const weeklyEl = document.getElementById('chartWeekly');
    if (evTime.length > 0) {
      renderEVOverTime(weeklyEl, evTime);
    } else {
      weeklyEl.innerHTML = ovEmptyChart('No data yet — run a scrape');
    }

    // Locations chart
    const locEl = document.getElementById('chartLocations');
    if (overview.top_locations.length > 0) {
      renderTopLocations(locEl, overview.top_locations);
    } else {
      locEl.innerHTML = ovEmptyChart('No location data yet');
    }

    // Department chart
    const deptEl = document.getElementById('chartDepts');
    if (deptData.length > 0) {
      renderJobsByDepartment(deptEl, deptData);
    } else {
      deptEl.innerHTML = ovEmptyChart('No department data yet');
    }

    // Recently posted feed
    try {
      const recent = await API.jobs({
        ev_only: 'true', status: 'active',
        sort_by: 'posted_date_normalized', sort_dir: 'desc',
        page: 1, page_size: 10,
      });
      const el = document.getElementById('recentJobsList');
      if (!el) return;

      if (recent.items.length === 0) {
        el.innerHTML = '<div class="ov-card-body"><p class="text-muted">No jobs yet — run a scrape.</p></div>';
        return;
      }

      el.innerHTML = recent.items.map(j => {
        const n = jobNewness(j);
        const nBadge = n === 'reposted'
          ? '<span class="newness-badge newness-reposted">Reposted</span>'
          : n === 'new'
          ? '<span class="newness-badge newness-new">New</span>'
          : '';
        const score = j.ev_score ?? 0;
        const postedStr = j.posted_date_normalized
          ? formatDate(j.posted_date_normalized)
          : escHtml(j.posted_text_raw || '–');
        const meta = [j.department, j.location].filter(Boolean).map(escHtml).join(' · ');

        return `
          <div class="ov-feed-row" onclick="openJobModal(${j.id})">
            <div class="ov-feed-score ${score >= 60 ? 'high' : 'mid'}">${score}</div>
            <div class="ov-feed-body">
              <div class="ov-feed-title">${escHtml(j.title || '–')} ${nBadge}</div>
              <div class="ov-feed-meta">${meta}</div>
            </div>
            <div class="ov-feed-date">${postedStr}</div>
          </div>
        `;
      }).join('');

    } catch (_) {
      const el = document.getElementById('recentJobsList');
      if (el) el.innerHTML = '<div class="ov-card-body"><p class="text-muted">Could not load recent jobs.</p></div>';
    }

  } catch (err) {
    content.innerHTML = errorHtml(err.message);
  }
}

function _buildSignals(overview) {
  const signals = [];
  if (overview.posted_this_week >= 5) {
    signals.push({ type: 'positive', text: `${overview.posted_this_week} new EV jobs posted this week` });
  } else if (overview.posted_this_week > 0) {
    signals.push({ type: 'neutral', text: `${overview.posted_this_week} new post${overview.posted_this_week > 1 ? 's' : ''} this week` });
  }
  if (overview.missing_jobs_count >= 10) {
    signals.push({ type: 'warning', text: `${overview.missing_jobs_count} jobs missing from last scrape` });
  }
  if (overview.ev_jobs_count >= 50) {
    signals.push({ type: 'positive', text: `${overview.ev_jobs_count} active EV roles tracked` });
  }
  return signals;
}

function ovEmptyChart(msg) {
  return `<div class="ov-empty-chart"><span class="text-muted">${msg}</span></div>`;
}
