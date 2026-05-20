# Quantitative Trading Backtesting Dashboard 分析結果報告

## 1. Executive Summary

本報告基於 `data/` 資料集與 `data/assumptions.json` 的實際回測結果，評估正式股票母體與五種 Problem 1 策略，以及 Problem 2 的 Pairs Trading 驗證。
研究對象為 5 檔正式股票：`MCD`、`KO`、`AAPL`、`MSFT`、`ORCL`，市場基準為 `SPY`。資料實際涵蓋期間為 `1996-01-02` 到 `2026-05-08`。

Problem 1 中的五個策略為：`Buy-and-Hold`、`Fair DCA`、`SMA 20/60`、`SMA 50/200`、`SMA 100/300`。分析結果顯示，`Buy-and-Hold` 的全樣本平均年化報酬最高，AAPL Buy-and-Hold 以 26.38% 年化領先；`Fair DCA` 提供較低波動與較高 Sharpe Ratio，但在多數個股上仍落後於單次投入的 Buy-and-Hold。三組 SMAStrategy 中，`SMA 100/300` 的平均年化報酬最好、交易次數最少，`SMA 20/60` 交易最多，且最容易受到交易成本影響。

Temporal Validation（750 個測試視窗）表明：`Buy-and-Hold` 穩定性最高，97.3% 測試視窗為正報酬，且 62.7% 期間跑贏 SPY。`Fair DCA` 與 SMA 策略雖然多數情況為正報酬，但只有約 17%~27% 視窗可超越 SPY，代表 Benchmark 仍是重要的機會成本比較標準。

Problem 2 的配對交易僅選出 `MSFT-ORCL`。30 個驗證視窗中平均年化報酬僅 0.18%，中位數為 -0.33%，ADF p-value 範圍 0.176 到 0.736，顯示弱化的均值回歸證據。最大回撤最低可達 -121.32%，這表明長短倉模擬在未考慮保證金、強制平倉、借券成本與交易成本時，風險可能被低估。

本報告強調：
- `SPY` 僅作為 Benchmark，不參與 SMA 訊號與配對交易。
- SMA 策略僅使用個股自身 `Adjusted Close`。
- 同日收盤執行為簡化假設，可能使結果偏向樂觀。
- 本報告僅為研究分析，不構成投資建議。

## 2. 資料與研究設計

### 2.1 Formal Stock Universe

- MCD
- KO
- AAPL
- MSFT
- ORCL

### 2.2 Market Benchmark

- SPY（僅作為基準；不參與 SMA 策略與配對交易）

### 2.3 資料來源與期間

- 資料來源：Yahoo Finance via `yfinance`，或使用快取的 `data/stock_prices.csv`
- `actual_start_date`：1996-01-02
- `actual_end_date`：2026-05-08
- `price_column`：`Adjusted Close`

### 2.4 Stock Summary

| ticker | company_name | sector | asset_type | observations | first_price | last_price |
| --- | --- | --- | --- | --- | --- | --- |
| MCD | McDonald's Corporation | Consumer Cyclical | stock | 7,638 | 11.741809 | 275.750000 |
| KO | The Coca-Cola Company | Consumer Defensive | stock | 7,638 | 8.657427 | 78.419998 |
| AAPL | Apple Inc. | Technology | stock | 7,638 | 0.240419 | 293.050018 |
| MSFT | Microsoft Corporation | Technology | stock | 7,638 | 3.418719 | 415.119995 |
| ORCL | Oracle Corporation | Technology | stock | 7,638 | 2.552572 | 195.949997 |
| SPY | SPDR S&P 500 ETF Trust | Market Benchmark | benchmark | 7,638 | 36.813354 | 737.619995 |

## 3. 回測假設

