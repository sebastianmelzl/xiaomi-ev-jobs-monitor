/* ECharts utilities — shared theming and chart factories */

function getChartTheme() {
  const isDark = document.documentElement.dataset.theme === 'dark';
  return {
    textColor: isDark ? '#8888a0' : '#5a5a72',
    labelColor: isDark ? '#e2e2ec' : '#0f0f1a',
    splitLine: isDark ? '#1f1f2e' : '#e4e4ec',
    axisLine: isDark ? '#1f1f2e' : '#e4e4ec',
    tooltip: {
      bg: isDark ? '#14141a' : '#ffffff',
      border: isDark ? '#1f1f2e' : '#e4e4ec',
    },
  };
}

const EV_COLORS = {
  core_ev: '#10b981',
  likely_ev: '#3b82f6',
  maybe_ev: '#f59e0b',
  non_ev: '#6b7280',
};

function makeChart(el, option) {
  const chart = echarts.init(el, null, { renderer: 'svg' });
  chart.setOption(option);
  new ResizeObserver(() => chart.resize()).observe(el);
  return chart;
}

function baseAxisOption() {
  const t = getChartTheme();
  return {
    axisLine: { lineStyle: { color: t.axisLine } },
    axisTick: { show: false },
    axisLabel: { color: t.textColor, fontSize: 11 },
    splitLine: { lineStyle: { color: t.splitLine } },
  };
}

function baseTooltip(formatter) {
  const t = getChartTheme();
  return {
    trigger: 'axis',
    backgroundColor: t.tooltip.bg,
    borderColor: t.tooltip.border,
    borderWidth: 1,
    textStyle: { color: t.labelColor, fontSize: 12 },
    formatter,
  };
}

/* ── Chart factories ─────────────────────────────────────────────────────── */

function renderEVLabelPie(el, breakdown) {
  const t = getChartTheme();
  const data = [
    { name: 'Core EV', value: breakdown.core_ev, itemStyle: { color: EV_COLORS.core_ev } },
    { name: 'Likely EV', value: breakdown.likely_ev, itemStyle: { color: EV_COLORS.likely_ev } },
  ].filter(d => d.value > 0);

  return makeChart(el, {
    tooltip: {
      trigger: 'item',
      backgroundColor: t.tooltip.bg,
      borderColor: t.tooltip.border,
      borderWidth: 1,
      textStyle: { color: t.labelColor, fontSize: 12 },
      formatter: '{b}: {c} ({d}%)',
    },
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      itemStyle: { borderWidth: 2, borderColor: 'transparent' },
      label: { show: true, color: t.textColor, fontSize: 11, formatter: '{b}\n{c}' },
      data,
    }],
  });
}

function renderEVOverTime(el, rows) {
  const t = getChartTheme();
  const weeks = rows.map(r => r.week);
  const counts = rows.map(r => r.count);

  return makeChart(el, {
    grid: { top: 10, right: 10, bottom: 30, left: 36 },
    tooltip: baseTooltip((p) => `Week ${p[0].axisValue}<br/><b>${p[0].value} new EV jobs</b>`),
    xAxis: { ...baseAxisOption(), type: 'category', data: weeks },
    yAxis: { ...baseAxisOption(), type: 'value', minInterval: 1 },
    series: [{
      type: 'bar',
      data: counts,
      itemStyle: { color: EV_COLORS.likely_ev, borderRadius: [3, 3, 0, 0] },
      barMaxWidth: 40,
    }],
  });
}

