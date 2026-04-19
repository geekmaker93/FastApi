from pydantic import BaseModel
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

# Farm Models
class FarmCreate(BaseModel):
    name: str
    polygon: List[Tuple[float, float]]

class FarmResponse(BaseModel):
    id: str
    name: str
    polygon_id: str
    created_at: datetime

# NDVI Models
class NDVIRequest(BaseModel):
    nir: float
    red: float

class NDVIResponse(BaseModel):
    ndvi: float
    health_status: str

class NDWIRequest(BaseModel):
    green: float
    nir: float

class NDWIResponse(BaseModel):
    ndwi: float
    water_status: str

class LAIRequest(BaseModel):
    ndvi: float

class LAIResponse(BaseModel):
    ndvi: float
    lai: float
    health_status: str


class NDVILAIResponse(BaseModel):
    ndvi: float
    lai: float
    ndvi_health_status: str
    lai_health_status: str

# Satellite Imagery Models
class SatelliteImageryRequest(BaseModel):
    polygon_id: str
    start_date: str
    end_date: str
    source: str = "sentinel2"  # sentinel2, landsat, gee

class SatelliteImageryResponse(BaseModel):
    id: str
    provider: str
    status: str
    metadata: Dict[str, Any]
    created_at: datetime

# Sentinel-2 Models
class Sentinel2Request(BaseModel):
    latitude: float
    longitude: float
    start_date: str
    end_date: str

class NDVIAnalysis(BaseModel):
    min: float
    max: float
    mean: float
    std: float
    median: float

class VegetationMap(BaseModel):
    classification: Dict[float, str]
    statistics: NDVIAnalysis

# Farmonaut Models
class SoilDataResponse(BaseModel):
    polygon_id: str
    moisture: float
    ph: float
    nitrogen: float
    phosphorus: float
    potassium: float
    temperature: float

class WeatherDataResponse(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    humidity: float
    precipitation: float
    wind_speed: float
    timestamp: datetime

class VegetationIndices(BaseModel):
    polygon_id: str
    ndvi: float
    evi: float
    savi: float
    lai: float
    timestamp: datetime


class SoilProfileLocationRequest(BaseModel):
    latitude: float
    longitude: float
    label: Optional[str] = None