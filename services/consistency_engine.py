import re
from difflib import SequenceMatcher
from urllib.parse import urlparse


FREE_EMAIL_PROVIDERS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "protonmail.com",
    "rediffmail.com",
}


def normalize_text(value):
    """Normalize text for safer comparisons."""

    if not value:
        return ""

    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def similarity(a, b):
    """Return similarity percentage between two strings."""

    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0

    return round(
        SequenceMatcher(None, a, b).ratio() * 100,
        2,
    )


def extract_email_domain(email):
    """Extract domain from recruiter email."""

    if not email or "@" not in email:
        return ""

    return email.lower().strip().split("@")[-1]


def extract_website_domain(website):
    """Extract normalized domain from company website."""

    if not website:
        return ""

    website = website.lower().strip()

    if not website.startswith(
        (
            "http://",
            "https://",
        )
    ):
        website = "https://" + website

    try:
        parsed = urlparse(website)
        domain = parsed.netloc

    except Exception:
        return ""

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def company_present_in_text(
    company_name,
    extracted_text,
):
    """
    Check whether the supplied company name appears
    consistent with the submitted evidence.
    """

    company = normalize_text(company_name)
    document = normalize_text(extracted_text)

    if not company or not document:
        return None

    # Direct company-name match
    if company in document:
        return True

    ignored_words = {
        "private",
        "limited",
        "ltd",
        "pvt",
        "technologies",
        "technology",
        "solutions",
        "company",
        "services",
    }

    company_words = [
        word
        for word in company.split()
        if len(word) > 2
        and word not in ignored_words
    ]

    if not company_words:
        return False

    matched_words = sum(
        1
        for word in company_words
        if word in document
    )

    return (
        matched_words / len(company_words)
        >= 0.6
    )


def role_present_in_text(
    role_title,
    extracted_text,
):
    """
    Check whether the supplied internship role appears
    consistent with the submitted evidence.
    """

    role = normalize_text(role_title)
    document = normalize_text(extracted_text)

    if not role or not document:
        return None

    # Direct role match
    if role in document:
        return True

    role_words = [
        word
        for word in role.split()
        if len(word) > 2
        and word not in {
            "intern",
            "internship",
            "trainee",
        }
    ]

    if not role_words:
        return None

    matched_words = sum(
        1
        for word in role_words
        if word in document
    )

    return (
        matched_words / len(role_words)
        >= 0.6
    )


