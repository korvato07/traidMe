from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import asyncio
import concurrent.futures

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .data_fetcher import fetch_ohlcv, df_to_records, get_current_price, ASSETS
from .indicators   import compute_indicators, extract_last_values, indicators_to_series
from .signal_engine import generate_signal
from .history_store import signal_history
from .backtester    import run_backtest
from .telegram_notifier import send_alert, send_startup

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
ALERT_INTERVAL = 15 * 60  # 15 minutes


async def _alert_scanner():
    """Tache de fond : scan tous les assets toutes les 15 min et envoie les alertes."""
    await asyncio.sleep(30)  # attendre que le serveur soit pret
    loop = asyncio.get_event_loop()
    while True:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                futs = {ex.submit(_build_summary, a): a for a in ASSETS}
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        fut.result()
                    except Exception as e:
                        print(f"[Scanner] {futs[fut]}: {e}")
        except Exception as e:
            print(f"[Scanner] Erreur globale: {e}")
        await asyncio.sleep(ALERT_INTERVAL)


@asynccontextmanager
async def lifespan(app):
    send_startup()
    task = asyncio.create_task(_alert_scanner())
    yield
    task.cancel()


app = FastAPI(title="TraidMe by KORVATO — Multi-Asset Trading Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pages HTML ─────────────────────────────────────────────────────────────

@app.get("/",           include_in_schema=False)
async def serve_gold():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/btc",        include_in_schema=False)
@app.get("/eth",        include_in_schema=False)
@app.get("/icp",        include_in_schema=False)
@app.get("/xrp",        include_in_schema=False)
@app.get("/bnb",        include_in_schema=False)
@app.get("/sol",        include_in_schema=False)
async def serve_crypto():
    return FileResponse(FRONTEND_DIR / "crypto.html")

@app.get("/dashboard",  include_in_schema=False)
async def serve_dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/history",    include_in_schema=False)
async def serve_history_page():
    return FileResponse(FRONTEND_DIR / "history.html")

@app.get("/algo",       include_in_schema=False)
async def serve_algo():
    return FileResponse(FRONTEND_DIR / "algo.html")

# Fichiers PWA servis a la racine
@app.get("/manifest.json", include_in_schema=False)
async def serve_manifest():
    return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/sw.js",         include_in_schema=False)
async def serve_sw():
    return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")


# ── Core helpers ────────────────────────────────────────────────────────────

def _build_analysis(asset: str, interval: str, period: str) -> dict:
    df_raw = fetch_ohlcv(interval=interval, period=period, asset=asset)
    df     = compute_indicators(df_raw)
    vals   = extract_last_values(df)
    result = generate_signal(vals)

    signal_history.record(asset, result.signal, result.score, result.confidence, vals)

    send_alert(
        asset=asset, signal=result.signal, label=ASSETS[asset]["label"],
        price=vals.get("close"), rsi=vals.get("rsi"),
        score=result.score, confidence=result.confidence,
        stop_loss=result.stop_loss, take_profit=result.take_profit,
    )

    return {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "asset":       asset,
        "ticker":      ASSETS[asset]["ticker"],
        "label":       ASSETS[asset]["label"],
        "interval":    interval,
        "candles":     df_to_records(df_raw),
        "indicators":  indicators_to_series(df),
        "values":      vals,
        "signal":      result.signal,
        "score":       result.score,
        "confidence":  result.confidence,
        "reasons":     result.reasons,
        "explanation": result.explanation,
        "stop_loss":   result.stop_loss,
        "take_profit": result.take_profit,
    }


def _build_forecast(asset: str) -> dict:
    horizons = [
        {"interval": "5m",  "period": "5d",  "label": "30 min"},
        {"interval": "15m", "period": "5d",  "label": "1 heure"},
        {"interval": "30m", "period": "60d", "label": "2 heures"},
    ]
    results = []
    for h in horizons:
        try:
            df_raw = fetch_ohlcv(interval=h["interval"], period=h["period"], asset=asset)
            df     = compute_indicators(df_raw)
            vals   = extract_last_values(df)
            result = generate_signal(vals, horizon_label=h["label"])
            results.append({
                "horizon":     h["label"],
                "interval":    h["interval"],
                "signal":      result.signal,
                "score":       result.score,
                "confidence":  result.confidence,
                "reasons":     result.reasons,
                "explanation": result.explanation,
                "values":      vals,
                "stop_loss":   result.stop_loss,
                "take_profit": result.take_profit,
            })
        except Exception as exc:
            results.append({
                "horizon":     h["label"],
                "interval":    h["interval"],
                "signal":      "ERROR",
                "score":       0,
                "confidence":  0,
                "reasons":     [str(exc)],
                "explanation": f"Erreur : {exc}",
                "values":      {},
                "stop_loss":   None,
                "take_profit": None,
            })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset":     asset,
        "ticker":    ASSETS[asset]["ticker"],
        "forecasts": results,
    }


