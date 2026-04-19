import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

# Approximate bounding boxes for countries (for basic geolocation)
COUNTRY_BOUNDARIES = {
    "Jamaica": {"lat_min": 17.7, "lat_max": 18.6, "lon_min": -78.5, "lon_max": -76.0},
    "USA": {"lat_min": 24.0, "lat_max": 49.0, "lon_min": -125.0, "lon_max": -66.0},
    "Canada": {"lat_min": 42.0, "lat_max": 83.0, "lon_min": -141.0, "lon_max": -52.0},
}

def _load_products_kb() -> Dict[str, Any]:
    """Load agricultural products knowledge base"""
    kb_path = Path(__file__).resolve().parent / "agri_products_kb.json"
    try:
        return json.loads(kb_path.read_text(encoding="utf-8"))
    except Exception:
        return {"categories": {}, "sourcing": {"store_locations": []}}

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers"""
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def _detect_country(latitude: float, longitude: float) -> str:
    """Detect country from coordinates based on approximate boundaries"""
    for country, bounds in COUNTRY_BOUNDARIES.items():
        if (bounds["lat_min"] <= latitude <= bounds["lat_max"] and
            bounds["lon_min"] <= longitude <= bounds["lon_max"]):
            return country
    return "Unknown"

def _get_location_context(latitude: float, longitude: float) -> str:
    """Get human-readable location context from coordinates"""
    country = _detect_country(latitude, longitude)
    
    # Add region/island info for known coordinates
    if country == "Jamaica":
        if latitude > 18.3:
            return "Jamaica (Northern Region)"
        elif latitude < 18.1:
            return "Jamaica (Southern Region)"
        return "Jamaica"
    return country

def find_nearby_stores(latitude: float, longitude: float, radius_km: float = 50) -> List[Dict[str, Any]]:
    """Find stores selling agricultural products near given coordinates.
    
    Prioritizes stores in the same country/region as the farm location.
    First shows closest stores in the same country, then expands to regional stores.
    """
    kb = _load_products_kb()
    stores = kb.get("sourcing", {}).get("store_locations", [])
    
    farm_country = _detect_country(latitude, longitude)
    
    nearby = []
    for store in stores:
        store_lat = store.get("latitude")
        store_lon = store.get("longitude")
        if store_lat is None or store_lon is None:
            continue
        
        distance = _haversine_distance(latitude, longitude, store_lat, store_lon)
        store_country = store.get("country", _detect_country(store_lat, store_lon))
        
        # Include stores within radius AND prioritize same-country stores
        if distance <= radius_km or store_country == farm_country:
            store_copy = dict(store)
            store_copy["distance_km"] = round(distance, 1)
            store_copy["in_same_country"] = (store_country == farm_country)
            nearby.append(store_copy)
    
    # Sort: same-country stores first, then by distance
    nearby.sort(key=lambda x: (not x["in_same_country"], x["distance_km"]))
    
    return nearby

def get_product_categories() -> Dict[str, Any]:
    """Get all product categories and products"""
    kb = _load_products_kb()
    return kb.get("categories", {})

def get_product_recommendations(issue: str) -> Dict[str, Any]:
    """Get product recommendations based on farm issue"""
    kb = _load_products_kb()
    categories = kb.get("categories", {})
    
    issue_lower = (issue or "").lower()
    recommendations = {}
    
    for category, data in categories.items():
        products = data.get("products", [])
        for product in products:
            use_for = product.get("use_for", [])
            for use in use_for:
                if any(keyword in issue_lower for keyword in [use.replace("_", " "), use.replace("_", "_")]):
                    if category not in recommendations:
                        recommendations[category] = []
                    recommendations[category].append(product)
    
    return recommendations

def search_online_stores(product_name: str, latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
    """Search for product online (can be extended with real Google Shopping API)"""
    # For now, return curated info based on product name
    kb = _load_products_kb()
    retailers = kb.get("sourcing", {}).get("national_retailers", [])
    
    product_lower = (product_name or "").lower()
    relevant_retailers = []
    
    for retailer in retailers:
        retailer_name = retailer.get("name", "").lower()
        if any(word in product_lower for word in ["fertilizer", "npk", "nitro", "phosph", "potash"]):
            if "tractor" in retailer_name or "home" in retailer_name or "lowe" in retailer_name:
                relevant_retailers.append(retailer)
        else:
            relevant_retailers.append(retailer)
    
    return {
        "product": product_name,
        "recommended_retailers": relevant_retailers[:3],
        "note": "Visit retailer websites or call for current stock and pricing"
    }

def get_procurement_guidelines() -> List[str]:
    """Get product procurement guidelines"""
    kb = _load_products_kb()
    return kb.get("procurement_guidelines", [])

def format_stores_for_ai(stores: List[Dict[str, Any]]) -> str:
    """Format store list for AI consumption with location-aware context"""
    if not stores:
        return "No stores found within 50km radius."
    
    lines = []
    same_country_stores = [s for s in stores if s.get("in_same_country")]
    other_stores = [s for s in stores if not s.get("in_same_country")]
    
    if same_country_stores:
        lines.append("**Local Suppliers in Your Region:**")
        for i, store in enumerate(same_country_stores[:5], 1):
            name = store.get("name", "Unknown")
            distance = store.get("distance_km", "?")
            store_type = store.get("type", "").replace("_", " ").title()
            phone = store.get("phone", "N/A")
            country = store.get("country", "Local")
            lines.append(f"{i}. {name} ({store_type}) - {distance}km - {country}")
            lines.append(f"   📞 {phone}")
    
    if other_stores:
        lines.append("\n**Other Suppliers (Different Region):**")
        for store in other_stores[:3]:
            name = store.get("name", "Unknown")
            distance = store.get("distance_km", "?")
            store_type = store.get("type", "").replace("_", " ").title()
            country = store.get("country", _detect_country(store.get("latitude", 0), store.get("longitude", 0)))
            lines.append(f"• {name} ({store_type}) - {distance}km - {country}")
    
    return "\n".join(lines)

def format_products_for_ai(products_dict: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format product recommendations for AI consumption"""
    if not products_dict:
        return "No specific product recommendations available."
    
    lines = []
    for category, items in products_dict.items():
        lines.append(f"\n**{category.replace('_', ' ').title()}:**")
        for product in items[:2]:  # Show top 2 per category
            name = product.get("name", "Unknown")
            lines.append(f"  • {name}")
    
    return "\n".join(lines)
