#!/usr/bin/env python3
"""
SPDX-License-Identifier: Apache-2.0
===================================
SARAISE GCR Collector
===================================
Collects compliance data from CI/CD and generates GCR entries
===================================
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

GCR_ROOT = Path(__file__).parent.parent.parent / "saraise-documentation" / ".governance"


def collect_coverage_data() -> Dict:
    """Collect test coverage data."""
    backend_coverage = Path("backend/coverage.xml")
    frontend_coverage = Path("frontend/coverage/coverage-summary.json")
    
    data = {
        "backend": {},
        "frontend": {},
    }
    
    # Parse backend coverage
    if backend_coverage.exists():
        try:
            # Use defusedxml for secure XML parsing
            try:
                from defusedxml.ElementTree import parse as safe_parse
            except ImportError:
                # Fallback to standard library if defusedxml not available
                import xml.etree.ElementTree as ET
                safe_parse = ET.parse
            
            tree = safe_parse(backend_coverage)
            root = tree.getroot()
            total_line_rate = float(root.get("line-rate", 0)) * 100
            data["backend"]["overall"] = total_line_rate
        except Exception as e:
            print(f"⚠️  Error parsing backend coverage: {e}", file=sys.stderr)
    
    # Parse frontend coverage
    if frontend_coverage.exists():
        try:
            with open(frontend_coverage) as f:
                cov_data = json.load(f)
                if "total" in cov_data and "lines" in cov_data["total"]:
                    data["frontend"]["overall"] = cov_data["total"]["lines"]["pct"]
        except Exception as e:
            print(f"⚠️  Error parsing frontend coverage: {e}", file=sys.stderr)
    
    return data


def collect_sast_data() -> Dict:
    """Collect SAST scan results."""
    semgrep_results = Path("semgrep-results.json")
    
    data = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }
    
    if semgrep_results.exists():
        try:
            with open(semgrep_results) as f:
                results = json.load(f)
                for finding in results.get("results", []):
                    severity = finding.get("extra", {}).get("severity", "INFO")
                    if severity == "ERROR":
                        data["critical"] += 1
                    elif severity == "WARNING":
                        data["high"] += 1
        except Exception as e:
            print(f"⚠️  Error parsing SAST results: {e}", file=sys.stderr)
    
    return data


def generate_compliance_snapshot() -> Dict:
    """Generate daily compliance snapshot."""
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "coverage": collect_coverage_data(),
        "sast": collect_sast_data(),
    }
    
    return snapshot


def save_snapshot(snapshot: Dict):
    """Save compliance snapshot to GCR."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot_dir = GCR_ROOT / "status" / date_str
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot_file = snapshot_dir / "compliance-report.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    
    print(f"✅ Compliance snapshot saved: {snapshot_file}")


def main():
    """Main entry point."""
    if not GCR_ROOT.exists():
        print(f"⚠️  GCR root not found: {GCR_ROOT}")
        print("   Skipping GCR collection (documentation repo may not be available)")
        sys.exit(0)
    
    snapshot = generate_compliance_snapshot()
    save_snapshot(snapshot)
    
    print("✅ GCR collection complete")


if __name__ == "__main__":
    main()
