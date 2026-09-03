"""
InternShield Contact & Support system.

Features:
- student support requests
- student follow-up thread
- admin-only support inbox
- admin replies and request status management
- SMTP email notifications
- server-only Supabase service-role access for the admin inbox
"""

from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from functools import wraps
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urljoin

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from supabase import create_client

from supabase_client import get_supabase_client


VALID_CATEGORIES = {
    "assessment_question": "Assessment question",
    "technical_problem": "Technical problem",
    "feedback": "Feedback / suggestion",
    "account_help": "Account help",
    "other": "Other",
}

VALID_STATUSES = {
    "open",
    "reviewing",
    "resolved",
}


def _admin_emails() -> list[str]:
    raw = (
        os.getenv("SUPPORT_ADMIN_EMAILS")
        or os.getenv("SUPPORT_ADMIN_EMAIL")
        or ""
    )

    return [
        item.strip().lower()
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    ]


def is_support_admin() -> bool:
    current_email = (
        session.get("user_email")
        or ""
    ).strip().lower()

    return (
        bool(current_email)
        and current_email in set(_admin_emails())
    )


def _login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "Please log in to continue.",
                "warning",
            )
            return redirect(
                url_for("login")
            )

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped_view


def _admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash(
                "Please log in to continue.",
                "warning",
            )
            return redirect(
                url_for("login")
            )

        if not is_support_admin():
            flash(
                "You do not have access to the support inbox.",
                "danger",
            )
            return redirect(
                url_for("dashboard")
            )

        return view_function(
            *args,
            **kwargs,
        )

    return wrapped_view


def _authenticated_supabase():
    supabase = get_supabase_client()

    auth_response = supabase.auth.set_session(
        session["access_token"],
        session["refresh_token"],
    )

    if auth_response.session:
        session["access_token"] = (
            auth_response.session.access_token
        )

        session["refresh_token"] = (
            auth_response.session.refresh_token
        )

    return supabase


def _service_supabase():
    """
    Build the server-only Supabase client used by Support Inbox.

    Preferred:
        SUPABASE_SECRET_KEY=sb_secret_...

    Legacy fallback:
        SUPABASE_SERVICE_ROLE_KEY=<legacy service_role JWT>

    Both elevated key types bypass RLS. Never expose either key
    in HTML, JavaScript, screenshots, or browser code.
    """

    supabase_url = (
        os.getenv("SUPABASE_URL")
        or ""
    ).strip()

    elevated_key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is not configured."
        )

    if not elevated_key:
        raise RuntimeError(
            "No elevated Supabase server key is configured. "
            "Set SUPABASE_SECRET_KEY (recommended) or "
            "SUPABASE_SERVICE_ROLE_KEY (legacy)."
        )

    if elevated_key == "...":
        raise RuntimeError(
            "The Supabase elevated key is still the placeholder '...'. "
            "Copy the real Secret key from Supabase Settings > API Keys."
        )

    return create_client(
        supabase_url,
        elevated_key,
    )


def _truthy(
    value: str | None,
    default: bool = False,
) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _public_url(
    endpoint: str,
    **values,
) -> str:
    """
    Build a public URL for email messages.

    During local development, if PUBLIC_BASE_URL is not set,
    Flask uses the current request host such as 127.0.0.1:5000.

    In production, set:
        PUBLIC_BASE_URL=https://your-real-domain.com
    """

    configured_base = (
        os.getenv("PUBLIC_BASE_URL")
        or os.getenv("APP_BASE_URL")
        or ""
    ).strip()

    if configured_base:
        relative_path = url_for(
            endpoint,
            _external=False,
            **values,
        )

        return urljoin(
            configured_base.rstrip("/") + "/",
            relative_path.lstrip("/"),
        )

    return url_for(
        endpoint,
        _external=True,
        **values,
    )


