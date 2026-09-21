#!/usr/bin/env python3
"""主張台帳の根拠状態を集計し、未解決の主張を機械的に止める。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / "work" / "claim_maps"


def audit(directory: Path) -> dict:
    rows = []
    for path in sorted(directory.glob("K-*.yaml")):
        item = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        claims = item.get("claims", [])
        derived = [claim for claim in claims if claim.get("type") == "lecture_derived"]
        unresolved = [claim["id"] for claim in derived if claim.get("disposition") != "supported_by_search_excerpt"]
        hypotheses = [claim["id"] for claim in claims if claim.get("type") == "application_hypothesis"]
        rows.append({
            "card_id": item.get("card_id", path.stem),
            "derived_claims": len(derived),
            "supported_derived_claims": len(derived) - len(unresolved),
            "unresolved_claims": unresolved,
            "application_hypotheses": hypotheses,
            "review_ready": bool(derived) and not unresolved,
        })
    return {
        "cards": rows,
        "review_ready": [row["card_id"] for row in rows if row["review_ready"]],
        "blocked": [row["card_id"] for row in rows if not row["review_ready"]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="主張台帳の根拠状態を監査")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), ensure_ascii=False, indent=2))
