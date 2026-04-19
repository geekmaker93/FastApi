import unittest

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


class LocalAdvisorTests(unittest.TestCase):
    def test_local_advisor_returns_grounded_sections(self):
        payload = {
            "question": "Will it be too cold today to plant flowers and what soil should I use?",
            "context": {
                "latitude": 18.0179,
                "longitude": -76.8099,
                "analytics": {
                    "overall_accuracy": 81.2,
                    "data_quality": {
                        "report_completeness_percent": 78.0,
                    },
                    "year_over_year": {
                        "change_percent": 4.8,
                        "status": "up",
                    },
                },
                "ndvi": {
                    "correlation_analysis": {
                        "correlation_coefficient": 0.71,
                        "interpretation": "strong positive",
                    }
                },
                "validation": {
                    "overall_accuracy": 81.2,
                },
            },
        }

        response = client.post("/ai/advisor", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "local-advisor")
        self.assertIn("answer", body)
        self.assertIn("Decision:", body["answer"])
        self.assertIn("Data comparison:", body["answer"])
        self.assertIn("Action plan:", body["answer"])
        self.assertIn("Why this recommendation:", body["answer"])
        self.assertIn("advisor", body)
        self.assertIn("comparison_points", body["advisor"])
        self.assertTrue(body["realtime_summary"]["available"])


if __name__ == "__main__":
    unittest.main()