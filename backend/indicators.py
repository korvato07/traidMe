"""
Indicateurs techniques implémentés en pur pandas/numpy.
Compatible Python 3.14+ sans pandas-ta.
"""
import pandas as pd
import numpy as np


# ── EMA ────────────────────────────────────────────────────────────────────
def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


# ── RSI ────────────────────────────────────────────────────────────────────
def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=length - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=length - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).rename("rsi")


# ── MACD ───────────────────────────────────────────────────────────────────
def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast   = _ema(series, fast)
    ema_slow   = _ema(series, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist       = macd_line - signal_line
    return macd_line, signal_line, hist


# ── Bollinger Bands ────────────────────────────────────────────────────────
def _bollinger(series: pd.Series, length: int = 20, std: float = 2.0):
    mid   = series.rolling(length).mean()
    sigma = series.rolling(length).std(ddof=0)
    upper = mid + std * sigma
    lower = mid - std * sigma
    return upper, mid, lower


# ── Compute All ────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    df["rsi"]   = _rsi(close, 14)

    macd_line, sig_line, hist = _macd(close, 12, 26, 9)
    df["macd"]        = macd_line
    df["macd_signal"] = sig_line
    df["macd_hist"]   = hist

    df["ema9"]  = _ema(close, 9)
    df["ema21"] = _ema(close, 21)
    df["ema50"] = _ema(close, 50)

    bb_upper, bb_mid, bb_lower = _bollinger(close, 20, 2.0)
    df["bb_upper"] = bb_upper
    df["bb_mid"]   = bb_mid
    df["bb_lower"] = bb_lower

    return df


def extract_last_values(df: pd.DataFrame) -> dict:
    needed = ["rsi", "macd", "macd_signal", "macd_hist",
              "ema9", "ema21", "ema50", "bb_lower", "bb_mid", "bb_upper"]
    clean  = df.dropna(subset=needed)
    if clean.empty:
        raise ValueError("Pas assez de données pour calculer les indicateurs.")
    row = clean.iloc[-1]
    return {
        "close":       round(float(row["Close"]),       2),
        "rsi":         round(float(row["rsi"]),         2),
        "macd":        round(float(row["macd"]),        4),
        "macd_signal": round(float(row["macd_signal"]), 4),
        "macd_hist":   round(float(row["macd_hist"]),   4),
        "ema9":        round(float(row["ema9"]),        2),
        "ema21":       round(float(row["ema21"]),       2),
        "ema50":       round(float(row["ema50"]),       2),
        "bb_lower":    round(float(row["bb_lower"]),    2),
        "bb_mid":      round(float(row["bb_mid"]),      2),
        "bb_upper":    round(float(row["bb_upper"]),    2),
    }


def indicators_to_series(df: pd.DataFrame) -> dict:
    def _s(col):
        return [
            {"time": int(ts.timestamp()), "value": round(float(v), 4)}
            for ts, v in df[col].dropna().items()
        ]

    return {
        "rsi":         _s("rsi"),
        "macd":        _s("macd"),
        "macd_signal": _s("macd_signal"),
        "macd_hist":   _s("macd_hist"),
        "ema9":        _s("ema9"),
        "ema21":       _s("ema21"),
        "ema50":       _s("ema50"),
        "bb_lower":    _s("bb_lower"),
        "bb_mid":      _s("bb_mid"),
        "bb_upper":    _s("bb_upper"),
    }
