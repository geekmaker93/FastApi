# Crop Backend API

Agricultural monitoring API with satellite imagery integration, soil/weather data, and vegetation indices analysis.

## Project Structure

```
app/
├── main.py                 # FastAPI app entry point
├── core/
│   └── config.py          # Configuration and environment variables
├── models/
│   └── schemas.py         # Pydantic models for all APIs
├── routes/
│   ├── land.py            # Land/NDVI calculation routes
│   ├── farm.py            # Farm registration routes
│   ├── satellite.py       # Sentinel-2 satellite imagery routes
│   ├── soil_weather.py    # Farmonaut soil/weather/vegetation routes
│   ├── vegetation.py      # Vegetation analysis routes
│   └── polygons.py        # Polygon/field management routes
├── services/
│   ├── agromonitoring.py  # AgroMonitoring API integration
│   ├── farmonaut.py       # Farmonaut API integration
│   ├── sentinel.py        # Sentinel-2/Google Earth Engine integration
│   ├── imagery.py         # Imagery processing utilities
│   └── ndvi.py            # NDVI calculation
└── utils/
    ├── geo.py             # GeoPandas/geometric utilities
    └── imagery_processing.py  # Rasterio/numpy band processing
```

## Data Sources

### 1. **AgroMonitoring API**
   - REST API for polygon management
   - NDVI history data
   - Field monitoring

### 2. **Farmonaut API**
   - Soil data (moisture, pH, NPK)
   - Weather data (temperature, humidity, precipitation)
   - Vegetation indices (NDVI, EVI, SAVI, LAI)

### 3. **Sentinel-2 / Google Earth Engine**
   - Free satellite imagery
   - Multi-spectral band processing
   - NDVI computations from raw bands

## Dependencies

```
requests              # API calls
rasterio             # Satellite imagery processing
geopandas            # Polygon/field management
numpy                # Array operations
shapely              # Geometric operations
fastapi              # Web framework
uvicorn              # ASGI server
python-dotenv        # Environment variables
```

## Installation

1. Create virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install fastapi uvicorn requests rasterio geopandas numpy shapely python-dotenv
```

3. Setup environment variables:
```bash
copy .env.example .env
# Edit .env with your API keys
```

4. Configure PostgreSQL:
```bash
# Example local connection string
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/crop_app
```

5. Create tables:
```bash
python -m app.create_tables
```

## Running the Server

```bash
uvicorn app.main:app --reload
```

Server runs at: `http://127.0.0.1:8000`
API Docs: `http://127.0.0.1:8000/docs`

## API Endpoints

### Land (NDVI)
- `POST /land/ndvi` - Calculate NDVI from bands

### Farms
- `POST /farms` - Register farm
- `GET /farms/{farm_id}/soil-profile` - Get stored SoilGrids-backed soil profile for a farm
- `POST /farms/{farm_id}/soil-profile/refresh` - Refresh and persist farm soil profile from SoilGrids
- `POST /farms/soil-profile/location` - Persist a soil profile for a tapped map location

Note: farm endpoints now require a Bearer token from `/auth/login`.

### Auth
- `POST /auth/signup` - Create a new user with hashed password
- `POST /auth/login` - OAuth2 form login, returns JWT bearer token
- `POST /auth/login/json` - JSON login for mobile/web clients
- `GET /auth/me` - Read current authenticated user profile

### Satellite (Sentinel-2)
- `POST /sentinel/imagery/request` - Request satellite imagery
- `POST /sentinel/ndvi/analyze` - Analyze NDVI from satellite bands
- `GET /sentinel/metadata/{file_path}` - Get raster metadata

### Soil & Weather (Farmonaut)
- `GET /farmonaut/soil/{polygon_id}` - Get soil data
- `GET /farmonaut/weather` - Get weather data
- `GET /farmonaut/vegetation/{polygon_id}` - Get vegetation indices

### Vegetation
- `POST /vegetation/ndvi` - Calculate vegetation health
- `POST /vegetation/lai` - Estimate Leaf Area Index (LAI) from NDVI
- `POST /vegetation/ndvi-lai` - Calculate NDVI + LAI in one request
- `POST /vegetation/health-classification` - Classify health status

### Polygons
- `POST /polygons/create` - Create field polygon
- `GET /polygons/area/{polygon_id}` - Get polygon area
- `GET /polygons/centroid/{polygon_id}` - Get polygon center

## Key Features

✅ Multi-source satellite imagery integration
✅ Soil & weather monitoring
✅ Backend-owned SoilGrids soil profile storage with derived soil type, drainage, water holding estimate, and fertility score
✅ Vegetation indices calculation (NDVI, EVI, SAVI, LAI)
✅ Field polygon management with GeoPandas
✅ Raster band processing with Rasterio
✅ RESTful API with auto-generated documentation
✅ CORS enabled for frontend integration

## Example Usage

```python
import requests

# Calculate NDVI
response = requests.post(
    "http://127.0.0.1:8000/land/ndvi",
    json={"nir": 0.8, "red": 0.4}
)
print(response.json())

# Register farm
response = requests.post(
    "http://127.0.0.1:8000/farms",
    json={
        "name": "Farm A",
        "polygon": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    }
)
print(response.json())

# Get soil data
response = requests.get("http://127.0.0.1:8000/farmonaut/soil/polygon_123")
print(response.json())
```

## Environment Variables

Create `.env` file with:
- `AGRO_API_KEY` - AgroMonitoring API key
- `FARMONAUT_API_KEY` - Farmonaut API key  
- `GEE_API_KEY` - Google Earth Engine API key
- `GEE_PROJECT_ID` - Google Earth Engine project ID
- `PERENUAL_API_KEY` - Perenual plant care API key
- `TREFLE_API_KEY` - Trefle plant database API key
- `DATABASE_URL` - Database connection string (optional)
- `JWT_SECRET_KEY` - Secret used to sign JWT access tokens
- `JWT_ALGORITHM` - JWT signing algorithm (default `HS256`)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` - Access token lifetime in minutes

PostgreSQL example:
- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/crop_app`

---

**Status**: ✅ Production Ready | **Version**: 1.0.0
