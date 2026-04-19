from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, HTTPException, Query

from app.services.bbc_weather import bbc_weather, BBC_LOCATION_CODES

router = APIRouter(tags=["weather"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_OPEN_METEO_CACHE: Dict[str, Dict[str, Any]] = {}
_OPEN_METEO_CACHE_TTL_S = 120.0
_WEATHER_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}
_WEATHER_RESPONSE_CACHE_TTL_S = 120.0


def _safe_float(value: Any, default: float = 0.0) -> float:
	try:
		if value is None:
			return default
		return float(value)
	except Exception:
		return default


def _safe_optional_float(value: Any) -> float | None:
	try:
		if value is None:
			return None
		return float(value)
	except Exception:
		return None


def _clean_humidity(value: Any) -> float | None:
	humidity = _safe_optional_float(value)
	if humidity is None:
		return None
	# RH is physically bounded to 0-100%; treat out-of-range values as invalid input.
	if humidity < 0.0 or humidity > 100.0:
		return None
	return round(humidity, 1)


def _to_condition(weather_code: Any) -> str:
	code = int(_safe_float(weather_code, -1))
	if code in (0, 1):
		return "Sunny"
	if code == 2:
		return "Partly Cloudy"
	if code == 3:
		return "Overcast"
	if code in (45, 48):
		return "Foggy"
	if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
		return "Rainy"
	if code in (71, 73, 75, 77, 85, 86):
		return "Snowy"
	if code in (95, 96, 99):
		return "Thunderstorm"
	return "Unknown"


def _uv_level(uv_index: float) -> str:
	if uv_index < 3:
		return "Low"
	if uv_index < 6:
		return "Moderate"
	if uv_index < 8:
		return "High"
	if uv_index < 11:
		return "Very High"
	return "Extreme"


def _air_quality_from_weather(precip_mm: float, wind_kph: float, humidity_pct: float) -> str:
	if precip_mm >= 1.0 or wind_kph >= 20.0:
		return "Good"
	if humidity_pct >= 85.0:
		return "Moderate"
	return "Fair"


def _quick_weather_fallback(latitude: float, longitude: float) -> Dict[str, Any]:
	return {
		"latitude": latitude,
		"longitude": longitude,
		"temperature": 25.0,
		"humidity": 65.0,
		"precipitation": 0.0,
		"wind_speed": 5.0,
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"provider": "fallback",
	}


def _weather_cache_key(latitude: float, longitude: float, past_days: int) -> str:
	return f"{round(latitude, 4):.4f}:{round(longitude, 4):.4f}:{past_days}"


import concurrent.futures
import threading
import time

# ---------------------------------------------------------------------------
# World Bank baselines cache (refreshed every 24 h — data changes annually)
# ---------------------------------------------------------------------------
_WB_CACHE: Dict[str, Any] = {}
_WB_LOCK = threading.Lock()
_WB_LAST_FETCH: float = 0.0
_WB_TTL = 86400.0  # 24 hours

_WB_INDICATORS = {
	"fossil_share": "EG.ELC.FOSL.ZS",
	"energy_kwh_year": "EG.USE.ELEC.KH.PC",
}

def _fetch_world_bank_baselines() -> Dict[str, Any]:
	global _WB_LAST_FETCH
	with _WB_LOCK:
		if time.time() - _WB_LAST_FETCH < _WB_TTL and _WB_CACHE:
			return dict(_WB_CACHE)
		result: Dict[str, Any] = {}
		for key, indicator in _WB_INDICATORS.items():
			try:
				url = f"https://api.worldbank.org/v2/country/JM/indicator/{indicator}?format=json&mrv=3"
				resp = requests.get(url, timeout=4)
				resp.raise_for_status()
				data = resp.json()
				rows = data[1] if isinstance(data, list) and len(data) > 1 else []
				for row in rows:
					if row.get("value") is not None:
						result[key] = float(row["value"])
						break
			except Exception:
				pass
		_WB_CACHE.update(result)
		_WB_LAST_FETCH = time.time()
		return dict(_WB_CACHE)

# Pre-warm World Bank cache in background so first real request hits cache, not the API
def _prewarm_world_bank() -> None:
	try:
		_fetch_world_bank_baselines()
	except Exception:
		pass

_prewarm_thread = threading.Thread(target=_prewarm_world_bank, daemon=True)
_prewarm_thread.start()


def _fetch_air_quality(latitude: float, longitude: float) -> Dict[str, Any]:
	"""Fetch real-time air quality from Open-Meteo (no API key required)."""
	try:
		url = "https://air-quality-api.open-meteo.com/v1/air-quality"
		params = {
			"latitude": latitude,
			"longitude": longitude,
			"current": "carbon_monoxide,nitrogen_dioxide,pm2_5,pm10,european_aqi",
		}
		resp = requests.get(url, params=params, timeout=4)
		resp.raise_for_status()
		return resp.json().get("current", {})
	except Exception:
		return {}


def _fetch_open_meteo(latitude: float, longitude: float, past_days: int = 7) -> Dict[str, Any]:
	cache_key = _weather_cache_key(latitude, longitude, past_days)
	cached = _OPEN_METEO_CACHE.get(cache_key)
	if cached and (time.time() - _safe_float(cached.get("_cached_at"), 0.0)) < _OPEN_METEO_CACHE_TTL_S:
		return dict(cached)

	base_params = {
		"latitude": latitude,
		"longitude": longitude,
		"forecast_days": 7,
		"past_days": max(0, min(past_days, 14)),
		"current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code,apparent_temperature",
		"hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,apparent_temperature,wind_speed_10m,wind_direction_10m,uv_index,weather_code",
		"daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,wind_speed_10m_max,uv_index_max,weather_code,precipitation_sum",
	}

	last_error = "unknown"
	# Keep worst-case latency under mobile client timeouts.
	# First try auto timezone (5s), then one short fallback attempt (3s).
	attempts = (("auto", 5), ("America/Jamaica", 3))

	for tz, timeout_secs in attempts:
		try:
			params = dict(base_params)
			params["timezone"] = tz
			response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout_secs)
			response.raise_for_status()
			payload = response.json()
			if isinstance(payload, dict):
				payload["_provider"] = "open-meteo"
				payload["_timezone_mode"] = tz
				payload["_cached_at"] = time.time()
				_OPEN_METEO_CACHE[cache_key] = dict(payload)
			return payload
		except requests.exceptions.Timeout as exc:
			last_error = f"timeout ({timeout_secs}s)"
			# Try fallback timezone once, then return fast fallback response.
			continue
		except requests.exceptions.RequestException as exc:
			last_error = str(exc)

	return {
		"current": {},
		"hourly": {},
		"daily": {},
		"_provider": "fallback",
		"_error": last_error,
	}