def _email_shell(
    *,
    eyebrow: str,
    title: str,
    intro: str,
    message_text: str,
    button_label: str,
    button_url: str,
    meta_rows: list[tuple[str, str]] | None = None,
) -> str:
    """
    Build a compact branded HTML email using inline styles so it
    renders reliably in Gmail and other common email clients.
    """

    safe_eyebrow = html.escape(
        eyebrow or ""
    )

    safe_title = html.escape(
        title or ""
    )

    safe_intro = html.escape(
        intro or ""
    )

    safe_message = html.escape(
        message_text or ""
    ).replace(
        "\n",
        "<br>",
    )

    safe_button_label = html.escape(
        button_label or "Open InternShield"
    )

    safe_button_url = html.escape(
        button_url or "",
        quote=True,
    )

    rows_html = ""

    for label, value in (
        meta_rows
        or []
    ):
        safe_label = html.escape(
            str(label or "")
        )

        safe_value = html.escape(
            str(value or "")
        )

        rows_html += f"""
        <tr>
            <td
                style="
                    padding:8px 0;
                    width:125px;
                    color:#8d90a6;
                    font-size:12px;
                    vertical-align:top;
                "
            >
                {safe_label}
            </td>

            <td
                style="
                    padding:8px 0;
                    color:#f4f3ff;
                    font-size:13px;
                    font-weight:600;
                    vertical-align:top;
                "
            >
                {safe_value}
            </td>
        </tr>
        """

    meta_table = ""

    if rows_html:
        meta_table = (
            "<table role='presentation' width='100%' "
            "cellspacing='0' cellpadding='0' "
            "style='margin-bottom:18px;'>"
            + rows_html
            + "</table>"
        )

    return f"""<!DOCTYPE html>
<html>
<body
    style="
        margin:0;
        padding:0;
        background:#080912;
        color:#f8f8ff;
        font-family:Arial,Helvetica,sans-serif;
    "
>
<table
    role="presentation"
    width="100%"
    cellspacing="0"
    cellpadding="0"
    style="
        width:100%;
        background:#080912;
        padding:28px 12px;
    "
>
<tr>
<td align="center">

<table
    role="presentation"
    width="100%"
    cellspacing="0"
    cellpadding="0"
    style="
        width:100%;
        max-width:620px;
        border:1px solid #25283b;
        border-radius:18px;
        background:#111321;
        overflow:hidden;
    "
>
<tr>
<td
    style="
        padding:28px 30px 20px;
        border-bottom:1px solid #25283b;
    "
>
    <div
        style="
            margin-bottom:18px;
            font-size:20px;
            line-height:1;
            font-weight:800;
            color:#ffffff;
        "
    >
        InternShield
        <span style="color:#aa99ff;">AI</span>
    </div>

    <div
        style="
            margin-bottom:8px;
            color:#aa99ff;
            font-size:11px;
            font-weight:800;
            letter-spacing:1.1px;
            text-transform:uppercase;
        "
    >
        {safe_eyebrow}
    </div>

    <h1
        style="
            margin:0 0 10px;
            color:#ffffff;
            font-size:24px;
            line-height:1.25;
        "
    >
        {safe_title}
    </h1>

    <p
        style="
            margin:0;
            color:#9ea1b5;
            font-size:14px;
            line-height:1.6;
        "
    >
        {safe_intro}
    </p>
</td>
</tr>

<tr>
<td style="padding:24px 30px 28px;">

    {meta_table}

    <div
        style="
            margin:0 0 22px;
            padding:16px 18px;
            border:1px solid #2c3047;
            border-radius:14px;
            background:#181b2e;
            color:#e7e6f2;
            font-size:14px;
            line-height:1.65;
        "
    >
        {safe_message}
    </div>

    <a
        href="{safe_button_url}"
        style="
            display:inline-block;
            padding:13px 18px;
            border-radius:11px;
            background:#7459ee;
            color:#ffffff;
            font-size:13px;
            font-weight:800;
            text-decoration:none;
        "
    >
        {safe_button_label}
    </a>

    <p
        style="
            margin:22px 0 0;
            color:#73778d;
            font-size:11px;
            line-height:1.55;
        "
    >
        This message was sent by InternShield Support.
        Open the link only if you recognize this support request.
    </p>

</td>
</tr>
</table>

</td>
</tr>
</table>
</body>
</html>"""



