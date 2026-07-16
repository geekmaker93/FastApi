import logging
import os
from pathlib import Path

import ee
import google.auth
from google.oauth2 import service_account

from app.core.config import GEE_PROJECT_ID


logger = logging.getLogger("crop_backend.earth_engine")
PROJECT_ROOT = Path(__file__).resolve().parent
_DEFAULT_CREDENTIAL_FILES = (
    PROJECT_ROOT / "serviceAccountKey.json",
    PROJECT_ROOT / "google-service-account.json",
    PROJECT_ROOT / "firebase-service-account.json",
)

_EE_INITIALIZED = False
_EE_INIT_ERROR = None


def _resolve_credentials_file():
    configured_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if candidate.is_file():
            return candidate

    for candidate in _DEFAULT_CREDENTIAL_FILES:
        if candidate.is_file():
            return candidate

    return None


def _build_init_attempts(scopes):
    configured_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    credentials_file = _resolve_credentials_file()

    if configured_path and credentials_file is not None:
        return [(
            "service_account_file",
            lambda: service_account.Credentials.from_service_account_file(
                str(credentials_file),
                scopes=scopes,
            ),
        )]

    attempts = [(
        "application_default_credentials",
        lambda: google.auth.default(scopes=scopes)[0],
    )]

    if credentials_file is not None:
        attempts.append((
            "service_account_file",
            lambda: service_account.Credentials.from_service_account_file(
                str(credentials_file),
                scopes=scopes,
            ),
        ))

    return attempts


def _initialize_earth_engine() -> bool:
    global _EE_INITIALIZED
    global _EE_INIT_ERROR

    if _EE_INITIALIZED:
        return True

    project_id = (GEE_PROJECT_ID or "").strip()
    if not project_id:
        _EE_INIT_ERROR = "GEE_PROJECT_ID is not configured"
        return False

    scopes = [
        "https://www.googleapis.com/auth/earthengine",
        "https://www.googleapis.com/auth/cloud-platform",
    ]

    last_error = None
    for source_name, credentials_factory in _build_init_attempts(scopes):
        try:
            credentials = credentials_factory()
            if hasattr(credentials, "with_quota_project"):
                credentials = credentials.with_quota_project(project_id)
            ee.Initialize(credentials=credentials, project=project_id)
            try:
                ee.data.setCloudApiUserProject(project_id)
            except Exception:
                pass
            _EE_INITIALIZED = True
            _EE_INIT_ERROR = None
            logger.info("Earth Engine initialized for NDVI history using %s", source_name)
            return True
        except Exception as exc:
            last_error = exc
            logger.warning("Earth Engine initialization attempt failed in ndvi_history using %s: %s", source_name, exc)

    _EE_INIT_ERROR = str(last_error) if last_error else "Unknown initialization error"
    logger.error("Earth Engine initialization warning: %s", _EE_INIT_ERROR)
    return False

def get_historical_ndvi(lat, lon, start_year=2020, end_year=2024):
    if not _initialize_earth_engine():
        raise RuntimeError(f"Earth Engine not initialized: {_EE_INIT_ERROR}")

    point = ee.Geometry.Point(lon, lat)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterBounds(point)
        .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi"))
    )

    stats = collection.reduce(
        ee.Reducer.min()
        .combine(ee.Reducer.max(), "", True)
        .combine(ee.Reducer.mean(), "", True)
    )

    values = stats.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=point,
        scale=10
    )

    return {
        "min": values.get("ndvi_min").getInfo(),
        "max": values.get("ndvi_max").getInfo(),
        "mean": values.get("ndvi_mean").getInfo()
    }

def normalize_ndvi(current_ndvi, hist_min, hist_max):
    if hist_max == hist_min:
        return 0.5
    return round(
        (current_ndvi - hist_min) / (hist_max - hist_min),
        2
    )