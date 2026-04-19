"""
Test script: Seed database with comparison data and test all validation endpoints
Demonstrates NDVI vs Yield comparison across multiple seasons with accuracy metrics
"""

import requests
from datetime import date, timedelta
import json

API_BASE = "http://127.0.0.1:8000"
FARM_ID = 1

def test_comparison_workflow():
    """Complete workflow demonstrating comparison functionality"""
    
    print("=" * 80)
    print("NDVI vs YIELD COMPARISON WORKFLOW")
    print("=" * 80)
    
    # 1. Add farmer-reported yields for Season 2024
    print("\n[1] Adding farmer-reported yields for 2024 season...")
    
    farmer_reports_2024 = [
        {
            "farm_id": FARM_ID,
            "date": "2024-09-15",
            "actual_yield": 4500.0,
            "notes": "Good harvest, above expectations"
        },
        {
            "farm_id": FARM_ID,
            "date": "2024-10-20",
            "actual_yield": 4650.0,
            "notes": "Final harvest assessment"
        }
    ]
    
    for report in farmer_reports_2024:
        resp = requests.post(f"{API_BASE}/yields/reports/", json=report)
        print(f"  ✓ Report created: {report['date']} - {report['actual_yield']} kg/ha")
    
    # 2. Add farmer-reported yields for Season 2025
    print("\n[2] Adding farmer-reported yields for 2025 season...")
    
    farmer_reports_2025 = [
        {
            "farm_id": FARM_ID,
            "date": "2025-09-10",
            "actual_yield": 4200.0,
            "notes": "Moderate harvest, conditions were challenging"
        },
        {
            "farm_id": FARM_ID,
            "date": "2025-10-15",
            "actual_yield": 4350.0,
            "notes": "Recovery evident in second harvest"
        }
    ]
    
    for report in farmer_reports_2025:
        resp = requests.post(f"{API_BASE}/yields/reports/", json=report)
        print(f"  ✓ Report created: {report['date']} - {report['actual_yield']} kg/ha")
    
    # 3. Add historical yield baselines
    print("\n[3] Adding historical yield baselines...")
    
    historical = [
        {
            "farm_id": FARM_ID,
            "crop_type": "maize",
            "year": 2024,
            "avg_yield": 4400.0,
            "min_yield": 4000.0,
            "max_yield": 4800.0,
            "sample_count": 5
        },
        {
            "farm_id": FARM_ID,
            "crop_type": "maize",
            "year": 2025,
            "avg_yield": 4300.0,
            "min_yield": 3900.0,
            "max_yield": 4700.0,
            "sample_count": 5
        }
    ]
    
    for hist in historical:
        resp = requests.post(f"{API_BASE}/yields/historical/", json=hist)
        print(f"  ✓ Baseline created: {hist['year']} - {hist['avg_yield']} kg/ha (historical avg)")
    
    # 4. Get seasonal comparison
    print("\n[4] Fetching seasonal comparison (NDVI vs Yield)...")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/comparison?num_seasons=2")
    data = resp.json()
    
    if data.get('seasonal_metrics'):
        for season in data['seasonal_metrics']:
            print(f"\n  Season: {season['season']}")
            print(f"    Predicted Yield:  {season['predicted_yield_avg']:.0f} kg/ha")
            print(f"    Actual Yield:     {season['actual_yield_avg']:.0f} kg/ha")
            print(f"    Deviation:        {season['deviation_percent']:+.1f}%")
            print(f"    Trend:            {season['trend_description']}")
            if season['historical_avg']:
                print(f"    Historical Avg:   {season['historical_avg']:.0f} kg/ha")
    else:
        print("  (No seasonal data yet - need more historical yield reports)")
    
    # 5. Get overall accuracy metrics
    print("\n[5] Fetching overall accuracy metrics...")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/accuracy")
    accuracy = resp.json().get('accuracy_metrics', {})
    
    print(f"  Sample Count:         {accuracy.get('sample_count', 0)}")
    print(f"  MAPE (Mean Abs % Error): {accuracy.get('mape', 'N/A')}%")
    print(f"  Mean Deviation:       ±{accuracy.get('mean_absolute_deviation', 'N/A')}%")
    print(f"  Accuracy Rating:      {accuracy.get('accuracy_rating', 'N/A')}")
    
    # 6. Get NDVI-Yield correlation
    print("\n[6] Analyzing NDVI-Yield correlation...")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/ndvi-correlation?days_lag=30")
    correlation = resp.json().get('correlation_analysis', {})
    
    print(f"  Correlation Coefficient: {correlation.get('correlation_coefficient', 'N/A')}")
    print(f"  Interpretation:          {correlation.get('interpretation', 'Insufficient data')}")
    print(f"  Paired Observations:     {correlation.get('paired_count', 0)}")
    
    # 7. Get complete validation dashboard
    print("\n[7] Loading complete validation dashboard...")
    resp = requests.get(f"{API_BASE}/yields/farm/{FARM_ID}/validation-dashboard?num_seasons=2")
    dashboard = resp.json()
    
    print(f"\n  Farm: {dashboard.get('farm_name', 'Unknown')}")
    print(f"  Crop Type: {dashboard.get('crop_type', 'Unknown')}")
    
    summary = dashboard.get('summary', {})
    print(f"\n  SUMMARY METRICS:")
    print(f"    Average Deviation:    {summary.get('avg_deviation_percent', 'N/A')}%")
    print(f"    Trends Correct:       {summary.get('trends_correct_percent', 'N/A')}%")
    print(f"    Total Seasons:        {summary.get('total_seasons_analyzed', 0)}")
    print(f"    Prediction Samples:   {summary.get('prediction_samples', 0)}")
    
    print("\n" + "=" * 80)
    print("Comparison workflow complete! Open http://localhost:8080 and click")
    print("'📊 Compare NDVI vs Yield' to view the interactive dashboard.")
    print("=" * 80)

if __name__ == "__main__":
    test_comparison_workflow()
