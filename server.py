#!/usr/bin/env python3
"""
AICTE SATYA-SHIKSHA Web Server & REST API Gateway
Serves the official Government of India styled Scrutiny Dashboard and executes live regulatory checks.
Standard library only: runs with standard Python 3.14 without pip dependencies.
"""
import http.server
import socketserver
import json
import os
import sys
import urllib.parse
from datetime import datetime

# Add prototype/core to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "prototype"))

from core.rules_engine import APHRuleEngine
from core.faculty_graph import FacultyIntegrityGraph
from core.verification_state_machine import VerificationStateMachine
from core.affidavit_triangulator import AffidavitTriangulator
from core.forensic_analyzer import ForensicAnalyzer

PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Shared in-memory engine instances
rule_engine = APHRuleEngine(aph_version="2024-2027")
faculty_graph = FacultyIntegrityGraph()
state_machine = VerificationStateMachine()
triangulator = AffidavitTriangulator()
forensics = ForensicAnalyzer()

# Seed initial graph collisions
faculty_graph.register_faculty("INST_101", "Greenfield Institute of Technology", "Dr. R. K. S.", "ABCPS1234F", "1-4829104", "Professor & HOD", "2022-06-01")
faculty_graph.register_faculty("INST_202", "Vidya Polytechnic & Engineering College", "Dr. R. K. S.", "ABCPS1234F", "1-4829104", "Professor", "2023-01-15")
faculty_graph.register_faculty("INST_101", "Greenfield Institute of Technology", "Dr. A. V.", "BZXPV9876K", "1-9921023", "Associate Professor", "2021-08-01")
faculty_graph.register_faculty("INST_202", "Vidya Polytechnic & Engineering College", "Dr. A. V.", "BZXPV9876K", "1-9921023", "Associate Professor", "2023-08-01")

class GovPortalRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        
        if url.path == "/api/status":
            self.send_json_response({
                "service": "AICTE_SATYA_SHIKSHA_CORE",
                "status": "OPERATIONAL",
                "version": "1.0.0",
                "aph_norm": "2024-2027",
                "timestamp": datetime.now().isoformat()
            })
            return

        if url.path == "/api/faculty-stats":
            stats = faculty_graph.get_network_stats()
            self.send_json_response(stats)
            return

        if url.path == "/api/audit-trail":
            self.send_json_response({"audit_chain": state_machine.audit_ledger})
            return

        # Fallback to serving web/ directory
        return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)

        # 1. Shift-Left Pre-Audit Simulation API
        if url.path == "/api/pre-audit":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            eval_result = rule_engine.evaluate_application(data)
            self.send_json_response(eval_result)
            return

        # 2. Officer Decision Action with Merkle Audit Entry
        if url.path == "/api/officer-action":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except Exception:
                data = {}

            app_id = data.get("app_id", "AICTE-APP-GENERIC")
            decision = data.get("decision", "SCRUTINY_HOLD")
            actor = data.get("actor", "REGULATION_OFFICER_CHIEF")
            remarks = data.get("remarks", "Statutory human scrutiny completed.")

            block_hash = state_machine.record_audit_event(
                doc_id=f"DECISION_{app_id}",
                actor=actor,
                action=decision,
                details={"remarks": remarks, "app_id": app_id}
            )

            self.send_json_response({
                "status": "RECORDED",
                "block_hash": block_hash,
                "timestamp": datetime.now().isoformat(),
                "audit_index": len(state_machine.audit_ledger)
            })
            return

        self.send_error(404, "Endpoint not found")

    def send_json_response(self, payload: dict, status_code: int = 200):
        body = json.dumps(payload, indent=2).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

def run_server():
    print("=" * 80)
    print("       AICTE 'SATYA-SHIKSHA' (सत्य-शिक्षा) OFFICIAL WEB PLATFORM")
    print("   AI-Powered Application Validation, Document Authentication & Scrutiny")
    print("             Ministry of Education • Government of India")
    print("=" * 80)
    print()
    print(f"🏛️  Serving Official Government Scrutiny Dashboard from: {WEB_DIR}")
    print(f"🚀  Portal URL: http://localhost:{PORT}")
    print(f"🔒  Security: Standard-library isolated, DPDP Act 2023 compliant")
    print()
    print("👉 Press Ctrl+C in terminal to stop server anytime.")
    print("-" * 80)

    # Allow immediate address reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), GovPortalRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down AICTE SATYA-SHIKSHA server gracefully.")

if __name__ == "__main__":
    run_server()
