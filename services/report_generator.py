from io import BytesIO
import json

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# -------------------------------------------------------------------
# Colours
# -------------------------------------------------------------------

TEAL = colors.HexColor("#16BFA6")
DARK_TEAL = colors.HexColor("#0F8F7E")
DARK_NAVY = colors.HexColor("#071525")
LIGHT_NAVY = colors.HexColor("#EAF5F4")
BORDER = colors.HexColor("#B8D2D0")
TEXT = colors.HexColor("#172B35")
MUTED = colors.HexColor("#607982")

GREEN = colors.HexColor("#198754")
GREEN_BG = colors.HexColor("#E8F6EE")

AMBER = colors.HexColor("#D98C00")
AMBER_BG = colors.HexColor("#FFF4D6")

RED = colors.HexColor("#DC3545")
RED_BG = colors.HexColor("#FCE8EA")

GREY_BG = colors.HexColor("#F3F6F7")
WHITE = colors.white


# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

def safe_text(value, fallback="Not provided"):
    """Return safe printable text for PDF paragraphs."""

    if value is None:
        return fallback

    value = str(value).strip()

    if not value:
        return fallback

    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def as_list(value):
    """
    Convert a Supabase JSON field, JSON string, list or single value
    into a Python list.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, dict):
        return [value]

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return []

        try:
            parsed = json.loads(stripped)

            if isinstance(parsed, list):
                return parsed

            if isinstance(parsed, dict):
                return [parsed]

        except (json.JSONDecodeError, TypeError):
            return [stripped]

    return [value]


def format_number(
    value,
    decimal_places=0,
    fallback="N/A",
):
    try:
        number = float(value)

        if decimal_places == 0:
            return str(int(round(number)))

        return f"{number:.{decimal_places}f}"

    except (TypeError, ValueError):
        return fallback


def format_date(value):
    if not value:
        return "Not available"

    value = str(value)

    # Supabase timestamps normally begin with YYYY-MM-DD.
    if len(value) >= 10:
        return value[:10]

    return value


def display_status(status):
    labels = {
        "appears_reasonable": "Appears Reasonable",
        "verification_required": "Verification Required",
        "potentially_suspicious": "Potentially Suspicious",
        "manageable": "Manageable",
        "demanding": "Demanding",
        "conflict_risk": "Conflict Risk",
    }

    normalized = str(
        status or ""
    ).strip().lower()

    return labels.get(
        normalized,
        normalized.replace(
            "_",
            " ",
        ).title()
        or "Not available",
    )


def status_colours(status):
    normalized = str(
        status or ""
    ).strip().lower()

    if normalized in {
        "appears_reasonable",
        "manageable",
    }:
        return GREEN, GREEN_BG

    if normalized in {
        "verification_required",
        "demanding",
    }:
        return AMBER, AMBER_BG

    if normalized in {
        "potentially_suspicious",
        "conflict_risk",
    }:
        return RED, RED_BG

    return MUTED, GREY_BG


def decision_colours(decision_class):
    normalized = str(
        decision_class or ""
    ).strip().lower()

    if normalized == "success":
        return GREEN, GREEN_BG

    if normalized == "danger":
        return RED, RED_BG

    return AMBER, AMBER_BG


def get_detected_flags(analysis):
    """
    Support different field names that may have been used during
    earlier InternShield development steps.
    """

    value = (
        analysis.get("detected_flags")
        or analysis.get("detected_indicators")
        or analysis.get("flags")
        or []
    )

    return as_list(value)


def get_recommendations(analysis):
    value = (
        analysis.get("recommendations")
        or analysis.get("recommended_checks")
        or []
    )

    return as_list(value)


def get_compatibility_reasons(analysis):
    return as_list(
        analysis.get("compatibility_reasons")
    )


def get_verification_factors(analysis):
    return as_list(
        analysis.get("verification_factors")
    )


def get_value_factors(analysis):
    return as_list(
        analysis.get("value_factors")
    )


def format_points(value):
    try:
        points = float(value)

    except (TypeError, ValueError):
        return "0"

    if points.is_integer():
        points = int(points)

    return (
        f"+{points}"
        if points > 0
        else str(points)
    )


# -------------------------------------------------------------------
# Page decoration
# -------------------------------------------------------------------

def draw_page(canvas, document):
    canvas.saveState()

    page_width, page_height = A4

    # Header
    canvas.setFillColor(TEAL)

    canvas.setFont(
        "Helvetica-Bold",
        14,
    )

    canvas.drawString(
        18 * mm,
        page_height - 16 * mm,
        "InternShield AI",
    )

    canvas.setFillColor(MUTED)

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.drawString(
        18 * mm,
        page_height - 21 * mm,
        "Internship Safety, Value and Academic Compatibility Report",
    )

    # Header line
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)

    canvas.line(
        18 * mm,
        page_height - 25 * mm,
        page_width - 18 * mm,
        page_height - 25 * mm,
    )

    # Footer line
    canvas.line(
        18 * mm,
        15 * mm,
        page_width - 18 * mm,
        15 * mm,
    )

    canvas.setFillColor(MUTED)

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.drawString(
        18 * mm,
        10 * mm,
        "InternShield AI - Explainable Internship Assessment",
    )

    canvas.drawRightString(
        page_width - 18 * mm,
        10 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()


# -------------------------------------------------------------------
# Main report generator
# -------------------------------------------------------------------

def generate_assessment_report(
    analysis,
    student_name="Student",
    offer_decision=None,
    offer_application=None,
):
    """
    Generate an InternShield assessment PDF.

    Parameters
    ----------
    analysis:
        Dictionary returned from Supabase for one internship analysis.

    student_name:
        Full name of the authenticated student.

    offer_decision:
        Optional dictionary returned by evaluate_offer_decision().
        When provided, the PDF includes Final Offer Decision Support.

    offer_application:
        Optional linked application tracker record.

    Returns
    -------
    BytesIO
        In-memory PDF file ready to be returned using Flask send_file().
    """

    if analysis is None:
        analysis = {}

    pdf_buffer = BytesIO()

    document = BaseDocTemplate(
        pdf_buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
        title="InternShield AI Assessment Report",
        author="InternShield AI",
        subject=(
            "Internship safety, value and academic "
            "compatibility assessment"
        ),
    )

    page_width, page_height = A4

    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        (
            page_width
            - document.leftMargin
            - document.rightMargin
        ),
        (
            page_height
            - document.topMargin
            - document.bottomMargin
        ),
        id="report_frame",
    )

    document.addPageTemplates(
        [
            PageTemplate(
                id="report_page",
                frames=[frame],
                onPage=draw_page,
            )
        ]
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=DARK_NAVY,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=DARK_NAVY,
        spaceBefore=2 * mm,
        spaceAfter=3 * mm,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=TEXT,
        alignment=TA_LEFT,
        spaceAfter=1.5 * mm,
    )

    small_style = ParagraphStyle(
        "Small",
        parent=body_style,
        fontSize=7.5,
        leading=10,
    )

    table_label_style = ParagraphStyle(
        "TableLabel",
        parent=small_style,
        fontName="Helvetica-Bold",
        textColor=DARK_NAVY,
    )

    score_label_style = ParagraphStyle(
        "ScoreLabel",
        parent=small_style,
        fontName="Helvetica",
        textColor=MUTED,
        alignment=TA_CENTER,
    )

    score_value_style = ParagraphStyle(
        "ScoreValue",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=DARK_TEAL,
        alignment=TA_CENTER,
    )

    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=small_style,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=TEXT,
    )

    story = []

    opportunity = (
        analysis.get("role_title")
        or analysis.get("internship_role")
        or analysis.get("role")
        or analysis.get("opportunity")
        or "Internship"
    )

    company = (
        analysis.get("company_name")
        or "Not provided"
    )

    input_method = (
        analysis.get("input_type")
        or analysis.get("input_method")
        or "text"
    )

    assessment_date = (
        analysis.get("created_at")
        or analysis.get("assessment_date")
    )

    verification_score = format_number(
        analysis.get("verification_score"),
        decimal_places=0,
    )

    value_score = format_number(
        analysis.get("value_score"),
        decimal_places=0,
    )

    hourly_stipend_value = (
        analysis.get(
            "effective_hourly_stipend"
        )
    )

    if hourly_stipend_value is None:
        hourly_stipend = "N/A"

    else:
        try:
            hourly_stipend = (
                f"INR "
                f"{float(hourly_stipend_value):.2f}"
            )

        except (TypeError, ValueError):
            hourly_stipend = safe_text(
                hourly_stipend_value
            )

    assessment_status = (
        analysis.get("assessment_status")
        or "Not available"
    )

    assessment_status_label = (
        display_status(
            assessment_status
        )
    )

    (
        assessment_text_colour,
        assessment_background,
    ) = status_colours(
        assessment_status
    )

    compatibility_status = (
        analysis.get(
            "compatibility_status"
        )
    )

    compatibility_score = (
        analysis.get(
            "compatibility_score"
        )
    )

    weekly_workload = (
        analysis.get(
            "weekly_workload"
        )
    )

    available_hours = (
        analysis.get(
            "available_hours_per_week"
        )
    )

    compatibility_reasons = (
        get_compatibility_reasons(
            analysis
        )
    )

    detected_flags = (
        get_detected_flags(
            analysis
        )
    )

    recommendations = (
        get_recommendations(
            analysis
        )
    )

    verification_factors = (
        get_verification_factors(
            analysis
        )
    )

    value_factors = (
        get_value_factors(
            analysis
        )
    )

    # ----------------------------------------------------------------
    # Report title
    # ----------------------------------------------------------------

    story.append(
        Paragraph(
            "InternShield AI",
            title_style,
        )
    )

    # ----------------------------------------------------------------
    # Basic assessment information
    # ----------------------------------------------------------------

    information_data = [
        [
            Paragraph(
                "Student",
                table_label_style,
            ),
            Paragraph(
                safe_text(student_name),
                small_style,
            ),
        ],
        [
            Paragraph(
                "Opportunity",
                table_label_style,
            ),
            Paragraph(
                safe_text(opportunity),
                small_style,
            ),
        ],
        [
            Paragraph(
                "Company",
                table_label_style,
            ),
            Paragraph(
                safe_text(company),
                small_style,
            ),
        ],
        [
            Paragraph(
                "Input method",
                table_label_style,
            ),
            Paragraph(
                safe_text(
                    str(
                        input_method
                    ).upper()
                ),
                small_style,
            ),
        ],
        [
            Paragraph(
                "Assessment date",
                table_label_style,
            ),
            Paragraph(
                safe_text(
                    format_date(
                        assessment_date
                    )
                ),
                small_style,
            ),
        ],
    ]

    information_table = Table(
        information_data,
        colWidths=[
            43 * mm,
            112 * mm,
        ],
    )

    information_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    BORDER,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    GREY_BG,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2.2 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2.2 * mm,
                ),
            ]
        )
    )

    story.append(
        information_table
    )

    story.append(
        Spacer(
            1,
            4 * mm,
        )
    )

    # ----------------------------------------------------------------
    # Internship assessment status
    # ----------------------------------------------------------------

    status_table = Table(
        [
            [
                Paragraph(
                    "Internship assessment",
                    table_label_style,
                ),
                Paragraph(
                    (
                        f"<b>"
                        f"{safe_text(assessment_status_label)}"
                        f"</b>"
                    ),
                    small_style,
                ),
            ]
        ],
        colWidths=[
            78 * mm,
            77 * mm,
        ],
    )

    status_table.setStyle(
        TableStyle(
            [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    assessment_text_colour,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    assessment_background,
                ),
                (
                    "TEXTCOLOR",
                    (1, 0),
                    (1, 0),
                    assessment_text_colour,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, 0),
                    "CENTER",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2.5 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2.5 * mm,
                ),
            ]
        )
    )

    story.append(
        status_table
    )

    story.append(
        Spacer(
            1,
            4 * mm,
        )
    )

    # ----------------------------------------------------------------
    # Internship scores
    # ----------------------------------------------------------------

    story.append(
        Paragraph(
            "Internship scores",
            section_style,
        )
    )

    score_table = Table(
        [
            [
                Paragraph(
                    "Verification",
                    score_label_style,
                ),
                Paragraph(
                    "Value",
                    score_label_style,
                ),
                Paragraph(
                    "Effective hourly stipend",
                    score_label_style,
                ),
            ],
            [
                Paragraph(
                    (
                        f"{verification_score}"
                        "/100"
                    ),
                    score_value_style,
                ),
                Paragraph(
                    (
                        f"{value_score}"
                        "/100"
                    ),
                    score_value_style,
                ),
                Paragraph(
                    hourly_stipend,
                    score_value_style,
                ),
            ],
        ],
        colWidths=[
            51.7 * mm,
            51.7 * mm,
            51.6 * mm,
        ],
    )

    score_table.setStyle(
        TableStyle(
            [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    BORDER,
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    BORDER,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    LIGHT_NAVY,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, 0),
                    2 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, 0),
                    1.5 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 1),
                    (-1, 1),
                    2.5 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 1),
                    (-1, 1),
                    3 * mm,
                ),
            ]
        )
    )

    story.append(
        score_table
    )

    story.append(
        Spacer(
            1,
            4 * mm,
        )
    )

    # ----------------------------------------------------------------
    # Final offer decision support
    # ----------------------------------------------------------------

    if offer_decision:
        decision_score = format_number(
            offer_decision.get(
                "decision_score"
            ),
            decimal_places=0,
        )

        decision_label = (
            offer_decision.get(
                "decision_label"
            )
            or "Review Carefully"
        )

        decision_class = (
            offer_decision.get(
                "decision_class"
            )
            or "warning"
        )

        (
            decision_colour,
            decision_background,
        ) = decision_colours(
            decision_class
        )

        story.append(
            Paragraph(
                "Final offer decision support",
                section_style,
            )
        )

        offer_stage = (
            (
                offer_application
                or {}
            ).get(
                "status"
            )
            or offer_decision.get(
                "application_status"
            )
            or "offer"
        )

        decision_table = Table(
            [
                [
                    Paragraph(
                        "Application stage",
                        score_label_style,
                    ),
                    Paragraph(
                        "Decision score",
                        score_label_style,
                    ),
                    Paragraph(
                        "Current guidance",
                        score_label_style,
                    ),
                ],
                [
                    Paragraph(
                        safe_text(
                            str(
                                offer_stage
                            ).title()
                        ),
                        score_value_style,
                    ),
                    Paragraph(
                        (
                            f"{safe_text(decision_score)}"
                            "/100"
                        ),
                        score_value_style,
                    ),
                    Paragraph(
                        (
                            f"<b>"
                            f"{safe_text(decision_label)}"
                            f"</b>"
                        ),
                        small_style,
                    ),
                ],
            ],
            colWidths=[
                42 * mm,
                42 * mm,
                71 * mm,
            ],
        )

        decision_table.setStyle(
            TableStyle(
                [
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.7,
                        decision_colour,
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        BORDER,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        decision_background,
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 1),
                        (-1, 1),
                        decision_colour,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER",
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        2.2 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        2.2 * mm,
                    ),
                ]
            )
        )

        story.append(
            decision_table
        )

        story.append(
            Spacer(
                1,
                2.5 * mm,
            )
        )

        summary = (
            offer_decision.get(
                "summary"
            )
        )

        if summary:
            summary_table = Table(
                [
                    [
                        Paragraph(
                            safe_text(
                                summary
                            ),
                            body_style,
                        )
                    ]
                ],
                colWidths=[
                    155 * mm
                ],
            )

            summary_table.setStyle(
                TableStyle(
                    [
                        (
                            "BOX",
                            (0, 0),
                            (-1, -1),
                            0.6,
                            decision_colour,
                        ),
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, -1),
                            decision_background,
                        ),
                        (
                            "LEFTPADDING",
                            (0, 0),
                            (-1, -1),
                            4 * mm,
                        ),
                        (
                            "RIGHTPADDING",
                            (0, 0),
                            (-1, -1),
                            4 * mm,
                        ),
                        (
                            "TOPPADDING",
                            (0, 0),
                            (-1, -1),
                            2.5 * mm,
                        ),
                        (
                            "BOTTOMPADDING",
                            (0, 0),
                            (-1, -1),
                            2.5 * mm,
                        ),
                    ]
                )
            )

            story.append(
                summary_table
            )

            story.append(
                Spacer(
                    1,
                    2.5 * mm,
                )
            )

        offer_change_score = (
            offer_decision.get(
                "offer_change_score"
            )
        )

        offer_change_value = (
            (
                f"{format_number(offer_change_score)}"
                "/100"
            )
            if offer_change_score
            is not None
            else "Pending"
        )

        # -------------------------------------------------------------
        # Fix:
        # Consistency now displays only "N/A" when no score exists,
        # instead of the incorrect "N/A/100".
        # -------------------------------------------------------------

        consistency_score = (
            offer_decision.get(
                "consistency_score"
            )
        )

        consistency_display = (
            (
                f"{format_number(consistency_score)}"
                "/100"
            )
            if consistency_score
            is not None
            else "N/A"
        )

        signal_table = Table(
            [
                [
                    Paragraph(
                        "Verification",
                        score_label_style,
                    ),
                    Paragraph(
                        "Opportunity value",
                        score_label_style,
                    ),
                    Paragraph(
                        "Compatibility",
                        score_label_style,
                    ),
                    Paragraph(
                        "Consistency",
                        score_label_style,
                    ),
                    Paragraph(
                        "Final offer match",
                        score_label_style,
                    ),
                ],
                [
                    Paragraph(
                        (
                            f"{format_number(offer_decision.get('verification_score'))}"
                            "/100"
                        ),
                        score_value_style,
                    ),
                    Paragraph(
                        (
                            f"{format_number(offer_decision.get('value_score'))}"
                            "/100"
                        ),
                        score_value_style,
                    ),
                    Paragraph(
                        (
                            f"{format_number(offer_decision.get('compatibility_score'))}"
                            "/100"
                        ),
                        score_value_style,
                    ),
                    Paragraph(
                        consistency_display,
                        score_value_style,
                    ),
                    Paragraph(
                        safe_text(
                            offer_change_value
                        ),
                        score_value_style,
                    ),
                ],
            ],
            colWidths=[
                31 * mm
            ] * 5,
        )

        signal_table.setStyle(
            TableStyle(
                [
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        BORDER,
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.35,
                        BORDER,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        GREY_BG,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER",
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        2 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        2 * mm,
                    ),
                ]
            )
        )

        story.append(
            signal_table
        )

        story.append(
            Spacer(
                1,
                2.5 * mm,
            )
        )

        offer_change_status = (
            offer_decision.get(
                "offer_change_status"
            )
            or "Not Reviewed"
        )

        offer_change_reviewed = bool(
            offer_decision.get(
                "offer_change_reviewed"
            )
        )

        change_note = (
            (
                "Offer Change Detection result: "
                f"{offer_change_status}. "
                "This final-offer comparison is included in "
                "the decision score and guidance."
            )
            if offer_change_reviewed
            else (
                "Final written offer comparison is still pending. "
                "Run Final Offer Analysis in the Application Tracker "
                "before accepting."
            )
        )

        change_note_table = Table(
            [
                [
                    Paragraph(
                        safe_text(
                            change_note
                        ),
                        small_style,
                    )
                ]
            ],
            colWidths=[
                155 * mm
            ],
        )

        change_note_table.setStyle(
            TableStyle(
                [
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        BORDER,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        GREY_BG,
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        2 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        2 * mm,
                    ),
                ]
            )
        )

        story.append(
            change_note_table
        )

        story.append(
            Spacer(
                1,
                3 * mm,
            )
        )

        offer_lists = [
            (
                "Positive signals",
                as_list(
                    offer_decision.get(
                        "strengths"
                    )
                ),
            ),
            (
                "Concerns to review",
                as_list(
                    offer_decision.get(
                        "concerns"
                    )
                ),
            ),
            (
                "Before you decide",
                as_list(
                    offer_decision.get(
                        "next_steps"
                    )
                ),
            ),
        ]

        for heading, items in offer_lists:
            story.append(
                Paragraph(
                    safe_text(
                        heading
                    ),
                    section_style,
                )
            )

            if items:
                for (
                    index,
                    item,
                ) in enumerate(
                    items,
                    start=1,
                ):
                    story.append(
                        Paragraph(
                            (
                                f"{index}."
                                "&nbsp;&nbsp;"
                                f"{safe_text(item)}"
                            ),
                            body_style,
                        )
                    )

            else:
                story.append(
                    Paragraph(
                        (
                            "No additional "
                            "items were recorded."
                        ),
                        small_style,
                    )
                )

            story.append(
                Spacer(
                    1,
                    1.5 * mm,
                )
            )

        decision_factors = [
            factor
            for factor in as_list(
                offer_decision.get(
                    "factors"
                )
            )
            if isinstance(
                factor,
                dict,
            )
        ]

        if decision_factors:
            story.append(
                Paragraph(
                    (
                        "Why InternShield reached "
                        "this guidance"
                    ),
                    section_style,
                )
            )

            factor_rows = [
                [
                    Paragraph(
                        "Impact",
                        table_label_style,
                    ),
                    Paragraph(
                        "Decision factor",
                        table_label_style,
                    ),
                ]
            ]

            for factor in decision_factors:
                impact = (
                    factor.get(
                        "impact",
                        0,
                    )
                )

                label = (
                    factor.get(
                        "label"
                    )
                    or "Decision factor"
                )

                description = (
                    factor.get(
                        "description"
                    )
                    or ""
                )

                factor_rows.append(
                    [
                        Paragraph(
                            (
                                f"<b>"
                                f"{safe_text(format_points(impact))}"
                                f"</b>"
                            ),
                            score_label_style,
                        ),
                        Paragraph(
                            (
                                f"<b>"
                                f"{safe_text(label)}"
                                f"</b>"
                                + (
                                    "<br/>"
                                    "<font color='#607982'>"
                                    f"{safe_text(description)}"
                                    "</font>"
                                    if description
                                    else ""
                                )
                            ),
                            small_style,
                        ),
                    ]
                )

            factor_table = Table(
                factor_rows,
                colWidths=[
                    27 * mm,
                    128 * mm,
                ],
                repeatRows=1,
            )

            factor_styles = [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    BORDER,
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    BORDER,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    GREY_BG,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2 * mm,
                ),
            ]

            for (
                row_index,
                factor,
            ) in enumerate(
                decision_factors,
                start=1,
            ):
                factor_type = str(
                    factor.get(
                        "type"
                    )
                    or "warning"
                ).lower()

                if factor_type == "positive":
                    factor_colour = GREEN
                    factor_background = GREEN_BG

                elif factor_type == "danger":
                    factor_colour = RED
                    factor_background = RED_BG

                else:
                    factor_colour = AMBER
                    factor_background = AMBER_BG

                factor_styles.extend(
                    [
                        (
                            "TEXTCOLOR",
                            (0, row_index),
                            (0, row_index),
                            factor_colour,
                        ),
                        (
                            "BACKGROUND",
                            (0, row_index),
                            (0, row_index),
                            factor_background,
                        ),
                        (
                            "ALIGN",
                            (0, row_index),
                            (0, row_index),
                            "CENTER",
                        ),
                    ]
                )

            factor_table.setStyle(
                TableStyle(
                    factor_styles
                )
            )

            story.append(
                factor_table
            )

            story.append(
                Spacer(
                    1,
                    3 * mm,
                )
            )

        offer_disclaimer = (
            offer_decision.get(
                "disclaimer"
            )
            or (
                "This is decision-support guidance only. "
                "Independently verify the written offer "
                "before accepting."
            )
        )

        offer_disclaimer_table = Table(
            [
                [
                    Paragraph(
                        (
                            "<b>Final offer guidance:</b> "
                            f"{safe_text(offer_disclaimer)}"
                        ),
                        disclaimer_style,
                    )
                ]
            ],
            colWidths=[
                155 * mm
            ],
        )

        offer_disclaimer_table.setStyle(
            TableStyle(
                [
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.7,
                        TEAL,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        LIGHT_NAVY,
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        4 * mm,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        4 * mm,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        3 * mm,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP",
                    ),
                ]
            )
        )

        story.append(
            offer_disclaimer_table
        )

        story.append(
            Spacer(
                1,
                4 * mm,
            )
        )

    # ----------------------------------------------------------------
    # Explainable score breakdown
    # ----------------------------------------------------------------

    if (
        verification_factors
        or value_factors
    ):
        # -------------------------------------------------------------
        # PDF polish fix:
        #
        # Avoid placing "How the scores were calculated" at the very
        # bottom of a page while the factor tables begin on the next
        # page.
        #
        # If less than approximately 58 mm remains, ReportLab starts
        # this section on the next page.
        # -------------------------------------------------------------

        story.append(
            CondPageBreak(
                58 * mm
            )
        )

        score_breakdown_intro = [
            Paragraph(
                "How the scores were calculated",
                section_style,
            ),
            Paragraph(
                (
                    "The following evidence-based adjustments explain "
                    "which submitted details influenced the final scores."
                ),
                small_style,
            ),
            Spacer(
                1,
                1.5 * mm,
            ),
        ]

        story.append(
            KeepTogether(
                score_breakdown_intro
            )
        )

        def build_factor_table(
            title,
            factors,
            final_score,
        ):
            rows = [
                [
                    Paragraph(
                        (
                            f"<b>"
                            f"{safe_text(title)}"
                            f"</b>"
                        ),
                        table_label_style,
                    ),
                    Paragraph(
                        (
                            f"<b>Final score: "
                            f"{safe_text(final_score)}"
                            f"/100</b>"
                        ),
                        small_style,
                    ),
                ]
            ]

            valid_factors = [
                factor
                for factor in factors
                if isinstance(
                    factor,
                    dict,
                )
            ]

            if not valid_factors:
                rows.append(
                    [
                        Paragraph(
                            "N/A",
                            score_label_style,
                        ),
                        Paragraph(
                            (
                                "A detailed breakdown is unavailable "
                                "for this assessment."
                            ),
                            small_style,
                        ),
                    ]
                )

            else:
                for factor in valid_factors:
                    points = (
                        factor.get(
                            "points",
                            0,
                        )
                    )

                    label = (
                        factor.get(
                            "label"
                        )
                        or "Score factor"
                    )

                    evidence = (
                        factor.get(
                            "evidence"
                        )
                    )

                    explanation = (
                        safe_text(
                            label
                        )
                    )

                    if evidence:
                        explanation += (
                            "<br/>"
                            "<font color='#607982'>"
                            "Evidence: "
                            f"{safe_text(evidence)}"
                            "</font>"
                        )

                    rows.append(
                        [
                            Paragraph(
                                (
                                    f"<b>"
                                    f"{safe_text(format_points(points))}"
                                    f"</b>"
                                ),
                                score_label_style,
                            ),
                            Paragraph(
                                explanation,
                                small_style,
                            ),
                        ]
                    )

            factor_table = Table(
                rows,
                colWidths=[
                    25 * mm,
                    130 * mm,
                ],
                repeatRows=1,
            )

            factor_styles = [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    BORDER,
                ),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    BORDER,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    GREY_BG,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, 0),
                    "RIGHT",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    2 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    2 * mm,
                ),
            ]

            for (
                row_index,
                factor,
            ) in enumerate(
                valid_factors,
                start=1,
            ):
                try:
                    points = float(
                        factor.get(
                            "points",
                            0,
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    points = 0

                if points >= 0:
                    point_colour = GREEN
                    point_background = GREEN_BG

                else:
                    point_colour = RED
                    point_background = RED_BG

                factor_styles.extend(
                    [
                        (
                            "TEXTCOLOR",
                            (0, row_index),
                            (0, row_index),
                            point_colour,
                        ),
                        (
                            "BACKGROUND",
                            (0, row_index),
                            (0, row_index),
                            point_background,
                        ),
                        (
                            "ALIGN",
                            (0, row_index),
                            (0, row_index),
                            "CENTER",
                        ),
                    ]
                )

            factor_table.setStyle(
                TableStyle(
                    factor_styles
                )
            )

            return factor_table

        story.append(
            build_factor_table(
                "Verification factors",
                verification_factors,
                verification_score,
            )
        )

        story.append(
            Spacer(
                1,
                2.5 * mm,
            )
        )

        story.append(
            build_factor_table(
                "Opportunity value factors",
                value_factors,
                value_score,
            )
        )

        story.append(
            Spacer(
                1,
                4 * mm,
            )
        )

    # ----------------------------------------------------------------
    # Academic compatibility
    # ----------------------------------------------------------------

    if (
        compatibility_status
        or compatibility_score
        is not None
    ):
        compatibility_label = (
            display_status(
                compatibility_status
            )
        )

        (
            compatibility_colour,
            compatibility_background,
        ) = status_colours(
            compatibility_status
        )

        compatibility_heading = Table(
            [
                [
                    Paragraph(
                        "Academic compatibility",
                        section_style,
                    ),
                    Paragraph(
                        (
                            f"<b>"
                            f"{safe_text(compatibility_label)}"
                            f"</b>"
                        ),
                        small_style,
                    ),
                ]
            ],
            colWidths=[
                105 * mm,
                50 * mm,
            ],
        )

        compatibility_heading.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (1, 0),
                        (1, 0),
                        compatibility_background,
                    ),
                    (
                        "TEXTCOLOR",
                        (1, 0),
                        (1, 0),
                        compatibility_colour,
                    ),
                    (
                        "BOX",
                        (1, 0),
                        (1, 0),
                        0.7,
                        compatibility_colour,
                    ),
                    (
                        "ALIGN",
                        (1, 0),
                        (1, 0),
                        "CENTER",
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "LEFTPADDING",
                        (1, 0),
                        (1, 0),
                        3 * mm,
                    ),
                    (
                        "RIGHTPADDING",
                        (1, 0),
                        (1, 0),
                        3 * mm,
                    ),
                    (
                        "TOPPADDING",
                        (1, 0),
                        (1, 0),
                        2 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (1, 0),
                        (1, 0),
                        2 * mm,
                    ),
                ]
            )
        )

        compatibility_data = [
            [
                Paragraph(
                    "Compatibility score",
                    score_label_style,
                ),
                Paragraph(
                    "Internship workload",
                    score_label_style,
                ),
                Paragraph(
                    "Student availability",
                    score_label_style,
                ),
            ],
            [
                Paragraph(
                    (
                        f"{format_number(compatibility_score)}"
                        "/100"
                    ),
                    score_value_style,
                ),
                Paragraph(
                    (
                        f"{format_number(weekly_workload, 1)}"
                        " hours/week"
                    ),
                    score_value_style,
                ),
                Paragraph(
                    (
                        f"{format_number(available_hours, 1)}"
                        " hours/week"
                    ),
                    score_value_style,
                ),
            ],
        ]

        compatibility_table = Table(
            compatibility_data,
            colWidths=[
                51.7 * mm,
                51.7 * mm,
                51.6 * mm,
            ],
        )

        compatibility_table.setStyle(
            TableStyle(
                [
                    (
                        "BOX",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        BORDER,
                    ),
                    (
                        "INNERGRID",
                        (0, 0),
                        (-1, -1),
                        0.5,
                        BORDER,
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        GREY_BG,
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "ALIGN",
                        (0, 0),
                        (-1, -1),
                        "CENTER",
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, 0),
                        2 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, 0),
                        1.5 * mm,
                    ),
                    (
                        "TOPPADDING",
                        (0, 1),
                        (-1, 1),
                        2.5 * mm,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 1),
                        (-1, 1),
                        3 * mm,
                    ),
                ]
            )
        )

        story.append(
            KeepTogether(
                [
                    compatibility_heading,
                    Spacer(
                        1,
                        2 * mm,
                    ),
                    compatibility_table,
                ]
            )
        )

        if compatibility_reasons:
            story.append(
                Spacer(
                    1,
                    2.5 * mm,
                )
            )

            reason_content = [
                Paragraph(
                    "Compatibility explanation",
                    section_style,
                )
            ]

            for reason in (
                compatibility_reasons
            ):
                reason_content.append(
                    Paragraph(
                        (
                            "&#8226;"
                            "&nbsp;&nbsp;"
                            f"{safe_text(reason)}"
                        ),
                        body_style,
                    )
                )

            story.append(
                KeepTogether(
                    reason_content
                )
            )

        story.append(
            Spacer(
                1,
                3 * mm,
            )
        )

    # ----------------------------------------------------------------
    # Detected indicators
    # ----------------------------------------------------------------

    story.append(
        Paragraph(
            "Detected indicators",
            section_style,
        )
    )

    if detected_flags:
        for flag in detected_flags:
            if isinstance(
                flag,
                dict,
            ):
                title = (
                    flag.get(
                        "title"
                    )
                    or "Warning indicator"
                )

                severity = str(
                    flag.get(
                        "severity"
                    )
                    or "medium"
                ).upper()

                matched_phrase = (
                    flag.get(
                        "matched_phrase"
                    )
                    or flag.get(
                        "matched"
                    )
                    or "Not specified"
                )

                if severity == "HIGH":
                    severity_colour = RED

                elif severity == "MEDIUM":
                    severity_colour = AMBER

                else:
                    severity_colour = MUTED

                indicator_content = [
                    Paragraph(
                        (
                            f"<font color='"
                            f"{severity_colour.hexval()}"
                            f"'>"
                            f"<b>"
                            f"{safe_text(severity)}"
                            f"</b>"
                            f"</font>"
                            "&nbsp;&nbsp;"
                            f"<b>"
                            f"{safe_text(title)}"
                            f"</b>"
                        ),
                        body_style,
                    ),
                    Paragraph(
                        (
                            "Matched phrase: "
                            f"{safe_text(matched_phrase)}"
                        ),
                        small_style,
                    ),
                ]

                story.append(
                    KeepTogether(
                        indicator_content
                    )
                )

                story.append(
                    Spacer(
                        1,
                        1 * mm,
                    )
                )

            else:
                story.append(
                    Paragraph(
                        (
                            "&#8226;"
                            "&nbsp;&nbsp;"
                            f"{safe_text(flag)}"
                        ),
                        body_style,
                    )
                )

    else:
        story.append(
            Paragraph(
                (
                    "No predefined warning indicators "
                    "were detected."
                ),
                body_style,
            )
        )

    story.append(
        Spacer(
            1,
            3 * mm,
        )
    )

    # ----------------------------------------------------------------
    # Recommended checks and disclaimer
    #
    # KeepTogether prevents only the last recommendation from being
    # pushed alone onto a new page.
    # ----------------------------------------------------------------

    recommendation_block = [
        Paragraph(
            "Recommended checks",
            section_style,
        )
    ]

    if recommendations:
        for (
            index,
            recommendation,
        ) in enumerate(
            recommendations,
            start=1,
        ):
            if isinstance(
                recommendation,
                dict,
            ):
                recommendation_text = (
                    recommendation.get(
                        "text"
                    )
                    or recommendation.get(
                        "recommendation"
                    )
                    or str(
                        recommendation
                    )
                )

            else:
                recommendation_text = (
                    recommendation
                )

            recommendation_block.append(
                Paragraph(
                    (
                        f"{index}."
                        "&nbsp;&nbsp;"
                        f"{safe_text(recommendation_text)}"
                    ),
                    body_style,
                )
            )

    else:
        recommendation_block.append(
            Paragraph(
                (
                    "Verify the company website, recruiter identity "
                    "and written responsibilities before accepting."
                ),
                body_style,
            )
        )

    recommendation_block.append(
        Spacer(
            1,
            3 * mm,
        )
    )

    disclaimer_table = Table(
        [
            [
                Paragraph(
                    (
                        "<b>Important:</b> "
                        "This automated assessment does not "
                        "prove that an internship is legitimate "
                        "or fraudulent. Verify the company, "
                        "recruiter and written terms independently "
                        "before accepting the opportunity or "
                        "sharing personal information."
                    ),
                    disclaimer_style,
                )
            ]
        ],
        colWidths=[
            155 * mm
        ],
    )

    disclaimer_table.setStyle(
        TableStyle(
            [
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.7,
                    AMBER,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    AMBER_BG,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4 * mm,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3 * mm,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
            ]
        )
    )

    recommendation_block.append(
        disclaimer_table
    )

    story.append(
        KeepTogether(
            recommendation_block
        )
    )

    # ----------------------------------------------------------------
    # Build PDF
    # ----------------------------------------------------------------

    document.build(
        story
    )

    pdf_buffer.seek(
        0
    )

    return pdf_buffer