def _build_weather_response_cached(latitude: float, longitude: float) -> Dict[str, Any]:
	cache_key = f"{latitude:.4f}:{longitude:.4f}"
	cached = _WEATHER_RESPONSE_CACHE.get(cache_key)
	if cached and (time.time() - _safe_float(cached.get("_cached_at"), 0.0)) < _WEATHER_RESPONSE_CACHE_TTL_S:
		result = dict(cached)
		result.pop("_cached_at", None)
		return result

	meteo = _fetch_open_meteo(latitude, longitude, past_days=0)
	current_fallback = {}
	if not meteo.get("current"):
		current_fallback = _quick_weather_fallback(latitude, longitude)

	current = meteo.get("current", {})
	hourly = meteo.get("hourly", {})
	daily = meteo.get("daily", {})
	is_live_meteo = bool(current)
	daily_precip_list = daily.get("precipitation_sum", [])
	today_precip_sum = _safe_float(daily_precip_list[0] if daily_precip_list else None)
	seven_day_precip_total = round(sum(_safe_float(value, 0.0) for value in daily_precip_list[:7]), 2)

	current_temp = _safe_float(current.get("temperature_2m"), _safe_float(current_fallback.get("temperature")))
	current_humidity = _safe_float(current.get("relative_humidity_2m"), _safe_float(current_fallback.get("humidity")))
	current_wind = _safe_float(current.get("wind_speed_10m"), _safe_float(current_fallback.get("wind_speed")))
	instant_precip = _safe_float(current.get("precipitation"), _safe_float(current_fallback.get("precipitation"), 0.0))
	current_precip = today_precip_sum if today_precip_sum is not None else instant_precip
	if current_precip <= 0.0 and seven_day_precip_total > 0.0:
		current_precip = seven_day_precip_total
	current_condition = _to_condition(current.get("weather_code"))
	if current_condition == "Unknown":
		fallback_condition = str(current_fallback.get("condition") or "").strip()
		if fallback_condition:
			current_condition = fallback_condition
		elif current_precip > 0.0:
			current_condition = "Rainy"

	hourly_items: List[Dict[str, Any]] = []
	hourly_times = hourly.get("time", [])
	temp_series = hourly.get("temperature_2m", [])
	humidity_series = hourly.get("relative_humidity_2m", [])
	precip_prob_series = hourly.get("precipitation_probability", [])
	apparent_series = hourly.get("apparent_temperature", [])
	wind_series = hourly.get("wind_speed_10m", [])
	wind_dir_series = hourly.get("wind_direction_10m", [])
	uv_series = hourly.get("uv_index", [])
	code_series = hourly.get("weather_code", [])
	total_hourly = min(24, len(hourly_times))
	for index in range(total_hourly):
		uv_index = _safe_float(uv_series[index] if index < len(uv_series) else None)
		hourly_items.append({
			"time": hourly_times[index],
			"temperature": _safe_float(temp_series[index] if index < len(temp_series) else None),
			"humidity": _safe_float(humidity_series[index] if index < len(humidity_series) else None),
			"precip_probability_pct": _safe_float(precip_prob_series[index] if index < len(precip_prob_series) else None),
			"realfeel_c": _safe_float(apparent_series[index] if index < len(apparent_series) else None),
			"realfeel_shade_c": _safe_float(apparent_series[index] if index < len(apparent_series) else None) - 1.5,
			"wind_kph": _safe_float(wind_series[index] if index < len(wind_series) else None),
			"wind_dir": str(wind_dir_series[index]) if index < len(wind_dir_series) else "N/A",
			"air_quality": _air_quality_from_weather(0.0, _safe_float(wind_series[index] if index < len(wind_series) else None), _safe_float(humidity_series[index] if index < len(humidity_series) else None)),
			"uv_index": uv_index,
			"uv_level": _uv_level(uv_index),
			"condition": _to_condition(code_series[index] if index < len(code_series) else None),
		})

	daily_items: List[Dict[str, Any]] = []
	daily_times = daily.get("time", [])
	max_series = daily.get("temperature_2m_max", [])
	min_series = daily.get("temperature_2m_min", [])
	mean_humidity_series = daily.get("relative_humidity_2m_mean", [])
	day_wind_series = daily.get("wind_speed_10m_max", [])
	day_uv_series = daily.get("uv_index_max", [])
	day_code_series = daily.get("weather_code", [])
	day_precip_series = daily.get("precipitation_sum", [])
	hourly_humidity_by_date: Dict[str, List[float]] = {}
	for index, ts in enumerate(hourly_times):
		h = _clean_humidity(humidity_series[index] if index < len(humidity_series) else None)
		if h is None:
			continue
		date_key = str(ts)[:10]
		hourly_humidity_by_date.setdefault(date_key, []).append(h)
	total_daily = min(7, len(daily_times))
	for index in range(total_daily):
		day_uv = _safe_float(day_uv_series[index] if index < len(day_uv_series) else None)
		date_key = daily_times[index]
		daily_mean_humidity = _clean_humidity(mean_humidity_series[index] if index < len(mean_humidity_series) else None)
		if daily_mean_humidity is None:
			hourly_day_values = hourly_humidity_by_date.get(str(date_key)[:10], [])
			if hourly_day_values:
				daily_mean_humidity = round(sum(hourly_day_values) / len(hourly_day_values), 1)
		daily_items.append({
			"date": date_key,
			"temp_max": _safe_float(max_series[index] if index < len(max_series) else None),
			"temp_min": _safe_float(min_series[index] if index < len(min_series) else None),
			"humidity": daily_mean_humidity,
			"wind_kph": _safe_float(day_wind_series[index] if index < len(day_wind_series) else None),
			"precipitation_mm": _safe_float(day_precip_series[index] if index < len(day_precip_series) else None),
			"uv_index": day_uv,
			"uv_level": _uv_level(day_uv),
			"condition": _to_condition(day_code_series[index] if index < len(day_code_series) else None),
		})

	historical_items: List[Dict[str, Any]] = []
	historical_count = min(7, len(daily_times))
	for index in range(historical_count):
		date_key = daily_times[index]
		historical_humidity = _clean_humidity(mean_humidity_series[index] if index < len(mean_humidity_series) else None)
		if historical_humidity is None:
			hourly_day_values = hourly_humidity_by_date.get(str(date_key)[:10], [])
			if hourly_day_values:
				historical_humidity = round(sum(hourly_day_values) / len(hourly_day_values), 1)
		historical_items.append({
			"date": date_key,
			"temperature": _safe_float(max_series[index] if index < len(max_series) else None),
			"humidity": historical_humidity,
			"condition": _to_condition(day_code_series[index] if index < len(day_code_series) else None),
			"wind_kph": _safe_float(day_wind_series[index] if index < len(day_wind_series) else None),
			"pressure": 1013.0,
		})

	if not hourly_items:
		# Ensure clients always receive a 24-point hourly trend, even when upstream APIs timeout.
		start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
		for index in range(24):
			ts = (start + timedelta(hours=index)).isoformat().replace("+00:00", "Z")
			temp = round(current_temp + ((index % 6) - 3) * 0.2, 1)
			hourly_items.append({
				"time": ts,
				"temperature": temp,
				"humidity": current_humidity,
				"precip_probability_pct": 0.0,
				"realfeel_c": temp,
				"realfeel_shade_c": temp - 1.5,
				"wind_kph": current_wind,
				"wind_dir": "N/A",
				"air_quality": _air_quality_from_weather(0.0, current_wind, current_humidity),
				"uv_index": 0.0,
				"uv_level": _uv_level(0.0),
				"condition": current_condition,
			})

	result = {
		"current": {
			"temperature": current_temp,
			"humidity": current_humidity,
			"wind_kph": current_wind,
			"condition": current_condition,
			"wind_dir": "N/A",
			"uv_index": _safe_float(current.get("uv_index"), 0.0),
			"uv_level": _uv_level(_safe_float(current.get("uv_index"), 0.0)),
		},
		"hourly": hourly_items,
		"daily": daily_items,
		"historical": historical_items,
		"source": "open-meteo" if is_live_meteo else "farmonaut-fallback",
		"source_detail": meteo.get("_provider"),
		"source_error": meteo.get("_error"),
		"coordinates": {
			"latitude": latitude,
			"longitude": longitude,
		},
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"precipitation_mm": current_precip,
		"precipitation_today_mm": today_precip_sum,
		"precipitation_7day_mm": seven_day_precip_total,
	}
	# Only store in cache when Open-Meteo returned real hourly data (skip failed/fallback responses)
	if hourly_items:
		_WEATHER_RESPONSE_CACHE[cache_key] = {**result, "_cached_at": time.time()}
	return result


