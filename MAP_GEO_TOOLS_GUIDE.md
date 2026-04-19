# Agricultural Monitoring Map & Geo Tools Implementation

## Overview

This document describes the implementation of four key Map & Geo Tool features for your crop backend project:

1. **NDVI Tiles** - GeoTIFF tile generation for efficient NDVI visualization
2. **Time-series Layer Toggle** - Interactive temporal comparison of vegetation indices
3. **Yield Layers** - Backend integration and frontend visualization of yield predictions
4. **WMS/Tile Server** - OGC-compliant tile server for multi-layer support

---

## 1. NDVI Tiles

### What It Does
Generates GeoTIFF tiles from NDVI satellite data for efficient map rendering and storage.

### Components

#### Backend Service: `app/services/tiles.py`
- **`NDVITileService`** class handles:
  - NDVI array to GeoTIFF conversion
  - Web tile generation (XYZ format for Leaflet)
  - NDVI colorization (red/yellow/green/dark-green based on values)
  - Tile metadata management

**Key Methods:**
- `ndvi_to_geotiff()` - Convert numpy array to georeferenced GeoTIFF
- `generate_tiles()` - Create web tiles from GeoTIFF
- `colorize_ndvi()` - Apply color mapping to NDVI values
- `create_tif_with_colormap()` - Create colorized GeoTIFF for map overlay

#### API Endpoint
```
POST /ndvi/{snapshot_id}/generate-tiles
```
Returns tile metadata with access URL.

### Usage Example
```python
from app.services.tiles import NDVITileService
import numpy as np

service = NDVITileService()
ndvi_array = np.random.rand(512, 512)  # NDVI values
bounds = [-76.81, 18.01, -76.80, 18.02]  # [minx, miny, maxx, maxy]

# Generate GeoTIFF
tif_path = service.ndvi_to_geotiff(ndvi_array, bounds)

# Generate web tiles
tile_info = service.generate_tiles(tif_path)
```

---

## 2. Time-Series Layer Toggle

### What It Does
Allows frontend users to view NDVI data across multiple dates with interactive selection and statistics.

### Components

#### Backend Route: `app/routes/ndvi.py`
New endpoint for temporal data:
```
GET /ndvi/farm/{farm_id}/timeseries
  ?start_date=2024-01-01&end_date=2024-12-31
```

Returns array of NDVI snapshots with statistics for date range.

#### Frontend Features (`mobile_app/index.html`)

1. **Date Range Picker**
   - Select start and end dates
   - Load time series for comparison

2. **Layer Toggle Buttons**
   - NDVI, Yield, Soil Moisture, Weather
   - Active/inactive states

3. **Time Series Panel**
   - Lists all snapshots with NDVI statistics
   - Click to select and display on map
   - Shows health status (Poor/Fair/Moderate/Good)

4. **Statistics Panel**
   - Min/Max/Mean/Std Dev NDVI
   - Date of current snapshot

### Frontend JavaScript API
```javascript
// Load time series data
loadTimeSeries();

// Toggle layer visibility
toggleLayer('ndvi');

// Select specific snapshot
selectTimeSeriesSnapshot(snapshot, element);

// View statistics
updateStatsPanel(snapshot);
```

---

## 3. Yield Layers

### What It Does
Visualizes yield predictions on the map, correlating with vegetation and soil data.

### Components

#### Database Model: `app/models/db_models.py`
```python
class YieldResult(Base):
    __tablename__ = "yield_results"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id"))
    date = Column(Date)
    yield_estimate = Column(Float)
    notes = Column(String)
    farm = relationship("Farm", back_populates="yields")
```

#### Backend Routes: `app/routes/yields.py`
Available endpoints:
- `POST /yields/` - Create yield estimate
- `GET /yields/{yield_id}` - Get specific yield
- `GET /yields/farm/{farm_id}` - Get all farm yields (with date filtering)
- `GET /yields/farm/{farm_id}/geojson` - Get yields as GeoJSON for mapping

