import unittest

from services.analysis_engine import analyze_internship


class PaymentVariantTests(unittest.TestCase):
    def get_flag_titles(self, text):
        result = analyze_internship(
            text=text,
            stipend_monthly=6000,
            hours_per_day=8,
            days_per_week=6,
        )

        return [
            flag["title"]
            for flag in result["detected_flags"]
        ]

    def test_registration_and_security_fee(self):
        titles = self.get_flag_titles(
            "To confirm your position, pay a registration "
            "and security fee of ₹2,499 today."
        )

        self.assertIn("Payment requested", titles)

    def test_registration_charge(self):
        titles = self.get_flag_titles(
            "Candidates must submit a registration charge "
            "before joining."
        )

        self.assertIn("Payment requested", titles)

    def test_document_verification_fee(self):
        titles = self.get_flag_titles(
            "A document verification fee must be paid before "
            "the offer letter is released."
        )

        self.assertIn("Payment requested", titles)

    def test_numeric_transfer_request(self):
        titles = self.get_flag_titles(
            "Transfer INR 2499 today to secure your internship "
            "position."
        )

        self.assertIn("Payment requested", titles)

    def test_negated_combined_fee_is_safe(self):
        titles = self.get_flag_titles(
            "No registration or security fee is required at "
            "any stage."
        )

        self.assertNotIn("Payment requested", titles)

    def test_negated_payment_amount_is_safe(self):
        titles = self.get_flag_titles(
            "Candidates are not required to pay ₹2499 or any "
            "other amount."
        )

        self.assertNotIn("Payment requested", titles)

    def test_contrast_after_negation_is_detected(self):
        titles = self.get_flag_titles(
            "No fee is charged during application, but selected "
            "candidates must pay a registration and security fee."
        )

        self.assertIn("Payment requested", titles)


if __name__ == "__main__":
    unittest.main()