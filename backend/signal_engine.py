from __future__ import annotations
from dataclasses import dataclass


HORIZON_LABELS = {
    "5m":  "30 min",
    "15m": "1 heure",
    "30m": "2 heures",
}


@dataclass
class SignalResult:
    signal:      str
    score:       float
    reasons:     list[str]
    explanation: str
    confidence:  int
    stop_loss:   float | None = None
    take_profit: float | None = None


def _score_rsi(vals: dict, reasons: list) -> float:
    rsi = vals.get("rsi") or 50
    if rsi < 25:
        reasons.append(f"RSI en survente extreme a {rsi:.1f} (< 25) => Pression acheteuse forte imminente")
        return 3.0
    elif rsi < 30:
        reasons.append(f"RSI en survente a {rsi:.1f} (< 30) => Signal haussier")
        return 2.0
    elif rsi < 40:
        reasons.append(f"RSI faible a {rsi:.1f} => Tendance baissiere moderee")
        return 0.5
    elif rsi > 75:
        reasons.append(f"RSI en surachat extreme a {rsi:.1f} (> 75) => Correction probable")
        return -3.0
    elif rsi > 70:
        reasons.append(f"RSI en surachat a {rsi:.1f} (> 70) => Signal baissier")
        return -2.0
    elif rsi > 60:
        reasons.append(f"RSI eleve a {rsi:.1f} => Tendance haussiere moderee")
        return -0.5
    return 0.0


def _score_macd(vals: dict, reasons: list) -> float:
    macd = vals.get("macd") or 0
    sig  = vals.get("macd_signal") or 0
    hist = vals.get("macd_hist") or 0
    score = 0.0
    if macd > sig and hist > 0:
        if hist > abs(macd) * 0.1:
            reasons.append(f"MACD haussier ({macd:.4f} > signal {sig:.4f}) avec histogramme positif => Elan acheteur")
            score += 2.0
        else:
            reasons.append(f"MACD legerement haussier => Elan faible")
            score += 0.8
    elif macd < sig and hist < 0:
        if abs(hist) > abs(macd) * 0.1:
            reasons.append(f"MACD baissier ({macd:.4f} < signal {sig:.4f}) avec histogramme negatif => Elan vendeur")
            score -= 2.0
        else:
            reasons.append(f"MACD legerement baissier => Elan faible")
            score -= 0.8
    return score


def _score_ema(vals: dict, reasons: list) -> float:
    e9, e21, e50 = vals.get("ema9") or 0, vals.get("ema21") or 0, vals.get("ema50") or 0
    close = vals.get("close") or 0
    score = 0.0
    if e9 > e21 > e50:
        reasons.append(f"Alignement EMA haussier : EMA9({e9:.2f}) > EMA21({e21:.2f}) > EMA50({e50:.2f}) => Tendance montante confirmee")
        score += 1.5
    elif e9 < e21 < e50:
        reasons.append(f"Alignement EMA baissier : EMA9({e9:.2f}) < EMA21({e21:.2f}) < EMA50({e50:.2f}) => Tendance descendante confirmee")
        score -= 1.5
    else:
        reasons.append(f"EMA mixte (e9={e9:.2f}, e21={e21:.2f}, e50={e50:.2f}) => Pas de tendance claire")
    score += 0.3 if close > e50 else -0.3
    return score


def _score_bollinger(vals: dict, reasons: list) -> float:
    close = vals.get("close") or 0
    bbl   = vals.get("bb_lower") or 0
    bbu   = vals.get("bb_upper") or 0
    bbm   = vals.get("bb_mid") or 0
    bw    = bbu - bbl
    if bw <= 0:
        return 0.0
    pct = (close - bbl) / bw
    if pct < 0.05:
        reasons.append(f"Prix ({close:.4f}) touche la bande Bollinger basse ({bbl:.4f}) => Rebond potentiel")
        return 1.5
    elif pct < 0.2:
        reasons.append(f"Prix proche de la bande Bollinger basse ({bbl:.4f}) => Possible support")
        return 0.8
    elif pct > 0.95:
        reasons.append(f"Prix ({close:.4f}) touche la bande Bollinger haute ({bbu:.4f}) => Resistance/retournement possible")
        return -1.5
    elif pct > 0.8:
        reasons.append(f"Prix proche de la bande Bollinger haute ({bbu:.4f}) => Zone de prudence")
        return -0.8
    return 0.0


