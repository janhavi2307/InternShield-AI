import re
from urllib.parse import urlparse


# =========================================================
# BASIC HELPERS
# =========================================================

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "protonmail.com",
    "rediffmail.com",
}


def _normalize(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def _safe_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _domain_from_email(email):
    email = _normalize(email)

    if "@" not in email:
        return None

    return email.rsplit("@", 1)[-1]


def _domain_from_url(url):
    if not url:
        return None

    value = str(url).strip()

    if not value:
        return None

    if not value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        value = "https://" + value

    try:
        domain = (
            urlparse(value)
            .netloc
            .lower()
            .split(":")[0]
        )

        if domain.startswith("www."):
            domain = domain[4:]

        return domain or None

    except Exception:
        return None


# =========================================================
# TEXT EXTRACTION HELPERS
# =========================================================

def _extract_money_values(text):
    """
    Extract likely INR amounts from text.
    """

    patterns = [
        r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*(?:₹|rs\.?|inr)",
    ]

    values = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            try:
                value = float(
                    str(match).replace(
                        ",",
                        "",
                    )
                )

                values.append(value)

            except ValueError:
                continue

    return values


def _extract_stipend(text):
    """
    Find a stipend/salary amount located near stipend,
    salary, compensation or pay wording.
    """

    text_lower = _normalize(text)

    patterns = [
        (
            r"(?:monthly\s+)?"
            r"(?:stipend|salary|compensation|pay)"
            r"\s*(?:is|of|:|-)?\s*"
            r"(?:₹|rs\.?|inr)?\s*"
            r"([\d,]+(?:\.\d+)?)"
        ),
        (
            r"(?:₹|rs\.?|inr)\s*"
            r"([\d,]+(?:\.\d+)?)"
            r"\s*(?:per\s+month|monthly|/month)"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text_lower,
            flags=re.IGNORECASE,
        )

        if match:
            try:
                return float(
                    match.group(1).replace(
                        ",",
                        "",
                    )
                )
            except ValueError:
                pass

    return None


def _extract_weekly_hours(text):
    """
    Extract workload in hours/week.

    Supports:
    - 25 hours/week
    - 25 hrs per week
    - 5 hours/day, 5 days/week
    """

    text_lower = _normalize(text)

    weekly_patterns = [
        r"(\d+(?:\.\d+)?)\s*hours?\s*/\s*week",
        r"(\d+(?:\.\d+)?)\s*hours?\s+per\s+week",
        r"(\d+(?:\.\d+)?)\s*hrs?\s*/\s*week",
        r"(\d+(?:\.\d+)?)\s*hrs?\s+per\s+week",
    ]

    for pattern in weekly_patterns:
        match = re.search(
            pattern,
            text_lower,
        )

        if match:
            return _safe_float(
                match.group(1)
            )

    hours_per_day = None
    days_per_week = None

    daily_match = re.search(
        (
            r"(\d+(?:\.\d+)?)\s*"
            r"(?:hours?|hrs?)\s*"
            r"(?:/|per)\s*day"
        ),
        text_lower,
    )

    if daily_match:
        hours_per_day = _safe_float(
            daily_match.group(1)
        )

    days_match = re.search(
        (
            r"(\d+)\s*days?\s*"
            r"(?:/|per)\s*week"
        ),
        text_lower,
    )

    if days_match:
        days_per_week = _safe_float(
            days_match.group(1)
        )

    if (
        hours_per_day is not None
        and days_per_week is not None
    ):
        return round(
            hours_per_day
            * days_per_week,
            2,
        )

    return None


def _extract_duration_months(text):
    text_lower = _normalize(text)

    month_match = re.search(
        r"(\d+(?:\.\d+)?)\s*months?",
        text_lower,
    )

    if month_match:
        return _safe_float(
            month_match.group(1)
        )

    week_match = re.search(
        r"(\d+(?:\.\d+)?)\s*weeks?",
        text_lower,
    )

    if week_match:
        weeks = _safe_float(
            week_match.group(1)
        )

        if weeks is not None:
            return round(
                weeks / 4.33,
                2,
            )

    return None


def _extract_work_mode(text):
    text_lower = _normalize(text)

    if re.search(
        r"\bhybrid\b",
        text_lower,
    ):
        return "hybrid"

    if re.search(
        r"\b(remote|work\s+from\s+home|wfh)\b",
        text_lower,
    ):
        return "remote"

    if re.search(
        (
            r"\b(on[-\s]?site|onsite|"
            r"work\s+from\s+office|wfo|"
            r"in[-\s]?office)\b"
        ),
        text_lower,
    ):
        return "onsite"

    return None


def _extract_email(text):
    match = re.search(
        (
            r"\b[A-Z0-9._%+-]+"
            r"@[A-Z0-9.-]+"
            r"\.[A-Z]{2,}\b"
        ),
        str(text or ""),
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(0).lower()


def _detect_fee_request(text):
    """
    Detect newly introduced fees/deposits/payments.
    """

    text_lower = _normalize(text)

    fee_terms = [
        "registration fee",
        "verification fee",
        "onboarding fee",
        "training fee",
        "security deposit",
        "refundable deposit",
        "processing fee",
        "joining fee",
        "application fee",
        "documentation fee",
        "background verification fee",
    ]

    detected = []

    for term in fee_terms:
        if term in text_lower:
            detected.append(term)

    generic_payment_pattern = re.search(
        (
            r"(?:pay|payment|deposit|fee)"
            r".{0,40}"
            r"(?:₹|rs\.?|inr)"
            r"\s*[\d,]+"
        ),
        text_lower,
        flags=re.IGNORECASE,
    )

    if generic_payment_pattern:
        detected.append(
            generic_payment_pattern.group(0)
        )

    return list(
        dict.fromkeys(
            detected
        )
    )


def _detect_urgency(text):
    text_lower = _normalize(text)

    urgency_phrases = [
        "within 24 hours",
        "within 12 hours",
        "immediately",
        "urgent joining",
        "join immediately",
        "limited time",
        "today only",
        "respond immediately",
        "confirm immediately",
        "accept immediately",
        "final chance",
    ]

    detected = []

    for phrase in urgency_phrases:
        if phrase in text_lower:
            detected.append(phrase)

    return detected


# =========================================================
# ORIGINAL OPPORTUNITY EXTRACTION
# =========================================================

def _original_weekly_hours(analysis):
    weekly_workload = _safe_float(
        analysis.get(
            "weekly_workload"
        )
    )

    if weekly_workload is not None:
        return weekly_workload

    hours_per_day = _safe_float(
        analysis.get(
            "hours_per_day"
        )
    )

    days_per_week = _safe_float(
        analysis.get(
            "days_per_week"
        )
    )

    if (
        hours_per_day is not None
        and days_per_week is not None
    ):
        return round(
            hours_per_day
            * days_per_week,
            2,
        )

    return None


def _original_work_mode(analysis):
    schedule_type = _normalize(
        analysis.get(
            "work_mode"
        )
    )

    if schedule_type in {
        "remote",
        "hybrid",
        "onsite",
    }:
        return schedule_type

    return _extract_work_mode(
        analysis.get(
            "original_text"
        )
    )


# =========================================================
# CHANGE OBJECT
# =========================================================

def _change(
    field,
    status,
    severity,
    original,
    final,
    message,
    points=0,
):
    return {
        "field": field,
        "status": status,
        "severity": severity,
        "original": original,
        "final": final,
        "message": message,
        "points": points,
    }


# =========================================================
# MAIN OFFER CHANGE ENGINE
# =========================================================

def compare_offer_to_original(
    analysis,
    final_offer_text,
    final_recruiter_email=None,
):
    """
    Compare final offer evidence with the original
    internship assessment.

    Returns an explainable consistency/change report.
    """

    analysis = analysis or {}
    final_offer_text = str(
        final_offer_text
        or ""
    ).strip()

    if not final_offer_text:
        return {
            "change_score": 0,
            "change_status": (
                "Insufficient Information"
            ),
            "changes": [],
            "critical_changes": [],
            "warnings": [
                (
                    "No final offer text was supplied "
                    "for comparison."
                )
            ],
        }

    changes = []
    warnings = []
    critical_changes = []

    score = 100

    final_text_normalized = _normalize(
        final_offer_text
    )

    original_text = _normalize(
        analysis.get(
            "original_text"
        )
    )

    # =====================================================
    # COMPANY IDENTITY
    # =====================================================

    company = (
        analysis.get(
            "company_name"
        )
        or ""
    ).strip()

    if company:
        if _normalize(company) in final_text_normalized:
            changes.append(
                _change(
                    field="Company identity",
                    status="same",
                    severity="low",
                    original=company,
                    final=company,
                    message=(
                        "The final offer references the "
                        "same company name."
                    ),
                )
            )

        else:
            score -= 25

            item = _change(
                field="Company identity",
                status="changed",
                severity="high",
                original=company,
                final="Not confirmed",
                message=(
                    "The original company name could not "
                    "be confirmed in the final offer."
                ),
                points=-25,
            )

            changes.append(item)
            critical_changes.append(item)

    # =====================================================
    # ROLE TITLE
    # =====================================================

    role = (
        analysis.get(
            "role_title"
        )
        or ""
    ).strip()

    if role:
        if _normalize(role) in final_text_normalized:
            changes.append(
                _change(
                    field="Internship role",
                    status="same",
                    severity="low",
                    original=role,
                    final=role,
                    message=(
                        "The internship role appears "
                        "unchanged."
                    ),
                )
            )

        else:
            score -= 15

            changes.append(
                _change(
                    field="Internship role",
                    status="review",
                    severity="medium",
                    original=role,
                    final="Not confirmed",
                    message=(
                        "The original role title was not "
                        "clearly confirmed in the final "
                        "offer."
                    ),
                    points=-15,
                )
            )

    # =====================================================
    # STIPEND
    # =====================================================

    original_stipend = _safe_float(
        analysis.get(
            "stipend_monthly"
        )
    )

    final_stipend = _extract_stipend(
        final_offer_text
    )

    if (
        original_stipend is not None
        and final_stipend is not None
    ):
        change_percent = (
            (
                final_stipend
                - original_stipend
            )
            / original_stipend
            * 100
            if original_stipend > 0
            else 0
        )

        if abs(change_percent) < 5:
            changes.append(
                _change(
                    field="Monthly stipend",
                    status="same",
                    severity="low",
                    original=original_stipend,
                    final=final_stipend,
                    message=(
                        "The monthly stipend is "
                        "approximately unchanged."
                    ),
                )
            )

        elif change_percent < 0:
            deduction = (
                20
                if change_percent <= -20
                else 10
            )

            score -= deduction

            item = _change(
                field="Monthly stipend",
                status="changed",
                severity=(
                    "high"
                    if deduction >= 20
                    else "medium"
                ),
                original=original_stipend,
                final=final_stipend,
                message=(
                    "The final offer contains a lower "
                    "monthly stipend than the original "
                    "opportunity."
                ),
                points=-deduction,
            )

            changes.append(item)

            if deduction >= 20:
                critical_changes.append(item)

        else:
            changes.append(
                _change(
                    field="Monthly stipend",
                    status="improved",
                    severity="low",
                    original=original_stipend,
                    final=final_stipend,
                    message=(
                        "The final offer contains a higher "
                        "monthly stipend."
                    ),
                )
            )

    elif original_stipend is not None:
        warnings.append(
            "The final offer stipend could not be "
            "confidently extracted."
        )

    # =====================================================
    # WORKLOAD
    # =====================================================

    original_hours = _original_weekly_hours(
        analysis
    )

    final_hours = _extract_weekly_hours(
        final_offer_text
    )

    if (
        original_hours is not None
        and final_hours is not None
        and original_hours > 0
    ):
        workload_change = (
            (
                final_hours
                - original_hours
            )
            / original_hours
            * 100
        )

        if abs(workload_change) < 10:
            changes.append(
                _change(
                    field="Weekly workload",
                    status="same",
                    severity="low",
                    original=original_hours,
                    final=final_hours,
                    message=(
                        "The expected weekly workload is "
                        "approximately unchanged."
                    ),
                )
            )

        elif workload_change > 0:
            deduction = (
                15
                if workload_change >= 25
                else 8
            )

            score -= deduction

            changes.append(
                _change(
                    field="Weekly workload",
                    status="changed",
                    severity=(
                        "high"
                        if deduction >= 15
                        else "medium"
                    ),
                    original=original_hours,
                    final=final_hours,
                    message=(
                        "The final offer requires more "
                        "weekly working hours than the "
                        "original opportunity."
                    ),
                    points=-deduction,
                )
            )

        else:
            changes.append(
                _change(
                    field="Weekly workload",
                    status="improved",
                    severity="low",
                    original=original_hours,
                    final=final_hours,
                    message=(
                        "The final offer requires fewer "
                        "weekly working hours."
                    ),
                )
            )

    # =====================================================
    # DURATION
    # =====================================================

    original_duration = _safe_float(
        analysis.get(
            "duration_months"
        )
    )

    final_duration = _extract_duration_months(
        final_offer_text
    )

    if (
        original_duration is not None
        and final_duration is not None
    ):
        if abs(
            original_duration
            - final_duration
        ) <= 0.25:
            changes.append(
                _change(
                    field="Internship duration",
                    status="same",
                    severity="low",
                    original=original_duration,
                    final=final_duration,
                    message=(
                        "The internship duration appears "
                        "unchanged."
                    ),
                )
            )

        else:
            score -= 8

            changes.append(
                _change(
                    field="Internship duration",
                    status="changed",
                    severity="medium",
                    original=original_duration,
                    final=final_duration,
                    message=(
                        "The duration in the final offer "
                        "differs from the original "
                        "opportunity."
                    ),
                    points=-8,
                )
            )

    # =====================================================
    # WORK MODE
    # =====================================================

    original_mode = _original_work_mode(
        analysis
    )

    final_mode = _extract_work_mode(
        final_offer_text
    )

    if (
        original_mode
        and final_mode
    ):
        if original_mode == final_mode:
            changes.append(
                _change(
                    field="Work mode",
                    status="same",
                    severity="low",
                    original=original_mode.title(),
                    final=final_mode.title(),
                    message=(
                        "The work mode appears unchanged."
                    ),
                )
            )

        else:
            score -= 10

            changes.append(
                _change(
                    field="Work mode",
                    status="changed",
                    severity="medium",
                    original=original_mode.title(),
                    final=final_mode.title(),
                    message=(
                        "The final offer changes the "
                        "work mode."
                    ),
                    points=-10,
                )
            )

    # =====================================================
    # NEW PAYMENT / FEE REQUIREMENTS
    # =====================================================

    original_fees = _detect_fee_request(
        original_text
    )

    final_fees = _detect_fee_request(
        final_offer_text
    )

    newly_added_fees = [
        item
        for item in final_fees
        if item not in original_fees
    ]

    if newly_added_fees:
        score -= 25

        item = _change(
            field="Payment requirement",
            status="new_warning",
            severity="high",
            original=(
                ", ".join(original_fees)
                if original_fees
                else "No matching fee detected"
            ),
            final=", ".join(
                newly_added_fees
            ),
            message=(
                "A payment, fee or deposit appears in "
                "the final offer that was not detected "
                "in the original opportunity."
            ),
            points=-25,
        )

        changes.append(item)
        critical_changes.append(item)

    # =====================================================
    # NEW URGENCY
    # =====================================================

    original_urgency = _detect_urgency(
        original_text
    )

    final_urgency = _detect_urgency(
        final_offer_text
    )

    newly_added_urgency = [
        item
        for item in final_urgency
        if item not in original_urgency
    ]

    if newly_added_urgency:
        score -= 10

        changes.append(
            _change(
                field="Decision pressure",
                status="new_warning",
                severity="medium",
                original=(
                    ", ".join(original_urgency)
                    if original_urgency
                    else "No matching urgency detected"
                ),
                final=", ".join(
                    newly_added_urgency
                ),
                message=(
                    "The final offer introduces new "
                    "urgency or pressure language."
                ),
                points=-10,
            )
        )

    # =====================================================
    # RECRUITER EMAIL / DOMAIN
    # =====================================================

    original_email = (
        analysis.get(
            "recruiter_email"
        )
        or ""
    )

    final_email = (
        final_recruiter_email
        or _extract_email(
            final_offer_text
        )
    )

    original_domain = _domain_from_email(
        original_email
    )

    final_domain = _domain_from_email(
        final_email
    )

    if (
        original_domain
        and final_domain
    ):
        if original_domain == final_domain:
            changes.append(
                _change(
                    field="Recruiter email domain",
                    status="same",
                    severity="low",
                    original=original_domain,
                    final=final_domain,
                    message=(
                        "The recruiter email domain is "
                        "unchanged."
                    ),
                )
            )

        else:
            score -= 12

            changes.append(
                _change(
                    field="Recruiter email domain",
                    status="changed",
                    severity="medium",
                    original=original_domain,
                    final=final_domain,
                    message=(
                        "The recruiter email domain in "
                        "the final offer differs from "
                        "the original communication."
                    ),
                    points=-12,
                )
            )

    # Public email provider in final offer.
    if (
        final_domain
        and final_domain in FREE_EMAIL_DOMAINS
    ):
        existing_public_domain = (
            original_domain
            in FREE_EMAIL_DOMAINS
        )

        if not existing_public_domain:
            score -= 12

            changes.append(
                _change(
                    field="Recruiter email",
                    status="new_warning",
                    severity="medium",
                    original=(
                        original_domain
                        or "Unavailable"
                    ),
                    final=final_domain,
                    message=(
                        "The final offer uses a public "
                        "email provider for recruiter "
                        "communication."
                    ),
                    points=-12,
                )
            )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    high_severity_count = sum(
        1
        for item in changes
        if item.get(
            "severity"
        ) == "high"
        and item.get(
            "status"
        ) != "same"
    )

    medium_change_count = sum(
        1
        for item in changes
        if item.get(
            "severity"
        ) == "medium"
        and item.get(
            "status"
        )
        in {
            "changed",
            "review",
            "new_warning",
        }
    )

    if (
        score < 60
        or high_severity_count > 0
    ):
        change_status = (
            "Major Changes Detected"
        )

    elif (
        score < 85
        or medium_change_count > 0
        or warnings
    ):
        change_status = (
            "Review Changes"
        )

    else:
        change_status = (
            "Consistent With Original"
        )

    recommendations = []

    if critical_changes:
        recommendations.append(
            (
                "Do not accept the final offer until "
                "all high-severity changes have been "
                "independently verified."
            )
        )

    if newly_added_fees:
        recommendations.append(
            (
                "Do not make payments or deposits "
                "before independently verifying the "
                "company and written terms."
            )
        )

    if newly_added_urgency:
        recommendations.append(
            (
                "Do not allow urgency language to "
                "prevent independent verification."
            )
        )

    if not recommendations:
        recommendations.append(
            (
                "Read the final written offer carefully "
                "and confirm all important terms before "
                "accepting."
            )
        )

    return {
        "change_score": int(
            round(score)
        ),

        "change_status": change_status,

        "changes": changes,

        "critical_changes": (
            critical_changes
        ),

        "warnings": warnings,

        "recommendations": (
            recommendations
        ),

        "summary": {
            "company_name": company
            or None,

            "role_title": role
            or None,

            "original_stipend": (
                original_stipend
            ),

            "final_stipend": (
                final_stipend
            ),

            "original_weekly_hours": (
                original_hours
            ),

            "final_weekly_hours": (
                final_hours
            ),

            "original_duration_months": (
                original_duration
            ),

            "final_duration_months": (
                final_duration
            ),

            "original_work_mode": (
                original_mode
            ),

            "final_work_mode": (
                final_mode
            ),

            "original_recruiter_domain": (
                original_domain
            ),

            "final_recruiter_domain": (
                final_domain
            ),
        },

        "disclaimer": (
            "Offer Change Detection compares the "
            "information available in the original "
            "assessment with the submitted final offer. "
            "It does not independently prove that either "
            "document, recruiter or company is legitimate."
        ),
    }