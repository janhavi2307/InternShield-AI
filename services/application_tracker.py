from datetime import date, datetime


APPLICATION_STATUSES = (
    "saved",
    "applied",
    "interview",
    "offer",
    "rejected",
)


# =========================================================
# DATE HELPERS
# =========================================================

def _optional_date(
    value,
    field_label,
    errors,
):
    """
    Convert an optional YYYY-MM-DD form value into
    an ISO date string.
    """

    value = (value or "").strip()

    if not value:
        return None

    try:
        return date.fromisoformat(
            value
        ).isoformat()

    except ValueError:
        errors.append(
            f"Enter a valid {field_label.lower()}."
        )

        return None


def _parse_date(value):
    """
    Safely convert a stored date value into a date object.
    """

    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(
            str(value)[:10]
        )

    except (ValueError, TypeError):
        return None


def _parse_datetime_date(value):
    """
    Safely extract a date from a Supabase timestamp such as:

    2026-08-15T15:24:10.123+00:00
    """

    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        cleaned = str(value).replace(
            "Z",
            "+00:00",
        )

        return datetime.fromisoformat(
            cleaned
        ).date()

    except (ValueError, TypeError):
        try:
            return date.fromisoformat(
                str(value)[:10]
            )

        except (ValueError, TypeError):
            return None


# =========================================================
# APPLICATION FORM VALIDATION
# =========================================================

def validate_application_payload(form):
    company_name = (
        form.get("company_name")
        or ""
    ).strip()

    role_title = (
        form.get("role_title")
        or ""
    ).strip()

    status = (
        form.get("status")
        or "saved"
    ).strip().lower()

    notes = (
        form.get("notes")
        or ""
    ).strip()

    analysis_id = (
        form.get("analysis_id")
        or ""
    ).strip() or None

    errors = []

    # -----------------------------------------------------
    # Required fields
    # -----------------------------------------------------

    if not company_name:
        errors.append(
            "Company name is required."
        )

    if not role_title:
        errors.append(
            "Role title is required."
        )

    # -----------------------------------------------------
    # Status validation
    # -----------------------------------------------------

    if status not in APPLICATION_STATUSES:
        errors.append(
            "Select a valid application stage."
        )

    # -----------------------------------------------------
    # Length validation
    # -----------------------------------------------------

    if len(company_name) > 120:
        errors.append(
            "Company name must be "
            "120 characters or fewer."
        )

    if len(role_title) > 120:
        errors.append(
            "Role title must be "
            "120 characters or fewer."
        )

    if len(notes) > 2000:
        errors.append(
            "Notes must be 2,000 "
            "characters or fewer."
        )

    # -----------------------------------------------------
    # Payload
    # -----------------------------------------------------

    payload = {
        "company_name": company_name,
        "role_title": role_title,
        "status": status,

        "application_deadline": _optional_date(
            form.get(
                "application_deadline"
            ),
            "Application deadline",
            errors,
        ),

        "interview_date": _optional_date(
            form.get(
                "interview_date"
            ),
            "Interview date",
            errors,
        ),

        "notes": notes or None,

        "analysis_id": analysis_id,
    }

    return payload, errors


# =========================================================
# TRACKER STATISTICS
# =========================================================

def application_statistics(
    applications,
):
    """
    Return counts for every application stage.
    """

    statistics = {
        status: 0
        for status in APPLICATION_STATUSES
    }

    statistics["total"] = len(
        applications
    )

    for application in applications:

        status = application.get(
            "status"
        )

        if status in statistics:
            statistics[status] += 1

    return statistics


# =========================================================
# SMART ALERT HELPERS
# =========================================================

def _build_alert(
    application,
    alert_type,
    severity,
    title,
    message,
    action_label=None,
    target_date=None,
    priority=50,
):
    """
    Create one normalized alert object.
    """

    return {
        "application_id": application.get(
            "id"
        ),

        "analysis_id": application.get(
            "analysis_id"
        ),

        "company_name": (
            application.get(
                "company_name"
            )
            or "Unknown company"
        ),

        "role_title": (
            application.get(
                "role_title"
            )
            or "Internship opportunity"
        ),

        "status": application.get(
            "status"
        ),

        "alert_type": alert_type,

        "severity": severity,

        "title": title,

        "message": message,

        "action_label": action_label,

        "target_date": (
            target_date.isoformat()
            if isinstance(
                target_date,
                date,
            )
            else target_date
        ),

        "priority": priority,
    }


