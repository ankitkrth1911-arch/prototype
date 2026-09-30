/**
 * apiService.ts — Backend API client for PHC Federated AI Platform
 *
 * Routes that exist on the REAL backend (http://localhost:8000):
 *   GET /forecasts               → all 15 ForecastObjects
 *   GET /forecast/{phc}/{med}    → single ForecastObject + Gemini explanation
 *   GET /risk-summary            → { total, risk_distribution, data_label }
 *   GET /metrics                 → model comparison table from CSV
 *
 * When VITE_API_BASE_URL is not set, all methods fall back to mock data
 * and isOfflineMode() returns true.
 */

import { adaptForecastObjects } from './backendAdapter';
import type { PHCNodeData, RiskRadarItem } from '../types/decision';

// ─── Configuration ─────────────────────────────────────────────────────────
// Supports VITE_API_URL or VITE_API_BASE_URL; defaults to "" in production (same domain)
const rawApiUrl = (
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  ''
).trim().replace(/\/$/, '');

// Form API base path: in same domain or with Vite proxy, use relative /api
export const API_BASE = rawApiUrl
  ? (rawApiUrl.startsWith('http://') || rawApiUrl.startsWith('https://') ? `${rawApiUrl}/api` : `https://${rawApiUrl}/api`)
  : '/api';

let liveConnectionActive = true;
export const isOfflineMode = () => !liveConnectionActive;

// ─── Raw backend types (what FastAPI returns) ───────────────────────────────
export interface BackendForecast {
  phc_id: string;
  medicine_id: string;
  forecast_horizon: string;
  predicted_15_day_demand: number;
  current_stock: number;
  safety_stock: number;
  expected_shortage: number;
  stock_ratio: number;
  days_to_stockout: number;
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW';
  model_version: string;
  generated_at: string;
  model_inputs: Record<string, number>;
  top_model_drivers: { feature: string; impact: number; direction: string }[];
  risk_reasons: string[];
  gemini_explanation?: string;
  data_label: string;
}

export interface BackendForecastsResponse {
  count: number;
  data_label: string;
  forecasts: BackendForecast[];
}

export interface BackendRiskSummary {
  total: number;
  data_label: string;
  risk_distribution: { LOW: number; MEDIUM: number; HIGH: number };
}

export interface BackendMetric {
  model: string;
  mae: number;
  rmse: number;
  mae_raw: number;
  rmse_raw: number;
}

export interface BackendMetricsResponse {
  status: string;
  count: number;
  horizon_days: number;
  data_label: string;
  best_model: string;
  metrics: BackendMetric[];
}

export interface BackendExplanation {
  phc_id: string;
  medicine_id: string;
  explanation: string;
  gemini_explanation: string;
  source: 'gemini' | 'cached';
  model_used: string;
  risk_level: string;
  predicted_15_day_demand: number;
  current_stock: number;
  expected_shortage: number;
  data_label: string;
}

// ─── Fetch helper with timeout ──────────────────────────────────────────────
async function apiFetch<T>(path: string, timeoutMs = 6000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  try {
    const res = await fetch(`${API_BASE}${normalizedPath}`, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${API_BASE}${normalizedPath}`);
    liveConnectionActive = true;
    return (await res.json()) as T;
  } catch (err) {
    liveConnectionActive = false;
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Exported API calls ─────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{
  system: string;
  status: string;
  service: string;
  forecast_objects: number;
  gemini_explanations: number;
  data_label: string;
} | null> {
  try {
    return await apiFetch('/status');
  } catch (err) {
    console.warn('[apiService] /api/status health check failed:', err);
    return null;
  }
}

/** All 15 forecast objects — returns adapted frontend shapes + data label. */
export async function fetchAllForecasts(): Promise<{
  phcList: PHCNodeData[];
  riskList: RiskRadarItem[];
  rawForecasts?: BackendForecast[];
  isLive: boolean;
  dataLabel: string;
}> {
  try {
    const data = await apiFetch<BackendForecastsResponse>('/forecasts');
    const { phcList, riskList } = adaptForecastObjects(data.forecasts);
    const label = data.data_label.toLowerCase().includes('simulated')
      ? 'Simulated data'
      : `${data.data_label} data`;
    return { phcList, riskList, rawForecasts: data.forecasts, isLive: true, dataLabel: label };
  } catch (err) {
    console.warn('[apiService] /api/forecasts failed, using offline fallback:', err);
  }

  // Offline fallback — import lazily to avoid circular deps
  const { SEEDED_PHC_NODES, SEEDED_RISK_RADAR } = await import('./decisionService');
  return {
    phcList: SEEDED_PHC_NODES,
    riskList: SEEDED_RISK_RADAR,
    isLive: false,
    dataLabel: 'Offline demo data',
  };
}

/** Single PHC + medicine forecast including Gemini explanation. */
export async function fetchForecast(
  phcId: string,
  medicineId: string
): Promise<{ data: BackendForecast | null; isLive: boolean }> {
  try {
    const data = await apiFetch<BackendForecast>(`/forecast/${phcId}/${medicineId}`);
    return { data, isLive: true };
  } catch (err) {
    console.warn(`[apiService] /api/forecast/${phcId}/${medicineId} failed:`, err);
    return { data: null, isLive: false };
  }
}

/** Risk distribution across network. */
export async function fetchRiskSummary(): Promise<{
  data: BackendRiskSummary | null;
  isLive: boolean;
}> {
  try {
    const data = await apiFetch<BackendRiskSummary>('/risk-summary');
    return { data, isLive: true };
  } catch (err) {
    console.warn('[apiService] /api/risk-summary failed:', err);
    return { data: null, isLive: false };
  }
}

/** Model comparison metrics from model_comparison.csv via backend. */
export async function fetchMetrics(): Promise<{
  data: BackendMetricsResponse | null;
  isLive: boolean;
}> {
  try {
    const data = await apiFetch<BackendMetricsResponse>('/metrics');
    return { data, isLive: true };
  } catch (err) {
    console.warn('[apiService] /api/metrics failed:', err);
    return { data: null, isLive: false };
  }
}

/** Fetch explanation for specific PHC + medicine from backend /explain/{phc}/{med}. */
export async function fetchExplanation(
  phcId: string,
  medicineId: string
): Promise<{ data: BackendExplanation | null; isLive: boolean }> {
  try {
    const data = await apiFetch<BackendExplanation>(
      `/explain/${encodeURIComponent(phcId)}/${encodeURIComponent(medicineId)}`
    );
    return { data, isLive: true };
  } catch (err) {
    console.warn(`[apiService] /api/explain/${phcId}/${medicineId} failed:`, err);
    return { data: null, isLive: false };
  }
}

export const apiService = {
  isOfflineMode,
  fetchHealth,
  fetchAllForecasts,
  fetchForecast,
  fetchRiskSummary,
  fetchMetrics,
  fetchExplanation,
};

export default apiService;
