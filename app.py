import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from services.consistency_engine import analyze_consistency

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_session import Session

from services.analysis_engine import analyze_internship
from services.application_tracker import (
    APPLICATION_STATUSES,
    application_statistics,
    validate_application_payload,
    build_application_alerts,
    alert_statistics,
)
from services.comparison_engine import compare_internships
from services.compatibility_engine import calculate_compatibility
from services.domain_verification import analyze_recruiter_domain
from services.document_extractor import (
    DocumentExtractionError,
    extract_pdf_text,
)
from services.offer_decision_engine import (
    evaluate_offer_decision,
)
from services.offer_change_engine import (
    compare_offer_to_original,
)
from services.internshield_assistant import (
    generate_assistant_reply,
)
from services.gemini_service import (
    generate_assessment_explanation,
)
from services.image_extractor import (
    ImageExtractionError,
    extract_image_text,
)
from services.report_generator import (
    generate_assessment_report,
)
from services.website_verification import (
    WebsiteVerificationError,
    verify_company_website,
)
from supabase_client import get_supabase_client
from services.support_system import (
    is_support_admin,
    register_support_routes,
)

load_dotenv()

app = Flask(__name__)

app.config.update(
    SECRET_KEY=(
        os.getenv("FLASK_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or "internshield-local-development-key"
    ),
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.path.join(
        app.root_path,
        ".flask_session",
    ),
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    SESSION_USE_SIGNER=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

Session(app)

register_support_routes(app)


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


def get_authenticated_supabase():
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


@app.context_processor
def inject_workspace_identity():
    """
    Make one consistent signed-in identity available to every
    InternShield template using the shared workspace sidebar.
    """

    user_name = (
        session.get(
            "full_name"
        )
        or "Student"
    )

    user_email = (
        session.get(
            "user_email"
        )
        or ""
    )

    profile_image_path = (
        session.get(
            "workspace_profile_image_path"
        )
        or ""
    )

    profile_loaded = (
        session.get(
            "workspace_profile_loaded"
        )
        is True
    )

    if (
        session.get("user_id")
        and not profile_loaded
    ):
        try:
            supabase = (
                get_authenticated_supabase()
            )

            response = (
                supabase
                .table(
                    "user_profiles"
                )
                .select(
                    "full_name, profile_image_path"
                )
                .eq(
                    "user_id",
                    session["user_id"],
                )
                .execute()
            )

            if response.data:
                saved_profile = (
                    response.data[0]
                )

                saved_name = (
                    saved_profile.get(
                        "full_name"
                    )
                    or ""
                ).strip()

                if saved_name:
                    user_name = (
                        saved_name
                    )

                    session[
                        "full_name"
                    ] = saved_name

                profile_image_path = (
                    saved_profile.get(
                        "profile_image_path"
                    )
                    or ""
                )

            session[
                "workspace_profile_image_path"
            ] = profile_image_path

            session[
                "workspace_profile_loaded"
            ] = True

        except Exception:
            app.logger.exception(
                "Shared sidebar profile could not be loaded"
            )

    return {
        "workspace_user_name": (
            user_name
        ),
        "workspace_user_email": (
            user_email
        ),
        "workspace_profile_image_path": (
            profile_image_path
        ),
        "workspace_is_support_admin": (
            is_support_admin()
        ),
    }

def record_timeline_event(
    supabase,
    event_type,
    title,
    details=None,
    analysis_id=None,
    application_id=None,
    metadata=None,
):
    """
    Save an opportunity timeline event without interrupting
    the user's main workflow if timeline logging fails.
    """

    try:
        payload = {
            "user_id": session["user_id"],
            "event_type": event_type,
            "title": title,
            "details": details,
            "analysis_id": analysis_id,
            "application_id": application_id,
            "metadata": metadata or {},
        }

        supabase.table(
            "opportunity_timeline"
        ).insert(payload).execute()

    except Exception:
        app.logger.exception(
            "Timeline event could not be recorded"
        )

@app.errorhandler(413)
def file_too_large(error):
    flash(
        "The uploaded file is too large. Select a file "
        "smaller than 5 MB.",
        "danger",
    )
    return redirect(url_for("analyze"))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            "",
        )

        if not full_name or not email or not password:
            flash(
                "Please complete all required fields.",
                "danger",
            )
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger",
            )
            return redirect(url_for("signup"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("signup"))

        try:
            supabase = get_supabase_client()

            response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": full_name,
                    }
                },
            })

            if response.user:
                flash(
                    "Registration successful. Confirm your "
                    "email, then log in.",
                    "success",
                )
                return redirect(url_for("login"))

            flash(
                "Registration could not be completed.",
                "danger",
            )

        except Exception:
            flash(
                "Registration failed. The email may already "
                "be registered.",
                "danger",
            )

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash(
                "Enter your email address and password.",
                "danger",
            )
            return redirect(url_for("login"))

        try:
            supabase = get_supabase_client()

            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })

            if not response.user or not response.session:
                flash("Unable to log in.", "danger")
                return redirect(url_for("login"))

            session.clear()
            session.permanent = True

            session["user_id"] = str(response.user.id)
            session["user_email"] = response.user.email
            session["access_token"] = (
                response.session.access_token
            )
            session["refresh_token"] = (
                response.session.refresh_token
            )

            user_metadata = response.user.user_metadata or {}

            session["full_name"] = user_metadata.get(
                "full_name",
                "Student",
            )

            flash("Welcome to InternShield AI!", "success")
            return redirect(url_for("dashboard"))

        except Exception:
            flash(
                "Login failed. Check your email and password.",
                "danger",
            )

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email or "@" not in email:
            flash(
                "Enter a valid email address.",
                "danger",
            )
            return redirect(url_for("forgot_password"))

        try:
            supabase = get_supabase_client()

            reset_url = url_for(
                "reset_password",
                _external=True,
            )

            supabase.auth.reset_password_for_email(
                email,
                {
                    "redirect_to": reset_url,
                },
            )

        except Exception:
            # Keep the response generic so the page does not reveal
            # whether a particular email address is registered.
            pass

        flash(
            "If an account exists for that email, a password "
            "reset link has been sent. Check your inbox and "
            "spam folder.",
            "success",
        )
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            "",
        )
        access_token = request.form.get(
            "access_token",
            "",
        ).strip()
        refresh_token = request.form.get(
            "refresh_token",
            "",
        ).strip()

        if not access_token or not refresh_token:
            flash(
                "The recovery link is missing, invalid or "
                "expired. Request a new password-reset email.",
                "danger",
            )
            return redirect(url_for("forgot_password"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger",
            )
            return render_template(
                "reset_password.html",
                recovery_error=False,
                access_token=access_token,
                refresh_token=refresh_token,
            )

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template(
                "reset_password.html",
                recovery_error=False,
                access_token=access_token,
                refresh_token=refresh_token,
            )

        try:
            supabase = get_supabase_client()

            auth_response = supabase.auth.set_session(
                access_token,
                refresh_token,
            )

            if not auth_response.session:
                raise ValueError("Recovery session unavailable")

            supabase.auth.update_user({
                "password": password,
            })

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            session.clear()

            flash(
                "Your password has been updated. Log in using "
                "your new password.",
                "success",
            )
            return redirect(url_for("login"))

        except Exception:
            flash(
                "The recovery link is invalid or expired. "
                "Request a new password-reset email.",
                "danger",
            )
            return redirect(url_for("forgot_password"))

    return render_template(
        "reset_password.html",
        recovery_error=False,
        access_token="",
        refresh_token="",
    )


@app.route("/dashboard")
@login_required
def dashboard():
    analyses = []
    dashboard_profile = {}

    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .select(
                "id, company_name, role_title, "
                "verification_score, value_score, "
                "assessment_status, created_at"
                ", is_shortlisted"
            )
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )

        analyses = response.data or []

        try:
            profile_response = (
                supabase
                .table("user_profiles")
                .select(
                    "full_name, profile_image_path"
                )
                .eq(
                    "user_id",
                    session["user_id"],
                )
                .execute()
            )

            if profile_response.data:
                dashboard_profile = (
                    profile_response.data[0]
                )

        except Exception:
            app.logger.exception(
                "Dashboard profile preview could not be loaded"
            )

    except Exception:
        flash(
            "Your analysis history could not be loaded.",
            "warning",
        )

    statistics = {
        "total": len(analyses),
        "reasonable": sum(
            item["assessment_status"] == "appears_reasonable"
            for item in analyses
        ),
        "verification": sum(
            item["assessment_status"] == "verification_required"
            for item in analyses
        ),
        "suspicious": sum(
            item["assessment_status"] == "potentially_suspicious"
            for item in analyses
        ),
    }

    return render_template(
        "dashboard.html",
        full_name=session.get("full_name", "Student"),
        email=session.get("user_email"),
        analyses=analyses,
        statistics=statistics,
        profile_image_path=(
            dashboard_profile.get(
                "profile_image_path"
            )
            or ""
        ),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Show the signed-in student's profile first.
    Editing is opened only when the user explicitly chooses it.
    """

    try:
        supabase = get_authenticated_supabase()

    except Exception:
        flash(
            "Unable to load your profile right now.",
            "danger",
        )
        return redirect(
            url_for("dashboard")
        )

    # ---------------------------------------------------------
    # LOAD SAVED PROFILE
    # ---------------------------------------------------------

    existing_profile = {}

    try:
        profile_response = (
            supabase
            .table("user_profiles")
            .select("*")
            .eq(
                "user_id",
                session["user_id"],
            )
            .execute()
        )

        profile_records = (
            profile_response.data
            or []
        )

        if profile_records:
            existing_profile = (
                profile_records[0]
            )

    except Exception:
        app.logger.exception(
            "User profile could not be loaded"
        )

        flash(
            "Your saved profile could not be loaded. "
            "Check the Flask terminal for details.",
            "warning",
        )

    profile_data = {
        "user_id": session["user_id"],
        "full_name": (
            existing_profile.get(
                "full_name"
            )
            or session.get(
                "full_name",
                "Student",
            )
        ),
        "college_name": (
            existing_profile.get(
                "college_name"
            )
            or ""
        ),
        "branch": (
            existing_profile.get(
                "branch"
            )
            or ""
        ),
        "semester": (
            existing_profile.get(
                "semester"
            )
        ),
        "available_hours_per_week": (
            existing_profile.get(
                "available_hours_per_week"
            )
        ),
        "preferred_work_mode": (
            existing_profile.get(
                "preferred_work_mode"
            )
            or "no_preference"
        ),
        "default_schedule_type": (
            existing_profile.get(
                "default_schedule_type"
            )
            or "not_specified"
        ),
        "profile_image_path": (
            existing_profile.get(
                "profile_image_path"
            )
            or ""
        ),
        "created_at": (
            existing_profile.get(
                "created_at"
            )
        ),
        "updated_at": (
            existing_profile.get(
                "updated_at"
            )
        ),
    }

    edit_mode = (
        request.args.get("edit") == "1"
    )

    # ---------------------------------------------------------
    # SAVE PROFILE
    # ---------------------------------------------------------

    if request.method == "POST":
        edit_mode = True

        full_name = (
            request.form.get(
                "full_name",
                "",
            )
            or ""
        ).strip()

        college_name = (
            request.form.get(
                "college_name",
                "",
            )
            or ""
        ).strip()

        branch = (
            request.form.get(
                "branch",
                "",
            )
            or ""
        ).strip()

        semester_text = (
            request.form.get(
                "semester",
                "",
            )
            or ""
        ).strip()

        available_hours_text = (
            request.form.get(
                "available_hours_per_week",
                "",
            )
            or ""
        ).strip()

        preferred_work_mode = (
            request.form.get(
                "preferred_work_mode",
                "no_preference",
            )
            or "no_preference"
        ).strip().lower()

        default_schedule_type = (
            request.form.get(
                "default_schedule_type",
                "not_specified",
            )
            or "not_specified"
        ).strip().lower()

        remove_profile_image = (
            request.form.get(
                "remove_profile_image"
            )
            == "1"
        )

        uploaded_profile_image = (
            request.files.get(
                "profile_image"
            )
        )

        errors = []

        # -----------------------------------------------------
        # BASIC VALIDATION
        # -----------------------------------------------------

        if not full_name:
            errors.append(
                "Full name is required."
            )

        if len(full_name) > 120:
            errors.append(
                "Full name must be 120 characters or fewer."
            )

        if len(college_name) > 180:
            errors.append(
                "College name must be 180 characters or fewer."
            )

        if len(branch) > 120:
            errors.append(
                "Branch must be 120 characters or fewer."
            )

        # -----------------------------------------------------
        # SEMESTER
        # -----------------------------------------------------

        semester = None

        if semester_text:
            try:
                semester = int(
                    semester_text
                )

                if not 1 <= semester <= 12:
                    errors.append(
                        "Semester must be between 1 and 12."
                    )

            except ValueError:
                errors.append(
                    "Semester must be a valid number."
                )

        # -----------------------------------------------------
        # WEEKLY AVAILABILITY
        # -----------------------------------------------------

        available_hours = None

        if available_hours_text:
            try:
                available_hours = float(
                    available_hours_text
                )

                if not 0 <= available_hours <= 168:
                    errors.append(
                        "Available weekly hours must be "
                        "between 0 and 168."
                    )

            except ValueError:
                errors.append(
                    "Available weekly hours must be a valid number."
                )

        # -----------------------------------------------------
        # SELECTS
        # -----------------------------------------------------

        valid_work_modes = {
            "remote",
            "hybrid",
            "onsite",
            "no_preference",
        }

        valid_schedule_types = {
            "flexible",
            "fixed",
            "not_specified",
        }

        if preferred_work_mode not in valid_work_modes:
            errors.append(
                "Select a valid preferred work mode."
            )

        if default_schedule_type not in valid_schedule_types:
            errors.append(
                "Select a valid default schedule type."
            )

        # -----------------------------------------------------
        # PROFILE IMAGE VALIDATION
        # -----------------------------------------------------

        new_profile_image_path = (
            profile_data.get(
                "profile_image_path"
            )
            or ""
        )

        image_extension = None

        if (
            uploaded_profile_image
            and uploaded_profile_image.filename
        ):
            filename_lower = (
                uploaded_profile_image
                .filename
                .lower()
            )

            allowed_extensions = {
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
            }

            image_extension = os.path.splitext(
                filename_lower
            )[1]

            if image_extension not in allowed_extensions:
                errors.append(
                    "Profile image must be JPG, JPEG, PNG or WEBP."
                )

            allowed_mimetypes = {
                "image/jpeg",
                "image/png",
                "image/webp",
            }

            if (
                uploaded_profile_image.mimetype
                not in allowed_mimetypes
            ):
                errors.append(
                    "The selected profile image format is not supported."
                )

            try:
                uploaded_profile_image.stream.seek(
                    0,
                    os.SEEK_END,
                )

                image_size = (
                    uploaded_profile_image
                    .stream
                    .tell()
                )

                uploaded_profile_image.stream.seek(
                    0
                )

                if image_size > 2 * 1024 * 1024:
                    errors.append(
                        "Profile image must be 2 MB or smaller."
                    )

            except Exception:
                errors.append(
                    "The selected profile image could not be read."
                )

        # Preserve form values if validation fails.
        profile_data.update({
            "full_name": full_name,
            "college_name": college_name,
            "branch": branch,
            "semester": (
                semester_text
                if semester_text
                else None
            ),
            "available_hours_per_week": (
                available_hours_text
                if available_hours_text
                else None
            ),
            "preferred_work_mode": (
                preferred_work_mode
            ),
            "default_schedule_type": (
                default_schedule_type
            ),
        })

        if errors:
            for message in errors:
                flash(
                    message,
                    "danger",
                )

        else:
            # -------------------------------------------------
            # SAVE / REMOVE PROFILE IMAGE
            # -------------------------------------------------

            profile_image_directory = (
                os.path.join(
                    app.static_folder,
                    "profile_images",
                )
            )

            os.makedirs(
                profile_image_directory,
                exist_ok=True,
            )

            old_relative_path = (
                profile_data.get(
                    "profile_image_path"
                )
                or ""
            )

            old_absolute_path = (
                os.path.join(
                    app.static_folder,
                    old_relative_path,
                )
                if old_relative_path
                else ""
            )

            if remove_profile_image:
                if (
                    old_absolute_path
                    and os.path.isfile(
                        old_absolute_path
                    )
                ):
                    try:
                        os.remove(
                            old_absolute_path
                        )
                    except OSError:
                        app.logger.exception(
                            "Old profile image could not be removed"
                        )

                new_profile_image_path = ""

            if (
                uploaded_profile_image
                and uploaded_profile_image.filename
                and image_extension
            ):
                # Remove the previous image if it used
                # a different extension.
                if (
                    old_absolute_path
                    and os.path.isfile(
                        old_absolute_path
                    )
                ):
                    try:
                        os.remove(
                            old_absolute_path
                        )
                    except OSError:
                        app.logger.exception(
                            "Old profile image could not be replaced"
                        )

                safe_user_id = (
                    str(
                        session["user_id"]
                    )
                    .replace(
                        "-",
                        "",
                    )
                )

                normalized_extension = (
                    ".jpg"
                    if image_extension == ".jpeg"
                    else image_extension
                )

                image_filename = (
                    f"{safe_user_id}"
                    f"{normalized_extension}"
                )

                absolute_image_path = (
                    os.path.join(
                        profile_image_directory,
                        image_filename,
                    )
                )

                uploaded_profile_image.save(
                    absolute_image_path
                )

                new_profile_image_path = (
                    "profile_images/"
                    + image_filename
                )

            # -------------------------------------------------
            # DATABASE SAVE
            # -------------------------------------------------

            now_iso = datetime.now(
                timezone.utc
            ).isoformat()

            save_payload = {
                "full_name": full_name,
                "college_name": (
                    college_name
                    or None
                ),
                "branch": (
                    branch
                    or None
                ),
                "semester": semester,
                "available_hours_per_week": (
                    available_hours
                ),
                "preferred_work_mode": (
                    preferred_work_mode
                ),
                "default_schedule_type": (
                    default_schedule_type
                ),
                "profile_image_path": (
                    new_profile_image_path
                    or None
                ),
                "updated_at": now_iso,
            }

            try:
                if existing_profile:
                    save_response = (
                        supabase
                        .table("user_profiles")
                        .update(
                            save_payload
                        )
                        .eq(
                            "user_id",
                            session["user_id"],
                        )
                        .execute()
                    )

                else:
                    create_payload = {
                        **save_payload,
                        "user_id": (
                            session["user_id"]
                        ),
                    }

                    save_response = (
                        supabase
                        .table("user_profiles")
                        .insert(
                            create_payload
                        )
                        .execute()
                    )

                if not save_response.data:
                    raise ValueError(
                        "Profile save returned no data."
                    )

                session["full_name"] = (
                    full_name
                )

                session[
                    "workspace_profile_image_path"
                ] = (
                    new_profile_image_path
                    or ""
                )

                session[
                    "workspace_profile_loaded"
                ] = True

                try:
                    supabase.auth.update_user({
                        "data": {
                            "full_name": (
                                full_name
                            )
                        }
                    })

                except Exception:
                    app.logger.exception(
                        "Auth profile name could not be synchronized"
                    )

                flash(
                    "Profile updated successfully.",
                    "success",
                )

                return redirect(
                    url_for("profile")
                )

            except Exception:
                app.logger.exception(
                    "User profile could not be saved"
                )

                flash(
                    "Your profile could not be saved. "
                    "Check the Flask terminal for details.",
                    "danger",
                )

    # ---------------------------------------------------------
    # ACCOUNT OVERVIEW
    # ---------------------------------------------------------

    profile_statistics = {
        "assessments": 0,
        "shortlisted": 0,
        "applications": 0,
        "offers": 0,
    }

    try:
        analyses_response = (
            supabase
            .table("internship_analyses")
            .select(
                "id, is_shortlisted"
            )
            .eq(
                "user_id",
                session["user_id"],
            )
            .execute()
        )

        analysis_records = (
            analyses_response.data
            or []
        )

        profile_statistics[
            "assessments"
        ] = len(
            analysis_records
        )

        profile_statistics[
            "shortlisted"
        ] = sum(
            1
            for item in analysis_records
            if item.get(
                "is_shortlisted"
            )
        )

    except Exception:
        app.logger.exception(
            "Profile assessment statistics could not be loaded"
        )

    try:
        applications_response = (
            supabase
            .table("internship_applications")
            .select(
                "id, status"
            )
            .eq(
                "user_id",
                session["user_id"],
            )
            .execute()
        )

        application_records = (
            applications_response.data
            or []
        )

        profile_statistics[
            "applications"
        ] = len(
            application_records
        )

        profile_statistics[
            "offers"
        ] = sum(
            1
            for item in application_records
            if item.get(
                "status"
            ) == "offer"
        )

    except Exception:
        app.logger.exception(
            "Profile application statistics could not be loaded"
        )

    return render_template(
        "profile.html",
        profile=profile_data,
        email=session.get(
            "user_email",
            "",
        ),
        profile_statistics=(
            profile_statistics
        ),
        edit_mode=edit_mode,
    )



@app.route("/assistant", methods=["GET", "POST"])
@login_required
def assistant():
    """
    Context-aware assistant grounded in the signed-in user's
    InternShield profile, assessments and application tracker.
    """

    try:
        supabase = get_authenticated_supabase()

    except Exception:
        flash(
            "Unable to open InternShield Assistant right now.",
            "danger",
        )
        return redirect(
            url_for("dashboard")
        )

    profile_data = {}
    analyses = []
    applications = []

    # ---------------------------------------------------------
    # PROFILE CONTEXT
    # ---------------------------------------------------------

    try:
        profile_response = (
            supabase
            .table("user_profiles")
            .select("*")
            .eq(
                "user_id",
                session["user_id"],
            )
            .execute()
        )

        if profile_response.data:
            profile_data = (
                profile_response.data[0]
            )

    except Exception:
        app.logger.exception(
            "Assistant profile context could not be loaded"
        )

    # ---------------------------------------------------------
    # ASSESSMENT CONTEXT
    # ---------------------------------------------------------

    try:
        analyses_response = (
            supabase
            .table("internship_analyses")
            .select(
                "id, company_name, role_title, "
                "recruiter_email, company_website, "
                "recruiter_email_domain, "
                "company_website_domain, domain_match, "
                "verification_score, value_score, "
                "compatibility_score, compatibility_status, "
                "compatibility_reasons, consistency_score, "
                "consistency_status, assessment_status, "
                "detected_flags, recommendations, "
                "domain_verification, website_verification, "
                "weekly_workload, available_hours_per_week, "
                "schedule_type, exam_period, "
                "class_schedule_conflict, created_at"
            )
            .eq(
                "user_id",
                session["user_id"],
            )
            .order(
                "created_at",
                desc=True,
            )
            .limit(12)
            .execute()
        )

        analyses = (
            analyses_response.data
            or []
        )

    except Exception:
        app.logger.exception(
            "Assistant assessment context could not be loaded"
        )

    # ---------------------------------------------------------
    # APPLICATION CONTEXT
    # ---------------------------------------------------------

    try:
        applications_response = (
            supabase
            .table("internship_applications")
            .select("*")
            .eq(
                "user_id",
                session["user_id"],
            )
            .order(
                "updated_at",
                desc=True,
            )
            .limit(20)
            .execute()
        )

        applications = (
            applications_response.data
            or []
        )

    except Exception:
        app.logger.exception(
            "Assistant application context could not be loaded"
        )

    # ---------------------------------------------------------
    # SESSION CHAT HISTORY
    # ---------------------------------------------------------

    chat_history = (
        session.get(
            "internshield_assistant_chat"
        )
        or []
    )

    if request.method == "POST":
        action = (
            request.form.get(
                "action",
                "",
            )
            or ""
        ).strip()

        if action == "clear":
            session[
                "internshield_assistant_chat"
            ] = []

            session.modified = True

            return redirect(
                url_for("assistant")
            )

        message = (
            request.form.get(
                "message",
                "",
            )
            or ""
        ).strip()

        if not message:
            flash(
                "Type a question for InternShield Assistant.",
                "warning",
            )

        elif len(message) > 800:
            flash(
                "Keep assistant questions under 800 characters.",
                "warning",
            )

        else:
            result = generate_assistant_reply(
                message,
                profile=profile_data,
                analyses=analyses,
                applications=applications,
                user_name=session.get(
                    "full_name",
                    "Student",
                ),
            )

            chat_history.append({
                "role": "user",
                "content": message,
            })

            chat_history.append({
                "role": "assistant",
                "content": result.get(
                    "reply",
                    "",
                ),
                "intent": result.get(
                    "intent",
                    "",
                ),
                "ai_used": result.get(
                    "ai_used",
                    False,
                ),
                "provider": result.get(
                    "provider",
                    "internshield",
                ),
                "model": result.get(
                    "model"
                ),
            })

            # Keep the conversation lightweight in the
            # server-side Flask session.
            chat_history = (
                chat_history[-16:]
            )

            session[
                "internshield_assistant_chat"
            ] = chat_history

            session.modified = True

            return redirect(
                url_for("assistant")
            )

    assistant_statistics = {
        "assessments": len(analyses),
        "applications": len(applications),
        "offers": sum(
            1
            for item in applications
            if (
                item.get("status")
                or ""
            ).lower() == "offer"
        ),
        "warnings": sum(
            len(
                item.get(
                    "detected_flags"
                )
                or []
            )
            for item in analyses
        ),
    }

    latest_analysis = (
        analyses[0]
        if analyses
        else None
    )

    return render_template(
        "assistant.html",
        chat_history=chat_history,
        assistant_statistics=(
            assistant_statistics
        ),
        latest_analysis=latest_analysis,
        profile=profile_data,
        full_name=session.get(
            "full_name",
            "Student",
        ),
        email=session.get(
            "user_email",
            "",
        ),
    )


@app.route("/applications", methods=["GET", "POST"])
@login_required
def applications():
    supabase = None

    try:
        supabase = get_authenticated_supabase()
    except Exception:
        flash("Unable to connect to your application tracker.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        payload, errors = validate_application_payload(request.form)

        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            payload["user_id"] = session["user_id"]

            try:
                response = (
                    supabase
                    .table("internship_applications")
                    .insert(payload)
                    .execute()
                )

                if response.data:
                    application = response.data[0]
                    application_id = application["id"]

                    record_timeline_event(
                        supabase=supabase,
                        event_type="application_added",
                        title="Added to application tracker",
                        details=(
                            f"{payload.get('role_title')} at "
                            f"{payload.get('company_name')} was added "
                            f"with stage "
                            f"{payload.get('status', 'saved').title()}."
                        ),
                        analysis_id=payload.get("analysis_id"),
                        application_id=application_id,
                        metadata={
                            "status": payload.get("status"),
                            "application_deadline": (
                                payload.get(
                                    "application_deadline"
                                )
                            ),
                            "interview_date": payload.get(
                                "interview_date"
                            ),
                        },
                    )

                flash(
                    "Internship added to your application tracker.",
                    "success",
                )

                return redirect(url_for("applications"))

            except Exception:
                flash(
                    "The application could not be saved. Run the tracker SQL "
                    "setup once, then try again.",
                    "danger",
                )

    tracked = []
    analyses = []
    timeline_events = []
    timeline_by_application = {}

    smart_alerts = []
    smart_alert_statistics = {
        "total": 0,
        "danger": 0,
        "warning": 0,
        "info": 0,
        "success": 0,
    }
    try:
        tracked_response = (
            supabase.table("internship_applications")
            .select("*")
            .eq("user_id", session["user_id"])
            .order("updated_at", desc=True)
            .execute()
        )
        tracked = tracked_response.data or []
    except Exception as error:
        app.logger.exception("Application tracker records could not be loaded")
        flash(
            "Application records could not be loaded. Check the Flask terminal "
            f"for the Supabase error ({type(error).__name__}).",
            "warning",
        )

    # ---------------------------------------------------------
    # SMART DEADLINE & INTERVIEW ALERTS
    # ---------------------------------------------------------

    try:
        smart_alerts = build_application_alerts(
            tracked
        )

        smart_alert_statistics = alert_statistics(
            smart_alerts
        )

    except Exception:
        app.logger.exception(
            "Smart application alerts could not be generated"
        )

        smart_alerts = []

        smart_alert_statistics = {
            "total": 0,
            "danger": 0,
            "warning": 0,
            "info": 0,
            "success": 0,
        }

    try:
        analyses_response = (
            supabase.table("internship_analyses")
            .select("id, company_name, role_title, assessment_status")
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )
        analyses = analyses_response.data or []
    except Exception:
        app.logger.exception("Linked assessments could not be loaded")
        flash(
            "Your linked assessments could not be loaded, but you can still "
            "add an application manually.",
            "warning",
        )

    try:
        timeline_response = (
            supabase
            .table("opportunity_timeline")
            .select("*")
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )

        timeline_events = timeline_response.data or []

    except Exception:
        app.logger.exception(
            "Application timeline could not be loaded"
        )

        timeline_events = []

    for application in tracked:
        application_id = application.get("id")
        analysis_id = application.get("analysis_id")

        related_events = []
        seen_event_ids = set()

        for event in timeline_events:
            event_matches_application = (
                event.get("application_id")
                == application_id
            )

            event_matches_analysis = (
                analysis_id
                and event.get("analysis_id")
                == analysis_id
            )

            if (
                event_matches_application
                or event_matches_analysis
            ):
                event_id = event.get("id")

                if event_id not in seen_event_ids:
                    related_events.append(event)

                    if event_id:
                        seen_event_ids.add(event_id)

        timeline_by_application[
            application_id
        ] = related_events

    return render_template(
        "applications.html",

        applications=tracked,

        analyses=analyses,

        statuses=APPLICATION_STATUSES,

        statistics=application_statistics(
            tracked
        ),

        timeline_by_application=(
            timeline_by_application
        ),

        smart_alerts=smart_alerts,

        smart_alert_statistics=(
            smart_alert_statistics
        ),

        full_name=session.get(
            "full_name",
            "Student",
        ),
    )

@app.get("/shortlist")
@login_required
def shortlist():
    analyses = []

    try:
        supabase = get_authenticated_supabase()
        response = (
            supabase.table("internship_analyses")
            .select(
                "id, company_name, role_title, verification_score, "
                "value_score, compatibility_score, assessment_status, "
                "created_at, is_shortlisted"
            )
            .eq("user_id", session["user_id"])
            .eq("is_shortlisted", True)
            .order("created_at", desc=True)
            .execute()
        )
        analyses = response.data or []
    except Exception:
        app.logger.exception("Shortlisted assessments could not be loaded")
        flash(
            "Your shortlist could not be loaded. Run the shortlist SQL setup once.",
            "warning",
        )

    return render_template("shortlist.html", analyses=analyses)


@app.post("/analysis/<analysis_id>/shortlist")
@login_required
def toggle_shortlist(analysis_id):
    should_save = (
        request.form.get("action") != "remove"
    )

    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .update({
                "is_shortlisted": should_save
            })
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        if not response.data:
            flash(
                "Assessment not found.",
                "danger",
            )

        else:
            analysis = response.data[0]

            company = (
                analysis.get("company_name")
                or "Unknown company"
            )

            role = (
                analysis.get("role_title")
                or "Internship opportunity"
            )

            if should_save:
                record_timeline_event(
                    supabase=supabase,
                    event_type="shortlisted",
                    title="Added to shortlist",
                    details=(
                        f"{role} at {company} was "
                        "added to your shortlist."
                    ),
                    analysis_id=analysis_id,
                )

                flash(
                    "Assessment added to your shortlist.",
                    "success",
                )

            else:
                record_timeline_event(
                    supabase=supabase,
                    event_type="shortlist_removed",
                    title="Removed from shortlist",
                    details=(
                        f"{role} at {company} was "
                        "removed from your shortlist."
                    ),
                    analysis_id=analysis_id,
                )

                flash(
                    "Assessment removed from your shortlist.",
                    "success",
                )

    except Exception:
        app.logger.exception(
            "Assessment shortlist could not be updated"
        )

        flash(
            "The shortlist could not be updated.",
            "danger",
        )

    destination = request.form.get(
        "next",
        "dashboard",
    )

    return redirect(
        url_for(
            "shortlist"
            if destination == "shortlist"
            else "dashboard"
        )
    )

@app.post("/analysis/<analysis_id>/delete")
@login_required
def delete_analysis(analysis_id):
    try:
        supabase = get_authenticated_supabase()

        # -----------------------------------------------------
        # Make sure assessment exists and belongs to user
        # -----------------------------------------------------

        existing_response = (
            supabase
            .table("internship_analyses")
            .select("id, company_name, role_title")
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        existing_records = existing_response.data or []

        if not existing_records:
            flash(
                "Assessment not found.",
                "danger",
            )
            return redirect(url_for("dashboard"))

        # -----------------------------------------------------
        # Keep tracker records but unlink this assessment
        # -----------------------------------------------------

        try:
            (
                supabase
                .table("internship_applications")
                .update({
                    "analysis_id": None
                })
                .eq("analysis_id", analysis_id)
                .eq("user_id", session["user_id"])
                .execute()
            )

        except Exception:
            app.logger.exception(
                "Linked tracker record could not be unlinked"
            )

            flash(
                "The assessment could not be deleted because "
                "a linked tracker record could not be updated.",
                "danger",
            )

            return redirect(url_for("dashboard"))

        # -----------------------------------------------------
        # Delete assessment
        # -----------------------------------------------------

        delete_response = (
            supabase
            .table("internship_analyses")
            .delete()
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        if not delete_response.data:
            flash(
                "Assessment could not be deleted.",
                "danger",
            )

        else:
            flash(
                "Assessment deleted successfully.",
                "success",
            )

    except Exception:
        app.logger.exception(
            "Assessment could not be deleted"
        )

        flash(
            "The assessment could not be deleted.",
            "danger",
        )

    return redirect(url_for("dashboard"))

@app.post("/applications/<application_id>/review-offer")
@login_required
def review_final_offer(application_id):
    """
    Compare a submitted final offer with the original
    assessment evidence and save the explainable result
    on the linked tracker record.
    """

    try:
        supabase = get_authenticated_supabase()

        # -----------------------------------------------------
        # LOAD TRACKED APPLICATION
        # -----------------------------------------------------

        application_response = (
            supabase
            .table("internship_applications")
            .select("*")
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        application_records = (
            application_response.data
            or []
        )

        if not application_records:
            flash(
                "Application not found.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        application = application_records[0]

        # Offer change detection is meaningful only once
        # the application has reached the Offer stage.
        if application.get("status") != "offer":
            flash(
                "Final offer comparison is available when "
                "the application reaches the Offer stage.",
                "warning",
            )
            return redirect(
                url_for("applications")
            )

        analysis_id = application.get(
            "analysis_id"
        )

        if not analysis_id:
            flash(
                "Link this application to an assessment "
                "before comparing the final offer.",
                "warning",
            )
            return redirect(
                url_for("applications")
            )

        # -----------------------------------------------------
        # LOAD ORIGINAL ASSESSMENT
        # -----------------------------------------------------

        analysis_response = (
            supabase
            .table("internship_analyses")
            .select("*")
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        analysis_records = (
            analysis_response.data
            or []
        )

        if not analysis_records:
            flash(
                "The linked assessment could not be found.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        analysis = analysis_records[0]

        # -----------------------------------------------------
        # FINAL OFFER INPUT
        # -----------------------------------------------------

        manual_text = (
            request.form.get(
                "final_offer_text",
                "",
            )
            or ""
        ).strip()

        final_recruiter_email = (
            request.form.get(
                "final_offer_recruiter_email",
                "",
            )
            or ""
        ).strip().lower()

        uploaded_pdf = request.files.get(
            "final_offer_pdf"
        )

        uploaded_image = request.files.get(
            "final_offer_image"
        )

        has_text = bool(
            manual_text
        )

        has_pdf = bool(
            uploaded_pdf
            and uploaded_pdf.filename
        )

        has_image = bool(
            uploaded_image
            and uploaded_image.filename
        )

        input_count = sum(
            [
                has_text,
                has_pdf,
                has_image,
            ]
        )

        if input_count == 0:
            flash(
                "Paste the final offer text or upload "
                "one PDF or one image.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        if input_count > 1:
            flash(
                "Use only one final-offer source: pasted "
                "text, one PDF, or one image.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        input_type = "text"
        final_offer_text = manual_text

        if has_pdf:
            try:
                final_offer_text = extract_pdf_text(
                    uploaded_pdf
                )

            except DocumentExtractionError as error:
                flash(
                    str(error),
                    "danger",
                )
                return redirect(
                    url_for("applications")
                )

            input_type = "pdf"

        elif has_image:
            try:
                final_offer_text = extract_image_text(
                    uploaded_image
                )

            except ImageExtractionError as error:
                flash(
                    str(error),
                    "danger",
                )
                return redirect(
                    url_for("applications")
                )

            input_type = "image"

        final_offer_text = (
            final_offer_text
            or ""
        ).strip()

        if len(final_offer_text) < 30:
            flash(
                "The final offer must contain at least "
                "30 characters after extraction.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        # -----------------------------------------------------
        # RUN OFFER CHANGE DETECTION
        # -----------------------------------------------------

        comparison = compare_offer_to_original(
            analysis=analysis,
            final_offer_text=final_offer_text,
            final_recruiter_email=(
                final_recruiter_email
                or None
            ),
        )

        update_payload = {
            "final_offer_input_type": (
                input_type
            ),
            "final_offer_text": (
                final_offer_text
            ),
            "final_offer_recruiter_email": (
                final_recruiter_email
                or None
            ),
            "offer_change_analysis": (
                comparison
            ),
            "offer_change_score": (
                comparison.get(
                    "change_score"
                )
            ),
            "offer_change_status": (
                comparison.get(
                    "change_status"
                )
            ),
            "offer_reviewed_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        update_response = (
            supabase
            .table("internship_applications")
            .update(update_payload)
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        if not update_response.data:
            flash(
                "The final offer comparison could not "
                "be saved.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        # -----------------------------------------------------
        # TIMELINE EVENT
        # -----------------------------------------------------

        company = (
            application.get("company_name")
            or "Unknown company"
        )

        role = (
            application.get("role_title")
            or "Internship opportunity"
        )

        record_timeline_event(
            supabase=supabase,
            event_type="offer_reviewed",
            title="Final offer compared",
            details=(
                f"The final offer for {role} at "
                f"{company} was compared with the "
                "original assessment. "
                f"Result: "
                f"{comparison.get('change_status', 'Review Changes')} "
                f"({comparison.get('change_score', 0)}/100)."
            ),
            analysis_id=analysis_id,
            application_id=application_id,
            metadata={
                "offer_change_score": (
                    comparison.get(
                        "change_score"
                    )
                ),
                "offer_change_status": (
                    comparison.get(
                        "change_status"
                    )
                ),
                "final_offer_input_type": (
                    input_type
                ),
            },
        )

        flash(
            "Final offer comparison completed successfully.",
            "success",
        )

    except Exception:
        app.logger.exception(
            "Final offer comparison could not be completed"
        )

        flash(
            "The final offer could not be compared. "
            "Check the Flask terminal for details.",
            "danger",
        )

    return redirect(
        url_for("applications")
    )


@app.post("/applications/<application_id>/update")
@login_required
def update_application(application_id):
    payload, errors = validate_application_payload(
        request.form
    )

    if errors:
        for message in errors:
            flash(message, "danger")

        return redirect(url_for("applications"))

    try:
        supabase = get_authenticated_supabase()

        existing_response = (
            supabase
            .table("internship_applications")
            .select("*")
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        existing_records = (
            existing_response.data or []
        )

        if not existing_records:
            flash(
                "Application not found.",
                "danger",
            )
            return redirect(
                url_for("applications")
            )

        existing = existing_records[0]

        old_status = existing.get("status")
        old_interview = existing.get(
            "interview_date"
        )
        old_deadline = existing.get(
            "application_deadline"
        )

        response = (
            supabase
            .table("internship_applications")
            .update(payload)
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        if not response.data:
            flash(
                "Application not found.",
                "danger",
            )

        else:
            updated = response.data[0]

            analysis_id = (
                updated.get("analysis_id")
                or existing.get("analysis_id")
            )

            company = (
                updated.get("company_name")
                or existing.get("company_name")
                or "Unknown company"
            )

            role = (
                updated.get("role_title")
                or existing.get("role_title")
                or "Internship opportunity"
            )

            new_status = updated.get("status")
            new_interview = updated.get(
                "interview_date"
            )
            new_deadline = updated.get(
                "application_deadline"
            )

            meaningful_event_created = False

            # ---------------------------------------------
            # Stage change
            # ---------------------------------------------

            if old_status != new_status:
                record_timeline_event(
                    supabase=supabase,
                    event_type="stage_changed",
                    title="Application stage changed",
                    details=(
                        f"{role} at {company}: "
                        f"{(old_status or 'unknown').title()} "
                        f"→ "
                        f"{(new_status or 'unknown').title()}."
                    ),
                    analysis_id=analysis_id,
                    application_id=application_id,
                    metadata={
                        "old_status": old_status,
                        "new_status": new_status,
                    },
                )

                meaningful_event_created = True

            # ---------------------------------------------
            # Interview date
            # ---------------------------------------------

            if old_interview != new_interview:

                if new_interview:
                    event_title = (
                        "Interview scheduled"
                        if not old_interview
                        else "Interview date updated"
                    )

                    details = (
                        f"Interview for {role} at "
                        f"{company} is scheduled for "
                        f"{new_interview}."
                    )

                else:
                    event_title = (
                        "Interview date removed"
                    )

                    details = (
                        f"The interview date for "
                        f"{role} at {company} "
                        "was removed."
                    )

                record_timeline_event(
                    supabase=supabase,
                    event_type="interview_updated",
                    title=event_title,
                    details=details,
                    analysis_id=analysis_id,
                    application_id=application_id,
                    metadata={
                        "old_interview_date": (
                            old_interview
                        ),
                        "new_interview_date": (
                            new_interview
                        ),
                    },
                )

                meaningful_event_created = True

            # ---------------------------------------------
            # Application deadline
            # ---------------------------------------------

            if old_deadline != new_deadline:

                record_timeline_event(
                    supabase=supabase,
                    event_type="deadline_updated",
                    title="Application deadline updated",
                    details=(
                        f"The application deadline for "
                        f"{role} at {company} is now "
                        f"{new_deadline or 'not specified'}."
                    ),
                    analysis_id=analysis_id,
                    application_id=application_id,
                    metadata={
                        "old_deadline": old_deadline,
                        "new_deadline": new_deadline,
                    },
                )

                meaningful_event_created = True

            # ---------------------------------------------
            # General edit
            # ---------------------------------------------

            if not meaningful_event_created:
                record_timeline_event(
                    supabase=supabase,
                    event_type="application_updated",
                    title="Application details updated",
                    details=(
                        f"Tracker details for "
                        f"{role} at {company} "
                        "were updated."
                    ),
                    analysis_id=analysis_id,
                    application_id=application_id,
                )

            flash(
                "Application updated successfully.",
                "success",
            )

    except Exception:
        app.logger.exception(
            "Application could not be updated"
        )

        flash(
            "The application could not be updated.",
            "danger",
        )

    return redirect(url_for("applications"))

@app.post("/applications/<application_id>/delete")
@login_required
def delete_application(application_id):
    try:
        supabase = get_authenticated_supabase()

        existing_response = (
            supabase
            .table("internship_applications")
            .select("*")
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        existing_records = (
            existing_response.data or []
        )

        if not existing_records:
            flash(
                "Application not found.",
                "danger",
            )

            return redirect(
                url_for("applications")
            )

        existing = existing_records[0]

        response = (
            supabase
            .table("internship_applications")
            .delete()
            .eq("id", application_id)
            .eq("user_id", session["user_id"])
            .execute()
        )

        if not response.data:
            flash(
                "Application not found.",
                "danger",
            )

        else:
            company = (
                existing.get("company_name")
                or "Unknown company"
            )

            role = (
                existing.get("role_title")
                or "Internship opportunity"
            )

            record_timeline_event(
                supabase=supabase,
                event_type="application_removed",
                title="Removed from application tracker",
                details=(
                    f"{role} at {company} was "
                    "removed from the application tracker."
                ),
                analysis_id=existing.get(
                    "analysis_id"
                ),
                metadata={
                    "last_status": existing.get(
                        "status"
                    ),
                },
            )

            flash(
                "Application removed from your tracker.",
                "success",
            )

    except Exception:
        app.logger.exception(
            "Application could not be removed"
        )

        flash(
            "The application could not be removed.",
            "danger",
        )

    return redirect(url_for("applications"))

@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    analyses = []

    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .select(
                "id, company_name, role_title, "
                "verification_score, value_score, "
                "compatibility_score, "
                "effective_hourly_stipend, "
                "assessment_status, compatibility_status, "
                "detected_flags, created_at"
            )
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )

        analyses = response.data or []

    except Exception:
        flash(
            "Your saved assessments could not be loaded.",
            "danger",
        )
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        first_analysis_id = request.form.get(
            "first_analysis_id",
            "",
        ).strip()

        second_analysis_id = request.form.get(
            "second_analysis_id",
            "",
        ).strip()

        if not first_analysis_id or not second_analysis_id:
            flash(
                "Select two assessments to compare.",
                "danger",
            )
            return render_template(
                "compare.html",
                analyses=analyses,
            )

        if first_analysis_id == second_analysis_id:
            flash(
                "Select two different assessments.",
                "danger",
            )
            return render_template(
                "compare.html",
                analyses=analyses,
            )

        analyses_by_id = {
            item["id"]: item
            for item in analyses
        }

        first_analysis = analyses_by_id.get(
            first_analysis_id
        )
        second_analysis = analyses_by_id.get(
            second_analysis_id
        )

        if not first_analysis or not second_analysis:
            flash(
                "One of the selected assessments could not "
                "be found.",
                "danger",
            )
            return redirect(url_for("compare"))

        comparison = compare_internships(
            first_analysis,
            second_analysis,
        )

        return render_template(
            "compare_result.html",
            first_analysis=first_analysis,
            second_analysis=second_analysis,
            comparison=comparison,
        )

    return render_template(
        "compare.html",
        analyses=analyses,
    )


@app.route("/analyze", methods=["GET", "POST"])
@login_required
def analyze():
    if request.method == "POST":
        company_name = request.form.get(
            "company_name",
            "",
        ).strip()

        role_title = request.form.get(
            "role_title",
            "",
        ).strip()

        recruiter_email = request.form.get(
            "recruiter_email",
            "",
        ).strip().lower()

        company_website = request.form.get(
            "company_website",
            "",
        ).strip()

        manual_text = request.form.get(
            "original_text",
            "",
        ).strip()

        uploaded_pdf = request.files.get("pdf_file")
        uploaded_image = request.files.get("image_file")

        has_pdf = bool(
            uploaded_pdf
            and uploaded_pdf.filename
        )

        has_image = bool(
            uploaded_image
            and uploaded_image.filename
        )

        if has_pdf and has_image:
            flash(
                "Upload either one PDF or one image, not both.",
                "danger",
            )
            return redirect(url_for("analyze"))

        input_type = "text"
        original_text = manual_text
        evidence_text = manual_text

        if has_pdf:
            try:
                extracted_text = extract_pdf_text(uploaded_pdf)
                evidence_text = extracted_text

            except DocumentExtractionError as error:
                flash(str(error), "danger")
                return redirect(url_for("analyze"))

            input_type = "pdf"

            if manual_text:
                original_text = (
                    extracted_text
                    + "\n\nAdditional user notes:\n"
                    + manual_text
                )
            else:
                original_text = extracted_text

        elif has_image:
            try:
                extracted_text = extract_image_text(
                    uploaded_image
                )
                evidence_text = extracted_text

            except ImageExtractionError as error:
                flash(str(error), "danger")
                return redirect(url_for("analyze"))

            input_type = "image"

            if manual_text:
                original_text = (
                    extracted_text
                    + "\n\nAdditional user notes:\n"
                    + manual_text
                )
            else:
                original_text = extracted_text

        if not original_text:
            flash(
                "Paste an internship description, upload a "
                "PDF or upload a screenshot.",
                "danger",
            )
            return redirect(url_for("analyze"))

        if len(original_text) < 30:
            flash(
                "The extracted or entered text must contain "
                "at least 30 characters.",
                "danger",
            )
            return redirect(url_for("analyze"))

        try:
            stipend_text = request.form.get(
                "stipend_monthly",
                "",
            ).strip()

            hours_text = request.form.get(
                "hours_per_day",
                "",
            ).strip()

            days_text = request.form.get(
                "days_per_week",
                "",
            ).strip()

            duration_text = request.form.get(
                "duration_months",
                "",
            ).strip()

            available_hours_text = request.form.get(
                "available_hours_per_week",
                "",
            ).strip()

            stipend_monthly = (
                float(stipend_text)
                if stipend_text
                else None
            )

            hours_per_day = (
                float(hours_text)
                if hours_text
                else None
            )

            days_per_week = (
                int(days_text)
                if days_text
                else None
            )

            duration_months = (
                float(duration_text)
                if duration_text
                else None
            )

            available_hours_per_week = (
                float(available_hours_text)
                if available_hours_text
                else None
            )

        except ValueError:
            flash(
                "Enter valid numbers for stipend, working "
                "hours, days, duration and available time.",
                "danger",
            )
            return redirect(url_for("analyze"))

        schedule_type = request.form.get(
            "schedule_type",
            "not_specified",
        )

        valid_schedule_types = {
            "flexible",
            "fixed",
            "not_specified",
        }

        if schedule_type not in valid_schedule_types:
            schedule_type = "not_specified"

        exam_period = (
            request.form.get("exam_period") == "on"
        )

        class_schedule_conflict = (
            request.form.get("class_schedule_conflict") == "on"
        )

        if stipend_monthly is not None and stipend_monthly < 0:
            flash("Stipend cannot be negative.", "danger")
            return redirect(url_for("analyze"))

        if hours_per_day is not None and not (
            0 < hours_per_day <= 24
        ):
            flash(
                "Working hours must be between 1 and 24.",
                "danger",
            )
            return redirect(url_for("analyze"))

        if days_per_week is not None and not (
            1 <= days_per_week <= 7
        ):
            flash(
                "Working days must be between 1 and 7.",
                "danger",
            )
            return redirect(url_for("analyze"))

        if duration_months is not None and duration_months <= 0:
            flash(
                "Duration must be greater than zero.",
                "danger",
            )
            return redirect(url_for("analyze"))

        if available_hours_per_week is not None and not (
            0 <= available_hours_per_week <= 168
        ):
            flash(
                "Available weekly hours must be between "
                "0 and 168.",
                "danger",
            )
            return redirect(url_for("analyze"))

        assessment_result = analyze_internship(
            text=original_text,
            stipend_monthly=stipend_monthly,
            hours_per_day=hours_per_day,
            days_per_week=days_per_week,
        )

        compatibility_result = calculate_compatibility(
            hours_per_day=hours_per_day,
            days_per_week=days_per_week,
            available_hours_per_week=(
                available_hours_per_week
            ),
            schedule_type=schedule_type,
            exam_period=exam_period,
            class_schedule_conflict=(
                class_schedule_conflict
            ),
        )

        domain_result = analyze_recruiter_domain(
            recruiter_email=recruiter_email or None,
            company_website=company_website or None,
            company_name=company_name or None,
        )

        consistency_result = analyze_consistency(
            company_name=company_name,
            role_title=role_title,
            extracted_text=evidence_text,
            recruiter_email=recruiter_email or None,
            company_website=company_website or None,
        )

        website_result = {
            "checked": False,
            "status": "not_provided",
            "message": (
                "No company website was supplied for a live "
                "technical check."
            ),
        }

        if company_website:
            try:
                website_result = verify_company_website(
                    company_website,
                )
                website_result["checked"] = True
                website_result["status"] = "completed"

            except WebsiteVerificationError as error:
                website_result = {
                    "checked": True,
                    "status": "unavailable",
                    "submitted_url": company_website,
                    "reachable": False,
                    "uses_https": None,
                    "message": str(error),
                    "checks": [
                        {
                            "type": "warning",
                            "label": (
                                "Live website check could not "
                                "be completed"
                            ),
                            "detail": str(error),
                        }
                    ],
                    "disclaimer": (
                        "An unavailable technical check does not "
                        "by itself prove that an internship is "
                        "fraudulent."
                    ),
                }

        domain_risk_points = domain_result.get(
            "domain_risk_points",
            0,
        )

        combined_verification_score = max(
            0,
            assessment_result["verification_score"]
            - domain_risk_points,
        )

        combined_assessment_status = assessment_result[
            "assessment_status"
        ]

        if (
            combined_assessment_status
            == "appears_reasonable"
            and domain_result["domain_status"]
            in {
                "verification_required",
                "high_concern",
            }
        ):
            combined_assessment_status = "verification_required"

        if (
            consistency_result["consistency_status"]
            == "Conflicting Evidence"
            and combined_assessment_status
            == "appears_reasonable"
        ):
            combined_assessment_status = "verification_required"

        combined_recommendations = list(dict.fromkeys(
            assessment_result["recommendations"]
            + domain_result["recommendations"]
            + consistency_result["warnings"]
        ))

        domain_verification_factors = [
            factor
            for factor in domain_result["factors"]
            if factor.get("type") in {
                "warning",
                "evidence",
            }
        ]
        combined_verification_factors = (
            assessment_result.get(
                "verification_factors",
                [],
            )
            + domain_verification_factors
        )

        analysis_data = {
            "user_id": session["user_id"],
            "input_type": input_type,
            "original_text": original_text,
            "company_name": company_name or None,
            "role_title": role_title or None,
            "recruiter_email": (
                domain_result["recruiter_email"]
            ),
            "company_website": (
                domain_result["company_website"]
            ),
            "recruiter_email_domain": (
                domain_result["recruiter_email_domain"]
            ),
            "company_website_domain": (
                domain_result["company_website_domain"]
            ),
            "domain_match": domain_result["domain_match"],
            "domain_verification": domain_result,
            "website_verification": website_result,
            "consistency_verification": consistency_result,
            "consistency_score": consistency_result[
                "consistency_score"
            ],
            "consistency_status": consistency_result[
                "consistency_status"
            ],
            "stipend_monthly": stipend_monthly,
            "hours_per_day": hours_per_day,
            "days_per_week": days_per_week,
            "duration_months": duration_months,
            "effective_hourly_stipend": assessment_result[
                "effective_hourly_stipend"
            ],
            "verification_score": combined_verification_score,
            "value_score": assessment_result[
                "value_score"
            ],
            "assessment_status": combined_assessment_status,
            "detected_flags": assessment_result[
                "detected_flags"
            ],
            "recommendations": combined_recommendations,
            "verification_factors": (
                combined_verification_factors
            ),
            "value_factors": assessment_result.get(
                "value_factors",
                [],
            ),
            "available_hours_per_week": (
                available_hours_per_week
            ),
            "schedule_type": schedule_type,
            "exam_period": exam_period,
            "class_schedule_conflict": (
                class_schedule_conflict
            ),
            "weekly_workload": compatibility_result[
                "weekly_workload"
            ],
            "compatibility_score": compatibility_result[
                "compatibility_score"
            ],
            "compatibility_status": compatibility_result[
                "compatibility_status"
            ],
            "compatibility_reasons": compatibility_result[
                "compatibility_reasons"
            ],
        }

        try:
            supabase = get_authenticated_supabase()

            response = (
                supabase
                .table("internship_analyses")
                .insert(analysis_data)
                .execute()
            )

            if response.data:
                analysis_id = response.data[0]["id"]

                record_timeline_event(
                    supabase=supabase,
                    event_type="assessment_created",
                    title="Assessment created",
                    details=(
                        f"{role_title or 'Internship opportunity'}"
                        f" at {company_name or 'Unknown company'} "
                        "was analyzed."
                    ),
                    analysis_id=analysis_id,
                    metadata={
                        "assessment_status": (
                            combined_assessment_status
                        ),
                        "verification_score": (
                            combined_verification_score
                        ),
                        "value_score": assessment_result[
                            "value_score"
                        ],
                    },
                )

                return redirect(
                    url_for(
                        "analysis_result",
                        analysis_id=analysis_id,
                    )
                )

            flash(
                "The analysis was completed but could not "
                "be saved.",
                "danger",
            )

        except Exception:
            flash(
                "Unable to save the analysis. Please try again.",
                "danger",
            )

    return render_template("analyze.html")


@app.route("/analysis/<analysis_id>")
@login_required
def analysis_result(analysis_id):
    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .select("*")
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .single()
            .execute()
        )

        analysis = response.data

        if not analysis:
            flash(
                "Analysis not found.",
                "danger",
            )
            return redirect(
                url_for("dashboard")
            )

    except Exception:
        flash(
            "Unable to load the analysis result.",
            "danger",
        )
        return redirect(
            url_for("dashboard")
        )

    offer_application = None
    offer_decision = None

    try:
        application_response = (
            supabase
            .table("internship_applications")
            .select("*")
            .eq(
                "user_id",
                session["user_id"],
            )
            .eq(
                "analysis_id",
                analysis_id,
            )
            .eq(
                "status",
                "offer",
            )
            .order(
                "updated_at",
                desc=True,
            )
            .limit(1)
            .execute()
        )

        application_records = (
            application_response.data
            or []
        )

        if application_records:
            offer_application = (
                application_records[0]
            )

            offer_decision = (
                evaluate_offer_decision(
                    analysis=analysis,
                    application=offer_application,
                )
            )

    except Exception:
        app.logger.exception(
            "Offer decision support could not be generated"
        )

        offer_application = None
        offer_decision = None

    status_details = {
        "appears_reasonable": {
            "label": "Appears Reasonable",
            "class": "status-reasonable",
            "message": (
                "No major predefined warning indicators were "
                "detected. Independent verification is still "
                "recommended."
            ),
        },
        "verification_required": {
            "label": "Verification Required",
            "class": "status-verification",
            "message": (
                "Some details require verification before you "
                "accept or provide personal information."
            ),
        },
        "potentially_suspicious": {
            "label": "Potentially Suspicious",
            "class": "status-suspicious",
            "message": (
                "Multiple significant warning indicators were "
                "detected. Proceed cautiously."
            ),
        },
    }

    status = status_details.get(
        analysis["assessment_status"],
        status_details[
            "verification_required"
        ],
    )

    # ---------------------------------------------------------
    # GEMINI-ASSISTED EXPLANATION
    # ---------------------------------------------------------
    # InternShield's deterministic engines remain authoritative.
    # Gemini only explains their already-calculated structured output.

    ai_explanation = None

    try:
        explanation_cache = (
            session.get(
                "internshield_ai_explanations"
            )
            or {}
        )

        analysis_stamp = str(
            analysis.get("updated_at")
            or analysis.get("created_at")
            or ""
        )

        offer_stamp = str(
            (offer_application or {}).get("updated_at")
            or (offer_application or {}).get("offer_reviewed_at")
            or ""
        )

        cache_stamp = analysis_stamp + "|" + offer_stamp
        cached_item = explanation_cache.get(analysis_id) or {}

        if (
            cached_item.get("stamp") == cache_stamp
            and cached_item.get("data")
        ):
            ai_explanation = cached_item["data"]
        else:
            ai_explanation = generate_assessment_explanation(
                analysis,
                offer_decision=offer_decision,
            )

            explanation_cache[analysis_id] = {
                "stamp": cache_stamp,
                "data": ai_explanation,
            }

            # Keep the server-side session lightweight.
            while len(explanation_cache) > 8:
                first_key = next(iter(explanation_cache))
                explanation_cache.pop(first_key, None)

            session["internshield_ai_explanations"] = explanation_cache
            session.modified = True

    except Exception:
        app.logger.exception(
            "AI assessment explanation could not be generated"
        )
        ai_explanation = None

    return render_template(
        "analysis_result.html",
        analysis=analysis,
        status=status,
        offer_application=offer_application,
        offer_decision=offer_decision,
        ai_explanation=ai_explanation,
    )

@app.route("/analysis/<analysis_id>/report")
@login_required
def download_analysis_report(analysis_id):
    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .select("*")
            .eq("id", analysis_id)
            .eq("user_id", session["user_id"])
            .single()
            .execute()
        )

        analysis = response.data

        if not analysis:
            flash(
                "Analysis not found.",
                "danger",
            )
            return redirect(
                url_for("dashboard")
            )

        offer_application = None
        offer_decision = None

        try:
            application_response = (
                supabase
                .table("internship_applications")
                .select("*")
                .eq(
                    "user_id",
                    session["user_id"],
                )
                .eq(
                    "analysis_id",
                    analysis_id,
                )
                .eq(
                    "status",
                    "offer",
                )
                .order(
                    "updated_at",
                    desc=True,
                )
                .limit(1)
                .execute()
            )

            application_records = (
                application_response.data
                or []
            )

            if application_records:
                offer_application = (
                    application_records[0]
                )

                offer_decision = (
                    evaluate_offer_decision(
                        analysis=analysis,
                        application=offer_application,
                    )
                )

        except Exception:
            app.logger.exception(
                "Offer decision could not be added to PDF report"
            )

            offer_application = None
            offer_decision = None

        report_buffer = generate_assessment_report(
            analysis=analysis,
            student_name=session.get(
                "full_name",
                "Student",
            ),
            offer_decision=offer_decision,
            offer_application=offer_application,
        )

        filename = (
            "InternShield_Assessment_"
            f"{analysis_id[:8]}.pdf"
        )

        return send_file(
            report_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except Exception:
        app.logger.exception(
            "The PDF report could not be generated"
        )

        flash(
            "The PDF report could not be generated.",
            "danger",
        )

        return redirect(
            url_for(
                "analysis_result",
                analysis_id=analysis_id,
            )
        )

@app.route("/logout")
@login_required
def logout():
    try:
        supabase = get_supabase_client()

        supabase.auth.set_session(
            session["access_token"],
            session["refresh_token"],
        )

        supabase.auth.sign_out()

    except Exception:
        pass

    finally:
        session.clear()

    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/health")
def health():
    get_supabase_client()

    return {
        "application": "InternShield AI",
        "status": "running",
        "supabase": "configured",
    }


if __name__ == "__main__":
    app.run(debug=True)
