/* charts.js — thin Chart.js wrappers + Chart.js global defaults */

(function () {
  if (typeof Chart === 'undefined') return;
  // Chart.js v4 globals
  Chart.defaults.color = '#aab5c5';
  Chart.defaults.borderColor = '#1d2a40';
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  Chart.defaults.font.size = 11.5;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = '#131a26';
  Chart.defaults.plugins.tooltip.borderColor = '#22304a';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = '#e6ecf3';
  Chart.defaults.plugins.tooltip.bodyColor = '#e6ecf3';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.elements.point.radius = 0;
  Chart.defaults.elements.point.hoverRadius = 4;
  Chart.defaults.elements.line.tension = 0;
  Chart.defaults.elements.line.borderWidth = 1.6;
})();

const QT_CHARTS = {};  // store all chart instances keyed by canvas id

window.QTCharts = {
  destroy(id) {
    if (QT_CHARTS[id]) { QT_CHARTS[id].destroy(); delete QT_CHARTS[id]; }
  },
  get(id) { return QT_CHARTS[id]; },

  /* Common time-axis config */
  _timeAxis(unit = 'year') {
    return {
      type: 'time',
      time: { unit, tooltipFormat: 'yyyy-MM-dd' },
      grid: { color: '#1d2a40' },
      ticks: { color: '#6e7c93', maxRotation: 0, autoSkipPadding: 12 },
    };
  },
  _linearAxis(opts = {}) {
    return {
      type: 'linear',
      grid: { color: '#1d2a40' },
      ticks: { color: '#6e7c93', ...opts.ticks },
      ...opts,
    };
  },

  line(canvasId, datasets, opts = {}) {
    this.destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    const cfg = {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: opts.interaction || { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'top', align: 'end' },
          tooltip: { callbacks: opts.tooltipCallbacks },
        },
        scales: {
          x: this._timeAxis(opts.timeUnit || 'year'),
          y: this._linearAxis({
            ticks: { callback: opts.yFormat || ((v) => v) },
            grid: { color: '#1d2a40' },
          }),
        },
      },
    };
    if (opts.scales) Object.assign(cfg.options.scales, opts.scales);
    const c = new Chart(ctx, cfg);
    QT_CHARTS[canvasId] = c;
    return c;
  },

  bar(canvasId, labels, datasets, opts = {}) {
    this.destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    const cfg = {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { position: 'top', align: 'end' },
        },
        scales: {
          x: { grid: { color: '#1d2a40' }, ticks: { color: '#6e7c93' } },
          y: { grid: { color: '#1d2a40' }, ticks: { color: '#6e7c93', callback: opts.yFormat || ((v) => v) } },
        },
      },
    };
    if (opts.scales) Object.assign(cfg.options.scales, opts.scales);
    const c = new Chart(ctx, cfg);
    QT_CHARTS[canvasId] = c;
    return c;
  },

  scatter(canvasId, datasets, opts = {}) {
    this.destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    const cfg = {
      type: 'scatter',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { position: 'top', align: 'end' } },
        scales: {
          x: this._timeAxis(opts.timeUnit || 'year'),
          y: this._linearAxis({ ticks: { callback: opts.yFormat || ((v) => v) } }),
        },
      },
    };
    if (opts.scales) Object.assign(cfg.options.scales, opts.scales);
    const c = new Chart(ctx, cfg);
    QT_CHARTS[canvasId] = c;
    return c;
  },
};
