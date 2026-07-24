import unittest
from email.message import Message
from unittest.mock import patch

from services.website_verification import (
    WebsiteVerificationError,
    verify_company_website,
)


class WebsiteVerificationTests(unittest.TestCase):
    @staticmethod
    def public_dns(*args, **kwargs):
        return [
            (
                2,
                1,
                6,
                "",
                ("93.184.216.34", 0),
            )
        ]

    @staticmethod
    def response(
        status_code=200,
        location=None,
        body=b"<html><title>Example Careers</title></html>",
    ):
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"

        if location:
            headers["Location"] = location

        return {
            "status_code": status_code,
            "headers": headers,
            "body": body,
        }

    @patch(
        "services.website_verification.socket.getaddrinfo",
        side_effect=public_dns,
    )
    @patch("services.website_verification._request_once")
    def test_https_website(self, request_once, _dns):
        request_once.return_value = self.response()

        result = verify_company_website("https://example.com")

        self.assertTrue(result["reachable"])
        self.assertTrue(result["uses_https"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["page_title"], "Example Careers")

    @patch(
        "services.website_verification.socket.getaddrinfo",
        side_effect=public_dns,
    )
    @patch("services.website_verification._request_once")
    def test_http_warning(self, request_once, _dns):
        request_once.return_value = self.response()

        result = verify_company_website("http://example.com")

        self.assertFalse(result["uses_https"])
        self.assertEqual(result["checks"][1]["type"], "warning")

    @patch(
        "services.website_verification.socket.getaddrinfo",
        side_effect=public_dns,
    )
    @patch("services.website_verification._request_once")
    def test_safe_redirect(self, request_once, _dns):
        request_once.side_effect = [
            self.response(301, "https://www.example.com/careers"),
            self.response(200),
        ]

        result = verify_company_website("http://example.com")

        self.assertEqual(result["redirect_count"], 1)
        self.assertEqual(
            result["final_url"],
            "https://www.example.com/careers",
        )

    @patch(
        "services.website_verification.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    def test_localhost_is_blocked(self, _dns):
        with self.assertRaises(WebsiteVerificationError):
            verify_company_website("http://localhost")

    @patch(
        "services.website_verification.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("192.168.1.10", 0))],
    )
    def test_private_address_is_blocked(self, _dns):
        with self.assertRaises(WebsiteVerificationError):
            verify_company_website("http://internal.example")

    def test_non_web_scheme_is_blocked(self):
        with self.assertRaises(WebsiteVerificationError):
            verify_company_website("file:///etc/passwd")

    def test_credentials_are_blocked(self):
        with self.assertRaises(WebsiteVerificationError):
            verify_company_website(
                "https://user:password@example.com"
            )


if __name__ == "__main__":
    unittest.main()