def _send_email_via_brevo(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
) -> dict:
    recipients = [
        item.strip()
        for item in recipients
        if item and item.strip()
    ]

    if not recipients:
        return {
            "sent": False,
            "reason": "No recipient email is configured.",
            "provider": "brevo",
        }

    api_key = (
        os.getenv("BREVO_API_KEY")
        or ""
    ).strip()

    sender_email = (
        os.getenv("BREVO_SENDER_EMAIL")
        or ""
    ).strip()

    sender_name = (
        os.getenv("BREVO_SENDER_NAME")
        or "InternShield Support"
    ).strip()

    if not api_key:
        return {
            "sent": False,
            "reason": "BREVO_API_KEY is not configured.",
            "provider": "brevo",
        }

    if not sender_email:
        return {
            "sent": False,
            "reason": "BREVO_SENDER_EMAIL is not configured.",
            "provider": "brevo",
        }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {"email": recipient}
            for recipient in recipients
        ],
        "subject": subject,
        "textContent": body,
    }

    if html_body:
        payload["htmlContent"] = html_body

    if reply_to:
        payload["replyTo"] = {
            "email": reply_to,
        }

    api_request = urllib_request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(
            api_request,
            timeout=20,
        ) as response:
            status_code = response.getcode() or 0

        if 200 <= status_code < 300:
            return {
                "sent": True,
                "reason": "",
                "provider": "brevo",
            }

        return {
            "sent": False,
            "reason": f"Brevo returned HTTP {status_code}.",
            "provider": "brevo",
        }

    except urllib_error.HTTPError as exc:
        try:
            details = (
                exc.read()
                .decode("utf-8", errors="replace")
            )
        except Exception:
            details = str(exc)

        return {
            "sent": False,
            "reason": (
                f"Brevo API HTTP {exc.code}: "
                f"{details[:500]}"
            ),
            "provider": "brevo",
        }

    except urllib_error.URLError as exc:
        return {
            "sent": False,
            "reason": (
                "Brevo API connection failed: "
                f"{exc.reason}"
            ),
            "provider": "brevo",
        }

    except Exception as exc:
        return {
            "sent": False,
            "reason": f"Brevo email failed: {exc}",
            "provider": "brevo",
        }


def _send_email(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    reply_to: str | None = None,
) -> dict:
    email_provider = (
        os.getenv("EMAIL_PROVIDER")
        or ""
    ).strip().lower()

    brevo_api_key = (
        os.getenv("BREVO_API_KEY")
        or ""
    ).strip()

    if (
        email_provider == "brevo"
        or bool(brevo_api_key)
    ):
        return _send_email_via_brevo(
            recipients=recipients,
            subject=subject,
            body=body,
            html_body=html_body,
            reply_to=reply_to,
        )

    # Existing SMTP code remains as a local fallback.
    recipients = [
        item.strip()
        for item in recipients
        if item and item.strip()
    ]

    if not recipients:
        return {
            "sent": False,
            "reason": "No recipient email is configured.",
        }

    smtp_host = (
        os.getenv("SMTP_HOST")
        or ""
    ).strip()

    smtp_port_text = (
        os.getenv("SMTP_PORT")
        or "587"
    ).strip()

    smtp_user = (
        os.getenv("SMTP_USER")
        or ""
    ).strip()

    smtp_password = (
        os.getenv("SMTP_PASSWORD")
        or ""
    ).strip()

    from_email = (
        os.getenv("SMTP_FROM_EMAIL")
        or smtp_user
    ).strip()

    from_name = (
        os.getenv("SMTP_FROM_NAME")
        or "InternShield Support"
    ).strip()

    if not smtp_host or not from_email:
        return {
            "sent": False,
            "reason": (
                "SMTP is not configured. Set SMTP_HOST and "
                "SMTP_FROM_EMAIL/SMTP_USER."
            ),
        }

    try:
        smtp_port = int(
            smtp_port_text
        )
    except ValueError:
        return {
            "sent": False,
            "reason": "SMTP_PORT is not a valid number.",
        }

    use_ssl = _truthy(
        os.getenv("SMTP_USE_SSL"),
        default=(smtp_port == 465),
    )

    use_tls = _truthy(
        os.getenv("SMTP_USE_TLS"),
        default=(not use_ssl),
    )

    email_message = EmailMessage()

    email_message["Subject"] = subject

    email_message["From"] = formataddr(
        (
            from_name,
            from_email,
        )
    )

    email_message["To"] = ", ".join(
        recipients
    )

    if reply_to:
        email_message["Reply-To"] = (
            reply_to
        )

    email_message.set_content(
        body
    )

    if html_body:
        email_message.add_alternative(
            html_body,
            subtype="html",
        )

    context = (
        ssl.create_default_context()
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                timeout=20,
                context=context,
            ) as smtp:
                if smtp_user:
                    smtp.login(
                        smtp_user,
                        smtp_password,
                    )

                smtp.send_message(
                    email_message
                )

        else:
            with smtplib.SMTP(
                smtp_host,
                smtp_port,
                timeout=20,
            ) as smtp:
                smtp.ehlo()

                if use_tls:
                    smtp.starttls(
                        context=context
                    )

                    smtp.ehlo()

                if smtp_user:
                    smtp.login(
                        smtp_user,
                        smtp_password,
                    )

                smtp.send_message(
                    email_message
                )

        return {
            "sent": True,
            "reason": "",
        }

    except Exception as exc:
        return {
            "sent": False,
            "reason": str(exc),
        }

