"""
Yield prediction validation and accuracy metrics
Compare NDVI-based yield predictions against:
- Farmer-reported actual yields
- Historical yield averages
- Trend analysis (up/down correctness)
"""

from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.db_models import (
    YieldResult, 
    FarmerYieldReport, 
    HistoricalYieldAverage,
    NDVISnapshot,
    Farm
)


def calculate_deviation_percent(predicted: float, actual: float) -> float:
    """
    Calculate percentage deviation of prediction from actual value.
    
    Returns: ((predicted - actual) / actual) * 100
    Positive = overestimate, Negative = underestimate
    """
    if actual == 0:
        return 0.0
    return ((predicted - actual) / abs(actual)) * 100


def calculate_mape(predictions: List[float], actuals: List[float]) -> float:
    """
    Mean Absolute Percentage Error - average absolute deviation across multiple samples.
    Useful for comparing prediction accuracy across multiple years/seasons.
    """
    if not predictions or len(predictions) != len(actuals):
        return 0.0
    
    deviations = [
        abs((p - a) / abs(a)) * 100 
        for p, a in zip(predictions, actuals) 
        if a != 0
    ]
    return sum(deviations) / len(deviations) if deviations else 0.0


def calculate_trend_correctness(
    predicted_values: List[Tuple[date, float]], 
    actual_values: List[Tuple[date, float]]
) -> Tuple[bool, str]:
    """
    Determine if prediction trend matches actual trend.
    
    Args:
        predicted_values: List of (date, yield) tuples
        actual_values: List of (date, yield) tuples
    
    Returns:
        (is_correct, trend_description)
        - is_correct: Boolean if trends match
        - trend_description: e.g., "UP/UP", "DOWN/DOWN", "UP/DOWN (incorrect)"
    """
    if len(predicted_values) < 2 or len(actual_values) < 2:
        return (None, "Insufficient data for trend analysis")
    
    # Sort by date
    pred_sorted = sorted(predicted_values, key=lambda x: x[0])
    actual_sorted = sorted(actual_values, key=lambda x: x[0])
    
    # Calculate trends (first to last value)
    pred_trend = "UP" if pred_sorted[-1][1] > pred_sorted[0][1] else "DOWN"
    actual_trend = "UP" if actual_sorted[-1][1] > actual_sorted[0][1] else "DOWN"
    
    is_correct = pred_trend == actual_trend
    description = f"{pred_trend}/{actual_trend}" + (
        "" if is_correct else " (incorrect)"
    )
    
    return (is_correct, description)