- 初始資本：USD 10,000。
- Fair DCA：總投入 USD 10,000；每月投入 USD 27.39726，總計 365 個日曆月。
- 允許零股交易（fractional shares）。
- 交易成本：未包含。
- 滑價：未包含。
- 稅費：未包含。
- 借券成本：未包含。
- 現金處理：未刻意計息。
- 風險無風險利率：0.0。
- 執行時機：同日收盤執行（simplified same-day close execution），此假設可能偏樂觀。
- SMA 訊號來源：每檔股票自身的 `Adjusted Close`。
- SPY 用途：僅作為 Benchmark，並不參與 SMA 訊號、Fair DCA 或 Pairs Trading。
- Pairs Trading 假設：僅對正式股票母體進行 pair selection，使用訓練期日報酬相關性，測試期採用 Z-score spread 交易。

## 4. Problem 1 策略方法

### 4.1 Buy-and-Hold

- 在第一個交易日投入 USD 10,000。
- 持有至回測期末，不進行再平衡、不加碼、不減碼。

### 4.2 Fair DCA

- 總投入 USD 10,000。
- 每月投入 USD 27.39726，共 365 個日曆月。
- DCA 與 Buy-and-Hold 的主要差異在於：Buy-and-Hold 將資本一次性投入；Fair DCA 分散進場時點，減少單次進場價格風險，但延遲全部資本投入。

### 4.3 SMA Crossover 策略

- SMA 訊號僅使用該股票自身的 `Adjusted Close`。
- 若 short SMA > long SMA，系統持有該股票；若 short SMA <= long SMA，系統持有現金。
- 不放空、不槓桿。
- SMA 參數為預先定義：
  - `SMA 20/60`：短期、反應快、交易頻繁，容易產生 whipsaw。
  - `SMA 50/200`：中長期經典交叉策略，為折衷型趨勢策略。
  - `SMA 100/300`：長週期，交易較少，較晚發出訊號，可能保留趨勢但錯過快速反轉。

### 4.4 SMA 進出場訊號視覺化

Dashboard 的「策略比較」頁面已新增 SMA 進出場訊號圖。此圖以個股 `Adjusted Close` 為主線，並依使用者選擇顯示 `SMA 20/60`、`SMA 50/200` 或 `SMA 100/300` 的短期 / 長期均線與 BUY / SELL markers。

- `SMA 20/60` 的訊號較頻繁，因此在圖上可直觀看到更多進出場點，也更容易受到 whipsaw、交易成本與滑價影響。
- `SMA 100/300` 的訊號較少，能過濾較多短期雜訊，但進出場反應較慢。
- `SMA 50/200` 是經典中長期交叉策略，但本樣本中未必在所有股票上最佳。
- 此視覺化不改變回測邏輯；SMA 訊號仍只使用個股自身 `Adjusted Close`，`SPY` 仍僅作為 Benchmark。

## 5. Problem 1 整體績效分析

### 5.1 SPY Benchmark

| 指標 | SPY |
| --- | --- |
| final_value | $200,367.50 |
| cumulative_return | 1,903.68% |
| annualized_return | 10.38% |
| max_drawdown | -55.19% |
| volatility | 19.24% |
| Sharpe Ratio | 0.54 |

SPY 在本專案中作為機會成本比較標準。若策略報酬為正但低於 10.38% 年化，則其長期相對吸引力受限。

### 5.2 策略整體排名

以下策略排名前 10 名的年化報酬：

| 排名 | ticker | strategy | annualized_return |
| --- | --- | --- | --- |
| 1 | AAPL | Buy-and-Hold | 26.38% |
| 2 | AAPL | Fair DCA | 21.47% |
| 3 | AAPL | SMA 100/300 | 21.16% |
| 4 | AAPL | SMA 50/200 | 19.28% |
| 5 | AAPL | SMA 20/60 | 19.19% |
| 6 | MSFT | Buy-and-Hold | 17.13% |
| 7 | ORCL | Buy-and-Hold | 15.38% |
| 8 | ORCL | SMA 100/300 | 11.69% |
| 9 | MSFT | SMA 50/200 | 11.26% |
| 10 | MCD | Buy-and-Hold | 10.96% |

