"""
SAMPARK-SATYA dashboard service layer.

Loads the (synthetic) application dataset, runs every application through the
REAL prototype engines in prototype/core, and keeps the results plus the
hash-chained audit ledger in memory.  The HTTP server (server.py) is a thin
JSON wrapper around this class, and the unit tests drive it directly.
"""
import copy
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.rules_engine import APHRuleEngine
from core.faculty_graph import FacultyIntegrityGraph
from core.verification_state_machine import VerificationStateMachine, VerificationStatus
from core.affidavit_triangulator import AffidavitTriangulator
from core.forensic_analyzer import ForensicAnalyzer
from core import trust_index

VERIFICATION_STATES = [s.value for s in VerificationStatus]

ROLES: Dict[str, Dict[str, Any]] = {
    "SCRUTINY_OFFICER": {
        "label": "Scrutiny Officer",
        "label_hi": "संवीक्षा अधिकारी",
        "can_view_applications": True,
        "decisions": ["FORWARD_WITH_CONCURRENCE", "FORWARD_WITH_DISSENT", "REQUEST_CLARIFICATION"],
    },
    "APPROVING_AUTHORITY": {
        "label": "Approving Authority (Approval Bureau)",
        "label_hi": "अनुमोदन प्राधिकारी",
        "can_view_applications": True,
        "decisions": ["APPROVE_EOA", "ISSUE_DEFICIENCY_NOTICE", "ORDER_EVC_INSPECTION",
                      "ISSUE_SHOW_CAUSE", "REQUEST_CLARIFICATION"],
    },
    "AUDITOR": {
        "label": "Auditor (read-only)",
        "label_hi": "लेखा परीक्षक (केवल पढ़ें)",
        "can_view_applications": True,
        "decisions": [],
    },
    "INSTITUTION": {
        "label": "Institution (College Admin)",
        "label_hi": "संस्थान (कॉलेज व्यवस्थापक)",
        "can_view_applications": False,
        "decisions": [],
    },
}
DEFAULT_ROLE = "SCRUTINY_OFFICER"

DECISIONS: Dict[str, Dict[str, Any]] = {
    "FORWARD_WITH_CONCURRENCE": {"label": "Forward to Approving Authority - concur with AI recommendation", "adverse": False},
    "FORWARD_WITH_DISSENT": {"label": "Forward to Approving Authority - dissent from AI recommendation", "adverse": False},
    "REQUEST_CLARIFICATION": {"label": "Seek clarification from institution", "adverse": False},
    "APPROVE_EOA": {"label": "Grant Extension of Approval", "adverse": False},
    "ISSUE_DEFICIENCY_NOTICE": {"label": "Issue deficiency notice (10-day rectification)", "adverse": True},
    "ORDER_EVC_INSPECTION": {"label": "Order Expert Visit Committee (EVC) inspection", "adverse": True},
    "ISSUE_SHOW_CAUSE": {"label": "Issue show-cause notice (hearing mandatory)", "adverse": True},
}
MIN_REMARKS = 20
MIN_REMARKS_ADVERSE = 40

FIX_GUIDANCE = {
    "APH_ANNEX_5_FSR_UG_ENGG": "Recruit and register the deficit faculty on the AICTE faculty portal (PAN + Aadhaar-verified) before submission.",
    "APH_CLAUSE_7_3_PROVISIONAL_OC": "Obtain the Permanent Occupancy / Completion Certificate from the local municipal authority.",
    "APH_CLAUSE_7_4_FIRE_NOC": "Renew the Fire Safety NOC so it is valid on/after the academic session start date.",
    "APH_LAND_REQUIREMENT": "Land below the APH minimum - acquire contiguous land or re-check the location category.",
}