def get_seasonal_comparison(
    farm_id: int,
    db: Session,
    season_start_month: int = 5,  # May (growing season start)
    season_end_month: int = 10,   # October (harvest)
    num_seasons: int = 2
) -> List[Dict]:
    """
    Compare NDVI-based yield predictions vs actual farmer-reported yields
    across multiple growing seasons.
    
    Args:
        farm_id: Farm ID
        db: Database session
        season_start_month: Start of growing season (1-12)
        season_end_month: End of season (1-12)
        num_seasons: Number of past seasons to include
    
    Returns:
        List of season comparison objects with metrics
    """
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        return []
    
    comparisons = []
    current_year = date.today().year
    
    for season_offset in range(num_seasons):
        season_year = current_year - season_offset
        
        # Get predicted yields for this season
        season_start = date(season_year, season_start_month, 1)
        season_end = date(season_year, season_end_month, 28)
        
        predicted_yields = db.query(YieldResult).filter(
            YieldResult.farm_id == farm_id,
            YieldResult.date >= season_start,
            YieldResult.date <= season_end
        ).all()

        if not predicted_yields and season_offset == 0:
            fallback_start = date.today() - timedelta(days=365)
            predicted_yields = db.query(YieldResult).filter(
                YieldResult.farm_id == farm_id,
                YieldResult.date >= fallback_start,
                YieldResult.date <= date.today()
            ).all()
        
        # Get actual/reported yields for this season
        actual_yields = db.query(FarmerYieldReport).filter(
            FarmerYieldReport.farm_id == farm_id,
            FarmerYieldReport.date >= season_start,
            FarmerYieldReport.date <= season_end
        ).all()

        if not actual_yields and season_offset == 0:
            fallback_start = date.today() - timedelta(days=365)
            actual_yields = db.query(FarmerYieldReport).filter(
                FarmerYieldReport.farm_id == farm_id,
                FarmerYieldReport.date >= fallback_start,
                FarmerYieldReport.date <= date.today()
            ).all()
        
        # Get NDVI stats for season
        ndvi_records = db.query(NDVISnapshot).filter(
            NDVISnapshot.farm_id == farm_id,
            NDVISnapshot.date >= season_start,
            NDVISnapshot.date <= season_end
        ).all()

        if not ndvi_records and season_offset == 0:
            fallback_start = date.today() - timedelta(days=365)
            ndvi_records = db.query(NDVISnapshot).filter(
                NDVISnapshot.farm_id == farm_id,
                NDVISnapshot.date >= fallback_start,
                NDVISnapshot.date <= date.today()
            ).all()
        
        # Get historical average for crop type
        historical = db.query(HistoricalYieldAverage).filter(
            HistoricalYieldAverage.farm_id == farm_id,
            HistoricalYieldAverage.crop_type == farm.crop_type,
            HistoricalYieldAverage.year == season_year
        ).first()
        
        if predicted_yields and actual_yields:
            avg_predicted = sum(y.yield_estimate for y in predicted_yields) / len(predicted_yields)
            avg_actual = sum(y.actual_yield for y in actual_yields) / len(actual_yields)
            
            deviation = calculate_deviation_percent(avg_predicted, avg_actual)
            
            trend_pred = [(y.date, y.yield_estimate) for y in predicted_yields]
            trend_actual = [(y.date, y.actual_yield) for y in actual_yields]
            trend_correct, trend_desc = calculate_trend_correctness(trend_pred, trend_actual)
            
            avg_ndvi = None
            if ndvi_records:
                ndvi_stats = [y.ndvi_stats for y in ndvi_records if y.ndvi_stats]
                if ndvi_stats:
                    avg_ndvi = sum(s.get('avg', 0) for s in ndvi_stats) / len(ndvi_stats)
            
            comparisons.append({
                "season": f"{season_year}-{season_year+1}",
                "year": season_year,
                "predicted_yield_avg": round(avg_predicted, 2),
                "actual_yield_avg": round(avg_actual, 2),
                "deviation_percent": round(deviation, 2),
                "trend_correct": trend_correct,
                "trend_description": trend_desc,
                "historical_avg": round(historical.avg_yield, 2) if historical else None,
                "historical_min": round(historical.min_yield, 2) if historical else None,
                "historical_max": round(historical.max_yield, 2) if historical else None,
                "avg_ndvi": round(avg_ndvi, 3) if avg_ndvi else None,
                "predictions_count": len(predicted_yields),
                "reports_count": len(actual_yields),
                "ndvi_observations": len(ndvi_records)
            })
        elif predicted_yields:
            avg_predicted = sum(y.yield_estimate for y in predicted_yields) / len(predicted_yields)

            avg_ndvi = None
            if ndvi_records:
                ndvi_stats = [y.ndvi_stats for y in ndvi_records if y.ndvi_stats]
                if ndvi_stats:
                    avg_ndvi = sum(s.get('avg', 0) for s in ndvi_stats) / len(ndvi_stats)

            comparisons.append({
                "season": f"{season_year}-{season_year+1}",
                "year": season_year,
                "predicted_yield_avg": round(avg_predicted, 2),
                "actual_yield_avg": round(avg_predicted, 2),
                "deviation_percent": 0.0,
                "trend_correct": True,
                "trend_description": "Predicted only",
                "historical_avg": round(historical.avg_yield, 2) if historical else None,
                "historical_min": round(historical.min_yield, 2) if historical else None,
                "historical_max": round(historical.max_yield, 2) if historical else None,
                "avg_ndvi": round(avg_ndvi, 3) if avg_ndvi else None,
                "predictions_count": len(predicted_yields),
                "reports_count": 0,
                "ndvi_observations": len(ndvi_records)
            })
    
    return comparisons


