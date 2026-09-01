"""Optional Gemini language layer for InternShield AI.

InternShield's deterministic engines remain authoritative. Gemini only
explains already-calculated structured results and improves Assistant
wording. All functions fail closed to local fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()
LOGGER = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except Exception:  # Optional dependency; the app must still work.
    genai = None
    types = None

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_TIMEOUT_MS = 15000


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _enabled() -> bool:
    value = (os.getenv("GEMINI_AI_ENABLED", "true") or "true").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _timeout_ms() -> int:
    raw = (os.getenv("GEMINI_TIMEOUT_MS") or str(DEFAULT_TIMEOUT_MS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_TIMEOUT_MS
    return max(3000, min(value, 45000))


def _models() -> list[str]:
    primary = (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
    fallback = (os.getenv("GEMINI_FALLBACK_MODEL") or "").strip()
    result: list[str] = []
    for model in (primary, fallback):
        if model and model not in result:
            result.append(model)
    return result


def _client():
    if not _enabled() or genai is None or types is None:
        return None
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=_timeout_ms()),
    )


def _call(prompt: str) -> tuple[str | None, str | None]:
    client = _client()
    if client is None:
        return None, None

    try:
        for model in _models():
            try:
                interaction = client.interactions.create(
                    model=model,
                    input=prompt,
                )
                output = _text(getattr(interaction, "output_text", ""))
                if output:
                    return output, model
            except Exception as error:
                LOGGER.warning(
                    "Gemini model %s unavailable (%s).",
                    model,
                    type(error).__name__,
                )
        return None, None
    finally:
        try:
            client.close()
        except Exception:
            pass


def _flag(flag: Any) -> dict[str, Any] | str:
    if not isinstance(flag, dict):
        return _text(flag, "Warning indicator")
    return {
        "title": _text(
            flag.get("title")
            or flag.get("name")
            or flag.get("label")
            or flag.get("matched_phrase"),
            "Warning indicator",
        ),
        "severity": _text(flag.get("severity")),
        "matched_phrase": _text(
            flag.get("matched_phrase") or flag.get("matched")
        ),
    }


def _recommendation(item: Any) -> str:
    if isinstance(item, dict):
        return _text(
            item.get("text")
            or item.get("recommendation")
            or item.get("message")
            or item.get("title")
        )
    return _text(item)


def _assessment_context(
    analysis: dict[str, Any],
    offer_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    """Only structured results are sent; raw uploaded text is excluded."""
    domain = analysis.get("domain_verification") or {}
    website = analysis.get("website_verification") or {}

    context: dict[str, Any] = {
        "company_name": _text(analysis.get("company_name"), "Not provided"),
        "role_title": _text(analysis.get("role_title"), "Internship opportunity"),
        "assessment_status": _text(analysis.get("assessment_status")),
        "verification_score": _number(analysis.get("verification_score")),
        "value_score": _number(analysis.get("value_score")),
        "compatibility_score": _number(analysis.get("compatibility_score")),
        "compatibility_status": _text(analysis.get("compatibility_status")),
        "consistency_score": _number(analysis.get("consistency_score")),
        "consistency_status": _text(analysis.get("consistency_status")),
        "effective_hourly_stipend": _number(analysis.get("effective_hourly_stipend")),
        "weekly_workload": _number(analysis.get("weekly_workload")),
        "available_hours_per_week": _number(analysis.get("available_hours_per_week")),
        "exam_period": bool(analysis.get("exam_period")),
        "class_schedule_conflict": bool(analysis.get("class_schedule_conflict")),
        "domain_status": _text(domain.get("domain_status")),
        "domain_match": analysis.get("domain_match"),
        "website_check_status": _text(website.get("status")),
        "website_reachable": website.get("reachable"),
        "detected_indicators": [
            _flag(item)
            for item in (analysis.get("detected_flags") or [])[:6]
        ],
        "recommended_checks": [
            text
            for text in (
                _recommendation(item)
                for item in (analysis.get("recommendations") or [])[:6]
            )
            if text
        ],
    }

    if offer_decision:
        context["final_offer_decision"] = {
            "decision_score": _number(offer_decision.get("decision_score")),
            "decision_label": _text(offer_decision.get("decision_label")),
            "summary": _text(offer_decision.get("summary")),
            "offer_change_status": _text(offer_decision.get("offer_change_status")),
            "offer_change_score": _number(offer_decision.get("offer_change_score")),
            "concerns": (offer_decision.get("concerns") or [])[:6],
            "next_steps": (offer_decision.get("next_steps") or [])[:6],
        }

    return context


def _clean_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _parse_explanation(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_clean_json(text))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    summary = _text(data.get("summary"))
    if not summary:
        return None

    points = data.get("key_points") or []
    if not isinstance(points, list):
        points = []

    return {
        "summary": summary,
        "key_points": [_text(item) for item in points[:4] if _text(item)],
        "next_step": _text(data.get("next_step")),
    }


def _fallback_explanation(
    analysis: dict[str, Any],
    offer_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    status = _text(analysis.get("assessment_status"), "verification_required")
    meanings = {
        "appears_reasonable": "the submitted evidence did not trigger major predefined warning indicators",
        "verification_required": "some submitted details still require independent verification",
        "potentially_suspicious": "multiple important warning indicators were detected",
    }

    points: list[str] = []
    for label, key in (
        ("Verification", "verification_score"),
        ("Academic compatibility", "compatibility_score"),
        ("Evidence consistency", "consistency_score"),
    ):
        value = _number(analysis.get(key))
        if value is not None:
            points.append(f"{label}: {value}/100.")

    flags = analysis.get("detected_flags") or []
    if flags:
        first = _flag(flags[0])
        title = first.get("title") if isinstance(first, dict) else str(first)
        points.append(f"A key warning is: {title}.")

    next_step = ""
    if offer_decision and (offer_decision.get("next_steps") or []):
        next_step = _text((offer_decision.get("next_steps") or [""])[0])
    if not next_step and (analysis.get("recommendations") or []):
        next_step = _recommendation((analysis.get("recommendations") or [""])[0])
    if not next_step:
        next_step = (
            "Independently verify the recruiter, company and written internship terms "
            "before making a final decision."
        )

    return {
        "summary": "InternShield recommends review because " + meanings.get(
            status, meanings["verification_required"]
        ) + ".",
        "key_points": points[:4],
        "next_step": next_step,
        "ai_used": False,
        "provider": "InternShield explainable fallback",
        "model": None,
    }


def generate_assessment_explanation(
    analysis: dict[str, Any],
    *,
    offer_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = _fallback_explanation(analysis, offer_decision)
    context = _assessment_context(analysis, offer_decision)

    prompt = (
        "You are the explanation layer for InternShield AI, a student internship "
        "decision-support system.\n\n"
        "Rules:\n"
        "- Use ONLY the structured InternShield facts below.\n"
        "- Do not recalculate, change or invent scores.\n"
        "- Do not claim legitimacy, fraud, safety or danger as proven facts.\n"
        "- Do not add external company or recruiter facts.\n"
        "- Explain uncertainty and recommend independent verification when relevant.\n"
        "- Keep the wording concise and professional.\n"
        "- Return JSON only, with exactly: summary, key_points, next_step.\n\n"
        "STRUCTURED RESULT:\n"
        + json.dumps(context, ensure_ascii=False, default=str)
    )

    text, model = _call(prompt)
    if not text:
        return fallback

    parsed = _parse_explanation(text)
    if not parsed:
        return fallback

    parsed.update(
        {
            "ai_used": True,
            "provider": "Gemini-assisted explanation",
            "model": model,
        }
    )
    return parsed



def _assistant_context(
    profile: dict[str, Any],
    analyses: list[dict[str, Any]],
    applications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a compact, structured context for grounded chat.

    Raw uploaded documents, screenshots, account email addresses and API
    secrets are intentionally excluded. The Assistant receives only the
    facts InternShield has already calculated or saved for the user.
    """

    recent_assessments: list[dict[str, Any]] = []

    for item in analyses[:8]:
        domain = item.get("domain_verification") or {}
        website = item.get("website_verification") or {}

        domain_factors = []
        for factor in (domain.get("factors") or [])[:5]:
            if not isinstance(factor, dict):
                continue
            domain_factors.append({
                "type": _text(factor.get("type")),
                "label": _text(factor.get("label")),
                "evidence": _text(factor.get("evidence")),
            })

        website_checks = []
        for check in (website.get("checks") or [])[:5]:
            if not isinstance(check, dict):
                continue
            website_checks.append({
                "type": _text(check.get("type")),
                "label": _text(check.get("label")),
                "detail": _text(check.get("detail")),
            })

        recommendations = [
            text
            for text in (
                _recommendation(rec)
                for rec in (item.get("recommendations") or [])[:6]
            )
            if text
        ]

        recent_assessments.append({
            "company_name": _text(item.get("company_name")),
            "role_title": _text(item.get("role_title")),
            "assessment_status": _text(item.get("assessment_status")),
            "verification_score": _number(item.get("verification_score")),
            "value_score": _number(item.get("value_score")),
            "compatibility_score": _number(item.get("compatibility_score")),
            "compatibility_status": _text(item.get("compatibility_status")),
            "compatibility_reasons": (item.get("compatibility_reasons") or [])[:5],
            "consistency_score": _number(item.get("consistency_score")),
            "consistency_status": _text(item.get("consistency_status")),
            "weekly_workload": _number(item.get("weekly_workload")),
            "available_hours_per_week": _number(item.get("available_hours_per_week")),
            "schedule_type": _text(item.get("schedule_type")),
            "exam_period": bool(item.get("exam_period")),
            "class_schedule_conflict": bool(item.get("class_schedule_conflict")),
            "domain_verification": {
                "status": _text(domain.get("domain_status")),
                "domain_match": item.get("domain_match"),
                "recruiter_domain": _text(item.get("recruiter_email_domain")),
                "website_domain": _text(item.get("company_website_domain")),
                "factors": domain_factors,
                "recommendations": (domain.get("recommendations") or [])[:4],
            },
            "website_verification": {
                "checked": bool(website.get("checked")),
                "status": _text(website.get("status")),
                "reachable": website.get("reachable"),
                "uses_https": website.get("uses_https"),
                "status_code": website.get("status_code"),
                "final_domain": _text(website.get("final_domain")),
                "checks": website_checks,
            },
            "warning_indicators": [
                _flag(flag)
                for flag in (item.get("detected_flags") or [])[:6]
            ],
            "recommended_checks": recommendations,
        })

    tracked_applications: list[dict[str, Any]] = []

    for item in applications[:10]:
        offer_change = item.get("offer_change_analysis") or {}

        tracked_applications.append({
            "company_name": _text(item.get("company_name")),
            "role_title": _text(item.get("role_title")),
            "status": _text(item.get("status")),
            "application_deadline": _text(item.get("application_deadline")),
            "interview_date": _text(item.get("interview_date")),
            "offer_change_status": _text(item.get("offer_change_status")),
            "offer_change_score": _number(item.get("offer_change_score")),
            "offer_change_summary": _text(
                offer_change.get("summary")
                or offer_change.get("message")
            ),
            "critical_offer_changes": (
                offer_change.get("critical_changes")
                or offer_change.get("critical_differences")
                or []
            )[:4],
        })

    return {
        "profile": {
            "college_name": _text(profile.get("college_name")),
            "branch": _text(profile.get("branch")),
            "semester": profile.get("semester"),
            "available_hours_per_week": _number(profile.get("available_hours_per_week")),
            "preferred_work_mode": _text(profile.get("preferred_work_mode")),
            "default_schedule_type": _text(profile.get("default_schedule_type")),
        },
        "recent_assessments": recent_assessments,
        "tracked_applications": tracked_applications,
    }




