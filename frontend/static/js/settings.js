/* Settings page */
async function renderSettings() {
  setPageTitle('Settings', 'Configuration & scrape sources');
  const content = document.getElementById('content');
  content.innerHTML = loadingHtml();

  try {
    const status = await API.scrapeStatus();

    content.innerHTML = `
      <!-- Scheduler status -->
      <div class="settings-section">
        <div class="section-header"><span class="section-title">Scheduler</span></div>
        <div class="settings-row">
          <span class="settings-key">Enabled</span>
          <span class="settings-val">${status.scheduler.enabled ? '✅ Yes' : '❌ No (set SCHEDULER_ENABLED=true)'}</span>
        </div>
        <div class="settings-row">
          <span class="settings-key">Running</span>
          <span class="settings-val">${status.scheduler.running ? '✅ Running' : '–'}</span>
        </div>
        ${status.scheduler.interval_hours ? `
          <div class="settings-row">
            <span class="settings-key">Interval</span>
            <span class="settings-val">Every ${status.scheduler.interval_hours}h (SCHEDULER_INTERVAL_HOURS)</span>
          </div>
        ` : ''}
        ${status.scheduler.next_run ? `
          <div class="settings-row">
            <span class="settings-key">Next Run</span>
            <span class="settings-val">${formatDateTime(status.scheduler.next_run)}</span>
          </div>
        ` : ''}
      </div>

      <!-- Scrape status -->
      <div class="settings-section">
        <div class="section-header"><span class="section-title">Active Scrape</span></div>
        <div class="settings-row">
          <span class="settings-key">Status</span>
          <span class="settings-val">${status.is_running ? '⏳ Running (run #' + status.active_run_id + ')' : '💤 Idle'}</span>
        </div>
      </div>

      <!-- Environment -->
      <div class="settings-section">
        <div class="section-header"><span class="section-title">Configuration (.env)</span></div>
        <div class="settings-row">
          <span class="settings-key">DATABASE_URL</span>
          <span class="settings-val">sqlite:///./data/jobs.db</span>
        </div>
        <div class="settings-row">
          <span class="settings-key">ARCHIVE_MISSING_THRESHOLD</span>
          <span class="settings-val">3 runs (default)</span>
        </div>
        <div class="settings-row">
          <span class="settings-key">SCRAPER_HEADLESS</span>
          <span class="settings-val">true (default)</span>
        </div>
        <div class="settings-row">
          <span class="settings-key">SCRAPER_MIN_DELAY_S / MAX_DELAY_S</span>
          <span class="settings-val">2.0–5.0s (default)</span>
        </div>
        <div class="settings-row">
          <span class="settings-key">LINKEDIN_EMAIL / PASSWORD</span>
          <span class="settings-val">Optional — enables applicant counts</span>
        </div>
      </div>

      <!-- Sources config -->
      <div class="settings-section">
        <div class="section-header">
          <span class="section-title">Scrape Sources</span>
          <span style="font-size:12px;color:var(--text-muted)">config/sources.yml</span>
        </div>
        <div id="sourcesContent">
          ${loadingHtml()}
        </div>
      </div>

      <!-- EV Keywords -->
      <div class="settings-section">
        <div class="section-header">
          <span class="section-title">EV Classification Rules</span>
          <span style="font-size:12px;color:var(--text-muted)">config/ev_positive_keywords.yml · ev_negative_keywords.yml</span>
        </div>
        <div class="section-body">
          <p style="font-size:13px;color:var(--text-secondary);line-height:1.6">
            The EV classifier uses three tiers of positive keywords (<strong>hard +25pts</strong>, <strong>soft +10pts</strong>, <strong>context +5pts</strong>)
            and three tiers of negative penalties (<strong>strong -30pts</strong>, <strong>moderate -15pts</strong>, <strong>weak -5pts</strong>).
            Location boosts add +10pts for known automotive hubs (Munich, Stuttgart, etc.).
            <br/><br/>
            Labels: <span class="badge badge-core-ev">Core EV ≥60</span>
            <span class="badge badge-likely-ev">Likely EV ≥35</span>
            <span class="badge badge-maybe-ev">Maybe EV ≥15</span>
            <span class="badge badge-non-ev">Non-EV &lt;15</span>
            <br/><br/>
            To extend rules: edit the YAML files in <code class="text-mono">config/</code> and restart the app.
          </p>
        </div>
      </div>

      <!-- Hidden jobs -->
      <div class="settings-section">
        <div class="section-header">
          <span class="section-title">Hidden Jobs</span>
          <span style="font-size:12px;color:var(--text-muted)">Jobs you permanently dismissed</span>
        </div>
        <div id="hiddenJobsContent">${loadingHtml()}</div>
      </div>

      <!-- Danger zone -->
      <div class="settings-section danger-zone">
        <div class="section-header">
          <span class="section-title danger-title">Danger Zone</span>
        </div>
        <div class="section-body">
          <div class="danger-row">
            <div>
              <div class="danger-action-title">Reset all data</div>
              <div class="danger-action-sub">Deletes all scraped jobs, scrape history, and applicant data. Config files and scrape sources are kept. Use this to start completely fresh.</div>
            </div>
            <button class="btn btn-danger" onclick="confirmReset()">Reset Database</button>
          </div>
        </div>
      </div>

      <!-- Legal notice -->
      <div class="settings-section">
        <div class="section-header"><span class="section-title">⚠️ Legal & Compliance</span></div>
        <div class="section-body">
          <p style="font-size:13px;color:var(--text-secondary);line-height:1.7">
            This tool scrapes publicly visible LinkedIn job pages.
            <strong>LinkedIn's Terms of Service prohibit automated data collection</strong> without explicit written permission.
            Use this tool for personal research only, at your own risk and responsibility.
            Do not scrape at high frequency, do not scrape private/authenticated data without authorization,
            and do not redistribute scraped data commercially.
            The author assumes no liability for misuse.
          </p>
        </div>
      </div>
    `;

    // Load hidden jobs
    API.hiddenJobs().then(jobs => {
      const el = document.getElementById('hiddenJobsContent');
      if (!el) return;
      if (jobs.length === 0) {
        el.innerHTML = '<div class="section-body"><p class="text-muted" style="font-size:13px">No hidden jobs.</p></div>';
        return;
      }
      el.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:6px;padding:12px 0">
          ${jobs.map(j => `
            <div class="hidden-job-row" id="hjr-${j.job_id}">
              <div style="flex:1;min-width:0">
                <div style="font-size:13px;font-weight:500">${escHtml(j.title || '–')}</div>
                <div style="font-size:12px;color:var(--text-muted)">${escHtml(j.department || '')}${j.department && j.location ? ' · ' : ''}${escHtml(j.location || '')}</div>
              </div>
              <button class="btn btn-ghost btn-sm" onclick="unhideJob(${j.job_id})">Unhide</button>
            </div>
          `).join('')}
        </div>
      `;
    }).catch(() => {
      const el = document.getElementById('hiddenJobsContent');
      if (el) el.innerHTML = '<div class="section-body"><p class="text-muted">Could not load hidden jobs.</p></div>';
    });

    // Load sources from API
    fetch('/api/health').then(() => {
      // Sources are loaded from config — display static info for now
      document.getElementById('sourcesContent').innerHTML = `
        <div class="section-body" style="display:flex;flex-direction:column;gap:10px">
          ${renderSourceCard('xiaomi_global_jobs', 'All Xiaomi LinkedIn jobs', 'https://www.linkedin.com/jobs/search/?f_C=1090514', true)}
          ${renderSourceCard('xiaomi_ev_keyword', 'Xiaomi EV keyword search', 'https://www.linkedin.com/jobs/search/?keywords=xiaomi+electric+vehicle', true)}
          ${renderSourceCard('xiaomi_automotive_keyword', 'Xiaomi automotive keyword', 'https://www.linkedin.com/jobs/search/?keywords=xiaomi+automotive', true)}
          ${renderSourceCard('xiaomi_germany', 'Xiaomi jobs in Germany', 'https://www.linkedin.com/jobs/search/?f_C=1090514&geoId=101282230', true)}
          ${renderSourceCard('xiaomi_europe', 'Xiaomi jobs in Europe', 'https://www.linkedin.com/jobs/search/?f_C=1090514&geoId=91000000', true)}
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px">
            Edit <code class="text-mono">config/sources.yml</code> to add, remove, or disable sources.
          </p>
        </div>
      `;
    });

  } catch (err) {
    content.innerHTML = errorHtml(err.message);
  }
}

async function unhideJob(jobId) {
  try {
    await API.unhideJob(jobId);
    const row = document.getElementById(`hjr-${jobId}`);
    if (row) row.remove();
    showToast('Job unhidden — will reappear in EV Jobs list', 'success');
  } catch (err) {
    showToast('Could not unhide: ' + err.message, 'error');
  }
}

function confirmReset() {
  const overlay = document.createElement('div');
  overlay.className = 'reset-overlay';
  overlay.innerHTML = `
    <div class="reset-dialog">
      <div class="reset-dialog-icon">⚠️</div>
      <div class="reset-dialog-title">Reset all data?</div>
      <div class="reset-dialog-body">
        This will permanently delete all scraped jobs, scrape runs, and applicant history.
        Your config files and scrape sources will not be affected.
        <br><br>
        <strong>This cannot be undone.</strong>
      </div>
      <div class="reset-dialog-actions">
        <button class="btn btn-secondary" onclick="this.closest('.reset-overlay').remove()">Cancel</button>
        <button class="btn btn-danger" id="confirmResetBtn" onclick="executeReset(this)">Yes, delete everything</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
}

async function executeReset(btn) {
  btn.disabled = true;
  btn.textContent = 'Deleting…';
  try {
    const result = await API.resetAllData();
    document.querySelector('.reset-overlay')?.remove();
    showToast(`Database reset — ${result.total_rows} rows deleted. Ready for a fresh scrape.`, 'success');
    // Reload overview after short delay
    setTimeout(() => { window.location.hash = '#/'; router(); }, 1200);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Yes, delete everything';
    showToast('Reset failed: ' + err.message, 'error');
  }
}

function renderSourceCard(name, desc, url, enabled) {
  return `
    <div class="source-card">
      <div class="source-enabled ${enabled ? '' : 'source-disabled'}"></div>
      <div style="flex:1;min-width:0">
        <div class="source-name">${escHtml(name)}</div>
        <div style="font-size:12px;color:var(--text-secondary)">${escHtml(desc)}</div>
        <div class="source-url">${escHtml(url)}</div>
      </div>
      <span class="tag">${enabled ? 'enabled' : 'disabled'}</span>
    </div>
  `;
}
