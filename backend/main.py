from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .data_fetcher import fetch_ohlcv, df_to_records, get_current_price, ASSETS
from .indicators import compute_indicators, extract_last_values, indicators_to_series
from .signal_engine import generate_signal

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="TraidMe by KORVATO — Multi-Asset Trading Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Frontend routes ────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_gold():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/btc", include_in_schema=False)
@app.get("/icp", include_in_schema=False)
@app.get("/xrp", include_in_schema=False)
@app.get("/bnb", include_in_schema=False)
async def serve_crypto():
    return FileResponse(FRONTEND_DIR / "crypto.html")

@app.get("/algo", include_in_schema=False)
async def serve_algo():
    return FileResponse(FRONTEND_DIR / "algo.html")


# ── API helpers ────────────────────────────────────────────────────────────

def _build_analysis(asset: str, interval: str, period: str) -> dict:
    df_raw = fetch_ohlcv(interval=interval, period=period, asset=asset)
    df     = compute_indicators(df_raw)
    vals   = extract_last_values(df)
    result = generate_signal(vals)
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
            })
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset":     asset,
        "ticker":    ASSETS[asset]["ticker"],
        "forecasts": results,
    }


# ── API endpoints ──────────────────────────────────────────────────────────

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
