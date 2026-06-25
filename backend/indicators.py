"""
Indicateurs techniques : RSI, MACD, EMA, Bollinger Bands, ATR, VWAP, Pivots, Ichimoku.
Implementes en pur pandas/numpy pour compatibilite Python 3.14+.
"""
import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=length - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=length - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).rename("rsi")


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast    = _ema(series, fast)
    ema_slow    = _ema(series, slow)
    macd_line   = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist        = macd_line - signal_line
    return macd_line, signal_line, hist


def _bollinger(series: pd.Series, length=20, std=2.0):
    mid   = series.rolling(length).mean()
    sigma = series.rolling(length).std(ddof=0)
    return mid + std * sigma, mid, mid - std * sigma


def _atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(com=length - 1, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> pd.Series:
    tp  = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].replace(0, np.nan)
    return (tp * vol).cumsum() / vol.cumsum()


def _ichimoku(df: pd.DataFrame):
    h, l = df["High"], df["Low"]
    tenkan = (h.rolling(9).max()  + l.rolling(9).min())  / 2
    kijun  = (h.rolling(26).max() + l.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    chikou = df["Close"].shift(-26)
    return tenkan, kijun, span_a, span_b, chikou


def _pivot_points(df: pd.DataFrame) -> dict:
    if len(df) < 2:
        return {}
    p = df.iloc[-2]
    pivot = (p["High"] + p["Low"] + p["Close"]) / 3
    rang  = p["High"] - p["Low"]
    return {
        "pivot": round(float(pivot), 4),
        "r1":    round(float(2 * pivot - p["Low"]), 4),
        "r2":    round(float(pivot + rang), 4),
        "r3":    round(float(p["High"] + 2 * (pivot - p["Low"])), 4),
        "s1":    round(float(2 * pivot - p["High"]), 4),
        "s2":    round(float(pivot - rang), 4),
        "s3":    round(float(p["Low"] - 2 * (p["High"] - pivot)), 4),
    }


def _local_pivots(series: pd.Series, window: int = 5):
    arr   = series.values
    highs = [i for i in range(window, len(arr) - window)
             if arr[i] == max(arr[i - window: i + window + 1])]
    lows  = [i for i in range(window, len(arr) - window)
             if arr[i] == min(arr[i - window: i + window + 1])]
    return highs, lows


# ── API publique ─────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df    = df.copy()
    close = df["Close"]

    df["rsi"] = _rsi(close, 14)

    df["macd"], df["macd_signal"], df["macd_hist"] = _macd(close)

    df["ema9"]  = _ema(close, 9)
    df["ema21"] = _ema(close, 21)
    df["ema50"] = _ema(close, 50)

    df["bb_upper"], df["bb_mid"], df["bb_lower"] = _bollinger(close)

    df["atr"] = _atr(df)

    if "Volume" in df.columns:
        df["vwap"] = _vwap(df)

    df["ichi_tenkan"], df["ichi_kijun"], df["ichi_span_a"], df["ichi_span_b"], df["ichi_chikou"] = _ichimoku(df)

    return df


def extract_last_values(df: pd.DataFrame) -> dict:
    needed = ["rsi", "macd", "macd_signal", "macd_hist",
              "ema9", "ema21", "ema50", "bb_lower", "bb_mid", "bb_upper"]
    clean = df.dropna(subset=needed)
    if clean.empty:
        raise ValueError("Pas assez de donnees pour calculer les indicateurs.")
    row = clean.iloc[-1]

    def f(col, dec=4):
        v = row.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), dec)

    highs_idx, lows_idx = _local_pivots(df["Close"])
    recent_highs = [round(float(df["Close"].iloc[i]), 4) for i in highs_idx[-3:]]
    recent_lows  = [round(float(df["Close"].iloc[i]), 4) for i in lows_idx[-3:]]

    return {
        "close":        round(float(row["Close"]), 4),
        "rsi":          f("rsi", 2),
        "macd":         f("macd"),
        "macd_signal":  f("macd_signal"),
        "macd_hist":    f("macd_hist"),
        "ema9":         f("ema9", 2),
        "ema21":        f("ema21", 2),
        "ema50":        f("ema50", 2),
        "bb_upper":     f("bb_upper", 4),
        "bb_mid":       f("bb_mid", 4),
        "bb_lower":     f("bb_lower", 4),
        "atr":          f("atr", 4),
        "vwap":         f("vwap", 4),
        "ichi_tenkan":  f("ichi_tenkan", 4),
        "ichi_kijun":   f("ichi_kijun", 4),
        "ichi_span_a":  f("ichi_span_a", 4),
        "ichi_span_b":  f("ichi_span_b", 4),
        "pivots":       _pivot_points(df),
        "recent_highs": recent_highs,
        "recent_lows":  recent_lows,
    }


def indicators_to_series(df: pd.DataFrame) -> dict:
    def _s(col):
        if col not in df.columns:
            return []
        return [
            {"time": int(ts.timestamp()), "value": round(float(v), 4)}
            for ts, v in df[col].dropna().items()
        ]
    return {k: _s(k) for k in [
        "rsi", "macd", "macd_signal", "macd_hist",
        "ema9", "ema21", "ema50",
        "bb_lower", "bb_mid", "bb_upper",
        "atr", "vwap",
        "ichi_tenkan", "ichi_kijun", "ichi_span_a", "ichi_span_b",
    ]}
