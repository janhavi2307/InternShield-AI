import re
from urllib.parse import urlparse


FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "yahoo.co.in",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "aol.com",
    "mail.com",
    "gmx.com",
}

DISPOSABLE_EMAIL_DOMAINS = {
    "10minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "temp-mail.org",
    "tempmail.com",
    "throwawaymail.com",
    "yopmail.com",
}

COMMON_MULTI_PART_SUFFIXES = {
    "ac.in",
    "co.in",
    "firm.in",
    "gen.in",
    "gov.in",
    "ind.in",
    "net.in",
    "org.in",
    "res.in",
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.sg",
    "com.my",
    "co.jp",
    "co.za",
    "com.br",
}

EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


def _clean_domain(domain):
    value = (domain or "").strip().lower().rstrip(".")

    if value.startswith("www."):
        value = value[4:]

    return value


def _extract_email_domain(email):
    normalized_email = (email or "").strip().lower()

    if not normalized_email:
        return None, None

    if not EMAIL_PATTERN.fullmatch(normalized_email):
        return normalized_email, None

    return normalized_email, _clean_domain(
        normalized_email.rsplit("@", 1)[1]
    )


def _extract_website_domain(website):
    normalized_website = (website or "").strip()

    if not normalized_website:
        return None, None

    parse_target = normalized_website

    if "://" not in parse_target:
        parse_target = f"https://{parse_target}"

    try:
        parsed = urlparse(parse_target)
        hostname = parsed.hostname
    except ValueError:
        hostname = None

    if not hostname:
        return normalized_website, None

    domain = _clean_domain(hostname)

    if (
        not domain
        or "." not in domain
        or " " in domain
        or not re.fullmatch(r"[a-z0-9.-]+", domain)
    ):
        return normalized_website, None

    return normalized_website, domain


def _registrable_domain(domain):
    cleaned = _clean_domain(domain)

    if not cleaned:
        return None

    labels = cleaned.split(".")

    if len(labels) < 2:
        return cleaned

    final_two = ".".join(labels[-2:])

    if final_two in COMMON_MULTI_PART_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])

    return final_two


def _domains_match(email_domain, website_domain):
    email_root = _registrable_domain(email_domain)
    website_root = _registrable_domain(website_domain)

    if not email_root or not website_root:
        return None

    return email_root == website_root


def _normalized_company_tokens(company_name):
    ignored_words = {
        "and",
        "company",
        "corporation",
        "global",
        "group",
        "india",
        "limited",
        "llp",
        "ltd",
        "private",
        "pvt",
        "services",
        "solutions",
        "technologies",
        "technology",
        "the",
    }

    tokens = re.findall(
        r"[a-z0-9]+",
        (company_name or "").lower(),
    )

    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in ignored_words
    }


def _domain_brand(domain):
    root = _registrable_domain(domain)

    if not root:
        return ""

    labels = root.split(".")

    if len(labels) >= 3 and ".".join(labels[-2:]) in (
        COMMON_MULTI_PART_SUFFIXES
    ):
        return labels[-3]

    return labels[0]


def _brand_consistency(company_name, website_domain):
    company_tokens = _normalized_company_tokens(company_name)

    if not company_tokens or not website_domain:
        return None

    brand = re.sub(
        r"[^a-z0-9]",
        "",
        _domain_brand(website_domain),
    )

    if not brand:
        return None

    return any(
        token in brand or brand in token
        for token in company_tokens
    )


