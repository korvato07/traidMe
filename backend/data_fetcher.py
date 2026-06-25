"""
Recuperation OHLCV via MEXC API public (sans cle API requise).
Format klines identique a Binance v3 — 12 colonnes.
Or : XAUUSDT | Crypto : BTCUSDT, ETHUSDT, ICPUSDT, XRPUSDT, BNBUSDT, SOLUSDT
"""
import sys
import ssl
import time
import warnings
import threading
import urllib3
import requests
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

if sys.platform == "win32":
    ssl._create_default_https_context = ssl._create_unverified_context

MEXC_BASE = "https://api.mexc.com/api/v3"

ASSETS = {
    "GOLD": {"ticker": "XAUUSDT", "label": "XAU/USD — Gold",              "currency": "USD/oz", "icon": "⚡"},
    "BTC":  {"ticker": "BTCUSDT", "label": "BTC/USDT — Bitcoin",          "currency": "USDT",   "icon": "₿"},
    "ETH":  {"ticker": "ETHUSDT", "label": "ETH/USDT — Ethereum",         "currency": "USDT",   "icon": "Ξ"},
    "ICP":  {"ticker": "ICPUSDT", "label": "ICP/USDT — Internet Computer","currency": "USDT",   "icon": "∞"},
    "XRP":  {"ticker": "XRPUSDT", "label": "XRP/USDT — Ripple",           "currency": "USDT",   "icon": "✕"},
    "BNB":  {"ticker": "BNBUSDT", "label": "BNB/USDT — BNB Chain",        "currency": "USDT",   "icon": "B"},
    "SOL":  {"ticker": "SOLUSDT", "label": "SOL/USDT — Solana",           "currency": "USDT",   "icon": "◎"},
}

# MEXC utilise "60m" pas "1h"
_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "60m", "60m": "60m", "4h": "4h", "1d": "1d",
}

_INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "60m": 3_600_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}

_PERIOD_DAYS = {
    "1d": 1, "3d": 3, "5d": 5, "15d": 15,
    "30d": 30, "60d": 60, "90d": 90,
}

_session = requests.Session()
_session.verify = sys.platform != "win32"
_session.headers.update({
    "User-Agent": "TraidMe/2.0",
    "Accept": "application/json",
})

_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 55


def _cache_get(key):
    with _cache_lock:
        e = _cache.get(key)
        if e and time.time() - e["ts"] < CACHE_TTL:
            return e["data"]
    return None


def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _limit_from_period(interval: str, period: str) -> int:
    days = _PERIOD_DAYS.get(period, 5)
    mexc_iv = _INTERVAL_MAP.get(interval, interval)
    iv_ms = _INTERVAL_MS.get(mexc_iv, _INTERVAL_MS.get(interval, 300_000))
    return int(days * 86_400_000 / iv_ms) + 5


def _fetch_klines(symbol: str, mexc_interval: str, limit: int) -> list:
    """Appel MEXC /klines avec pagination si limit > 1000."""
    MAX = 1000
    iv_ms = _INTERVAL_MS.get(mexc_interval, 300_000)

    if limit <= MAX:
        r = _session.get(f"{MEXC_BASE}/klines", params={
            "symbol": symbol, "interval": mexc_interval, "limit": limit,
        }, timeout=15)
        r.raise_for_status()
        return r.json()

    # Pagination par startTime/endTime
    end_ms   = int(time.time() * 1000)
    start_ms = end_ms - limit * iv_ms
    all_rows = []

    while start_ms < end_ms and len(all_rows) < limit:
        batch_end = min(start_ms + MAX * iv_ms, end_ms)
        r = _session.get(f"{MEXC_BASE}/klines", params={
            "symbol": symbol, "interval": mexc_interval,
            "startTime": start_ms, "endTime": batch_end,
            "limit": MAX,
        }, timeout=15)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_rows.extend(batch)
        start_ms = int(batch[-1][0]) + iv_ms
        if len(batch) < MAX:
            break
        time.sleep(0.15)

    return all_rows


def fetch_ohlcv(interval: str = "5m", period: str = "5d", asset: str = "GOLD") -> pd.DataFrame:
    if asset not in ASSETS:
        raise ValueError(f"Asset inconnu : {asset}")

    cache_key = f"ohlcv:{asset}:{interval}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    symbol       = ASSETS[asset]["ticker"]
    mexc_interval = _INTERVAL_MAP.get(interval, interval)
    limit        = _limit_from_period(interval, period)

    rows = _fetch_klines(symbol, mexc_interval, limit)
    if not rows:
        raise ValueError(f"Aucune donnee MEXC pour {symbol}")

    # Colonnes MEXC/Binance klines : index 0-11
    df = pd.DataFrame(rows, columns=[
        "open_time", "Open", "High", "Low", "Close", "Volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)

    df.index = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    df.sort_index(inplace=True)

    _cache_set(cache_key, df)
    return df


def get_current_price(asset: str = "GOLD") -> float:
    symbol = ASSETS[asset]["ticker"]
    r = _session.get(f"{MEXC_BASE}/ticker/price",
                     params={"symbol": symbol}, timeout=8)
    r.raise_for_status()
    return float(r.json()["price"])


def df_to_records(df: pd.DataFrame) -> list:
    return [{
        "time":   int(ts.timestamp()),
        "open":   round(float(row["Open"]),  8),
        "high":   round(float(row["High"]),  8),
        "low":    round(float(row["Low"]),   8),
        "close":  round(float(row["Close"]), 8),
        "volume": round(float(row.get("Volume", 0)), 4),
    } for ts, row in df.iterrows()]
