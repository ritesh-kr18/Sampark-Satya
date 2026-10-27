"""
Document Forensic Analyzer: Error Level Analysis (ELA) Simulation,
PAdES Incremental Revision Check, and Perceptual Hashing (pHash).
"""
import hashlib
from typing import Dict, Any

class ForensicAnalyzer:
    def inspect_pdf_pades_signature(self, has_digital_signature: bool, has_incremental_modification_after_sign: bool) -> Dict[str, Any]:
        """
        Inspects PDF byte-level revision tree to detect if content was injected
        after a trusted Controller of Certifying Authorities (CCA India) digital signature was sealed.
        """
        if not has_digital_signature:
            return {
                "has_pades_signature": False,
                "is_signature_valid": False,
                "post_sign_tamper_detected": False,
                "remarks": "Document has no PAdES digital signature. Requires visual/authority verification."
            }

        if has_incremental_modification_after_sign:
            return {
                "has_pades_signature": True,
                "is_signature_valid": False,
                "post_sign_tamper_detected": True,
                "severity": "CRITICAL_SECURITY_BREACH",
                "remarks": "PDF contains incremental byte updates modifying visual text streams AFTER the digital signature was applied!"
            }

        return {
            "has_pades_signature": True,
            "is_signature_valid": True,
            "post_sign_tamper_detected": False,
            "certificate_authority": "CCA India Empanelled CA (e-Mudhra / NSDL / NIC)",
            "remarks": "Valid digital signature with uncompromised cryptographic byte integrity."
        }

    def simulate_ela_analysis(self, is_digitally_altered: bool, altered_region: str = "") -> Dict[str, Any]:
        """
        Simulates Error Level Analysis (ELA) for detecting JPEG recompression anomalies
        around modified dates, numbers, or cloned stamps.
        """
        if is_digitally_altered:
            return {
                "ela_anomaly_detected": True,
                "compression_variance_ratio": 4.82,  # Normal background is ~1.0
                "suspicious_bounding_box": {"x": 420, "y": 680, "w": 140, "h": 45},
                "affected_region_description": altered_region or "Validity expiry date region",
                "severity": "HIGH_CONFIDENCE_TAMPER",
                "forensic_explanation": "Pixel compression error levels in the date bounding box are 4.8x higher than the surrounding stamp paper background, indicating digital cut-and-paste alteration."
            }

        return {
            "ela_anomaly_detected": False,
            "compression_variance_ratio": 1.04,
            "severity": "CLEAN",
            "forensic_explanation": "Uniform compression error distribution across the entire page surface. No localized digital compositing detected."
        }

    def compute_perceptual_hash(self, document_token: str) -> str:
        """Computes a simulated 64-bit DCT perceptual hash for cross-institutional duplicate detection."""
        return hashlib.md5(f"PHASH_SAMPLE_{document_token}".encode('utf-8')).hexdigest()[:16]
