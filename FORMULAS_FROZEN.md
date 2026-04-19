# YIELD PREDICTION & VALIDATION FORMULAS - UNFROZEN
**Status**: ✅ EDITABLE - All changes allowed  
**Date**: January 30, 2026  
**Unfrozen**: January 30, 2026 @ 14:30 UTC  
**Version**: 1.0.0 (development mode)

---

## DEVIATION CALCULATION

**Formula**: Percentage deviation of prediction from actual value

```
deviation_percent = ((predicted - actual) / actual) * 100
```

**Interpretation**:
- `> 0`: Overestimate (prediction higher than actual)
- `< 0`: Underestimate (prediction lower than actual)
- `= 0`: Perfect prediction

**Example**:
- Predicted: 4500 kg/ha
- Actual: 4400 kg/ha
- Deviation: ((4500 - 4400) / 4400) × 100 = +2.27%

**Constraints**:
- Returns 0.0 if actual = 0
- Always calculated for each paired prediction-report

---

## MEAN ABSOLUTE PERCENTAGE ERROR (MAPE)

**Formula**: Average absolute deviation across multiple predictions

```
MAPE = (1/n) * Σ |((predicted_i - actual_i) / actual_i) × 100|
```

Where n = number of paired samples, actual_i ≠ 0

**Purpose**: Measure overall prediction accuracy across all seasons

**Example**:
- Predictions: [4350, 4450, 4500]
- Actuals: [4320, 4480, 4520]
- Deviations: [+0.70%, -0.67%, -0.44%]
- MAPE: (0.70 + 0.67 + 0.44) / 3 = 0.60%

**Accuracy Ratings**:
- `< 10%`: Excellent (±10%)
- `< 20%`: Good (±20%)
- `< 35%`: Fair (±35%)
- `≥ 35%`: Needs Improvement (>35%)

**Requirements**:
- Minimum 1 paired sample
- Returns None if no paired data

---

## TREND CORRECTNESS

**Formula**: Directional agreement between predicted and actual trends

```
predicted_trend = "UP" if max(predicted_values) > min(predicted_values) else "DOWN"
actual_trend = "UP" if max(actual_values) > min(actual_values) else "DOWN"
is_correct = (predicted_trend == actual_trend)
```

**Process**:
1. Sort values by date (ascending)
2. Compare first and last values
3. Determine trend (UP if last > first, DOWN otherwise)
4. Return boolean and string description

**Output Format**: `"{PRED_TREND}/{ACTUAL_TREND}"` or with note if incorrect

**Examples**:
- Predicted: [4350, 4450, 4500] → UP
- Actual: [4320, 4480, 4520] → UP
- Result: `true, "UP/UP"`

- Predicted: [4500, 4450, 4350] → DOWN
- Actual: [4520, 4480, 4320] → DOWN
- Result: `true, "DOWN/DOWN"`

- Predicted: [4350, 4450, 4500] → UP
- Actual: [4520, 4480, 4320] → DOWN
- Result: `false, "UP/DOWN (incorrect)"`

**Requirements**:
- Minimum 2 values in each series
- Returns (None, "Insufficient data") if < 2 values

---

## SEASONAL COMPARISON LOGIC

**Definition**: Season spans May 1 to October 28 (growing season)

```
season_start = May 1 (month=5, day=1)
season_end = October 28 (month=10, day=28)
season_year = harvest_year
season_label = f"{season_year}-{season_year+1}"
```

**Data Collection for Each Season**:
1. Gather all YieldResult entries within [season_start, season_end]
2. Gather all FarmerYieldReport entries within same date range
3. Gather all NDVISnapshot entries within same date range
4. Fetch HistoricalYieldAverage for that year and crop_type

**Aggregation**:
```
predicted_yield_avg = mean(yield_results.yield_estimate)
actual_yield_avg = mean(farmer_reports.actual_yield)
avg_ndvi = mean(ndvi_snapshots.ndvi_stats.avg)
```

**Constraints**:
- Both predicted and actual yields must exist to include season
- NDVI optional (None if missing)
- Historical average optional (None if missing)

---

## NDVI-YIELD CORRELATION

**Formula**: Pearson correlation coefficient

