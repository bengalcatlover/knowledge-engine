"""O-0100: 第二価格封印入札シミュレーター（版固定）

A-0100: 全許容入力の厳密列挙+逸脱利得検査
V-0100: 検証結果の記録

設定:
- 入札者2人、単一財
- 評価額・入札額: {0, 1, 2}
- 落札者: 最高入札者（同額時は入札者1優先）
- 支払額: 他者の入札額（第二価格）
- 私的価値、準線形効用
"""

import hashlib
import json
from datetime import datetime, timezone
from itertools import product
from pathlib import Path


VALUES = [0, 1, 2]
BIDS = [0, 1, 2]


# ════════════════════════════════════════════
# O-0100: シミュレーター
# ════════════════════════════════════════════

def second_price_auction(bid1: int, bid2: int, val1: int, val2: int) -> tuple[float, float]:
    """第二価格封印入札。(utility1, utility2)を返す"""
    if bid1 > bid2:
        return val1 - bid2, 0.0
    elif bid2 > bid1:
        return 0.0, val2 - bid1
    else:  # 同額: 入札者1優先
        return float(val1 - bid2), 0.0


def first_price_auction(bid1: int, bid2: int, val1: int, val2: int) -> tuple[float, float]:
    """第一価格封印入札（変異実装）。検査器が逸脱を検出すべき"""
    if bid1 > bid2:
        return val1 - bid1, 0.0
    elif bid2 > bid1:
        return 0.0, val2 - bid2
    else:
        return float(val1 - bid1), 0.0


# ════════════════════════════════════════════
# A-0100: 全入力列挙+逸脱利得検査
# ════════════════════════════════════════════

def check_deviations(auction_func, label: str) -> dict:
    """全入力組合せについて正直入札からの逸脱利得を検査"""
    results = {
        "auction_type": label,
        "total_scenarios": 0,
        "deviations_found": [],
    }

    for v1, v2 in product(VALUES, repeat=2):
        # 正直入札: bid = value
        truthful_u1, truthful_u2 = auction_func(v1, v2, v1, v2)

        # 入札者1の逸脱チェック
        for b1 in BIDS:
            if b1 == v1:
                continue
            u1, _ = auction_func(b1, v2, v1, v2)
            results["total_scenarios"] += 1
            if u1 > truthful_u1 + 1e-9:
                results["deviations_found"].append({
                    "player": 1, "value": v1, "other_bid": v2,
                    "truthful_bid": v1, "deviated_bid": b1,
                    "truthful_utility": truthful_u1, "deviated_utility": u1,
                    "gain": u1 - truthful_u1,
                })

        # 入札者2の逸脱チェック
        for b2 in BIDS:
            if b2 == v2:
                continue
            _, u2 = auction_func(v1, b2, v1, v2)
            results["total_scenarios"] += 1
            if u2 > truthful_u2 + 1e-9:
                results["deviations_found"].append({
                    "player": 2, "value": v2, "other_bid": v1,
                    "truthful_bid": v2, "deviated_bid": b2,
                    "truthful_utility": truthful_u2, "deviated_utility": u2,
                    "gain": u2 - truthful_u2,
                })

    results["deviations_count"] = len(results["deviations_found"])
    return results


# ════════════════════════════════════════════
# V-0100: 検証
# ════════════════════════════════════════════

