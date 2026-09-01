def _safe_score(value):
    """
    Convert a score into a number between 0 and 100.
    """

    if value is None:
        return None

    try:
        score = float(value)
    except (TypeError, ValueError):
        return None

    return max(0, min(100, score))


def _normalise_text(value):
    return str(value or "").strip().lower()



def _as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def _flag_severity_counts(flags):
    counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    for flag in flags or []:
        if not isinstance(flag, dict):
            continue

        severity = _normalise_text(
            flag.get("severity")
        )

        if severity in counts:
            counts[severity] += 1

    return counts


def _add_factor(
    factors,
    label,
    description,
    impact,
    factor_type,
):
    factors.append({
        "label": label,
        "description": description,
        "impact": impact,
        "type": factor_type,
    })


def evaluate_offer_decision(
    analysis,
    application=None,
):
    """
    Produce explainable final offer guidance from an
    existing InternShield assessment.

    The result is decision support, not proof that the
    company or internship is legitimate.
    """

    analysis = analysis or {}
    application = application or {}

    # =====================================================
    # CORE SCORES
    # =====================================================

    verification_score = _safe_score(
        analysis.get("verification_score")
    )

    value_score = _safe_score(
        analysis.get("value_score")
    )

    compatibility_score = _safe_score(
        analysis.get("compatibility_score")
    )

    consistency_score = _safe_score(
        analysis.get("consistency_score")
    )

    # =====================================================
    # FINAL OFFER CHANGE DATA
    # =====================================================

    offer_change_analysis = (
        application.get("offer_change_analysis")
        or {}
    )

    offer_change_score = _safe_score(
        application.get("offer_change_score")
        if application.get("offer_change_score") is not None
        else offer_change_analysis.get("change_score")
    )

    offer_change_status = (
        application.get("offer_change_status")
        or offer_change_analysis.get("change_status")
        or ""
    )

    offer_change_status_normalised = _normalise_text(
        offer_change_status
    )

    offer_change_reviewed = bool(
        offer_change_analysis
        or offer_change_score is not None
        or offer_change_status
    )

    critical_offer_changes = _as_list(
        offer_change_analysis.get("critical_changes")
    )

    offer_change_warnings = _as_list(
        offer_change_analysis.get("warnings")
    )

    weighted_scores = []

    if verification_score is not None:
        weighted_scores.append(
            (verification_score, 0.40)
        )

    if value_score is not None:
        weighted_scores.append(
            (value_score, 0.20)
        )

    if compatibility_score is not None:
        weighted_scores.append(
            (compatibility_score, 0.20)
        )

    if consistency_score is not None:
        weighted_scores.append(
            (consistency_score, 0.20)
        )

    if weighted_scores:
        total_weight = sum(
            weight
            for _, weight in weighted_scores
        )

        base_score = sum(
            score * weight
            for score, weight in weighted_scores
        ) / total_weight
    else:
        base_score = 50

    factors = []
    strengths = []
    concerns = []
    next_steps = []

    penalty = 0
    severe_blocker = False
    review_required = False

    # =====================================================
    # VERIFICATION SCORE
    # =====================================================

    if verification_score is not None:
        if verification_score >= 75:
            strengths.append(
                "The assessment has a relatively strong "
                "verification score."
            )

            _add_factor(
                factors,
                "Verification score",
                (
                    f"Verification score is "
                    f"{verification_score:.0f}/100."
                ),
                0,
                "positive",
            )

        elif verification_score >= 50:
            review_required = True

            concerns.append(
                "Some verification signals still require "
                "independent checking."
            )

            penalty += 5

            _add_factor(
                factors,
                "Verification score",
                (
                    f"Verification score is "
                    f"{verification_score:.0f}/100."
                ),
                -5,
                "warning",
            )

        else:
            review_required = True

            concerns.append(
                "The verification score is low."
            )

            penalty += 15

            _add_factor(
                factors,
                "Low verification score",
                (
                    f"Verification score is only "
                    f"{verification_score:.0f}/100."
                ),
                -15,
                "danger",
            )

    # =====================================================
    # VALUE SCORE
    # =====================================================

    if value_score is not None:
        if value_score >= 75:
            strengths.append(
                "The opportunity has a strong estimated "
                "value score."
            )

            _add_factor(
                factors,
                "Opportunity value",
                (
                    f"Value score is "
                    f"{value_score:.0f}/100."
                ),
                0,
                "positive",
            )

        elif value_score < 50:
            review_required = True

            concerns.append(
                "The estimated opportunity value is low."
            )

            penalty += 6

            _add_factor(
                factors,
                "Low opportunity value",
                (
                    f"Value score is "
                    f"{value_score:.0f}/100."
                ),
                -6,
                "warning",
            )

    # =====================================================
    # ACADEMIC COMPATIBILITY
    # =====================================================

    compatibility_status = _normalise_text(
        analysis.get("compatibility_status")
    )

    if compatibility_score is not None:
        if (
            compatibility_score >= 75
            and compatibility_status == "manageable"
        ):
            strengths.append(
                "The internship workload appears compatible "
                "with the student's available schedule."
            )

            _add_factor(
                factors,
                "Academic compatibility",
                (
                    f"Compatibility score is "
                    f"{compatibility_score:.0f}/100 "
                    "and the workload is marked manageable."
                ),
                0,
                "positive",
            )

        elif compatibility_status == "conflict_risk":
            review_required = True

            concerns.append(
                "The internship may conflict with college, "
                "classes or academic commitments."
            )

            penalty += 12

            _add_factor(
                factors,
                "Academic conflict risk",
                (
                    f"Compatibility score is "
                    f"{compatibility_score:.0f}/100."
                ),
                -12,
                "danger",
            )

        elif compatibility_score < 60:
            review_required = True

            concerns.append(
                "The expected workload may be difficult to "
                "manage alongside academic commitments."
            )

            penalty += 7

            _add_factor(
                factors,
                "Demanding workload",
                (
                    f"Compatibility score is "
                    f"{compatibility_score:.0f}/100."
                ),
                -7,
                "warning",
            )

    # Explicit academic conflicts must affect the final offer
    # decision even when the compatibility status is only "demanding".

    if analysis.get("class_schedule_conflict"):
        review_required = True

        concerns.append(
            "The internship timing directly conflicts with "
            "the student's lecture or practical schedule."
        )

        penalty += 10

        _add_factor(
            factors,
            "Lecture or practical conflict",
            (
                "The assessment records an explicit conflict "
                "with the student's class schedule."
            ),
            -10,
            "danger",
        )

    if analysis.get("exam_period"):
        review_required = True

        concerns.append(
            "The internship overlaps with an examination period."
        )

        penalty += 6

        _add_factor(
            factors,
            "Examination overlap",
            (
                "The assessment records that the internship "
                "overlaps with an examination period."
            ),
            -6,
            "warning",
        )

    # =====================================================
    # MAIN ASSESSMENT STATUS
    # =====================================================

    assessment_status = _normalise_text(
        analysis.get("assessment_status")
    )

    if assessment_status == "potentially_suspicious":
        severe_blocker = True

        concerns.append(
            "The original internship assessment was marked "
            "Potentially Suspicious."
        )

        penalty += 25

        _add_factor(
            factors,
            "Potentially suspicious assessment",
            (
                "Multiple important warning indicators were "
                "identified in the original assessment."
            ),
            -25,
            "danger",
        )

    elif assessment_status == "verification_required":
        review_required = True

        concerns.append(
            "Important details still require independent "
            "verification."
        )

        penalty += 10

        _add_factor(
            factors,
            "Verification required",
            (
                "The original assessment requires additional "
                "verification before accepting."
            ),
            -10,
            "warning",
        )

    else:
        strengths.append(
            "The original assessment was marked "
            "Appears Reasonable."
        )

    # =====================================================
    # CONSISTENCY
    # =====================================================

    consistency_status = _normalise_text(
        analysis.get("consistency_status")
    )

    if consistency_status == "conflicting evidence":
        severe_blocker = True

        concerns.append(
            "Conflicting evidence was found between the "
            "submitted details and internship evidence."
        )

        penalty += 20

        _add_factor(
            factors,
            "Conflicting evidence",
            (
                "Company, role or recruiter information "
                "contains significant inconsistencies."
            ),
            -20,
            "danger",
        )

    elif consistency_status == "review recommended":
        review_required = True

        concerns.append(
            "Some evidence could not be fully confirmed."
        )

        penalty += 8

        _add_factor(
            factors,
            "Evidence review recommended",
            (
                "The consistency checker recommends "
                "additional verification."
            ),
            -8,
            "warning",
        )

    elif consistency_status == "consistent":
        strengths.append(
            "The submitted evidence is internally consistent."
        )

    # =====================================================
    # DOMAIN VERIFICATION
    # =====================================================

    domain = (
        analysis.get("domain_verification")
        or {}
    )

    domain_status = _normalise_text(
        domain.get("domain_status")
    )

    if domain_status == "high_concern":
        severe_blocker = True

        concerns.append(
            "The recruiter/company domain verification "
            "contains a high-concern signal."
        )

        penalty += 18

        _add_factor(
            factors,
            "Recruiter domain high concern",
            (
                "Recruiter and company domain information "
                "requires serious verification."
            ),
            -18,
            "danger",
        )

    elif domain_status == "verification_required":
        review_required = True

        concerns.append(
            "Recruiter or company domain details require "
            "additional verification."
        )

        penalty += 8

        _add_factor(
            factors,
            "Recruiter verification required",
            (
                "The recruiter or company domain could not "
                "be confidently confirmed."
            ),
            -8,
            "warning",
        )

    elif domain_status == "consistent":
        strengths.append(
            "Recruiter and company domain information "
            "appears consistent."
        )

    # =====================================================
    # DETECTED FLAGS
    # =====================================================

    flags = (
        analysis.get("detected_flags")
        or []
    )

    severity_counts = _flag_severity_counts(flags)

    high_flags = severity_counts["high"]
    medium_flags = severity_counts["medium"]

    if high_flags:
        high_penalty = min(
            24,
            high_flags * 12,
        )

        penalty += high_penalty
        review_required = True

        if high_flags >= 2:
            severe_blocker = True

        concerns.append(
            (
                f"{high_flags} high-severity warning "
                f"indicator"
                f"{'' if high_flags == 1 else 's'} "
                "were detected."
            )
        )

        _add_factor(
            factors,
            "High-severity warning indicators",
            (
                f"{high_flags} high-severity "
                "indicator(s) were detected."
            ),
            -high_penalty,
            "danger",
        )

    if medium_flags:
        medium_penalty = min(
            10,
            medium_flags * 5,
        )

        penalty += medium_penalty
        review_required = True

        concerns.append(
            (
                f"{medium_flags} medium-severity warning "
                f"indicator"
                f"{'' if medium_flags == 1 else 's'} "
                "were detected."
            )
        )

        _add_factor(
            factors,
            "Medium-severity indicators",
            (
                f"{medium_flags} medium-severity "
                "indicator(s) were detected."
            ),
            -medium_penalty,
            "warning",
        )

    # =====================================================
    # WEBSITE SIGNALS
    # =====================================================

    website = (
        analysis.get("website_verification")
        or {}
    )

    if website.get("checked"):
        if website.get("reachable") is False:
            review_required = True

            concerns.append(
                "The supplied company website could not be "
                "successfully reached during the technical "
                "verification."
            )

            penalty += 4

            _add_factor(
                factors,
                "Website verification unavailable",
                (
                    "The supplied company website did not "
                    "produce a successful technical response."
                ),
                -4,
                "warning",
            )

        elif website.get("reachable") is True:
            strengths.append(
                "The supplied company website responded to "
                "the technical verification check."
            )

    # =====================================================
    # FINAL OFFER CHANGE DETECTION
    # =====================================================

    if application.get("status") == "offer":
        if not offer_change_reviewed:
            review_required = True

            concerns.append(
                "The final written offer has not yet been "
                "compared with the original assessed opportunity."
            )

            penalty += 4

            _add_factor(
                factors,
                "Final offer not yet compared",
                (
                    "Run Offer Change Detection before accepting "
                    "so changed terms can influence the final "
                    "decision support."
                ),
                -4,
                "warning",
            )

        elif (
            offer_change_status_normalised
            == "consistent with original"
        ):
            strengths.append(
                "The final written offer is broadly consistent "
                "with the original assessed opportunity."
            )

            _add_factor(
                factors,
                "Final offer consistency",
                (
                    "Offer Change Detection found the final offer "
                    "broadly consistent with the original assessment"
                    + (
                        f" ({offer_change_score:.0f}/100)."
                        if offer_change_score is not None
                        else "."
                    )
                ),
                0,
                "positive",
            )

        elif (
            offer_change_status_normalised
            == "review changes"
        ):
            review_required = True

            concerns.append(
                "The final written offer contains changed terms "
                "that should be reviewed before accepting."
            )

            change_penalty = 8

            if (
                offer_change_score is not None
                and offer_change_score < 70
            ):
                change_penalty = 12

            penalty += change_penalty

            _add_factor(
                factors,
                "Final offer terms changed",
                (
                    "Offer Change Detection recommends reviewing "
                    "differences between the original opportunity "
                    "and the final written offer"
                    + (
                        f" ({offer_change_score:.0f}/100)."
                        if offer_change_score is not None
                        else "."
                    )
                ),
                -change_penalty,
                "warning",
            )

        elif (
            offer_change_status_normalised
            == "major changes detected"
        ):
            review_required = True

            concerns.append(
                "Major differences were detected between the "
                "original opportunity and the final written offer."
            )

            penalty += 18

            _add_factor(
                factors,
                "Major final-offer changes",
                (
                    "The final offer materially differs from the "
                    "original assessed opportunity"
                    + (
                        f" ({offer_change_score:.0f}/100)."
                        if offer_change_score is not None
                        else "."
                    )
                ),
                -18,
                "danger",
            )

            if (
                critical_offer_changes
                or (
                    offer_change_score is not None
                    and offer_change_score < 45
                )
            ):
                severe_blocker = True

        elif offer_change_reviewed:
            review_required = True

            concerns.append(
                "The final offer comparison produced an "
                "unrecognised review status."
            )

            penalty += 6

            _add_factor(
                factors,
                "Final offer comparison requires review",
                (
                    "Offer Change Detection completed, but its "
                    "result should be reviewed manually."
                ),
                -6,
                "warning",
            )

    if critical_offer_changes:
        severe_blocker = True

        concerns.append(
            (
                f"{len(critical_offer_changes)} critical final-offer "
                "change"
                f"{'' if len(critical_offer_changes) == 1 else 's'} "
                "require independent verification."
            )
        )

        penalty += 10

        _add_factor(
            factors,
            "Critical final-offer changes",
            (
                f"{len(critical_offer_changes)} critical change(s) "
                "were reported by Offer Change Detection."
            ),
            -10,
            "danger",
        )

    elif offer_change_warnings and offer_change_reviewed:
        review_required = True

    # =====================================================
    # FINAL SCORE
    # =====================================================

    final_score = round(
        max(
            0,
            min(
                100,
                base_score - penalty,
            ),
        )
    )

    # =====================================================
    # FINAL RECOMMENDATION
    # =====================================================

    if (
        severe_blocker
        or final_score < 45
    ):
        decision_code = "avoid"
        decision_label = "Avoid / Do Not Accept Yet"
        decision_class = "danger"

        summary = (
            "Important concerns remain in this offer. "
            "Do not accept until the warning signals have "
            "been independently resolved."
        )

    elif (
        review_required
        or final_score < 75
    ):
        decision_code = "review"
        decision_label = "Review Carefully"
        decision_class = "warning"

        summary = (
            "The offer has positive aspects, but some "
            "important details still require verification "
            "or consideration before accepting."
        )

    else:
        decision_code = "accept"
        decision_label = "Acceptable to Consider"
        decision_class = "success"

        summary = (
            "The available assessment signals are generally "
            "favourable. Review the written offer and confirm "
            "all important terms before making the final "
            "decision."
        )

    # Add final-offer context to the decision summary.
    if (
        offer_change_reviewed
        and offer_change_status_normalised
        == "major changes detected"
    ):
        summary = (
            "The final written offer differs materially from the "
            "original assessed opportunity. Review and independently "
            "verify the changed terms before making any acceptance "
            "decision."
        )

    elif (
        offer_change_reviewed
        and offer_change_status_normalised
        == "review changes"
        and decision_code != "avoid"
    ):
        summary = (
            "The offer has positive aspects, but the final written "
            "terms changed from the original opportunity. Review "
            "those differences together with the remaining "
            "verification and academic signals before accepting."
        )

    # =====================================================
    # NEXT STEPS
    # =====================================================

    if decision_code == "avoid":
        next_steps.extend([
            (
                "Do not pay registration, onboarding, "
                "training or security fees."
            ),
            (
                "Verify the recruiter independently using "
                "the company's official contact channels."
            ),
            (
                "Request a written offer containing company "
                "details, role, stipend, schedule and terms."
            ),
        ])

    elif decision_code == "review":
        next_steps.extend([
            (
                "Verify all unresolved recruiter and company "
                "details independently."
            ),
            (
                "Compare the written offer with the original "
                "internship description."
            ),
            (
                "Confirm stipend, workload, duration, leave "
                "policy and academic compatibility."
            ),
        ])

    else:
        next_steps.extend([
            (
                "Read the written offer carefully before "
                "accepting."
            ),
            (
                "Confirm stipend, working hours, duration "
                "and responsibilities."
            ),
            (
                "Keep a copy of the final written offer and "
                "official communication."
            ),
        ])

    if (
        application.get("status") == "offer"
        and not offer_change_reviewed
    ):
        next_steps.insert(
            0,
            (
                "Run Final Offer Analysis in the Application Tracker "
                "before accepting the written offer."
            ),
        )

    if (
        offer_change_reviewed
        and offer_change_status_normalised
        in {
            "review changes",
            "major changes detected",
        }
    ):
        next_steps.insert(
            0,
            (
                "Compare every changed final-offer term against the "
                "original internship description and recruiter "
                "communication."
            ),
        )

    if critical_offer_changes:
        next_steps.insert(
            0,
            (
                "Do not accept the offer until all critical "
                "final-offer changes have been independently resolved."
            ),
        )

    strengths = list(dict.fromkeys(strengths))
    concerns = list(dict.fromkeys(concerns))
    next_steps = list(dict.fromkeys(next_steps))

    return {
        "decision_score": final_score,
        "decision_code": decision_code,
        "decision_label": decision_label,
        "decision_class": decision_class,
        "summary": summary,
        "strengths": strengths,
        "concerns": concerns,
        "next_steps": next_steps,
        "factors": factors,
        "application_status": application.get("status"),
        "verification_score": verification_score,
        "value_score": value_score,
        "compatibility_score": compatibility_score,
        "consistency_score": consistency_score,
        "offer_change_reviewed": offer_change_reviewed,
        "offer_change_score": offer_change_score,
        "offer_change_status": (
            offer_change_status
            or (
                "Not Reviewed"
                if application.get("status") == "offer"
                else None
            )
        ),
        "offer_change_critical_count": len(
            critical_offer_changes
        ),
        "offer_change_warning_count": len(
            offer_change_warnings
        ),
        "disclaimer": (
            "This is decision-support guidance based on the "
            "information available to InternShield. It does "
            "not prove that a company, recruiter, internship "
            "or offer is legitimate, and it should not replace "
            "independent verification of the written offer."
        ),
    }
