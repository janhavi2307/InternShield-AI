"""Explainable comparison helpers for saved internship assessments."""

from __future__ import annotations

from typing import Any


STATUS_RANK = {
    "appears_reasonable": 3,
    "verification_required": 2,
    "potentially_suspicious": 1,
}

COMPATIBILITY_RANK = {
    "manageable": 3,
    "demanding": 2,
    "conflict_risk": 1,
}


def _number(value: Any, default: float = 0) -> float:
    """Convert Supabase numeric values safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metric_winner(
    first_value: float,
    second_value: float,
    higher_is_better: bool = True,
) -> str:
    """Return first, second or tie for a numeric metric."""
    if first_value == second_value:
        return "tie"

    first_wins = (
        first_value > second_value
        if higher_is_better
        else first_value < second_value
    )

    return "first" if first_wins else "second"


def _overall_score(record: dict[str, Any]) -> float:
    """
    Create a transparent comparison score.

    This is a decision-support score only. It is not a legitimacy
    score and it does not independently verify an organization.
    """
    verification = _number(
        record.get("verification_score")
    )

    value = _number(
        record.get("value_score")
    )

    compatibility = _number(
        record.get("compatibility_score")
    )

    assessment_status = STATUS_RANK.get(
        record.get("assessment_status"),
        1,
    )

    compatibility_status = COMPATIBILITY_RANK.get(
        record.get("compatibility_status"),
        1,
    )

    status_component = (
        assessment_status / 3
    ) * 10

    compatibility_status_component = (
        compatibility_status / 3
    ) * 5

    score = (
        verification * 0.40
        + value * 0.25
        + compatibility * 0.20
        + status_component
        + compatibility_status_component
    )

    return round(
        min(
            max(score, 0),
            100,
        ),
        1,
    )


def _display_name(
    record: dict[str, Any],
) -> str:
    company = (
        record.get("company_name")
        or "Company not provided"
    )

    role = (
        record.get("role_title")
        or "Internship opportunity"
    )

    return f"{company} — {role}"


def _winner_name(
    winner: str,
    first: dict[str, Any],
    second: dict[str, Any],
) -> str:
    if winner == "first":
        return _display_name(first)

    if winner == "second":
        return _display_name(second)

    return "Tie"


def _metric_highlight(
    *,
    key: str,
    label: str,
    metric: dict[str, Any],
    first: dict[str, Any],
    second: dict[str, Any],
    display_first: str,
    display_second: str,
    detail: str,
) -> dict[str, Any]:
    winner = metric["winner"]

    if winner == "first":
        display_value = display_first
    elif winner == "second":
        display_value = display_second
    else:
        display_value = display_first

    return {
        "key": key,
        "label": label,
        "winner": winner,
        "winner_name": _winner_name(
            winner,
            first,
            second,
        ),
        "display_value": display_value,
        "detail": detail,
    }


def compare_internships(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two saved internship assessments and return an
    explainable recommendation plus detailed metric winners.
    """
    if not first or not second:
        raise ValueError(
            "Two internship assessments are required."
        )

    if first.get("id") == second.get("id"):
        raise ValueError(
            "Select two different internship assessments."
        )

    first_verification = _number(
        first.get("verification_score")
    )

    second_verification = _number(
        second.get("verification_score")
    )

    first_value = _number(
        first.get("value_score")
    )

    second_value = _number(
        second.get("value_score")
    )

    first_compatibility = _number(
        first.get("compatibility_score")
    )

    second_compatibility = _number(
        second.get("compatibility_score")
    )

    first_monthly = _number(
        first.get("stipend_monthly")
    )

    second_monthly = _number(
        second.get("stipend_monthly")
    )

    first_hourly = _number(
        first.get("effective_hourly_stipend")
    )

    second_hourly = _number(
        second.get("effective_hourly_stipend")
    )

    first_workload = _number(
        first.get("weekly_workload")
    )

    second_workload = _number(
        second.get("weekly_workload")
    )

    first_flags = (
        first.get("detected_flags")
        or []
    )

    second_flags = (
        second.get("detected_flags")
        or []
    )

    metrics = {
        "verification": {
            "first": first_verification,
            "second": second_verification,
            "winner": _metric_winner(
                first_verification,
                second_verification,
            ),
        },
        "value": {
            "first": first_value,
            "second": second_value,
            "winner": _metric_winner(
                first_value,
                second_value,
            ),
        },
        "compatibility": {
            "first": first_compatibility,
            "second": second_compatibility,
            "winner": _metric_winner(
                first_compatibility,
                second_compatibility,
            ),
        },
        "monthly_stipend": {
            "first": first_monthly,
            "second": second_monthly,
            "winner": _metric_winner(
                first_monthly,
                second_monthly,
            ),
        },
        "hourly_stipend": {
            "first": first_hourly,
            "second": second_hourly,
            "winner": _metric_winner(
                first_hourly,
                second_hourly,
            ),
        },
        "weekly_workload": {
            "first": first_workload,
            "second": second_workload,
            "winner": _metric_winner(
                first_workload,
                second_workload,
                higher_is_better=False,
            ),
        },
        "warning_indicators": {
            "first": len(first_flags),
            "second": len(second_flags),
            "winner": _metric_winner(
                len(first_flags),
                len(second_flags),
                higher_is_better=False,
            ),
        },
    }

    first_score = _overall_score(first)
    second_score = _overall_score(second)

    overall_winner = _metric_winner(
        first_score,
        second_score,
    )

    reason_labels = {
        "verification": "stronger verification signals",
        "value": "higher opportunity value",
        "compatibility": "better academic compatibility",
        "monthly_stipend": "higher monthly stipend",
        "hourly_stipend": "better effective hourly compensation",
        "weekly_workload": "lower weekly workload",
        "warning_indicators": "fewer warning indicators",
    }

    reasons: list[str] = []
    tradeoffs: list[str] = []

    if overall_winner != "tie":
        other_side = (
            "second"
            if overall_winner == "first"
            else "first"
        )

        for key, metric in metrics.items():
            if metric["winner"] == overall_winner:
                reasons.append(
                    reason_labels[key]
                )

            elif metric["winner"] == other_side:
                tradeoffs.append(
                    reason_labels[key]
                )

    if overall_winner == "tie":
        summary = (
            "The two internships are closely matched on the "
            "overall comparison score. Review the category "
            "leaders and detailed metrics before deciding."
        )

        recommendation = {
            "title": "No single best fit",
            "subtitle": (
                "Both opportunities currently have the same "
                "overall decision-support score."
            ),
            "winner": "tie",
            "winner_name": "Tie",
            "reasons": [],
            "tradeoffs": [],
        }

    else:
        chosen = (
            first
            if overall_winner == "first"
            else second
        )

        chosen_name = _display_name(
            chosen
        )

        strongest_reasons = reasons[:4]

        reason_text = ", ".join(
            strongest_reasons[:3]
        )

        summary = (
            f"{chosen_name} is the stronger overall fit"
            + (
                f" because it currently has {reason_text}."
                if reason_text
                else "."
            )
        )

        recommendation = {
            "title": f"Best fit: {chosen_name}",
            "subtitle": (
                "This recommendation balances verification, "
                "opportunity value and academic compatibility "
                "instead of choosing only by stipend."
            ),
            "winner": overall_winner,
            "winner_name": chosen_name,
            "reasons": strongest_reasons,
            "tradeoffs": tradeoffs[:3],
        }

    score_gap = abs(
        first_score - second_score
    )

    if overall_winner == "tie":
        recommendation_strength = "Closely matched"
    elif score_gap >= 10:
        recommendation_strength = "Clearer fit"
    elif score_gap >= 4:
        recommendation_strength = "Moderate advantage"
    else:
        recommendation_strength = "Close decision"

    highlights = [
        _metric_highlight(
            key="verification",
            label="Strongest verification",
            metric=metrics["verification"],
            first=first,
            second=second,
            display_first=(
                f"{first_verification:.0f}/100"
            ),
            display_second=(
                f"{second_verification:.0f}/100"
            ),
            detail=(
                "Higher verification score based on the "
                "submitted evidence and verification checks."
            ),
        ),
        _metric_highlight(
            key="monthly_stipend",
            label="Best compensation",
            metric=metrics["monthly_stipend"],
            first=first,
            second=second,
            display_first=(
                f"₹{first_monthly:,.0f}/month"
            ),
            display_second=(
                f"₹{second_monthly:,.0f}/month"
            ),
            detail=(
                "Higher stated monthly stipend."
            ),
        ),
        _metric_highlight(
            key="compatibility",
            label="Best compatibility",
            metric=metrics["compatibility"],
            first=first,
            second=second,
            display_first=(
                f"{first_compatibility:.0f}/100"
            ),
            display_second=(
                f"{second_compatibility:.0f}/100"
            ),
            detail=(
                "Better alignment with the student's "
                "available academic schedule."
            ),
        ),
        _metric_highlight(
            key="weekly_workload",
            label="Lowest workload",
            metric=metrics["weekly_workload"],
            first=first,
            second=second,
            display_first=(
                f"{first_workload:.1f} hrs/week"
            ),
            display_second=(
                f"{second_workload:.1f} hrs/week"
            ),
            detail=(
                "Lower estimated weekly time commitment."
            ),
        ),
        _metric_highlight(
            key="hourly_stipend",
            label="Best hourly value",
            metric=metrics["hourly_stipend"],
            first=first,
            second=second,
            display_first=(
                f"₹{first_hourly:,.2f}/hr"
            ),
            display_second=(
                f"₹{second_hourly:,.2f}/hr"
            ),
            detail=(
                "Higher effective hourly stipend after "
                "considering the workload."
            ),
        ),
    ]

    return {
        "first_score": first_score,
        "second_score": second_score,
        "score_gap": round(
            score_gap,
            1,
        ),
        "overall_winner": overall_winner,
        "recommendation_strength": (
            recommendation_strength
        ),
        "metrics": metrics,
        "highlights": highlights,
        "recommendation": recommendation,
        "summary": summary,
        "disclaimer": (
            "The comparison score helps organize submitted "
            "evidence. It does not prove that either internship "
            "is legitimate and should not replace independent "
            "verification of the organization and written terms."
        ),
    }