# =========================================================
# SINGLE APPLICATION ALERTS
# =========================================================

def application_alerts(
    application,
    today=None,
):
    """
    Generate smart alerts for one tracked application.

    Possible alerts include:

    - Deadline today
    - Deadline tomorrow
    - Deadline approaching
    - Deadline passed
    - Interview today
    - Interview tomorrow
    - Interview approaching
    - Follow-up recommended
    - Offer received
    """

    if today is None:
        today = date.today()

    alerts = []

    status = (
        application.get("status")
        or "saved"
    ).lower()

    company = (
        application.get(
            "company_name"
        )
        or "Unknown company"
    )

    role = (
        application.get(
            "role_title"
        )
        or "Internship opportunity"
    )

    deadline = _parse_date(
        application.get(
            "application_deadline"
        )
    )

    interview_date = _parse_date(
        application.get(
            "interview_date"
        )
    )

    # -----------------------------------------------------
    # APPLICATION DEADLINE
    # -----------------------------------------------------

    if (
        deadline
        and status not in {
            "offer",
            "rejected",
        }
    ):

        deadline_days = (
            deadline - today
        ).days

        # Deadline already passed
        if deadline_days < 0:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="deadline_passed",
                    severity="danger",
                    title="Application deadline passed",
                    message=(
                        f"The deadline for {role} at "
                        f"{company} passed "
                        f"{abs(deadline_days)} "
                        f"day"
                        f"{'' if abs(deadline_days) == 1 else 's'} "
                        "ago."
                    ),
                    action_label=(
                        "Review application"
                    ),
                    target_date=deadline,
                    priority=100,
                )
            )

        # Deadline today
        elif deadline_days == 0:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="deadline_today",
                    severity="danger",
                    title="Application deadline today",
                    message=(
                        f"The application deadline for "
                        f"{role} at {company} is today."
                    ),
                    action_label=(
                        "Complete application"
                    ),
                    target_date=deadline,
                    priority=98,
                )
            )

        # Deadline tomorrow
        elif deadline_days == 1:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="deadline_tomorrow",
                    severity="warning",
                    title="Deadline tomorrow",
                    message=(
                        f"The application deadline for "
                        f"{role} at {company} is tomorrow."
                    ),
                    action_label=(
                        "Review deadline"
                    ),
                    target_date=deadline,
                    priority=90,
                )
            )

        # Deadline in next 3 days
        elif deadline_days <= 3:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="deadline_soon",
                    severity="warning",
                    title=(
                        f"Deadline in "
                        f"{deadline_days} days"
                    ),
                    message=(
                        f"The application deadline for "
                        f"{role} at {company} is "
                        f"approaching."
                    ),
                    action_label=(
                        "Prepare application"
                    ),
                    target_date=deadline,
                    priority=82,
                )
            )

        # Deadline within one week
        elif deadline_days <= 7:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="deadline_upcoming",
                    severity="info",
                    title=(
                        f"Deadline in "
                        f"{deadline_days} days"
                    ),
                    message=(
                        f"Plan ahead for the "
                        f"{role} application at "
                        f"{company}."
                    ),
                    action_label=(
                        "Review application"
                    ),
                    target_date=deadline,
                    priority=65,
                )
            )

    # -----------------------------------------------------
    # INTERVIEW ALERTS
    # -----------------------------------------------------

    if (
        interview_date
        and status not in {
            "offer",
            "rejected",
        }
    ):

        interview_days = (
            interview_date - today
        ).days

        # Interview today
        if interview_days == 0:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="interview_today",
                    severity="danger",
                    title="Interview today",
                    message=(
                        f"Your interview for {role} "
                        f"at {company} is scheduled "
                        "for today."
                    ),
                    action_label=(
                        "Prepare for interview"
                    ),
                    target_date=interview_date,
                    priority=110,
                )
            )

        # Interview tomorrow
        elif interview_days == 1:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="interview_tomorrow",
                    severity="warning",
                    title="Interview tomorrow",
                    message=(
                        f"Your interview for {role} "
                        f"at {company} is tomorrow."
                    ),
                    action_label=(
                        "Prepare for interview"
                    ),
                    target_date=interview_date,
                    priority=105,
                )
            )

        # Interview in next 3 days
        elif 1 < interview_days <= 3:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="interview_soon",
                    severity="warning",
                    title=(
                        f"Interview in "
                        f"{interview_days} days"
                    ),
                    message=(
                        f"Prepare for your upcoming "
                        f"{role} interview at {company}."
                    ),
                    action_label=(
                        "Review preparation"
                    ),
                    target_date=interview_date,
                    priority=95,
                )
            )

        # Interview within one week
        elif 3 < interview_days <= 7:

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type="interview_upcoming",
                    severity="info",
                    title=(
                        f"Interview in "
                        f"{interview_days} days"
                    ),
                    message=(
                        f"Your interview for {role} "
                        f"at {company} is approaching."
                    ),
                    action_label=(
                        "Start preparation"
                    ),
                    target_date=interview_date,
                    priority=70,
                )
            )

        # Old interview date without stage update
        elif (
            interview_days < 0
            and status == "interview"
        ):

            days_since_interview = abs(
                interview_days
            )

            alerts.append(
                _build_alert(
                    application=application,
                    alert_type=(
                        "interview_follow_up"
                    ),
                    severity="info",
                    title=(
                        "Interview follow-up recommended"
                    ),
                    message=(
                        f"The interview for {role} at "
                        f"{company} was "
                        f"{days_since_interview} "
                        f"day"
                        f"{'' if days_since_interview == 1 else 's'} "
                        "ago. Consider updating the "
                        "application stage or following up."
                    ),
                    action_label=(
                        "Update application"
                    ),
                    target_date=interview_date,
                    priority=72,
                )
            )

    # -----------------------------------------------------
    # GENERAL FOLLOW-UP AFTER APPLYING
    # -----------------------------------------------------

    if (
        status == "applied"
        and not interview_date
    ):

        updated_date = _parse_datetime_date(
            application.get(
                "updated_at"
            )
            or application.get(
                "created_at"
            )
        )

        if updated_date:

            days_waiting = (
                today - updated_date
            ).days

            if days_waiting >= 14:

                alerts.append(
                    _build_alert(
                        application=application,
                        alert_type=(
                            "follow_up_overdue"
                        ),
                        severity="warning",
                        title=(
                            "Follow-up recommended"
                        ),
                        message=(
                            f"You have been waiting "
                            f"{days_waiting} days after "
                            f"applying for {role} at "
                            f"{company}. Consider sending "
                            "a polite follow-up."
                        ),
                        action_label=(
                            "Review application"
                        ),
                        priority=75,
                    )
                )

            elif days_waiting >= 7:

                alerts.append(
                    _build_alert(
                        application=application,
                        alert_type=(
                            "follow_up_recommended"
                        ),
                        severity="info",
                        title=(
                            "Consider following up"
                        ),
                        message=(
                            f"It has been "
                            f"{days_waiting} days since "
                            f"your latest update for "
                            f"{role} at {company}."
                        ),
                        action_label=(
                            "Review application"
                        ),
                        priority=55,
                    )
                )

    # -----------------------------------------------------
    # OFFER RECEIVED
    # -----------------------------------------------------

    if status == "offer":

        alerts.append(
            _build_alert(
                application=application,
                alert_type="offer_received",
                severity="success",
                title="Offer received",
                message=(
                    f"{role} at {company} is currently "
                    "marked as an offer. Review the "
                    "assessment, compensation, schedule "
                    "and written terms before deciding."
                ),
                action_label=(
                    "Review offer"
                ),
                priority=60,
            )
        )

    # -----------------------------------------------------
    # SORT MOST IMPORTANT FIRST
    # -----------------------------------------------------

    alerts.sort(
        key=lambda alert: alert.get(
            "priority",
            0,
        ),
        reverse=True,
    )

    return alerts


# =========================================================
# ALL APPLICATION ALERTS
# =========================================================

def build_application_alerts(
    applications,
    today=None,
):
    """
    Generate a combined alert list for all tracked
    internship applications.
    """

    if today is None:
        today = date.today()

    alerts = []

    for application in applications:

        alerts.extend(
            application_alerts(
                application,
                today=today,
            )
        )

    alerts.sort(
        key=lambda alert: (
            -alert.get(
                "priority",
                0,
            ),
            alert.get(
                "target_date"
            )
            or "9999-12-31",
        )
    )

    return alerts


# =========================================================
# ALERT STATISTICS
# =========================================================

def alert_statistics(alerts):
    """
    Provide simple counts for the alerts UI.
    """

    statistics = {
        "total": len(alerts),
        "danger": 0,
        "warning": 0,
        "info": 0,
        "success": 0,
    }

    for alert in alerts:

        severity = alert.get(
            "severity"
        )

        if severity in statistics:
            statistics[severity] += 1

    return statistics