def analyze_recruiter_domain(
    recruiter_email=None,
    company_website=None,
    company_name=None,
):
    normalized_email, email_domain = _extract_email_domain(
        recruiter_email
    )
    normalized_website, website_domain = _extract_website_domain(
        company_website
    )

    factors = []
    recommendations = []
    risk_points = 0

    email_is_free = bool(
        email_domain and email_domain in FREE_EMAIL_DOMAINS
    )
    email_is_disposable = bool(
        email_domain and email_domain in DISPOSABLE_EMAIL_DOMAINS
    )
    domain_match = _domains_match(email_domain, website_domain)
    brand_consistent = _brand_consistency(
        company_name,
        website_domain,
    )

    if recruiter_email and not email_domain:
        risk_points += 25
        factors.append({
            "type": "warning",
            "severity": "high",
            "label": "Invalid recruiter email format",
            "evidence": normalized_email,
            "points": -25,
        })
        recommendations.append(
            "Request communication from a correctly formatted "
            "official company email address."
        )

    elif email_is_disposable:
        risk_points += 45
        factors.append({
            "type": "warning",
            "severity": "high",
            "label": "Disposable recruiter email provider",
            "evidence": email_domain,
            "points": -45,
        })
        recommendations.append(
            "Do not share personal information or make payments. "
            "Request an email from the company's official domain."
        )

    elif email_is_free:
        risk_points += 18
        factors.append({
            "type": "warning",
            "severity": "medium",
            "label": "Free email provider used by recruiter",
            "evidence": email_domain,
            "points": -18,
        })
        recommendations.append(
            "Ask the recruiter to continue the conversation from "
            "an official company-domain email address."
        )

    elif email_domain:
        factors.append({
            "type": "evidence",
            "severity": "positive",
            "label": "Company-style recruiter email supplied",
            "evidence": email_domain,
            "points": 8,
        })

    if company_website and not website_domain:
        risk_points += 18
        factors.append({
            "type": "warning",
            "severity": "medium",
            "label": "Invalid company website format",
            "evidence": normalized_website,
            "points": -18,
        })
        recommendations.append(
            "Request the company's complete official website URL "
            "and verify it independently."
        )

    if domain_match is True:
        factors.append({
            "type": "evidence",
            "severity": "positive",
            "label": "Recruiter and website domains match",
            "evidence": (
                f"{email_domain} matches {website_domain}"
            ),
            "points": 15,
        })

    elif domain_match is False and not email_is_free:
        risk_points += 28
        factors.append({
            "type": "warning",
            "severity": "high",
            "label": "Recruiter and website domains do not match",
            "evidence": (
                f"{email_domain} does not match {website_domain}"
            ),
            "points": -28,
        })
        recommendations.append(
            "Verify why the recruiter's email domain differs from "
            "the company's website before accepting the offer."
        )

    if brand_consistent is False:
        risk_points += 12
        factors.append({
            "type": "warning",
            "severity": "medium",
            "label": "Website domain differs from company name",
            "evidence": (
                f"{company_name} compared with {website_domain}"
            ),
            "points": -12,
        })
        recommendations.append(
            "Search for the company independently and confirm that "
            "the supplied website belongs to it."
        )

    elif brand_consistent is True:
        factors.append({
            "type": "evidence",
            "severity": "positive",
            "label": "Website domain is consistent with company name",
            "evidence": website_domain,
            "points": 5,
        })

    if not recruiter_email:
        recommendations.append(
            "Request the recruiter's official company email address."
        )

    if not company_website:
        recommendations.append(
            "Find and verify the company's official website "
            "independently."
        )

    if not factors:
        factors.append({
            "type": "information",
            "severity": "neutral",
            "label": "Insufficient domain information",
            "evidence": (
                "A recruiter email and company website were not "
                "both supplied."
            ),
            "points": 0,
        })

    if risk_points >= 28:
        status = "high_concern"
    elif risk_points >= 18:
        status = "verification_required"
    elif email_domain and website_domain:
        status = "consistent"
    else:
        status = "insufficient_information"

    unique_recommendations = list(dict.fromkeys(recommendations))

    return {
        "recruiter_email": normalized_email,
        "company_website": normalized_website,
        "recruiter_email_domain": email_domain,
        "company_website_domain": website_domain,
        "domain_match": domain_match,
        "domain_status": status,
        "domain_risk_points": min(risk_points, 100),
        "email_is_free_provider": email_is_free,
        "email_is_disposable_provider": email_is_disposable,
        "company_brand_consistent": brand_consistent,
        "factors": factors,
        "recommendations": unique_recommendations,
        "disclaimer": (
            "Domain consistency is only one verification signal. "
            "A matching domain does not prove that a company, "
            "recruiter or internship is legitimate."
        ),
    }