- AAPL 策略佔據前五名，表明該股票在本樣本期間具有最強勢的長期上漲趨勢。
- Buy-and-Hold 仍是排名最穩定的策略，前十名中出現 4 次。
- SMA 策略中，只有 `SMA 100/300` 與 `SMA 50/200` 在少數個股上接近或超越 Buy-and-Hold。
- 若年化報酬低於 SPY，策略雖可能賺錢，但相對於基準的機會成本仍較高。

### 5.3 Buy-and-Hold vs Fair DCA

- `AAPL`：Buy-and-Hold 26.38% > Fair DCA 21.47%。
- `MSFT`：Buy-and-Hold 17.13% > Fair DCA 9.99%。
- `ORCL`：Buy-and-Hold 15.38% > Fair DCA 9.14%。
- `MCD`：Buy-and-Hold 10.96% > Fair DCA 7.48%。
- `KO`：Buy-and-Hold 7.53% > Fair DCA 4.71%。

雖然 Fair DCA 在資金分批投入時可降低短期風險，但在本資料集中遇到長期上漲的個股時，延遲投入使其累積報酬低於一次投入的 Buy-and-Hold。

### 5.4 三種 SMA 策略比較

| strategy | average annualized_return | average max_drawdown | average volatility | average sharpe_ratio | average number_of_trades |
| --- | --- | --- | --- | --- | --- |
| SMA 100/300 | 10.55% | -61.94% | 25.24% | 0.39 | 24.2 |
| SMA 20/60 | 8.69% | -60.52% | 22.84% | 0.36 | 145.0 |
| SMA 50/200 | 8.25% | -63.88% | 23.41% | 0.33 | 44.2 |

- `SMA 100/300` 的平均年化報酬最高，交易最少，適合偏向長期趨勢保留的設計。
- `SMA 20/60` 交易最多（平均 145 次），因此最容易受交易成本與滑價影響。
- `SMA 50/200` 的平均報酬最低，且中位數表現較差，並沒有在本樣本中呈現明顯的穩健折衷優勢。
- `SMA 100/300` 在 ORCL 上相對優勢明顯；在 MSFT 上則不如 `SMA 50/200` 穩定。

### 5.5 與 SPY Benchmark 比較

在 `strategy_performance.csv` 中，跑贏 SPY 的策略如下：

- AAPL：全部 5 種策略均優於 SPY。
- MCD：僅 Buy-and-Hold 超越 SPY。
- MSFT：Buy-and-Hold 與 SMA 50/200 超越 SPY。
- ORCL：Buy-and-Hold 與 SMA 100/300 超越 SPY。
- KO：無任何策略超越 SPY。

這說明即使策略報酬為正，若未超越 SPY，長期機會成本仍需慎重考量。

## 6. 個股層級分析

### 6.1 MCD

- Buy-and-Hold：最終價值 $234,844.56，累積報酬 22.48%，年化報酬 10.96%，最大回撤 -73.63%，Sharpe 0.47。
- Fair DCA：年化 7.48%，Sharpe 0.54，風險較低但報酬不足。
- SMA 100/300：年化 7.12%，最大回撤 -52.33%。
- SMA 20/60：年化 6.55%。
- SMA 50/200：年化 4.35%。

只有 Buy-and-Hold 勝過 SPY。MCD 的 SMA 策略回撤仍高，顯示趨勢交叉在此防禦型標的上效果有限。

### 6.2 KO

- KO Buy-and-Hold 年化 7.53%，Sharpe 0.35。
- KO Fair DCA 年化 4.71%，Sharpe 0.41。
- 三組 SMA 年化皆低於 5%。

KO 在本資料集中呈現低報酬、低波動的典型防禦型特徵，但無一策略能跑贏 SPY。

### 6.3 AAPL

- Buy-and-Hold 年化 26.38%，累積報酬 1,217.92%，Sharpe 0.63。
- Fair DCA 年化 21.47%，Sharpe 0.81。
- SMA 100/300 年化 21.16%。
- SMA 50/200 年化 19.28%。
- SMA 20/60 年化 19.19%。

AAPL 是本樣本最強標的，且所有策略皆超過 SPY。此類高成長標的讓一次性投入的 Buy-and-Hold 優勢最為明顯。

