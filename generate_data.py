"""
Generate the data bundle for the Quantitative Trading dashboard.

Formal specifications:
- Stock universe: MCD, KO, AAPL, MSFT, ORCL (5 stocks)
- Market benchmark: SPY (not part of pairs trading)
- Data target period: 1996-01-02 through 2026-05-19
- yfinance download end date: 2026-05-20 because yfinance end is exclusive
- Strategies: Buy-and-Hold, Fair DCA, SMA 20/60, SMA 50/200, SMA 100/300, SPY Buy-and-Hold
- Pairs trading: Only 5 formal stocks, SPY excluded

This script is offline-friendly: if data/stock_prices.csv exists, it is reused by default.
Otherwise prices are downloaded via yfinance with --refresh flag.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None

try:
    from statsmodels.tsa.stattools import adfuller
except Exception:  # pragma: no cover - optional dependency
    adfuller = None


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PRICE_CACHE = DATA_DIR / "stock_prices.csv"

# Stock universe: 5 formal stocks for strategy & pairs
STOCK_UNIVERSE = ["MCD", "KO", "AAPL", "MSFT", "ORCL"]
STOCK_INFO = {
    "MCD": {"name": "McDonald's Corporation", "sector": "Consumer Cyclical"},
    "KO": {"name": "The Coca-Cola Company", "sector": "Consumer Defensive"},
    "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
    "MSFT": {"name": "Microsoft Corporation", "sector": "Technology"},
    "ORCL": {"name": "Oracle Corporation", "sector": "Technology"},
}

# Market benchmark (not in pairs universe)
MARKET_BENCHMARK = "SPY"
MARKET_INFO = {
    "SPY": {"name": "SPDR S&P 500 ETF Trust", "sector": "Market Benchmark"},
}

# All tickers for data download
ALL_TICKERS = STOCK_UNIVERSE + [MARKET_BENCHMARK]

# Data period
REQUESTED_START_DATE = "1996-01-02"
REQUESTED_TARGET_END_DATE = "2026-05-19"
YFINANCE_END_DATE = "2026-05-20"
REQUESTED_END_DATE = YFINANCE_END_DATE  # legacy alias for yfinance download end

PRICE_COLUMN = "Adj Close"
INITIAL_CAPITAL = 10_000.0
TRADING_DAYS = 252
SMA_SHORT_WINDOW = 50
SMA_LONG_WINDOW = 200
PAIR_ZSCORE_WINDOW = 60
PAIR_ENTRY_THRESHOLD = 2.0
PAIR_EXIT_THRESHOLD = 0.5
TEMPORAL_VALIDATION_METHOD = "expanding_window_all_future_test"
PAIR_SELECTION_METHOD = "training_period_correlation_ranking"

SMA_STRATEGIES = [
    {"name": "SMA 20/60", "short_window": 20, "long_window": 60},
    {"name": "SMA 50/200", "short_window": 50, "long_window": 200},
    {"name": "SMA 100/300", "short_window": 100, "long_window": 300},
]


@dataclass
class Performance:
    initial_capital: float
    total_invested: float
    final_value: float
    cumulative_return: float
    annualized_return: float | None
    max_drawdown: float
    volatility: float
    sharpe_ratio: float | None

    def as_row(self) -> dict[str, float | None]:
        return {
            "initial_capital": round(self.initial_capital, 2),
            "total_invested": round(self.total_invested, 2),
            "final_value": round(self.final_value, 2),
            "cumulative_return": round(self.cumulative_return, 6),
            "annualized_return": None if self.annualized_return is None else round(self.annualized_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "volatility": round(self.volatility, 6),
            "sharpe_ratio": None if self.sharpe_ratio is None else round(self.sharpe_ratio, 6),
        }


@dataclass
class StrategyResult:
    equity: pd.Series
    cash: pd.Series
    asset_value: pd.Series
    units: pd.Series
    signals: pd.DataFrame
    total_invested: float
    number_of_trades: int
    strategy_notes: str = ""


def to_float(value: float) -> float:
    return float(np.round(value, 10))


def nullable_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def perf_metrics(equity: pd.Series, total_invested: float, initial_capital: float) -> Performance:
    equity = equity.dropna().astype(float)
    if equity.empty:
        return Performance(initial_capital, total_invested, initial_capital, 0.0, 0.0, 0.0, 0.0, None)

    final_value = float(equity.iloc[-1])
    cumulative_return = final_value / total_invested - 1.0 if total_invested > 0 else 0.0

    days = max((equity.index[-1] - equity.index[0]).days, 1)
    years = days / 365.25
    ratio = final_value / total_invested if total_invested > 0 else float("nan")
    if total_invested > 0 and years > 0 and ratio > 0:
        annualized_return = ratio ** (1.0 / years) - 1.0
    elif total_invested > 0 and years > 0:
        annualized_return = None
    else:
        annualized_return = None

    daily_returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    volatility = float(daily_returns.std() * math.sqrt(TRADING_DAYS)) if not daily_returns.empty else 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    sharpe_ratio = None if annualized_return is None or volatility <= 1e-12 else annualized_return / volatility
    return Performance(initial_capital, total_invested, final_value, cumulative_return, annualized_return, max_drawdown, volatility, sharpe_ratio)


def drawdown_series(equity: pd.Series) -> pd.Series:
    equity = equity.astype(float)
    running_max = equity.cummax()
    return equity / running_max - 1.0


def load_prices(refresh: bool = False) -> pd.DataFrame:
    if PRICE_CACHE.exists() and not refresh:
        print(f"Loading cached prices from {PRICE_CACHE.name} ...")
        df = pd.read_csv(PRICE_CACHE, parse_dates=["Date"])
        return normalize_prices(df)

    if yf is None:
        raise RuntimeError("yfinance is not installed and no cached stock_prices.csv file is available.")

    print(
        f"Downloading {ALL_TICKERS} from {REQUESTED_START_DATE} to {YFINANCE_END_DATE} "
        f"(target coverage through {REQUESTED_TARGET_END_DATE}) ..."
    )
    raw = yf.download(
        ALL_TICKERS,
        start=REQUESTED_START_DATE,
        end=YFINANCE_END_DATE,
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    missing_tickers = [ticker for ticker in ALL_TICKERS if ticker not in raw.columns.get_level_values(0)]
    if missing_tickers:
        print(f"Warning: Missing price data for {missing_tickers}. Attempting individual downloads...")
        for ticker in missing_tickers:
            try:
                single_raw = yf.download(
                    ticker,
                    start=REQUESTED_START_DATE,
                    end=YFINANCE_END_DATE,
                    auto_adjust=False,
                    progress=False,
                    group_by="ticker",
                    threads=False,
                )
            except Exception as exc:
                print(f"  Failed individual download for {ticker}: {exc}")
                continue

            if isinstance(single_raw.columns, pd.MultiIndex) and ticker in single_raw.columns.get_level_values(0):
                raw = pd.concat([raw, single_raw], axis=1)
            elif not isinstance(single_raw.columns, pd.MultiIndex):
                single_raw.columns = pd.MultiIndex.from_product([[ticker], single_raw.columns])
                raw = pd.concat([raw, single_raw], axis=1)
            else:
                print(f"  Individual download did not return expected columns for {ticker}.")

        missing_tickers = [ticker for ticker in ALL_TICKERS if ticker not in raw.columns.get_level_values(0)]
        if missing_tickers:
            print(f"  Still missing price data for {missing_tickers} after individual retry.")

    frames = []
    for ticker in ALL_TICKERS:
        if ticker not in raw.columns.get_level_values(0):
            print(f"Warning: Missing price data for {ticker}")
            continue
        frame = raw[ticker].copy().dropna(how="all")
        frame["Symbol"] = ticker
        frame = frame.reset_index()
        frame = frame[["Date", "Symbol", "Open", "High", "Low", "Close", "Adj Close", "Volume"]]
        frames.append(frame)

    df = pd.concat(frames, ignore_index=True)
    df = normalize_prices(df)
    df.to_csv(PRICE_CACHE, index=False)
    print(f"Cached prices to {PRICE_CACHE.name}")
    return df


def normalize_prices(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
    out = out.sort_values(["Symbol", "Date"]).reset_index(drop=True)
    numeric_cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def build_stock_summary(prices_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    
    # Add formal 5 stocks
    for ticker in STOCK_UNIVERSE:
        subset = prices_df[prices_df["Symbol"] == ticker].copy()
        if subset.empty:
            continue
        rows.append({
            "ticker": ticker,
            "company_name": STOCK_INFO[ticker]["name"],
            "sector": STOCK_INFO[ticker]["sector"],
            "asset_type": "stock",
            "start_date": subset["Date"].min().strftime("%Y-%m-%d"),
            "end_date": subset["Date"].max().strftime("%Y-%m-%d"),
            "observations": int(len(subset)),
            "first_price": round(float(subset.iloc[0][PRICE_COLUMN]), 6),
            "last_price": round(float(subset.iloc[-1][PRICE_COLUMN]), 6),
            "data_source": "Yahoo Finance via yfinance",
        })
    
    # Add market benchmark
    subset = prices_df[prices_df["Symbol"] == MARKET_BENCHMARK].copy()
    if not subset.empty:
        rows.append({
            "ticker": MARKET_BENCHMARK,
            "company_name": MARKET_INFO[MARKET_BENCHMARK]["name"],
            "sector": MARKET_INFO[MARKET_BENCHMARK]["sector"],
            "asset_type": "benchmark",
            "start_date": subset["Date"].min().strftime("%Y-%m-%d"),
            "end_date": subset["Date"].max().strftime("%Y-%m-%d"),
            "observations": int(len(subset)),
            "first_price": round(float(subset.iloc[0][PRICE_COLUMN]), 6),
            "last_price": round(float(subset.iloc[-1][PRICE_COLUMN]), 6),
            "data_source": "Yahoo Finance via yfinance",
        })
    
    return pd.DataFrame(rows)


def first_trading_day_each_month(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    periods = pd.Series(index=index, data=index.to_period("M"))
    return list(periods.groupby(periods).head(1).index)


def strategy_buy_and_hold(prices: pd.Series, initial_capital: float = INITIAL_CAPITAL) -> StrategyResult:
    prices = prices.dropna().astype(float)
    if prices.empty:
        return StrategyResult(
            equity=pd.Series([], dtype=float, name="equity"),
            cash=pd.Series([], dtype=float, name="cash"),
            asset_value=pd.Series([], dtype=float, name="asset_value"),
            units=pd.Series([], dtype=float, name="units"),
            signals=pd.DataFrame([], columns=["date", "signal", "price", "shares", "cash_after"]),
            total_invested=0.0,
            number_of_trades=0,
            strategy_notes="No price data available.",
        )
    shares = initial_capital / prices.iloc[0]
    asset_value = prices * shares
    cash = pd.Series(0.0, index=prices.index, name="cash")
    units = pd.Series(shares, index=prices.index, name="units")
    signals = pd.DataFrame([{
        "date": prices.index[0],
        "signal": "BUY",
        "action": "BUY",
        "price": float(prices.iloc[0]),
        "shares": float(shares),
        "cash_after": 0.0,
    }])
    return StrategyResult(
        equity=asset_value.rename("equity"),
        cash=cash,
        asset_value=asset_value.rename("asset_value"),
        units=units,
        signals=signals,
        total_invested=initial_capital,
        number_of_trades=1,
        strategy_notes="Fractional shares allowed. USD 10,000 invested on first trading day.",
    )


def strategy_dca(prices: pd.Series, total_invested: float = INITIAL_CAPITAL) -> StrategyResult:
    prices = prices.dropna().astype(float)
    if prices.empty:
        return StrategyResult(
            equity=pd.Series([], dtype=float, name="equity"),
            cash=pd.Series([], dtype=float, name="cash"),
            asset_value=pd.Series([], dtype=float, name="asset_value"),
            units=pd.Series([], dtype=float, name="units"),
            signals=pd.DataFrame([], columns=["date", "signal", "price", "shares", "contribution", "cash_after"]),
            total_invested=0.0,
            number_of_trades=0,
            strategy_notes="No price data available.",
        )
    invest_dates = first_trading_day_each_month(prices.index)
    if not invest_dates:
        return StrategyResult(
            equity=pd.Series([], dtype=float, name="equity"),
            cash=pd.Series([], dtype=float, name="cash"),
            asset_value=pd.Series([], dtype=float, name="asset_value"),
            units=pd.Series([], dtype=float, name="units"),
            signals=pd.DataFrame([], columns=["date", "signal", "price", "shares", "contribution", "cash_after"]),
            total_invested=0.0,
            number_of_trades=0,
            strategy_notes="No trading dates available.",
        )

    monthly_contribution = total_invested / len(invest_dates)
    cash_balance = total_invested
    shares = 0.0
    equity_values = []
    cash_values = []
    asset_values = []
    unit_values = []
    signal_rows = []
    invest_set = set(invest_dates)

    for current_date, price in prices.items():
        if current_date in invest_set:
            contribution = monthly_contribution
            if contribution > cash_balance:
                contribution = cash_balance
            bought = contribution / price
            shares += bought
            cash_balance -= contribution
            cash_balance = max(cash_balance, 0.0)
            signal_rows.append({
                "date": current_date,
                "signal": "BUY",
                "action": "BUY",
                "price": float(price),
                "shares": float(bought),
                "contribution": float(contribution),
                "cash_after": float(cash_balance),
            })

        asset_value = shares * price
        equity_values.append(asset_value + cash_balance)
        cash_values.append(cash_balance)
        asset_values.append(asset_value)
        unit_values.append(shares)

    index = prices.index
    return StrategyResult(
        equity=pd.Series(equity_values, index=index, name="equity"),
        cash=pd.Series(cash_values, index=index, name="cash"),
        asset_value=pd.Series(asset_values, index=index, name="asset_value"),
        units=pd.Series(unit_values, index=index, name="units"),
        signals=pd.DataFrame(signal_rows),
        total_invested=total_invested,
        number_of_trades=len(signal_rows),
        strategy_notes=(
            "Total capital USD 10,000. For N calendar months: contribution = 10,000/N. "
            "Uninvested capital remains in cash."
        ),
    )


def strategy_sma_cross(
    prices: pd.Series,
    initial_capital: float = INITIAL_CAPITAL,
    short_window: int = SMA_SHORT_WINDOW,
    long_window: int = SMA_LONG_WINDOW,
    history: pd.Series | None = None,
) -> StrategyResult:
    prices = prices.dropna().astype(float)
    if history is not None:
        combined = pd.concat([history.dropna().astype(float), prices]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
    else:
        combined = prices
    if prices.empty:
        return StrategyResult(
            equity=pd.Series([], dtype=float, name="equity"),
            cash=pd.Series([], dtype=float, name="cash"),
            asset_value=pd.Series([], dtype=float, name="asset_value"),
            units=pd.Series([], dtype=float, name="units"),
            signals=pd.DataFrame([], columns=["date", "signal", "price", "shares", "cash_after", "reason"]),
            total_invested=0.0,
            number_of_trades=0,
            strategy_notes="No price data available.",
        )

    sma_short = combined.rolling(short_window).mean().shift(1)
    sma_long = combined.rolling(long_window).mean().shift(1)
    above = (sma_short > sma_long).astype(int)
    cross = above.diff().fillna(0)

    cash_balance = initial_capital
    shares = 0.0
    in_market = False
    equity_values = []
    cash_values = []
    asset_values = []
    unit_values = []
    signal_rows = []

    first_test_day = prices.index[0]
    first_above = int(above.loc[first_test_day]) if pd.notna(above.loc[first_test_day]) else 0
    if history is not None and first_above == 1:
        first_price = float(prices.iloc[0])
        cash_before = cash_balance
        shares_before = shares
        shares = cash_balance / first_price
        cash_balance = 0.0
        in_market = True
        signal_rows.append({
            "date": first_test_day,
            "signal": "BUY",
            "action": "BUY",
            "price": first_price,
            "shares": float(shares),
            "shares_before": float(shares_before),
            "shares_after": float(shares),
            "cash_before": float(cash_before),
            "cash_after": 0.0,
            "equity": float(shares * first_price + cash_balance),
            "short_sma": nullable_float(sma_short.loc[first_test_day]),
            "long_sma": nullable_float(sma_long.loc[first_test_day]),
            "short_window": short_window,
            "long_window": long_window,
            "reason": "Bullish regime active by prior-period SMA regime at test start.",
        })

    for current_date, price in prices.items():
        signal = cross.loc[current_date] if current_date in cross.index else 0.0
        price_value = float(price)
        short_sma_value = nullable_float(sma_short.loc[current_date])
        long_sma_value = nullable_float(sma_long.loc[current_date])
        if signal == 1 and not in_market:
            cash_before = cash_balance
            shares_before = shares
            shares = cash_balance / price_value
            cash_balance = 0.0
            in_market = True
            signal_rows.append({
                "date": current_date,
                "signal": "BUY",
                "action": "BUY",
                "price": price_value,
                "shares": float(shares),
                "shares_before": float(shares_before),
                "shares_after": float(shares),
                "cash_before": float(cash_before),
                "cash_after": 0.0,
                "equity": float(shares * price_value + cash_balance),
                "short_sma": short_sma_value,
                "long_sma": long_sma_value,
                "short_window": short_window,
                "long_window": long_window,
                "reason": "Signal based on prior available adjusted close data; executed at current close.",
            })
        elif signal == -1 and in_market:
            cash_before = cash_balance
            shares_before = shares
            cash_balance = shares * price_value
            shares = 0.0
            in_market = False
            signal_rows.append({
                "date": current_date,
                "signal": "SELL",
                "action": "SELL",
                "price": price_value,
                "shares": 0.0,
                "shares_before": float(shares_before),
                "shares_after": 0.0,
                "cash_before": float(cash_before),
                "cash_after": float(cash_balance),
                "equity": float(cash_balance),
                "short_sma": short_sma_value,
                "long_sma": long_sma_value,
                "short_window": short_window,
                "long_window": long_window,
                "reason": "Signal based on prior available adjusted close data; executed at current close.",
            })

        asset_value = shares * price
        equity_values.append(asset_value + cash_balance)
        cash_values.append(cash_balance)
        asset_values.append(asset_value)
        unit_values.append(shares)

    return StrategyResult(
        equity=pd.Series(equity_values, index=prices.index, name="equity"),
        cash=pd.Series(cash_values, index=prices.index, name="cash"),
        asset_value=pd.Series(asset_values, index=prices.index, name="asset_value"),
        units=pd.Series(unit_values, index=prices.index, name="units"),
        signals=pd.DataFrame(signal_rows),
        total_invested=initial_capital,
        number_of_trades=len(signal_rows),
        strategy_notes=(
            "Pre-defined SMA rule. Signals are computed from prior available adjusted close data using shifted smoothing windows; trades execute on current close."
        ),
    )



def strategy_spy_buy_and_hold(prices: pd.Series, initial_capital: float = INITIAL_CAPITAL) -> StrategyResult:
    """SPY Buy-and-Hold as market benchmark."""
    prices = prices.dropna().astype(float)
    if prices.empty:
        return StrategyResult(
            equity=pd.Series([], dtype=float, name="equity"),
            cash=pd.Series([], dtype=float, name="cash"),
            asset_value=pd.Series([], dtype=float, name="asset_value"),
            units=pd.Series([], dtype=float, name="units"),
            signals=pd.DataFrame([], columns=["date", "signal", "price", "shares", "cash_after"]),
            total_invested=0.0,
            number_of_trades=0,
            strategy_notes="No price data available.",
        )
    shares = initial_capital / prices.iloc[0]
    asset_value = prices * shares
    cash = pd.Series(0.0, index=prices.index, name="cash")
    units = pd.Series(shares, index=prices.index, name="units")
    signals = pd.DataFrame([{
        "date": prices.index[0],
        "signal": "BUY",
        "action": "BUY",
        "price": float(prices.iloc[0]),
        "shares": float(shares),
        "cash_after": 0.0,
    }])
    return StrategyResult(
        equity=asset_value.rename("equity"),
        cash=cash,
        asset_value=asset_value.rename("asset_value"),
        units=units,
        signals=signals,
        total_invested=initial_capital,
        number_of_trades=1,
        strategy_notes="SPY market benchmark. Buy-and-hold USD 10,000 on first trading day.",
    )


def run_problem_one_backtests(prices_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Run Problem 1 strategies for all 5 formal stocks + SPY benchmark.
    Returns: (performance_df, equity_curves_df, strategy_signals_df, benchmark_df)
    """
    performance_rows = []
    curve_rows = []
    signal_rows = []
    benchmark_rows = []

    spy_series = prices_df.loc[prices_df["Symbol"] == MARKET_BENCHMARK].set_index("Date")[PRICE_COLUMN]
    if not spy_series.empty:
        spy_perf = perf_metrics(strategy_spy_buy_and_hold(spy_series).equity, INITIAL_CAPITAL, INITIAL_CAPITAL)
        spy_ann_return = spy_perf.annualized_return
    else:
        spy_ann_return = 0.0

    # Define canonical strategy names required by the course project
    strategies = {
        "Buy-and-Hold": strategy_buy_and_hold,
        "Fair DCA": strategy_dca,
    }

    # Run for formal 5 stocks
    for ticker in STOCK_UNIVERSE:
        price_series = prices_df.loc[prices_df["Symbol"] == ticker].set_index("Date")[PRICE_COLUMN]
        if price_series.empty:
            print(f"Warning: price series missing for {ticker}; skipping Problem 1 strategies for this ticker.")
            continue

        for strategy_name, runner in strategies.items():
            result = runner(price_series)
            perf = perf_metrics(result.equity, result.total_invested, INITIAL_CAPITAL)
            perf_row = {
                "ticker": ticker,
                "strategy": strategy_name,
                **perf.as_row(),
                "number_of_trades": result.number_of_trades,
                "excess_annualized_return_vs_spy": None if perf.annualized_return is None or spy_ann_return is None else round(perf.annualized_return - spy_ann_return, 6),
                "outperformed_spy": False if perf.annualized_return is None or spy_ann_return is None else perf.annualized_return > spy_ann_return,
                "monthly_contribution": round(INITIAL_CAPITAL / len(first_trading_day_each_month(price_series.index)), 6)
                if strategy_name == "Fair DCA"
                else None,
                "notes": result.strategy_notes,
            }
            performance_rows.append(perf_row)

            drawdowns = drawdown_series(result.equity)
            frame = pd.DataFrame({
                "date": result.equity.index.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "strategy": strategy_name,
                "equity": result.equity.values,
                "cash": result.cash.values,
                "asset_value": result.asset_value.values,
                "units": result.units.values,
                "drawdown": drawdowns.values,
            })
            curve_rows.append(frame)

            if not result.signals.empty:
                sig = result.signals.copy()
                sig["date"] = pd.to_datetime(sig["date"]).dt.strftime("%Y-%m-%d")
                sig["ticker"] = ticker
                sig["strategy"] = strategy_name
                signal_rows.append(sig)
        
        # Add SMA strategies from SMA_STRATEGIES list
        for sma_def in SMA_STRATEGIES:
            sma_name = sma_def["name"]
            result = strategy_sma_cross(price_series, short_window=sma_def["short_window"], long_window=sma_def["long_window"], history=None)
            perf = perf_metrics(result.equity, result.total_invested, INITIAL_CAPITAL)
            perf_row = {
                "ticker": ticker,
                "strategy": sma_name,
                **perf.as_row(),
                "number_of_trades": result.number_of_trades,
                "excess_annualized_return_vs_spy": None if perf.annualized_return is None or spy_ann_return is None else round(perf.annualized_return - spy_ann_return, 6),
                "outperformed_spy": False if perf.annualized_return is None or spy_ann_return is None else perf.annualized_return > spy_ann_return,
                "monthly_contribution": None,
                "notes": result.strategy_notes,
            }
            performance_rows.append(perf_row)

            drawdowns = drawdown_series(result.equity)
            frame = pd.DataFrame({
                "date": result.equity.index.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "strategy": sma_name,
                "equity": result.equity.values,
                "cash": result.cash.values,
                "asset_value": result.asset_value.values,
                "units": result.units.values,
                "drawdown": drawdowns.values,
            })
            curve_rows.append(frame)

            if not result.signals.empty:
                sig = result.signals.copy()
                sig["date"] = pd.to_datetime(sig["date"]).dt.strftime("%Y-%m-%d")
                sig["ticker"] = ticker
                sig["strategy"] = sma_name
                signal_rows.append(sig)
    
    # SPY Buy-and-Hold benchmark
    spy_series = prices_df.loc[prices_df["Symbol"] == MARKET_BENCHMARK].set_index("Date")[PRICE_COLUMN]
    if not spy_series.empty:
        result = strategy_spy_buy_and_hold(spy_series)
        perf = perf_metrics(result.equity, result.total_invested, INITIAL_CAPITAL)
        benchmark_row = {
            "ticker": MARKET_BENCHMARK,
            "strategy": "Buy-and-Hold",
            "asset_type": "benchmark",
            **perf.as_row(),
            "number_of_trades": result.number_of_trades,
            "notes": result.strategy_notes,
        }
        benchmark_rows.append(benchmark_row)
        
        drawdowns = drawdown_series(result.equity)
        frame = pd.DataFrame({
            "date": result.equity.index.strftime("%Y-%m-%d"),
            "ticker": MARKET_BENCHMARK,
            "strategy": "Buy-and-Hold",
            "asset_type": "benchmark",
            "equity": result.equity.values,
            "cash": result.cash.values,
            "asset_value": result.asset_value.values,
            "units": result.units.values,
            "drawdown": drawdowns.values,
        })
        curve_rows.append(frame)
        
        if not result.signals.empty:
            sig = result.signals.copy()
            sig["date"] = pd.to_datetime(sig["date"]).dt.strftime("%Y-%m-%d")
            sig["ticker"] = MARKET_BENCHMARK
            sig["strategy"] = "Buy-and-Hold"
            signal_rows.append(sig)

    performance_df = pd.DataFrame(performance_rows)
    curves_df = pd.concat(curve_rows, ignore_index=True)
    signals_df = pd.concat(signal_rows, ignore_index=True) if signal_rows else pd.DataFrame()
    benchmark_df = pd.DataFrame(benchmark_rows)
    
    return performance_df, curves_df, signals_df, benchmark_df