@router.get("/weather/bbc/current")
def get_bbc_current_weather():
	location_code = BBC_LOCATION_CODES.get("kingston_jamaica", 3489854)
	try:
		payload = bbc_weather.get_weather_for_location(location_code)
		if not payload:
			raise ValueError("No weather data returned")
		weather = payload.get("weather", {})
		return {
			"data": {
				"weather": {
					"temperature": _safe_float(weather.get("temperature_c")),
					"condition": weather.get("condition") or "Fair",
					"wind_speed": _safe_float(weather.get("wind_speed_mph")) * 1.60934,
					"humidity": _safe_float(weather.get("humidity_percent")),
				}
			},
			"source": "bbc",
			"location": payload.get("location"),
			"timestamp": payload.get("timestamp") or datetime.now(timezone.utc).isoformat(),
		}
	except Exception as exc:
		raise HTTPException(status_code=502, detail=f"BBC weather unavailable: {exc}")


@router.get("/weather")
def get_weather(
	latitude: float = Query(..., ge=-90, le=90),
	longitude: float = Query(..., ge=-180, le=180),
):
	try:
		return _build_weather_response_cached(round(latitude, 4), round(longitude, 4))
	except Exception as exc:
		raise HTTPException(status_code=502, detail=f"Weather service unavailable: {exc}")


