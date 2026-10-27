"""
Regulatory Trust Index (RTI) & Green / Amber / Red track router.

Implements the formula from SIH_AICTE_PROPOSAL_MASTER.md (Idea 4):

    RTI = 0.35 * S_doc_authenticity
        + 0.25 * S_consistency
        + 0.25 * S_faculty_integrity
        + 0.15 * S_infrastructure
        - P_penalties                      (clamped to 0..100)

Routing (proposal thresholds):
    GREEN : RTI >= 85 AND zero critical flags AND all verifications complete
    AMBER : otherwise, when RTI >= 60 and no fraud flag
    RED   : RTI < 60 OR any fraud / ghost-faculty / tamper / perjury flag

Every number that feeds the result is returned in the output so the
recommendation is explainable.  The output is ADVISORY ONLY - no adverse
action may be taken without human review.
"""
from typing import Any, Dict, List, Optional

WEIGHTS = {
    "doc_authenticity": 0.35,
    "consistency": 0.25,
    "faculty_integrity": 0.25,
    "infrastructure": 0.15,
}

GREEN_MIN_RTI = 85.0
RED_BELOW_RTI = 60.0

# Score contributed by a single document, by verification status.
DOC_STATUS_SCORES = {
    "VERIFIED": 100.0,
    "EXPIRED": 70.0,               # genuinely issued, but no longer valid
    "VERIFICATION_PENDING": 60.0,  # unknown yet
    "SOURCE_UNAVAILABLE": 60.0,    # unknown yet
    "MISMATCH_DETECTED": 30.0,
    "MANUAL_REVIEW_REQUIRED": 40.0,
}
TAMPERED_DOC_SCORE = 0.0

PENALTY_PER_CRITICAL_DEFICIENCY = 8.0
PENALTY_PER_RULE_WARNING = 3.0
PENALTY_PER_FRAUD_FLAG = 15.0
PENALTY_PER_MISMATCH = 10.0

CONSISTENCY_DEDUCTION_PERJURY = 40.0
CONSISTENCY_DEDUCTION_OTHER = 25.0
FACULTY_DEDUCTION_PER_COLLISION = 30.0

