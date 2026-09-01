"""Context-aware InternShield Assistant with optional Gemini enhancement.

The rule-based reply is always produced first and remains the fallback.
Gemini only improves wording using already-saved InternShield context.
"""

from __future__ import annotations

import re
from typing import Any

from services.gemini_service import generate_grounded_assistant_response

STATUS_LABELS = {
    "saved": "Saved",
    "applied": "Applied",
    "interview": "Interview",
    "offer": "Offer",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}
ASSESSMENT_LABELS = {
    "appears_reasonable": "Appears Reasonable",
    "verification_required": "Verification Required",
    "potentially_suspicious": "Potentially Suspicious",
}
COMPATIBILITY_LABELS = {
    "manageable": "Manageable",
    "demanding": "Demanding",
    "conflict_risk": "Conflict Risk",
}


def _text(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def _score(value: Any) -> str:
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return "N/A"


def _status_label(value: Any) -> str:
    raw = _text(value, "").lower()
    if raw in STATUS_LABELS:
        return STATUS_LABELS[raw]
    if raw in ASSESSMENT_LABELS:
        return ASSESSMENT_LABELS[raw]
    if raw in COMPATIBILITY_LABELS:
        return COMPATIBILITY_LABELS[raw]
    return raw.replace("_", " ").title() if raw else "Not available"


def _company_role(item: dict[str, Any]) -> str:
    return f"{_text(item.get('role_title'), 'Internship')} at {_text(item.get('company_name'), 'Unknown company')}"


def _flag_title(flag: Any) -> str:
    if isinstance(flag, dict):
        return _text(
            flag.get("title")
            or flag.get("name")
            or flag.get("label")
            or flag.get("matched_phrase"),
            "Warning indicator",
        )
    return _text(flag, "Warning indicator")


def _flag_severity(flag: Any) -> str:
    if isinstance(flag, dict):
        value = _text(flag.get("severity"), "")
        return value.title() if value else ""
    return ""


def _recommendation_text(item: Any) -> str:
    if isinstance(item, dict):
        return _text(
            item.get("text")
            or item.get("recommendation")
            or item.get("message")
            or item.get("title"),
            "",
        )
    return _text(item, "")


def _find_named(message: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    lower = message.lower()
    for item in records:
        company = _text(item.get("company_name"), "")
        role = _text(item.get("role_title"), "")
        if company and company.lower() in lower:
            return item
        if role and len(role) >= 5 and role.lower() in lower:
            return item
    return None



def _assessment_summary(
    analysis: dict[str, Any],
) -> str:
    title = _company_role(analysis)

    lines = [
        f"Here is the saved InternShield assessment for {title}:",
        "",
        f"• Assessment: {_status_label(analysis.get('assessment_status'))}",
        f"• Verification score: {_score(analysis.get('verification_score'))}/100",
        f"• Value score: {_score(analysis.get('value_score'))}/100",
        f"• Academic compatibility: {_score(analysis.get('compatibility_score'))}/100",
        f"• Evidence consistency: {_score(analysis.get('consistency_score'))}/100",
    ]

    concerns: list[str] = []
    positive_signals: list[str] = []

    domain = analysis.get("domain_verification") or {}
    domain_status = _text(domain.get("domain_status"), "").lower()

    if domain_status == "high_concern":
        concerns.append(
            "Recruiter/company domain verification contains a high-concern signal."
        )
    elif domain_status == "verification_required":
        concerns.append(
            "Recruiter/company domain details require independent verification."
        )
    elif domain_status == "consistent":
        positive_signals.append(
            "The supplied recruiter and website domains are recorded as consistent."
        )

    website = analysis.get("website_verification") or {}
    if website.get("checked"):
        if website.get("reachable") is False:
            concerns.append(
                "The supplied company website could not be reached during the saved technical check."
            )
        elif website.get("reachable") is True:
            positive_signals.append(
                "The supplied company website responded during the saved technical check."
            )

    compatibility_status = _text(
        analysis.get("compatibility_status"),
        "",
    ).lower()

    if analysis.get("exam_period"):
        concerns.append(
            "The internship overlaps with an examination or major assessment period."
        )

    if analysis.get("class_schedule_conflict"):
        concerns.append(
            "The internship timing conflicts with lectures or practicals."
        )

    if compatibility_status == "manageable":
        positive_signals.append(
            "The saved academic compatibility result is manageable."
        )
    elif compatibility_status == "conflict_risk":
        concerns.append(
            "The saved academic compatibility result shows a conflict risk."
        )

    consistency_status = _text(
        analysis.get("consistency_status"),
        "",
    ).lower()

    if consistency_status == "conflicting evidence":
        concerns.append(
            "The saved consistency check found conflicting evidence."
        )
    elif consistency_status == "review recommended":
        concerns.append(
            "The saved consistency check recommends additional review."
        )

    flags = analysis.get("detected_flags") or []

    for flag in flags[:5]:
        severity = _flag_severity(flag)
        suffix = f" ({severity})" if severity else ""
        concerns.append(_flag_title(flag) + suffix)

    if concerns:
        lines.extend(["", "Important points to review:"])
        for item in concerns[:6]:
            lines.append(f"• {item}")
    else:
        lines.extend([
            "",
            "No major saved concern is available in the structured assessment context.",
        ])

    if positive_signals:
        lines.extend(["", "Positive signals:"])
        for item in positive_signals[:3]:
            lines.append(f"• {item}")

    recommendations = [
        _recommendation_text(item)
        for item in (analysis.get("recommendations") or [])
    ]
    recommendations = [item for item in recommendations if item]

    if recommendations:
        lines.extend(["", "Useful next check:", f"• {recommendations[0]}"])

    lines.extend([
        "",
        (
            "This uses the assessment already saved in your InternShield account; "
            "it is not a new external verification of the company or recruiter."
        ),
    ])

    return "\n".join(lines)




def _why_flagged_reply(
    analysis: dict[str, Any],
) -> str:
    title = _company_role(analysis)

    lines = [
        (
            f"InternShield's saved assessment for {title} is "
            f"“{_status_label(analysis.get('assessment_status'))}”."
        ),
        "",
        "The important saved signals are:",
    ]

    signals: list[str] = []

    for flag in (analysis.get("detected_flags") or [])[:6]:
        severity = _flag_severity(flag)
        suffix = f" — {severity}" if severity else ""
        signals.append(_flag_title(flag) + suffix)

    domain = analysis.get("domain_verification") or {}
    domain_status = _text(domain.get("domain_status"), "").lower()

    if domain_status == "high_concern":
        signals.append(
            "Recruiter/company domain verification is marked High Concern."
        )
    elif domain_status == "verification_required":
        signals.append(
            "Recruiter/company domain verification still requires review."
        )

    website = analysis.get("website_verification") or {}
    if website.get("checked") and website.get("reachable") is False:
        signals.append(
            "The saved live website check could not reach the supplied company website."
        )

    if analysis.get("exam_period"):
        signals.append(
            "The internship overlaps with an examination or major assessment period."
        )

    if analysis.get("class_schedule_conflict"):
        signals.append(
            "The internship conflicts with the saved lecture/practical schedule."
        )

    if _text(analysis.get("consistency_status"), "").lower() == "conflicting evidence":
        signals.append(
            "The saved evidence consistency check found conflicting information."
        )

    if signals:
        for signal in signals[:7]:
            lines.append(f"• {signal}")
    else:
        lines.append(
            "• No detailed warning signal is stored for this assessment."
        )

    recommendations = [
        _recommendation_text(item)
        for item in (analysis.get("recommendations") or [])
    ]
    recommendations = [item for item in recommendations if item]

    if recommendations:
        lines.extend(["", "What to verify next:"])
        for item in recommendations[:4]:
            lines.append(f"• {item}")

    lines.extend([
        "",
        (
            "This explanation uses saved InternShield evidence and does not "
            "independently prove whether the company or internship is legitimate."
        ),
    ])

    return "\n".join(lines)



def _application_overview(applications: list[dict[str, Any]]) -> str:
    if not applications:
        return (
            "You do not have any internships in the Application Tracker yet. "
            "Add an assessed opportunity to start tracking its stage, deadlines and interview activity."
        )
    counts: dict[str, int] = {}
    for item in applications:
        status = _text(item.get("status"), "saved").lower()
        counts[status] = counts.get(status, 0) + 1

    lines = [
        f"You currently have {len(applications)} tracked application{'s' if len(applications) != 1 else ''}.",
        "",
    ]
    for status in ["offer", "interview", "applied", "saved", "rejected", "withdrawn"]:
        if counts.get(status):
            lines.append(f"• {STATUS_LABELS.get(status, status.title())}: {counts[status]}")
    lines += ["", "Most recent tracker items:"]
    for item in applications[:4]:
        lines.append(f"• {_company_role(item)} — {_status_label(item.get('status'))}")
    return "\n".join(lines)


def _offer_overview(applications: list[dict[str, Any]]) -> str:
    offers = [item for item in applications if _text(item.get("status"), "").lower() == "offer"]
    if not offers:
        return (
            "None of your tracked applications are currently at the Offer stage. "
            "When an application reaches Offer, InternShield can compare the final written offer with the original assessment."
        )
    lines = [f"You currently have {len(offers)} application{'s' if len(offers) != 1 else ''} at Offer stage.", ""]
    for item in offers[:5]:
        lines.append(f"• {_company_role(item)}")
        if item.get("offer_change_status"):
            lines.append(
                f"  Final offer comparison: {_text(item.get('offer_change_status'))} ({_score(item.get('offer_change_score'))}/100)"
            )
        else:
            lines.append("  Final offer comparison: Not analyzed yet")
    lines += ["", "Open Application Tracker → Final offer analysis to review changed terms before accepting."]
    return "\n".join(lines)


def _follow_up_draft(application: dict[str, Any] | None, user_name: str) -> str:
    if not application:
        return (
            "I can draft a recruiter follow-up once you have an internship in the Application Tracker. "
            "Add the role first, then ask me for a follow-up message."
        )
    company = _text(application.get("company_name"), "your company")
    role = _text(application.get("role_title"), "internship position")
    status = _text(application.get("status"), "saved").lower()
    first_name = _text(user_name, "Student").split()[0]

    if status == "interview":
        return (
            f"Here is a professional post-interview follow-up for {role} at {company}:\n\n"
            "Subject: Thank you for the interview\n\nHello,\n\n"
            f"Thank you for taking the time to speak with me about the {role} opportunity at {company}. "
            "I appreciated learning more about the role and the team.\n\n"
            "I remain interested in the opportunity and would be happy to provide any additional information if needed. "
            "Please let me know if there are any updates regarding the next steps.\n\n"
            f"Best regards,\n{first_name}"
        )
    if status == "offer":
        return (
            f"Here is a clarification message for the {role} offer from {company}:\n\nHello,\n\n"
            "Thank you for sharing the internship offer. Before I confirm my decision, I would like to verify a few final "
            "details in writing, including the expected weekly working hours, stipend, internship duration, work mode and "
            "any fees or charges associated with joining.\n\nCould you please confirm these terms?\n\n"
            f"Best regards,\n{first_name}"
        )
    return (
        f"Here is a professional status follow-up for {role} at {company}:\n\nSubject: Follow-up on {role} application\n\n"
        "Hello,\n\n"
        f"I am writing to follow up on my application for the {role} position at {company}. I remain interested in the opportunity "
        "and wanted to ask whether there are any updates regarding the application or next steps.\n\n"
        "Please let me know if you need any additional information from my side.\n\n"
        f"Best regards,\n{first_name}"
    )


def _profile_reply(profile: dict[str, Any]) -> str:
    if not profile:
        return "Your InternShield profile has not been completed yet. Open Profile → Edit profile to add academic and internship preferences."
    hours = profile.get("available_hours_per_week")
    return "\n".join(
        [
            "Your saved profile context:",
            "",
            f"• College: {_text(profile.get('college_name'), 'Not added')}",
            f"• Branch: {_text(profile.get('branch'), 'Not added')}",
            f"• Semester: {profile.get('semester') or 'Not added'}",
            f"• Weekly availability: {f'{hours} hours' if hours is not None else 'Not added'}",
            f"• Preferred work mode: {_status_label(profile.get('preferred_work_mode') or 'no_preference')}",
            f"• Default schedule: {_status_label(profile.get('default_schedule_type') or 'not_specified')}",
        ]
    )


def _next_action_reply(analyses: list[dict[str, Any]], applications: list[dict[str, Any]]) -> str:
    offer_without_review = next(
        (
            item
            for item in applications
            if _text(item.get("status"), "").lower() == "offer" and not item.get("offer_change_status")
        ),
        None,
    )
    if offer_without_review:
        return (
            f"Your strongest next action is to analyze the final offer for {_company_role(offer_without_review)}. "
            "It is at Offer stage but does not yet have a saved final-offer comparison. Open Applications → Analyze final offer."
        )

    review_offer = next(
        (
            item
            for item in applications
            if _text(item.get("offer_change_status"), "").lower() in {"major changes detected", "review changes"}
        ),
        None,
    )
    if review_offer:
        return (
            f"Review the changed final-offer terms for {_company_role(review_offer)} before accepting. "
            f"The saved comparison is {_text(review_offer.get('offer_change_status'))} ({_score(review_offer.get('offer_change_score'))}/100)."
        )

    risky = next(
        (
            item
            for item in analyses
            if _text(item.get("assessment_status"), "").lower() == "potentially_suspicious"
        ),
        None,
    )
    if risky:
        return (
            f"Your next useful action is to verify the warning indicators for {_company_role(risky)} before moving forward. "
            "Ask me “Why is this internship suspicious?” or open the full assessment."
        )
    if applications:
        return (
            "Your tracker does not currently show an unresolved offer-change warning. "
            "Review Upcoming Actions in the Application Tracker for deadlines, interviews and follow-ups."
        )
    return (
        "Start by assessing an internship offer or recruiter message. Once the assessment is saved, "
        "I can explain the scores and help you decide what to verify next."
    )


def _rule_based_reply(
    message: str,
    *,
    profile: dict[str, Any],
    analyses: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    user_name: str,
) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", (message or "").strip().lower())
    named_analysis = _find_named(normalized, analyses)
    named_application = _find_named(normalized, applications)
    latest_analysis = named_analysis or (analyses[0] if analyses else None)
    latest_application = named_application or (applications[0] if applications else None)

    suggestions = [
        "Explain my latest assessment",
        "What should I do next?",
        "Show my application status",
        "Draft a recruiter follow-up",
    ]

    if not normalized:
        return {"intent": "empty", "reply": "Ask me about your assessments, applications, offers, warning indicators or recruiter follow-ups.", "suggestions": suggestions}

    if re.fullmatch(r"(hi+|hello|hey+|help)[!. ]*", normalized):
        return {
            "intent": "greeting",
            "reply": f"Hi {_text(user_name, 'there').split()[0]}! I can explain your saved InternShield assessments, review application stages, summarize final-offer changes and draft recruiter follow-ups.",
            "suggestions": suggestions,
        }

    if any(term in normalized for term in ["what should i do next", "next step", "what next", "next action"]):
        return {"intent": "next_action", "reply": _next_action_reply(analyses, applications), "suggestions": suggestions}

    if any(term in normalized for term in ["follow up", "follow-up", "followup", "draft", "message recruiter", "email recruiter"]):
        return {
            "intent": "follow_up",
            "reply": _follow_up_draft(latest_application, user_name),
            "suggestions": ["Show my application status", "What should I do next?", "Explain my latest assessment"],
        }

    if any(term in normalized for term in ["profile", "my preference", "available hours"]):
        return {"intent": "profile", "reply": _profile_reply(profile), "suggestions": suggestions}

    if "offer" in normalized and any(term in normalized for term in ["change", "final", "compare", "my offer"]):
        return {
            "intent": "offer",
            "reply": _offer_overview(applications),
            "suggestions": ["What should I do next?", "Draft a recruiter follow-up", "Show my application status"],
        }

    if any(term in normalized for term in ["application", "tracker", "status"]):
        return {
            "intent": "applications",
            "reply": _application_overview(applications),
            "suggestions": ["What should I do next?", "Draft a recruiter follow-up", "Explain my latest assessment"],
        }

    if latest_analysis and (
        any(term in normalized for term in ["suspicious", "warning", "flag"])
        or "why" in normalized
    ):
        return {
            "intent": "explain_flags",
            "reply": _why_flagged_reply(latest_analysis),
            "suggestions": ["Explain my latest assessment", "What should I do next?", "Draft a recruiter follow-up"],
        }

    if any(term in normalized for term in ["assessment", "score", "verification", "compatibility", "consistency"]) or named_analysis:
        if latest_analysis:
            return {
                "intent": "assessment",
                "reply": _assessment_summary(latest_analysis),
                "suggestions": ["Why is this internship suspicious?", "What should I do next?", "Show my application status"],
            }
        return {
            "intent": "no_assessment",
            "reply": "You do not have a saved internship assessment yet. Create a New Assessment first, then I can explain its verification, value, compatibility and consistency scores.",
            "suggestions": suggestions,
        }

    if named_analysis:
        return {
            "intent": "named_assessment",
            "reply": _assessment_summary(named_analysis),
            "suggestions": ["Why is this internship suspicious?", "What should I do next?", "Draft a recruiter follow-up"],
        }

    return {
        "intent": "guided_fallback",
        "reply": (
            "I can answer questions using the information already saved in your InternShield account. "
            "Try asking about your latest assessment, a company in your history, application status, final-offer changes, "
            "warning indicators or a recruiter follow-up.\n\nFor company facts that are not present in your saved assessment, "
            "use InternShield's verification workflow instead of relying on chat alone."
        ),
        "suggestions": suggestions,
    }


def generate_assistant_reply(
    message: str,
    *,
    profile: dict[str, Any] | None = None,
    analyses: list[dict[str, Any]] | None = None,
    applications: list[dict[str, Any]] | None = None,
    user_name: str = "Student",
) -> dict[str, Any]:
    """Generate a grounded reply with automatic Gemini → local fallback."""
    profile = profile or {}
    analyses = analyses or []
    applications = applications or []

    result = _rule_based_reply(
        message,
        profile=profile,
        analyses=analyses,
        applications=applications,
        user_name=user_name,
    )
    result.update({"ai_used": False, "provider": "internshield", "model": None})

    if not (message or "").strip():
        return result

    try:
        ai = generate_grounded_assistant_response(
            message,
            profile=profile,
            analyses=analyses,
            applications=applications,
            baseline_reply=result["reply"],
        )
    except Exception:
        ai = None

    if ai and _text(ai.get("reply"), ""):
        result["reply"] = _text(ai.get("reply"), result["reply"])
        result["ai_used"] = True
        result["provider"] = "gemini"
        result["model"] = ai.get("model")

    return result
