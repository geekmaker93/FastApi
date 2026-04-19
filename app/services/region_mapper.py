from __future__ import annotations


def get_region(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "default"

    # Jamaica bounding box (lightweight first pass).
    if 17.5 <= lat <= 18.6 and -78.5 <= lon <= -76.0:
        return "caribbean_tropical"

    return "default"
