# Quantitative Trading Backtesting Dashboard — Course Project

此儲存庫為一個可重現的課程專案，用於評估簡單股票投資規則與配對交易驗證，並針對正式股票母體呈現報告式儀表板。

正式設計摘要：

- 正式股票母體：MCD、KO、AAPL、MSFT、ORCL
- 市場基準：SPY（僅作為基準；不納入配對交易）
- 請求資料期間：1996-01-02 到 2026-05-19
- yfinance 下載 end 參數：2026-05-20（因 end 為 exclusive）
- 每檔股票/策略初始資本：USD 10,000

問題定義：

1. Problem 1 — 單一股票回測（每檔股票資本 USD 10,000）
   - Buy-and-Hold
   - Fair DCA（總投入 USD 10,000，月度投入 = 10000 / N 月）
   - SMA 20/60 交叉策略
   - SMA 50/200 交叉策略
   - SMA 100/300 交叉策略

2. Problem 2 — 配對交易驗證
   - 股票母體：MCD、KO、AAPL、MSFT、ORCL（不含 SPY）
   - 使用訓練期日報酬相關性進行配對選擇
   - Z-score 價差交易：60 日視窗，進場 |z|>=2，出場 |z|<0.5
   - 等額多空部位 (50%/50%)

關鍵假設與重現性：

- 所有結果皆由 `generate_data.py` 生成。請勿手動編輯 CSV/JSON 數值。
- 管線支援離線模式：若存在，會使用快取的 `data/stock_prices.csv`；如需重下載，請加上 `--refresh`。
- 假設可買賣零股；不包含交易成本、滑價、稅金或借貸成本。
- SPY 嚴格作為基準，並排除於配對交易與配對選擇之外。
- SMA 參數（20/60、50/200、100/300）為預先定義的代表性周期，未在測試資料上優化。
- 時間驗證採用擴增視窗（無隨機拆分），以避免前視偏誤。
- 若 yfinance 多重下載漏掉個別股票，腳本會嘗試逐一重試並在必要時跳過缺失的價格序列。

安裝 Python 依賴：

```bash
python -m pip install -r requirements.txt
```

重新生成資料與執行儀表板

1. 先檢查語法：

```bash
python -m py_compile generate_data.py
```

2. 生成資料（若已有快取價格則直接使用）：

```bash
python generate_data.py
# 或從 Yahoo Finance 重新下載：
python generate_data.py --refresh
```

3. 本機啟動儀表板並於瀏覽器開啟：

```bash
python -m http.server 8000
# 然後訪問 http://localhost:8000
```

## SMA 進出場訊號視覺化

Dashboard 在「策略比較」頁面新增 SMA 進出場圖。Buy marker 表示 SMA short > SMA long 後策略進場，Sell marker 表示 SMA short <= SMA long 後策略出場；圖表同時顯示個股 Adjusted Close price 與所選 SMA 策略的短期 / 長期均線。此功能只用於視覺化，不改變回測邏輯、績效計算或交易判斷。

SMA 訊號只使用個股自身 Adjusted Close price，SPY 不參與訊號。前端使用輕量化的 `data/sma_trade_markers.csv` / `data_bundle.js` 中的 `sma_trade_markers`，只包含 BUY / SELL 交易點，不包含每日 HOLD。

主要輸出檔案（`data/`）：

- `stock_prices.csv` — MCD、KO、AAPL、MSFT、ORCL、SPY 的 OHLCV / 調整後價格
- `stock_summary.csv` — 6 列（5 檔股票 + SPY）
- `market_benchmark.csv` — SPY Buy-and-Hold 基準結果
- `strategy_performance.csv` — 25 列（5 檔股票 × 5 個策略）
- `equity_curves.csv` — 所有策略的日度權益曲線
- `strategy_signals.csv` — DCA 與 SMA 交易訊號
- `sma_trade_markers.csv` — Dashboard 使用的 SMA BUY / SELL 進出場標記
- `temporal_validation.csv` — 擴增視窗驗證輸出
- `pair_correlations.csv` — 10 對配對（正式 5 檔股票母體）
- `pairs_window_correlations.csv`、`pairs_temporal_validation.csv`、`pairs_temporal_curves.csv`、`pairs_temporal_signals.csv` — 配對交易輸出
- `assumptions.json`、`dashboard.json`、`data_bundle.js`
- `temporal_validation_robustness.csv`
- `pairs_temporal_robustness.csv`

解讀與限制

- 此專案屬於教育用途，並非實時交易系統。
- 未建模交易成本、滑價或稅金；結果可能偏向樂觀。
- SMA 訊號使用 shift(1) 先前可用指標，以避免當日收盤同日交易的前視偏誤。
- 配對交易使用訓練期估計的 hedge ratio。測試期 z-score 使用測試期間截至前一日可得的 rolling spread statistics，並以 shift(1) 的 prior z-score 生成交易訊號，以降低前視偏誤。
- 配對交易選擇僅基於訓練期相關性；相關性不保證均值回歸。
- 樣本期間影響結論；過去績效不代表未來報酬。

若重新生成資料後仍發現舊策略或舊股票代碼的遺留參考，請執行 `python generate_data.py --refresh` 並重新開啟儀表板。欲進一步修改，請參考 `generate_data.py`（主要資料生成與回測邏輯）。
