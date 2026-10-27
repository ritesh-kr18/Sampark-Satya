"""
National Faculty Integrity Graph (FIG) & Ghost Faculty Radar
Detects concurrent dual/multiple employment across technical institutions
using privacy-preserving salted PAN hashes and temporal employment records.
"""
from typing import Dict, Any, List, Set
import hashlib
from datetime import datetime

class FacultyIntegrityGraph:
    def __init__(self, salt: str = "AICTE_REGULATION_BUREAU_2024"):
        self.salt = salt
        # Map: hashed_pan -> list of employment records
        self.faculty_deployments: Dict[str, List[Dict[str, Any]]] = {}

    def hash_identity(self, raw_pan: str, aicte_faculty_id: str) -> str:
        """Cryptographically anonymizes PAN + Faculty ID in compliance with DPDP 2023."""
        clean_pan = raw_pan.strip().upper()
        clean_fid = aicte_faculty_id.strip().upper()
        return hashlib.sha256(f"{clean_pan}:{clean_fid}:{self.salt}".encode('utf-8')).hexdigest()

    def register_faculty(self, 
                         institution_id: str, 
                         institution_name: str, 
                         faculty_name_initials: str, 
                         raw_pan: str, 
                         aicte_faculty_id: str, 
                         designation: str, 
                         start_date: str, 
                         end_date: str = None) -> str:
        """
        Registers an employment link between a faculty token and an institution.
        """
        token = self.hash_identity(raw_pan, aicte_faculty_id)
        if token not in self.faculty_deployments:
            self.faculty_deployments[token] = []

        self.faculty_deployments[token].append({
            "institution_id": institution_id,
            "institution_name": institution_name,
            "name_masked": faculty_name_initials,
            "designation": designation,
            "start_date": start_date,
            "end_date": end_date,  # None means active
            "aicte_faculty_id_masked": f"{aicte_faculty_id[:3]}***{aicte_faculty_id[-2:]}"
        })
        return token

    def check_institution_collisions(self, institution_id: str) -> List[Dict[str, Any]]:
        """
        Scans all faculty registered under the given institution and detects
        overlapping active full-time appointments in other technical colleges.
        """
        collisions = []

        for token, deployments in self.faculty_deployments.items():
            # Check if this faculty is claimed by the target institution
            inst_deployments = [d for d in deployments if d["institution_id"] == institution_id and d["end_date"] is None]
            if not inst_deployments:
                continue

            # Check if simultaneously active in ANY OTHER institution
            other_active_deployments = [d for d in deployments if d["institution_id"] != institution_id and d["end_date"] is None]
            
            if other_active_deployments:
                conflicting_institutions = [
                    f"{d['institution_name']} (ID: {d['institution_id']})" for d in other_active_deployments
                ]
                collisions.append({
                    "faculty_token": token[:12] + "...",
                    "name_initials": inst_deployments[0]["name_masked"],
                    "faculty_id": inst_deployments[0]["aicte_faculty_id_masked"],
                    "designation": inst_deployments[0]["designation"],
                    "conflict_type": "CONCURRENT_DUAL_EMPLOYMENT",
                    "severity": "CRITICAL_FRAUD_ALERT",
                    "conflicting_colleges": conflicting_institutions,
                    "total_concurrent_institutions": len(conflicting_institutions) + 1,
                    "statutory_implication": "Breaches AICTE Faculty Code of Conduct; Void for FSR calculation."
                })

        return collisions

    def get_network_stats(self) -> Dict[str, Any]:
        """Returns national health metrics for the faculty graph."""
        total_faculty_tokens = len(self.faculty_deployments)
        flagged_tokens = 0
        multi_college_rosters = 0

        for token, deployments in self.faculty_deployments.items():
            active_count = len([d for d in deployments if d["end_date"] is None])
            if active_count > 1:
                flagged_tokens += 1
                multi_college_rosters += active_count

        return {
            "total_registered_faculty_tokens": total_faculty_tokens,
            "flagged_ghost_faculty_count": flagged_tokens,
            "phantom_positions_uncovered": multi_college_rosters,
            "overall_integrity_rate": round(100.0 - (flagged_tokens / max(1, total_faculty_tokens) * 100), 2)
        }
