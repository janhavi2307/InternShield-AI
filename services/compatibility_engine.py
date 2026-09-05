from typing import Optional


VALID_WORK_MODES = {
    "remote",
    "hybrid",
    "onsite",
    "no_preference",
    "not_specified",
}


def _normalize_work_mode(
    value: Optional[str],
    default: str,
) -> str:
    """
    Normalize work-mode values coming from profile/form data.
    """

    cleaned = (
        value
        or default
    ).strip().lower()

    aliases = {
        "on-site": "onsite",
        "on_site": "onsite",
        "office": "onsite",
        "wfo": "onsite",
        "work_from_office": "onsite",
        "work-from-office": "onsite",
        "wfh": "remote",
        "work_from_home": "remote",
        "work-from-home": "remote",
        "none": "no_preference",
    }

    cleaned = aliases.get(
        cleaned,
        cleaned,
    )

    if cleaned not in VALID_WORK_MODES:
        return default

    return cleaned


def calculate_compatibility(
    hours_per_day: Optional[float],
    days_per_week: Optional[int],
    available_hours_per_week: Optional[float],
    schedule_type: str,
    exam_period: bool,
    class_schedule_conflict: bool,
    internship_work_mode: str = "not_specified",
    preferred_work_mode: str = "no_preference",
) -> dict:
    """
    Calculate academic/workload compatibility.

    Work-mode preference is intentionally a smaller signal than
    direct schedule conflicts, exam overlap, or excessive workload.

    Returns a transparent compatibility score plus reasons.
    """

    compatibility_score = 100
    compatibility_reasons = []

    weekly_workload = None

    # ---------------------------------------------------------
    # WEEKLY WORKLOAD
    # ---------------------------------------------------------

    if (
        hours_per_day is not None
        and days_per_week is not None
    ):
        weekly_workload = round(
            hours_per_day * days_per_week,
            1,
        )

    else:
        compatibility_score -= 25

        compatibility_reasons.append(
            "Working hours or working days were not fully "
            "specified, so the weekly workload could not be "
            "calculated."
        )

    # ---------------------------------------------------------
    # STUDENT AVAILABILITY
    # ---------------------------------------------------------

    if available_hours_per_week is None:
        compatibility_score -= 20

        compatibility_reasons.append(
            "The student's available weekly hours were not "
            "provided."
        )

    elif weekly_workload is not None:

        if weekly_workload > available_hours_per_week:
            compatibility_score -= 40

            extra_hours = round(
                weekly_workload
                - available_hours_per_week,
                1,
            )

            compatibility_reasons.append(
                f"The internship requires {extra_hours} more "
                "hours per week than the student has available."
            )

        elif available_hours_per_week > 0:

            workload_ratio = (
                weekly_workload
                / available_hours_per_week
            )

            if workload_ratio >= 0.8:
                compatibility_score -= 20

                compatibility_reasons.append(
                    "The internship would consume at least 80% "
                    "of the student's available weekly time."
                )

            elif workload_ratio >= 0.6:
                compatibility_score -= 10

                compatibility_reasons.append(
                    "The internship would consume a significant "
                    "portion of the student's available time."
                )

            else:
                compatibility_reasons.append(
                    "The weekly workload fits within the "
                    "student's stated available hours."
                )

    # ---------------------------------------------------------
    # INTERNSHIP SCHEDULE TYPE
    # ---------------------------------------------------------

    if schedule_type == "fixed":
        compatibility_score -= 10

        compatibility_reasons.append(
            "Fixed working hours may provide less flexibility "
            "around lectures and college activities."
        )

    elif schedule_type == "not_specified":
        compatibility_score -= 5

        compatibility_reasons.append(
            "The internship schedule type was not specified."
        )

    elif schedule_type == "flexible":
        compatibility_reasons.append(
            "Flexible working hours may be easier to manage "
            "alongside college."
        )

    # ---------------------------------------------------------
    # WORK-MODE COMPATIBILITY
    # ---------------------------------------------------------

    normalized_internship_mode = _normalize_work_mode(
        internship_work_mode,
        "not_specified",
    )

    normalized_preferred_mode = _normalize_work_mode(
        preferred_work_mode,
        "no_preference",
    )

    work_mode_match = None
    work_mode_adjustment = 0

    if normalized_internship_mode == "not_specified":
        compatibility_score -= 3
        work_mode_adjustment = -3

        compatibility_reasons.append(
            "The internship work mode was not specified, so "
            "work-mode preference could not be fully evaluated."
        )

    elif normalized_preferred_mode == "no_preference":
        work_mode_match = None

        compatibility_reasons.append(
            "No preferred work mode is set in the student's "
            "profile, so the internship work mode does not "
            "affect compatibility."
        )

    elif (
        normalized_internship_mode
        == normalized_preferred_mode
    ):
        work_mode_match = True

        compatibility_reasons.append(
            "The internship work mode matches the student's "
            "saved preference."
        )

    else:
        work_mode_match = False

        # A direct Remote <-> On-site mismatch is stronger.
        direct_mismatch = {
            normalized_internship_mode,
            normalized_preferred_mode,
        } == {
            "remote",
            "onsite",
        }

        if direct_mismatch:
            compatibility_score -= 12
            work_mode_adjustment = -12

            compatibility_reasons.append(
                "The internship work mode does not match the "
                "student's saved preference and represents a "
                "significant work-mode difference."
            )

        else:
            compatibility_score -= 7
            work_mode_adjustment = -7

            compatibility_reasons.append(
                "The internship work mode differs from the "
                "student's saved preference."
            )

    # ---------------------------------------------------------
    # EXAM / CLASS CONFLICTS
    # ---------------------------------------------------------

    if exam_period:
        compatibility_score -= 20

        compatibility_reasons.append(
            "The internship overlaps with an examination or "
            "major academic-assessment period."
        )

    if class_schedule_conflict:
        compatibility_score -= 40

        compatibility_reasons.append(
            "The internship timings directly conflict with "
            "the student's lecture or practical schedule."
        )

    # ---------------------------------------------------------
    # FINAL SCORE + STATUS
    # ---------------------------------------------------------

    compatibility_score = max(
        0,
        min(
            100,
            compatibility_score,
        ),
    )

    if compatibility_score >= 75:
        compatibility_status = "manageable"

    elif compatibility_score >= 45:
        compatibility_status = "demanding"

    else:
        compatibility_status = "conflict_risk"

    if not compatibility_reasons:
        compatibility_reasons.append(
            "No major academic scheduling conflict was reported."
        )

    return {
        "weekly_workload": weekly_workload,

        "compatibility_score": (
            compatibility_score
        ),

        "compatibility_status": (
            compatibility_status
        ),

        "compatibility_reasons": (
            compatibility_reasons
        ),

        "internship_work_mode": (
            normalized_internship_mode
        ),

        "preferred_work_mode": (
            normalized_preferred_mode
        ),

        "work_mode_match": (
            work_mode_match
        ),

        "work_mode_adjustment": (
            work_mode_adjustment
        ),
    }