def analyze_consistency(
    company_name,
    role_title,
    extracted_text,
    recruiter_email=None,
    company_website=None,
):
    """
    Compare user-entered internship information with
    the submitted internship evidence.

    The function checks:

    - Company identity consistency
    - Internship role consistency
    - Recruiter email domain
    - Company website domain

    It returns an explainable consistency assessment.
    """

    checks = []
    warnings = []

    score = 100

    # ---------------------------------------------------------
    # COMPANY NAME CHECK
    # ---------------------------------------------------------

    company_match = company_present_in_text(
        company_name,
        extracted_text,
    )

    if company_match is True:
        checks.append({
            "name": "Company identity",
            "status": "consistent",
            "message": (
                "The supplied company name appears "
                "consistent with the submitted internship "
                "evidence."
            ),
        })

    elif company_match is False:
        score -= 30

        checks.append({
            "name": "Company identity",
            "status": "warning",
            "message": (
                "The supplied company name could not be "
                "clearly confirmed from the submitted "
                "document."
            ),
        })

        warnings.append(
            "Company information may require "
            "additional verification."
        )

    else:
        checks.append({
            "name": "Company identity",
            "status": "unknown",
            "message": (
                "There was not enough information to "
                "compare the company identity."
            ),
        })

    # ---------------------------------------------------------
    # INTERNSHIP ROLE CHECK
    # ---------------------------------------------------------

    role_match = role_present_in_text(
        role_title,
        extracted_text,
    )

    if role_match is True:
        checks.append({
            "name": "Internship role",
            "status": "consistent",
            "message": (
                "The supplied internship role appears "
                "consistent with the submitted evidence."
            ),
        })

    elif role_match is False:
        score -= 20

        checks.append({
            "name": "Internship role",
            "status": "warning",
            "message": (
                "The supplied internship role was not "
                "clearly identified in the submitted "
                "document."
            ),
        })

        warnings.append(
            "Internship role information may be "
            "inconsistent."
        )

    else:
        checks.append({
            "name": "Internship role",
            "status": "unknown",
            "message": (
                "There was not enough information to "
                "compare the internship role."
            ),
        })

    # ---------------------------------------------------------
    # RECRUITER DOMAIN VS COMPANY WEBSITE
    # ---------------------------------------------------------

    email_domain = extract_email_domain(
        recruiter_email
    )

    website_domain = extract_website_domain(
        company_website
    )

    if email_domain and website_domain:

        if email_domain == website_domain:
            checks.append({
                "name": "Recruiter domain",
                "status": "consistent",
                "message": (
                    "The recruiter email domain matches "
                    "the supplied company website domain."
                ),
            })

        elif email_domain in FREE_EMAIL_PROVIDERS:
            score -= 15

            checks.append({
                "name": "Recruiter domain",
                "status": "warning",
                "message": (
                    "The recruiter uses a free email "
                    "provider instead of the supplied "
                    "company domain."
                ),
            })

            warnings.append(
                "Recruiter email uses a free email "
                "provider."
            )

        else:
            score -= 20

            checks.append({
                "name": "Recruiter domain",
                "status": "warning",
                "message": (
                    "The recruiter email domain differs "
                    "from the supplied company website "
                    "domain."
                ),
            })

            warnings.append(
                "Recruiter and company website domains "
                "do not match."
            )

    elif email_domain:

        if email_domain in FREE_EMAIL_PROVIDERS:
            score -= 10

            checks.append({
                "name": "Recruiter email",
                "status": "warning",
                "message": (
                    "The recruiter uses a public email "
                    "provider. This does not prove the "
                    "offer is unsafe, but independent "
                    "verification is recommended."
                ),
            })

            warnings.append(
                "Recruiter email uses a public email "
                "provider."
            )

        else:
            checks.append({
                "name": "Recruiter email",
                "status": "unknown",
                "message": (
                    "A recruiter domain was provided but "
                    "no company website was available "
                    "for comparison."
                ),
            })

    elif website_domain:

        checks.append({
            "name": "Company website",
            "status": "unknown",
            "message": (
                "A company website was provided but no "
                "recruiter email was available for "
                "domain comparison."
            ),
        })

    # ---------------------------------------------------------
    # FINAL RESULT
    # ---------------------------------------------------------

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    warning_count = sum(
        1
        for check in checks
        if check.get("status") == "warning"
    )

    unknown_count = sum(
        1
        for check in checks
        if check.get("status") == "unknown"
    )

    if score < 60:
        status = "Conflicting Evidence"

        interpretation = (
            "One or more supplied details conflict with the submitted "
            "internship evidence. Verify the company, role and recruiter "
            "information before relying on the assessment."
        )

    elif (
        score < 85
        or warning_count > 0
        or unknown_count > 0
    ):
        status = "Review Recommended"

        if (
            warning_count == 0
            and unknown_count > 0
        ):
            interpretation = (
                "The supplied details do not contradict each other, "
                "but some information could not be independently "
                "cross-checked. Additional verification is recommended."
            )

        elif warning_count > 0:
            interpretation = (
                "Most supplied details may be consistent, but one or "
                "more checks identified information that should be "
                "reviewed independently."
            )

        else:
            interpretation = (
                "The submitted information is partly consistent, but "
                "additional verification is recommended before relying "
                "on it."
            )

    else:
        status = "Consistent"

        interpretation = (
            "The supplied company, role and recruiter details appear "
            "internally consistent with the submitted evidence. This "
            "does not independently prove legitimacy."
        )

    return {
        "consistency_score": score,
        "consistency_status": status,
        "interpretation": interpretation,
        "checks": checks,
        "warnings": warnings,
        "warning_count": warning_count,
        "unknown_count": unknown_count,
        "recruiter_domain": email_domain,
        "website_domain": website_domain,
    }