"""
Backtesting simple : applique le moteur de signal sur les donnees historiques
et verifie si le signal s'est confirme N bougies plus tard.
"""
import numpy as np
import pandas as pd
from .indicators import compute_indicators


def _score_vectorized(df: pd.DataFrame) -> pd.Series:
    """Calcule un score scalaire pour chaque bougie (version simplifiee)."""
    rsi   = df["rsi"].fillna(50)
    macd  = df["macd"].fillna(0)
    msig  = df["macd_signal"].fillna(0)
    mhist = df["macd_hist"].fillna(0)
    e9    = df["ema9"].fillna(df["Close"])
    e21   = df["ema21"].fillna(df["Close"])
    e50   = df["ema50"].fillna(df["Close"])
    bbl   = df["bb_lower"].fillna(df["Close"])
    bbu   = df["bb_upper"].fillna(df["Close"])
    close = df["Close"]

    score = pd.Series(0.0, index=df.index)

    # RSI
    score += np.where(rsi < 25,  3.0,
             np.where(rsi < 30,  2.0,
             np.where(rsi < 40,  0.5,
             np.where(rsi > 75, -3.0,
             np.where(rsi > 70, -2.0,
             np.where(rsi > 60, -0.5, 0.0))))))

    # MACD
    bull_macd = (macd > msig) & (mhist > 0)
    bear_macd = (macd < msig) & (mhist < 0)
    score += np.where(bull_macd, 2.0, np.where(bear_macd, -2.0, 0.0))

    # EMA alignment
    score += np.where((e9 > e21) & (e21 > e50),  1.5,
             np.where((e9 < e21) & (e21 < e50), -1.5, 0.0))
    score += np.where(close > e50, 0.3, -0.3)

    # Bollinger
    bw  = bbu - bbl
    pct = np.where(bw > 0, (close - bbl) / bw, 0.5)
    score += np.where(pct < 0.05,  1.5,
             np.where(pct < 0.2,   0.8,
             np.where(pct > 0.95, -1.5,
             np.where(pct > 0.8,  -0.8, 0.0))))

    return score


def run_backtest(df_raw: pd.DataFrame, n_forward: int = 3) -> dict:
    """
    df_raw : OHLCV brut
    n_forward : combien de bougies plus tard on verifie la direction
    """
    df = compute_indicators(df_raw)
    min_rows = 60  # laisser les indicateurs se chauffer
    if len(df) < min_rows + n_forward:
        return {"error": "Pas assez de donnees pour le backtest"}

    scores  = _score_vectorized(df)
    close   = df["Close"]
    results = []

    for i in range(min_rows, len(df) - n_forward):
        sc    = float(scores.iloc[i])
        if abs(sc) < 3.0:
            continue  # NEUTRAL, on ignore
        signal    = "BUY" if sc >= 3.0 else "SELL"
        p_now     = float(close.iloc[i])
        p_later   = float(close.iloc[i + n_forward])
        pct_chg   = (p_later - p_now) / p_now * 100
        correct   = (signal == "BUY" and p_later > p_now) or (signal == "SELL" and p_later < p_now)
        results.append({"signal": signal, "correct": correct, "pct_change": round(pct_chg, 3)})

    if not results:
        return {"error": "Aucun signal BUY/SELL dans la periode"}

    total   = len(results)
    correct = sum(1 for r in results if r["correct"])
    buys    = [r for r in results if r["signal"] == "BUY"]
    sells   = [r for r in results if r["signal"] == "SELL"]

    def wr(lst):
        return round(sum(1 for r in lst if r["correct"]) / max(1, len(lst)) * 100, 1)

    def avg_gain(lst):
        pos = [abs(r["pct_change"]) for r in lst if r["correct"]]
        return round(float(np.mean(pos)), 3) if pos else 0.0

    return {
        "total_signals":   total,
        "correct_signals": correct,
        "win_rate":        round(correct / total * 100, 1),
        "buy_signals":     len(buys),
        "buy_win_rate":    wr(buys),
        "sell_signals":    len(sells),
        "sell_win_rate":   wr(sells),
        "avg_gain_pct":    avg_gain(results),
        "n_forward":       n_forward,
    }
