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
    if first_value == second_value:
        return "tie"

    first_wins = (
        first_value > second_value
        if higher_is_better
        else first_value < second_value
    )
    return "first" if first_wins else "second"


def _overall_score(record: dict[str, Any]) -> float:
    """Create a transparent comparison score, not a legitimacy score."""
    verification = _number(record.get("verification_score"))
    value = _number(record.get("value_score"))
    compatibility = _number(record.get("compatibility_score"))

    assessment_status = STATUS_RANK.get(
        record.get("assessment_status"),
        1,
    )
    compatibility_status = COMPATIBILITY_RANK.get(
        record.get("compatibility_status"),
        1,
    )

    status_component = (assessment_status / 3) * 10
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
    return round(min(max(score, 0), 100), 1)


def compare_internships(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """Compare two assessments and return explainable results."""
    if not first or not second:
        raise ValueError("Two internship assessments are required.")

    if first.get("id") == second.get("id"):
        raise ValueError("Select two different internship assessments.")

    first_verification = _number(first.get("verification_score"))
    second_verification = _number(second.get("verification_score"))
    first_value = _number(first.get("value_score"))
    second_value = _number(second.get("value_score"))
    first_compatibility = _number(
        first.get("compatibility_score")
    )
    second_compatibility = _number(
        second.get("compatibility_score")
    )
    first_hourly = _number(
        first.get("effective_hourly_stipend")
    )
    second_hourly = _number(
        second.get("effective_hourly_stipend")
    )

    first_flags = first.get("detected_flags") or []
    second_flags = second.get("detected_flags") or []

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
        "hourly_stipend": {
            "first": first_hourly,
            "second": second_hourly,
            "winner": _metric_winner(
                first_hourly,
                second_hourly,
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

    reasons: list[str] = []
    labels = {
        "verification": "higher verification score",
        "value": "higher opportunity value",
        "compatibility": "better academic compatibility",
        "hourly_stipend": "higher effective hourly stipend",
        "warning_indicators": "fewer warning indicators",
    }

    for key, metric in metrics.items():
        if metric["winner"] == overall_winner:
            reasons.append(labels[key])

    if overall_winner == "tie":
        summary = (
            "The two internships have the same overall comparison "
            "score. Review the detailed differences before deciding."
        )
    else:
        chosen = first if overall_winner == "first" else second
        chosen_name = (
            chosen.get("role_title")
            or chosen.get("company_name")
            or "The selected internship"
        )
        reason_text = ", ".join(reasons[:3])
        summary = (
            f"{chosen_name} is the stronger overall fit in this "
            f"comparison"
            + (f" because it has {reason_text}." if reason_text else ".")
        )

    return {
        "first_score": first_score,
        "second_score": second_score,
        "overall_winner": overall_winner,
        "metrics": metrics,
        "summary": summary,
        "disclaimer": (
            "The comparison score helps organize submitted evidence. "
            "It does not prove that either internship is legitimate "
            "and should not replace independent verification."
        ),
    }
