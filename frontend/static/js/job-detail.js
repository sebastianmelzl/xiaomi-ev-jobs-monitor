/* Job detail modal/panel */
async function openJobModal(jobId) {
  const modal = document.getElementById('jobModal');
  const panel = document.getElementById('jobModalPanel');
  modal.style.display = 'flex';
  panel.innerHTML = loadingHtml();
  document.body.style.overflow = 'hidden';

  try {
    const [job, history] = await Promise.all([
      API.job(jobId),
      API.jobApplicants(jobId),
    ]);

    const ev = job.ev_classification;
    const evLabel = ev ? ev.ev_label : 'non_ev';
    const evScore = ev ? ev.ev_score : 0;

    panel.innerHTML = `
      <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
            <span class="badge badge-${evLabel.replace('_', '-')}">${formatEVLabelFull(evLabel)}</span>
            <span class="badge badge-${job.status}">${job.status}</span>
            ${job.is_reposted ? '<span class="newness-badge newness-reposted">Reposted</span>' : ''}
          </div>
          <h2 style="font-size:17px;font-weight:700;line-height:1.3">${escHtml(job.title || 'Untitled')}</h2>
          <p style="color:var(--text-secondary);margin-top:4px;font-size:13px">${escHtml(job.company_name || '')} · ${escHtml(job.location || '')}</p>
        </div>
        <button class="btn btn-ghost btn-sm" onclick="closeJobModal()" style="flex-shrink:0;margin-left:12px">✕ Close</button>
      </div>

      <div class="job-meta-grid">
        ${metaItem('Department', job.department)}
        ${metaItem('Employment', job.employment_type)}
        ${metaItem('Seniority', job.seniority_level)}
        ${metaItem('Posted', job.posted_text_raw || (job.posted_date_normalized ? formatDate(job.posted_date_normalized) : null))}
        ${metaItem('First Seen', formatDate(job.first_seen_at))}
        ${metaItem('Last Seen', formatDate(job.last_seen_at))}
        ${job.archived_at ? metaItem('Archived', formatDate(job.archived_at)) : ''}
        ${metaItem('Missing Count', job.missing_count)}
      </div>

      ${job.job_url ? `
        <a href="${job.job_url}" target="_blank" rel="noopener" class="btn btn-secondary btn-sm" style="margin-bottom:20px">
          ↗ Open on LinkedIn
        </a>
      ` : ''}

      <!-- EV Classification -->
      ${ev ? `
        <div class="section" style="margin-bottom:16px">
          <div class="section-header">
            <span class="section-title">EV Classification</span>
            <span style="font-size:12px;color:var(--text-muted)">v${ev.classifier_version}</span>
          </div>
          <div class="section-body">
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
              <div>
                <div class="kpi-label">Score</div>
                <div class="kpi-value ${evScore >= 60 ? 'green' : evScore >= 35 ? 'accent' : 'yellow'}">${evScore}</div>
              </div>
              <div>
                <div class="kpi-label">Confidence</div>
                <div class="kpi-value">${(ev.ev_confidence * 100).toFixed(0)}%</div>
              </div>
              <div>
                <div class="kpi-label">Label</div>
                <span class="badge badge-${evLabel.replace('_', '-')}" style="font-size:13px">${formatEVLabelFull(evLabel)}</span>
              </div>
            </div>
            <div class="kpi-label" style="margin-bottom:6px">Scoring Breakdown</div>
            <div class="reasoning-list">
              ${(ev.reasoning_json || []).map(r => {
                const isPositive = r.startsWith('+');
                return `<div class="reasoning-item ${isPositive ? 'positive' : 'negative'}">${escHtml(r)}</div>`;
              }).join('') || '<span class="text-muted">No reasoning available</span>'}
            </div>
          </div>
        </div>
      ` : ''}

      <!-- Applicant timeline -->
      <div class="section" style="margin-bottom:16px">
        <div class="section-header">
          <span class="section-title">Applicant History</span>
          ${history.length > 0 ? `<span style="font-size:12px;color:var(--text-muted)">${history.length} data points</span>` : ''}
        </div>
        <div class="section-body">
          <div id="applicantChart" style="height:180px"></div>
          ${history.length > 0 ? `
            <div style="margin-top:12px;display:flex;gap:20px;font-size:12px;color:var(--text-muted)">
              ${(() => {
                const latest = history[history.length - 1];
                const current = latest.applicant_count_exact ?? latest.applicant_count_min;
                const quality = latest.applicant_count_quality;
                return `
                  <span>Latest: <strong>${current != null ? current + (quality === 'lower_bound' ? '+' : '') : '–'}</strong></span>
                  <span>Quality: <strong>${quality}</strong></span>
                  <span>Raw: <em>${escHtml(latest.raw_applicant_text || '–')}</em></span>
                `;
              })()}
            </div>
          ` : ''}
        </div>
      </div>

      <!-- Description -->
      ${job.description_text ? `
        <div class="section" style="margin-bottom:16px">
          <div class="section-header"><span class="section-title">Job Description</span></div>
          <div class="desc-body">${formatDescription(job.description_text)}</div>
        </div>
      ` : ''}

      <!-- Change log -->
      ${job.change_log && job.change_log.length > 0 ? `
        <div class="section">
          <div class="section-header"><span class="section-title">Change History</span></div>
          <div class="section-body">
            <div class="change-log-list">
              ${job.change_log.map(c => changeLogItem(c)).join('')}
            </div>
          </div>
        </div>
      ` : ''}
    `;

    // Render applicant chart
    renderApplicantTimeline(document.getElementById('applicantChart'), history);

  } catch (err) {
    panel.innerHTML = `${errorHtml(err.message)}<button class="btn btn-secondary" onclick="closeJobModal()">Close</button>`;
  }
}

