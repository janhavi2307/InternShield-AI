

from __future__ import annotations

from typing import Any, Optional


DETAILED_TEXT_MIN_CHARS = 120

EVIDENCE_LEVELS = {
    "high": {
        "minimum": 75,
        "label": "High",
    },
    "moderate": {
        "minimum": 45,
        "label": "Moderate",
    },
    "limited": {
        "minimum": 0,
        "label": "Limited",
    },
}


def _clean_text(
    value: Optional[str],
) -> str:
    return (
        value
        or ""
    ).strip()


def _factor(
    *,
    key: str,
    label: str,
    points: int,
    max_points: int,
    detail: str,
) -> dict[str, Any]:
    if points >= max_points:
        status = "complete"
    elif points > 0:
        status = "partial"
    else:
        status = "missing"

    return {
        "key": key,
        "label": label,
        "points": points,
        "max_points": max_points,
        "status": status,
        "detail": detail,
    }


def calculate_evidence_quality(
    *,
    text: Optional[str],
    recruiter_email: Optional[str],
    company_website: Optional[str],
    stipend_monthly: Optional[float],
    hours_per_day: Optional[float],
    days_per_week: Optional[int],
    input_type: str,
    available_hours_per_week: Optional[float],
    schedule_type: str,
) -> dict[str, Any]:
    """
    Measure how complete the submitted evidence is.

    This is NOT a legitimacy or fraud-confidence score.
    It only measures how much structured information was
    available for InternShield to assess.

    Scoring:
        Detailed internship text ............... 25
        Recruiter email ........................ 15
        Company website ........................ 15
        Compensation details ................... 10
        Workload details ....................... 10
        PDF/image supporting evidence .......... 15
        Academic availability/schedule ......... 10
                                                ---
                                                100
    """

    factors: list[dict[str, Any]] = []

    cleaned_text = _clean_text(
        text
    )

    cleaned_recruiter_email = _clean_text(
        recruiter_email
    )

    cleaned_company_website = _clean_text(
        company_website
    )

    normalized_input_type = (
        input_type
        or "text"
    ).strip().lower()

    normalized_schedule_type = (
        schedule_type
        or "not_specified"
    ).strip().lower()

    # ---------------------------------------------------------
    # 1. DETAILED INTERNSHIP TEXT — 25
    # ---------------------------------------------------------

    has_detailed_text = (
        len(cleaned_text)
        >= DETAILED_TEXT_MIN_CHARS
    )

    factors.append(
        _factor(
            key="detailed_text",
            label="Detailed internship description",
            points=25 if has_detailed_text else 0,
            max_points=25,
            detail=(
                "The submitted or extracted internship text "
                f"contains at least {DETAILED_TEXT_MIN_CHARS} "
                "characters."
                if has_detailed_text
                else (
                    "Add a more detailed internship description "
                    f"of at least {DETAILED_TEXT_MIN_CHARS} "
                    "characters so responsibilities and terms "
                    "can be assessed more completely."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 2. RECRUITER EMAIL — 15
    # ---------------------------------------------------------

    has_recruiter_email = bool(
        cleaned_recruiter_email
    )

    factors.append(
        _factor(
            key="recruiter_email",
            label="Recruiter email supplied",
            points=15 if has_recruiter_email else 0,
            max_points=15,
            detail=(
                "A recruiter email was supplied for identity "
                "and domain-related checks."
                if has_recruiter_email
                else (
                    "No recruiter email was supplied, so email "
                    "domain verification is more limited."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 3. COMPANY WEBSITE — 15
    # ---------------------------------------------------------

    has_company_website = bool(
        cleaned_company_website
    )

    factors.append(
        _factor(
            key="company_website",
            label="Company website supplied",
            points=15 if has_company_website else 0,
            max_points=15,
            detail=(
                "A company website was supplied for domain and "
                "technical website checks."
                if has_company_website
                else (
                    "No company website was supplied, so website "
                    "and cross-domain checks are more limited."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 4. COMPENSATION DETAILS — 10
    # ---------------------------------------------------------

    has_compensation = (
        stipend_monthly is not None
    )

    factors.append(
        _factor(
            key="compensation",
            label="Compensation details supplied",
            points=10 if has_compensation else 0,
            max_points=10,
            detail=(
                "Monthly stipend information is available for "
                "opportunity-value calculations."
                if has_compensation
                else (
                    "No monthly stipend was available, so "
                    "compensation analysis is less complete."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 5. WORKLOAD DETAILS — 10
    # ---------------------------------------------------------

    has_workload = (
        hours_per_day is not None
        and days_per_week is not None
    )

    factors.append(
        _factor(
            key="workload",
            label="Workload details supplied",
            points=10 if has_workload else 0,
            max_points=10,
            detail=(
                "Hours per day and days per week are available "
                "for workload calculations."
                if has_workload
                else (
                    "Both hours per day and days per week are "
                    "needed for a complete workload estimate."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 6. PDF OR IMAGE SUPPORTING EVIDENCE — 15
    # ---------------------------------------------------------

    has_attachment = (
        normalized_input_type
        in {
            "pdf",
            "image",
        }
    )

    factors.append(
        _factor(
            key="supporting_file",
            label="Supporting PDF or image supplied",
            points=15 if has_attachment else 0,
            max_points=15,
            detail=(
                "A PDF or image was supplied as supporting "
                "internship evidence."
                if has_attachment
                else (
                    "No supporting PDF or screenshot was "
                    "uploaded. Text-only assessments can still "
                    "be useful, but supporting evidence improves "
                    "completeness."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # 7. ACADEMIC AVAILABILITY / SCHEDULE — 10
    # ---------------------------------------------------------

    has_academic_context = (
        available_hours_per_week is not None
        and normalized_schedule_type
        in {
            "flexible",
            "fixed",
        }
    )

    factors.append(
        _factor(
            key="academic_context",
            label="Academic availability and schedule supplied",
            points=10 if has_academic_context else 0,
            max_points=10,
            detail=(
                "Weekly availability and internship schedule "
                "type are available for compatibility analysis."
                if has_academic_context
                else (
                    "Weekly availability and a specified "
                    "internship schedule are both needed for the "
                    "most complete academic-compatibility review."
                )
            ),
        )
    )

    # ---------------------------------------------------------
    # TOTAL + LEVEL
    # ---------------------------------------------------------

    score = sum(
        factor["points"]
        for factor in factors
    )

    if score >= 75:
        level = "high"

        summary = (
            "InternShield received enough structured information "
            "to perform a more complete assessment across several "
            "verification, value and compatibility checks."
        )

    elif score >= 45:
        level = "moderate"

        summary = (
            "InternShield received a useful amount of information, "
            "but some evidence or structured details are missing. "
            "Adding the missing items can make the assessment more "
            "complete."
        )

    else:
        level = "limited"

        summary = (
            "The assessment is based on limited submitted evidence. "
            "Add more internship details, identity information, "
            "workload or supporting documents before relying heavily "
            "on the result."
        )

    complete_count = sum(
        factor["status"] == "complete"
        for factor in factors
    )

    missing_count = sum(
        factor["status"] == "missing"
        for factor in factors
    )

    return {
        "score": score,
        "level": level,
        "level_label": (
            EVIDENCE_LEVELS[
                level
            ]["label"]
        ),
        "factors": factors,
        "summary": summary,
        "complete_count": complete_count,
        "missing_count": missing_count,
        "disclaimer": (
            "Evidence Quality measures completeness of the "
            "information submitted to InternShield. It does not "
            "prove that an internship, recruiter or company is "
            "legitimate."
        ),
    }