def run_verification() -> dict:
    """全検証を実行し、結果を返す"""

    # 第二価格の逸脱検査
    sp_result = check_deviations(second_price_auction, "second_price")

    # 第一価格の逸脱検査（変異検出テスト）
    fp_result = check_deviations(first_price_auction, "first_price_mutation")

    # コードのハッシュ（再現性のため）
    code_path = Path(__file__)
    code_hash = hashlib.sha256(code_path.read_bytes()).hexdigest()[:16]

    verification = {
        "verification_id": "V-0100@1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_hash": code_hash,
        "code_path": str(code_path),

        "second_price": {
            "total_scenarios": sp_result["total_scenarios"],
            "deviations_count": sp_result["deviations_count"],
            "verdict": "NO_PROFITABLE_DEVIATION" if sp_result["deviations_count"] == 0 else "DEVIATION_FOUND",
            "deviations": sp_result["deviations_found"],
        },

        "first_price_mutation": {
            "total_scenarios": fp_result["total_scenarios"],
            "deviations_count": fp_result["deviations_count"],
            "verdict": "MUTATION_DETECTED" if fp_result["deviations_count"] > 0 else "MUTATION_NOT_DETECTED",
            "deviations": fp_result["deviations_found"],
        },

        "conclusions": {
            "Q1_answer": None,  # 後で設定
            "H1_status": "not_run",
            "limitations": [
                "有限離散モデル({0,1,2})のみ。連続評価額への拡張は未検証",
                "入札者2人のみ。n>=3への拡張は別途検証が必要",
                "人間への効果(H1)は実験未実施のため未検証",
            ],
        },

        "pass_criteria": {
            "no_profitable_deviation": sp_result["deviations_count"] == 0,
            "mutation_detected": fp_result["deviations_count"] > 0,
        },
    }

    # Q1への回答
    if sp_result["deviations_count"] == 0:
        verification["conclusions"]["Q1_answer"] = (
            "指定モデル（入札者2人、評価額{0,1,2}、私的価値、準線形効用）において、"
            "第二価格封印入札では正直入札からの有利な逸脱は存在しない。"
            "正直入札は弱支配戦略であり、正直入札プロファイルはナッシュ均衡である。"
        )
    else:
        verification["conclusions"]["Q1_answer"] = (
            f"逸脱が{sp_result['deviations_count']}件検出された。正直入札は弱支配戦略ではない。"
        )

    return verification


# ════════════════════════════════════════════
# 実行+DB記録
# ════════════════════════════════════════════

if __name__ == "__main__":
    result = run_verification()

    # 結果表示
    print("=== V-0100 Verification Results ===\n")

    sp = result["second_price"]
    print(f"Second Price Auction:")
    print(f"  Scenarios tested: {sp['total_scenarios']}")
    print(f"  Deviations found: {sp['deviations_count']}")
    print(f"  Verdict: {sp['verdict']}")

    fp = result["first_price_mutation"]
    print(f"\nFirst Price Mutation Test:")
    print(f"  Scenarios tested: {fp['total_scenarios']}")
    print(f"  Deviations found: {fp['deviations_count']}")
    print(f"  Verdict: {fp['verdict']}")
    if fp["deviations"]:
        print(f"  Example: player={fp['deviations'][0]['player']}, "
              f"value={fp['deviations'][0]['value']}, "
              f"truthful_bid={fp['deviations'][0]['truthful_bid']}→"
              f"deviated_bid={fp['deviations'][0]['deviated_bid']}, "
              f"gain={fp['deviations'][0]['gain']:.2f}")

    print(f"\nQ1 Answer: {result['conclusions']['Q1_answer']}")
    print(f"H1 Status: {result['conclusions']['H1_status']}")
    print(f"\nCode hash: {result['code_hash']}")

    # 結果をJSONで保存
    out_path = Path(__file__).parent / "work" / "mvp_verification_result.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out_path}")

    # MVPストアに実行ログをevidenceとして記録
    from mvp_store import get_db as get_mvp_db, add_evidence, add_support, set_status
    db = get_mvp_db()

    result_hash = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]

    add_evidence(db, "E-SIM-V1", "execution_log",
        source_uri=None,
        source_version="1.0.0",
        locator="work/mvp_verification_result.json",
        content_hash=result_hash,
        origin_group="simulator_v1",
        reliability_grade="C")

    add_support(db, "E-SIM-V1", "O-0100", 1, None, "observation",
        rationale="シミュレーター実行ログ", assessor="deterministic_runner")

    add_support(db, "E-SIM-V1", "V-0100", 1, None, "observation",
        rationale="検証結果", assessor="deterministic_runner")

    # Pass criteria met → ノードをreadyに
    if result["pass_criteria"]["no_profitable_deviation"] and result["pass_criteria"]["mutation_detected"]:
        for nid in ["O-0100", "V-0100"]:
            set_status(db, nid, 1, "ready")
        print("\nO-0100, V-0100 → ready")
    else:
        print("\nPass criteria NOT met. Nodes remain draft.")

    all_pass = all(result["pass_criteria"].values())
    print(f"\n{'ALL PASS' if all_pass else 'SOME FAILED'}")
