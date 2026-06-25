"""
Récupération des données financières via Yahoo Finance (yfinance).
Générique : supporte XAU/USD (GC=F) et BTC/USD (BTC-USD).
"""
import ssl
import sys
import time
import warnings
import urllib3
import requests
import yfinance as yf
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

# Le patch SSL n'est nécessaire que sur Windows (certificats manquants en Python 3.14)
if sys.platform == "win32":
    ssl._create_default_https_context = ssl._create_unverified_context

ASSETS = {
    "GOLD": {
        "ticker":   "GC=F",
        "label":    "XAU/USD — Gold",
        "currency": "USD/oz",
    },
    "BTC": {
        "ticker":   "BTC-USD",
        "label":    "BTC/USD — Bitcoin",
        "currency": "USD",
    },
}

_session = requests.Session()
_session.verify = sys.platform != "win32"  # True sur Linux/Mac, False sur Windows
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})


def _make_ticker(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker, session=_session)


def _download_with_retry(ticker_obj: yf.Ticker, period: str, interval: str, retries: int = 3) -> pd.DataFrame:
    for attempt in range(retries):
        try:
            df = ticker_obj.history(period=period, interval=interval, auto_adjust=True)
            if not df.empty:
                return df
        except Exception as e:
            err_str = str(e)
            if "Rate" in err_str or "Too Many" in err_str:
                time.sleep(10 * (attempt + 1))
            else:
                raise
    raise ValueError(f"Impossible de récupérer les données après {retries} tentatives")


def fetch_ohlcv(interval: str = "5m", period: str = "5d", asset: str = "GOLD") -> pd.DataFrame:
    ticker_sym = ASSETS[asset]["ticker"]
    ticker_obj = _make_ticker(ticker_sym)
    df = _download_with_retry(ticker_obj, period=period, interval=interval)

    if df.empty:
        raise ValueError(f"Aucune donnée pour {ticker_sym} [{interval}/{period}]")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={c: c.capitalize() for c in df.columns})
    cols = [c for c in ["Open", "Close", "High", "Low", "Volume"] if c in df.columns]
    df = df[cols].copy()
    df.dropna(inplace=True)
    df.index = df.index.tz_convert("UTC") if df.index.tzinfo else df.index.tz_localize("UTC")
    return df


def get_current_price(asset: str = "GOLD") -> float:
    ticker_sym = ASSETS[asset]["ticker"]
    t    = _make_ticker(ticker_sym)
    info = t.fast_info
    return float(info.last_price or info.regular_market_previous_close)


def df_to_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for ts, row in df.iterrows():
        records.append({
            "time":   int(ts.timestamp()),
            "open":   round(float(row["Open"]),   2),
            "high":   round(float(row["High"]),   2),
            "low":    round(float(row["Low"]),    2),
            "close":  round(float(row["Close"]),  2),
            "volume": int(row.get("Volume", 0)),
        })
    return records
