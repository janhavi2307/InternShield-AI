from typing import Optional


def calculate_compatibility(
    hours_per_day: Optional[float],
    days_per_week: Optional[int],
    available_hours_per_week: Optional[float],
    schedule_type: str,
    exam_period: bool,
    class_schedule_conflict: bool,
) -> dict:
    compatibility_score = 100
    compatibility_reasons = []

    weekly_workload = None

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
                weekly_workload - available_hours_per_week,
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

    compatibility_score = max(
        0,
        min(100, compatibility_score),
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
        "compatibility_score": compatibility_score,
        "compatibility_status": compatibility_status,
        "compatibility_reasons": compatibility_reasons,
    }