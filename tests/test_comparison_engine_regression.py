import unittest

from services.comparison_engine import compare_internships


class ComparisonEngineTests(unittest.TestCase):
    def setUp(self):
        self.safe = {
            "id": "safe-id",
            "role_title": "Data Analyst Intern",
            "verification_score": 90,
            "value_score": 90,
            "compatibility_score": 80,
            "effective_hourly_stipend": 92.38,
            "assessment_status": "appears_reasonable",
            "compatibility_status": "manageable",
            "detected_flags": [],
        }
        self.risky = {
            "id": "risky-id",
            "role_title": "ML Intern",
            "verification_score": 20,
            "value_score": 65,
            "compatibility_score": 30,
            "effective_hourly_stipend": 28.87,
            "assessment_status": "potentially_suspicious",
            "compatibility_status": "conflict_risk",
            "detected_flags": [
                {"title": "Payment requested"},
                {"title": "Urgency pressure"},
            ],
        }

    def test_safer_assessment_wins(self):
        result = compare_internships(self.safe, self.risky)
        self.assertEqual(result["overall_winner"], "first")
        self.assertGreater(
            result["first_score"],
            result["second_score"],
        )

    def test_fewer_warning_indicators_wins_metric(self):
        result = compare_internships(self.safe, self.risky)
        self.assertEqual(
            result["metrics"]["warning_indicators"]["winner"],
            "first",
        )

    def test_reversed_order_changes_winner_side(self):
        result = compare_internships(self.risky, self.safe)
        self.assertEqual(result["overall_winner"], "second")

    def test_same_assessment_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_internships(self.safe, self.safe)

    def test_equal_assessments_tie(self):
        second = dict(self.safe)
        second["id"] = "another-safe-id"
        result = compare_internships(self.safe, second)
        self.assertEqual(result["overall_winner"], "tie")


if __name__ == "__main__":
    unittest.main()