### 6.4 MSFT

- Buy-and-Hold 年化 17.13%，Sharpe 0.56。
- SMA 50/200 年化 11.26%，Sharpe 0.49。
- Fair DCA 年化 9.99%。
- SMA 100/300 年化 9.53%。
- SMA 20/60 年化 7.45%。

MSFT 的 Buy-and-Hold 仍最強；`SMA 50/200` 為唯一非 Buy-and-Hold 策略可超越 SPY。

### 6.5 ORCL

- Buy-and-Hold 年化 15.38%。
- SMA 100/300 年化 11.69%。
- Fair DCA 年化 9.14%。
- SMA 20/60 年化 7.84%。
- SMA 50/200 年化 4.32%。

ORCL 的 `SMA 100/300` 表現相對優於其他 SMA 參數，這也解釋了其在 Pairs Trading 中作為 MSFT 配對標的的合理性。

## 7. Temporal Validation 分析

### 7.1 設計說明

- 使用擴增視窗（expanding window），不採隨機拆分。
- 每個視窗保留訓練期與測試期的時間順序，避免前視偏誤。
- 策略參數為預先定義，未依測試期調整。
- `temporal_validation.csv` 含 750 個測試記錄：30 個視窗 × 5 策略 × 5 股票。

### 7.2 各策略穩定性

| strategy | avg ann | median ann | std ann | positive windows | outperform SPY |
| --- | --- | --- | --- | --- | --- |
| Buy-and-Hold | 15.72% | 14.43% | 9.76% | 97.33% | 62.67% |
| Fair DCA | 9.80% | 9.46% | 8.17% | 96.00% | 24.67% |
| SMA 100/300 | 9.24% | 8.60% | 10.83% | 91.33% | 27.33% |
| SMA 20/60 | 8.68% | 7.65% | 7.03% | 96.00% | 17.33% |
| SMA 50/200 | 7.38% | 4.81% | 9.41% | 87.33% | 26.67% |

- `Buy-and-Hold` 在測試視窗中最穩定，正報酬比率最高。
- `Fair DCA` 具有高正報酬比率，但超越 SPY 的機率僅 24.7%。
- `SMA 20/60` 雖然正報酬視窗多，但超越 SPY 的比例最低，顯示其交易成本敏感度較高。
- `SMA 50/200` 的中位數表現最低，未呈現可靠的折衷優勢。

### 7.3 各股票 Temporal Validation 現況

- `AAPL` 表現最穩定：`Buy-and-Hold` 100% 正報酬，93.33% 視窗超越 SPY。
- `KO` 雖然多數視窗為正報酬，但僅 6.67% 視窗超越 SPY。
- `ORCL` 的 Fair DCA 具有 100% 正報酬視窗，但超越 SPY 的機率僅 16.67%。
- `MSFT` 中，`Buy-and-Hold` 有 80% 驗證視窗超越 SPY；`SMA 50/200` 也達 56.67%。

### 7.4 Temporal Validation 的影響

- 全樣本優勢不等於 out-of-sample 穩定性。
- Temporal Validation 揭示：少數策略在本樣本期間仍可能被 SPY 超越。
- 若策略全樣本報酬強，但驗證視窗不穩，則應以謹慎態度評估其實盤可行性。

## 8. Problem 2 Pairs Trading 分析

### 8.1 Pair Selection

- 只使用正式股票母體：`MCD`、`KO`、`AAPL`、`MSFT`、`ORCL`。
- `SPY` 不參與配對選擇。
- 以訓練期日報酬相關性選 pair，`pair_correlations.csv` 顯示 10 個候選配對。

前幾名 full-sample pair correlation：

| pair | correlation |
| --- | --- |
| MSFT-ORCL | 0.48918 |
| AAPL-MSFT | 0.42941 |
| MCD-KO | 0.37557 |
| AAPL-ORCL | 0.35935 |
| KO-MSFT | 0.30512 |

- `MSFT-ORCL` 為最高相關配對。
- 相關性不等同於 mean reversion；相關配對仍需進一步 cointegration 測試。

