# API Specification - UNFROZEN
**Status**: ✅ EDITABLE - All changes allowed  
**Date**: January 30, 2026  
**Unfrozen**: January 30, 2026 @ 14:30 UTC  
**Version**: 1.0.0 (development mode)

---

## BASE URL
```
http://127.0.0.1:8000
```

---

## NDVI ENDPOINTS

### GET /ndvi/farm/{farm_id}/timeseries
**Purpose**: Get NDVI snapshots for a farm within optional date range  
**Parameters**:
- `farm_id` (path, int, required)
- `start_date` (query, string, optional): YYYY-MM-DD format
- `end_date` (query, string, optional): YYYY-MM-DD format

**Response**:
```json
{
  "farm_id": int,
  "count": int,
  "snapshots": [
    {
      "id": int,
      "farm_id": int,
      "date": "YYYY-MM-DD",
      "ndvi_image_path": string,
      "ndvi_stats": {
        "min": float,
        "max": float,
        "mean": float,
        "std": float
      }
    }
  ]
}
```

---

## YIELD ENDPOINTS

### POST /yields/
**Purpose**: Create a new yield estimate  
**Request**:
```json
{
  "farm_id": int,
  "date": "YYYY-MM-DD",
  "yield_estimate": float,
  "notes": string (optional)
}
```

**Response**: 
```json
{
  "id": int,
  "farm_id": int,
  "date": "YYYY-MM-DD",
  "yield_estimate": float,
  "message": "Yield estimate created successfully"
}
```

### GET /yields/{yield_id}
**Purpose**: Get yield estimate by ID  
**Response**:
```json
{
  "id": int,
  "farm_id": int,
  "date": "YYYY-MM-DD",
  "yield_estimate": float,
  "notes": string
}
```

### GET /yields/farm/{farm_id}
**Purpose**: Get all yield estimates for a farm  
**Parameters**:
- `farm_id` (path, int, required)
- `start_date` (query, string, optional)
- `end_date` (query, string, optional)

**Response**:
```json
{
  "farm_id": int,
  "count": int,
  "yields": [
    {
      "id": int,
      "date": "YYYY-MM-DD",
      "yield_estimate": float,
      "notes": string
    }
  ]
}
```

