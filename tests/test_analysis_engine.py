import unittest

from services.analysis_engine import (
    analyze_internship,
    calculate_hourly_stipend,
)


class AnalysisEngineTests(unittest.TestCase):

    def test_safe_offer_with_negated_payment(self):
        result = analyze_internship(
            text=(
                "Candidates complete a technical interview and "
                "receive a formal offer letter through "
                "careers@brightpath.in. A dedicated mentor is "
                "assigned. No registration fee or payment is required."
            ),
            stipend_monthly=8000,
            hours_per_day=7,
            days_per_week=6,
        )

        self.assertEqual(
            result["assessment_status"],
            "appears_reasonable",
        )
        self.assertEqual(result["detected_flags"], [])
        self.assertEqual(result["verification_score"], 90)
        self.assertEqual(result["value_score"], 90)

    def test_multiple_dangerous_indicators(self):
        result = analyze_internship(
            text=(
                "You are guaranteed selection. Pay a registration "
                "fee today and join immediately. Send your bank "
                "account details through Telegram only."
            ),
            stipend_monthly=7000,
            hours_per_day=7,
            days_per_week=6,
        )

        detected_titles = {
            flag["title"]
            for flag in result["detected_flags"]
        }

        self.assertEqual(
            result["assessment_status"],
            "potentially_suspicious",
        )
        self.assertIn("Payment requested", detected_titles)
        self.assertIn(
            "Guaranteed selection claim",
            detected_titles,
        )
        self.assertIn("Urgency pressure", detected_titles)
        self.assertIn(
            "Sensitive information requested",
            detected_titles,
        )
        self.assertIn(
            "Informal communication channel",
            detected_titles,
        )

    def test_contrast_does_not_hide_payment_warning(self):
        result = analyze_internship(
            text=(
                "No interview is required, but pay a registration "
                "fee to secure the position."
            ),
            stipend_monthly=5000,
            hours_per_day=5,
            days_per_week=5,
        )

        detected_titles = [
            flag["title"]
            for flag in result["detected_flags"]
        ]

        self.assertIn("Payment requested", detected_titles)

    def test_negated_positive_evidence_is_not_rewarded(self):
        result = analyze_internship(
            text=(
                "There is no dedicated mentor and no formal offer "
                "letter will be provided."
            )
        )

        evidence_labels = [
            factor["label"]
            for factor in result["verification_factors"]
        ]

        self.assertNotIn(
            "Positive verification evidence",
            evidence_labels,
        )
        self.assertEqual(
            result["assessment_status"],
            "verification_required",
        )

    def test_free_email_is_not_official_evidence(self):
        result = analyze_internship(
            text=(
                "Contact the recruiter at recruiter@gmail.com "
                "for additional information."
            )
        )

        evidence_labels = [
            factor["label"]
            for factor in result["verification_factors"]
        ]

        self.assertNotIn(
            "Company-style email address supplied",
            evidence_labels,
        )

    def test_company_email_is_supporting_evidence(self):
        result = analyze_internship(
            text=(
                "Contact the recruiter at careers@examplecompany.in "
                "for additional information."
            )
        )

        evidence_labels = [
            factor["label"]
            for factor in result["verification_factors"]
        ]

        self.assertIn(
            "Company-style email address supplied",
            evidence_labels,
        )

    def test_hourly_stipend_calculation(self):
        hourly_stipend = calculate_hourly_stipend(
            stipend_monthly=7000,
            hours_per_day=7,
            days_per_week=6,
        )

        self.assertEqual(hourly_stipend, 38.49)

    def test_hourly_stipend_requires_working_hours(self):
        hourly_stipend = calculate_hourly_stipend(
            stipend_monthly=7000,
            hours_per_day=None,
            days_per_week=None,
        )

        self.assertIsNone(hourly_stipend)


if __name__ == "__main__":
    unittest.main()