LOCATION_TYPES = ("URBAN", "METRO", "RURAL")
OC_TYPES = ("PERMANENT", "PROVISIONAL")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ServiceError(Exception):
    def __init__(self, status: int, message: str, details: Optional[List[str]] = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or []


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DashboardService:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.lock = threading.RLock()
        self.reset()

    # ------------------------------------------------------------------ setup
    def _load_json(self, name: str) -> Dict[str, Any]:
        with open(os.path.join(self.data_dir, name), "r", encoding="utf-8") as fh:
            return json.load(fh)

    def reset(self) -> None:
        with self.lock:
            dataset = self._load_json("applications.json")
            registry = self._load_json("faculty_registry.json")
            self.academic_year_start = dataset.get("academic_year_start", "2024-08-01")
            self.raw_apps: List[Dict[str, Any]] = dataset["applications"]
            self.rule_engine = APHRuleEngine(aph_version="2024-2027")
            self.fig = FacultyIntegrityGraph()
            self.state_machine = VerificationStateMachine()
            self.triangulator = AffidavitTriangulator()
            self.forensics = ForensicAnalyzer()
            self.institution_names = {a["institution_id"]: a["institution_name"] for a in self.raw_apps}

            cols = registry["columns"]
            for row in registry["registrations"]:
                rec = dict(zip(cols, row))
                self.fig.register_faculty(
                    institution_id=rec["institution_id"],
                    institution_name=self.institution_names.get(rec["institution_id"], rec["institution_id"]),
                    faculty_name_initials=rec["name_initials"],
                    raw_pan=rec["pan"],
                    aicte_faculty_id=rec["aicte_faculty_id"],
                    designation=rec["designation"],
                    start_date=rec["start_date"],
                )

            self.results: Dict[str, Dict[str, Any]] = {}
            self.order: List[str] = []
            started = time.perf_counter()
            for raw in self.raw_apps:
                res = self._evaluate(raw)
                self.results[raw["id"]] = res
                self.order.append(raw["id"])
            self.total_eval_ms = round((time.perf_counter() - started) * 1000, 2)
            self.evaluated_at = _now()

    # ------------------------------------------------------------- evaluation
    def _analyze_forensics(self, spec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not spec:
            return None
        pades = self.forensics.inspect_pdf_pades_signature(
            has_digital_signature=bool(spec.get("has_digital_signature")),
            has_incremental_modification_after_sign=bool(spec.get("modified_after_sign")))
        ela = self.forensics.simulate_ela_analysis(
            is_digitally_altered=bool(spec.get("ela_altered")),
            altered_region=spec.get("altered_region", ""))
        tampered = bool(pades.get("post_sign_tamper_detected")) or bool(ela.get("ela_anomaly_detected"))
        return {"pades": pades, "ela": ela, "tampered": tampered, "simulated": True}

    def _evaluate(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        app_id = raw["id"]
        inst_id = raw["institution_id"]

        # 1. Faculty Integrity Graph - ghost faculty are voided for FSR.
        collisions = self.fig.check_institution_collisions(inst_id)
        app_input = dict(raw["application"])
        app_input.setdefault("academic_year_start", self.academic_year_start)
        declared_faculty = int(app_input.get("verified_faculty_count", 0))
        effective_faculty = max(0, declared_faculty - len(collisions))
        app_input["verified_faculty_count"] = effective_faculty

        # 2. APH rules
        rule_eval = self.rule_engine.evaluate_application(app_input)

        # 3. Documents: forensics -> 6-state authority verification
        documents = []
        for d in raw.get("documents", []):
            forensic = self._analyze_forensics(d.get("forensics"))
            declared = {"institution_name": raw["institution_name"],
                        "academic_year_start": self.academic_year_start}
            declared.update(d.get("declared_extra", {}))
            verdict = self.state_machine.evaluate_verification(
                doc_id=d["doc_id"],
                doc_type=d["doc_type"],
                declared_data=declared,
                authority_response=copy.deepcopy(d.get("authority_response")),
                is_source_online=d.get("source_online", True),
                has_forensic_tamper=bool(forensic and forensic["tampered"]),
            )
            status = verdict["status"]
            status = status.value if isinstance(status, VerificationStatus) else str(status)
            authority = (d.get("authority_response") or {}).get("source_authority")
            documents.append({
                "doc_id": d["doc_id"],
                "doc_type": d["doc_type"],
                "label": d.get("label", d["doc_type"]),
                "status": status,
                "reason": verdict["reason"],
                "mismatches": verdict.get("mismatches", []),
                "authority": authority,
                "forensics": forensic,
                "tampered": bool(forensic and forensic["tampered"]),
            })

        # 4. Affidavit triangulation
        contradictions: List[Dict[str, Any]] = []
        if raw.get("affidavit"):
            contradictions = self.triangulator.triangulate(raw["affidavit"]["claims"],
                                                           raw["affidavit"]["evidence"])

        # 5. Regulatory Trust Index + advisory track
        rti = trust_index.compute_trust_index(rule_eval, documents, collisions, contradictions)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        self.state_machine.record_audit_event(app_id, "RULE_ENGINE", "APH_EVALUATION", {
            "compliance_score": rule_eval["compliance_score"],
            "critical": rule_eval["critical_deficiencies_count"],
            "aph_version": rule_eval["aph_version"]})
        self.state_machine.record_audit_event(app_id, "RTI_ENGINE", "ADVISORY_RECOMMENDATION", {
            "rti": rti["rti"], "track": rti["track"], "advisory_only": True})

        return {
            "id": app_id,
            "institution_id": inst_id,
            "institution_name": raw["institution_name"],
            "city": raw.get("city"),
            "state": raw.get("state"),
            "region": raw.get("region"),
            "application_type": raw.get("application_type"),
            "submitted_on": raw.get("submitted_on"),
            "application": raw["application"],
            "declared_faculty": declared_faculty,
            "effective_faculty": effective_faculty,
            "rule_evaluation": rule_eval,
            "documents": documents,
            "collisions": collisions,
            "affidavit": raw.get("affidavit"),
            "contradictions": contradictions,
            "trust": rti,
            "evaluation_ms": elapsed_ms,
            "reviews": [],
            "workflow_status": "PENDING_SCRUTINY",
        }

    # ------------------------------------------------------------------ roles
    @staticmethod
    def normalize_role(role: Optional[str]) -> str:
        role = (role or DEFAULT_ROLE).strip().upper()
        if role not in ROLES:
            raise ServiceError(400, f"Unknown role '{role}'")
        return role

    @staticmethod
    def require_view(role: str) -> None:
        if not ROLES[role]["can_view_applications"]:
            raise ServiceError(403, "This role cannot view the regulatory scrutiny queue.")

    # ---------------------------------------------------------------- queries
    def meta(self) -> Dict[str, Any]:
        return {
            "roles": ROLES,
            "decisions": DECISIONS,
            "verification_states": VERIFICATION_STATES,
            "trust_config": trust_index.config(),
            "academic_year_start": self.academic_year_start,
            "min_remarks": MIN_REMARKS,
            "min_remarks_adverse": MIN_REMARKS_ADVERSE,
            "data_notice": "Synthetic demo data. Forensic signals (ELA / PAdES) are simulated in this prototype.",
        }

    def _row(self, r: Dict[str, Any]) -> Dict[str, Any]:
        counts = {s: 0 for s in VERIFICATION_STATES}
        for d in r["documents"]:
            counts[d["status"]] = counts.get(d["status"], 0) + 1
        return {
            "id": r["id"],
            "institution_id": r["institution_id"],
            "institution_name": r["institution_name"],
            "city": r["city"],
            "state": r["state"],
            "application_type": r["application_type"],
            "submitted_on": r["submitted_on"],
            "rti": r["trust"]["rti"],
            "track": r["trust"]["track"],
            "compliance_score": r["rule_evaluation"]["compliance_score"],
            "critical_deficiencies": r["rule_evaluation"]["critical_deficiencies_count"],
            "fraud_flags": len(r["trust"]["fraud_flags"]),
            "ghost_faculty": len(r["collisions"]),
            "doc_status_counts": counts,
            "workflow_status": r["workflow_status"],
            "evaluation_ms": r["evaluation_ms"],
        }

    def list_applications(self) -> List[Dict[str, Any]]:
        with self.lock:
            rows = [self._row(self.results[i]) for i in self.order]
        return sorted(rows, key=lambda x: x["rti"])

    def get_application(self, app_id: str) -> Dict[str, Any]:
        with self.lock:
            r = self.results.get(app_id)
            if r is None:
                raise ServiceError(404, f"Application '{app_id}' not found")
            out = copy.deepcopy(r)
            doc_ids = {d["doc_id"] for d in r["documents"]}
            out["audit"] = [copy.deepcopy(e) for e in self.state_machine.audit_ledger
                            if e["doc_id"] == app_id or e["doc_id"] in doc_ids]
        return out

    def documents(self) -> List[Dict[str, Any]]:
        with self.lock:
            out = []
            for i in self.order:
                r = self.results[i]
                for d in r["documents"]:
                    out.append({**{k: d[k] for k in ("doc_id", "doc_type", "label", "status", "reason", "authority", "tampered")},
                                "app_id": r["id"], "institution_name": r["institution_name"], "state": r["state"]})
        return out

    def summary(self) -> Dict[str, Any]:
        with self.lock:
            rows = [self._row(self.results[i]) for i in self.order]
            tracks = {"GREEN": 0, "AMBER": 0, "RED": 0}
            doc_status = {s: 0 for s in VERIFICATION_STATES}
            by_state: Dict[str, Dict[str, Any]] = {}
            alerts = []
            for r in rows:
                tracks[r["track"]] += 1
                for s, c in r["doc_status_counts"].items():
                    doc_status[s] = doc_status.get(s, 0) + c
                st = by_state.setdefault(r["state"], {"state": r["state"], "total": 0, "GREEN": 0, "AMBER": 0, "RED": 0})
                st["total"] += 1
                st[r["track"]] += 1
                full = self.results[r["id"]]
                for flag in full["trust"]["fraud_flags"]:
                    alerts.append({"app_id": r["id"], "institution_name": r["institution_name"],
                                   "severity": "FRAUD", "text": flag})
                for flag in full["trust"]["critical_flags"]:
                    if flag.startswith("APH deficiency"):
                        continue  # keep the feed focused; deficiencies shown per application
                    alerts.append({"app_id": r["id"], "institution_name": r["institution_name"],
                                   "severity": "CRITICAL", "text": flag})
            n = len(rows)
            reviewed = sum(1 for i in self.order if self.results[i]["reviews"])
            fig_stats = self.fig.get_network_stats()
            return {
                "generated_at": self.evaluated_at,
                "applications": n,
                "tracks": tracks,
                "avg_rti": round(sum(r["rti"] for r in rows) / n, 1) if n else 0.0,
                "documents_total": sum(doc_status.values()),
                "doc_status": doc_status,
                "by_state": sorted(by_state.values(), key=lambda s: (-s["RED"], s["state"])),
                "alerts": alerts,
                "rti_ranking": sorted([{"id": r["id"], "institution_name": r["institution_name"],
                                        "rti": r["rti"], "track": r["track"]} for r in rows],
                                      key=lambda x: x["rti"]),
                "faculty_graph": fig_stats,
                "reviewed": reviewed,
                "pending_review": n - reviewed,
                "engine_total_ms": self.total_eval_ms,
                "engine_avg_ms": round(sum(r["evaluation_ms"] for r in rows) / n, 3) if n else 0.0,
                "audit_blocks": len(self.state_machine.audit_ledger),
            }

    def faculty_graph(self) -> Dict[str, Any]:
        with self.lock:
            inst_nodes = {}
            fac_nodes = []
            edges = []
            for token, deployments in self.fig.faculty_deployments.items():
                active = [d for d in deployments if d["end_date"] is None]
                flagged = len({d["institution_id"] for d in active}) > 1
                fac_nodes.append({
                    "id": "F:" + token[:12],
                    "token": token[:12] + "...",
                    "name_initials": deployments[0]["name_masked"],
                    "faculty_id": deployments[0]["aicte_faculty_id_masked"],
                    "flagged": flagged,
                    "institutions": [d["institution_id"] for d in active],
                })
                for d in deployments:
                    inst_nodes.setdefault(d["institution_id"], {
                        "id": "I:" + d["institution_id"],
                        "institution_id": d["institution_id"],
                        "name": d["institution_name"],
                        "faculty": 0, "flagged_faculty": 0,
                        "track": (self._track_for_institution(d["institution_id"])),
                    })
                    inst_nodes[d["institution_id"]]["faculty"] += 1
                    if flagged:
                        inst_nodes[d["institution_id"]]["flagged_faculty"] += 1
                    edges.append({"source": "F:" + token[:12], "target": "I:" + d["institution_id"],
                                  "flagged": flagged, "designation": d["designation"],
                                  "start_date": d["start_date"]})
            return {"institutions": list(inst_nodes.values()), "faculty": fac_nodes,
                    "edges": edges, "stats": self.fig.get_network_stats()}

    def _track_for_institution(self, inst_id: str) -> Optional[str]:
        for r in self.results.values():
            if r["institution_id"] == inst_id:
                return r["trust"]["track"]
        return None

    def audit(self, limit: int = 500) -> Dict[str, Any]:
        with self.lock:
            ledger = [copy.deepcopy(e) for e in self.state_machine.audit_ledger]
        for e in ledger:
            e["details"] = {k: (v.value if isinstance(v, VerificationStatus) else v) for k, v in e["details"].items()} \
                if isinstance(e["details"], dict) else e["details"]
        return {"total": len(ledger), "entries": list(reversed(ledger))[:max(1, limit)]}

    def verify_audit(self) -> Dict[str, Any]:
        with self.lock:
            return self.state_machine.verify_chain()

    def tamper_demo(self) -> Dict[str, Any]:
        """Simulates an insider editing a sealed ledger row (for demonstrating tamper evidence)."""
        with self.lock:
            ledger = self.state_machine.audit_ledger
            target = next((e for e in ledger if e["action"] == "ADVISORY_RECOMMENDATION"
                           and e["details"].get("track") == "RED"), None)
            if target is None:
                if not ledger:
                    raise ServiceError(409, "Audit ledger is empty")
                target = ledger[0]
            target["details"] = dict(target["details"])
            target["details"]["track"] = "GREEN"
            target["details"]["tampered_by"] = "simulated-insider"
            return {"tampered_index": target["index"], "doc_id": target["doc_id"],
                    "note": "Row edited in place WITHOUT re-sealing. Run integrity verification to detect it."}

    # ----------------------------------------------------------------- review
    def review(self, app_id: str, role: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        decision = str(payload.get("decision", "")).strip().upper()
        remarks = str(payload.get("remarks", "")).strip()
        officer = str(payload.get("officer_name", "")).strip()[:80]
        acknowledged = payload.get("evidence_reviewed") is True

        if decision not in DECISIONS:
            raise ServiceError(400, f"Unknown decision '{decision}'")
        if decision not in ROLES[role]["decisions"]:
            raise ServiceError(403, f"Role {ROLES[role]['label']} is not permitted to record '{DECISIONS[decision]['label']}'.")
        errors = []
        if not officer:
            errors.append("Officer name is required.")
        adverse = DECISIONS[decision]["adverse"]
        min_len = MIN_REMARKS_ADVERSE if adverse else MIN_REMARKS
        if len(remarks) < min_len:
            errors.append(f"Remarks must be at least {min_len} characters{' for adverse actions' if adverse else ''}.")
        if not acknowledged:
            errors.append("You must confirm that you personally reviewed the evidence (AI output is advisory only).")
        if len(remarks) > 2000:
            errors.append("Remarks must be at most 2000 characters.")
        if errors:
            raise ServiceError(422, "Review not recorded", errors)

        with self.lock:
            r = self.results.get(app_id)
            if r is None:
                raise ServiceError(404, f"Application '{app_id}' not found")
            ai_track = r["trust"]["track"]
            entry = {
                "at": _now(),
                "role": role,
                "role_label": ROLES[role]["label"],
                "officer_name": officer,
                "decision": decision,
                "decision_label": DECISIONS[decision]["label"],
                "adverse": adverse,
                "remarks": remarks,
                "ai_track_at_review": ai_track,
                "ai_rti_at_review": r["trust"]["rti"],
            }
            block = self.state_machine.record_audit_event(app_id, f"{role}:{officer}", f"HUMAN_REVIEW:{decision}", {
                "decision": decision, "adverse": adverse, "ai_track": ai_track, "remarks": remarks})
            entry["audit_hash"] = block
            r["reviews"].append(entry)
            if role == "SCRUTINY_OFFICER":
                r["workflow_status"] = "CLARIFICATION_SOUGHT" if decision == "REQUEST_CLARIFICATION" else "FORWARDED_TO_AUTHORITY"
            else:
                r["workflow_status"] = "CLARIFICATION_SOUGHT" if decision == "REQUEST_CLARIFICATION" else "DECISION_RECORDED"
            return {"review": entry, "workflow_status": r["workflow_status"]}

    # -------------------------------------------------------------- simulator
    def simulate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        app, errors = self._validate_sim(payload)
        if errors:
            raise ServiceError(422, "Invalid simulator input", errors)
        t0 = time.perf_counter()
        rule_eval = APHRuleEngine(aph_version="2024-2027").evaluate_application(app)
        assumed_docs = [{"doc_id": "SELF", "label": "Self-declared documents", "status": "VERIFIED", "tampered": False}]
        projection = trust_index.compute_trust_index(rule_eval, assumed_docs, [], [])
        findings = []
        for f in rule_eval["findings"]:
            item = dict(f)
            if f["status"] != "COMPLIANT":
                item["how_to_fix"] = FIX_GUIDANCE.get(f["rule_id"], "Refer to the cited APH clause.")
            findings.append(item)
        rule_eval["findings"] = findings
        return {
            "rule_evaluation": rule_eval,
            "projection": projection,
            "assumption": "Projection assumes every uploaded document later verifies successfully with its issuing authority, "
                          "and no ghost-faculty or affidavit flags. Not a guarantee of approval.",
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 3),
        }

    def _validate_sim(self, p: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        errors: List[str] = []

        def num(key, lo, hi, integer=False):
            v = p.get(key)
            try:
                if isinstance(v, bool) or v is None or (isinstance(v, str) and not v.strip()):
                    raise ValueError
                v = float(v)
                if integer:
                    if not v.is_integer():
                        raise ValueError
                    v = int(v)
            except (TypeError, ValueError, OverflowError):
                errors.append(f"'{key}' must be a {'whole ' if integer else ''}number.")
                return None
            if not (lo <= v <= hi):
                errors.append(f"'{key}' must be between {lo} and {hi}.")
                return None
            return v

        def date(key):
            v = str(p.get(key, "")).strip()
            if not _DATE_RE.match(v):
                errors.append(f"'{key}' must be a date in YYYY-MM-DD format.")
                return None
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                errors.append(f"'{key}' is not a valid calendar date.")
                return None
            return v

        app = {
            "program": "ENGINEERING_UG",
            "total_approved_intake": num("total_approved_intake", 0, 10000, integer=True),
            "verified_faculty_count": num("verified_faculty_count", 0, 2000, integer=True),
            "consecutive_provisional_oc_years": num("consecutive_provisional_oc_years", 0, 50, integer=True),
            "declared_land_acres": num("declared_land_acres", 0, 10000),
            "fire_noc_valid_till": date("fire_noc_valid_till"),
            "academic_year_start": date("academic_year_start") if p.get("academic_year_start") else self.academic_year_start,
        }
        oc = str(p.get("occupancy_certificate_type", "")).upper()
        if oc not in OC_TYPES:
            errors.append(f"'occupancy_certificate_type' must be one of {', '.join(OC_TYPES)}.")
        loc = str(p.get("location_type", "")).upper()
        if loc not in LOCATION_TYPES:
            errors.append(f"'location_type' must be one of {', '.join(LOCATION_TYPES)}.")
        app["occupancy_certificate_type"] = oc
        app["location_type"] = loc
        return app, errors

    def rules(self) -> Dict[str, Any]:
        return {"aph_version": self.rule_engine.aph_version, "rules": self.rule_engine.rules,
                "trust_config": trust_index.config(),
                "note": "Rule thresholds are currently implemented in core/rules_engine.py; "
                        "this catalogue is read from the engine, not from an editable JSON file."}
