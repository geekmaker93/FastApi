import os
from dotenv import load_dotenv

load_dotenv()

# AgroMonitoring API
AGRO_API_KEY = os.getenv("AGRO_API_KEY")
AGRO_BASE_URL = "http://api.agromonitoring.com/agro/1.0"

# Farmonaut API
FARMONAUT_API_KEY = os.getenv("FARMONAUT_API_KEY")
FARMONAUT_BASE_URL = "https://api.farmonaut.com/api/v1"

# Google Earth Engine
GEE_API_KEY = os.getenv("GEE_API_KEY")
GEE_PROJECT_ID = os.getenv("GEE_PROJECT_ID")

# Firebase
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# Database
DATABASE_URL = os.getenv(
	"DATABASE_URL",
	"postgresql+psycopg://postgres:postgres@localhost:5432/crop_app",
)
