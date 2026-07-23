import re
from typing import Optional


RED_FLAG_RULES = [
    {
        "phrases": [
            "registration fee",
            "training fee",
            "security deposit",
            "pay to join",
            "application fee",
            "refundable fee",
        ],
        "title": "Payment requested",
        "severity": "high",
        "deduction": 30,
        "recommendation": (
            "Do not make a payment before independently "
            "verifying the company and internship."
        ),
    },
    {
        "phrases": [
            "guaranteed selection",
            "guaranteed job",
            "100% placement",
            "direct selection",
            "no interview required",
        ],
        "title": "Guaranteed selection claim",
        "severity": "high",
        "deduction": 20,
        "recommendation": (
            "Ask for the formal selection process and written "
            "role requirements."
        ),
    },
    {
        "phrases": [
            "join immediately",
            "limited slots",
            "respond immediately",
            "urgent joining",
            "offer expires today",
        ],
        "title": "Urgency pressure",
        "severity": "medium",
        "deduction": 12,
        "recommendation": (
            "Request sufficient time to verify the offer before "
            "accepting it."
        ),
    },
    {
        "phrases": [
            "bank account details",
            "aadhaar card",
            "pan card",
            "credit card details",
            "share your otp",
        ],
        "title": "Sensitive information requested",
        "severity": "high",
        "deduction": 25,
        "recommendation": (
            "Do not provide sensitive financial or identity "
            "information before verifying the recruiter."
        ),
    },
    {
        "phrases": [
            "telegram only",
            "whatsapp only",
            "contact on telegram",
        ],
        "title": "Informal communication channel",
        "severity": "medium",
        "deduction": 10,
        "recommendation": (
            "Request communication through an official company "
            "email address."
        ),
    },
    {
        "phrases": [
            "unpaid assignment",
            "unpaid task",
            "complete this project before selection",
        ],
        "title": "Unpaid pre-selection work",
        "severity": "medium",
        "deduction": 12,
        "recommendation": (
            "Confirm that the assignment is only an assessment "
            "and will not be used as unpaid company work."
        ),
    },
]


POSITIVE_EVIDENCE_RULES = [
    {
        "phrases": [
            "formal offer letter",
            "official offer letter",
        ],
        "points": 8,
    },
    {
        "phrases": [
            "interview process",
            "technical interview",
            "interview round",
        ],
        "points": 7,
    },
    {
        "phrases": [
            "assigned mentor",
            "dedicated mentor",
            "mentorship",
        ],
        "points": 7,
    },
    {
        "phrases": [
            "clear responsibilities",
            "roles and responsibilities",
        ],
        "points": 5,
    },
]


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def phrase_is_negated(
    text: str,
    phrase: str,
    phrase_start: int,
) -> bool:
    sentence_boundaries = ".!?\n;"

    sentence_start = 0

    for boundary in sentence_boundaries:
        position = text.rfind(
            boundary,
            0,
            phrase_start,
        )

        if position >= sentence_start:
            sentence_start = position + 1

    possible_ends = []

    for boundary in sentence_boundaries:
        position = text.find(
            boundary,
            phrase_start,
        )

        if position != -1:
            possible_ends.append(position)

    sentence_end = (
        min(possible_ends)
        if possible_ends
        else len(text)
    )

    sentence = text[sentence_start:sentence_end]
    local_phrase_start = phrase_start - sentence_start

    text_before = sentence[
        max(0, local_phrase_start - 120):
        local_phrase_start
    ]

    text_after = sentence[
        local_phrase_start + len(phrase):
        local_phrase_start + len(phrase) + 80
    ]

    negation_before_pattern = (
        r"\b(no|not|never|without)\b"
        r"[^.!?;]{0,100}$"
    )

    negation_after_pattern = (
        r"^\s*(is|are|was|were|will be)?\s*"
        r"(not|never)\b"
        r"[^.!?;]{0,40}"
        r"\b(required|needed|charged|requested)\b"
    )

    if re.search(
        negation_before_pattern,
        text_before,
    ):
        return True

    if re.search(
        negation_after_pattern,
        text_after,
    ):
        return True

    return False