### 8.2 Pairs Trading 回測結果

`pairs_temporal_validation.csv` 顯示：

- 所有 30 個驗證視窗均選出 `MSFT-ORCL`。
- 訓練期相關性範圍：0.38233 至 0.50010。
- 測試期 final_value 範圍：$1,174.12 至 $14,351.56。
- 測試期 cumulative_return 範圍：-88.26% 至 43.52%。
- 測試期 annualized_return 範圍：-7.54% 至 7.06%。
- 測試期 max_drawdown 範圍：-121.32% 至 -4.16%。
- win_rate 範圍：65.17% 至 100%。
- number_of_trades 範圍：1 至 120。

整體結果為：

- 平均 annualized_return 0.18%。
- 中位數 annualized_return -0.33%。
- 平均 max_drawdown -44.05%。
- 平均 Sharpe Ratio 0.08。

若 max_drawdown 低於 -100%，這反映 long-short equity 的模擬結果在未考慮保證金限制、強制平倉與借券成本時，可能會出現低於初始資本的損失。

### 8.3 Mean Reversion / ADF 分析

- ADF p-value 範圍：0.176 到 0.736，平均約 0.457。
- 由於沒有 p-value 低於 0.05，均值回歸的統計證據較弱。
- `mean_reversion_comment` 也指出 ADF p-value >= 0.05，表示未能確認強 stationarity。

### 8.4 Pairs Trading 結論

- 相關性選 pair 是一種合理的初步篩選方式，但不足以保證 spread 會 mean revert。
- `MSFT-ORCL` 即使在相關性最高時仍未展現穩定的正報酬。
- Pairs Trading 的測試結果提醒：若績效不佳，這是策略設計與風險管理的重要發現。
- 未來應加入 cointegration 測試、OLS hedge ratio、stop-loss、交易成本與借券成本模擬。

## 9. 研究限制

- 样本僅限 5 檔股票。
- SPY 為 ETF Benchmark，非策略標的。
- 未包含交易成本、滑價、稅金、借券成本。
- 同日收盤執行為簡化假設，可能偏樂觀。
- 假設可買賣零股。
- 現金未計息。
- risk-free rate = 0。
- SMA 只有三組預先定義參數，未進行 walk-forward 參數優化。
- Pairs Trading 僅以 correlation 選 pair，未使用 cointegration 或 OLS hedge ratio。
- 未模擬保證金限制、強制平倉、stop-loss。
- 過去績效不代表未來。

## 10. 未來改進方向

- 改為 next-day execution。
- 加入 transaction costs、slippage、tax model。
- 模擬 borrowing costs 與 margin requirements。
- 納入 cash interest 或 risk-free rate。
- 進行 transaction cost sensitivity analysis。
- 研究 SMA walk-forward parameter selection。
- 擴大股票母體與 sector ETF benchmark。
- 加入 equal-weight portfolio benchmark。
- Pairs Trading 引入 cointegration test 與 OLS hedge ratio spread。
- 設計 stop-loss / risk management 規則。
- 考慮 regime-based analysis。

## 11. 最終結論

- 本專案遵循正式研究設計：5 檔股票、SPY Benchmark、5 個 Problem 1 策略、30 個 Pairs Trading 時間驗證視窗。
- Problem 1 中，`Buy-and-Hold` 為最穩定策略；`AAPL` 是最強個股。
- `Fair DCA` 表現較為平滑，但在長期上漲個股仍落後一次性投入。
- 三組 SMA 中，`SMA 100/300` 的平均年化報酬最好，`SMA 20/60` 交易最多，`SMA 50/200` 並未明顯呈現最穩健折衷。
- `SPY` Benchmark 提供重要機會成本比較：若策略未跑贏 SPY，長期相對吸引力受限。
- Pairs Trading 的實驗結果顯示，僅憑 correlation 選 pair 並不足以保證穩定獲利，且無成本條件下的回撤風險仍需謹慎評估。

本報告僅供研究分析，不構成投資建議。
