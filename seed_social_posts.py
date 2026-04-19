from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.security import hash_password
from app.database import SessionLocal, Base, engine
from app.models import social_models
from app.models.db_models import User
from app.models.social_models import SocialPost, SocialProfile


DEFAULT_PASSWORD = "SeedPosts@2026"


@dataclass(frozen=True)
class SeedUser:
    handle: str
    email: str
    display_name: str
    bio: str
    location: str
    goals: str
    crops: str
    experience_level: str


@dataclass(frozen=True)
class SeedPost:
    user_handle: str
    content: str
    latitude: float
    longitude: float
    hours_ago: int
    is_global: bool = False
    image_url: Optional[str] = None
    media_type: Optional[str] = None


PHOTO_CORN_FIELD = "https://images.pexels.com/photos/33786745/pexels-photo-33786745.jpeg?cs=srgb&dl=pexels-sam-mccool-1923523643-33786745.jpg&fm=jpg"
PHOTO_TOMATO_PLANTS = "https://images.pexels.com/photos/5479033/pexels-photo-5479033.jpeg?cs=srgb&dl=pexels-yankrukov-5479033.jpg&fm=jpg"
PHOTO_RAIN_CROPS = "https://images.pexels.com/photos/17437555/pexels-photo-17437555.jpeg?cs=srgb&dl=pexels-peter-kovesi-421914941-17437555.jpg&fm=jpg"
PHOTO_SEEDLINGS = "https://images.pexels.com/photos/30839537/pexels-photo-30839537.jpeg?cs=srgb&dl=pexels-shootsaga-30839537.jpg&fm=jpg"
PHOTO_LIVESTOCK = "https://images.pexels.com/photos/11350565/pexels-photo-11350565.jpeg?cs=srgb&dl=pexels-feyzayildirimphoto-11350565.jpg&fm=jpg"
PHOTO_FARM_WORK = "https://images.pexels.com/photos/20878004/pexels-photo-20878004.jpeg?cs=srgb&dl=pexels-didpics-20878004.jpg&fm=jpg"
PHOTO_DRY_SOIL = "https://images.pexels.com/photos/15048526/pexels-photo-15048526.jpeg?cs=srgb&dl=pexels-andriy-nestruiev-288919368-15048526.jpg&fm=jpg"


SEED_USERS = [
    SeedUser(
        handle="AgriSense_AI",
        email="agrisense_ai@system.farmsense",
        display_name="AgriSense AI",
        bio="AI field monitor sharing weather-aware crop guidance and satellite-driven alerts.",
        location="Jamaica",
        goals="Keep farmers updated with timely climate and crop stress insights.",
        crops="tomatoes, peppers, mixed vegetables",
        experience_level="AI advisory system",
    ),
    SeedUser(
        handle="FarmWatch_JA",
        email="farmwatch_ja@system.farmsense",
        display_name="FarmWatch JA",
        bio="Local Jamaica field watch account tracking rainfall, vegetation shifts, and farmer observations.",
        location="Jamaica",
        goals="Highlight changing local field conditions before they become crop losses.",
        crops="corn, beans, peppers",
        experience_level="Regional monitor",
    ),
    SeedUser(
        handle="CropCare_Expert",
        email="cropcare_expert@system.farmsense",
        display_name="CropCare Expert",
        bio="Crop-health advisor focused on nutrient loss, disease pressure, and early treatment cues.",
        location="Jamaica",
        goals="Help growers respond quickly to crop stress and pest pressure.",
        crops="tomatoes, leafy vegetables, fruit crops",
        experience_level="Crop specialist",
    ),
    SeedUser(
        handle="GreenFields",
        email="greenfields@system.farmsense",
        display_name="GreenFields",
        bio="Field-level grower voice sharing practical crop observations and resilience tips.",
        location="Jamaica",
        goals="Keep the social feed active with practical on-farm updates.",
        crops="corn, beans, vegetables",
        experience_level="Experienced grower",
    ),
    SeedUser(
        handle="SoilSense",
        email="soilsense@system.farmsense",
        display_name="SoilSense",
        bio="Soil and moisture focused account tracking planting readiness and root-zone conditions.",
        location="Jamaica",
        goals="Surface soil-condition signals that affect planting and recovery.",
        crops="beans, peppers, mixed vegetables",
        experience_level="Soil analyst",
    ),
    SeedUser(
        handle="AgriGlobal",
        email="agriglobal@system.farmsense",
        display_name="AgriGlobal",
        bio="Global agriculture watcher sharing crop and climate insights from major production zones.",
        location="Global",
        goals="Surface international crop performance signals relevant to farmers everywhere.",
        crops="corn, wheat, soybeans",
        experience_level="Global monitor",
    ),
    SeedUser(
        handle="CropWatch_Global",
        email="cropwatch_global@system.farmsense",
        display_name="CropWatch Global",
        bio="Worldwide crop monitor focused on seasonal rainfall, rice systems, and production swings.",
        location="Global",
        goals="Track crop opportunities and stress signals across regions.",
        crops="rice, cereals, staple crops",
        experience_level="Global crop analyst",
    ),
    SeedUser(
        handle="FarmWatch_Africa",
        email="farmwatch_africa@system.farmsense",
        display_name="FarmWatch Africa",
        bio="Regional field network highlighting rainfall adaptation and smallholder resilience across Africa.",
        location="Africa",
        goals="Share practical weather and yield observations from African farming zones.",
        crops="cassava, maize, vegetables",
        experience_level="Regional monitor",
    ),
    SeedUser(
        handle="CropCare_Global",
        email="cropcare_global@system.farmsense",
        display_name="CropCare Global",
        bio="Crop systems advisor focused on irrigation control, protected agriculture, and crop stability worldwide.",
        location="Global",
        goals="Help growers learn from protected and precision agriculture systems.",
        crops="vegetables, greenhouse crops",
        experience_level="Global crop specialist",
    ),
]


