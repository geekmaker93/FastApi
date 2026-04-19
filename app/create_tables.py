from app.database import Base, engine
from app.models.db_models import User, Farm, NDVISnapshot, SnapshotAnalysis, YieldResult, SoilProfile
from app.models import social_models

# Create all tables
Base.metadata.create_all(bind=engine)
social_models.ensure_social_schema(engine)

print("Tables created successfully!")