function closeJobModal(evt) {
  if (evt && evt.target !== document.getElementById('jobModal')) return;
  document.getElementById('jobModal').style.display = 'none';
  document.body.style.overflow = '';
}

function metaItem(label, value) {
  if (value == null || value === '') return '';
  return `
    <div class="meta-item">
      <span class="meta-label">${label}</span>
      <span class="meta-value">${escHtml(String(value))}</span>
    </div>
  `;
}

function changeLogItem(c) {
  const descriptions = {
    insert: 'Job first seen',
    status_change: `Status → <span class="change-field">${c.new_value}</span>`,
    reactivation: 'Job reactivated',
    archive: 'Job archived (missing threshold)',
    update: `<span class="change-field">${c.field_name}</span>: ${escHtml(c.old_value || '–')} → ${escHtml(c.new_value || '–')}`,
  };
  return `
    <div class="change-item">
      <span class="change-time">${formatDate(c.changed_at)}</span>
      <span class="change-desc">${descriptions[c.change_type] || escHtml(c.change_type)}</span>
    </div>
  `;
}

function formatEVLabelFull(label) {
  return { core_ev: 'Core EV', likely_ev: 'Likely EV', maybe_ev: 'Maybe EV', non_ev: 'Non-EV' }[label] || label;
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeJobModal();
});

/* ── Description formatter ───────────────────────────────────────────────── */
const _BULLET_RE   = /^[•·▪◦✓✔*\-–—]\s+(.+)/;
const _NUMBERED_RE = /^(\d+)[.)]\s+(.+)/;

function formatDescription(text) {
  if (!text) return '';

  const lines = text.split('\n').map(l => l.trim());
  const out = [];
  const bullets = [];

  function flushBullets() {
    if (!bullets.length) return;
    out.push(`<ul class="desc-list">${bullets.map(b => `<li>${escHtml(b)}</li>`).join('')}</ul>`);
    bullets.length = 0;
  }

  function isHeading(line, nextLines) {
    if (!line || line.length > 120) return false;
    // Ends with colon
    if (line.endsWith(':')) return true;
    // ALL CAPS (and contains at least one letter)
    if (line === line.toUpperCase() && /[A-Z]/.test(line) && line.length >= 3) return true;
    // Short line immediately followed by a bullet list
    if (line.length < 80) {
      for (const nl of nextLines.slice(0, 4)) {
        if (!nl) continue;
        if (_BULLET_RE.test(nl) || _NUMBERED_RE.test(nl)) return true;
        break;
      }
    }
    return false;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (!line) { flushBullets(); continue; }

    // Bullet / numbered list item
    const bm = _BULLET_RE.exec(line);
    if (bm) { bullets.push(bm[1]); continue; }
    const nm = _NUMBERED_RE.exec(line);
    // Guard: "3+ years" is NOT a numbered list item
    if (nm && !line.match(/^\d+[+\-]?\s*\w/)) { bullets.push(nm[2]); continue; }

    flushBullets();

    if (isHeading(line, lines.slice(i + 1))) {
      out.push(`<div class="desc-heading">${escHtml(line.replace(/:$/, ''))}</div>`);
    } else {
      out.push(`<p class="desc-para">${escHtml(line)}</p>`);
    }
  }

  flushBullets();
  return out.join('');
}