### GET /yields/farm/{farm_id}/geojson
**Purpose**: Get farm yields as GeoJSON for map visualization  
**Response**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": int,
        "farm_id": int,
        "date": "YYYY-MM-DD",
        "yield_estimate": float,
        "notes": string
      },
      "geometry": {
        "type": "Point",
        "coordinates": [lon, lat]
      }
    }
  ]
}
```

---

## FARMER YIELD REPORTS (VALIDATION DATA)

### POST /yields/reports/
**Purpose**: Create farmer-reported actual yield for validation  
**Request**:
```json
{
  "farm_id": int,
  "yield_result_id": int (optional),
  "date": "YYYY-MM-DD",
  "actual_yield": float,
  "notes": string (optional)
}
```

**Response**:
```json
{
  "id": int,
  "farm_id": int,
  "date": "YYYY-MM-DD",
  "actual_yield": float,
  "message": "Farmer yield report created successfully"
}
```

### GET /yields/reports/farm/{farm_id}
**Purpose**: Get all farmer-reported yields for a farm  
**Response**:
```json
{
  "farm_id": int,
  "count": int,
  "reports": [
    {
      "id": int,
      "date": "YYYY-MM-DD",
      "actual_yield": float,
      "yield_result_id": int,
      "reported_date": "YYYY-MM-DD",
      "notes": string
    }
  ]
}
```

---

## HISTORICAL YIELD ENDPOINTS

### POST /yields/historical/
**Purpose**: Create historical yield average baseline  
**Request**:
```json
{
  "farm_id": int,
  "crop_type": string,
  "year": int,
  "avg_yield": float,
  "min_yield": float (optional),
  "max_yield": float (optional),
  "sample_count": int (optional)
}
```

**Response**:
```json
{
  "id": int,
  "farm_id": int,
  "year": int,
  "avg_yield": float,
  "message": "Historical yield average created successfully"
}
```

### GET /yields/historical/farm/{farm_id}
**Purpose**: Get historical yield averages for a farm  
**Response**:
```json
{
  "farm_id": int,
  "count": int,
  "historical_averages": [
    {
      "id": int,
      "year": int,
      "crop_type": string,
      "avg_yield": float,
      "min_yield": float,
      "max_yield": float,
      "sample_count": int
    }
  ]
}
```

---

## VALIDATION & COMPARISON ENDPOINTS

### GET /yields/farm/{farm_id}/comparison
**Purpose**: Compare NDVI-based yield predictions vs actual farmer yields across seasons  
**Parameters**:
- `farm_id` (path, int, required)
- `num_seasons` (query, int, optional, default=2, range: 1-10)

**Response**:
```json
{
  "farm_id": int,
  "crop_type": string,
  "seasons_compared": int,
  "seasonal_metrics": [
    {
      "season": "YYYY-YYYY+1",
      "year": int,
      "predicted_yield_avg": float,
      "actual_yield_avg": float,
      "deviation_percent": float,
      "trend_correct": boolean,
      "trend_description": string,
      "historical_avg": float,
      "historical_min": float,
      "historical_max": float,
      "avg_ndvi": float,
      "predictions_count": int,
      "reports_count": int,
      "ndvi_observations": int
    }
  ]
}
```

### GET /yields/farm/{farm_id}/accuracy
**Purpose**: Get overall prediction accuracy metrics  
**Response**:
```json
{
  "farm_id": int,
  "accuracy_metrics": {
    "sample_count": int,
    "mape": float,
    "mean_absolute_deviation": float,
    "accuracy_rating": string,
    "min_deviation": float,
    "max_deviation": float
  }
}
```

### GET /yields/farm/{farm_id}/ndvi-correlation
**Purpose**: Analyze correlation between NDVI and yield estimates  
**Parameters**:
- `days_lag` (query, int, optional, default=30, range: 1-180)

**Response**:
```json
{
  "farm_id": int,
  "correlation_analysis": {
    "correlation_coefficient": float,
    "interpretation": string,
    "paired_count": int,
    "days_lag": int
  }
}
```

### GET /yields/farm/{farm_id}/validation-dashboard
**Purpose**: Complete validation dashboard combining all metrics  
**Parameters**:
- `num_seasons` (query, int, optional, default=2, range: 1-10)

**Response**:
```json
{
  "farm_id": int,
  "farm_name": string,
  "crop_type": string,
  "seasons_data": [/* seasonal_metrics array */],
  "overall_accuracy": {/* accuracy_metrics object */},
  "ndvi_correlation": {/* correlation_analysis object */},
  "summary": {
    "avg_deviation_percent": float,
    "trends_correct_percent": float,
    "total_seasons_analyzed": int,
    "prediction_samples": int
  }
}
```

---

## TILE ENDPOINTS

### POST /tiles/yield/farm/{farm_id}/generate
**Purpose**: Generate colored GeoTIFF and tile data from yield data  
**Response**:
```json
{
  "status": "generated",
  "farm_id": int,
  "raster": string,
  "tilejson": string
}
```

### GET /tiles/yield/farm/{farm_id}/tilejson
**Purpose**: Get TileJSON manifest for yield layer  
**Response**: TileJSON 2.1 format

### GET /tiles/yield/farm/{farm_id}/tile/{z}/{x}/{y}.png
**Purpose**: Get PNG tile for yield layer at XYZ coordinates  
**Response**: PNG image bytes

---

## ERROR RESPONSES

All errors follow this format:
```json
{
  "detail": string
}
```

**HTTP Status Codes**:
- `200 OK` - Success
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Invalid request data
- `500 Internal Server Error` - Server error

---

## DEVELOPMENT RULES (UNFROZEN)

✅ **ALL CHANGES ALLOWED**:
- New endpoints
- Endpoint modifications
- Schema changes
- Parameter additions/changes
- Response format changes
- All bug fixes and improvements

⚠️ **BEST PRACTICES**:
- Document changes
- Update tests
- Consider backward compatibility
- Version appropriately

---

## DEPRECATION NOTICE

No endpoints are deprecated at this time.
