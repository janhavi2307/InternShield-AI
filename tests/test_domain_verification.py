import unittest

from services.domain_verification import analyze_recruiter_domain


class DomainVerificationTests(unittest.TestCase):
    def test_matching_official_domains(self):
        result = analyze_recruiter_domain(
            recruiter_email="careers@brightpath.in",
            company_website="https://www.brightpath.in/careers",
            company_name="BrightPath Technologies",
        )

        self.assertTrue(result["domain_match"])
        self.assertEqual(result["domain_status"], "consistent")
        self.assertFalse(result["email_is_free_provider"])

    def test_matching_subdomain(self):
        result = analyze_recruiter_domain(
            recruiter_email="hr@careers.example.com",
            company_website="https://www.example.com",
            company_name="Example",
        )

        self.assertTrue(result["domain_match"])

    def test_free_email_provider_requires_verification(self):
        result = analyze_recruiter_domain(
            recruiter_email="companyjobs@gmail.com",
            company_website="https://brightpath.in",
            company_name="BrightPath Technologies",
        )

        self.assertTrue(result["email_is_free_provider"])
        self.assertEqual(
            result["domain_status"],
            "verification_required",
        )

    def test_mismatched_company_domains(self):
        result = analyze_recruiter_domain(
            recruiter_email="hr@brightpath-careers.net",
            company_website="https://brightpath.in",
            company_name="BrightPath Technologies",
        )

        self.assertFalse(result["domain_match"])
        self.assertEqual(result["domain_status"], "high_concern")

    def test_disposable_email_is_high_concern(self):
        result = analyze_recruiter_domain(
            recruiter_email="recruiter@mailinator.com",
            company_website="https://example.com",
            company_name="Example",
        )

        self.assertTrue(result["email_is_disposable_provider"])
        self.assertEqual(result["domain_status"], "high_concern")

    def test_invalid_email_format(self):
        result = analyze_recruiter_domain(
            recruiter_email="not-an-email",
            company_website="https://example.com",
            company_name="Example",
        )

        self.assertIsNone(result["recruiter_email_domain"])
        self.assertEqual(
            result["domain_status"],
            "verification_required",
        )

    def test_missing_information(self):
        result = analyze_recruiter_domain()

        self.assertIsNone(result["domain_match"])
        self.assertEqual(
            result["domain_status"],
            "insufficient_information",
        )

    def test_multi_part_indian_domain(self):
        result = analyze_recruiter_domain(
            recruiter_email="hr@careers.example.co.in",
            company_website="https://example.co.in",
            company_name="Example Private Limited",
        )

        self.assertTrue(result["domain_match"])


if __name__ == "__main__":
    unittest.main()