@router.get("/weather/climate-report")
def get_climate_report(
	latitude: float = Query(..., ge=-90, le=90),
	longitude: float = Query(..., ge=-180, le=180),
):
	try:
		# Run all three external calls in parallel — worst-case latency = max(each), not sum
		with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
			f_meteo = pool.submit(_fetch_open_meteo, latitude, longitude, 30)
			f_aq = pool.submit(_fetch_air_quality, latitude, longitude)
			f_wb = pool.submit(_fetch_world_bank_baselines)
			try:
				meteo = f_meteo.result(timeout=8)
			except Exception:
				meteo = {"current": {}, "hourly": {}, "daily": {}, "_provider": "fallback"}
			try:
				aq = f_aq.result(timeout=6)
			except Exception:
				aq = {}
			try:
				wb = f_wb.result(timeout=6)
			except Exception:
				wb = {}

		current = meteo.get("current", {})
		daily = meteo.get("daily", {})

		current_temp = _safe_float(current.get("temperature_2m"))
		current_humidity = _safe_float(current.get("relative_humidity_2m"))
		current_precip = _safe_float(current.get("precipitation"))
		current_wind = _safe_float(current.get("wind_speed_10m"))
		current_uv = _safe_float(current.get("uv_index"), 3.0)

		daily_max = daily.get("temperature_2m_max", [])
		historical_baseline = sum(daily_max[:30]) / max(1, len(daily_max[:30])) if daily_max else current_temp
		temp_anomaly = current_temp - historical_baseline

		# Air quality: use real AQI from Open-Meteo if available, else estimate from weather
		co_ug = _safe_float(aq.get("carbon_monoxide"), 0.0)    # µg/m³, real-time
		no2_ug = _safe_float(aq.get("nitrogen_dioxide"), 0.0)  # µg/m³, real-time
		aqi = int(_safe_float(aq.get("european_aqi"), 0))
		if aqi > 0:
			if aqi <= 20:
				air_quality = "Good"
			elif aqi <= 40:
				air_quality = "Fair"
			elif aqi <= 60:
				air_quality = "Moderate"
			elif aqi <= 80:
				air_quality = "Poor"
			else:
				air_quality = "Very Poor"
		else:
			air_quality = _air_quality_from_weather(current_precip, current_wind, current_humidity)

		# --- Energy: real World Bank kWh/capita/year ÷ 365 + AC load for heat ---
		heat_load = max(0.0, current_temp - 28.0)
		wb_energy_year = wb.get("energy_kwh_year", 1147.5)  # fallback: Jamaica 2022 value
		energy_kwh = round((wb_energy_year / 365.0) + heat_load * 0.04, 3)

		# --- Grid intensity: Jamaica diesel-heavy 680 gCO2/kWh; slight drop when windy ---
		grid_intensity = round(max(580.0, 680.0 - max(0.0, current_wind - 15.0) * 2.5), 1)

		# --- Fossil share: real World Bank value (Jamaica ~87.9%) ---
		fossil_share = round(wb.get("fossil_share", 87.9), 1)

		# --- Traffic CO2: scaled from real CO reading (200 µg/m³ = baseline 1.6 kg/day) ---
		if co_ug > 0:
			traffic_co2 = round(1.6 * (co_ug / 200.0), 2)
		else:
			traffic_co2 = round(1.6 + heat_load * 0.02, 2)

		# --- Waste & recycling: Jamaica national stats (no live API available) ---
		waste_daily = round(0.92 + max(0.0, current_humidity - 70.0) * 0.001, 3)
		recycling_rate = 11.0

		# --- Total CO2: electricity + transport ---
		co2_daily = round((energy_kwh * grid_intensity / 1000.0) + traffic_co2, 3)
		co2_yearly_tons = round((co2_daily * 365.0) / 1000.0, 4)
		# Arctic ice loss: ~3 m² per tonne CO2 (IPCC AR6)
		arctic_ice_equivalent = round(max(0.5, co2_yearly_tons * 3.0), 3)

		if temp_anomaly > 1.5:
			impact_text = "Elevated warming pressure; prioritize energy efficiency and low-emission operations."
		elif temp_anomaly > 0.5:
			impact_text = "Mild warming signal; monitor cooling demand and transport activity."
		elif temp_anomaly < -0.5:
			impact_text = "Below-baseline temperatures; heating demand may increase local emissions."
		else:
			impact_text = "Near-baseline climate signal for this period."

		return {
			"daily_snapshot": {
				"temperature_c": round(current_temp, 2),
				"humidity_percent": round(current_humidity, 1),
				"wind_kph": round(current_wind, 1),
				"uv_index": round(current_uv, 1),
				"uv_level": _uv_level(current_uv),
				"air_quality": air_quality,
			},
			"human_activity_metrics": {
				"traffic_co2_kg_estimated": round(traffic_co2, 2),
				"energy_consumption_kwh_per_capita_daily": round(energy_kwh, 3),
				"grid_carbon_intensity_gco2_per_kwh_estimated": round(grid_intensity, 1),
				"fossil_fuel_energy_share_percent": round(fossil_share, 1),
				"waste_generation_kg_per_capita_daily": round(waste_daily, 3),
				"recycling_rate_percent": round(recycling_rate, 1),
			},
			"climate_impact_indicators": {
				"co2_daily_kg_per_capita": round(co2_daily, 3),
				"co2_emissions_tons_per_capita_year": round(co2_yearly_tons, 4),
				"temperature_anomaly_vs_historical_month_c": round(temp_anomaly, 3),
				"historical_baseline_temperature_c": round(historical_baseline, 3),
				"arctic_ice_m2_equivalent": round(arctic_ice_equivalent, 3),
				"equivalent_impact_text": impact_text,
			},
			"air_quality_realtime": {
				"carbon_monoxide_ug_m3": co_ug if co_ug > 0 else None,
				"nitrogen_dioxide_ug_m3": no2_ug if no2_ug > 0 else None,
				"pm2_5_ug_m3": _safe_float(aq.get("pm2_5"), 0.0) or None,
				"pm10_ug_m3": _safe_float(aq.get("pm10"), 0.0) or None,
				"european_aqi": aqi if aqi > 0 else None,
				"air_quality_label": air_quality,
			},
			"data_sources": {
				"weather": "open-meteo (real-time)",
				"air_quality": "open-meteo air quality API (real-time)" if aqi > 0 else "estimated from weather",
				"energy_kwh": f"World Bank {wb.get('_wb_year', 'latest')} (annual stat)" if "energy_kwh_year" in wb else "regional estimate",
				"fossil_share": "World Bank (annual stat)" if "fossil_share" in wb else "regional estimate",
				"waste_recycling": "Jamaica national statistics (static)",
			},
			"source": "open-meteo + world-bank",
			"coordinates": {
				"latitude": latitude,
				"longitude": longitude,
			},
			"generated_at": datetime.now(timezone.utc).isoformat(),
		}
	except Exception as exc:
		raise HTTPException(status_code=502, detail=f"Climate report unavailable: {exc}")


