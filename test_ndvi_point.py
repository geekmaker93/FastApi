import unittest
from unittest.mock import patch

from app.routes.ndvi import get_ndvi_for_point


class NDVIPointTests(unittest.TestCase):
    def setUp(self):
        from app.routes import ndvi

        ndvi._NDVI_POINT_CACHE.clear()

    @patch("app.routes.ndvi.get_historical_ndvi", side_effect=RuntimeError("Earth Engine unavailable"))
    def test_returns_fallback_when_earth_engine_is_unavailable(self, _get_historical_ndvi):
        response = get_ndvi_for_point(lat=38.7945952, lon=-106.5348379)

        self.assertEqual(response["source"], "fallback")
        self.assertEqual(response["health_status"], "Estimated")
        self.assertEqual(response["ndvi_mean"], 0.5)
        self.assertIn("Earth Engine unavailable", response["provider_error"])


if __name__ == "__main__":
    unittest.main()