SEED_POSTS = [
    SeedPost(
        user_handle="AgriSense_AI",
        content="High temperatures expected this week in Kingston. Farmers should increase irrigation for crops like tomatoes and peppers.",
        latitude=18.0179,
        longitude=-76.8099,
        hours_ago=6,
    ),
    SeedPost(
        user_handle="FarmWatch_JA",
        content="Low rainfall recorded in St. Elizabeth over the past 5 days. Soil moisture levels may drop significantly.",
        latitude=18.1096,
        longitude=-77.2975,
        hours_ago=21,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Moderate rainfall expected tomorrow. Good opportunity for planting short-cycle crops.",
        latitude=17.9712,
        longitude=-76.7936,
        hours_ago=33,
    ),
    SeedPost(
        user_handle="GreenFields",
        content="Corn crops looking healthy after a week of steady rainfall. Growth conditions are improving.",
        latitude=18.2000,
        longitude=-77.4667,
        hours_ago=45,
        image_url=PHOTO_CORN_FIELD,
        media_type="image",
    ),
    SeedPost(
        user_handle="CropCare_Expert",
        content="Tomato plants showing strong fruit development. Drip irrigation helping maintain soil moisture.",
        latitude=18.0123,
        longitude=-77.5034,
        hours_ago=59,
        image_url=PHOTO_TOMATO_PLANTS,
        media_type="image",
    ),
    SeedPost(
        user_handle="SoilSense",
        content="Soil moisture levels are stable in Clarendon. Good conditions for planting beans and peppers.",
        latitude=17.9557,
        longitude=-77.2405,
        hours_ago=71,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Recent rainfall is helping replenish soil moisture levels. Farmers should monitor for fungal risks.",
        latitude=18.1096,
        longitude=-77.2975,
        hours_ago=84,
        image_url=PHOTO_RAIN_CROPS,
        media_type="image",
    ),
    SeedPost(
        user_handle="CropCare_Expert",
        content="Reports of aphid activity increasing in some regions. Early treatment recommended.",
        latitude=18.0179,
        longitude=-76.8099,
        hours_ago=96,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Drip irrigation systems are helping farmers conserve water during dry periods.",
        latitude=18.0500,
        longitude=-77.3500,
        hours_ago=109,
    ),
    SeedPost(
        user_handle="SoilSense",
        content="Loamy soil conditions are ideal for most vegetable crops. Consider soil testing for better results.",
        latitude=18.0300,
        longitude=-77.1000,
        hours_ago=121,
    ),
    SeedPost(
        user_handle="GreenFields",
        content="New seedlings emerging after planting. Early growth stage looks healthy under current conditions.",
        latitude=18.1000,
        longitude=-77.2000,
        hours_ago=137,
        image_url=PHOTO_SEEDLINGS,
        media_type="image",
    ),
    SeedPost(
        user_handle="FarmWatch_JA",
        content="Livestock grazing conditions remain stable. Pasture quality improving after rainfall.",
        latitude=18.0413,
        longitude=-77.4989,
        hours_ago=18,
        image_url=PHOTO_LIVESTOCK,
        media_type="image",
    ),
    SeedPost(
        user_handle="SoilSense",
        content="Dry conditions are affecting root-zone moisture in exposed plots. Irrigation may be necessary to maintain crop health.",
        latitude=17.9924,
        longitude=-77.3018,
        hours_ago=31,
        image_url=PHOTO_DRY_SOIL,
        media_type="image",
    ),
    SeedPost(
        user_handle="GreenFields",
        content="Field preparation is underway for the next planting cycle. Soil conditions remain favorable after this week's weather.",
        latitude=18.0551,
        longitude=-77.3357,
        hours_ago=53,
        image_url=PHOTO_FARM_WORK,
        media_type="image",
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Satellite data shows reduced vegetation health in western regions this week. Monitor crop stress levels closely.",
        latitude=18.1500,
        longitude=-77.5000,
        hours_ago=149,
    ),
    SeedPost(
        user_handle="FarmWatch_JA",
        content="NDVI trends indicate improving crop health in central areas after recent rainfall.",
        latitude=17.9800,
        longitude=-77.3000,
        hours_ago=164,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Corn crops in the Midwest are showing strong growth this season due to consistent rainfall and moderate temperatures.",
        latitude=41.8780,
        longitude=-93.0977,
        hours_ago=11,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropWatch_Global",
        content="Rice farmers in northern regions are benefiting from steady monsoon rains. Water levels remain favorable for crop growth.",
        latitude=26.8467,
        longitude=80.9462,
        hours_ago=27,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Soybean production is increasing in central Brazil due to improved soil moisture and favorable weather patterns.",
        latitude=-15.7801,
        longitude=-47.9292,
        hours_ago=38,
        is_global=True,
    ),
    SeedPost(
        user_handle="FarmWatch_Africa",
        content="Cassava farmers are experiencing strong yields this season as rainfall patterns remain consistent across key regions.",
        latitude=9.0820,
        longitude=8.6753,
        hours_ago=52,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Wheat crops in southern Australia are under stress due to prolonged dry conditions and rising temperatures.",
        latitude=-34.9285,
        longitude=138.6007,
        hours_ago=64,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropCare_Global",
        content="Greenhouse vegetable production is increasing in eastern regions, supported by controlled irrigation systems.",
        latitude=31.2304,
        longitude=121.4737,
        hours_ago=77,
        is_global=True,
    ),
    SeedPost(
        user_handle="FarmWatch_Africa",
        content="Smallholder farmers are adopting drip irrigation to combat irregular rainfall patterns.",
        latitude=-1.2921,
        longitude=36.8219,
        hours_ago=91,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Cooler overnight temperatures across the Canadian Prairies are helping canola fields retain moisture after a dry start to the month.",
        latitude=51.0447,
        longitude=-114.0719,
        hours_ago=103,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropWatch_Global",
        content="Rice paddies in southern Vietnam are recovering well after recent rainfall, with stronger tiller development reported this week.",
        latitude=10.8231,
        longitude=106.6297,
        hours_ago=116,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Maize fields in Argentina are entering a favorable growth window as soil moisture reserves improve after scattered storms.",
        latitude=-31.4201,
        longitude=-64.1888,
        hours_ago=129,
        is_global=True,
    ),
    SeedPost(
        user_handle="FarmWatch_Africa",
        content="Bean growers in Rwanda are reporting improved emergence where early rainfall was followed by mild daytime temperatures.",
        latitude=-1.9441,
        longitude=30.0619,
        hours_ago=141,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropCare_Global",
        content="Vegetable farms in Spain are adjusting irrigation schedules as heat stress begins to rise in protected production zones.",
        latitude=37.3891,
        longitude=-5.9845,
        hours_ago=153,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Satellite imagery suggests patchy moisture stress in sunflower fields across eastern Europe. Uneven canopy density is becoming more visible.",
        latitude=44.4268,
        longitude=26.1025,
        hours_ago=165,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Wheat producers in western Europe are seeing steadier crop color after light rainfall reduced short-term drought pressure.",
        latitude=48.8566,
        longitude=2.3522,
        hours_ago=178,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropWatch_Global",
        content="Sugarcane fields in Thailand are benefiting from more consistent soil moisture, improving stand uniformity ahead of the next growth phase.",
        latitude=13.7563,
        longitude=100.5018,
        hours_ago=191,
        is_global=True,
    ),
    SeedPost(
        user_handle="FarmWatch_Africa",
        content="Groundnut farmers in Senegal are preparing for planting as early rainfall patterns become more reliable across central districts.",
        latitude=14.7167,
        longitude=-17.4677,
        hours_ago=204,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropCare_Global",
        content="High humidity in coastal Peru is increasing the risk of foliar disease in irrigated vegetable systems. Field scouting is advised.",
        latitude=-12.0464,
        longitude=-77.0428,
        hours_ago=218,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Barley crops in northern Germany are holding steady despite cooler daytime conditions, with grain fill prospects remaining favorable.",
        latitude=53.5511,
        longitude=9.9937,
        hours_ago=231,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropWatch_Global",
        content="Tea-growing regions in Sri Lanka are seeing healthier canopy recovery after recent showers eased moisture deficits.",
        latitude=6.9271,
        longitude=79.8612,
        hours_ago=245,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="NDVI signals are strengthening in parts of South Africa where recent rainfall improved pasture and maize conditions.",
        latitude=-26.2041,
        longitude=28.0473,
        hours_ago=258,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropCare_Global",
        content="Greenhouse tomato operations in the Netherlands are maintaining stable yields through tighter climate control and recycled irrigation water.",
        latitude=52.3676,
        longitude=4.9041,
        hours_ago=272,
        is_global=True,
    ),
    SeedPost(
        user_handle="FarmWatch_Africa",
        content="Millet fields in northern Ghana are responding well to early planting where rainfall onset matched local forecasts.",
        latitude=9.4008,
        longitude=-0.8393,
        hours_ago=286,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriGlobal",
        content="Soybean rust monitoring is intensifying in Paraguay after humid conditions persisted for several consecutive days.",
        latitude=-25.2637,
        longitude=-57.5759,
        hours_ago=301,
        is_global=True,
    ),
    SeedPost(
        user_handle="CropWatch_Global",
        content="Cotton growers in Pakistan are watching irrigation demand rise as hotter afternoons push evapotranspiration higher.",
        latitude=31.5204,
        longitude=74.3587,
        hours_ago=317,
        is_global=True,
    ),
    SeedPost(
        user_handle="AgriSense_AI",
        content="Remote sensing indicates improving vegetation vigor in parts of New Zealand where pasture recovery accelerated after rainfall.",
        latitude=-41.2866,
        longitude=174.7762,
        hours_ago=333,
        is_global=True,
    ),
]


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)
    social_models.ensure_social_schema(engine)