#### Frontend Visualization
- Yield predictions displayed as circular markers
- Marker size correlates with yield magnitude
- Color: Golden/orange (#f7b731)
- Interactive popups show:
  - Date of prediction
  - Estimated yield (units/ha)
  - Notes/comments

### API Usage
```bash
# Create yield estimate
curl -X POST http://localhost:8000/yields/ \
  -H "Content-Type: application/json" \
  -d '{
    "farm_id": 1,
    "date": "2024-06-15",
    "yield_estimate": 45.5,
    "notes": "Good growing conditions"
  }'

# Get yields with time range
curl http://localhost:8000/yields/farm/1?start_date=2024-01-01&end_date=2024-12-31
```

---

## 4. WMS/Tile Server

### What It Does
Provides an OGC Web Map Service (WMS) compatible endpoint for serving tiled data to any GIS-compatible client.

### Components

#### Backend Service: `app/services/wms_server.py`
**`WMSTileServer`** class implements:
- Layer registration and management
- WMS GetMap requests
- WMS GetFeatureInfo queries
- XYZ tile generation
- Custom style application

**Key Methods:**
- `register_layer()` - Add new layer to server
- `get_capabilities()` - Return WMS capabilities document
- `get_map()` - Render map tile for bbox
- `get_feature_info()` - Query pixel values
- `list_layers()` - List all available layers

#### Backend Routes: `app/routes/tiles.py`
WMS standard endpoints:
```
GET /tiles/wms/capabilities           - WMS capabilities document
GET /tiles/wms/layers                 - List available layers
GET /tiles/wms/getmap                 - GetMap (WMS standard)
GET /tiles/wms/getfeatureinfo         - GetFeatureInfo (WMS standard)
GET /tiles/{z}/{x}/{y}                - XYZ tile endpoint (Leaflet)
POST /tiles/register                  - Register custom layer
GET /tiles/config                     - Get server configuration
```

#### Default Registered Layers
1. **NDVI** - Vegetation health
   - Color mapping: Red (poor) → Yellow (fair) → Green (good)
   - Values: -1.0 to 1.0
   
2. **Yield** - Crop yield predictions
   - Source: Yield database
   - Values: Units per hectare
   
3. **Soil Moisture** - Soil water content
   - Values: 0-100% saturation

### WMS Capabilities Example
```json
{
  "service": "WMS",
  "version": "1.3.0",
  "title": "Crop Monitoring WMS Server",
  "abstract": "WMS service for agricultural monitoring data",
  "layers": [
    {
      "name": "ndvi",
      "title": "NDVI - Normalized Difference Vegetation Index",
      "bounds": [-76.81, 18.01, -76.80, 18.02],
      "crs": "EPSG:4326"
    }
  ]
}
```

### Integration with Frontend
WMS layers can be added to Leaflet using standard plugins:
```javascript
// WMS GetMap request
L.tileLayer.wms("http://localhost:8000/tiles/wms/getmap", {
    layers: 'ndvi',
    transparent: true,
    format: 'image/png'
}).addTo(map);

// XYZ tiles (native Leaflet)
L.tileLayer("http://localhost:8000/tiles/{z}/{x}/{y}?layer=ndvi").addTo(map);
```

---

## File Structure Summary

### New Files Created
```
app/
├── services/
│   ├── tiles.py          (NDVI tile service)
│   └── wms_server.py     (WMS tile server)
└── routes/
    └── tiles.py          (Tile server endpoints)

mobile_app/
└── index.html            (Enhanced map UI)
```

### Modified Files
- `app/routes/ndvi.py` - Added time-series endpoints
- `app/routes/yields.py` - Complete rewrite with full CRUD
- `app/main.py` - Included tiles router
- `requirements.txt` - Added rasterio and Pillow dependencies

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────┐
│  Frontend (Leaflet Map)                          │
│  ├─ Layer Toggle (NDVI/Yield/Soil/Weather)     │
│  ├─ Date Range Picker                          │
│  ├─ Time Series Selector                       │
│  └─ Statistics Panel                           │
└──────────────────┬──────────────────────────────┘
                   │ HTTP/REST
                   ▼
┌─────────────────────────────────────────────────┐
│  Backend Routes                                  │
│  ├─ /ndvi/farm/{id}/timeseries                 │
│  ├─ /ndvi/{id}/generate-tiles                  │
│  ├─ /yields/farm/{id}                          │
│  └─ /tiles/wms/getmap                          │
└──────────────────┬──────────────────────────────┘
                   │
      ┌────────────┼────────────┐
      ▼            ▼            ▼
   ┌────────┐  ┌────────┐  ┌─────────┐
   │ NDVI   │  │ Yield  │  │ WMS     │
   │Service │  │Database│  │Server   │
   │(Tiles) │  │        │  │         │
   └────────┘  └────────┘  └─────────┘
```

---

## Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Backend Server
```bash
uvicorn app.main:app --reload
```

### 3. Access Frontend
Open `mobile_app/index.html` in your browser or serve it with a simple HTTP server:
```bash
python -m http.server 8080 --directory mobile_app
```

### 4. Try the Features

#### Load NDVI Time Series
```bash
curl http://localhost:8000/ndvi/farm/1/timeseries
```

#### Generate Tiles
```bash
curl -X POST http://localhost:8000/ndvi/1/generate-tiles
```

#### Get WMS Capabilities
```bash
curl http://localhost:8000/tiles/wms/capabilities
```

#### Fetch Yield Data
```bash
curl http://localhost:8000/yields/farm/1
```

---

## Advanced Usage

### Adding Custom Layers to WMS
```bash
curl -X POST http://localhost:8000/tiles/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=custom_layer&title=My Custom Layer&source=/path/to/file.tif&bounds=-76.81,18.01,-76.80,18.02"
```

### Querying Pixel Values
```bash
curl "http://localhost:8000/tiles/wms/getfeatureinfo?layers=ndvi&x=-76.8050&y=18.0150&info_format=application/json"
```

### XYZ Tile Access
```
http://localhost:8000/tiles/14/8192/6553?layer=ndvi
(Format: /tiles/{z}/{x}/{y}?layer={layer_name})
```

---

## Performance Considerations

1. **Tile Caching** - Implement caching for frequently requested tiles
2. **GeoTIFF Compression** - Use LZW compression for large files
3. **Vector Tiles** - Consider using MVT format for large datasets
4. **Database Indexing** - Index by farm_id and date for faster queries

---

## Future Enhancements

1. **Real-time Updates** - WebSocket support for live data
2. **More Indices** - Add EVI, SAVI, LAI calculations
3. **Prediction Models** - Integrate ML for yield forecasting
4. **Historical Analysis** - Multi-year comparison tools
5. **Mobile App** - React Native or Flutter implementation
6. **API Documentation** - Full OpenAPI/Swagger docs
7. **Authentication** - JWT token-based access control

---

## Troubleshooting

### "Layer not found" Error
- Check layer name in request
- Verify layer is registered: `GET /tiles/wms/layers`

### Tile Generation Fails
- Ensure NDVI array contains valid values (-1 to 1)
- Check bounds are in correct format (minx, miny, maxx, maxy)

### Frontend Not Updating
- Clear browser cache
- Check CORS settings (currently allow all origins)
- Verify API endpoint in frontend code

### WMS GetMap Returns Black Image
- Check source GeoTIFF exists
- Verify coordinate system matches request CRS
- Try with different zoom level

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ndvi/farm/{farm_id}/timeseries` | Time series data for farm |
| POST | `/ndvi/{snapshot_id}/generate-tiles` | Generate tiles from snapshot |
| GET | `/yields/farm/{farm_id}` | Get yield estimates |
| GET | `/tiles/wms/capabilities` | WMS capabilities |
| GET | `/tiles/{z}/{x}/{y}` | Get XYZ tile |
| GET | `/tiles/wms/getmap` | WMS GetMap |
| GET | `/tiles/wms/getfeatureinfo` | Query pixel values |

---

## License & Credits

Part of the Crop Backend Project - Agricultural Monitoring System
