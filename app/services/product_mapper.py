from __future__ import annotations

from typing import Any, Dict, List


def map_products(crop: Dict[str, Any]) -> List[Dict[str, str]]:
    products: List[Dict[str, str]] = []
    watering = str(crop.get("watering") or "").lower()
    sunlight = [str(s).lower() for s in (crop.get("sunlight") or [])]

    if watering == "high":
        products.append(
            {
                "name": "Drip Irrigation System",
                "type": "irrigation",
                "reason": "supports frequent and efficient root-zone watering for high-demand crops",
                "timing": "run short irrigation cycles early morning and late afternoon",
            }
        )

    if "full sun" in sunlight:
        products.append(
            {
                "name": "Mulch Cover",
                "type": "soil_protection",
                "reason": "helps retain moisture and reduce heat stress under strong sunlight",
                "timing": "apply after transplanting or at early vegetative stage",
            }
        )

    products.append(
        {
            "name": "Neem Oil",
            "type": "pesticide",
            "reason": "supports preventive pest management, especially in warm humid weather",
            "timing": "spray weekly in the evening and reapply after heavy rain",
        }
    )
    return products
