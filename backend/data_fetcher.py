"""
Récupération des données financières via Yahoo Finance.
Supporte : XAU/USD, BTC, ETH, ICP, XRP, BNB, SOL.
Cache 55s pour le dashboard multi-actifs.
"""
import ssl
import sys
import time
import warnings
import threading
import urllib3
import requests
import yfinance as yf
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

if sys.platform == "win32":
    ssl._create_default_https_context = ssl._create_unverified_context

ASSETS = {
    "GOLD": {"ticker": "GC=F",    "label": "XAU/USD — Gold",             "currency": "USD/oz", "icon": "⚡"},
    "BTC":  {"ticker": "BTC-USD", "label": "BTC/USD — Bitcoin",           "currency": "USD",    "icon": "₿"},
    "ETH":  {"ticker": "ETH-USD", "label": "ETH/USD — Ethereum",          "currency": "USD",    "icon": "Ξ"},
    "ICP":  {"ticker": "ICP-USD", "label": "ICP/USD — Internet Computer", "currency": "USD",    "icon": "∞"},
    "XRP":  {"ticker": "XRP-USD", "label": "XRP/USD — Ripple",            "currency": "USD",    "icon": "✕"},
    "BNB":  {"ticker": "BNB-USD", "label": "BNB/USD — BNB Chain",         "currency": "USD",    "icon": "B"},
    "SOL":  {"ticker": "SOL-USD", "label": "SOL/USD — Solana",            "currency": "USD",    "icon": "◎"},
}

_session = requests.Session()
_session.verify = sys.platform != "win32"
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

# Cache simple thread-safe
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 55  # secondes


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return entry["data"]
    return None


def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _make_ticker(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker, session=_session)


def _download_with_retry(ticker_obj, period, interval, retries=3):
    for attempt in range(retries):
        try:
            df = ticker_obj.history(period=period, interval=interval, auto_adjust=True)
            if not df.empty:
                return df
        except Exception as e:
            if "Rate" in str(e) or "Too Many" in str(e):
                time.sleep(10 * (attempt + 1))
            else:
                raise
    raise ValueError("Impossible de récupérer les données après {retries} tentatives")


def fetch_ohlcv(interval="5m", period="5d", asset="GOLD") -> pd.DataFrame:
    if asset not in ASSETS:
        raise ValueError(f"Asset inconnu : {asset}")

    cache_key = f"ohlcv:{asset}:{interval}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    ticker_obj = _make_ticker(ASSETS[asset]["ticker"])
    df = _download_with_retry(ticker_obj, period=period, interval=interval)

    if df.empty:
        raise ValueError(f"Aucune donnée pour {ASSETS[asset]['ticker']}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={c: c.capitalize() for c in df.columns})
    cols = [c for c in ["Open", "Close", "High", "Low", "Volume"] if c in df.columns]
    df = df[cols].copy()
    df.dropna(inplace=True)
    df.index = df.index.tz_convert("UTC") if df.index.tzinfo else df.index.tz_localize("UTC")

    _cache_set(cache_key, df)
    return df


def get_current_price(asset="GOLD") -> float:
    t = _make_ticker(ASSETS[asset]["ticker"])
    info = t.fast_info
    return float(info.last_price or info.regular_market_previous_close)


def df_to_records(df: pd.DataFrame) -> list:
    return [{
        "time":   int(ts.timestamp()),
        "open":   round(float(row["Open"]),  2),
        "high":   round(float(row["High"]),  2),
        "low":    round(float(row["Low"]),   2),
        "close":  round(float(row["Close"]), 2),
        "volume": int(row.get("Volume", 0)),
    } for ts, row in df.iterrows()]
