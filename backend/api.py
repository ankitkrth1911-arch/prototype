import os
import json
import csv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware


# ============================================================
# FASTAPI APP & CORS
# ============================================================

app = FastAPI(
    title="BRICS Healthcare AI API",
    description="Medicine Demand Forecasting and Stockout Risk API (Federated Health Resilience)",
    version="2.0.0"
)

# Allow frontend dev servers and deployed origins
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
frontend_env = os.getenv("FRONTEND_URL")
if frontend_env:
    allowed_origins.append(frontend_env.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass


# ============================================================
# HELPER: DAYS TO STOCKOUT (Safe divide-by-zero)
# ============================================================

def calculate_days_to_stockout(current_stock: float, predicted_15_day_demand: float) -> float:
    """
    Calculate days of remaining stock based on predicted 15-day demand.
    Formula: current_stock / (predicted_15_day_demand / 15)
    """
    daily_demand = predicted_15_day_demand / 15.0
    if daily_demand > 0:
        return round(current_stock / daily_demand, 2)
    return 999.0 if current_stock > 0 else 0.0


# ============================================================
# LOAD DATASETS (All trained on 1000-day SIMULATED dataset)
# ============================================================

forecast_objects_path = os.path.join(BASE_DIR, "forecast_objects.json")
with open(forecast_objects_path, "r", encoding="utf-8") as f:
    forecast_objects = json.load(f)

# Ensure days_to_stockout and pipeline shortage formula are active on all objects
for item in forecast_objects:
    stock = float(item["current_stock"])
    demand = float(item["predicted_15_day_demand"])
    safety = float(item["safety_stock"])
    # Pipeline formula: shortage = demand + safety_stock - stock
    item["expected_shortage"] = round(max(0.0, demand + safety - stock), 2)
    item["days_to_stockout"] = calculate_days_to_stockout(stock, demand)
    item["data_label"] = "Simulated"

gemini_explanations_path = os.path.join(BASE_DIR, "gemini_explanations.json")
with open(gemini_explanations_path, "r", encoding="utf-8") as f:
    gemini_explanations = json.load(f)


# ============================================================
# 1. HOME / HEALTH
# ============================================================

@app.get("/")
def home():
    index_file = os.path.join(os.path.dirname(BASE_DIR), "dist", "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "system": "BRICS Healthcare AI",
        "status": "running",
        "service": "Medicine Demand Forecasting + Stockout Risk",
        "forecast_objects": len(forecast_objects),
        "gemini_explanations": len(gemini_explanations),
        "data_label": "Simulated"
    }


@app.get("/health")
def health():
    return {
        "system": "BRICS Healthcare AI",
        "status": "running",
        "service": "Medicine Demand Forecasting + Stockout Risk",
        "forecast_objects": len(forecast_objects),
        "gemini_explanations": len(gemini_explanations),
        "data_label": "Simulated"
    }


# ============================================================
# 2. GET ALL FORECASTS
# ============================================================

@app.get("/forecasts")
def get_forecasts():
    return {
        "count": len(forecast_objects),
        "data_label": "Simulated",
        "forecasts": forecast_objects
    }


# ============================================================
# 3. GET SPECIFIC PHC + MEDICINE FORECAST
# ============================================================

@app.get("/forecast/{phc_id}/{medicine_id}")
def get_forecast(phc_id: str, medicine_id: str):
    # Case-insensitive lookup
    forecast = None
    target_phc = phc_id.strip().lower()
    target_med = medicine_id.strip().lower()

    for item in forecast_objects:
        if (
            item["phc_id"].strip().lower() == target_phc
            and item["medicine_id"].strip().lower() == target_med
        ):
            forecast = item
            break

    if forecast is None:
        raise HTTPException(
            status_code=404,
            detail=f"Forecast not found for PHC '{phc_id}' and medicine '{medicine_id}'"
        )

    # Find Gemini explanation
    explanation = None
    for item in gemini_explanations:
        if (
            item["phc_id"].strip().lower() == target_phc
            and item["medicine_id"].strip().lower() == target_med
        ):
            explanation = item.get("gemini_explanation")
            break

    stock = float(forecast["current_stock"])
    demand = float(forecast["predicted_15_day_demand"])
    safety = float(forecast["safety_stock"])
    days_to_stockout = calculate_days_to_stockout(stock, demand)

    return {
        "phc_id": forecast["phc_id"],
        "medicine_id": forecast["medicine_id"],
        "forecast_horizon": forecast["forecast_horizon"],
        "predicted_15_day_demand": forecast["predicted_15_day_demand"],
        "current_stock": forecast["current_stock"],
        "safety_stock": forecast["safety_stock"],
        "expected_shortage": forecast["expected_shortage"],
        "stock_ratio": forecast["stock_ratio"],
        "days_to_stockout": days_to_stockout,
        "risk_level": forecast["risk_level"],
        "model_version": forecast["model_version"],
        "generated_at": forecast["generated_at"],
        "model_inputs": forecast["model_inputs"],
        "top_model_drivers": forecast["top_model_drivers"],
        "risk_reasons": forecast["risk_reasons"],
        "gemini_explanation": explanation,
        "data_label": "Simulated"
    }


# ============================================================
# 4. GET RISK SUMMARY
# ============================================================

@app.get("/risk-summary")
def risk_summary():
    summary = {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0
    }

    for item in forecast_objects:
        risk = item["risk_level"]
        if risk in summary:
            summary[risk] += 1

    return {
        "total": len(forecast_objects),
        "data_label": "Simulated",
        "risk_distribution": summary
    }


# ============================================================
# 5. GET MODEL METRICS (from model_comparison.csv)
# ============================================================

@app.get("/metrics")
def get_metrics():
    metrics_path = os.path.join(BASE_DIR, "model_comparison.csv")
    if not os.path.exists(metrics_path):
        raise HTTPException(status_code=404, detail="model_comparison.csv not found")

    metrics_list = []
    with open(metrics_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            metrics_list.append({
                "model": row["model"],
                "mae": round(float(row["MAE"]), 2),
                "rmse": round(float(row["RMSE"]), 2),
                "mae_raw": float(row["MAE"]),
                "rmse_raw": float(row["RMSE"]),
            })

    return {
        "status": "success",
        "count": len(metrics_list),
        "horizon_days": 15,
        "data_label": "Simulated",
        "best_model": "XGBoost",
        "metrics": metrics_list
    }


def normalize_phc_id(phc_id: str) -> str:
    p = phc_id.strip().upper()
    mapping = {
        "PHC-184": "PHC_A",
        "PHC_184": "PHC_A",
        "PHC-072": "PHC_B",
        "PHC_072": "PHC_B",
        "PHC-091": "PHC_C",
        "PHC_091": "PHC_C",
        "PHC-115": "PHC_D",
        "PHC_115": "PHC_D",
        "PHC-054": "PHC_E",
        "PHC_054": "PHC_E",
    }
    return mapping.get(p, p)


def normalize_medicine_id(med_id: str) -> str:
    m = med_id.strip().lower()
    if "telmisartan" in m:
        return "Telmisartan"
    if "diuretic" in m or "paracetamol" in m:
        return "Diuretic"
    if "amlodipine" in m or "amoxicillin" in m:
        return "Amlodipine"
    return med_id.strip()


# ============================================================
# 6. GET /explain/{phc}/{med} - EXPLAINABLE AI (GEMINI OR CACHED)
# ============================================================

@app.get("/explain/{phc}/{med}")
def get_explanation(phc: str, med: str):
    """
    Get explanation for a specific PHC and medicine.
    Defaults to cached text from gemini_explanations.json with source="cached".
    If GEMINI_API_KEY is configured in backend/.env or environment, calls Gemini
    from backend with REAL forecast/risk numbers and returns source="gemini".
    """
    norm_phc = normalize_phc_id(phc)
    norm_med = normalize_medicine_id(med)
    target_phc = norm_phc.strip().lower()
    target_med = norm_med.strip().lower()

    # Find the corresponding real forecast object
    forecast = None
    for item in forecast_objects:
        if (
            item["phc_id"].strip().lower() == target_phc
            and item["medicine_id"].strip().lower() == target_med
        ):
            forecast = item
            break

    # If exact match not found, match by PHC
    if forecast is None:
        for item in forecast_objects:
            if item["phc_id"].strip().lower() == target_phc:
                forecast = item
                break

    # Find matching cached explanation from gemini_explanations.json
    cached_entry = None
    for item in gemini_explanations:
        if (
            item["phc_id"].strip().lower() == target_phc
            and item["medicine_id"].strip().lower() == target_med
        ):
            cached_entry = item
            break

    # If exact cached not found, match by PHC
    if cached_entry is None:
        for item in gemini_explanations:
            if item["phc_id"].strip().lower() == target_phc:
                cached_entry = item
                break

    if forecast is None and cached_entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast or explanation found for PHC '{phc}' and medicine '{med}'"
        )

    # Dynamic check for backend/.env in case it was created/modified after startup
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)
        except ImportError:
            pass

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # If GEMINI_API_KEY is set, call Gemini from backend with real numbers
    if api_key:
        try:
            try:
                from backend.gemini_explainer import explain_risk, DEFAULT_GEMINI_MODEL
            except ImportError:
                from gemini_explainer import explain_risk, DEFAULT_GEMINI_MODEL
            live_payload = forecast if forecast else cached_entry
            live_text = explain_risk(
                phc_id=live_payload["phc_id"],
                medicine_id=live_payload["medicine_id"],
                risk_result=live_payload
            )
            return {
                "phc_id": live_payload["phc_id"],
                "medicine_id": live_payload["medicine_id"],
                "explanation": live_text,
                "gemini_explanation": live_text,
                "source": "gemini",
                "model_used": os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
                "risk_level": live_payload["risk_level"],
                "predicted_15_day_demand": live_payload["predicted_15_day_demand"],
                "current_stock": live_payload["current_stock"],
                "expected_shortage": live_payload["expected_shortage"],
                "data_label": "Simulated"
            }
        except Exception as e:
            print(f"[api.py] Gemini live explanation call error: {e}. Falling back to cached text.")

    # Default to cached text from gemini_explanations.json with "source": "cached"
    if cached_entry:
        return {
            "phc_id": cached_entry["phc_id"],
            "medicine_id": cached_entry["medicine_id"],
            "explanation": cached_entry["gemini_explanation"],
            "gemini_explanation": cached_entry["gemini_explanation"],
            "source": "cached",
            "model_used": "cached-gemini-output",
            "risk_level": cached_entry["risk_level"],
            "predicted_15_day_demand": cached_entry["predicted_15_day_demand"],
            "current_stock": cached_entry["current_stock"],
            "expected_shortage": cached_entry["expected_shortage"],
            "data_label": "Simulated"
        }

    # Deterministic fallback if only forecast was found
    shortage = forecast.get("expected_shortage", 0.0)
    risk = forecast.get("risk_level", "LOW")
    fallback_text = (
        f"Risk:\n{risk}\n\n"
        f"Reason:\nCurrent stock of {forecast.get('current_stock', 0)} against predicted 15-day demand of {forecast.get('predicted_15_day_demand', 0)}.\n\n"
        f"Expected shortage:\n{shortage}\n\n"
        f"Recommended attention:\nMonitor stock levels."
    )
    return {
        "phc_id": forecast["phc_id"],
        "medicine_id": forecast["medicine_id"],
        "explanation": fallback_text,
        "gemini_explanation": fallback_text,
        "source": "cached",
        "model_used": "deterministic-fallback",
        "risk_level": risk,
        "predicted_15_day_demand": forecast.get("predicted_15_day_demand", 0.0),
        "current_stock": forecast.get("current_stock", 0.0),
        "expected_shortage": shortage,
        "data_label": "Simulated"
    }