def generate_grounded_assistant_response(
    message: str,
    *,
    profile: dict[str, Any],
    analyses: list[dict[str, Any]],
    applications: list[dict[str, Any]],
    baseline_reply: str,
) -> dict[str, Any] | None:
    if not _text(message):
        return None

    context = _assistant_context(
        profile,
        analyses,
        applications,
    )

    prompt = (
        "You are InternShield Assistant, a grounded internship decision-support "
        "assistant for students. Answer naturally using ONLY the saved InternShield "
        "context below.\n\n"
        "STRICT RULES:\n"
        "- Never invent company, recruiter, website or internship facts.\n"
        "- Never change, recalculate or reinterpret a saved score as a different score.\n"
        "- A missing phrase-based warning indicator does NOT mean there are no concerns. "
        "Domain verification, website reachability, academic conflicts, consistency "
        "checks and final-offer changes are separate signals and must be considered.\n"
        "- If the user asks to explain an assessment, synthesize the most important "
        "reasons in plain language instead of merely dumping every score.\n"
        "- Mention the strongest positive signal as well as the most important concern "
        "when both are present.\n"
        "- If facts are missing, say InternShield does not have them and recommend the "
        "relevant verification workflow.\n"
        "- Preserve useful recruiter-message drafts from the valid local baseline.\n"
        "- Never claim that InternShield or the AI has proven an opportunity legitimate, "
        "fraudulent, safe or unsafe.\n"
        "- Do not mention API keys, Gemini, model names or implementation details.\n"
        "- Keep answers professional, student-friendly and reasonably concise.\n\n"
        f"USER QUESTION:\n{message}\n\n"
        "SAVED INTERNSHIELD CONTEXT:\n"
        + json.dumps(context, ensure_ascii=False, default=str)
        + f"\n\nVALID LOCAL FALLBACK ANSWER:\n{baseline_reply}"
        + "\n\nWrite the final grounded answer only."
    )

    text, model = _call(prompt)

    if not text:
        return None

    return {
        "reply": text.strip(),
        "model": model,
        "provider": "gemini",
    }
