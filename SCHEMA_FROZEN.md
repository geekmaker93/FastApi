# DATABASE SCHEMA - UNFROZEN
**Status**: ✅ EDITABLE - All changes allowed  
**Date**: January 30, 2026  
**Unfrozen**: January 30, 2026 @ 14:30 UTC  
**Version**: 1.0.0 (development mode)  
**Database**: SQLite with WAL mode

---

## TABLE: users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name VARCHAR,
    email VARCHAR UNIQUE NOT NULL,
    password VARCHAR,
    INDEX ix_users_email (email)
);
```

**Columns**:
- `id` (Integer): Primary key
- `name` (String): User's name
- `email` (String): Unique email address
- `password` (String): Hashed password
- `farms` (Relationship): One-to-many relationship with Farm

---

## TABLE: farms

```sql
CREATE TABLE farms (
    id INTEGER PRIMARY KEY,
    user_id INTEGER FOREIGN KEY REFERENCES users.id,
    name VARCHAR,
    crop_type VARCHAR,
    polygon JSON,
    INDEX ix_farms_user_id (user_id)
);
```

**Columns**:
- `id` (Integer): Primary key
- `user_id` (Integer): Foreign key to users table
- `name` (String): Farm name
- `crop_type` (String): Crop type (e.g., "Corn", "Maize", "Wheat")
- `polygon` (JSON): GeoJSON polygon coordinates for farm boundaries
- `ndvi_snapshots` (Relationship): One-to-many with NDVISnapshot
- `yields` (Relationship): One-to-many with YieldResult

---

## TABLE: ndvi_snapshots

```sql
CREATE TABLE ndvi_snapshots (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER FOREIGN KEY REFERENCES farms.id,
    date DATE,
    ndvi_image_path VARCHAR,
    ndvi_stats JSON,
    INDEX ix_ndvi_snapshots_farm_id (farm_id)
);
```

**Columns**:
- `id` (Integer): Primary key
- `farm_id` (Integer): Foreign key to farms table
- `date` (Date): Date of NDVI snapshot
- `ndvi_image_path` (String): Path to NDVI GeoTIFF file
- `ndvi_stats` (JSON): Statistics object with structure:
  ```json
  {
    "min": float,
    "max": float,
    "mean": float,
    "std": float
  }
  ```
- `farm` (Relationship): Many-to-one with Farm

---

## TABLE: yield_results

```sql
CREATE TABLE yield_results (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER FOREIGN KEY REFERENCES farms.id,
    date DATE,
    yield_estimate FLOAT,
    notes VARCHAR,
    INDEX ix_yield_results_farm_id (farm_id)
);
```

**Columns**:
- `id` (Integer): Primary key
- `farm_id` (Integer): Foreign key to farms table
- `date` (Date): Date of yield prediction
- `yield_estimate` (Float): Predicted yield in kg/ha
- `notes` (String): Optional notes
- `farm` (Relationship): Many-to-one with Farm
- `farmer_report` (Relationship): One-to-one with FarmerYieldReport

---

## TABLE: farmer_yield_reports

```sql
CREATE TABLE farmer_yield_reports (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER FOREIGN KEY REFERENCES farms.id,
    yield_result_id INTEGER FOREIGN KEY REFERENCES yield_results.id,
    date DATE,
    actual_yield FLOAT,
    reported_date DATE,
    notes VARCHAR,
    INDEX ix_farmer_yield_reports_farm_id (farm_id),
    INDEX ix_farmer_yield_reports_yield_result_id (yield_result_id)
);
```

**Columns**:
- `id` (Integer): Primary key
- `farm_id` (Integer): Foreign key to farms table
- `yield_result_id` (Integer): Foreign key to yield_results (optional, for linking to predictions)
- `date` (Date): Harvest/report date
- `actual_yield` (Float): Measured actual yield in kg/ha
- `reported_date` (Date): When farmer reported this value
- `notes` (String): Optional notes from farmer
- `farm` (Relationship): Many-to-one with Farm
- `yield_estimate_record` (Relationship): One-to-one with YieldResult

---

## TABLE: historical_yield_averages

```sql
CREATE TABLE historical_yield_averages (
    id INTEGER PRIMARY KEY,
    farm_id INTEGER FOREIGN KEY REFERENCES farms.id,
    crop_type VARCHAR,
    year INTEGER,
    avg_yield FLOAT,
    min_yield FLOAT,
    max_yield FLOAT,
    sample_count INTEGER,
    INDEX ix_historical_yield_averages_farm_id (farm_id)
);
```

**Columns**:
- `id` (Integer): Primary key
- `farm_id` (Integer): Foreign key to farms table
- `crop_type` (String): Crop type for the baseline
- `year` (Integer): Year of the historical average
- `avg_yield` (Float): Historical average yield in kg/ha
- `min_yield` (Float): Historical minimum yield
- `max_yield` (Float): Historical maximum yield
- `sample_count` (Integer): Number of observations in the average
- `farm` (Relationship): Many-to-one with Farm

---

## JSON FIELD FORMATS

### ndvi_stats (stored in ndvi_snapshots.ndvi_stats)
```json
{
  "min": 0.15,
  "max": 0.85,
  "mean": 0.65,
  "std": 0.12
}
```

### polygon (stored in farms.polygon)
```json
[
  [lat1, lon1],
  [lat2, lon2],
  [lat3, lon3],
  [lat4, lon4]
]
```

---

## DEVELOPMENT RULES (UNFROZEN)

✅ **ALL CHANGES ALLOWED**:
- Add/remove tables
- Add/remove columns
- Modify column types
- Change field names
- Modify relationships
- Alter JSON structure
- Add/modify indexes
- Change constraints
- All optimizations

⚠️ **MIGRATION REQUIRED**:
- Create migration scripts for schema changes
- Test with existing data
- Document breaking changes

---

## RELATIONSHIPS

```
users (1) ──→ (n) farms
           ├──→ (n) ndvi_snapshots
           └──→ (n) yield_results
                   └──→ (1) farmer_yield_reports

farms (1) ──→ (n) historical_yield_averages
```

---

## DATABASE PRAGMAS (SQLite Configuration)

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

**Purpose**: Enable concurrent reads while maintaining data integrity.

---

## MIGRATION HISTORY

- **v1.0.0** (2026-01-30): Initial schema with NDVI, yields, farmer reports, and historical baselines