def build_sma_trade_markers(strategy_signals: pd.DataFrame) -> pd.DataFrame:
    marker_columns = [
        "date",
        "ticker",
        "strategy",
        "signal",
        "action",
        "price",
        "equity",
        "cash_before",
        "cash_after",
        "shares_before",
        "shares_after",
        "shares",
        "short_sma",
        "long_sma",
        "short_window",
        "long_window",
    ]
    if strategy_signals.empty:
        return pd.DataFrame(columns=marker_columns)

    allowed_strategies = {item["name"] for item in SMA_STRATEGIES}
    markers = strategy_signals.copy()
    if "action" not in markers.columns:
        markers["action"] = markers["signal"]
    markers["action"] = markers["action"].astype(str).str.upper()
    markers["signal"] = markers["signal"].astype(str).str.upper()

    markers = markers[
        markers["ticker"].isin(STOCK_UNIVERSE)
        & markers["strategy"].isin(allowed_strategies)
        & markers["action"].isin(["BUY", "SELL"])
    ].copy()

    for column in marker_columns:
        if column not in markers.columns:
            markers[column] = None
    markers = markers[marker_columns]
    markers = markers.sort_values(["ticker", "strategy", "date", "action"]).reset_index(drop=True)
    return markers


def temporal_validation(prices_df: pd.DataFrame, spy_prices: pd.Series) -> pd.DataFrame:
    """Temporal validation for formal 5 stocks + SPY benchmark."""
    rows = []
    
    # Formal stocks
    for ticker in STOCK_UNIVERSE:
        full_series = prices_df.loc[prices_df["Symbol"] == ticker].set_index("Date")[PRICE_COLUMN].astype(float)
        years = sorted(pd.Index(full_series.index.year).unique())
        if len(years) < 3:
            continue

        for idx in range(1, len(years)):
            train_years = years[:idx]
            test_years = years[idx:]
            train_start = pd.Timestamp(f"{train_years[0]}-01-01")
            train_end = pd.Timestamp(f"{train_years[-1]}-12-31")
            test_start = pd.Timestamp(f"{test_years[0]}-01-01")
            test_end = pd.Timestamp(f"{test_years[-1]}-12-31")

            train_slice = full_series.loc[(full_series.index >= train_start) & (full_series.index <= train_end)]
            test_slice = full_series.loc[(full_series.index >= test_start) & (full_series.index <= test_end)]
            spy_test_slice = spy_prices.loc[(spy_prices.index >= test_start) & (spy_prices.index <= test_end)]
            if len(test_slice) < 30:
                continue

            window_id = f"W{idx:02d}"

            # Buy-and-Hold
            bh_result = strategy_buy_and_hold(test_slice)
            rows.append(build_tv_row(window_id, train_slice, test_slice, spy_test_slice, ticker, "Buy-and-Hold", bh_result))

            # Fair DCA
            dca_result = strategy_dca(test_slice)
            rows.append(build_tv_row(window_id, train_slice, test_slice, spy_test_slice, ticker, "Fair DCA", dca_result))

            # Pre-defined SMA strategies (use training history for indicators)
            for sma_def in SMA_STRATEGIES:
                sma_name = sma_def["name"]
                sma_result = strategy_sma_cross(test_slice, history=train_slice, short_window=sma_def["short_window"], long_window=sma_def["long_window"])
                rows.append(build_tv_row(window_id, train_slice, test_slice, spy_test_slice, ticker, sma_name, sma_result))

    return pd.DataFrame(rows)


