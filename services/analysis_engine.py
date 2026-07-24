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
            "processing fee",
            "onboarding fee",
            "certificate fee",
            "refundable fee",
            "scan the qr code",
            "send payment",
            "make the payment",
        ],
        "patterns": [
            (
                r"\bregistration(?:\s+(?:and|or)\s+"
                r"[a-z0-9-]+){1,3}\s+(?:fee|charge|deposit)\b"
            ),
            (
                r"\b(?:registration|training|application|processing|"
                r"onboarding|certificate|document(?:\s+verification)?|"
                r"verification|security)\s+(?:fee|charge|deposit)\b"
            ),
            (
                r"\b(?:pay|transfer|send)\b[^.!?;]{0,70}"
                r"(?:₹\s?\d|rs\.?\s?\d|inr\s?\d|\b\d{3,}\b)"
            ),
            (
                r"\b(?:pay|make\s+(?:a|the)\s+payment|"
                r"complete\s+(?:a|the)\s+payment)\b"
                r"[^.!?;]{0,80}\b(?:confirm|secure|reserve)\b"
                r"[^.!?;]{0,35}\b(?:position|seat|slot|offer)\b"
            ),
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
            "limited opportunity",
            "respond immediately",
            "urgent joining",
            "offer expires today",
            "pay today",
            "within two hours",
            "within 24 hours",
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
            "debit card details",
            "card number",
            "cvv",
            "upi pin",
            "internet banking password",
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
            "message on telegram",
            "communicate only through whatsapp",
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
            "complete production work before selection",
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
            "written responsibilities",
            "job description",
        ],
        "points": 5,
    },
    {
        "phrases": [
            "company website",
            "official website",
        ],
        "points": 4,
    },
]


FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "rediffmail.com",
}


def normalize_text(text: str) -> str:
    text = str(text or "").lower()
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )
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

    text_before = sentence[max(0, local_phrase_start - 100):local_phrase_start]

    text_after = sentence[
        local_phrase_start + len(phrase):
        local_phrase_start + len(phrase) + 80
    ]

    # Only treat a nearby negation as applying to the phrase. A broad
    # sentence-level check can hide a genuine warning in text such as:
    # "No interview is required, but pay a registration fee."
    negation_before_pattern = (
        r"\b(no|not|never|without|isn't|aren't|wasn't|weren't|"
        r"doesn't|don't|won't)\b"
        r"(?:\W+\w+){0,6}\W*$"
    )

    negation_after_pattern = (
        r"^\s*(is|are|was|were|will be)?\s*"
        r"(not|never)\b"
        r"[^.!?;]{0,40}"
        r"\b(required|needed|charged|requested)\b"
    )

    before_match = re.search(negation_before_pattern, text_before)

    if before_match:
        negated_segment = text_before[before_match.start():]

        # A contrast word ends the scope of the earlier negation.
        if not re.search(r"\b(but|however|yet|although)\b", negated_segment):
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


def find_non_negated_pattern(
    text: str,
    pattern: str,
) -> Optional[str]:
    """
    Return the first regex match that is not negated.

    Regex patterns allow the engine to recognise natural variations
    such as "registration and security fee" without maintaining every
    possible exact phrase.
    """
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        matched_text = match.group(0).strip()

        if not phrase_is_negated(
            text,
            matched_text,
            match.start(),
        ):
            return matched_text

    return None


def contains_non_negated_phrase(text: str, phrases: list[str]) -> bool:
    """Return True when at least one phrase appears outside negation."""
    return any(find_non_negated_match(text, phrase) for phrase in phrases)


def contains_official_email(text: str) -> bool:
    """
    Detect a company-style email address while excluding common free
    mailbox providers. This is supporting evidence, not proof that a
    company or recruiter is legitimate.
    """
    addresses = re.findall(
        r"\b[a-z0-9._%+-]+@([a-z0-9.-]+\.[a-z]{2,})\b",
        text,
        flags=re.IGNORECASE,
    )

    return any(domain.lower() not in FREE_EMAIL_DOMAINS for domain in addresses)


