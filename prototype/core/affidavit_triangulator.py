"""
Affidavit vs Ground Evidence Triangulation Engine
Extracts sworn legal statements made in AICTE Affidavit-2 (sworn before a Magistrate/Notary)
and cross-examines them against attached municipal certificates and state revenue records.
"""
from typing import Dict, Any, List

class AffidavitTriangulator:
    def triangulate(self, affidavit_claims: Dict[str, Any], attached_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Cross-checks sworn declarations against physical supporting attachments.
        """
        contradictions = []

        # Check 1: Sworn Occupancy Certificate Type vs. Attached Certificate Type
        sworn_oc_nature = affidavit_claims.get("sworn_occupancy_type", "").upper()
        attached_oc_nature = attached_evidence.get("attached_occupancy_type", "").upper()

        if "PERMANENT" in sworn_oc_nature and "PROVISIONAL" in attached_oc_nature:
            contradictions.append({
                "field": "OCCUPANCY_CERTIFICATE_PERMANENCY",
                "severity": "CRITICAL_PERJURY_FLAG",
                "sworn_statement": f"Chairman swore in Affidavit-2: 'The institution has obtained Permanent Occupancy Certificate'",
                "evidence_reality": f"Attached Document from Municipal Authority is strictly 'Provisional / Temporary OC' valid for 1 year.",
                "legal_implication": "False declaration on oath under Section 199/200 IPC / Bharatiya Nyaya Sanhita."
            })

        # Check 2: Sworn Land Survey Numbers vs Attached Land Sale Deed
        sworn_survey_no = str(affidavit_claims.get("sworn_survey_number", "")).strip()
        attached_survey_no = str(attached_evidence.get("attached_survey_number", "")).strip()

        if sworn_survey_no and attached_survey_no and sworn_survey_no != attached_survey_no:
            contradictions.append({
                "field": "LAND_SURVEY_NUMBER_MISMATCH",
                "severity": "HIGH_DISCREPANCY",
                "sworn_statement": f"Affidavit declares land title on Survey No: {sworn_survey_no}",
                "evidence_reality": f"Attached Registered Sale Deed specifies Survey No: {attached_survey_no}",
                "legal_implication": "Campus premises title is unverified or operates on unregistered land parcel."
            })

        # Check 3: Sworn Built-Up Area vs Attached Approved Floor Plan
        sworn_area = affidavit_claims.get("sworn_built_up_area_sqm", 0)
        attached_area = attached_evidence.get("attached_floor_plan_area_sqm", 0)

        if sworn_area > 0 and attached_area > 0:
            discrepancy_pct = abs(sworn_area - attached_area) / max(1, sworn_area) * 100
            if discrepancy_pct > 10.0:
                contradictions.append({
                    "field": "BUILT_UP_AREA_INFLATION",
                    "severity": "CRITICAL_DEFICIENCY",
                    "sworn_statement": f"Sworn total built-up area: {sworn_area:,.2f} sq.m.",
                    "evidence_reality": f"Architect / Municipal approved floor plan certifies only: {attached_area:,.2f} sq.m.",
                    "inflation_percentage": f"{discrepancy_pct:.1f}% inflation",
                    "legal_implication": "Failure to satisfy minimum instructional carpet area per APH norms."
                })

        return contradictions
