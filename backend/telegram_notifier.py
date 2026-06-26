"""
Envoi d'alertes Telegram sur signaux BUY/SELL.
Config via variables d'environnement (ou fichier .env) :
  TELEGRAM_TOKEN   = token du bot BotFather
  TELEGRAM_CHAT_ID = @username_chaine ou ID numerique
"""
import os
import sys
import ssl
import time
import threading
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
if sys.platform == "win32":
    ssl._create_default_https_context = ssl._create_unverified_context

# Charge .env si present (sans dependance externe)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

_SIGNAL_ICONS = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "⚪"}
_CURRENCY = {"GOLD": "USD", "BTC": "USDT", "ETH": "USDT", "ICP": "USDT",
             "XRP": "USDT", "BNB": "USDT", "SOL": "USDT"}

_last_sent: dict = {}
_lock = threading.Lock()

MIN_INTERVAL_SAME = 7200   # 2h entre deux alertes identiques
MIN_INTERVAL_ANY  = 300    # 5 min si signal change


def _post(text: str) -> bool:
    """Envoie un message brut sur la chaine."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
            verify=sys.platform != "win32",
        )
        if r.ok:
            return True
        print(f"[Telegram] Erreur {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[Telegram] Exception: {e}")
    return False


def send_startup() -> bool:
    """Message de demarrage envoye une fois au lancement du serveur."""
    ts = time.strftime("%d %b %Y — %H:%M UTC", time.gmtime())
    text = (
        "🤖 *TraidMe by KORVATO — En ligne*\n\n"
        "Surveillance active de 7 actifs :\n"
        "Au/XAU · BTC · ETH · ICP · XRP · BNB · SOL\n\n"
        f"📡 Scan toutes les 15 min\n"
        f"⏰ _{ts}_"
    )
    return _post(text)


def _should_send(asset: str, signal: str) -> bool:
    now = time.time()
    with _lock:
        prev = _last_sent.get(asset)
        if prev is None:
            return True
        elapsed = now - prev["ts"]
        if prev["signal"] == signal:
            return elapsed >= MIN_INTERVAL_SAME
        return elapsed >= MIN_INTERVAL_ANY


def _mark_sent(asset: str, signal: str):
    with _lock:
        _last_sent[asset] = {"signal": signal, "ts": time.time()}


def _fmt_price(value, asset: str) -> str:
    if value is None:
        return "—"
    if asset in ("XRP", "ICP") or value < 10:
        return f"{value:,.4f}"
    return f"{value:,.2f}"


def _build_message(asset: str, signal: str, label: str, price: float,
                   rsi: float, score: float, confidence: int,
                   stop_loss: float | None, take_profit: float | None) -> str:
    icon   = _SIGNAL_ICONS.get(signal, "⚪")
    cur    = _CURRENCY.get(asset, "USDT")
    action = "ACHAT" if signal == "BUY" else "VENTE"
    ts     = time.strftime("%d %b %Y — %H:%M UTC", time.gmtime())

    rsi_txt  = f"{rsi:.1f}" if rsi is not None else "—"
    sc_txt   = f"+{score:.2f}" if score >= 0 else f"{score:.2f}"
    conf_txt = f"{confidence}%" if confidence is not None else "—"
    pr_txt   = _fmt_price(price, asset)
    sl_txt   = _fmt_price(stop_loss,  asset) if stop_loss  else "—"
    tp_txt   = _fmt_price(take_profit, asset) if take_profit else "—"

    lines = [
        f"{icon} *SIGNAL {action} — {label}*",
        "",
        f"💰 Prix : `{pr_txt} {cur}`",
        f"📊 RSI : `{rsi_txt}` | Score : `{sc_txt}` | Confiance : `{conf_txt}`",
    ]
    if stop_loss or take_profit:
        lines += [
            "",
            f"🛡 Stop Loss : `{sl_txt} {cur}`",
            f"🎯 Take Profit : `{tp_txt} {cur}`",
        ]
    lines += ["", f"⏰ _{ts}_", "📡 TraidMe by KORVATO"]
    return "\n".join(lines)


def send_alert(
    asset: str, signal: str, label: str, price: float,
    rsi: float, score: float, confidence: int,
    stop_loss: float | None = None, take_profit: float | None = None,
) -> bool:
    """Envoie une alerte BUY/SELL. Retourne True si envoye."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if signal == "NEUTRAL":
        return False
    if not _should_send(asset, signal):
        return False

    text = _build_message(asset, signal, label, price,
                          rsi, score, confidence, stop_loss, take_profit)
    sent = _post(text)
    if sent:
        _mark_sent(asset, signal)
    return sent
