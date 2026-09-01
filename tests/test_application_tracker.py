import unittest

from services.application_tracker import (
    application_statistics,
    validate_application_payload,
)


class ApplicationTrackerTests(unittest.TestCase):
    def test_valid_payload(self):
        payload, errors = validate_application_payload({
            "company_name": "OpenAI",
            "role_title": "Engineering Intern",
            "status": "applied",
            "application_deadline": "2026-09-01",
            "interview_date": "",
            "notes": "Applied through the careers page.",
            "analysis_id": "assessment-1",
        })
        self.assertEqual(errors, [])
        self.assertEqual(payload["status"], "applied")
        self.assertIsNone(payload["interview_date"])

    def test_required_fields(self):
        _, errors = validate_application_payload({})
        self.assertIn("Company name is required.", errors)
        self.assertIn("Role title is required.", errors)

    def test_invalid_status_and_date(self):
        _, errors = validate_application_payload({
            "company_name": "Example",
            "role_title": "Intern",
            "status": "unknown",
            "application_deadline": "not-a-date",
        })
        self.assertIn("Select a valid application stage.", errors)
        self.assertIn("Enter a valid application deadline.", errors)

    def test_statistics(self):
        result = application_statistics([
            {"status": "saved"},
            {"status": "applied"},
            {"status": "applied"},
        ])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["applied"], 2)
        self.assertEqual(result["offer"], 0)


if __name__ == "__main__":
    unittest.main()