def _notify_admins(
    *,
    support_request: dict,
    event_label: str,
    message_text: str,
) -> dict:
    admins = (
        _admin_emails()
    )

    if not admins:
        return {
            "sent": False,
            "reason": (
                "SUPPORT_ADMIN_EMAILS is not configured."
            ),
        }

    request_id = (
        support_request.get("id")
        or ""
    )

    inbox_link = _public_url(
        "admin_support_detail",
        request_id=request_id,
    )

    user_email = (
        support_request.get("user_email")
        or session.get("user_email")
        or ""
    )

    user_name = (
        support_request.get("user_name")
        or "Student"
    )

    request_subject = (
        support_request.get("subject")
        or "Support request"
    )

    category = (
        support_request.get("category")
        or "Not available"
    )

    readable_category = (
        str(category)
        .replace(
            "_",
            " ",
        )
        .title()
    )

    subject = (
        "[InternShield Support] "
        + event_label
        + ": "
        + request_subject
    )

    body = (
        f"{event_label}\n\n"
        f"Student: {user_name}\n"
        f"Email: {user_email or 'Not available'}\n"
        f"Category: {readable_category}\n"
        f"Subject: {request_subject}\n\n"
        f"{message_text}\n\n"
        f"Open Support Inbox:\n{inbox_link}\n"
    )

    html_body = _email_shell(
        eyebrow="Support inbox",
        title=event_label,
        intro=(
            "A student support conversation needs your attention."
        ),
        message_text=message_text,
        button_label="Open Support Inbox",
        button_url=inbox_link,
        meta_rows=[
            (
                "Student",
                user_name,
            ),
            (
                "Email",
                user_email
                or "Not available",
            ),
            (
                "Category",
                readable_category,
            ),
            (
                "Subject",
                request_subject,
            ),
        ],
    )

    return _send_email(
        recipients=admins,
        subject=subject,
        body=body,
        html_body=html_body,
        reply_to=(
            user_email
            or None
        ),
    )

