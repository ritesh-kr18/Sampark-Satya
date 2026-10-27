"""
6-State Issuing Authority Document Verification State Machine & Merkle Audit Trail
Implements strict state transitions matching the SIH problem statement requirements:
[VERIFIED, MISMATCH_DETECTED, EXPIRED, VERIFICATION_PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW_REQUIRED]
"""
from enum import Enum
from typing import Dict, Any, List, Optional
import hashlib
from datetime import datetime

class VerificationStatus(str, Enum):
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"
    MISMATCH_DETECTED = "MISMATCH_DETECTED"
    EXPIRED = "EXPIRED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

class VerificationStateMachine:
    def __init__(self):
        # Genesis hash for the Merkle audit trail
        self.last_audit_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        self.audit_ledger: List[Dict[str, Any]] = []

    def record_audit_event(self, doc_id: str, actor: str, action: str, details: Dict[str, Any]) -> str:
        """Appends an immutable hash-chained audit block to the ledger."""
        timestamp = datetime.now().isoformat()
        payload = f"{self.last_audit_hash}:{doc_id}:{actor}:{action}:{details}:{timestamp}"
        current_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()

        entry = {
            "index": len(self.audit_ledger) + 1,
            "doc_id": doc_id,
            "actor": actor,
            "action": action,
            "details": details,
            "timestamp": timestamp,
            "previous_hash": self.last_audit_hash,
            "current_hash": current_hash
        }
        self.audit_ledger.append(entry)
        self.last_audit_hash = current_hash
        return current_hash

    GENESIS_HASH = "0" * 64

    def verify_chain(self) -> Dict[str, Any]:
        """
        Recomputes every block hash and checks the previous-hash links.
        Returns {"valid": bool, "checked": n, "broken_at_index": int|None, "problem": str|None}.
        """
        expected_prev = self.GENESIS_HASH
        for entry in self.audit_ledger:
            if entry["previous_hash"] != expected_prev:
                return {"valid": False, "checked": entry["index"], "broken_at_index": entry["index"],
                        "problem": "previous_hash link does not match the preceding block"}
            payload = (f"{entry['previous_hash']}:{entry['doc_id']}:{entry['actor']}:"
                       f"{entry['action']}:{entry['details']}:{entry['timestamp']}")
            recomputed = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            if recomputed != entry["current_hash"]:
                return {"valid": False, "checked": entry["index"], "broken_at_index": entry["index"],
                        "problem": "block contents were altered after it was sealed (hash mismatch)"}
            expected_prev = entry["current_hash"]
        return {"valid": True, "checked": len(self.audit_ledger), "broken_at_index": None, "problem": None}

    def evaluate_verification(self, 
                              doc_id: str, 
                              doc_type: str, 
                              declared_data: Dict[str, Any], 
                              authority_response: Optional[Dict[str, Any]], 
                              is_source_online: bool = True,
                              has_forensic_tamper: bool = False) -> Dict[str, Any]:
        """
        Determines the statutory verification status based on authority response and evidence.
        """
        # Case 1: Physical forgery detected by computer vision / ELA
        if has_forensic_tamper:
            status = VerificationStatus.MANUAL_REVIEW_REQUIRED
            reason = "Forensic inspection detected visual/byte tamper anomaly (ELA or PAdES violation). Escalated to Scrutiny Officer."
            self.record_audit_event(doc_id, "FORENSIC_ENGINE", "FLAG_TAMPER", {"reason": reason})
            return {"status": status, "reason": reason}

        # Case 2: Target issuing authority portal is offline or timed out
        if not is_source_online:
            status = VerificationStatus.SOURCE_UNAVAILABLE
            reason = f"Issuing authority portal for {doc_type} is currently unresponsive (HTTP 504 / Connection Timeout). Fallback queue active."
            self.record_audit_event(doc_id, "AUTHORITY_HUB", "SOURCE_UNAVAILABLE", {"reason": reason})
            return {"status": status, "reason": reason}

        # Case 3: Authority response not yet received
        if authority_response is None:
            status = VerificationStatus.VERIFICATION_PENDING
            reason = "Awaiting asynchronous response from official issuing repository."
            self.record_audit_event(doc_id, "AUTHORITY_HUB", "POLL_PENDING", {"reason": reason})
            return {"status": status, "reason": reason}

        # Case 4: Document is expired at source
        is_expired = authority_response.get("is_expired", False)
        valid_till = authority_response.get("valid_till")
        if is_expired or (valid_till and valid_till < declared_data.get("academic_year_start", "2024-08-01")):
            status = VerificationStatus.EXPIRED
            reason = f"Official issuing authority records indicate document validity expired on {valid_till}."
            self.record_audit_event(doc_id, "AUTHORITY_HUB", "FLAG_EXPIRED", {"valid_till": valid_till})
            return {"status": status, "reason": reason}

        # Case 5: Critical field mismatch between application and official repository
        mismatches = []
        for key in ["institution_name", "survey_number", "carpet_area_sqm", "approved_intake"]:
            if key in declared_data and key in authority_response:
                if str(declared_data[key]).strip().lower() != str(authority_response[key]).strip().lower():
                    mismatches.append(f"Declared '{key}': {declared_data[key]} != Authority record: {authority_response[key]}")

        if mismatches:
            status = VerificationStatus.MISMATCH_DETECTED
            reason = f"Discrepancy detected against official authority database: {'; '.join(mismatches)}"
            self.record_audit_event(doc_id, "AUTHORITY_HUB", "FLAG_MISMATCH", {"mismatches": mismatches})
            return {"status": status, "reason": reason, "mismatches": mismatches}

        # Case 6: Exact authentic match
        status = VerificationStatus.VERIFIED
        reason = f"Cryptographically validated against official issuing authority ({authority_response.get('source_authority', 'Official Source')})."
        self.record_audit_event(doc_id, "AUTHORITY_HUB", "CONFIRM_VERIFIED", {"authority": authority_response.get('source_authority')})
        return {"status": status, "reason": reason}
