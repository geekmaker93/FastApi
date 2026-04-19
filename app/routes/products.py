from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services.product_locator import (
    find_nearby_stores, 
    get_product_categories,
    get_product_recommendations,
    search_online_stores,
    get_procurement_guidelines,
    format_stores_for_ai,
    format_products_for_ai
)

router = APIRouter(prefix="/products", tags=["products"])

class ProductSearchRequest(BaseModel):
    issue: Optional[str] = None  # e.g., "fungal_pressure", "low_nitrogen"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = 50

class StoreSearchRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 50

class ProductLocatorResponse(BaseModel):
    product_recommendations: Dict[str, Any]
    nearby_stores: List[Dict[str, Any]]
    guidelines: List[str]
    formatted_for_ai: str

@router.get("/categories")
def get_categories():
    """Get all available agricultural product categories"""
    categories = get_product_categories()
    return {
        "categories": list(categories.keys()),
        "details": {cat: {
            "product_count": len(cat_data.get("products", [])),
            "products": [p.get("name") for p in cat_data.get("products", [])]
        } for cat, cat_data in categories.items()}
    }

@router.post("/find-solutions")
def find_product_solutions(body: ProductSearchRequest):
    """Find product recommendations and nearby stores for a farm issue"""
    if not body.issue:
        raise HTTPException(status_code=400, detail="issue is required")
    
    # Get product recommendations
    recommendations = get_product_recommendations(body.issue)
    
    # Find nearby stores if location provided
    stores = []
    if body.latitude is not None and body.longitude is not None:
        stores = find_nearby_stores(body.latitude, body.longitude, body.radius_km)
    
    # Get guidelines
    guidelines = get_procurement_guidelines()
    
    # Format for AI consumption
    formatted = f"""
Product Recommendations for '{body.issue}':
{format_products_for_ai(recommendations)}

Nearby Stores (within {body.radius_km}km):
{format_stores_for_ai(stores) if stores else "Provide your location for store recommendations."}

Important Guidelines:
{chr(10).join(f"• {g}" for g in guidelines)}
"""
    
    return {
        "issue": body.issue,
        "product_recommendations": recommendations,
        "nearby_stores": stores,
        "guidelines": guidelines,
        "formatted_for_ai": formatted
    }

@router.get("/nearby-stores")
def get_nearby_stores(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(50, ge=1, le=500)
):
    """Find stores selling agricultural products near given coordinates"""
    stores = find_nearby_stores(latitude, longitude, radius_km)
    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "stores_found": len(stores),
        "stores": stores,
        "formatted": format_stores_for_ai(stores)
    }

@router.get("/search")
def search_product(
    product_name: str = Query(...),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180)
):
    """Search for where to buy a specific product"""
    if not product_name or len(product_name) < 2:
        raise HTTPException(status_code=400, detail="product_name too short")
    
    # Search online retailers
    online_results = search_online_stores(product_name, latitude, longitude)
    
    # Search nearby physical stores if location provided
    nearby = []
    if latitude is not None and longitude is not None:
        nearby = find_nearby_stores(latitude, longitude, 50)
    
    return {
        "product": product_name,
        "online_retailers": online_results.get("recommended_retailers", []),
        "nearby_physical_stores": nearby,
        "guidelines": get_procurement_guidelines(),
        "note": "Contact stores for current stock and pricing"
    }

@router.get("/guidelines")
def get_buying_guidelines():
    """Get agricultural product procurement and usage guidelines"""
    return {
        "guidelines": get_procurement_guidelines(),
        "tip": "Always verify product registration and compatibility with your crops before purchase"
    }

@router.post("/ai-context")
def get_ai_product_context(body: ProductSearchRequest):
    """Get product information formatted for AI context"""
    recommendations = get_product_recommendations(body.issue or "general")
    stores = []
    if body.latitude is not None and body.longitude is not None:
        stores = find_nearby_stores(body.latitude, body.longitude, body.radius_km)
    
    return {
        "product_context": {
            "recommendations": recommendations,
            "stores": stores[:5],  # Top 5 closest
            "guidelines": get_procurement_guidelines()
        },
        "formatted_prompt": f"""
Available agricultural products for recommendations:
{format_products_for_ai(recommendations)}

Trusted retailers in the area:
{format_stores_for_ai(stores)}

When recommending products:
{chr(10).join(f"- {g}" for g in get_procurement_guidelines())}
""" if (recommendations or stores) else "User location not provided. Ask for location to provide store recommendations."
    }
