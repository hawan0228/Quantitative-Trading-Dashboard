/* main.js - app entry for the backtesting dashboard */

(function () {
  'use strict';

  if (!window.QT_DATA) {
    document.body.innerHTML = '<pre style="color:#ff5d6c;padding:24px">缺少 data/data_bundle.js。請先執行 python generate_data.py。</pre>';
    return;
  }

  const D = window.QT_DATA;
  const STRATEGIES = [
    'Buy-and-Hold',
    'Fair DCA',
    'SMA 20/60',
    'SMA 50/200',
    'SMA 100/300',
  ];
  const SMA_STRATEGIES = [
    'SMA 20/60',
    'SMA 50/200',
    'SMA 100/300',
  ];
  const STRATEGY_LABELS = {
    'Buy-and-Hold': 'Buy-and-Hold',
    'Fair DCA': 'Fair DCA',
    'SMA 20/60': 'SMA 20/60',
    'SMA 50/200': 'SMA 50/200',
    'SMA 100/300': 'SMA 100/300',
  };
  const STOCK_COLORS = {
    MCD: '#5aa9ff',
    KO: '#9ad07a',
    AAPL: '#f5b75a',
    MSFT: '#ff8aa1',
    ORCL: '#cc8eff',
    SPY: '#a0a0a0',
  };
  const STRATEGY_COLORS = {
    'Buy-and-Hold': '#5aa9ff',
    'Fair DCA': '#9ad07a',
    'SMA 20/60': '#f5b75a',
    'SMA 50/200': '#ff8aa1',
    'SMA 100/300': '#cc8eff',
  };

  const ASSUMPTION_LABELS = {
    data_source: '資料來源',
    stock_universe: '股票母體',
    market_benchmark: '市場基準',
    fractional_shares: '可交易碎股',
    transaction_costs: '交易成本',
    short_selling: '放空',
    signal_execution_timing: '訊號執行時機',
    sma_strategies: 'SMA 策略',
    sma_signal_source: 'SMA 訊號來源',
    sma_parameter_note: 'SMA 參數說明',
    pairs_zscore_window: '配對 z-score 視窗',
    pairs_entry_threshold: '進場門檻',
    pairs_exit_threshold: '平倉門檻',
    pairs_position_sizing: '部位規則',
    borrowing_costs: '借貸成本',
    temporal_validation_method: '時序驗證方式',
    pair_selection_rule: '配對選擇規則',
    look_ahead_bias_control: '提前看偏誤控制',
    spy_usage_note: 'SPY 使用備註',
    removed_strategy_note: '移除策略說明',
    cleanup_note: '清理說明',
  };

  const perfRows = D.strategy_performance || [];
  const stockSummary = D.stock_summary || [];
  const marketBenchmark = D.market_benchmark || [];
  const priceRows = D.stock_prices || [];
  const equityCurves = D.equity_curves || [];
  const smaTradeMarkers = D.sma_trade_markers || [];
  const temporalRows = D.temporal_validation || [];
  const pairTemporalRows = D.pairs_temporal_validation || [];
  const pairTemporalCurves = D.pairs_temporal_curves || [];
  const pairWindowCorrelations = D.pairs_window_correlations || [];
  const assumptions = D.assumptions || {};

  const byTicker = Object.fromEntries(stockSummary.map((row) => [row.ticker, row]));

  function fmtMoney(value, digits = 0) {
    if (value == null || Number.isNaN(Number(value))) return 'N/A';
    return '$' + Number(value).toLocaleString(undefined, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function fmtPct(value, digits = 2) {
    if (value == null || Number.isNaN(Number(value))) return 'N/A';
    return (Number(value) * 100).toFixed(digits) + '%';
  }

  function fmtSignedPct(value, digits = 2) {
    if (value == null || Number.isNaN(Number(value))) return 'N/A';
    const n = Number(value);
    return (n >= 0 ? '+' : '') + (n * 100).toFixed(digits) + '%';
  }

  function fmtNum(value, digits = 2) {
    if (value == null || Number.isNaN(Number(value))) return 'N/A';
    return Number(value).toFixed(digits);
  }

  function fmtSharpe(value) {
    return fmtNum(value, 2);
  }

  function priceDate(row) {
    return row.date || row.Date;
  }

  function cls(value) {
    return Number(value) >= 0 ? 'pos' : 'neg';
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function sortByWindow(rows) {
    return rows.slice().sort((a, b) => a.window_id.localeCompare(b.window_id));
  }

  function populateSelect(id, values) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';
    values.forEach((value) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      el.appendChild(option);
    });
  }

  function smaWindows(strategy) {
    const match = /SMA\s+(\d+)\/(\d+)/.exec(strategy);
    if (!match) return { shortWindow: 50, longWindow: 200 };
    return { shortWindow: Number(match[1]), longWindow: Number(match[2]) };
  }

  function movingAverage(rows, windowSize) {
    let rollingSum = 0;
    return rows.map((row, index) => {
      const price = Number(row.adj_close);
      rollingSum += price;
      if (index >= windowSize) rollingSum -= Number(rows[index - windowSize].adj_close);
      if (index < windowSize - 1) return null;
      return { x: priceDate(row), y: rollingSum / windowSize };
    }).filter(Boolean);
  }

  function renderSmaSignalChart(ticker, strategy) {
    const rows = priceRows
      .filter((row) => row.ticker === ticker)
      .sort((a, b) => String(priceDate(a)).localeCompare(String(priceDate(b))));
    const markers = smaTradeMarkers
      .filter((row) => row.ticker === ticker && row.strategy === strategy)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const { shortWindow, longWindow } = smaWindows(strategy);
    const buyMarkers = markers
      .filter((row) => String(row.action || row.signal).toUpperCase() === 'BUY')
      .map((row) => ({ x: row.date, y: Number(row.price), marker: row }));
    const sellMarkers = markers
      .filter((row) => String(row.action || row.signal).toUpperCase() === 'SELL')
      .map((row) => ({ x: row.date, y: Number(row.price), marker: row }));

    // Chart.js draws higher order values first, so smaller values appear above.
    const LAYERS = {
      price: 30,
      sma: 20,
      signal: 10,
    };

    QTCharts.line('sma-signal-chart', [
      {
        label: `${ticker} 調整後收盤價`,
        data: rows.map((row) => ({ x: priceDate(row), y: row.adj_close })),
        borderColor: '#d8e3ef',
        backgroundColor: 'transparent',
        borderWidth: 1.4,
        pointRadius: 0,
        order: LAYERS.price,
      },
      {
        label: `短期 SMA ${shortWindow}`,
        data: movingAverage(rows, shortWindow),
        borderColor: '#f5b75a',
        backgroundColor: 'transparent',
        borderWidth: 1.2,
        pointRadius: 0,
        order: LAYERS.sma,
      },
      {
        label: `長期 SMA ${longWindow}`,
        data: movingAverage(rows, longWindow),
        borderColor: '#cc8eff',
        backgroundColor: 'transparent',
        borderWidth: 1.2,
        pointRadius: 0,
        order: LAYERS.sma,
      },
      {
        type: 'scatter',
        label: '進場訊號 Buy',
        data: buyMarkers,
        showLine: false,
        pointStyle: 'triangle',
        pointRadius: 6,
        pointHoverRadius: 8,
        pointHitRadius: 10,
        pointBackgroundColor: '#2ecc71',
        pointBorderColor: '#0b0f17',
        pointBorderWidth: 1,
        order: LAYERS.signal,
      },
      {
        type: 'scatter',
        label: '出場訊號 Sell',
        data: sellMarkers,
        showLine: false,
        pointStyle: 'triangle',
        pointRotation: 180,
        pointRadius: 6,
        pointHoverRadius: 8,
        pointHitRadius: 10,
        pointBackgroundColor: '#ff5d6c',
        pointBorderColor: '#0b0f17',
        pointBorderWidth: 1,
        order: LAYERS.signal,
      },
    ], {
      yFormat: (v) => '$' + Number(v).toFixed(0),
      interaction: { mode: 'nearest', intersect: false },
      tooltipCallbacks: {
        title(items) {
          const item = items[0];
          const raw = item && item.raw ? item.raw : {};
          return `日期：${raw.x || item.label}`;
        },
        label(context) {
          const marker = context.raw && context.raw.marker;
          if (!marker) {
            return `${context.dataset.label}：${fmtMoney(context.parsed.y, 2)}`;
          }
          return [
            `策略：${marker.strategy}`,
            `動作：${String(marker.action || marker.signal).toUpperCase()}`,
            `價格：${fmtMoney(marker.price, 2)}`,
            `短期 SMA：${fmtMoney(marker.short_sma, 2)}`,
            `長期 SMA：${fmtMoney(marker.long_sma, 2)}`,
            `權益：${fmtMoney(marker.equity, 2)}`,
            `現金：${fmtMoney(marker.cash_after, 2)}`,
            `股數：${fmtNum(marker.shares_after, 4)}`,
          ];
        },
      },
    });
  }

  function renderNav() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section');
    navItems.forEach((el) => {
      el.addEventListener('click', () => {
        const target = el.dataset.section;
        navItems.forEach((n) => n.classList.toggle('active', n === el));
        sections.forEach((section) => section.classList.toggle('active', section.id === 'section-' + target));
        window.scrollTo({ top: 0 });
      });
    });
  }

  function renderOverview() {
    const dash = D.dashboard || {};
    const start = dash.data_range.start;
    const end = dash.data_range.end;
    const days = Math.round((new Date(end) - new Date(start)) / 86400000);
    const years = (days / 365.25).toFixed(2);

    setText('data-range', `${start} ~ ${end}`);
    setText('dash-range', `${start} ~ ${end}`);
    setText('dash-range-days', `${years} 年 (${days.toLocaleString()} 日曆日)`);
    setText('dash-capital', fmtMoney(dash.initial_capital));
    setText('dash-price-column', `價格欄位：${dash.price_column}`);
    setText('dash-pairs-windows', String(pairTemporalRows.length));

    const dcaRow = perfRows.find((row) => row.ticker === dash.default_stock && row.strategy === 'Fair DCA');
    if (dcaRow) {
      setText('dash-dca-rule', `${fmtMoney(dcaRow.monthly_contribution, 2)} x ${dcaRow.number_of_trades}`);
    }

    const badges = document.getElementById('ticker-badges');
    badges.innerHTML = '';
    (dash.tickers || []).forEach((ticker) => {
      const span = document.createElement('span');
      span.className = 'badge accent';
      span.textContent = ticker;
      badges.appendChild(span);
    });
    
    if (dash.market_benchmark) {
      const spyBadge = document.createElement('span');
      spyBadge.className = 'badge muted';
      spyBadge.textContent = `${dash.market_benchmark}（基準）`;
      badges.appendChild(spyBadge);
    }

    const assumptionWrap = document.getElementById('overview-assumptions');
    const overviewItems = [
      ['資料來源', assumptions.data_source],
      ['股票母體', (assumptions.stock_universe || []).join('、')],
      ['市場基準', assumptions.market_benchmark || 'N/A'],
      ['可交易碎股', String(assumptions.fractional_shares)],
      ['交易成本', assumptions.transaction_costs],
      ['放空', String(assumptions.short_selling)],
      ['訊號執行時機', assumptions.signal_execution_timing],
    ];
    assumptionWrap.innerHTML = '';
    overviewItems.forEach(([label, value]) => {
      const row = document.createElement('div');
      row.className = 'kv-row';
      row.innerHTML = `<span class="k">${label}</span><span class="v">${value}</span>`;
      assumptionWrap.appendChild(row);
    });

    const bhRows = perfRows.filter((row) => row.strategy === 'Buy-and-Hold');
    QTCharts.bar(
      'dash-bh-chart',
      bhRows.map((row) => row.ticker),
      [{
        label: '最終價值',
        data: bhRows.map((row) => row.final_value),
        backgroundColor: bhRows.map((row) => STOCK_COLORS[row.ticker] || '#5aa9ff'),
        borderColor: 'transparent',
      }],
      { yFormat: (v) => '$' + (v / 1000).toFixed(0) + 'k' }
    );

    const tickers = (D.dashboard.tickers || []).slice();
    QTCharts.bar(
      'dash-ann-chart',
      tickers,
      STRATEGIES.map((strategy) => ({
        label: STRATEGY_LABELS[strategy],
        data: tickers.map((ticker) => {
          const row = perfRows.find((item) => item.ticker === ticker && item.strategy === strategy);
          return row ? row.annualized_return : null;
        }),
        backgroundColor: STRATEGY_COLORS[strategy],
        borderColor: 'transparent',
      })),
      { yFormat: (v) => (v * 100).toFixed(0) + '%' }
    );
  }

  function renderStockSummaryTable() {
    const tbody = document.querySelector('#stock-summary-table tbody');
    tbody.innerHTML = '';
    stockSummary.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="text">${row.ticker}</td>
        <td class="text">${row.company_name}</td>
        <td class="text">${row.sector}</td>
        <td>${row.start_date}</td>
        <td>${row.end_date}</td>
        <td>${Number(row.observations).toLocaleString()}</td>
        <td>${fmtMoney(row.first_price, 2)}</td>
        <td>${fmtMoney(row.last_price, 2)}</td>
        <td class="text">${row.data_source}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderStockSection(ticker) {
    const meta = byTicker[ticker];
    const rows = priceRows.filter((row) => row.ticker === ticker);
    setText('stock-meta-ticker', meta.ticker);
    setText('stock-meta-company', meta.company_name);
    setText('stock-meta-sector', meta.sector);
    setText('stock-meta-coverage', `${meta.start_date} ~ ${meta.end_date}`);
    setText('stock-meta-observations', `${Number(meta.observations).toLocaleString()} 筆觀測資料`);

    QTCharts.line('stock-price-chart', [{
      label: `${ticker} 調整後收盤價`,
      data: rows.map((row) => ({ x: row.Date || row.date, y: row.adj_close })),
      borderColor: STOCK_COLORS[ticker] || '#5aa9ff',
      backgroundColor: (STOCK_COLORS[ticker] || '#5aa9ff') + '22',
      fill: true,
    }], { yFormat: (v) => '$' + Number(v).toFixed(0) });

    QTCharts.line('stock-volume-chart', [{
      label: `${ticker} 交易量`,
      data: rows.map((row) => ({ x: row.Date || row.date, y: row.volume })),
      borderColor: STOCK_COLORS[ticker] || '#5aa9ff',
      backgroundColor: (STOCK_COLORS[ticker] || '#5aa9ff') + '44',
      fill: 'origin',
      borderWidth: 0.8,
    }], { yFormat: (v) => (v / 1e6).toFixed(0) + 'M' });
  }

  function renderStrategySection(ticker) {
    const smaSelect = document.getElementById('strategy-sma-select');
    const selectedSmaStrategy = smaSelect ? smaSelect.value : 'SMA 50/200';
    const rows = perfRows.filter((row) => row.ticker === ticker);

    const cards = document.getElementById('strategy-cards');
    cards.innerHTML = '';
    rows.forEach((row) => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <div class="card-label">${STRATEGY_LABELS[row.strategy]}</div>
        <div class="card-value">${fmtMoney(row.final_value)}</div>
        <div class="kpi">
          <div class="kpi-row"><span class="k">總投入</span><span class="v">${fmtMoney(row.total_invested)}</span></div>
          <div class="kpi-row"><span class="k">累計報酬</span><span class="v ${cls(row.cumulative_return)}">${fmtSignedPct(row.cumulative_return)}</span></div>
          <div class="kpi-row"><span class="k">年化報酬</span><span class="v ${cls(row.annualized_return)}">${fmtSignedPct(row.annualized_return)}</span></div>
          <div class="kpi-row"><span class="k">最大回撤</span><span class="v neg">${fmtPct(row.max_drawdown)}</span></div>
          <div class="kpi-row"><span class="k">波動率</span><span class="v">${fmtPct(row.volatility)}</span></div>
          <div class="kpi-row"><span class="k">Sharpe 比率</span><span class="v">${fmtSharpe(row.sharpe_ratio)}</span></div>
          <div class="kpi-row"><span class="k">交易次數</span><span class="v">${row.number_of_trades}</span></div>
        </div>
      `;
      cards.appendChild(card);
    });

    const spyRow = marketBenchmark.find((row) => row.ticker === 'SPY');
    if (spyRow) {
      const spyCard = document.createElement('div');
      spyCard.className = 'card';
      spyCard.style.opacity = '0.8';
      spyCard.style.borderLeft = '3px solid #a0a0a0';
      spyCard.innerHTML = `
        <div class="card-label">SPY 基準</div>
        <div class="card-value">${fmtMoney(spyRow.final_value)}</div>
        <div class="kpi">
          <div class="kpi-row"><span class="k">總投入</span><span class="v">${fmtMoney(spyRow.total_invested)}</span></div>
          <div class="kpi-row"><span class="k">累計報酬</span><span class="v ${cls(spyRow.cumulative_return)}">${fmtSignedPct(spyRow.cumulative_return)}</span></div>
          <div class="kpi-row"><span class="k">年化報酬</span><span class="v ${cls(spyRow.annualized_return)}">${fmtSignedPct(spyRow.annualized_return)}</span></div>
          <div class="kpi-row"><span class="k">最大回撤</span><span class="v neg">${fmtPct(spyRow.max_drawdown)}</span></div>
          <div class="kpi-row"><span class="k">波動率</span><span class="v">${fmtPct(spyRow.volatility)}</span></div>
          <div class="kpi-row"><span class="k">Sharpe 比率</span><span class="v">${fmtSharpe(spyRow.sharpe_ratio)}</span></div>
          <div class="kpi-row"><span class="k">交易次數</span><span class="v">${spyRow.number_of_trades}</span></div>
        </div>
      `;
      cards.appendChild(spyCard);
    }

    const tbody = document.querySelector('#strategy-table tbody');
    tbody.innerHTML = '';
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="text">${STRATEGY_LABELS[row.strategy]}</td>
        <td>${fmtMoney(row.initial_capital)}</td>
        <td>${fmtMoney(row.total_invested)}</td>
        <td>${fmtMoney(row.final_value)}</td>
        <td class="${cls(row.cumulative_return)}">${fmtSignedPct(row.cumulative_return)}</td>
        <td class="${cls(row.annualized_return)}">${fmtSignedPct(row.annualized_return)}</td>
        <td class="${cls(row.excess_annualized_return_vs_spy)}">${fmtSignedPct(row.excess_annualized_return_vs_spy)}</td>
        <td>${row.outperformed_spy ? '是' : '否'}</td>
        <td class="neg">${fmtPct(row.max_drawdown)}</td>
        <td>${fmtPct(row.volatility)}</td>
        <td>${fmtSharpe(row.sharpe_ratio)}</td>
        <td>${row.number_of_trades}</td>
      `;
      tbody.appendChild(tr);
    });

    const curves = equityCurves.filter((row) => row.ticker === ticker);
    const spyEquityCurves = equityCurves.filter((row) => row.ticker === 'SPY' && row.strategy === 'Buy-and-Hold');

    QTCharts.line('strategy-equity-chart',
      STRATEGIES.map((strategy) => ({
        label: STRATEGY_LABELS[strategy],
        data: curves
          .filter((row) => row.strategy === strategy)
          .map((row) => ({ x: row.date, y: row.equity })),
        borderColor: STRATEGY_COLORS[strategy],
        backgroundColor: STRATEGY_COLORS[strategy] + '18',
      })).concat([{
        label: 'SPY 基準',
        data: spyEquityCurves.map((row) => ({ x: row.date, y: row.equity })),
        borderColor: '#a0a0a0',
        backgroundColor: 'transparent',
        borderDash: [5, 5],
        borderWidth: 2,
      }]),
      { yFormat: (v) => '$' + (v / 1000).toFixed(0) + 'k' }
    );

    QTCharts.line('strategy-drawdown-chart',
      STRATEGIES.map((strategy) => ({
        label: STRATEGY_LABELS[strategy],
        data: curves
          .filter((row) => row.strategy === strategy)
          .map((row) => ({ x: row.date, y: row.drawdown })),
        borderColor: STRATEGY_COLORS[strategy],
        backgroundColor: 'transparent',
      })).concat([{
        label: 'SPY 基準',
        data: spyEquityCurves.map((row) => ({ x: row.date, y: row.drawdown })),
        borderColor: '#a0a0a0',
        backgroundColor: 'transparent',
        borderDash: [5, 5],
        borderWidth: 2,
      }]),
      { yFormat: (v) => (v * 100).toFixed(0) + '%' }
    );

    renderSmaSignalChart(ticker, selectedSmaStrategy);
  }

  function renderTemporalSection(ticker, strategy) {
    const rows = sortByWindow(temporalRows.filter((row) => row.ticker === ticker && row.strategy === strategy));

    QTCharts.bar('tv-ann-chart',
      rows.map((row) => row.window_id),
      [{
        label: '年化報酬',
        data: rows.map((row) => row.annualized_return),
        backgroundColor: rows.map((row) => Number(row.annualized_return) >= 0 ? STRATEGY_COLORS[strategy] : '#ff5d6c'),
        borderColor: 'transparent',
      }],
      { yFormat: (v) => (v * 100).toFixed(0) + '%' }
    );

    QTCharts.bar('tv-dd-chart',
      rows.map((row) => row.window_id),
      [{
        label: '最大回撤',
        data: rows.map((row) => row.max_drawdown),
        backgroundColor: '#ff5d6c',
        borderColor: 'transparent',
      }],
      { yFormat: (v) => (v * 100).toFixed(0) + '%' }
    );

    const tbody = document.querySelector('#tv-table tbody');
    tbody.innerHTML = '';
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="text">${row.window_id}</td>
        <td>${row.train_start}</td>
        <td>${row.train_end}</td>
        <td>${row.test_start}</td>
        <td>${row.test_end}</td>
        <td>${fmtMoney(row.final_value)}</td>
        <td class="${cls(row.cumulative_return)}">${fmtSignedPct(row.cumulative_return)}</td>
        <td class="${cls(row.annualized_return)}">${fmtSignedPct(row.annualized_return)}</td>
        <td class="neg">${fmtPct(row.max_drawdown)}</td>
        <td>${fmtPct(row.volatility)}</td>
        <td>${fmtSharpe(row.sharpe_ratio)}</td>
        <td>${row.number_of_trades}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  function renderPairsSection(windowId) {
    const row = pairTemporalRows.find((item) => item.window_id === windowId);
    if (!row) return;

    setText('pair-selected', row.selected_pair);
    setText('pair-period', `訓練 ${row.train_start} 至 ${row.train_end} | 測試 ${row.test_start} 至 ${row.test_end}`);
    setText('pair-corr', fmtNum(row.train_correlation, 4));
    setText('pair-final', fmtMoney(row.final_value));
    setText('pair-returns', `${fmtSignedPct(row.cumulative_return)} 累計 | ${fmtSignedPct(row.annualized_return)} 年化`);
    setText('pair-sharpe', fmtSharpe(row.sharpe_ratio));
    setText('pair-trades', `${row.number_of_trades} 筆完成交易 | 勝率 ${fmtPct(row.win_rate)}`);

    let meanReversionText = row.mean_reversion_comment || '相關性不保證均值回歸。';
    if (row.adf_p_value != null) {
      meanReversionText += ` ADF p-value = ${fmtNum(row.adf_p_value, 4)}。`;
    }
    document.getElementById('pair-mean-reversion-note').textContent = meanReversionText;

    const corrRows = pairWindowCorrelations
      .filter((item) => item.window_id === windowId)
      .sort((a, b) => Number(b.correlation) - Number(a.correlation));
    const corrBody = document.querySelector('#pair-corr-table tbody');
    corrBody.innerHTML = '';
    corrRows.forEach((item) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="text">${item.pair}</td>
        <td class="text">${item.stock_a}</td>
        <td class="text">${item.stock_b}</td>
        <td>${fmtNum(item.correlation, 4)}</td>
      `;
      corrBody.appendChild(tr);
    });

    const curves = pairTemporalCurves.filter((item) => item.window_id === windowId);
    QTCharts.line('pair-spread-chart', [{
      label: row.spread_definition,
      data: curves.map((item) => ({ x: item.date, y: item.spread })),
      borderColor: '#5aa9ff',
      backgroundColor: 'transparent',
    }], { yFormat: (v) => Number(v).toFixed(2) });

    const zData = curves.filter((item) => item.zscore != null).map((item) => ({ x: item.date, y: item.zscore }));
    function constLine(value, color, label, dash) {
      if (!zData.length) return { label, data: [], borderColor: color, pointRadius: 0 };
      return {
        label,
        data: [{ x: zData[0].x, y: value }, { x: zData[zData.length - 1].x, y: value }],
        borderColor: color,
        backgroundColor: 'transparent',
        borderDash: dash,
        borderWidth: 1,
        pointRadius: 0,
      };
    }

    QTCharts.line('pair-zscore-chart', [
      {
        label: 'Z-score',
        data: zData,
        borderColor: '#9ad07a',
        backgroundColor: 'transparent',
      },
      constLine(row.entry_threshold, '#ff5d6c', '進場 +2', [6, 4]),
      constLine(-row.entry_threshold, '#ff5d6c', '進場 -2', [6, 4]),
      constLine(row.exit_threshold, '#f5b75a', '出場 +0.5', [2, 4]),
      constLine(-row.exit_threshold, '#f5b75a', '出場 -0.5', [2, 4]),
      constLine(0, '#6e7c93', '零線', [1, 6]),
    ], { yFormat: (v) => Number(v).toFixed(2) });

    QTCharts.line('pair-equity-chart', [{
      label: '配對組合價值',
      data: curves.map((item) => ({ x: item.date, y: item.portfolio_value })),
      borderColor: '#cc8eff',
      backgroundColor: '#cc8eff18',
      fill: true,
    }], { yFormat: (v) => '$' + (v / 1000).toFixed(1) + 'k' });

    const pairTableBody = document.querySelector('#pair-tv-table tbody');
    pairTableBody.innerHTML = '';
    sortByWindow(pairTemporalRows).forEach((item) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="text">${item.window_id}</td>
        <td>${item.train_start}</td>
        <td>${item.train_end}</td>
        <td>${item.test_start}</td>
        <td>${item.test_end}</td>
        <td class="text">${item.selected_pair}</td>
        <td>${fmtNum(item.train_correlation, 4)}</td>
        <td>${fmtMoney(item.final_value)}</td>
        <td class="${cls(item.cumulative_return)}">${fmtSignedPct(item.cumulative_return)}</td>
        <td class="${cls(item.annualized_return)}">${fmtSignedPct(item.annualized_return)}</td>
        <td class="neg">${fmtPct(item.max_drawdown)}</td>
        <td>${fmtPct(item.volatility)}</td>
        <td>${fmtSharpe(item.sharpe_ratio)}</td>
        <td>${item.number_of_trades}</td>
      `;
      pairTableBody.appendChild(tr);
    });
  }

  function renderSummary() {
    const ranked = perfRows.slice().sort((a, b) => Number(b.annualized_return) - Number(a.annualized_return));
    const tbody = document.querySelector('#summary-rank-table tbody');
    tbody.innerHTML = '';
    ranked.forEach((row, index) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${index + 1}</td>
        <td class="text">${row.ticker}</td>
        <td class="text">${STRATEGY_LABELS[row.strategy]}</td>
        <td>${fmtMoney(row.final_value)}</td>
        <td class="${cls(row.cumulative_return)}">${fmtSignedPct(row.cumulative_return)}</td>
        <td class="${cls(row.annualized_return)}">${fmtSignedPct(row.annualized_return)}</td>
        <td class="neg">${fmtPct(row.max_drawdown)}</td>
        <td>${fmtPct(row.volatility)}</td>
        <td>${fmtSharpe(row.sharpe_ratio)}</td>
        <td>${row.number_of_trades}</td>
      `;
      tbody.appendChild(tr);
    });

    const assumptionsBody = document.querySelector('#assumptions-table tbody');
    assumptionsBody.innerHTML = '';
    Object.entries(assumptions).forEach(([key, value]) => {
      const tr = document.createElement('tr');
      const label = ASSUMPTION_LABELS[key] || key;
      tr.innerHTML = `
        <td class="text">${label}</td>
        <td class="text">${String(value)}</td>
      `;
      assumptionsBody.appendChild(tr);
    });
  }

  function init() {
    renderNav();
    renderOverview();
    renderStockSummaryTable();

    const tickers = stockSummary.map((row) => row.ticker);
    const formalStocks = stockSummary
      .filter((row) => row.asset_type === 'stock')
      .map((row) => row.ticker);

    populateSelect('stock-select', tickers);
    populateSelect('strategy-stock-select', formalStocks);
    populateSelect('strategy-sma-select', SMA_STRATEGIES);
    populateSelect('tv-stock-select', formalStocks);
    populateSelect('tv-strategy-select', STRATEGIES);
    populateSelect('pair-window-select', sortByWindow(pairTemporalRows).map((row) => row.window_id));

    const stockSelect = document.getElementById('stock-select');
    const strategyStockSelect = document.getElementById('strategy-stock-select');
    const strategySmaSelect = document.getElementById('strategy-sma-select');
    const tvStockSelect = document.getElementById('tv-stock-select');
    const tvStrategySelect = document.getElementById('tv-strategy-select');
    const pairWindowSelect = document.getElementById('pair-window-select');

    stockSelect.value = D.dashboard.default_stock;
    strategyStockSelect.value = D.dashboard.default_stock;
    strategySmaSelect.value = D.dashboard.default_sma_strategy || 'SMA 50/200';
    tvStockSelect.value = D.dashboard.default_stock;
    tvStrategySelect.value = D.dashboard.default_temporal_strategy;
    if (D.dashboard.default_pairs_window) pairWindowSelect.value = D.dashboard.default_pairs_window;

    stockSelect.addEventListener('change', () => renderStockSection(stockSelect.value));
    strategyStockSelect.addEventListener('change', () => renderStrategySection(strategyStockSelect.value));
    strategySmaSelect.addEventListener('change', () => renderStrategySection(strategyStockSelect.value));
    tvStockSelect.addEventListener('change', () => renderTemporalSection(tvStockSelect.value, tvStrategySelect.value));
    tvStrategySelect.addEventListener('change', () => renderTemporalSection(tvStockSelect.value, tvStrategySelect.value));
    pairWindowSelect.addEventListener('change', () => renderPairsSection(pairWindowSelect.value));

    renderStockSection(stockSelect.value);
    renderStrategySection(strategyStockSelect.value);
    renderTemporalSection(tvStockSelect.value, tvStrategySelect.value);
    renderPairsSection(pairWindowSelect.value);
    renderSummary();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