def add_unique(items: list, value) -> None:
    """Append a value only when it has not already been added."""
    if value not in items:
        items.append(value)


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
    verification_factors = []
    value_factors = []
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
            for pattern in rule.get("patterns", []):
                match = find_non_negated_pattern(
                    normalized_text,
                    pattern,
                )

                if match:
                    matched_phrase = match
                    break

        if not matched_phrase:
            continue

        verification_score -= rule["deduction"]
        verification_factors.append({
            "type": "deduction",
            "label": rule["title"],
            "points": -rule["deduction"],
            "evidence": matched_phrase,
        })

        if rule["severity"] == "high":
            high_severity_count += 1

        detected_flags.append({
            "title": rule["title"],
            "severity": rule["severity"],
            "matched_phrase": matched_phrase,
        })

        add_unique(recommendations, rule["recommendation"])

    for rule in POSITIVE_EVIDENCE_RULES:
        matched_phrase = next(
            (
                phrase
                for phrase in rule["phrases"]
                if find_non_negated_match(normalized_text, phrase)
            ),
            None,
        )

        if matched_phrase:
            verification_score += rule["points"]
            positive_evidence_count += 1
            verification_factors.append({
                "type": "evidence",
                "label": "Positive verification evidence",
                "points": rule["points"],
                "evidence": matched_phrase,
            })

    if contains_official_email(normalized_text):
        verification_score += 8
        positive_evidence_count += 1
        verification_factors.append({
            "type": "evidence",
            "label": "Company-style email address supplied",
            "points": 8,
            "evidence": "Non-free email domain",
        })

    hourly_stipend = calculate_hourly_stipend(
        stipend_monthly,
        hours_per_day,
        days_per_week,
    )

    if stipend_monthly is None:
        value_score -= 10
        value_factors.append({
            "type": "deduction",
            "label": "Stipend not specified",
            "points": -10,
        })
        add_unique(
            recommendations,
            "Ask the recruiter to clearly state whether the "
            "internship is paid or unpaid.",
        )

    elif stipend_monthly <= 0:
        value_score -= 20
        value_factors.append({
            "type": "deduction",
            "label": "Unpaid internship",
            "points": -20,
        })
        add_unique(
            recommendations,
            "Evaluate whether the unpaid workload is justified "
            "by structured mentorship and meaningful learning.",
        )

    else:
        value_score += 10
        value_factors.append({
            "type": "evidence",
            "label": "Paid internship",
            "points": 10,
        })

    if hourly_stipend is not None:
        if hourly_stipend >= 75:
            value_score += 20
            value_factors.append({
                "type": "evidence",
                "label": "Strong effective hourly stipend",
                "points": 20,
            })

        elif hourly_stipend >= 40:
            value_score += 10
            value_factors.append({
                "type": "evidence",
                "label": "Moderate effective hourly stipend",
                "points": 10,
            })

        elif hourly_stipend < 20:
            value_score -= 15
            value_factors.append({
                "type": "deduction",
                "label": "Low effective hourly stipend",
                "points": -15,
            })

    if contains_non_negated_phrase(
        normalized_text,
        ["assigned mentor", "dedicated mentor", "mentorship"],
    ):
        value_score += 10
        value_factors.append({
            "type": "evidence",
            "label": "Structured mentorship mentioned",
            "points": 10,
        })

    if contains_non_negated_phrase(
        normalized_text,
        ["formal offer letter", "official offer letter", "offer letter"],
    ):
        value_score += 10
        value_factors.append({
            "type": "evidence",
            "label": "Offer letter mentioned",
            "points": 10,
        })

    if contains_non_negated_phrase(
        normalized_text,
        ["completion certificate", "experience certificate", "certificate"],
    ):
        value_score += 5
        value_factors.append({
            "type": "evidence",
            "label": "Certificate mentioned",
            "points": 5,
        })

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
        add_unique(
            recommendations,
            "Request independently verifiable evidence such as "
            "an official company email, formal offer letter and "
            "documented selection process.",
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
        "recommendations": recommendations,
        "verification_factors": verification_factors,
        "value_factors": value_factors,
    }
