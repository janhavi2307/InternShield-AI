from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "services" / "support_system.py"
ENV_EXAMPLE = ROOT / ".env.example"

if not TARGET.exists():
    raise SystemExit(
        "ERROR: Put this script inside D:\\InternShield-AI and run it there."
    )

text = TARGET.read_text(encoding="utf-8")

if "def _send_email_via_brevo(" in text:
    print("Brevo email upgrade is already installed.")
    raise SystemExit(0)

backup = TARGET.with_name(
    "support_system.py.before_brevo_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + ".bak"
)
shutil.copy2(TARGET, backup)
print("Backup:", backup)

if "import json\n" not in text:
    text = text.replace(
        "import html\n",
        "import html\nimport json\n",
        1,
    )

if "from urllib import error as urllib_error" not in text:
    text = text.replace(
        "from urllib.parse import urljoin\n",
        "from urllib import error as urllib_error\n"
        "from urllib import request as urllib_request\n"
        "from urllib.parse import urljoin\n",
        1,
    )

helper = r"""
def _send_email_via_brevo(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
) -> dict:
    recipients = [
        item.strip()
        for item in recipients
        if item and item.strip()
    ]

    if not recipients:
        return {
            "sent": False,
            "reason": "No recipient email is configured.",
            "provider": "brevo",
        }

    api_key = (
        os.getenv("BREVO_API_KEY")
        or ""
    ).strip()

    sender_email = (
        os.getenv("BREVO_SENDER_EMAIL")
        or ""
    ).strip()

    sender_name = (
        os.getenv("BREVO_SENDER_NAME")
        or "InternShield Support"
    ).strip()

    if not api_key:
        return {
            "sent": False,
            "reason": "BREVO_API_KEY is not configured.",
            "provider": "brevo",
        }

    if not sender_email:
        return {
            "sent": False,
            "reason": "BREVO_SENDER_EMAIL is not configured.",
            "provider": "brevo",
        }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {"email": recipient}
            for recipient in recipients
        ],
        "subject": subject,
        "textContent": body,
    }

    if html_body:
        payload["htmlContent"] = html_body

    if reply_to:
        payload["replyTo"] = {
            "email": reply_to,
        }

    api_request = urllib_request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(
            api_request,
            timeout=20,
        ) as response:
            status_code = response.getcode() or 0

        if 200 <= status_code < 300:
            return {
                "sent": True,
                "reason": "",
                "provider": "brevo",
            }

        return {
            "sent": False,
            "reason": f"Brevo returned HTTP {status_code}.",
            "provider": "brevo",
        }

    except urllib_error.HTTPError as exc:
        try:
            details = (
                exc.read()
                .decode("utf-8", errors="replace")
            )
        except Exception:
            details = str(exc)

        return {
            "sent": False,
            "reason": (
                f"Brevo API HTTP {exc.code}: "
                f"{details[:500]}"
            ),
            "provider": "brevo",
        }

    except urllib_error.URLError as exc:
        return {
            "sent": False,
            "reason": (
                "Brevo API connection failed: "
                f"{exc.reason}"
            ),
            "provider": "brevo",
        }

    except Exception as exc:
        return {
            "sent": False,
            "reason": f"Brevo email failed: {exc}",
            "provider": "brevo",
        }


"""

marker = "def _send_email(\n"

if marker not in text:
    raise SystemExit(
        "ERROR: Could not find _send_email in services/support_system.py"
    )

text = text.replace(
    marker,
    helper + marker,
    1,
)

signature_end = """) -> dict:
    recipients = [
"""

dispatch = """) -> dict:
    email_provider = (
        os.getenv("EMAIL_PROVIDER")
        or ""
    ).strip().lower()

    brevo_api_key = (
        os.getenv("BREVO_API_KEY")
        or ""
    ).strip()

    if (
        email_provider == "brevo"
        or bool(brevo_api_key)
    ):
        return _send_email_via_brevo(
            recipients=recipients,
            subject=subject,
            body=body,
            html_body=html_body,
            reply_to=reply_to,
        )

    # Existing SMTP code remains as a local fallback.
    recipients = [
"""

start = text.find("def _send_email(\n")
pos = text.find(signature_end, start)

if pos == -1:
    raise SystemExit(
        "ERROR: Could not patch _send_email safely."
    )

text = (
    text[:pos]
    + text[pos:].replace(
        signature_end,
        dispatch,
        1,
    )
)

text = text.replace(
    'or "SMTP is not configured."',
    'or "Email delivery is not configured."',
)

TARGET.write_text(
    text,
    encoding="utf-8",
)

print("Updated:", TARGET)

brevo_env = """

# ---------------------------------------------------------
# TRANSACTIONAL EMAIL - BREVO HTTPS API
# ---------------------------------------------------------

EMAIL_PROVIDER=brevo
BREVO_API_KEY=your-brevo-api-key
BREVO_SENDER_EMAIL=your-verified-sender@example.com
BREVO_SENDER_NAME=InternShield Support
"""

if ENV_EXAMPLE.exists():
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")

    if "BREVO_API_KEY=" not in env_text:
        ENV_EXAMPLE.write_text(
            env_text.rstrip()
            + brevo_env
            + "\n",
            encoding="utf-8",
        )
        print("Updated:", ENV_EXAMPLE)

print("\nBrevo HTTPS email support installed.")
print("Run:")
print("python -m py_compile services\\support_system.py")
