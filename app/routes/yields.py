from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict, Any
from app.models.db_models import (
    YieldResult, 
    Farm, 
    FarmerYieldReport,
    HistoricalYieldAverage,
    NDVISnapshot,
)
from app.dependencies import get_db
from app.services.comparison import (
    get_seasonal_comparison,
    get_overall_accuracy,
    get_ndvi_yield_correlation
)

router = APIRouter()

class YieldCreate(BaseModel):
    farm_id: int
    date: str
    yield_estimate: float
    notes: Optional[str] = None

class FarmerYieldReportCreate(BaseModel):
    """Actual harvested yield reported by farmer"""
    farm_id: int
    yield_result_id: Optional[int] = None  # Link to predicted yield
    date: str  # Harvest date
    actual_yield: float  # kg/ha
    notes: Optional[str] = None

class HistoricalYieldCreate(BaseModel):
    """Historical baseline yield for comparison"""
    farm_id: int
    crop_type: str
    year: int
    avg_yield: float
    min_yield: Optional[float] = None
    max_yield: Optional[float] = None
    sample_count: Optional[int] = None

class YieldResponse(BaseModel):
    id: int
    farm_id: int
    date: str
    yield_estimate: float
    notes: Optional[str]

@router.post("/")
def create_yield(yield_data: YieldCreate, db: Session = Depends(get_db)):
    """Create a new yield estimate for a farm"""
    farm = db.query(Farm).filter(Farm.id == yield_data.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    new_yield = YieldResult(
        farm_id=yield_data.farm_id,
        date=date.fromisoformat(yield_data.date),
        yield_estimate=yield_data.yield_estimate,
        notes=yield_data.notes
    )
    
    db.add(new_yield)
    db.commit()
    db.refresh(new_yield)
    
    return {
        "id": new_yield.id,
        "farm_id": new_yield.farm_id,
        "date": new_yield.date.isoformat(),
        "yield_estimate": new_yield.yield_estimate,
        "message": "Yield estimate created successfully"
    }

@router.get("/{yield_id}")
def get_yield(yield_id: int, db: Session = Depends(get_db)):
    """Get yield estimate by ID"""
    yield_result = db.query(YieldResult).filter(YieldResult.id == yield_id).first()
    if not yield_result:
        raise HTTPException(status_code=404, detail="Yield not found")
    
    return {
        "id": yield_result.id,
        "farm_id": yield_result.farm_id,
        "date": yield_result.date.isoformat(),
        "yield_estimate": yield_result.yield_estimate,
        "notes": yield_result.notes
    }

@router.get("/farm/{farm_id}")
def get_farm_yields(
    farm_id: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all yield estimates for a farm with optional date range"""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    query = db.query(YieldResult).filter(YieldResult.farm_id == farm_id)
    
    if start_date:
        query = query.filter(YieldResult.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(YieldResult.date <= date.fromisoformat(end_date))
    
    yields = query.order_by(YieldResult.date.desc()).all()
    
    return {
        "farm_id": farm_id,
        "count": len(yields),
        "yields": [
            {
                "id": y.id,
                "date": y.date.isoformat(),
                "yield_estimate": y.yield_estimate,
                "notes": y.notes
            }
            for y in yields
        ]
    }

@router.get("/farm/{farm_id}/geojson")
def get_farm_yields_geojson(
    farm_id: int,
    db: Session = Depends(get_db)
):
    """Get farm yields as GeoJSON for map visualization"""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    yields = db.query(YieldResult).filter(YieldResult.farm_id == farm_id).all()
    
    # Create GeoJSON feature collection
    features = []
    for y in yields:
        features.append({
            "type": "Feature",
            "properties": {
                "id": y.id,
                "farm_id": y.farm_id,
                "date": y.date.isoformat(),
                "yield_estimate": y.yield_estimate,
                "notes": y.notes
            },
            "geometry": {
                "type": "Point",
                # This would use farm's centroid in real implementation
                "coordinates": [0, 0]
            }
        })
    
    return {
        "type": "FeatureCollection",
        "features": features
    }


# ============================================================================
# FARMER REPORTED YIELDS - Actual harvest data for validation
# ============================================================================

@router.post("/reports/")
def create_farmer_report(
    report_data: FarmerYieldReportCreate,
    db: Session = Depends(get_db)
):
    """Create farmer-reported actual yield for validation"""
    farm = db.query(Farm).filter(Farm.id == report_data.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    new_report = FarmerYieldReport(
        farm_id=report_data.farm_id,
        yield_result_id=report_data.yield_result_id,
        date=date.fromisoformat(report_data.date),
        actual_yield=report_data.actual_yield,
        reported_date=date.today(),
        notes=report_data.notes
    )
    
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    
    return {
        "id": new_report.id,
        "farm_id": new_report.farm_id,
        "date": new_report.date.isoformat(),
        "actual_yield": new_report.actual_yield,
        "message": "Farmer yield report created successfully"
    }

@router.get("/reports/farm/{farm_id}")
def get_farmer_reports(
    farm_id: int,
    db: Session = Depends(get_db)
):
    """Get all farmer-reported yields for a farm"""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    reports = db.query(FarmerYieldReport).filter(
        FarmerYieldReport.farm_id == farm_id
    ).order_by(FarmerYieldReport.date.desc()).all()

    if not reports:
        predicted = db.query(YieldResult).filter(
            YieldResult.farm_id == farm_id
        ).order_by(YieldResult.date.desc()).all()

        return [
            {
                "id": -p.id,
                "date": p.date.isoformat(),
                "actual_yield": p.yield_estimate,
                "yield_result_id": p.id,
                "reported_date": p.date.isoformat(),
                "notes": "Predicted baseline (no farmer report submitted)",
                "source": "predicted",
                "report": "predicted",
                "report_type": "predicted",
                "type": "predicted",
            }
            for p in predicted
        ]
    
    return [
        {
            "id": r.id,
            "date": r.date.isoformat(),
            "actual_yield": r.actual_yield,
            "yield_result_id": r.yield_result_id,
            "reported_date": r.reported_date.isoformat(),
            "notes": r.notes or "Farmer report submitted",
            "source": "farmer",
            "report": "farmer",
            "report_type": "farmer",
            "type": "farmer",
        }
        for r in reports
    ]


# ============================================================================
# HISTORICAL YIELD AVERAGES - Baseline for comparison
# ============================================================================

@router.post("/historical/")
def create_historical_average(
    hist_data: HistoricalYieldCreate,
    db: Session = Depends(get_db)
):
    """Create historical yield average baseline"""
    farm = db.query(Farm).filter(Farm.id == hist_data.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    new_hist = HistoricalYieldAverage(
        farm_id=hist_data.farm_id,
        crop_type=hist_data.crop_type,
        year=hist_data.year,
        avg_yield=hist_data.avg_yield,
        min_yield=hist_data.min_yield,
        max_yield=hist_data.max_yield,
        sample_count=hist_data.sample_count or 1
    )
    
    db.add(new_hist)
    db.commit()
    db.refresh(new_hist)
    
    return {
        "id": new_hist.id,
        "farm_id": new_hist.farm_id,
        "year": new_hist.year,
        "avg_yield": new_hist.avg_yield,
        "message": "Historical yield average created successfully"
    }

@router.get("/historical/farm/{farm_id}")
def get_historical_averages(
    farm_id: int,
    db: Session = Depends(get_db)
):
    """Get historical yield averages for a farm"""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    averages = db.query(HistoricalYieldAverage).filter(
        HistoricalYieldAverage.farm_id == farm_id
    ).order_by(HistoricalYieldAverage.year.desc()).all()
    
    return {
        "farm_id": farm_id,
        "count": len(averages),
        "historical_averages": [
            {
                "id": h.id,
                "year": h.year,
                "crop_type": h.crop_type,
                "avg_yield": h.avg_yield,
                "min_yield": h.min_yield,
                "max_yield": h.max_yield,
                "sample_count": h.sample_count
            }
            for h in averages
        ]
    }


# ============================================================================
# VALIDATION & ACCURACY METRICS - Comparison endpoints
# ============================================================================

@router.get("/farm/{farm_id}/comparison")
def get_yield_comparison(
    farm_id: int,
    num_seasons: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """
    Compare NDVI-based yield predictions vs actual farmer yields across seasons.
    
    Returns seasonal metrics:
    - Predicted vs Actual yields
    - % Deviation
    - Trend correctness (up/down agreement)
    - Historical averages for reference
    - NDVI statistics
    """
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    seasonal_data = get_seasonal_comparison(
        farm_id=farm_id,
        db=db,
        num_seasons=num_seasons
    )
    
    return {
        "farm_id": farm_id,
        "crop_type": farm.crop_type,
        "seasons_compared": num_seasons,
        "seasonal_metrics": seasonal_data
    }

@router.get("/farm/{farm_id}/accuracy")
def get_accuracy_metrics(
    farm_id: int,
    db: Session = Depends(get_db)
):
    """
    Get overall prediction accuracy metrics across all available data.
    
    Returns:
    - MAPE (Mean Absolute Percentage Error)
    - Mean absolute deviation
    - Sample count
    - Accuracy rating (Excellent/Good/Fair/Needs Improvement)
    """
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    accuracy = get_overall_accuracy(farm_id=farm_id, db=db)
    
    return {
        "farm_id": farm_id,
        "accuracy_metrics": accuracy
    }

@router.get("/farm/{farm_id}/ndvi-correlation")
def get_ndvi_correlation(
    farm_id: int,
    days_lag: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db)
):
    """
    Analyze correlation between NDVI and yield estimates.
    
    Args:
        days_lag: Number of days to look back for NDVI when comparing to yields
    
    Returns:
    - Correlation coefficient (-1.0 to 1.0)
    - Interpretation (Strong/Moderate/Weak positive/negative)
    - Number of paired observations
    """
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    correlation = get_ndvi_yield_correlation(
        farm_id=farm_id,
        db=db,
        days_lag=days_lag
    )
    
    return {
        "farm_id": farm_id,
        "correlation_analysis": correlation
    }

@router.get("/farm/{farm_id}/validation-dashboard")
def get_validation_dashboard(
    farm_id: int,
    num_seasons: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Complete validation dashboard combining:
    - Seasonal comparison data
    - Overall accuracy metrics
    - NDVI-Yield correlation
    """
    return _build_farm_yield_analytics(
        farm_id=farm_id,
        num_seasons=num_seasons,
        db=db
    )


def _build_farm_yield_analytics(
    farm_id: int,
    num_seasons: int,
    db: Session
) -> Dict[str, Any]:
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    seasonal = get_seasonal_comparison(farm_id=farm_id, db=db, num_seasons=num_seasons)
    accuracy = get_overall_accuracy(farm_id=farm_id, db=db)
    correlation = get_ndvi_yield_correlation(farm_id=farm_id, db=db)
    reports = db.query(FarmerYieldReport).filter(
        FarmerYieldReport.farm_id == farm_id
    ).order_by(FarmerYieldReport.date.desc()).all()
    yields = db.query(YieldResult).filter(YieldResult.farm_id == farm_id).all()

    report_rows = reports
    report_source = "farmer"
    if not report_rows and yields:
        report_rows = [
            FarmerYieldReport(
                id=-y.id,
                farm_id=farm_id,
                yield_result_id=y.id,
                date=y.date,
                actual_yield=y.yield_estimate,
                reported_date=y.date,
                notes="Predicted baseline (no farmer report submitted)",
            )
            for y in sorted(yields, key=lambda y: y.date, reverse=True)
        ]
        report_source = "predicted"
    
    # Calculate summary statistics
    deviations = [s["deviation_percent"] for s in seasonal if s["deviation_percent"] is not None]
    trend_correct = [s["trend_correct"] for s in seasonal if s["trend_correct"] is not None]

    sorted_seasons = sorted(seasonal, key=lambda s: s.get("year", 0), reverse=True)
    yoy_change = None
    if len(sorted_seasons) >= 2:
        latest = sorted_seasons[0].get("predicted_yield_avg")
        previous = sorted_seasons[1].get("predicted_yield_avg")
        if latest is not None and previous not in (None, 0):
            yoy_change = round(((latest - previous) / abs(previous)) * 100, 2)

    ndvi_count = db.query(NDVISnapshot).filter(
        NDVISnapshot.farm_id == farm_id
    ).count()
    prediction_count = len(yields)
    report_count = len(report_rows)
    linkage_rate = 0.0
    if report_count > 0:
        linked = sum(1 for r in report_rows if r.yield_result_id is not None)
        linkage_rate = round((linked / report_count) * 100, 1)

    report_completeness = 0.0
    if prediction_count > 0:
        report_completeness = round((report_count / prediction_count) * 100, 1)
    
    return {
        "farm_id": farm_id,
        "farm_name": farm.name,
        "crop_type": farm.crop_type,
        "seasons_data": seasonal,
        "overall_accuracy": accuracy,
        "ndvi_correlation": correlation,
        "year_over_year": {
            "change_percent": yoy_change,
            "latest_season": sorted_seasons[0]["season"] if sorted_seasons else None,
            "previous_season": sorted_seasons[1]["season"] if len(sorted_seasons) >= 2 else None,
            "status": "insufficient_history" if yoy_change is None else ("up" if yoy_change > 0 else "down" if yoy_change < 0 else "flat"),
        },
        "data_quality": {
            "prediction_count": prediction_count,
            "farmer_report_count": report_count,
            "ndvi_snapshot_count": ndvi_count,
            "report_linkage_rate_percent": linkage_rate,
            "report_completeness_percent": report_completeness,
        },
        "farmer_reports": {
            "count": report_count,
            "source": report_source,
            "latest": [
                {
                    "id": r.id,
                    "date": r.date.isoformat(),
                    "actual_yield": r.actual_yield,
                    "yield_result_id": r.yield_result_id,
                    "notes": r.notes,
                }
                for r in report_rows[:5]
            ],
        },
        "summary": {
            "avg_deviation_percent": round(sum(deviations) / len(deviations), 2) if deviations else None,
            "trends_correct_percent": round(sum(1 for t in trend_correct if t) / len(trend_correct) * 100, 1) if trend_correct else None,
            "total_seasons_analyzed": len(seasonal),
            "prediction_samples": accuracy.get("sample_count", 0)
        }
    }


@router.get("/farm/{farm_id}/analytics")
def get_farm_yield_analytics(
    farm_id: int,
    num_seasons: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Primary farm-specific yield analytics endpoint for frontend integration.

    This is an alias of /farm/{farm_id}/validation-dashboard and returns:
    - seasonal comparison data
    - overall accuracy metrics
    - NDVI-yield correlation
    - summary KPIs
    """
    return _build_farm_yield_analytics(
        farm_id=farm_id,
        num_seasons=num_seasons,
        db=db
    )


@router.get("/farm/{farm_id}/analyze")
def analyze_farm_yields(
    farm_id: int,
    num_seasons: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Compatibility endpoint for frontend tabs labeled "Analyze your yields".
    """
    return _build_farm_yield_analytics(
        farm_id=farm_id,
        num_seasons=num_seasons,
        db=db
    )