def ensure_user(session, user: SeedUser) -> None:
    existing = session.query(User).filter(User.email == user.email).first()
    if existing is None:
        existing = User(
            name=user.display_name,
            email=user.email,
            password=hash_password(DEFAULT_PASSWORD),
            is_verified=True,
        )
        session.add(existing)
        session.flush()
    else:
        existing.name = user.display_name
        existing.is_verified = True

    profile = session.query(SocialProfile).filter(SocialProfile.user_id == user.email).first()
    if profile is None:
        profile = SocialProfile(user_id=user.email)
        session.add(profile)

    profile.display_name = user.display_name
    profile.bio = user.bio
    profile.location = user.location
    profile.goals = user.goals
    profile.crops = user.crops
    profile.experience_level = user.experience_level


def ensure_post(session, user_map: dict[str, SeedUser], post: SeedPost, now_utc: datetime) -> bool:
    seed_user = user_map[post.user_handle]
    existing = (
        session.query(SocialPost)
        .filter(
            SocialPost.user_id == seed_user.email,
            SocialPost.content == post.content,
            SocialPost.latitude == post.latitude,
            SocialPost.longitude == post.longitude,
        )
        .first()
    )
    if existing is not None:
        existing.user_name = seed_user.display_name
        existing.is_global = post.is_global
        existing.image_url = post.image_url
        existing.media_type = post.media_type
        return False

    created_at = now_utc - timedelta(hours=post.hours_ago)
    session.add(
        SocialPost(
            user_id=seed_user.email,
            user_name=seed_user.display_name,
            content=post.content,
            image_url=post.image_url,
            media_type=post.media_type,
            latitude=post.latitude,
            longitude=post.longitude,
            is_global=post.is_global,
            created_at=int(created_at.timestamp() * 1000),
        )
    )
    return True


def main() -> None:
    ensure_schema()
    session = SessionLocal()
    now_utc = datetime.now(timezone.utc)
    user_map = {user.handle: user for user in SEED_USERS}
    created_posts = 0
    try:
        for user in SEED_USERS:
            ensure_user(session, user)

        for post in SEED_POSTS:
            created_posts += 1 if ensure_post(session, user_map, post, now_utc) else 0

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"Seed complete. Users ensured: {len(SEED_USERS)} | New posts inserted: {created_posts}")
    print(f"Default password for seeded system users: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    main()