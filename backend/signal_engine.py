from __future__ import annotations
from dataclasses import dataclass, field


HORIZON_LABELS = {
    "5m":  "30 min",
    "15m": "1 heure",
    "30m": "2 heures",
}


@dataclass
class SignalResult:
    signal: str          # "BUY" | "SELL" | "NEUTRAL"
    score: float
    reasons: list[str]
    explanation: str
    confidence: int      # 0-100


def _score_rsi(vals: dict, reasons: list) -> float:
    rsi = vals["rsi"]
    if rsi < 25:
        reasons.append(f"RSI en survente extreme a {rsi:.1f} (< 25) → Pression acheteuse forte imminente")
        return 3.0
    elif rsi < 30:
        reasons.append(f"RSI en survente a {rsi:.1f} (< 30) → Signal haussier")
        return 2.0
    elif rsi < 40:
        reasons.append(f"RSI faible a {rsi:.1f} → Tendance baissiere moderee")
        return 0.5
    elif rsi > 75:
        reasons.append(f"RSI en surachat extreme a {rsi:.1f} (> 75) → Correction probable")
        return -3.0
    elif rsi > 70:
        reasons.append(f"RSI en surachat a {rsi:.1f} (> 70) → Signal baissier")
        return -2.0
    elif rsi > 60:
        reasons.append(f"RSI eleve a {rsi:.1f} → Tendance haussiere moderee")
        return -0.5
    return 0.0


def _score_macd(vals: dict, reasons: list) -> float:
    macd = vals["macd"]
    sig  = vals["macd_signal"]
    hist = vals["macd_hist"]
    score = 0.0

    if macd > sig and hist > 0:
        if hist > abs(macd) * 0.1:
            reasons.append(f"MACD haussier ({macd:.4f} > signal {sig:.4f}) avec histogramme positif → Elan acheteur")
            score += 2.0
        else:
            reasons.append(f"MACD legerement haussier → Elan faible")
            score += 0.8
    elif macd < sig and hist < 0:
        if abs(hist) > abs(macd) * 0.1:
            reasons.append(f"MACD baissier ({macd:.4f} < signal {sig:.4f}) avec histogramme negatif → Elan vendeur")
            score -= 2.0
        else:
            reasons.append(f"MACD legerement baissier → Elan faible")
            score -= 0.8

    # Croisement recent (histogramme change de signe sur les 3 dernières bougies)
    return score


def _score_ema(vals: dict, reasons: list) -> float:
    e9, e21, e50 = vals["ema9"], vals["ema21"], vals["ema50"]
    close = vals["close"]
    score = 0.0

    if e9 > e21 > e50:
        reasons.append(f"Alignement EMA haussier : EMA9({e9:.2f}) > EMA21({e21:.2f}) > EMA50({e50:.2f}) → Tendance montante confirmee")
        score += 1.5
    elif e9 < e21 < e50:
        reasons.append(f"Alignement EMA baissier : EMA9({e9:.2f}) < EMA21({e21:.2f}) < EMA50({e50:.2f}) → Tendance descendante confirmee")
        score -= 1.5
    else:
        reasons.append(f"EMA en configuration mixte (e9={e9:.2f}, e21={e21:.2f}, e50={e50:.2f}) → Pas de tendance claire")

    # Prix vs EMA50
    if close > e50:
        score += 0.3
    else:
        score -= 0.3

    return score


def _score_bollinger(vals: dict, reasons: list) -> float:
    close    = vals["close"]
    bb_lower = vals["bb_lower"]
    bb_upper = vals["bb_upper"]
    bb_mid   = vals["bb_mid"]
    score = 0.0
    bandwidth = bb_upper - bb_lower

    if bandwidth > 0:
        pct = (close - bb_lower) / bandwidth  # 0 = bande basse, 1 = bande haute
        if pct < 0.05:
            reasons.append(f"Prix ({close:.2f}) touche la bande Bollinger basse ({bb_lower:.2f}) → Rebond potentiel")
            score += 1.5
        elif pct < 0.2:
            reasons.append(f"Prix proche de la bande Bollinger basse ({bb_lower:.2f}) → Possible support")
            score += 0.8
        elif pct > 0.95:
            reasons.append(f"Prix ({close:.2f}) touche la bande Bollinger haute ({bb_upper:.2f}) → Resistance/retournement possible")
            score -= 1.5
        elif pct > 0.8:
            reasons.append(f"Prix proche de la bande Bollinger haute ({bb_upper:.2f}) → Zone de prudence")
            score -= 0.8

    return score


def generate_signal(vals: dict, horizon_label: str = "") -> SignalResult:
    reasons: list[str] = []
    score = 0.0

    score += _score_rsi(vals, reasons)
    score += _score_macd(vals, reasons)
    score += _score_ema(vals, reasons)
    score += _score_bollinger(vals, reasons)

    score = round(score, 2)

    if score >= 3.0:
        signal = "BUY"
        confidence = min(100, int(50 + score * 8))
    elif score <= -3.0:
        signal = "SELL"
        confidence = min(100, int(50 + abs(score) * 8))
    else:
        signal = "NEUTRAL"
        confidence = max(20, int(50 - abs(score) * 10))

    horizon_str = f" [{horizon_label}]" if horizon_label else ""
    explanation = _build_explanation(signal, score, reasons, vals, horizon_str)

    return SignalResult(
        signal=signal,
        score=score,
        reasons=reasons,
        explanation=explanation,
        confidence=confidence,
    )


def _build_explanation(signal: str, score: float, reasons: list, vals: dict, horizon_str: str) -> str:
    header = {
        "BUY":     f"Signal ACHAT{horizon_str} (score: +{score:.1f})",
        "SELL":    f"Signal VENTE{horizon_str} (score: {score:.1f})",
        "NEUTRAL": f"Signal NEUTRE{horizon_str} (score: {score:.1f})",
    }[signal]

    lines = [header, ""]
    lines.append("Facteurs detectes :")
    for i, r in enumerate(reasons, 1):
        lines.append(f"  {i}. {r}")

    lines.append("")
    lines.append(f"Prix actuel : {vals['close']:.2f} USD/oz")
    lines.append(f"RSI : {vals['rsi']:.1f}  |  MACD : {vals['macd']:.4f}  |  Signal MACD : {vals['macd_signal']:.4f}")
    lines.append(f"EMA9 : {vals['ema9']:.2f}  |  EMA21 : {vals['ema21']:.2f}  |  EMA50 : {vals['ema50']:.2f}")
    lines.append(f"Bollinger : [{vals['bb_lower']:.2f} — {vals['bb_mid']:.2f} — {vals['bb_upper']:.2f}]")

    conclusion = {
        "BUY":     "→ Conclusion : Les indicateurs convergent vers une opportunite d'ACHAT. Envisager une entree long avec stop sous EMA50.",
        "SELL":    "→ Conclusion : Les indicateurs convergent vers une opportunite de VENTE. Envisager une entree short avec stop au-dessus de EMA50.",
        "NEUTRAL": "→ Conclusion : Signal ambigu. Attendre une confirmation supplementaire avant d'agir.",
    }[signal]

    lines.append("")
    lines.append(conclusion)
    return "\n".join(lines)