TRACK_ACTIONS = {
    "GREEN": "Fast-track Extension of Approval recommended, subject to officer confirmation.",
    "AMBER": "Route to Bureau Scrutiny Desk; issue structured deficiency notice with a 10-day rectification window.",
    "AMBER_INCOMPLETE": "Hold for verification: re-poll issuing authority or dispatch a manual verification note before deciding.",
    "RED": "Recommend surprise EVC physical inspection with evidence dossier. No adverse action without officer review and a hearing.",
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def config() -> Dict[str, Any]:
    """Expose the scoring configuration (for dashboards / documentation)."""
    return {
        "weights": dict(WEIGHTS),
        "green_min_rti": GREEN_MIN_RTI,
        "red_below_rti": RED_BELOW_RTI,
        "doc_status_scores": dict(DOC_STATUS_SCORES),
        "tampered_doc_score": TAMPERED_DOC_SCORE,
        "penalties": {
            "per_critical_deficiency": PENALTY_PER_CRITICAL_DEFICIENCY,
            "per_rule_warning": PENALTY_PER_RULE_WARNING,
            "per_fraud_flag": PENALTY_PER_FRAUD_FLAG,
            "per_mismatch": PENALTY_PER_MISMATCH,
        },
        "consistency_deductions": {
            "perjury": CONSISTENCY_DEDUCTION_PERJURY,
            "other": CONSISTENCY_DEDUCTION_OTHER,
        },
        "faculty_deduction_per_collision": FACULTY_DEDUCTION_PER_COLLISION,
    }


def compute_trust_index(rule_evaluation: Dict[str, Any],
                        documents: List[Dict[str, Any]],
                        collisions: Optional[List[Dict[str, Any]]] = None,
                        contradictions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    rule_evaluation : output of APHRuleEngine.evaluate_application
    documents       : [{"doc_id", "label", "status", "tampered": bool}, ...]
    collisions      : output of FacultyIntegrityGraph.check_institution_collisions
    contradictions  : output of AffidavitTriangulator.triangulate
    """
    collisions = collisions or []
    contradictions = contradictions or []

    fraud_flags: List[str] = []
    critical_flags: List[str] = []
    incomplete_flags: List[str] = []
    penalties: List[Dict[str, Any]] = []

    # --- S_doc_authenticity -------------------------------------------------
    doc_scores = []
    mismatch_count = 0
    for d in documents:
        status = str(d.get("status"))
        label = d.get("label") or d.get("doc_id", "document")
        if d.get("tampered"):
            doc_scores.append(TAMPERED_DOC_SCORE)
            fraud_flags.append(f"Forensic tamper signal on {label}")
            continue
        doc_scores.append(DOC_STATUS_SCORES.get(status, 0.0))
        if status == "MISMATCH_DETECTED":
            mismatch_count += 1
            critical_flags.append(f"{label}: mismatch against issuing authority record")
        elif status == "EXPIRED":
            critical_flags.append(f"{label}: expired at source")
        elif status == "MANUAL_REVIEW_REQUIRED":
            critical_flags.append(f"{label}: requires manual review")
        elif status in ("VERIFICATION_PENDING", "SOURCE_UNAVAILABLE"):
            incomplete_flags.append(f"{label}: {status.replace('_', ' ').lower()}")
    if doc_scores:
        s_doc = sum(doc_scores) / len(doc_scores)
    else:
        s_doc = 0.0
        critical_flags.append("No documents submitted for authority verification")

    # --- S_consistency (affidavit vs evidence) ------------------------------
    s_cons = 100.0
    for c in contradictions:
        sev = str(c.get("severity", ""))
        if "PERJURY" in sev:
            s_cons -= CONSISTENCY_DEDUCTION_PERJURY
            fraud_flags.append(f"Affidavit perjury indicator: {c.get('field')}")
        else:
            s_cons -= CONSISTENCY_DEDUCTION_OTHER
            critical_flags.append(f"Affidavit contradiction: {c.get('field')}")
    s_cons = _clamp(s_cons)

    # --- S_faculty_integrity ------------------------------------------------
    s_fac = _clamp(100.0 - FACULTY_DEDUCTION_PER_COLLISION * len(collisions))
    for col in collisions:
        fraud_flags.append(
            f"Ghost faculty: {col.get('name_initials')} concurrently active at "
            f"{col.get('total_concurrent_institutions', 2) - 1} other institution(s)")

    # --- S_infrastructure (APH rule compliance) -----------------------------
    s_infra = float(rule_evaluation.get("compliance_score", 0))
    for f in rule_evaluation.get("findings", []):
        if f.get("severity") == "CRITICAL":
            critical_flags.append(f"APH deficiency ({f.get('clause')}): {f.get('message')}")

    # --- Penalties ----------------------------------------------------------
    n_crit = int(rule_evaluation.get("critical_deficiencies_count", 0))
    n_warn = int(rule_evaluation.get("warnings_count", 0))
    if n_crit:
        penalties.append({"reason": f"{n_crit} critical APH deficiency(ies)",
                          "points": n_crit * PENALTY_PER_CRITICAL_DEFICIENCY})
    if n_warn:
        penalties.append({"reason": f"{n_warn} APH warning(s)",
                          "points": n_warn * PENALTY_PER_RULE_WARNING})
    if mismatch_count:
        penalties.append({"reason": f"{mismatch_count} authority mismatch(es)",
                          "points": mismatch_count * PENALTY_PER_MISMATCH})
    if fraud_flags:
        penalties.append({"reason": f"{len(fraud_flags)} fraud / integrity flag(s)",
                          "points": len(fraud_flags) * PENALTY_PER_FRAUD_FLAG})
    total_penalty = sum(p["points"] for p in penalties)

    components = {}
    raw = 0.0
    for key, score in (("doc_authenticity", s_doc), ("consistency", s_cons),
                       ("faculty_integrity", s_fac), ("infrastructure", s_infra)):
        weighted = WEIGHTS[key] * score
        raw += weighted
        components[key] = {"score": round(score, 1), "weight": WEIGHTS[key],
                           "weighted": round(weighted, 2)}

    rti = round(_clamp(raw - total_penalty), 1)

    # --- Routing ------------------------------------------------------------
    reasons: List[str] = []
    if fraud_flags or rti < RED_BELOW_RTI:
        track = "RED"
        action = TRACK_ACTIONS["RED"]
        if fraud_flags:
            reasons.append(f"{len(fraud_flags)} fraud / integrity flag(s) force RED irrespective of score")
        if rti < RED_BELOW_RTI:
            reasons.append(f"RTI {rti} is below the RED threshold of {RED_BELOW_RTI:g}")
    elif rti >= GREEN_MIN_RTI and not critical_flags and not incomplete_flags:
        track = "GREEN"
        action = TRACK_ACTIONS["GREEN"]
        reasons.append(f"RTI {rti} >= {GREEN_MIN_RTI:g} with zero critical flags and all verifications complete")
    else:
        track = "AMBER"
        if critical_flags:
            action = TRACK_ACTIONS["AMBER"]
            reasons.append(f"{len(critical_flags)} curable critical flag(s) block the GREEN track")
        else:
            action = TRACK_ACTIONS["AMBER_INCOMPLETE"]
        if incomplete_flags:
            reasons.append(f"{len(incomplete_flags)} verification(s) not yet complete")
        if rti < GREEN_MIN_RTI:
            reasons.append(f"RTI {rti} is below the GREEN threshold of {GREEN_MIN_RTI:g}")

    return {
        "rti": rti,
        "track": track,
        "recommended_action": action,
        "advisory_only": True,
        "components": components,
        "raw_weighted_score": round(raw, 2),
        "penalties": penalties,
        "total_penalty": total_penalty,
        "fraud_flags": fraud_flags,
        "critical_flags": critical_flags,
        "incomplete_flags": incomplete_flags,
        "reasons": reasons,
    }
