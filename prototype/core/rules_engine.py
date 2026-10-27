"""
AICTE Approval Process Handbook (APH) Configurable Rule Engine
Evaluates applications against versioned regulatory formulas and checklists.
"""
from typing import Dict, Any, List
import math
from datetime import datetime

class APHRuleEngine:
    def __init__(self, aph_version: str = "2024-2027"):
        self.aph_version = aph_version
        self.rules = self._load_default_aph_rules()

    def _load_default_aph_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "rule_id": "APH_ANNEX_5_FSR_UG_ENGG",
                "category": "FACULTY_NORMS",
                "description": "UG Engineering Faculty-to-Student Ratio must be at least 1:20",
                "aph_clause": "Annexure-5, Table 5.1",
                "severity": "CRITICAL"
            },
            {
                "rule_id": "APH_CLAUSE_7_3_PROVISIONAL_OC",
                "category": "INFRASTRUCTURE_NORMS",
                "description": "Provisional Occupancy Certificate allowed for maximum 2 consecutive years",
                "aph_clause": "Chapter 1, Clause 7.3",
                "severity": "CRITICAL"
            },
            {
                "rule_id": "APH_CLAUSE_7_4_FIRE_NOC",
                "category": "SAFETY_NORMS",
                "description": "Fire Safety Certificate must be valid for the upcoming academic year",
                "aph_clause": "Chapter 1, Clause 7.4",
                "severity": "CRITICAL"
            },
            {
                "rule_id": "APH_LAND_REQUIREMENT_URBAN",
                "category": "LAND_NORMS",
                "description": "Minimum land for Engineering in Urban area is 2.5 Acres (or 1.5 in Metro)",
                "aph_clause": "Annexure-4, Table 4.1",
                "severity": "HIGH"
            }
        ]

    def evaluate_application(self, application_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates an application dossier against the active APH rules.
        """
        findings = []
        critical_deficiencies = 0
        warnings = 0

        # 1. FSR Evaluation
        program = application_data.get("program", "ENGINEERING_UG")
        total_intake = application_data.get("total_approved_intake", 0)
        verified_faculty = application_data.get("verified_faculty_count", 0)

        if program == "ENGINEERING_UG" and total_intake > 0:
            required_faculty = math.ceil(total_intake / 20.0)
            actual_fsr = round(total_intake / max(1, verified_faculty), 2)
            
            if verified_faculty < required_faculty:
                critical_deficiencies += 1
                findings.append({
                    "rule_id": "APH_ANNEX_5_FSR_UG_ENGG",
                    "status": "NON_COMPLIANT",
                    "severity": "CRITICAL",
                    "clause": "APH 2024-27, Annexure-5",
                    "message": f"Faculty-to-Student Ratio deficit: Current ratio is 1:{actual_fsr}. "
                               f"Total approved intake of {total_intake} requires at least {required_faculty} faculty (1:20 norm). "
                               f"Current verified faculty: {verified_faculty} (Deficit: {required_faculty - verified_faculty})."
                })
            else:
                findings.append({
                    "rule_id": "APH_ANNEX_5_FSR_UG_ENGG",
                    "status": "COMPLIANT",
                    "severity": "INFO",
                    "clause": "APH 2024-27, Annexure-5",
                    "message": f"FSR compliant: 1:{actual_fsr} (Norm is 1:20). Verified faculty: {verified_faculty}."
                })

        # 2. Provisional Occupancy Certificate 2-Year Limitation
        oc_type = application_data.get("occupancy_certificate_type", "PERMANENT")
        consecutive_provisional_years = application_data.get("consecutive_provisional_oc_years", 0)

        if oc_type == "PROVISIONAL":
            if consecutive_provisional_years >= 2:
                critical_deficiencies += 1
                findings.append({
                    "rule_id": "APH_CLAUSE_7_3_PROVISIONAL_OC",
                    "status": "NON_COMPLIANT",
                    "severity": "CRITICAL",
                    "clause": "APH 2024-27, Chapter 1, Clause 7.3",
                    "message": f"Provisional Occupancy Certificate has already been utilized for {consecutive_provisional_years} consecutive years. "
                               f"Per APH Clause 7.3, a Permanent Completion / Occupancy Certificate is now mandatory for EoA."
                })
            else:
                warnings += 1
                findings.append({
                    "rule_id": "APH_CLAUSE_7_3_PROVISIONAL_OC",
                    "status": "WARNING",
                    "severity": "WARNING",
                    "clause": "APH 2024-27, Chapter 1, Clause 7.3",
                    "message": f"Provisional OC in use for Year {consecutive_provisional_years + 1} of 2 permitted. Must transition to Permanent OC next year."
                })

        # 3. Fire NOC Expiry Check
        fire_noc_expiry_str = application_data.get("fire_noc_valid_till")
        academic_year_start_str = application_data.get("academic_year_start", "2024-08-01")

        if fire_noc_expiry_str:
            try:
                fire_expiry = datetime.strptime(fire_noc_expiry_str, "%Y-%m-%d")
                ay_start = datetime.strptime(academic_year_start_str, "%Y-%m-%d")

                if fire_expiry < ay_start:
                    critical_deficiencies += 1
                    findings.append({
                        "rule_id": "APH_CLAUSE_7_4_FIRE_NOC",
                        "status": "NON_COMPLIANT",
                        "severity": "CRITICAL",
                        "clause": "APH 2024-27, Chapter 1, Clause 7.4",
                        "message": f"Fire Safety Certificate expired on {fire_noc_expiry_str}. "
                                   f"Must be valid on/after academic session start ({academic_year_start_str})."
                    })
                else:
                    findings.append({
                        "rule_id": "APH_CLAUSE_7_4_FIRE_NOC",
                        "status": "COMPLIANT",
                        "severity": "INFO",
                        "clause": "APH 2024-27, Chapter 1, Clause 7.4",
                        "message": f"Fire Safety Certificate is valid until {fire_noc_expiry_str}."
                    })
            except ValueError:
                pass

        # 4. Land Requirement Verification
        location_type = application_data.get("location_type", "URBAN")
        declared_land_acres = application_data.get("declared_land_acres", 0.0)
        min_required_acres = 2.5 if location_type == "URBAN" else (1.5 if location_type == "METRO" else 4.0)

        if declared_land_acres < min_required_acres:
            critical_deficiencies += 1
            findings.append({
                "rule_id": "APH_LAND_REQUIREMENT",
                "status": "NON_COMPLIANT",
                "severity": "CRITICAL",
                "clause": "APH 2024-27, Annexure-4",
                "message": f"Land deficit: Declared {declared_land_acres} acres in {location_type} zone. "
                           f"Minimum required is {min_required_acres} contiguous acres."
            })

        # Calculate compliance score
        compliance_score = max(0, 100 - (critical_deficiencies * 30) - (warnings * 10))

        return {
            "evaluation_timestamp": datetime.now().isoformat(),
            "aph_version": self.aph_version,
            "compliance_score": compliance_score,
            "critical_deficiencies_count": critical_deficiencies,
            "warnings_count": warnings,
            "findings": findings
        }