function renderTopLocations(el, locations) {
  const t = getChartTheme();
  const names = locations.map(l => l.location);
  const counts = locations.map(l => l.count);

  return makeChart(el, {
    grid: { top: 10, right: 30, bottom: 10, left: 120 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltip.bg,
      borderColor: t.tooltip.border,
      borderWidth: 1,
      textStyle: { color: t.labelColor, fontSize: 12 },
    },
    xAxis: { ...baseAxisOption(), type: 'value', minInterval: 1 },
    yAxis: { ...baseAxisOption(), type: 'category', data: names, inverse: true },
    series: [{
      type: 'bar',
      data: counts,
      itemStyle: { color: EV_COLORS.core_ev, borderRadius: [0, 3, 3, 0] },
      barMaxWidth: 24,
      label: { show: true, position: 'right', color: t.textColor, fontSize: 11 },
    }],
  });
}

function renderApplicantTimeline(el, history) {
  const t = getChartTheme();
  if (!history || history.length === 0) {
    el.innerHTML = '<div class="empty-state" style="height:180px;"><p class="text-muted">No applicant data yet</p></div>';
    return null;
  }

  const dates = history.map(h => h.observed_at.split('T')[0]);
  const values = history.map(h => h.applicant_count_exact ?? h.applicant_count_min ?? null);

  return makeChart(el, {
    grid: { top: 10, right: 10, bottom: 30, left: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltip.bg,
      borderColor: t.tooltip.border,
      borderWidth: 1,
      textStyle: { color: t.labelColor, fontSize: 12 },
      formatter: (p) => {
        const h = history[p[0].dataIndex];
        const raw = h.raw_applicant_text || '';
        const q = h.applicant_count_quality;
        return `${p[0].axisValue}<br/><b>${p[0].value}</b> applicants${q === 'lower_bound' ? '+' : ''}<br/><small>${raw}</small>`;
      },
    },
    xAxis: { ...baseAxisOption(), type: 'category', data: dates },
    yAxis: { ...baseAxisOption(), type: 'value', minInterval: 1 },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: EV_COLORS.likely_ev, width: 2 },
      itemStyle: { color: EV_COLORS.likely_ev },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.3)' },
            { offset: 1, color: 'rgba(59,130,246,0.0)' },
          ],
        },
      },
    }],
  });
}

function renderJobsByDepartment(el, departments) {
  const t = getChartTheme();
  const names = departments.map(d => d.department);
  const counts = departments.map(d => d.count);

  return makeChart(el, {
    grid: { top: 10, right: 40, bottom: 10, left: 160 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltip.bg,
      borderColor: t.tooltip.border,
      borderWidth: 1,
      textStyle: { color: t.labelColor, fontSize: 12 },
    },
    xAxis: { ...baseAxisOption(), type: 'value', minInterval: 1 },
    yAxis: { ...baseAxisOption(), type: 'category', data: names, inverse: true, axisLabel: { fontSize: 11, width: 150, overflow: 'truncate' } },
    series: [{
      type: 'bar',
      data: counts,
      itemStyle: { color: '#6366f1', borderRadius: [0, 3, 3, 0] },
      barMaxWidth: 24,
      label: { show: true, position: 'right', color: t.textColor, fontSize: 11 },
    }],
  });
}

function renderScoreDistribution(el, dist) {
  const t = getChartTheme();
  const labels = dist.map(d => d.range);
  const counts = dist.map(d => d.count);

  return makeChart(el, {
    grid: { top: 10, right: 10, bottom: 40, left: 36 },
    tooltip: baseTooltip((p) => `Score ${p[0].axisValue}: <b>${p[0].value}</b> jobs`),
    xAxis: { ...baseAxisOption(), type: 'category', data: labels, axisLabel: { rotate: 30 } },
    yAxis: { ...baseAxisOption(), type: 'value', minInterval: 1 },
    series: [{
      type: 'bar',
      data: counts.map((v, i) => ({
        value: v,
        itemStyle: {
          color: i >= 6 ? EV_COLORS.core_ev : i >= 3 ? EV_COLORS.likely_ev : i >= 1 ? EV_COLORS.maybe_ev : EV_COLORS.non_ev,
          borderRadius: [3, 3, 0, 0],
        },
      })),
      barMaxWidth: 40,
    }],
  });
}
