from __future__ import annotations

from typing import Any, Dict, List, Optional


NOT_SPECIFIED = "Not specified"


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _question_mentions(question: str, words: List[str]) -> bool:
    text = (question or "").lower()
    return any(word in text for word in words)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_direction(yoy_change: float, status: Any) -> str:
    if isinstance(status, str) and status:
        return status
    if yoy_change > 0:
        return "up"
    if yoy_change < 0:
        return "down"
    return "flat"


def _summary_sections(app_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        "analytics": _as_dict(app_context.get("analytics") if isinstance(app_context, dict) else {}),
        "ndvi": _as_dict(app_context.get("ndvi") if isinstance(app_context, dict) else {}),
        "validation": _as_dict(app_context.get("validation") if isinstance(app_context, dict) else {}),
    }


def _resolve_accuracy(analytics: Dict[str, Any], validation: Dict[str, Any]) -> Optional[float]:
    return _safe_float(analytics.get("overall_accuracy"), _safe_float(validation.get("overall_accuracy"), None))


def _resolve_correlation(analytics: Dict[str, Any], ndvi: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    for candidate in (
        _as_dict(ndvi.get("correlation_analysis")),
        _as_dict(analytics.get("ndvi_correlation")),
        _as_dict(validation.get("ndvi_correlation")),
    ):
        if candidate:
            return candidate
    return {}


def _resolve_data_quality(analytics: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(validation.get("data_quality")) or _as_dict(analytics.get("data_quality"))


def _resolve_yoy(analytics: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(validation.get("year_over_year")) or _as_dict(analytics.get("year_over_year"))


def _farm_recent_values(farm_context: Dict[str, Any]) -> Dict[str, Any]:
    recent_yields = farm_context.get("recent_yields") if isinstance(farm_context, dict) else []
    recent_ndvi = farm_context.get("recent_ndvi") if isinstance(farm_context, dict) else []
    last_yield = recent_yields[0] if recent_yields else {}
    last_ndvi = recent_ndvi[0] if recent_ndvi else {}
    last_ndvi_stats = _as_dict(last_ndvi.get("ndvi_stats") if isinstance(last_ndvi, dict) else {})
    return {
        "last_yield": last_yield,
        "last_ndvi": last_ndvi,
        "last_ndvi_stats": last_ndvi_stats,
    }


def _sections_used(farm_context: Dict[str, Any], analytics: Dict[str, Any], ndvi: Dict[str, Any], validation: Dict[str, Any]) -> List[str]:
    sections_used: List[str] = []
    if farm_context:
        sections_used.append("farm")
    if analytics:
        sections_used.append("analytics")
    if ndvi:
        sections_used.append("ndvi")
    if validation:
        sections_used.append("validation")
    return sections_used


def _build_summary_lines(
    overall_accuracy: Optional[float],
    correlation_value: Optional[float],
    correlation_label: Any,
    yoy: Dict[str, Any],
    data_quality: Dict[str, Any],
    last_yield: Dict[str, Any],
    last_ndvi_stats: Dict[str, Any],
) -> List[str]:
    summary_lines: List[str] = []
    if overall_accuracy is not None:
        summary_lines.append(f"Model accuracy from app data is {overall_accuracy:.1f}%.")
    if correlation_value is not None:
        if correlation_label:
            summary_lines.append(f"NDVI to yield correlation is {correlation_value:.2f} ({correlation_label}).")
        else:
            summary_lines.append(f"NDVI to yield correlation is {correlation_value:.2f}.")

    yoy_change = _safe_float(yoy.get("change_percent"), None)
    if yoy_change is not None:
        direction = _resolve_direction(yoy_change, yoy.get("status"))
        summary_lines.append(f"Predicted yield trend is {direction} by {abs(yoy_change):.1f}% year over year.")

    completeness = _safe_float(data_quality.get("report_completeness_percent"), None)
    if completeness is not None:
        summary_lines.append(f"Yield report completeness is {completeness:.1f}%.")

    ndvi_mean = _safe_float(last_ndvi_stats.get("mean") or last_ndvi_stats.get("avg"), None)
    if ndvi_mean is not None:
        summary_lines.append(f"Latest NDVI mean in app data is {ndvi_mean:.2f}.")

    latest_yield = _safe_float(last_yield.get("yield_estimate") if isinstance(last_yield, dict) else None, None)
    if latest_yield is not None:
        summary_lines.append(f"Latest stored yield estimate is {latest_yield:.2f}.")
    return summary_lines


def summarize_app_sections(app_context: Dict[str, Any], farm_context: Dict[str, Any]) -> Dict[str, Any]:
    sections = _summary_sections(app_context)
    analytics = sections["analytics"]
    ndvi = sections["ndvi"]
    validation = sections["validation"]

    overall_accuracy = _resolve_accuracy(analytics, validation)
    correlation_block = _resolve_correlation(analytics, ndvi, validation)
    correlation_value = _safe_float(correlation_block.get("correlation_coefficient"), None)
    correlation_label = correlation_block.get("interpretation") or correlation_block.get("strength")
    data_quality = _resolve_data_quality(analytics, validation)
    yoy = _resolve_yoy(analytics, validation)
    farm_values = _farm_recent_values(farm_context)
    last_yield = farm_values["last_yield"]
    last_ndvi = farm_values["last_ndvi"]
    last_ndvi_stats = farm_values["last_ndvi_stats"]

    sections_used = _sections_used(farm_context, analytics, ndvi, validation)
    summary_lines = _build_summary_lines(
        overall_accuracy,
        correlation_value,
        correlation_label,
        yoy,
        data_quality,
        last_yield,
        last_ndvi_stats,
    )

    return {
        "sections_used": sections_used,
        "overall_accuracy": overall_accuracy,
        "correlation_value": correlation_value,
        "correlation_label": correlation_label,
        "year_over_year": yoy,
        "data_quality": data_quality,
        "last_yield": last_yield,
        "last_ndvi": last_ndvi,
        "summary_lines": summary_lines,
    }


def _realtime_weather_lines(realtime_context: Dict[str, Any]) -> List[str]:
    weather = _as_dict(realtime_context.get("weather"))
    climate = _as_dict(realtime_context.get("climate_report"))
    current = _as_dict(weather.get("current"))
    daily_snapshot = _as_dict(climate.get("daily_snapshot"))
    climate_impacts = _as_dict(climate.get("climate_impact_indicators"))

    comparisons: List[str] = []
    current_temp = _safe_float(current.get("temperature"), None)
    humidity = _safe_float(current.get("humidity"), None)
    wind_kph = _safe_float(current.get("wind_kph"), None)
    temp_anomaly = _safe_float(climate_impacts.get("temperature_anomaly_vs_historical_month_c"), None)
    uv_index = _safe_float(daily_snapshot.get("uv_index"), None)

    if current_temp is not None:
        comparisons.append(f"Realtime temperature is {current_temp:.1f}C.")
    if humidity is not None:
        comparisons.append(f"Realtime humidity is {humidity:.0f}%.")
    if wind_kph is not None:
        comparisons.append(f"Realtime wind speed is {wind_kph:.1f} kph.")
    if temp_anomaly is not None:
        if temp_anomaly > 1.0:
            comparisons.append(f"Current temperature is {temp_anomaly:.1f}C above the recent baseline, which raises heat stress risk.")
        elif temp_anomaly < -1.0:
            comparisons.append(f"Current temperature is {abs(temp_anomaly):.1f}C below the recent baseline, which raises cold stress risk.")
        else:
            comparisons.append("Realtime temperature is close to the recent climate baseline.")
    if uv_index is not None and uv_index >= 8.0:
        comparisons.append(f"UV index is high at {uv_index:.1f}, so fresh transplants may need moisture protection.")
    return comparisons


def _app_model_lines(app_summary: Dict[str, Any]) -> List[str]:
    comparisons: List[str] = []
    overall_accuracy = _safe_float(app_summary.get("overall_accuracy"), None)
    correlation_value = _safe_float(app_summary.get("correlation_value"), None)
    summary_lines = app_summary.get("summary_lines") if isinstance(app_summary, dict) else []

    if overall_accuracy is not None:
        if overall_accuracy < 55.0:
            comparisons.append("App model accuracy is limited, so field observations should weigh heavily in any decision.")
        elif overall_accuracy >= 75.0:
            comparisons.append("App model accuracy is strong enough to trust trend direction when combined with live weather.")
    if correlation_value is not None:
        if correlation_value < 0.3:
            comparisons.append("NDVI to yield linkage is weak in the stored data, so vegetation alone should not drive the recommendation.")
        elif correlation_value >= 0.6:
            comparisons.append("NDVI to yield linkage is strong in the stored data, so canopy health can meaningfully support the recommendation.")
    for line in summary_lines[:3]:
        comparisons.append(line)
    return comparisons


def build_data_comparison(app_summary: Dict[str, Any], realtime_context: Dict[str, Any]) -> List[str]:
    if not isinstance(realtime_context, dict) or not realtime_context.get("available"):
        return ["Realtime weather comparison is unavailable because location data is missing."]
    return _realtime_weather_lines(realtime_context) + _app_model_lines(app_summary)


def _action_weather_inputs(realtime_context: Dict[str, Any]) -> Dict[str, Optional[float]]:
    weather = _as_dict(realtime_context.get("weather") if isinstance(realtime_context, dict) else {})
    climate = _as_dict(realtime_context.get("climate_report") if isinstance(realtime_context, dict) else {})
    current = _as_dict(weather.get("current"))
    daily = weather.get("daily") if isinstance(weather.get("daily"), list) else []
    climate_daily = _as_dict(climate.get("daily_snapshot"))
    return {
        "temp_now": _safe_float(current.get("temperature"), _safe_float(climate_daily.get("temperature_c"), None)),
        "humidity": _safe_float(current.get("humidity"), _safe_float(climate_daily.get("humidity_percent"), None)),
        "precip": _safe_float(weather.get("precipitation_mm"), None),
        "forecast_min": _safe_float(_as_dict(daily[0]).get("temp_min"), None) if daily else None,
    }


def _question_flags(question: str) -> Dict[str, bool]:
    return {
        "planting": _question_mentions(question, ["plant", "sow", "transplant", "flowers", "flower"]),
        "soil": _question_mentions(question, ["soil", "top soil", "compost", "potting", "lighter"]),
        "general_farm": _question_mentions(question, ["farm", "field", "crop", "today", "now", "should i do", "what should i do"]),
        "irrigation": _question_mentions(question, ["water", "irrigat", "moisture", "dry"]),
        "disease": _question_mentions(question, ["disease", "fungus", "fungal", "blight", "mold"]),
        "fertility": _question_mentions(question, ["fertiliz", "nutrient", "compost", "soil health", "top soil"]),
    }


def _decision_reasons(inputs: Dict[str, Optional[float]], planting_question: bool) -> Dict[str, Any]:
    should_delay = False
    reasons: List[str] = []
    forecast_min = inputs.get("forecast_min")
    temp_now = inputs.get("temp_now")
    humidity = inputs.get("humidity")
    precip = inputs.get("precip")

    if forecast_min is not None and forecast_min < 10.0:
        should_delay = True
        reasons.append(f"forecast minimum is {forecast_min:.1f}C")
    if temp_now is not None and temp_now < 12.0 and planting_question:
        should_delay = True
        reasons.append(f"current temperature is only {temp_now:.1f}C")
    if humidity is not None and humidity >= 90.0 and planting_question:
        reasons.append(f"humidity is elevated at {humidity:.0f}%")
    if precip is not None and precip >= 3.0 and planting_question:
        reasons.append(f"precipitation is active at {precip:.1f} mm")
    return {"should_delay": should_delay, "reasons": reasons}


def _decision_text(planting_question: bool, should_delay: bool) -> str:
    if not planting_question:
        return "Use the app data together with live weather before making the next field adjustment."
    if should_delay:
        return "No, wait before planting until temperatures recover or conditions dry out."
    return "Yes, planting can proceed today if you protect young plants and manage soil moisture carefully."


def _general_farm_decision(inputs: Dict[str, Optional[float]], app_summary: Dict[str, Any]) -> str:
    temp_now = inputs.get("temp_now")
    humidity = inputs.get("humidity")
    precip = inputs.get("precip")
    overall_accuracy = _safe_float(app_summary.get("overall_accuracy"), None)

    if precip is not None and precip >= 5.0:
        return "Delay non-essential field operations until rainfall pressure eases."
    if humidity is not None and humidity >= 85.0:
        return "Prioritize crop scouting and airflow management today because disease pressure is elevated."
    if temp_now is not None and temp_now >= 32.0:
        return "Prioritize water management and avoid stressing the crop during the hottest part of the day."
    if overall_accuracy is not None and overall_accuracy >= 75.0:
        return "Routine field work can continue today, and your app data is strong enough to guide small adjustments."
    return "Routine farm work can continue today, but use a field walk and live weather as your final check before changing inputs."


def _general_farm_steps(
    inputs: Dict[str, Optional[float]],
    app_summary: Dict[str, Any],
    flags: Dict[str, bool],
) -> List[str]:
    steps: List[str] = []
    humidity = inputs.get("humidity")
    precip = inputs.get("precip")
    temp_now = inputs.get("temp_now")
    overall_accuracy = _safe_float(app_summary.get("overall_accuracy"), None)

    if precip is not None and precip >= 5.0:
        steps.append("Avoid spraying or heavy fertilizer application while rainfall is active or imminent.")
    else:
        steps.append("Walk the field and check for moisture stress, standing water, and leaf damage before the next task block.")

    if humidity is not None and humidity >= 85.0:
        steps.append("Inspect lower leaves and dense canopy zones first because humidity is high enough to favor fungal problems.")
    else:
        steps.append("Use the calmer weather window to inspect crop uniformity and update notes on weak zones.")

    if temp_now is not None and temp_now >= 32.0:
        steps.append("Shift irrigation or transplant work to the cooler part of the day to reduce heat stress.")
    elif flags.get("irrigation"):
        steps.append("Check soil moisture before watering so irrigation matches actual field need, not schedule only.")

    if flags.get("fertility"):
        steps.append("Base any soil amendment decision on the weakest field sections first instead of applying uniformly across the farm.")
    elif overall_accuracy is not None and overall_accuracy >= 75.0:
        steps.append("Use the app trend data to target small adjustments rather than making a broad whole-farm change today.")

    return steps[:4]


def _product_need_text(realtime_context: Dict[str, Any], flags: Dict[str, bool]) -> List[str]:
    products = _product_lines(realtime_context)
    stores = _store_lines(realtime_context)
    if flags.get("fertility") or flags.get("disease") or flags.get("soil") or flags.get("planting"):
        return (products + stores)[:4] or ["No targeted product recommendation is available yet, so do not buy inputs until the field issue is clearer."]
    return ["No immediate product purchase is indicated from the current weather and app signals."]


def _build_steps(
    planting_question: bool,
    soil_question: bool,
    should_delay: bool,
    humidity: Optional[float],
    precip: Optional[float],
) -> List[str]:
    steps: List[str] = []
    if planting_question:
        if should_delay:
            steps.append("Delay planting until the coldest part of the forecast is above the crop's tolerance range.")
            steps.append("Use the time to prepare beds, improve drainage, and stage inputs near the field.")
        else:
            steps.append("Plant during the mildest part of the day, not at dawn when the soil is coldest.")
            steps.append("Water lightly after planting so the root zone settles without becoming saturated.")
    if soil_question or planting_question:
        steps.append("Use lighter topsoil or compost-rich mix when conditions are cool or wet so roots do not sit in dense, waterlogged media.")
    if humidity is not None and humidity >= 85.0:
        steps.append("Increase spacing and airflow because high humidity raises fungal pressure.")
    if precip is not None and precip >= 3.0:
        steps.append("Avoid heavy fertilizer application right before or during rain to reduce runoff losses.")
    if not steps:
        steps.append("Review the latest weather and app trends again before the next operation window.")
    return steps


def build_action_plan(question: str, app_summary: Dict[str, Any], realtime_context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _action_weather_inputs(realtime_context)
    flags = _question_flags(question)
    reason_state = _decision_reasons(inputs, flags["planting"])
    should_delay = bool(reason_state["should_delay"])
    decision_reasons = reason_state["reasons"]
    is_general = bool(flags["general_farm"] and not flags["planting"] and not flags["soil"])
    if is_general:
        decision = _general_farm_decision(inputs, app_summary)
        steps = _general_farm_steps(inputs, app_summary, flags)
    else:
        decision = _decision_text(flags["planting"], should_delay)
        steps = _build_steps(
            planting_question=flags["planting"],
            soil_question=flags["soil"],
            should_delay=should_delay,
            humidity=inputs.get("humidity"),
            precip=inputs.get("precip"),
        )

    reasoning: List[str] = []
    reasoning.extend(build_data_comparison(app_summary, realtime_context))
    if decision_reasons:
        reasoning.append("Key limiting factors: " + ", ".join(decision_reasons) + ".")

    return {
        "decision": decision,
        "action_steps": steps,
        "reasoning": reasoning,
    }


def flatten_product_suggestions(realtime_context: Dict[str, Any]) -> List[str]:
    return _product_lines(realtime_context) + _store_lines(realtime_context)


def _product_lines(realtime_context: Dict[str, Any]) -> List[str]:
    suggestions: List[str] = []
    products = realtime_context.get("product_recommendations") if isinstance(realtime_context, dict) else {}

    if not isinstance(products, dict):
        return suggestions

    for category, items in products.items():
        if not isinstance(items, list):
            continue
        suggestions.extend(_product_items_for_category(category, items))
    return suggestions


def _product_items_for_category(category: str, items: List[Any]) -> List[str]:
    lines: List[str] = []
    for item in items[:2]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "Unnamed product"
        use_for = item.get("use_for") or []
        use_text = f" for {use_for[0]}" if isinstance(use_for, list) and use_for else ""
        lines.append(f"{name} ({category}){use_text}")
    return lines


def _store_lines(realtime_context: Dict[str, Any]) -> List[str]:
    stores = realtime_context.get("nearby_stores") if isinstance(realtime_context, dict) else []
    if not isinstance(stores, list) or not stores:
        return []
    store_names = [store.get("name") for store in stores[:3] if isinstance(store, dict) and store.get("name")]
    if not store_names:
        return []
    return ["Nearby sourcing options: " + ", ".join(store_names) + "."]


def build_advisor_response(
    question: str,
    farm_context: Dict[str, Any],
    app_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
    action_results: Dict[str, Any],
) -> Dict[str, Any]:
    app_summary = summarize_app_sections(app_context, farm_context)
    flags = _question_flags(question)
    plan = build_action_plan(question, app_summary, realtime_context)
    comparisons = build_data_comparison(app_summary, realtime_context)
    products = _product_need_text(realtime_context, flags)
    action_lines = plan.get("action_steps", [])
    reasoning = plan.get("reasoning", [])

    action_notice = None
    create_farm_result = action_results.get("create_farm") if isinstance(action_results, dict) else None
    if isinstance(create_farm_result, dict):
        if create_farm_result.get("created"):
            farm = create_farm_result.get("farm") or {}
            action_notice = f"Farm '{farm.get('name', 'Unnamed')}' was created and is ready for follow-up analysis."
        elif create_farm_result.get("reason") == "already_exists":
            farm = create_farm_result.get("farm") or {}
            action_notice = f"Farm '{farm.get('name', 'Unnamed')}' already exists, so the AI reused that record."

    product_lines = products[:4] if products else ["No matching product or store recommendation was available for the current issue."]
    comparison_lines = comparisons[:5] if comparisons else ["No app-to-realtime comparison could be produced from the available data."]
    reason_lines = reasoning[:5] if reasoning else comparison_lines

    parts: List[str] = [
        f"Decision: {plan.get('decision')}",
        "",
        "Data comparison:",
    ]
    parts.extend([f"- {line}" for line in comparison_lines])
    parts.extend([
        "",
        "Action plan:",
    ])
    parts.extend([f"- {line}" for line in action_lines])
    parts.extend([
        "",
        "Product and sourcing suggestions:",
    ])
    parts.extend([f"- {line}" for line in product_lines])
    parts.extend([
        "",
        "Why this recommendation:",
    ])
    parts.extend([f"- {line}" for line in reason_lines])
    if action_notice:
        parts.extend(["", f"Action result: {action_notice}"])

    return {
        "decision": plan.get("decision"),
        "app_summary": app_summary,
        "comparison_points": comparison_lines,
        "action_plan": action_lines,
        "product_suggestions": product_lines,
        "reasoning": reason_lines,
        "action_notice": action_notice,
        "formatted_answer": "\n".join(parts).strip(),
    }