def find_non_negated_match(
    text: str,
    phrase: str,
) -> Optional[str]:
    search_position = 0

    while True:
        phrase_start = text.find(
            phrase,
            search_position,
        )

        if phrase_start == -1:
            return None

        if not phrase_is_negated(
            text,
            phrase,
            phrase_start,
        ):
            return phrase

        search_position = phrase_start + len(phrase)


def calculate_hourly_stipend(
    stipend_monthly: Optional[float],
    hours_per_day: Optional[float],
    days_per_week: Optional[int],
) -> Optional[float]:
    if stipend_monthly is None:
        return None

    if hours_per_day is None or days_per_week is None:
        return None

    monthly_hours = hours_per_day * days_per_week * 4.33

    if monthly_hours <= 0:
        return None

    return round(stipend_monthly / monthly_hours, 2)


def analyze_internship(
    text: str,
    stipend_monthly: Optional[float] = None,
    hours_per_day: Optional[float] = None,
    days_per_week: Optional[int] = None,
) -> dict:
    normalized_text = normalize_text(text)

    verification_score = 60
    value_score = 50

    detected_flags = []
    recommendations = []
    positive_evidence_count = 0
    high_severity_count = 0

    for rule in RED_FLAG_RULES:
        matched_phrase = None

        for phrase in rule["phrases"]:
            match = find_non_negated_match(
                normalized_text,
                phrase,
            )

            if match:
                matched_phrase = match
                break

        if not matched_phrase:
            continue

        verification_score -= rule["deduction"]

        if rule["severity"] == "high":
            high_severity_count += 1

        detected_flags.append({
            "title": rule["title"],
            "severity": rule["severity"],
            "matched_phrase": matched_phrase,
        })

        recommendations.append(rule["recommendation"])

    for rule in POSITIVE_EVIDENCE_RULES:
        matched = any(
            phrase in normalized_text
            for phrase in rule["phrases"]
        )

        if matched:
            verification_score += rule["points"]
            positive_evidence_count += 1

    official_email_pattern = (
        r"\b[a-z0-9._%+-]+@"
        r"(?!gmail\.com|yahoo\.com|outlook\.com|hotmail\.com)"
        r"[a-z0-9.-]+\.[a-z]{2,}\b"
    )

    if re.search(
        official_email_pattern,
        normalized_text,
    ):
        verification_score += 8
        positive_evidence_count += 1

    hourly_stipend = calculate_hourly_stipend(
        stipend_monthly,
        hours_per_day,
        days_per_week,
    )

    if stipend_monthly is None:
        value_score -= 10
        recommendations.append(
            "Ask the recruiter to clearly state whether the "
            "internship is paid or unpaid."
        )

    elif stipend_monthly <= 0:
        value_score -= 20
        recommendations.append(
            "Evaluate whether the unpaid workload is justified "
            "by structured mentorship and meaningful learning."
        )

    else:
        value_score += 10

    if hourly_stipend is not None:
        if hourly_stipend >= 75:
            value_score += 20

        elif hourly_stipend >= 40:
            value_score += 10

        elif hourly_stipend < 20:
            value_score -= 15

    if (
        "mentor" in normalized_text
        or "mentorship" in normalized_text
    ):
        value_score += 10

    if "offer letter" in normalized_text:
        value_score += 10

    if "certificate" in normalized_text:
        value_score += 5

    verification_score = max(
        0,
        min(100, verification_score),
    )

    value_score = max(
        0,
        min(100, value_score),
    )

    if high_severity_count >= 2 or verification_score < 40:
        assessment_status = "potentially_suspicious"

    elif detected_flags or positive_evidence_count < 2:
        assessment_status = "verification_required"

    elif verification_score >= 75:
        assessment_status = "appears_reasonable"

    else:
        assessment_status = "verification_required"

    if positive_evidence_count < 2:
        recommendations.append(
            "Request independently verifiable evidence such as "
            "an official company email, formal offer letter and "
            "documented selection process."
        )

    if not recommendations:
        recommendations.append(
            "Verify the company website, recruiter identity and "
            "written responsibilities before accepting."
        )

    return {
        "verification_score": verification_score,
        "value_score": value_score,
        "effective_hourly_stipend": hourly_stipend,
        "assessment_status": assessment_status,
        "detected_flags": detected_flags,
        "recommendations": list(
            dict.fromkeys(recommendations)
        ),
    }