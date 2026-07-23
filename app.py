import os
from datetime import timedelta
from functools import wraps

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
from services.compatibility_engine import calculate_compatibility
from services.document_extractor import (
    DocumentExtractionError,
    extract_pdf_text,
)
from services.image_extractor import (
    ImageExtractionError,
    extract_image_text,
)
from services.report_generator import (
    generate_assessment_report,
)
from supabase_client import get_supabase_client

load_dotenv()

app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
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


@app.route("/dashboard")
@login_required
def dashboard():
    analyses = []

    try:
        supabase = get_authenticated_supabase()

        response = (
            supabase
            .table("internship_analyses")
            .select(
                "id, company_name, role_title, "
                "verification_score, value_score, "
                "assessment_status, created_at"
            )
            .eq("user_id", session["user_id"])
            .order("created_at", desc=True)
            .execute()
        )

        analyses = response.data or []

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

        if has_pdf:
            try:
                extracted_text = extract_pdf_text(uploaded_pdf)

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

        analysis_data = {
            "user_id": session["user_id"],
            "input_type": input_type,
            "original_text": original_text,
            "company_name": company_name or None,
            "role_title": role_title or None,
            "stipend_monthly": stipend_monthly,
            "hours_per_day": hours_per_day,
            "days_per_week": days_per_week,
            "duration_months": duration_months,
            "effective_hourly_stipend": assessment_result[
                "effective_hourly_stipend"
            ],
            "verification_score": assessment_result[
                "verification_score"
            ],
            "value_score": assessment_result[
                "value_score"
            ],
            "assessment_status": assessment_result[
                "assessment_status"
            ],
            "detected_flags": assessment_result[
                "detected_flags"
            ],
            "recommendations": assessment_result[
                "recommendations"
            ],
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
            flash("Analysis not found.", "danger")
            return redirect(url_for("dashboard"))

    except Exception:
        flash(
            "Unable to load the analysis result.",
            "danger",
        )
        return redirect(url_for("dashboard"))

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
        status_details["verification_required"],
    )

    return render_template(
        "analysis_result.html",
        analysis=analysis,
        status=status,
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
            flash("Analysis not found.", "danger")
            return redirect(url_for("dashboard"))

        report_buffer = generate_assessment_report(
            analysis=analysis,
            student_name=session.get(
                "full_name",
                "Student",
            ),
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