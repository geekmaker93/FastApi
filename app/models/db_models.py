from datetime import UTC, datetime

from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, Boolean, DateTime, Text, UniqueConstraint, inspect, text
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship
from app.database import Base

USER_ID_FK = "users.id"
FARM_ID_FK = "farms.id"


def _utc_now() -> datetime:
    return datetime.now(UTC)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    last_seen = Column(DateTime, nullable=True)
    verification_code = Column(String, nullable=True)
    code_expires_at = Column(DateTime, nullable=True)
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    farms = relationship("Farm", back_populates="owner")
    preferences = relationship("UserPreferences", back_populates="user", uselist=False)
    device_tokens = relationship("UserDeviceToken", back_populates="user", cascade="all, delete-orphan")


class UserDeviceToken(Base):
    __tablename__ = "user_device_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(USER_ID_FK, ondelete="CASCADE"), nullable=False, index=True)
    token = Column(Text, nullable=False, unique=True)
    platform = Column(String, nullable=False, default="android")
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    updated_at = Column(DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (UniqueConstraint("token", name="uq_user_device_token"),)

    user = relationship("User", back_populates="device_tokens")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(USER_ID_FK), unique=True, nullable=False)
    wants_updates = Column(Boolean, default=True)
    user = relationship("User", back_populates="preferences")

class Farm(Base):
    __tablename__ = "farms"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(USER_ID_FK))
    name = Column(String)
    crop_type = Column(String)
    polygon = Column(JSON)  # store farm boundaries as GeoJSON
    owner = relationship("User", back_populates="farms")
    ndvi_snapshots = relationship("NDVISnapshot", back_populates="farm")
    yields = relationship("YieldResult", back_populates="farm")
    soil_profile = relationship("SoilProfile", back_populates="farm", uselist=False)
    live_state = relationship("FarmLiveState", back_populates="farm", uselist=False)


class FarmLiveState(Base):
    __tablename__ = "farm_live_states"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK), unique=True, nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="pending")
    weather_data = Column(JSON, nullable=True)
    vegetation_data = Column(JSON, nullable=True)
    yield_data = Column(JSON, nullable=True)
    soil_data = Column(JSON, nullable=True)
    source_data = Column(JSON, nullable=True)
    data_hash = Column(String, nullable=True)
    refreshed_at = Column(DateTime, nullable=True)
    changed_at = Column(DateTime, nullable=True)
    farm = relationship("Farm", back_populates="live_state")


class SoilProfile(Base):
    __tablename__ = "soil_profiles"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK), unique=True, nullable=True)
    latitude = Column(Float)
    longitude = Column(Float)
    source = Column(String)
    source_ref = Column(String, index=True)
    fetched_at = Column(String)
    raw_payload = Column(JSON)
    topsoil_metrics = Column(JSON)
    derived_properties = Column(JSON)
    farm = relationship("Farm", back_populates="soil_profile")

class NDVISnapshot(Base):
    __tablename__ = "ndvi_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK))
    # Legacy columns (kept for backward compat with existing code)
    date = Column(Date, nullable=True)
    ndvi_image_path = Column(String, nullable=True)
    ndvi_stats = Column(JSON, nullable=True)           # {min, max, avg/mean}
    # New spec columns
    image_path = Column(String, nullable=True)         # local device path
    image_url = Column(String, nullable=True)          # future cloud URL
    ndvi_avg = Column(Float, nullable=True)
    ndvi_min = Column(Float, nullable=True)
    ndvi_max = Column(Float, nullable=True)
    captured_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    farm = relationship("Farm", back_populates="ndvi_snapshots")
    analysis = relationship("SnapshotAnalysis", back_populates="snapshot", uselist=False)


class SnapshotAnalysis(Base):
    __tablename__ = "snapshot_analysis"
    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("ndvi_snapshots.id", ondelete="CASCADE"))
    green_percent = Column(Float, nullable=True)
    yellow_percent = Column(Float, nullable=True)
    red_percent = Column(Float, nullable=True)
    stress_level = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    snapshot = relationship("NDVISnapshot", back_populates="analysis")

class YieldResult(Base):
    __tablename__ = "yield_results"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK))
    date = Column(Date)
    yield_estimate = Column(Float)
    notes = Column(String)
    farm = relationship("Farm", back_populates="yields")
    farmer_report = relationship("FarmerYieldReport", back_populates="yield_estimate_record", uselist=False)

class FarmerYieldReport(Base):
    """Actual harvested yield reported by farmer for validation"""
    __tablename__ = "farmer_yield_reports"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK))
    yield_result_id = Column(Integer, ForeignKey("yield_results.id"))  # Links to predicted yield
    date = Column(Date)  # Harvest date
    actual_yield = Column(Float)  # kg/ha or tons/acre - actual measured yield
    reported_date = Column(Date)  # When farmer reported this
    notes = Column(String)
    farm = relationship("Farm")
    yield_estimate_record = relationship("YieldResult", back_populates="farmer_report")

class HistoricalYieldAverage(Base):
    """Baseline yield averages by crop type and farm for comparison"""
    __tablename__ = "historical_yield_averages"
    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey(FARM_ID_FK))
    crop_type = Column(String)  # e.g., "maize", "wheat"
    year = Column(Integer)  # Year of average
    avg_yield = Column(Float)  # Historical average in kg/ha
    min_yield = Column(Float)  # Historical minimum
    max_yield = Column(Float)  # Historical maximum
    sample_count = Column(Integer)  # Number of observations
    farm = relationship("Farm")


def ensure_user_schema(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    existing_users = {column["name"] for column in inspector.get_columns("users")}
    statements = []
    if "is_online" not in existing_users:
        statements.append("ALTER TABLE users ADD COLUMN is_online BOOLEAN DEFAULT FALSE")
    if "last_seen" not in existing_users:
        statements.append("ALTER TABLE users ADD COLUMN last_seen TIMESTAMP")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