def build_tv_row(
    window_id: str,
    train_slice: pd.Series,
    test_slice: pd.Series,
    spy_test_slice: pd.Series | None,
    ticker: str,
    strategy_name: str,
    result: StrategyResult,
) -> dict[str, object]:
    perf = perf_metrics(result.equity, result.total_invested, INITIAL_CAPITAL)
    spy_perf = None
    if spy_test_slice is not None and not spy_test_slice.empty:
        spy_perf = perf_metrics(strategy_spy_buy_and_hold(spy_test_slice).equity, INITIAL_CAPITAL, INITIAL_CAPITAL)

    if strategy_name == "Buy-and-Hold":
        selected_parameters = "N/A"
        parameter_selection_method = "benchmark_no_training_parameters"
    elif strategy_name == "Fair DCA":
        selected_parameters = f"monthly_contribution = {INITIAL_CAPITAL} / {len(first_trading_day_each_month(test_slice.index))}"
        parameter_selection_method = "predefined_benchmark_rule"
    else:
        selected_parameters = f"short_window={result.strategy_notes and result.strategy_notes.split(' ')[0] or 'N/A'}"
        parameter_selection_method = "predefined_rule_not_optimized_on_test_data"
        if "SMA 20/60" in strategy_name:
            selected_parameters = "short_window=20,long_window=60"
        elif "SMA 50/200" in strategy_name:
            selected_parameters = "short_window=50,long_window=200"
        elif "SMA 100/300" in strategy_name:
            selected_parameters = "short_window=100,long_window=300"

    return {
        "window_id": window_id,
        "validation_method": TEMPORAL_VALIDATION_METHOD,
        "parameter_selection_method": parameter_selection_method,
        "selected_parameters": selected_parameters,
        "signal_execution_timing": "Shifted prior-period SMA / prior data signals; current close execution.",
        "train_start": train_slice.index.min().strftime("%Y-%m-%d"),
        "train_end": train_slice.index.max().strftime("%Y-%m-%d"),
        "test_start": test_slice.index.min().strftime("%Y-%m-%d"),
        "test_end": test_slice.index.max().strftime("%Y-%m-%d"),
        "ticker": ticker,
        "strategy": strategy_name,
        **perf.as_row(),
        "excess_annualized_return_vs_spy": None if spy_perf is None or perf.annualized_return is None or spy_perf.annualized_return is None else round(perf.annualized_return - spy_perf.annualized_return, 6),
        "outperformed_spy": False if spy_perf is None or perf.annualized_return is None or spy_perf.annualized_return is None else perf.annualized_return > spy_perf.annualized_return,
        "number_of_trades": result.number_of_trades,
    }


