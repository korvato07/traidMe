"""
Historique en mémoire des signaux émis. Réinitialisé au redémarrage du serveur.
Max 200 entrées par actif.
"""
from collections import deque
from threading import Lock
from datetime import datetime, timezone

class SignalHistory:
    def __init__(self, max_per_asset=200):
        self._data: dict[str, deque] = {}
        self._lock = Lock()
        self._max = max_per_asset

    def record(self, asset: str, signal: str, score: float, confidence: float, values: dict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "score": round(score, 2),
            "confidence": round(confidence, 1),
            "close": round(float(values.get("close") or 0), 4),
            "rsi": round(float(values.get("rsi") or 50), 2),
        }
        with self._lock:
            if asset not in self._data:
                self._data[asset] = deque(maxlen=self._max)
            # Ne dupliquer que si le signal ou le prix a changé
            buf = self._data[asset]
            if buf and buf[-1]["signal"] == signal and buf[-1]["close"] == entry["close"]:
                return
            buf.append(entry)

    def get(self, asset: str) -> list:
        with self._lock:
            return list(self._data.get(asset, []))

    def all_assets(self) -> dict:
        with self._lock:
            return {asset: list(deque_) for asset, deque_ in self._data.items()}


signal_history = SignalHistory()
