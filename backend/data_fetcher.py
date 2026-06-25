"""
Source de donnees :
  - Crypto (BTC/ETH/ICP/XRP/BNB/SOL) : Binance API public (pas de cle API)
  - Or (GOLD) : Yahoo Finance yfinance (seule source gratuite OHLCV or)
Donnees identiques a MEXC a moins de 0.2% pres (meme marche mondial).
"""
import sys
import ssl
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

BINANCE_BASE = "https://api.binance.com/api/v3"

ASSETS = {
    "GOLD": {"source": "yfinance",  "ticker": "GC=F",    "label": "XAU/USD — Gold",              "currency": "USD/oz", "icon": "⚡"},
    "BTC":  {"source": "binance",   "ticker": "BTCUSDT",  "label": "BTC/USDT — Bitcoin",          "currency": "USDT",   "icon": "₿"},
    "ETH":  {"source": "binance",   "ticker": "ETHUSDT",  "label": "ETH/USDT — Ethereum",         "currency": "USDT",   "icon": "Ξ"},
    "ICP":  {"source": "binance",   "ticker": "ICPUSDT",  "label": "ICP/USDT — Internet Computer","currency": "USDT",   "icon": "∞"},
    "XRP":  {"source": "binance",   "ticker": "XRPUSDT",  "label": "XRP/USDT — Ripple",           "currency": "USDT",   "icon": "✕"},
    "BNB":  {"source": "binance",   "ticker": "BNBUSDT",  "label": "BNB/USDT — BNB Chain",        "currency": "USDT",   "icon": "B"},
    "SOL":  {"source": "binance",   "ticker": "SOLUSDT",  "label": "SOL/USDT — Solana",           "currency": "USDT",   "icon": "◎"},
}

# Binance interval notation
_BINANCE_INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}

_INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}

_PERIOD_DAYS = {
    "1d": 1, "3d": 3, "5d": 5, "15d": 15,
    "30d": 30, "60d": 60, "90d": 90,
}

# Sessions
_b_session = requests.Session()
_b_session.verify = sys.platform != "win32"
_b_session.headers.update({"User-Agent": "TraidMe/2.0", "Accept": "application/json"})

_yf_session = requests.Session()
_yf_session.verify = sys.platform != "win32"
_yf_session.headers.update({"User-Agent": "Mozilla/5.0"})

# Cache thread-safe 55s
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


# ── Binance ───────────────────────────────────────────────────────────────

def _limit_from_period(interval: str, period: str) -> int:
    days    = _PERIOD_DAYS.get(period, 5)
    iv_ms   = _INTERVAL_MS.get(interval, 300_000)
    return min(int(days * 86_400_000 / iv_ms) + 5, 1000)


def _fetch_binance_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    b_interval = _BINANCE_INTERVAL.get(interval, interval)
    rows = []

    if limit <= 1000:
        r = _b_session.get(f"{BINANCE_BASE}/klines", params={
            "symbol": symbol, "interval": b_interval, "limit": limit,
        }, timeout=15)
        r.raise_for_status()
        rows = r.json()
    else:
        # Pagination par startTime
        iv_ms  = _INTERVAL_MS.get(interval, 300_000)
        end_ms = int(time.time() * 1000)
        cur_ms = end_ms - limit * iv_ms

        while cur_ms < end_ms and len(rows) < limit:
            batch = min(1000, limit - len(rows))
            r = _b_session.get(f"{BINANCE_BASE}/klines", params={
                "symbol": symbol, "interval": b_interval,
                "startTime": cur_ms, "limit": batch,
            }, timeout=15)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            rows.extend(data)
            cur_ms = int(data[-1][0]) + iv_ms
            if len(data) < batch:
                break
            time.sleep(0.1)

    if not rows:
        raise ValueError(f"Aucune donnee Binance pour {symbol}")

    df = pd.DataFrame(rows, columns=[
        "open_time", "Open", "High", "Low", "Close", "Volume",
        "close_time", "quote_vol", "trades", "taker_base", "taker_quote", "ignore",
    ])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)
    df.index = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.sort_index(inplace=True)
    df.dropna(inplace=True)
    return df


# ── Yahoo Finance (Or uniquement) ─────────────────────────────────────────

def _fetch_yfinance_ohlcv(ticker: str, interval: str, period: str) -> pd.DataFrame:
    obj = yf.Ticker(ticker, session=_yf_session)
    for attempt in range(3):
        try:
            df = obj.history(period=period, interval=interval, auto_adjust=True)
            if not df.empty:
                break
        except Exception as e:
            if attempt == 2:
                raise
            if "Rate" in str(e) or "Too Many" in str(e):
                time.sleep(10 * (attempt + 1))

    if df.empty:
        raise ValueError(f"Aucune donnee Yahoo Finance pour {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={c: c.capitalize() for c in df.columns})
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].copy()
    df.dropna(inplace=True)
    df.index = df.index.tz_convert("UTC") if df.index.tzinfo else df.index.tz_localize("UTC")
    df.sort_index(inplace=True)
    return df


# ── API publique ───────────────────────────────────────────────────────────

def fetch_ohlcv(interval: str = "5m", period: str = "5d", asset: str = "GOLD") -> pd.DataFrame:
    if asset not in ASSETS:
        raise ValueError(f"Asset inconnu : {asset}")

    cache_key = f"ohlcv:{asset}:{interval}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    cfg = ASSETS[asset]
    if cfg["source"] == "binance":
        limit = _limit_from_period(interval, period)
        df = _fetch_binance_klines(cfg["ticker"], interval, limit)
    else:
        df = _fetch_yfinance_ohlcv(cfg["ticker"], interval, period)

    _cache_set(cache_key, df)
    return df


def get_current_price(asset: str = "GOLD") -> float:
    cfg = ASSETS[asset]
    if cfg["source"] == "binance":
        r = _b_session.get(f"{BINANCE_BASE}/ticker/price",
                           params={"symbol": cfg["ticker"]}, timeout=8)
        r.raise_for_status()
        return float(r.json()["price"])
    else:
        obj = yf.Ticker(cfg["ticker"], session=_yf_session)
        info = obj.fast_info
        return float(info.last_price or info.regular_market_previous_close)


def df_to_records(df: pd.DataFrame) -> list:
    return [{
        "time":   int(ts.timestamp()),
        "open":   round(float(row["Open"]),  8),
        "high":   round(float(row["High"]),  8),
        "low":    round(float(row["Low"]),   8),
        "close":  round(float(row["Close"]), 8),
        "volume": round(float(row.get("Volume", 0)), 4),
    } for ts, row in df.iterrows()]