def get_overall_accuracy(
    farm_id: int,
    db: Session
) -> Dict:
    """
    Calculate overall prediction accuracy metrics across all available data.
    """
    # Get all paired predictions and reports
    reports = db.query(FarmerYieldReport).filter(
        FarmerYieldReport.farm_id == farm_id,
        FarmerYieldReport.yield_result_id.isnot(None)
    ).all()
    
    if not reports:
        predicted_count = db.query(YieldResult).filter(
            YieldResult.farm_id == farm_id
        ).count()

        if predicted_count > 0:
            return {
                "sample_count": predicted_count,
                "mape": 0.0,
                "mean_absolute_deviation": 0.0,
                "accuracy_rating": "Predicted only (no farmer reports)",
                "min_deviation": 0.0,
                "max_deviation": 0.0,
            }

        return {
            "sample_count": 0,
            "mape": None,
            "mean_deviation": None,
            "accuracy_rating": "Insufficient data"
        }
    
    predictions = []
    actuals = []
    deviations = []
    
    for report in reports:
        if report.yield_estimate_record:
            predictions.append(report.yield_estimate_record.yield_estimate)
            actuals.append(report.actual_yield)
            dev = calculate_deviation_percent(
                report.yield_estimate_record.yield_estimate,
                report.actual_yield
            )
            deviations.append(abs(dev))
    
    if not predictions:
        predicted_count = db.query(YieldResult).filter(
            YieldResult.farm_id == farm_id
        ).count()

        if predicted_count > 0:
            return {
                "sample_count": predicted_count,
                "mape": 0.0,
                "mean_absolute_deviation": 0.0,
                "accuracy_rating": "Predicted only (no linked farmer reports)",
                "min_deviation": 0.0,
                "max_deviation": 0.0,
            }

        return {
            "sample_count": 0,
            "mape": None,
            "mean_deviation": None,
            "accuracy_rating": "No paired predictions"
        }
    
    mape = calculate_mape(predictions, actuals)
    mean_dev = sum(deviations) / len(deviations)
    
    # Accuracy rating based on MAPE
    if mape < 10:
        rating = "Excellent (±10%)"
    elif mape < 20:
        rating = "Good (±20%)"
    elif mape < 35:
        rating = "Fair (±35%)"
    else:
        rating = "Needs improvement (>35%)"
    
    return {
        "sample_count": len(predictions),
        "mape": round(mape, 2),
        "mean_absolute_deviation": round(mean_dev, 2),
        "accuracy_rating": rating,
        "min_deviation": round(min(deviations), 2),
        "max_deviation": round(max(deviations), 2)
    }


def get_ndvi_yield_correlation(
    farm_id: int,
    db: Session,
    days_lag: int = 30
) -> Dict:
    """
    Analyze correlation between NDVI and yield estimates.
    
    Args:
        farm_id: Farm ID
        db: Database session
        days_lag: Number of days to look back for NDVI when comparing to yields
    
    Returns:
        Correlation metrics and analysis
    """
    yields = db.query(YieldResult).filter(
        YieldResult.farm_id == farm_id
    ).all()
    
    if not yields:
        return {
            "correlation_coefficient": None,
            "interpretation": "No yield data",
            "paired_count": 0,
            "days_lag": days_lag,
        }
    
    ndvi_by_date = {}
    ndvi_records = db.query(NDVISnapshot).filter(
        NDVISnapshot.farm_id == farm_id
    ).all()
    
    for record in ndvi_records:
        if record.ndvi_stats:
            ndvi_by_date[record.date] = record.ndvi_stats.get('avg', 0)
    
    if not ndvi_by_date:
        return {
            "correlation_coefficient": None,
            "interpretation": "No NDVI data",
            "paired_count": 0,
            "days_lag": days_lag,
        }
    
    # Pair yields with nearby NDVI observations
    yield_ndvi_pairs = []
    for y in yields:
        # Find NDVI within lag window
        for ndvi_date, ndvi_val in ndvi_by_date.items():
            days_diff = abs((y.date - ndvi_date).days)
            if days_diff <= days_lag:
                yield_ndvi_pairs.append((ndvi_val, y.yield_estimate))
                break
    
    if len(yield_ndvi_pairs) < 2:
        return {
            "correlation_coefficient": None,
            "interpretation": "Insufficient paired observations",
            "paired_count": len(yield_ndvi_pairs),
            "days_lag": days_lag,
        }
    
    # Simple correlation (Pearson-like)
    ndvi_vals = [p[0] for p in yield_ndvi_pairs]
    yield_vals = [p[1] for p in yield_ndvi_pairs]
    
    # Calculate means
    ndvi_mean = sum(ndvi_vals) / len(ndvi_vals)
    yield_mean = sum(yield_vals) / len(yield_vals)
    
    # Covariance and standard deviations
    cov = sum((n - ndvi_mean) * (y - yield_mean) for n, y in yield_ndvi_pairs) / len(yield_ndvi_pairs)
    ndvi_std = (sum((n - ndvi_mean)**2 for n in ndvi_vals) / len(ndvi_vals))**0.5
    yield_std = (sum((y - yield_mean)**2 for y in yield_vals) / len(yield_vals))**0.5
    
    correlation = cov / (ndvi_std * yield_std) if ndvi_std * yield_std > 0 else 0
    
    if correlation > 0.7:
        interpretation = "Strong positive"
    elif correlation > 0.4:
        interpretation = "Moderate positive"
    elif correlation > 0.1:
        interpretation = "Weak positive"
    elif correlation > -0.1:
        interpretation = "No correlation"
    elif correlation > -0.4:
        interpretation = "Weak negative"
    elif correlation > -0.7:
        interpretation = "Moderate negative"
    else:
        interpretation = "Strong negative"
    
    return {
        "correlation_coefficient": round(correlation, 3),
        "interpretation": interpretation,
        "paired_count": len(yield_ndvi_pairs),
        "days_lag": days_lag
    }