```
r = cov(NDVI, yield) / (σ_NDVI * σ_yield)

where:
  cov = Σ((NDVI_i - mean_NDVI) * (yield_i - mean_yield)) / n
  σ_NDVI = sqrt(Σ(NDVI_i - mean_NDVI)² / n)
  σ_yield = sqrt(Σ(yield_i - mean_yield)² / n)
```

**Pairing Logic**:
- For each yield value, find closest NDVI observation within `days_lag` window
- Match on date proximity (forward search)
- Stop at first match within lag window

**Lag Window**: Default 30 days (configurable 1-180 days)

**Correlation Interpretation**:
- `r > 0.7`: Strong positive
- `0.4 < r ≤ 0.7`: Moderate positive
- `0.1 < r ≤ 0.4`: Weak positive
- `-0.1 ≤ r ≤ 0.1`: No correlation
- `-0.4 ≤ r < -0.1`: Weak negative
- `-0.7 ≤ r < -0.4`: Moderate negative
- `r < -0.7`: Strong negative

**Example**:
- NDVI values: [0.45, 0.55, 0.65, 0.72]
- Yield values: [4200, 4300, 4400, 4500]
- Correlation: ~0.998 (strong positive)
- Interpretation: "Strong positive"

**Constraints**:
- Minimum 2 paired observations
- Returns 0 if σ_NDVI or σ_yield = 0
- Returns None if < 2 pairs

---

## OVERALL ACCURACY METRICS

**Calculation Steps**:
1. Fetch all FarmerYieldReport records with linked YieldResult
2. For each pair: `deviation_i = |((predicted_i - actual_i) / actual_i) × 100|`
3. Calculate MAPE from all deviations
4. Calculate mean absolute deviation: `mean(deviations)`
5. Assign rating based on MAPE

**Output**:
```json
{
  "sample_count": int,
  "mape": float,
  "mean_absolute_deviation": float,
  "accuracy_rating": string,
  "min_deviation": float,
  "max_deviation": float
}
```

**Constraints**:
- Requires at least 1 paired sample
- Returns "Insufficient data" if no paired predictions
- MAPE and deviations are always absolute values

---

## VALIDATION DASHBOARD SUMMARY

**Summary Statistics**:
```
avg_deviation_percent = mean(deviation_percent for all seasons)
trends_correct_percent = (count where trend_correct=true / total_seasons) × 100
total_seasons_analyzed = count(seasons with data)
prediction_samples = sum(predictions_count across all seasons)
```

**Aggregation**:
- Deviation: Average across all analyzed seasons
- Trend accuracy: Percentage of seasons where trend matched
- Seasons: Only includes seasons with both predicted and actual yields
- Samples: Total count of yield predictions made

---

## DEVELOPMENT RULES (UNFROZEN)

✅ **ALL CHANGES ALLOWED**:
- Modify formula definitions
- Change rating thresholds
- Adjust lag window defaults
- Update accuracy interpretation text
- Change statistical methods
- Modify season date ranges
- Add new formulas
- Remove/replace existing formulas

⚠️ **BEST PRACTICES**:
- Document formula changes with examples
- Test with existing data
- Consider impact on historical comparisons
- Version changes appropriately

---

## EXAMPLES & TEST CASES

### Example 1: Single Season Comparison
```
Season: 2025-2026
Predictions: [4200, 4300, 4350] → avg 4283.33
Actuals: [4180, 4250, 4400] → avg 4276.67
Deviation: ((4283.33 - 4276.67) / 4276.67) × 100 = 0.15%
Trend: UP → UP ✓
Rating: Excellent (0.15% < 10%)
```

### Example 2: Multi-Year Accuracy
```
Year 1 Pairs: [(4350, 4320), (4450, 4480), (4500, 4520)]
Year 2 Pairs: [(4200, 4180), (4300, 4250), (4350, 4400)]
Deviations: [0.70, 0.67, 0.44, 0.47, 2.00, 1.14]
MAPE: 0.90%
Mean Deviation: ±0.90%
Rating: Excellent (±10%)
```

### Example 3: Trend Analysis
```
Year 1: 4350 → 4500 (UP) vs 4320 → 4520 (UP) ✓
Year 2: 4200 → 4350 (UP) vs 4180 → 4400 (UP) ✓
Trends Correct: 100%
```

---

## MIGRATION HISTORY

- **v1.0.0** (2026-01-30): Initial formula set with deviation, MAPE, trend, and correlation calculations