def build_pivot(prices_df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Build pivot table of adjusted prices for the given tickers."""
    filtered = prices_df[prices_df["Symbol"].isin(tickers)]
    pivot = filtered.pivot(index="Date", columns="Symbol", values=PRICE_COLUMN)
    return pivot.sort_index().sort_index(axis=1)


def pair_ranking_from_pivot(pivot: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Rank pair candidates by pairwise return correlation."""
    returns = pivot[[col for col in pivot.columns if col in tickers]].pct_change().dropna()
    rows = []
    for stock_a, stock_b in combinations(tickers, 2):
        if stock_a not in returns.columns or stock_b not in returns.columns:
            continue
        correlation = float(returns[stock_a].corr(returns[stock_b]))
        rows.append({
            "pair": f"{stock_a}-{stock_b}",
            "stock_a": stock_a,
            "stock_b": stock_b,
            "correlation": round(correlation, 6),
        })
    return pd.DataFrame(rows).sort_values("correlation", ascending=False).reset_index(drop=True)


def adf_result_for_pair(spread: pd.Series) -> tuple[float | None, float | None, str]:
    clean_spread = spread.dropna().astype(float)
    if adfuller is None or len(clean_spread) < 30:
        return None, None, "ADF 無法計算。請參考價差 / z-score 圖以評估均值回歸。"

    statistic, p_value, *_ = adfuller(clean_spread)
    if p_value < 0.05:
        comment = "ADF p-value < 0.05：顯示價差呈現穩定性 / 均值回歸。"
    else:
        comment = "ADF p-value >= 0.05：對穩定性 / 均值回歸的證據較弱。"
    return float(statistic), float(p_value), comment


def pairs_backtest(
    pivot: pd.DataFrame,
    pair: tuple[str, str],
    train_pivot: pd.DataFrame | None = None,
    test_start: pd.Timestamp | None = None,
    test_end: pd.Timestamp | None = None,
    lookback: int = PAIR_ZSCORE_WINDOW,
    entry_threshold: float = PAIR_ENTRY_THRESHOLD,
    exit_threshold: float = PAIR_EXIT_THRESHOLD,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    stock_a, stock_b = pair
    combined = pivot[[stock_a, stock_b]].copy().dropna()
    if train_pivot is None:
        train_pivot = combined
    train_combined = train_pivot[[stock_a, stock_b]].copy().dropna()

    if test_start is None:
        test_start = combined.index.min()
    if test_end is None:
        test_end = combined.index.max()

    train_log_a = np.log(train_combined[stock_a]).astype(float)
    train_log_b = np.log(train_combined[stock_b]).astype(float)
    if len(train_log_a) < 2 or len(train_log_b) < 2:
        hedge_ratio = 1.0
    else:
        hedge_ratio = float(np.polyfit(train_log_b, train_log_a, 1)[0])

    spread = np.log(combined[stock_a]) - hedge_ratio * np.log(combined[stock_b])
    rolling_mean = spread.rolling(lookback).mean()
    rolling_std = spread.rolling(lookback).std()
    zscore = (spread - rolling_mean) / rolling_std
    signal_zscore = zscore.shift(1)

    test_index = combined.loc[(combined.index >= test_start) & (combined.index <= test_end)].index
    capital = INITIAL_CAPITAL
    cash_balance = capital
    position = 0  # +1 = long A / short B, -1 = short A / long B
    a_units = 0.0
    b_units = 0.0
    trades_completed = 0
    wins = 0
    last_entry_capital = capital

    log_rows = []
    signal_rows = []

    for current_date in test_index:
        price_a = float(combined.loc[current_date, stock_a])
        price_b = float(combined.loc[current_date, stock_b])
        raw_z = zscore.loc[current_date]
        signal_z = signal_zscore.loc[current_date]

        if pd.notna(signal_z):
            if position == 0:
                if signal_z >= entry_threshold:
                    leg_capital = capital / 2.0
                    a_units = -leg_capital / price_a
                    b_units = leg_capital / price_b
                    cash_balance = capital
                    position = -1
                    last_entry_capital = capital
                    signal_rows.append({
                        "date": current_date,
                        "signal": "ENTRY_SHORT_A_LONG_B",
                        "long_leg": stock_b,
                        "short_leg": stock_a,
                        "zscore": None if pd.isna(raw_z) else float(raw_z),
                        "signal_zscore_used": float(signal_z),
                    })
                elif signal_z <= -entry_threshold:
                    leg_capital = capital / 2.0
                    a_units = leg_capital / price_a
                    b_units = -leg_capital / price_b
                    cash_balance = capital
                    position = 1
                    last_entry_capital = capital
                    signal_rows.append({
                        "date": current_date,
                        "signal": "ENTRY_LONG_A_SHORT_B",
                        "long_leg": stock_a,
                        "short_leg": stock_b,
                        "zscore": None if pd.isna(raw_z) else float(raw_z),
                        "signal_zscore_used": float(signal_z),
                    })
            elif abs(signal_z) < exit_threshold:
                realized_value = cash_balance + a_units * price_a + b_units * price_b
                capital = realized_value
                cash_balance = capital
                if realized_value > last_entry_capital:
                    wins += 1
                trades_completed += 1
                a_units = 0.0
                b_units = 0.0
                position = 0
                signal_rows.append({
                    "date": current_date,
                        "signal": "EXIT",
                        "long_leg": "-",
                        "short_leg": "-",
                        "zscore": None if pd.isna(raw_z) else float(raw_z),
                        "signal_zscore_used": float(signal_z),
                })

        portfolio_value = cash_balance + a_units * price_a + b_units * price_b if position != 0 else capital
        log_rows.append({
            "date": current_date,
            "stock_a": stock_a,
            "stock_b": stock_b,
            "price_a": price_a,
            "price_b": price_b,
            "spread": None if pd.isna(spread.loc[current_date]) else float(spread.loc[current_date]),
            "zscore": None if pd.isna(raw_z) else float(raw_z),
            "signal_zscore": None if pd.isna(signal_z) else float(signal_z),
            "position": position,
            "portfolio_value": float(portfolio_value),
        })

    log_df = pd.DataFrame(log_rows)
    signals_df = pd.DataFrame(signal_rows)
    equity = log_df.set_index("date")["portfolio_value"].astype(float)
    perf = perf_metrics(equity, INITIAL_CAPITAL, INITIAL_CAPITAL)
    train_spread = np.log(train_combined[stock_a]) - hedge_ratio * np.log(train_combined[stock_b])
    test_spread = spread.loc[test_start:test_end]
    train_adf_stat, train_adf_p_value, train_mean_reversion_comment = adf_result_for_pair(train_spread)
    test_adf_stat, test_adf_p_value, test_mean_reversion_comment = adf_result_for_pair(test_spread)
    summary = {
        "selected_pair": f"{stock_a}-{stock_b}",
        "stock_a": stock_a,
        "stock_b": stock_b,
        "spread_definition": f"log({stock_a}) - {hedge_ratio:.6f}*log({stock_b})",
        "hedge_ratio": round(hedge_ratio, 6),
        "zscore_window": lookback,
        "entry_threshold": entry_threshold,
        "exit_threshold": exit_threshold,
        "pair_selection_method": PAIR_SELECTION_METHOD,
        "pair_training_sample_start": train_combined.index.min().strftime("%Y-%m-%d") if not train_combined.empty else None,
        "pair_training_sample_end": train_combined.index.max().strftime("%Y-%m-%d") if not train_combined.empty else None,
        **perf.as_row(),
        "number_of_trades": trades_completed,
        "win_rate": 0.0 if trades_completed == 0 else round(wins / trades_completed, 6),
        "train_adf_statistic": None if train_adf_stat is None else round(train_adf_stat, 6),
        "train_adf_p_value": None if train_adf_p_value is None else round(train_adf_p_value, 6),
        "train_mean_reversion_comment": train_mean_reversion_comment,
        "test_adf_statistic": None if test_adf_stat is None else round(test_adf_stat, 6),
        "test_adf_p_value": None if test_adf_p_value is None else round(test_adf_p_value, 6),
        "test_mean_reversion_comment": test_mean_reversion_comment,
        "adf_statistic": None if train_adf_stat is None else round(train_adf_stat, 6),
        "adf_p_value": None if train_adf_p_value is None else round(train_adf_p_value, 6),
        "mean_reversion_comment": train_mean_reversion_comment,
    }
    return log_df, signals_df, summary


def pairs_temporal_validation(prices_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Pairs trading validation using STOCK_UNIVERSE only (no SPY).
    Returns: (summary_df, curves_df, rankings_df, signals_df)
    """
    # Build pivot for formal stocks only
    pivot = build_pivot(prices_df, STOCK_UNIVERSE)
    
    rows = []
    curve_rows = []
    ranking_rows = []
    signal_rows = []
    years = sorted(pd.Index(pivot.index.year).unique())

    for idx in range(1, len(years)):
        train_years = years[:idx]
        test_years = years[idx:]
        train_start = pd.Timestamp(f"{train_years[0]}-01-01")
        train_end = pd.Timestamp(f"{train_years[-1]}-12-31")
        test_start = pd.Timestamp(f"{test_years[0]}-01-01")
        test_end = pd.Timestamp(f"{test_years[-1]}-12-31")

        train_pivot = pivot.loc[(pivot.index >= train_start) & (pivot.index <= train_end)]
        test_pivot = pivot.loc[(pivot.index >= test_start) & (pivot.index <= test_end)]
        if len(train_pivot) < PAIR_ZSCORE_WINDOW or len(test_pivot) < 30:
            continue

        window_id = f"W{idx:02d}"
        ranking = pair_ranking_from_pivot(train_pivot, STOCK_UNIVERSE)
        ranking["window_id"] = window_id
        ranking["train_start"] = train_start.strftime("%Y-%m-%d")
        ranking["train_end"] = train_end.strftime("%Y-%m-%d")
        ranking["test_start"] = test_start.strftime("%Y-%m-%d")
        ranking["test_end"] = test_end.strftime("%Y-%m-%d")
        ranking_rows.append(ranking)

        best = ranking.iloc[0]
        pair = (best["stock_a"], best["stock_b"])
        log_df, signals_df, summary = pairs_backtest(
            test_pivot,
            pair,
            train_pivot=train_pivot,
            test_start=test_start,
            test_end=test_end,
        )

        row = {
            "window_id": window_id,
            "train_start": train_start.strftime("%Y-%m-%d"),
            "train_end": train_end.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end": test_end.strftime("%Y-%m-%d"),
            "selected_pair": summary["selected_pair"],
            "stock_a": summary["stock_a"],
            "stock_b": summary["stock_b"],
            "pair_selection_method": summary.get("pair_selection_method"),
            "pair_training_sample_start": summary.get("pair_training_sample_start"),
            "pair_training_sample_end": summary.get("pair_training_sample_end"),
            "hedge_ratio": summary.get("hedge_ratio"),
            "train_correlation": float(best["correlation"]),
            "spread_definition": summary["spread_definition"],
            "zscore_window": summary["zscore_window"],
            "entry_threshold": summary["entry_threshold"],
            "exit_threshold": summary["exit_threshold"],
            "initial_capital": summary["initial_capital"],
            "total_invested": summary["total_invested"],
            "final_value": summary["final_value"],
            "cumulative_return": summary["cumulative_return"],
            "annualized_return": summary["annualized_return"],
            "max_drawdown": summary["max_drawdown"],
            "volatility": summary["volatility"],
            "sharpe_ratio": summary["sharpe_ratio"],
            "number_of_trades": summary["number_of_trades"],
            "win_rate": summary["win_rate"],
            "train_adf_statistic": summary.get("train_adf_statistic"),
            "train_adf_p_value": summary.get("train_adf_p_value"),
            "train_mean_reversion_comment": summary.get("train_mean_reversion_comment"),
            "test_adf_statistic": summary.get("test_adf_statistic"),
            "test_adf_p_value": summary.get("test_adf_p_value"),
            "test_mean_reversion_comment": summary.get("test_mean_reversion_comment"),
            "adf_statistic": summary["adf_statistic"],
            "adf_p_value": summary["adf_p_value"],
            "mean_reversion_comment": summary["mean_reversion_comment"],
        }
        rows.append(row)

        curve = log_df.copy()
        curve["window_id"] = window_id
        curve["selected_pair"] = summary["selected_pair"]
        curve["drawdown"] = drawdown_series(curve.set_index("date")["portfolio_value"]).values
        curve["date"] = pd.to_datetime(curve["date"]).dt.strftime("%Y-%m-%d")
        curve_rows.append(curve)

        if not signals_df.empty:
            signals_df = signals_df.copy()
            signals_df["window_id"] = window_id
            signals_df["selected_pair"] = summary["selected_pair"]
            signals_df["date"] = pd.to_datetime(signals_df["date"]).dt.strftime("%Y-%m-%d")
            signal_rows.append(signals_df)

    summary_df = pd.DataFrame(rows)
    curves_df = pd.concat(curve_rows, ignore_index=True) if curve_rows else pd.DataFrame()
    rankings_df = pd.concat(ranking_rows, ignore_index=True)
    signals_df = pd.concat(signal_rows, ignore_index=True) if signal_rows else pd.DataFrame()
    return summary_df, curves_df, rankings_df, signals_df


def build_assumptions(number_of_months: int, actual_start_date: str, actual_end_date: str) -> dict[str, object]:
    return {
        "stock_universe": STOCK_UNIVERSE,
        "market_benchmark": MARKET_BENCHMARK,
        "data_source": "Yahoo Finance via yfinance，或使用快取的 stock_prices.csv",
        "requested_start_date": REQUESTED_START_DATE,
        "requested_target_end_date": REQUESTED_TARGET_END_DATE,
        "yfinance_end_date": YFINANCE_END_DATE,
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "price_column": PRICE_COLUMN,
        "initial_capital": INITIAL_CAPITAL,
        "dca_total_invested": INITIAL_CAPITAL,
        "dca_monthly_contribution_rule": f"對於 N 個日曆月：投入 = {INITIAL_CAPITAL}/N。範例：{number_of_months} 個月。未投入資本保留現金。",
        "fractional_shares": True,
        "transaction_costs": "未包含",
        "slippage": "未包含",
        "taxes": "未包含",
        "risk_free_rate": 0.0,
        "signal_execution_timing": "Signals are computed from prior available adjusted close data using shifted indicators; trades are executed on the current adjusted close as a next-bar approximation.",
        "sma_strategies": SMA_STRATEGIES,
        "sma_signal_source": "每組 SMA 策略僅使用該檔股票自身的調整後收盤價。",
        "sma_parameter_note": "預先定義代表性周期（短/中/長）。不在測試資料上優化。",
        "pairs_zscore_window": PAIR_ZSCORE_WINDOW,
        "pairs_entry_threshold": PAIR_ENTRY_THRESHOLD,
        "pairs_exit_threshold": PAIR_EXIT_THRESHOLD,
        "pairs_position_sizing": "每次進場等額 50% 多頭 / 50% 空頭",
        "short_selling": True,
        "borrowing_costs": "未包含",
        "temporal_validation_method": "擴增視窗。時間序列不使用隨機拆分。",
        "pair_selection_rule": "僅在股票母體內選擇訓練期日報酬相關性最高的配對。不使用測試期資料。",
        "look_ahead_bias_control": "SMA 使用先前可用的移動平均信號；配對交易使用訓練期估計的 hedge ratio、spread 參數，且測試期信號以 shift(1) prior z-score 生成。",
        "spy_usage_note": "SPY 僅作為市場基準；不納入配對交易。",
        "removed_strategy_note": "已移除舊有相對動量輸出。活躍策略為 Buy-and-Hold、Fair DCA、SMA 20/60、SMA 50/200 以及 SMA 100/300。",
        "cleanup_note": "已清理舊有檔案；若需要更新資料，請執行 generate_data.py --refresh。",
    }


def build_temporal_validation_robustness(temporal_df: pd.DataFrame) -> pd.DataFrame:
    if temporal_df.empty:
        return pd.DataFrame(columns=[
            "ticker",
            "strategy",
            "number_of_windows",
            "positive_return_windows",
            "positive_return_ratio",
            "outperform_spy_windows",
            "outperform_spy_ratio",
            "avg_annualized_return",
            "median_annualized_return",
            "min_annualized_return",
            "max_annualized_return",
            "avg_max_drawdown",
            "worst_max_drawdown",
            "avg_volatility",
            "avg_sharpe_ratio",
            "robustness_comment",
        ])

    rows = []
    for (ticker, strategy), group in temporal_df.groupby(["ticker", "strategy"]):
        num = len(group)
        pos = int((group["cumulative_return"] > 0).sum())
        out = int((group["outperformed_spy"] == True).sum())
        sharpe_vals = pd.to_numeric(group["sharpe_ratio"], errors="coerce").dropna()
        rows.append({
            "ticker": ticker,
            "strategy": strategy,
            "number_of_windows": num,
            "positive_return_windows": pos,
            "positive_return_ratio": round(pos / num, 6) if num else 0.0,
            "outperform_spy_windows": out,
            "outperform_spy_ratio": round(out / num, 6) if num else 0.0,
            "avg_annualized_return": round(group["annualized_return"].mean(), 6),
            "median_annualized_return": round(group["annualized_return"].median(), 6),
            "min_annualized_return": round(group["annualized_return"].min(), 6),
            "max_annualized_return": round(group["annualized_return"].max(), 6),
            "avg_max_drawdown": round(group["max_drawdown"].mean(), 6),
            "worst_max_drawdown": round(group["max_drawdown"].min(), 6),
            "avg_volatility": round(group["volatility"].mean(), 6),
            "avg_sharpe_ratio": None if sharpe_vals.empty else round(sharpe_vals.mean(), 6),
            "robustness_comment": (
                f"基於 {num} 個時序驗證視窗的歷史穩健性摘要；不代表未來績效。"
            ),
        })
    return pd.DataFrame(rows)


def build_pairs_temporal_robustness(pairs_df: pd.DataFrame) -> pd.DataFrame:
    if pairs_df.empty:
        return pd.DataFrame(columns=[
            "number_of_windows",
            "positive_return_windows",
            "positive_return_ratio",
            "avg_annualized_return",
            "median_annualized_return",
            "min_annualized_return",
            "max_annualized_return",
            "avg_max_drawdown",
            "worst_max_drawdown",
            "avg_volatility",
            "avg_sharpe_ratio",
            "avg_trades",
            "most_common_selected_pair",
            "robustness_comment",
        ])

    num = len(pairs_df)
    pos = int((pairs_df["cumulative_return"] > 0).sum())
    sharpe_vals = pd.to_numeric(pairs_df["sharpe_ratio"], errors="coerce").dropna()
    most_common = pairs_df["selected_pair"].mode()
    top_pair = most_common.iloc[0] if not most_common.empty else None
    return pd.DataFrame([{
        "number_of_windows": num,
        "positive_return_windows": pos,
        "positive_return_ratio": round(pos / num, 6) if num else 0.0,
        "avg_annualized_return": round(pairs_df["annualized_return"].mean(), 6),
        "median_annualized_return": round(pairs_df["annualized_return"].median(), 6),
        "min_annualized_return": round(pairs_df["annualized_return"].min(), 6),
        "max_annualized_return": round(pairs_df["annualized_return"].max(), 6),
        "avg_max_drawdown": round(pairs_df["max_drawdown"].mean(), 6),
        "worst_max_drawdown": round(pairs_df["max_drawdown"].min(), 6),
        "avg_volatility": round(pairs_df["volatility"].mean(), 6),
        "avg_sharpe_ratio": None if sharpe_vals.empty else round(sharpe_vals.mean(), 6),
        "avg_trades": round(pairs_df["number_of_trades"].mean(), 6),
        "most_common_selected_pair": top_pair,
        "robustness_comment": (
            "此配對交易樣本摘要僅供歷史穩健性參考，無法保證未來結果。"
        ),
    }])


def write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def dataframe_records(df: pd.DataFrame) -> list[dict[str, object]]:
    frame = df.copy()
    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            frame[col] = frame[col].dt.strftime("%Y-%m-%d")
    frame = frame.where(pd.notna(frame), None)
    records = frame.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    record[key] = None
            elif value is pd.NaT:
                record[key] = None
    return records


def main(refresh: bool = False) -> None:
    print("=" * 60)
    print("Quantitative Trading Backtesting - Data Generation")
    print("=" * 60)
    print(f"Stock universe: {', '.join(STOCK_UNIVERSE)}")
    print(f"Market benchmark: {MARKET_BENCHMARK}")
    print(f"Data period: {REQUESTED_START_DATE} to {REQUESTED_END_DATE}")
    print(f"Initial capital per stock: USD {INITIAL_CAPITAL:,.0f}")
    print("=" * 60)
    
    prices_df = load_prices(refresh=refresh)
    prices_df.to_csv(DATA_DIR / "stock_prices.csv", index=False)
    actual_start = prices_df["Date"].min().strftime("%Y-%m-%d")
    actual_end = prices_df["Date"].max().strftime("%Y-%m-%d")
    print(f"Actual data range: {actual_start} to {actual_end}")
    print(f"stock_prices.csv: {len(prices_df):,} rows")
    if refresh and pd.Timestamp(actual_end) < pd.Timestamp(REQUESTED_TARGET_END_DATE):
        print(
            "Warning: actual_end_date is before target coverage date. "
            f"Actual end = {actual_end}, target = {REQUESTED_TARGET_END_DATE}."
        )

    stock_summary = build_stock_summary(prices_df)
    stock_summary.to_csv(DATA_DIR / "stock_summary.csv", index=False)
    print(f"stock_summary.csv: {len(stock_summary)} rows")

    # Problem 1 backtests
    strategy_performance, equity_curves, strategy_signals, market_benchmark = run_problem_one_backtests(prices_df)
    sma_trade_markers = build_sma_trade_markers(strategy_signals)
    strategy_performance.to_csv(DATA_DIR / "strategy_performance.csv", index=False)
    equity_curves.to_csv(DATA_DIR / "equity_curves.csv", index=False)
    strategy_signals.to_csv(DATA_DIR / "strategy_signals.csv", index=False)
    sma_trade_markers.to_csv(DATA_DIR / "sma_trade_markers.csv", index=False)
    print(f"strategy_performance.csv: {len(strategy_performance)} rows ({strategy_performance['strategy'].nunique()} strategies)")
    print(f"equity_curves.csv: {len(equity_curves):,} rows")
    print(f"sma_trade_markers.csv: {len(sma_trade_markers)} BUY/SELL markers")

    if not market_benchmark.empty:
        market_benchmark.to_csv(DATA_DIR / "market_benchmark.csv", index=False)
        print(f"market_benchmark.csv: {len(market_benchmark)} row(s) (SPY)")

    # Temporal validation
    spy_prices = prices_df.loc[prices_df["Symbol"] == MARKET_BENCHMARK].set_index("Date")[PRICE_COLUMN]
    temporal_df = temporal_validation(prices_df, spy_prices)
    temporal_df.to_csv(DATA_DIR / "temporal_validation.csv", index=False)
    print(f"temporal_validation.csv: {len(temporal_df)} rows")

    # Pairs trading (5 stocks only, no SPY)
    pair_correlations = pair_ranking_from_pivot(build_pivot(prices_df, STOCK_UNIVERSE), STOCK_UNIVERSE)
    pair_correlations.to_csv(DATA_DIR / "pair_correlations.csv", index=False)
    print(f"pair_correlations.csv: {len(pair_correlations)} pairs")

    pairs_tv, pairs_tv_curves, pairs_window_correlations, pairs_tv_signals = pairs_temporal_validation(prices_df)
    pairs_tv.to_csv(DATA_DIR / "pairs_temporal_validation.csv", index=False)
    pairs_tv_curves.to_csv(DATA_DIR / "pairs_temporal_curves.csv", index=False)
    pairs_window_correlations.to_csv(DATA_DIR / "pairs_window_correlations.csv", index=False)
    pairs_tv_signals.to_csv(DATA_DIR / "pairs_temporal_signals.csv", index=False)
    print(f"pairs_temporal_validation.csv: {len(pairs_tv)} windows")

    temporal_robustness = build_temporal_validation_robustness(temporal_df)
    temporal_robustness.to_csv(DATA_DIR / "temporal_validation_robustness.csv", index=False)
    print(f"temporal_validation_robustness.csv: {len(temporal_robustness)} rows")

    pairs_robustness = build_pairs_temporal_robustness(pairs_tv)
    pairs_robustness.to_csv(DATA_DIR / "pairs_temporal_robustness.csv", index=False)
    print(f"pairs_temporal_robustness.csv: {len(pairs_robustness)} rows")

    # Assumptions & dashboard
    full_sample_months = len(first_trading_day_each_month(pd.DatetimeIndex(prices_df["Date"])))
    assumptions = build_assumptions(full_sample_months, actual_start, actual_end)
    write_json(DATA_DIR / "assumptions.json", assumptions)

    dashboard = {
        "project": "量化交易回測儀表板",
        "project_type": "靜態研究儀表板",
        "not_a_live_trading_system": True,
        "tickers": STOCK_UNIVERSE,
        "market_benchmark": MARKET_BENCHMARK,
        "data_range": {
            "start": actual_start,
            "end": actual_end,
        },
        "data_source": "Yahoo Finance via yfinance",
        "price_column": PRICE_COLUMN,
        "initial_capital": INITIAL_CAPITAL,
        "strategies": [
            "Buy-and-Hold",
            "Fair DCA",
            "SMA 20/60",
            "SMA 50/200",
            "SMA 100/300",
        ],
        "default_stock": STOCK_UNIVERSE[0],
        "default_sma_strategy": "SMA 50/200",
        "default_temporal_strategy": "SMA 50/200",
        "default_pairs_window": "W01" if not pairs_tv.empty else None,
        "generated_at": date.today().strftime("%Y-%m-%d"),
    }
    write_json(DATA_DIR / "dashboard.json", dashboard)

    # Data bundle
    bundle = {
        "dashboard": dashboard,
        "assumptions": assumptions,
        "stock_summary": dataframe_records(stock_summary),
        "stock_prices": dataframe_records(prices_df.rename(columns={
            "Symbol": "ticker",
            "Adj Close": "adj_close",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })),
        "strategy_performance": dataframe_records(strategy_performance),
        "market_benchmark": dataframe_records(market_benchmark),
        "equity_curves": dataframe_records(equity_curves),
        "sma_trade_markers": dataframe_records(sma_trade_markers),
        "temporal_validation": dataframe_records(temporal_df),
        "pair_correlations": dataframe_records(pair_correlations),
        "pairs_temporal_validation": dataframe_records(pairs_tv),
        "pairs_temporal_curves": dataframe_records(pairs_tv_curves),
        "pairs_window_correlations": dataframe_records(pairs_window_correlations),
        "pairs_temporal_signals": dataframe_records(pairs_tv_signals),
        "temporal_validation_robustness": dataframe_records(temporal_robustness),
        "pairs_temporal_robustness": dataframe_records(pairs_robustness),
    }

    with (DATA_DIR / "data_bundle.js").open("w", encoding="utf-8") as handle:
        handle.write("// Auto-generated by generate_data.py. Do not edit by hand.\n")
        handle.write("window.QT_DATA = ")
        json.dump(bundle, handle, ensure_ascii=False, allow_nan=False)
        handle.write(";\n")
    print("data_bundle.js written")
    print("=" * 60)
    print("✓ Data generation complete")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Redownload prices instead of using cached stock_prices.csv.")
    args = parser.parse_args()
    main(refresh=args.refresh)
