# SATYA-SHIKSHA (सत्य-शिक्षा)
### AI-Powered Higher Education Application Validation, Document Authentication & Regulatory Scrutiny Platform

An intelligent decision-support system designed for the **All India Council for Technical Education (AICTE), Ministry of Education, Government of India**. 

The platform automates the scrutiny of Extension of Approval (EoA), New Institution setup, and Intake Expansion applications by evaluating documents against the AICTE Approval Process Handbook (APH 2024–2027), detecting digital forgeries, cross-checking ghost faculty, and tracking statutory decisions through an immutable cryptographic audit ledger.

---

## 🏛️ Key Capabilities

1. **Category-Based Checklists & Rule Engine:** Automated validation for Faculty-to-Student Ratios (FSR 1:20 norm), Provisional Occupancy Certificate limits (max 2 consecutive years per APH Clause 7.3), Fire Safety NOC validity, and land acreage standards.
2. **National Faculty Integrity Graph (FIG):** Privacy-preserving temporal bipartite graph detecting concurrent dual-employment across multiple institutions (DPDP Act 2023 compliant using salted SHA-256 tokens; zero raw Aadhaar stored).
3. **Affidavit-vs-Evidence Triangulator:** Cross-examines sworn declarations made in legal stamp-paper affidavits (Affidavit-2) against attached municipal certificates to flag false declarations and built-up area inflation.
4. **Multi-Layer Document Forensics:**
   - **PAdES Digital Signature Integrity (`pyHanko`):** Detects post-signing byte-level text/stamp additions.
   - **Error Level Analysis (ELA):** Analyzes JPEG compression variance to reveal digitally altered dates or numbers.
   - **Perceptual Hashing (pHash):** Flags inter-institutional document re-use and template recycling.
5. **"Shift-Left" Pre-Submission Simulator:** A zero-penalty diagnostic sandbox allowing colleges to test their applications and rectify deficiencies before paying non-refundable fees.
6. **6-State Issuing Authority Verification:** Enforces the mandatory state model: `VERIFIED`, `MISMATCH_DETECTED`, `EXPIRED`, `VERIFICATION_PENDING`, `SOURCE_UNAVAILABLE`, and `MANUAL_REVIEW_REQUIRED`.
7. **Merkle Hash-Chained Audit Ledger:** Immutably records every rule checked, authority response, and officer decision in a cryptographic SHA-256 block chain.

---

## 🚀 Quick Start Guide

### 1. Run the Web Dashboard & API Server
No external dependencies (`pip` or `npm`) required. Runs on standard Python 3:

```bash
python3 server.py
```
Open your browser and navigate to:
👉 **http://localhost:8000**

### 2. Run the CLI Simulation Engine
To execute the automated evaluation across all 4 synthetic institutional scenarios:

```bash
python3 prototype/demo_runner.py
```

---

## 📁 Repository Structure

```
├── server.py                        # Web server & REST API gateway (Python standard library)
├── web/
│   └── index.html                   # Official Government of India Scrutiny Dashboard & Simulator UI
├── prototype/
│   ├── demo_runner.py               # CLI test runner for 4 regulatory scenarios
│   └── core/
│       ├── rules_engine.py          # APH 2024-27 configurable regulatory rule engine
│       ├── faculty_graph.py         # National Faculty Integrity Graph (Ghost Faculty Radar)
│       ├── verification_state_machine.py # 6-state verification state machine & Merkle audit ledger
│       ├── affidavit_triangulator.py # Sworn affidavit vs ground evidence contradiction engine
│       └── forensic_analyzer.py     # PAdES signature, ELA heatmap & pHash forensics
├── SIH_AICTE_PROPOSAL_MASTER.md     # Full architectural specification, database schema & API docs
├── .gitignore                       # Standard Git ignore file
└── README.md                        # Project documentation
```

---

## 🔒 Security & Statutory Safeguards
* **Non-Adverse AI Decision Support:** AI outputs are strictly decision-support indicators. All adverse regulatory actions (issuing deficiency notices, scheduling surprise inspections, or withholding approval) require human review and digital sign-off by authorized regulatory officers.
* **Data Privacy Compliance:** Eliminates raw Aadhaar storage by utilizing cryptographic salted hashes of PAN and AICTE Faculty IDs in compliance with the Digital Personal Data Protection (DPDP) Act 2023 and UIDAI guidelines.