def _build_summary(asset: str) -> dict:
    """Resume leger pour le dashboard (pas de candles)."""
    df_raw = fetch_ohlcv(interval="15m", period="5d", asset=asset)
    df     = compute_indicators(df_raw)
    vals   = extract_last_values(df)
    result = generate_signal(vals)
    signal_history.record(asset, result.signal, result.score, result.confidence, vals)

    send_alert(
        asset=asset, signal=result.signal, label=ASSETS[asset]["label"],
        price=vals.get("close"), rsi=vals.get("rsi"),
        score=result.score, confidence=result.confidence,
        stop_loss=result.stop_loss, take_profit=result.take_profit,
    )

    return {
        "asset":      asset,
        "label":      ASSETS[asset]["label"],
        "icon":       ASSETS[asset].get("icon", ""),
        "currency":   ASSETS[asset]["currency"],
        "close":      vals["close"],
        "rsi":        vals["rsi"],
        "signal":     result.signal,
        "score":      result.score,
        "confidence": result.confidence,
        "atr":        vals.get("atr"),
        "stop_loss":  result.stop_loss,
        "take_profit":result.take_profit,
    }


# ── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/analysis")
async def get_analysis(
    asset:    str = Query("GOLD"),
    interval: str = Query("5m"),
    period:   str = Query("5d"),
):
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}. Valeurs : {list(ASSETS)}")
    try:
        return JSONResponse(_build_analysis(asset, interval, period))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/forecast")
async def get_forecast(asset: str = Query("GOLD")):
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}")
    try:
        return JSONResponse(_build_forecast(asset))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/price")
async def get_price(asset: str = Query("GOLD")):
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}")
    try:
        return JSONResponse({
            "asset":     asset,
            "ticker":    ASSETS[asset]["ticker"],
            "price":     get_current_price(asset),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/assets")
async def get_assets():
    return JSONResponse({"assets": list(ASSETS.keys()), "details": ASSETS})


@app.get("/api/dashboard")
async def get_dashboard():
    """Fetche les 7 actifs et retourne un resume global."""
    loop = asyncio.get_event_loop()
    assets = list(ASSETS.keys())

    def fetch_one(a):
        try:
            return _build_summary(a)
        except Exception as e:
            return {"asset": a, "error": str(e), "signal": "ERROR", "close": None}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        summaries = list(await loop.run_in_executor(
            None,
            lambda: [pool.submit(fetch_one, a).result() for a in assets]
        ))

    return JSONResponse({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assets":    summaries,
    })


@app.get("/api/history")
async def get_history(asset: str = Query("ALL")):
    if asset == "ALL":
        return JSONResponse(signal_history.all_assets())
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}")
    return JSONResponse({asset: signal_history.get(asset)})


@app.get("/api/test_alert")
async def test_alert(asset: str = Query("BTC")):
    """Envoie une alerte test sur Telegram pour verifier la configuration."""
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}")
    try:
        df  = fetch_ohlcv("15m", "5d", asset)
        df2 = compute_indicators(df)
        vals = extract_last_values(df2)
        result = generate_signal(vals)
        from .telegram_notifier import _post, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            return JSONResponse({"ok": False, "error": "TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant"})
        ts = __import__("time").strftime("%d %b %Y — %H:%M UTC", __import__("time").gmtime())
        ok = _post(
            f"🧪 *Test alerte — {ASSETS[asset]['label']}*\n\n"
            f"Signal : `{result.signal}` | Score : `{result.score:.2f}`\n"
            f"Prix : `{vals.get('close')} {ASSETS[asset]['currency']}`\n\n"
            f"⏰ _{ts}_\n📡 TraidMe by KORVATO"
        )
        return JSONResponse({"ok": ok, "signal": result.signal, "asset": asset})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/backtest")
async def get_backtest(
    asset:     str = Query("BTC"),
    interval:  str = Query("1h"),
    period:    str = Query("60d"),
    n_forward: int = Query(3),
):
    if asset not in ASSETS:
        raise HTTPException(400, f"Asset inconnu : {asset}")
    try:
        df_raw  = fetch_ohlcv(interval=interval, period=period, asset=asset)
        results = run_backtest(df_raw, n_forward=n_forward)
        results["asset"]    = asset
        results["interval"] = interval
        results["period"]   = period
        return JSONResponse(results)
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{asset}")
async def websocket_endpoint(websocket: WebSocket, asset: str):
    if asset not in ASSETS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                data = await loop.run_in_executor(
                    None, lambda: _build_analysis(asset, "5m", "5d")
                )
                await websocket.send_json(data)
            except Exception as e:
                await websocket.send_json({"error": str(e)})
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