def register_support_routes(app):
    if "support" in app.view_functions:
        return

    @app.route(
        "/support",
        methods=["GET", "POST"],
    )
    @_login_required
    def support():
        try:
            supabase = (
                _authenticated_supabase()
            )

        except Exception:
            flash(
                "Unable to open Contact & Support right now.",
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        form_data = {
            "category": "",
            "subject": "",
            "message": "",
        }

        if request.method == "POST":
            category = (
                request.form.get(
                    "category",
                    "",
                )
                or ""
            ).strip()

            subject = (
                request.form.get(
                    "subject",
                    "",
                )
                or ""
            ).strip()

            message = (
                request.form.get(
                    "message",
                    "",
                )
                or ""
            ).strip()

            form_data = {
                "category": category,
                "subject": subject,
                "message": message,
            }

            errors = []

            if category not in VALID_CATEGORIES:
                errors.append(
                    "Choose a valid support category."
                )

            if not subject:
                errors.append(
                    "Subject is required."
                )

            if len(subject) > 140:
                errors.append(
                    "Subject must be 140 characters or fewer."
                )

            if not message:
                errors.append(
                    "Message is required."
                )

            if (
                message
                and len(message) < 10
            ):
                errors.append(
                    "Please add a little more detail to your message."
                )

            if len(message) > 3000:
                errors.append(
                    "Message must be 3000 characters or fewer."
                )

            if errors:
                for error in errors:
                    flash(
                        error,
                        "danger",
                    )

            else:
                try:
                    now_iso = datetime.now(
                        timezone.utc
                    ).isoformat()

                    response = (
                        supabase
                        .table(
                            "support_requests"
                        )
                        .insert({
                            "user_id": (
                                session["user_id"]
                            ),
                            "user_email": (
                                session.get(
                                    "user_email"
                                )
                                or None
                            ),
                            "user_name": (
                                session.get(
                                    "full_name"
                                )
                                or "Student"
                            ),
                            "category": category,
                            "subject": subject,
                            "message": message,
                            "status": "open",
                            "updated_at": now_iso,
                        })
                        .execute()
                    )

                    if not response.data:
                        raise ValueError(
                            "Support request was not saved."
                        )

                    saved_request = (
                        response.data[0]
                    )

                    mail_result = _notify_admins(
                        support_request=(
                            saved_request
                        ),
                        event_label=(
                            "New support request"
                        ),
                        message_text=message,
                    )

                    if not mail_result.get(
                        "sent"
                    ):
                        app.logger.warning(
                            "Support notification email was not sent: %s",
                            mail_result.get(
                                "reason"
                            ),
                        )

                    flash(
                        "Your message was submitted successfully.",
                        "success",
                    )

                    return redirect(
                        url_for(
                            "support_request_detail",
                            request_id=(
                                saved_request[
                                    "id"
                                ]
                            ),
                        )
                    )

                except Exception:
                    app.logger.exception(
                        "Support request could not be saved"
                    )

                    flash(
                        "Your support request could not be submitted. "
                        "Check the Flask terminal for details.",
                        "danger",
                    )

        recent_requests = []

        try:
            response = (
                supabase
                .table(
                    "support_requests"
                )
                .select(
                    "id, category, subject, status, "
                    "created_at, updated_at"
                )
                .eq(
                    "user_id",
                    session["user_id"],
                )
                .order(
                    "updated_at",
                    desc=True,
                )
                .limit(5)
                .execute()
            )

            recent_requests = (
                response.data
                or []
            )

        except Exception:
            app.logger.exception(
                "Recent support requests could not be loaded"
            )

        return render_template(
            "support.html",
            categories=VALID_CATEGORIES,
            form_data=form_data,
            recent_requests=recent_requests,
        )

    @app.route(
        "/support/<request_id>",
        methods=["GET", "POST"],
    )
    @_login_required
    def support_request_detail(
        request_id,
    ):
        try:
            supabase = (
                _authenticated_supabase()
            )

            request_response = (
                supabase
                .table(
                    "support_requests"
                )
                .select("*")
                .eq(
                    "id",
                    request_id,
                )
                .eq(
                    "user_id",
                    session["user_id"],
                )
                .limit(1)
                .execute()
            )

            if not request_response.data:
                flash(
                    "Support request not found.",
                    "warning",
                )

                return redirect(
                    url_for("support")
                )

            support_request = (
                request_response.data[0]
            )

        except Exception:
            app.logger.exception(
                "Support request could not be loaded"
            )

            flash(
                "Support request could not be loaded.",
                "danger",
            )

            return redirect(
                url_for("support")
            )

        if request.method == "POST":
            follow_up = (
                request.form.get(
                    "follow_up",
                    "",
                )
                or ""
            ).strip()

            if len(follow_up) < 5:
                flash(
                    "Add a little more detail to your follow-up.",
                    "danger",
                )

            elif len(follow_up) > 3000:
                flash(
                    "Follow-up must be 3000 characters or fewer.",
                    "danger",
                )

            else:
                try:
                    response = (
                        supabase
                        .table(
                            "support_replies"
                        )
                        .insert({
                            "request_id": (
                                request_id
                            ),
                            "sender_type": (
                                "user"
                            ),
                            "sender_email": (
                                session.get(
                                    "user_email"
                                )
                                or None
                            ),
                            "message": (
                                follow_up
                            ),
                        })
                        .execute()
                    )

                    if not response.data:
                        raise ValueError(
                            "Support follow-up was not saved."
                        )

                    try:
                        service_supabase = (
                            _service_supabase()
                        )

                        service_supabase.table(
                            "support_requests"
                        ).update({
                            "status": "open",
                            "updated_at": datetime.now(
                                timezone.utc
                            ).isoformat(),
                        }).eq(
                            "id",
                            request_id,
                        ).execute()

                    except Exception:
                        app.logger.exception(
                            "Support request could not be re-opened"
                        )

                    mail_result = (
                        _notify_admins(
                            support_request=(
                                support_request
                            ),
                            event_label=(
                                "Student follow-up"
                            ),
                            message_text=(
                                follow_up
                            ),
                        )
                    )

                    if not mail_result.get(
                        "sent"
                    ):
                        app.logger.warning(
                            "Support follow-up notification was not sent: %s",
                            mail_result.get(
                                "reason"
                            ),
                        )

                    flash(
                        "Your follow-up was added.",
                        "success",
                    )

                    return redirect(
                        url_for(
                            "support_request_detail",
                            request_id=(
                                request_id
                            ),
                        )
                    )

                except Exception:
                    app.logger.exception(
                        "Support follow-up could not be saved"
                    )

                    flash(
                        "Your follow-up could not be saved.",
                        "danger",
                    )

        replies = []

        try:
            reply_response = (
                supabase
                .table(
                    "support_replies"
                )
                .select("*")
                .eq(
                    "request_id",
                    request_id,
                )
                .order(
                    "created_at",
                )
                .execute()
            )

            replies = (
                reply_response.data
                or []
            )

        except Exception:
            app.logger.exception(
                "Support replies could not be loaded"
            )

        return render_template(
            "support_request_detail.html",
            support_request=(
                support_request
            ),
            replies=replies,
        )

    @app.route(
        "/admin/support",
    )
    @_admin_required
    def admin_support():
        try:
            supabase = (
                _service_supabase()
            )

        except Exception as exc:
            flash(
                str(exc),
                "danger",
            )

            return redirect(
                url_for("dashboard")
            )

        status_filter = (
            request.args.get(
                "status",
                "all",
            )
            or "all"
        ).strip().lower()

        search_query = (
            request.args.get(
                "q",
                "",
            )
            or ""
        ).strip().lower()

        try:
            response = (
                supabase
                .table(
                    "support_requests"
                )
                .select("*")
                .order(
                    "updated_at",
                    desc=True,
                )
                .execute()
            )

            all_requests = (
                response.data
                or []
            )

        except Exception as exc:
            app.logger.exception(
                "Support inbox could not be loaded"
            )

            flash(
                "Support Inbox could not read all requests. "
                "Check the server-side Supabase Secret/service-role key. "
                f"Details: {exc}",
                "danger",
            )

            all_requests = []

        statistics = {
            "total": len(
                all_requests
            ),
            "open": sum(
                1
                for item in all_requests
                if item.get("status")
                == "open"
            ),
            "reviewing": sum(
                1
                for item in all_requests
                if item.get("status")
                == "reviewing"
            ),
            "resolved": sum(
                1
                for item in all_requests
                if item.get("status")
                == "resolved"
            ),
        }

        filtered_requests = (
            all_requests
        )

        if status_filter in VALID_STATUSES:
            filtered_requests = [
                item
                for item in filtered_requests
                if item.get(
                    "status"
                ) == status_filter
            ]

        if search_query:
            filtered_requests = [
                item
                for item in filtered_requests
                if search_query in " ".join([
                    str(
                        item.get(
                            "subject"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "user_email"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "user_name"
                        )
                        or ""
                    ),
                    str(
                        item.get(
                            "category"
                        )
                        or ""
                    ),
                ]).lower()
            ]

        return render_template(
            "admin_support.html",
            support_requests=(
                filtered_requests
            ),
            statistics=statistics,
            status_filter=status_filter,
            search_query=search_query,
        )

    @app.route(
        "/admin/support/<request_id>/delete",
        methods=["POST"],
    )
    @_admin_required
    def admin_support_delete(
        request_id,
    ):
        status_filter = (
            request.form.get(
                "status",
                "all",
            )
            or "all"
        ).strip().lower()

        search_query = (
            request.form.get(
                "q",
                "",
            )
            or ""
        ).strip()

        redirect_values = {}

        if (
            status_filter == "all"
            or status_filter in VALID_STATUSES
        ):
            redirect_values["status"] = (
                status_filter
            )

        if search_query:
            redirect_values["q"] = (
                search_query
            )

        try:
            supabase = (
                _service_supabase()
            )

            response = (
                supabase
                .table(
                    "support_requests"
                )
                .select(
                    "id, subject"
                )
                .eq(
                    "id",
                    request_id,
                )
                .limit(1)
                .execute()
            )

            if not response.data:
                flash(
                    "Support request was already removed "
                    "or could not be found.",
                    "warning",
                )

                return redirect(
                    url_for(
                        "admin_support",
                        **redirect_values,
                    )
                )

            support_request = (
                response.data[0]
            )

            (
                supabase
                .table(
                    "support_requests"
                )
                .delete()
                .eq(
                    "id",
                    request_id,
                )
                .execute()
            )

            verification = (
                supabase
                .table(
                    "support_requests"
                )
                .select("id")
                .eq(
                    "id",
                    request_id,
                )
                .limit(1)
                .execute()
            )

            if verification.data:
                raise ValueError(
                    "Support request still exists "
                    "after delete operation."
                )

            subject = (
                support_request.get(
                    "subject"
                )
                or "Support request"
            )

            flash(
                f'"{subject}" was deleted permanently.',
                "success",
            )

        except Exception:
            app.logger.exception(
                "Admin support request could not be deleted"
            )

            flash(
                "The support request could not be deleted.",
                "danger",
            )

        return redirect(
            url_for(
                "admin_support",
                **redirect_values,
            )
        )


    @app.route(
        "/admin/support/<request_id>",
        methods=["GET", "POST"],
    )
    @_admin_required
    def admin_support_detail(
        request_id,
    ):
        try:
            supabase = (
                _service_supabase()
            )

            response = (
                supabase
                .table(
                    "support_requests"
                )
                .select("*")
                .eq(
                    "id",
                    request_id,
                )
                .limit(1)
                .execute()
            )

            if not response.data:
                flash(
                    "Support request not found.",
                    "warning",
                )

                return redirect(
                    url_for(
                        "admin_support"
                    )
                )

            support_request = (
                response.data[0]
            )

        except Exception as exc:
            app.logger.exception(
                "Admin support request could not be loaded"
            )

            flash(
                str(exc),
                "danger",
            )

            return redirect(
                url_for(
                    "admin_support"
                )
            )

        if request.method == "POST":
            reply_message = (
                request.form.get(
                    "reply_message",
                    "",
                )
                or ""
            ).strip()

            new_status = (
                request.form.get(
                    "status",
                    support_request.get(
                        "status"
                    )
                    or "open",
                )
                or "open"
            ).strip().lower()

            if new_status not in VALID_STATUSES:
                flash(
                    "Choose a valid support status.",
                    "danger",
                )

            elif (
                reply_message
                and len(reply_message) < 5
            ):
                flash(
                    "Reply must contain at least 5 characters.",
                    "danger",
                )

            elif len(reply_message) > 3000:
                flash(
                    "Reply must be 3000 characters or fewer.",
                    "danger",
                )

            else:
                try:
                    now_iso = datetime.now(
                        timezone.utc
                    ).isoformat()

                    if reply_message:
                        reply_response = (
                            supabase
                            .table(
                                "support_replies"
                            )
                            .insert({
                                "request_id": (
                                    request_id
                                ),
                                "sender_type": (
                                    "admin"
                                ),
                                "sender_email": (
                                    session.get(
                                        "user_email"
                                    )
                                    or None
                                ),
                                "message": (
                                    reply_message
                                ),
                            })
                            .execute()
                        )

                        if not reply_response.data:
                            raise ValueError(
                                "Admin support reply was not saved."
                            )

                    update_response = (
                        supabase
                        .table(
                            "support_requests"
                        )
                        .update({
                            "status": (
                                new_status
                            ),
                            "updated_at": (
                                now_iso
                            ),
                        })
                        .eq(
                            "id",
                            request_id,
                        )
                        .execute()
                    )

                    if not update_response.data:
                        raise ValueError(
                            "Support status was not updated."
                        )

                    if (
                        reply_message
                        and support_request.get(
                            "user_email"
                        )
                    ):
                        student_link = (
                            _public_url(
                                "support_request_detail",
                                request_id=request_id,
                            )
                        )

                        request_subject = (
                            support_request.get(
                                "subject"
                            )
                            or "Support request"
                        )

                        plain_body = (
                            "InternShield Support replied to your request.\n\n"
                            f"Subject: {request_subject}\n"
                            f"Status: {new_status.title()}\n\n"
                            f"{reply_message}\n\n"
                            f"View the conversation:\n{student_link}\n"
                        )

                        html_body = _email_shell(
                            eyebrow="Support reply",
                            title="You received a support reply",
                            intro=(
                                "InternShield Support has replied to "
                                "your request."
                            ),
                            message_text=reply_message,
                            button_label="View conversation",
                            button_url=student_link,
                            meta_rows=[
                                (
                                    "Subject",
                                    request_subject,
                                ),
                                (
                                    "Status",
                                    new_status.title(),
                                ),
                            ],
                        )

                        mail_result = (
                            _send_email(
                                recipients=[
                                    support_request[
                                        "user_email"
                                    ]
                                ],
                                subject=(
                                    "[InternShield Support] Reply: "
                                    + request_subject
                                ),
                                body=plain_body,
                                html_body=html_body,
                                reply_to=(
                                    session.get(
                                        "user_email"
                                    )
                                    or None
                                ),
                            )
                        )

                        if not mail_result.get(
                            "sent"
                        ):
                            flash(
                                "Reply saved, but the email "
                                "notification was not sent: "
                                + (
                                    mail_result.get(
                                        "reason"
                                    )
                                    or "Email delivery is not configured."
                                ),
                                "warning",
                            )

                        else:
                            flash(
                                "Reply saved and the student was notified by email.",
                                "success",
                            )

                    else:
                        flash(
                            "Support request updated successfully.",
                            "success",
                        )

                    return redirect(
                        url_for(
                            "admin_support_detail",
                            request_id=(
                                request_id
                            ),
                        )
                    )

                except Exception:
                    app.logger.exception(
                        "Admin support response could not be saved"
                    )

                    flash(
                        "The support response could not be saved.",
                        "danger",
                    )

        try:
            reply_response = (
                supabase
                .table(
                    "support_replies"
                )
                .select("*")
                .eq(
                    "request_id",
                    request_id,
                )
                .order(
                    "created_at",
                )
                .execute()
            )

            replies = (
                reply_response.data
                or []
            )

        except Exception:
            app.logger.exception(
                "Admin support replies could not be loaded"
            )

            replies = []

        return render_template(
            "admin_support_detail.html",
            support_request=(
                support_request
            ),
            replies=replies,
        )
