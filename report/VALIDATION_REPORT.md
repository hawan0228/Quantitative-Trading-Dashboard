# Validation Report — Quantitative Trading Backtesting Dashboard

此文件總結專案清理後，針對正式研究設計所執行的驗證檢查結果。

驗證重點

- 股票母體：MCD、KO、AAPL、MSFT、ORCL — 已確認（5 檔股票）。
- 市場基準：SPY — 已確認；SPY 已排除於配對交易之外。
- 請求資料期間：1996-01-02 到 2026-05-11；實際資料期間為 1996-01-02 到 2026-05-08。`data/stock_prices.csv` 作為快取來源。
- 已實作策略（Problem 1）：Buy-and-Hold、Fair DCA、SMA 20/60、SMA 50/200、SMA 100/300（每檔股票 USD 10,000 資本）。
- 策略績效資料列數：25 列（5 檔股票 × 5 策略）— 已確認。
- 市場基準：`data/market_benchmark.csv` 含 SPY Buy-and-Hold — 已確認。
- 時間驗證：`data/temporal_validation.csv` 已產生擴增視窗輸出，涵蓋全部 5 個策略 — 已確認。
- 配對交易：僅針對 5 檔股票母體進行配對選擇與時間驗證；`data/pair_correlations.csv` 含 10 對配對 — 已確認。
- 已從活躍輸出與儀表板/假設檔中移除舊有相對動量策略。
- 假設已說明 SMA 訊號僅基於每檔股票自身的調整後收盤價，且 SPY 僅作為基準使用。
- `data/sma_trade_markers.csv` 已產生，僅包含 `SMA 20/60`、`SMA 50/200`、`SMA 100/300` 的 BUY / SELL 交易點。
- Dashboard「策略比較」頁面已新增 SMA Buy / Sell markers 圖，支援切換三組 SMA 策略。
- 已確認 SPY 不出現在 SMA trade markers，且 Momentum / 12M Relative Momentum 舊策略不出現在 SMA trade markers。
- `data_bundle.js` 僅內嵌輕量化 `sma_trade_markers` 供前端使用，避免加入每日 HOLD 訊號。

已重新生成的檔案

- `data/stock_prices.csv`（使用快取）
- `data/stock_summary.csv`
- `data/strategy_performance.csv`（25 列）
- `data/equity_curves.csv`
- `data/strategy_signals.csv`
- `data/sma_trade_markers.csv`
- `data/temporal_validation.csv`
- `data/pair_correlations.csv`（10 對）
- `data/pairs_window_correlations.csv`
- `data/pairs_temporal_validation.csv`
- `data/pairs_temporal_curves.csv`
- `data/pairs_temporal_signals.csv`
- `data/market_benchmark.csv`
- `data/assumptions.json`
- `data/dashboard.json`
- `data/data_bundle.js`

自動檢查

1. `generate_data.py` Python 語法檢查 — 通過。
2. 執行 `python generate_data.py`，使用快取的 `data/stock_prices.csv` 重新生成資料輸出。
3. 驗證 `strategy_performance.csv` 行數等於 25。
4. 驗證 `stock_summary.csv` 行數等於 6（5 檔股票 + SPY）。
5. 確認 `data/assumptions.json` 包含 `actual_start_date` 與 `actual_end_date`。
6. 驗證 `sma_trade_markers.csv` 欄位包含 `date`、`ticker`、`strategy`、`action`、`price`、`short_sma`、`long_sma`，且 `action` 僅為 `BUY` / `SELL`。
7. 驗證 SMA trade markers 只包含正式股票母體，不含 `SPY`、`Buy-and-Hold`、`Fair DCA` 或 Momentum 舊策略。
8. 驗證 `data_bundle.js` 大小沒有明顯惡化：目前約 90.88 MB，且已改為前端使用 `sma_trade_markers`，不再內嵌完整 `strategy_signals` key。
9. 執行 `python _smoketest.py`，Dashboard 各頁面與所有 canvas 均成功繪製，包含新增的 `sma-signal-chart`。
10. 以 Playwright 額外檢查「策略比較」頁，切換股票至 `MSFT`、SMA 策略至 `SMA 100/300` 後，價格線、SMA 100、SMA 300、Buy markers、Sell markers 均存在，且 tooltip callback 已掛載。
11. 驗證 `pair_correlations.csv` 包含 10 對配對，且不含 SPY。
12. 驗證 `pairs_window_correlations.csv`、`pairs_temporal_validation.csv`、`pairs_temporal_curves.csv`、`pairs_temporal_signals.csv` 已生成，且僅包含 5 檔股票母體的配對資料。

補充說明與後續確認

- 管線使用了快取的 `data/stock_prices.csv`。若需要重新下載網路資料，請執行 `python generate_data.py --refresh`（需安裝 `yfinance`）。
- 某些舊有資料檔案（較早的配對輸出與 legacy `data/stock_metadata.json`）曾保留於專案中；目前已移除未被引用者。若您仍依賴任一自訂舊檔案，請明確重新生成。

結論

專案已清理至正式課程設計：五檔股票、SPY 作為基準、五個 Problem 1 策略、擴增視窗時間驗證，以及配對交易僅限於五檔股票母體。資料工件與儀表板元資料已更新並重生成。