def _score_ichimoku(vals: dict, reasons: list) -> float:
    close   = vals.get("close") or 0
    tenkan  = vals.get("ichi_tenkan")
    kijun   = vals.get("ichi_kijun")
    span_a  = vals.get("ichi_span_a")
    span_b  = vals.get("ichi_span_b")
    if not all([tenkan, kijun]):
        return 0.0
    score = 0.0
    if tenkan > kijun:
        reasons.append(f"Ichimoku : Tenkan ({tenkan:.4f}) > Kijun ({kijun:.4f}) => Impulsion haussiere")
        score += 0.5
    elif tenkan < kijun:
        reasons.append(f"Ichimoku : Tenkan ({tenkan:.4f}) < Kijun ({kijun:.4f}) => Impulsion baissiere")
        score -= 0.5
    if span_a and span_b:
        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        if close > cloud_top:
            reasons.append(f"Prix au-dessus du nuage Ichimoku => Tendance haussiere forte")
            score += 0.8
        elif close < cloud_bot:
            reasons.append(f"Prix en-dessous du nuage Ichimoku => Tendance baissiere forte")
            score -= 0.8
    return score


def _compute_risk_levels(vals: dict, signal: str):
    close = vals.get("close") or 0
    atr   = vals.get("atr")
    if not atr or atr <= 0 or close <= 0:
        return None, None
    if signal == "BUY":
        sl = round(close - 2 * atr, 4)
        tp = round(close + 3 * atr, 4)
    elif signal == "SELL":
        sl = round(close + 2 * atr, 4)
        tp = round(close - 3 * atr, 4)
    else:
        return None, None
    return sl, tp


def generate_signal(vals: dict, horizon_label: str = "") -> SignalResult:
    reasons: list[str] = []
    score = 0.0

    score += _score_rsi(vals, reasons)
    score += _score_macd(vals, reasons)
    score += _score_ema(vals, reasons)
    score += _score_bollinger(vals, reasons)
    score += _score_ichimoku(vals, reasons)

    score = round(score, 2)

    if score >= 3.0:
        signal     = "BUY"
        confidence = min(100, int(50 + score * 8))
    elif score <= -3.0:
        signal     = "SELL"
        confidence = min(100, int(50 + abs(score) * 8))
    else:
        signal     = "NEUTRAL"
        confidence = max(20, int(50 - abs(score) * 10))

    sl, tp = _compute_risk_levels(vals, signal)
    explanation = _build_explanation(signal, score, reasons, vals, horizon_label, sl, tp)

    return SignalResult(
        signal=signal,
        score=score,
        reasons=reasons,
        explanation=explanation,
        confidence=confidence,
        stop_loss=sl,
        take_profit=tp,
    )


def _build_explanation(signal, score, reasons, vals, horizon_label, sl, tp) -> str:
    h = f" [{horizon_label}]" if horizon_label else ""
    header = {
        "BUY":     f"Signal ACHAT{h} (score: +{score:.1f})",
        "SELL":    f"Signal VENTE{h} (score: {score:.1f})",
        "NEUTRAL": f"Signal NEUTRE{h} (score: {score:.1f})",
    }[signal]

    lines = [header, "", "Facteurs detectes :"]
    for i, r in enumerate(reasons, 1):
        lines.append(f"  {i}. {r}")

    lines += [
        "",
        f"Prix actuel : {vals.get('close', 0):.4f}",
        f"RSI : {vals.get('rsi', 0):.1f}  |  MACD : {vals.get('macd', 0):.4f}  |  Signal MACD : {vals.get('macd_signal', 0):.4f}",
        f"EMA9 : {vals.get('ema9', 0):.4f}  |  EMA21 : {vals.get('ema21', 0):.4f}  |  EMA50 : {vals.get('ema50', 0):.4f}",
        f"Bollinger : [{vals.get('bb_lower', 0):.4f} - {vals.get('bb_mid', 0):.4f} - {vals.get('bb_upper', 0):.4f}]",
    ]
    atr = vals.get("atr")
    if atr:
        lines.append(f"ATR (14) : {atr:.4f}")
    if sl:
        lines.append(f"Stop Loss suggere : {sl:.4f}  |  Take Profit suggere : {tp:.4f}")

    conclusion = {
        "BUY":     "=> Conclusion : Les indicateurs convergent vers une opportunite d'ACHAT. Envisager une entree long avec stop sous EMA50.",
        "SELL":    "=> Conclusion : Les indicateurs convergent vers une opportunite de VENTE. Envisager une entree short avec stop au-dessus de EMA50.",
        "NEUTRAL": "=> Conclusion : Signal ambigu. Attendre une confirmation supplementaire avant d'agir.",
    }[signal]
    lines += ["", conclusion]
    return "\n".join(lines)
