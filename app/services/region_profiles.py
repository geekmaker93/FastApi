from __future__ import annotations

from typing import Any, Dict


REGION_PROFILES: Dict[str, Dict[str, Any]] = {
    "caribbean_tropical": {
        "avg_temp_range": (24, 32),
        "rainfall_pattern": "seasonal",
        "soil_types": ["loamy", "clay", "sandy"],
        "preferred_crops": [
            "banana",
            "plantain",
            "papaya",
            "cassava",
            "yam",
        ],
        "risk_factors": [
            "hurricane",
            "flooding",
            "fungal_risk",
        ],
    },
}