# ─── OPTIMIZED DASHBOARD: Parallel data fetching ─────────────────────────────
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

@router.get("/dashboard/fast-load")
def get_dashboard_fast_load(
	latitude: float = Query(..., ge=-90, le=90),
	longitude: float = Query(..., ge=-180, le=180),
	crop_type: str = Query("maize", description="Crop type for yield calculation"),
):
	"""
	Optimized dashboard endpoint that fetches weather, NDVI, and yield in PARALLEL.
	Returns combined data in <3 seconds instead of 15+ seconds.
	"""
	try:
		# Import here to avoid circular imports
		from ndvi_history import get_historical_ndvi
		from yield_engine import estimate_yield
		
		start_time = time.time()
		
		def fetch_weather():
			try:
				current_fallback = _quick_weather_fallback(latitude, longitude)
				meteo = _fetch_open_meteo(latitude, longitude, past_days=0)
				return {
					"weather": current_fallback,
					"meteo": meteo,
					"error": None
				}
			except Exception as e:
				return {
					"weather": {},
					"meteo": {},
					"error": str(e)
				}
		
		def fetch_ndvi():
			try:
				stats = get_historical_ndvi(latitude, longitude, start_year=2023, end_year=2024)
				mean_ndvi = float(stats.get("mean") or 0.5)
				mean_ndvi = round(max(0.0, min(1.0, mean_ndvi)), 4)
				
				# Derive EVI and NDWI from NDVI
				evi = round((mean_ndvi * 0.85) + 0.05, 4)
				ndwi = round((mean_ndvi * 0.6) - 0.2, 4)
				ndwi = round(max(-1.0, min(1.0, ndwi)), 4)
				
				return {
					"ndvi": mean_ndvi,
					"evi": evi,
					"ndwi": ndwi,
					"ndvi_min": round(float(stats.get("min") or mean_ndvi), 4),
					"ndvi_max": round(float(stats.get("max") or mean_ndvi), 4),
					"error": None
				}
			except Exception as e:
				return {
					"ndvi": 0.5,
					"evi": 0.475,
					"ndwi": 0.1,
					"ndvi_min": 0.5,
					"ndvi_max": 0.5,
					"error": str(e)
				}
		
		def fetch_yield():
			try:
				# Yield will be calculated after NDVI is fetched
				return None  # Placeholder
			except Exception as e:
				return {"error": str(e)}
		
		# Execute weather and NDVI in parallel
		with ThreadPoolExecutor(max_workers=2) as executor:
			weather_future = executor.submit(fetch_weather)
			ndvi_future = executor.submit(fetch_ndvi)

			weather_data = {
				"weather": _quick_weather_fallback(latitude, longitude),
				"meteo": {},
				"error": "weather_timeout",
			}
			ndvi_data = {
				"ndvi": 0.5,
				"evi": 0.475,
				"ndwi": 0.1,
				"ndvi_min": 0.5,
				"ndvi_max": 0.5,
				"error": "ndvi_timeout",
			}

			try:
				weather_data = weather_future.result(timeout=10)
			except Exception:
				pass

			try:
				ndvi_data = ndvi_future.result(timeout=10)
			except Exception:
				pass
		
		# Extract key values
		current = weather_data["meteo"].get("current", {})
		current_temp = _safe_float(current.get("temperature_2m"), 20.0)
		current_humidity = _safe_float(current.get("relative_humidity_2m"), 60.0)
		current_wind = _safe_float(current.get("wind_speed_10m"), 0.0)
		
		# Extract precipitation with fallback
		daily = weather_data["meteo"].get("daily", {})
		daily_precip_list = daily.get("precipitation_sum", [])
		today_precip = _safe_float(daily_precip_list[0] if daily_precip_list else None, 0.0)
		seven_day_precip = round(sum(_safe_float(v, 0.0) for v in daily_precip_list[:7]), 2)
		current_precip = today_precip if today_precip > 0 else (seven_day_precip if seven_day_precip > 0 else 0.0)
		
		current_condition = _to_condition(current.get("weather_code"))
		if current_condition == "Unknown" and current_precip > 0:
			current_condition = "Rainy"
		
		# Calculate yield
		ndvi = ndvi_data["ndvi"]
		evi = ndvi_data["evi"]
		ndwi = ndvi_data["ndwi"]
		
		yield_estimate = estimate_yield(
			ndvi=ndvi,
			evi=evi,
			ndwi=ndwi,
			rainfall_mm=current_precip,
			avg_temp_c=current_temp,
			crop=crop_type
		)
		
		elapsed_ms = (time.time() - start_time) * 1000.0
		
		# Return combined dashboard data
		return {
			"location": {
				"latitude": latitude,
				"longitude": longitude,
			},
			"weather": {
				"current": {
					"temperature_c": current_temp,
					"humidity_pct": current_humidity,
					"condition": current_condition,
					"wind_kph": current_wind,
					"precipitation_mm": current_precip,
				},
				"daily_forecasts": [
					{
						"date": daily.get("time", [])[i] if i < len(daily.get("time", [])) else "",
						"temp_max": _safe_float(daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else None),
						"temp_min": _safe_float(daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else None),
						"humidity_pct": _clean_humidity(daily.get("relative_humidity_2m_mean", [])[i] if i < len(daily.get("relative_humidity_2m_mean", [])) else None),
						"precipitation_mm": _safe_float(daily.get("precipitation_sum", [])[i] if i < len(daily.get("precipitation_sum", [])) else None),
					}
					for i in range(min(7, len(daily.get("time", []))))
				],
				"source": "open-meteo" if weather_data["meteo"].get("_provider") != "fallback" else "farmonaut-fallback",
			},
			"vegetation_indices": {
				"ndvi": ndvi,
				"evi": evi,
				"ndwi": ndwi,
				"ndvi_min": ndvi_data["ndvi_min"],
				"ndvi_max": ndvi_data["ndvi_max"],
			},
			"yield_forecast": {
				"crop_type": crop_type,
				"estimated_tons_per_hectare": yield_estimate,
			},
			"performance": {
				"response_time_ms": round(elapsed_ms, 1),
				"fetched_in_parallel": True,
			},
		}
	except Exception as exc:
		raise HTTPException(status_code=502, detail=f"Dashboard fast load failed: {str(exc)}")
