"""第二縦串: Huffman符号シミュレータ (O-0200) + 検証 (V-0200)

Shannon Source Coding Theoremの検証:
  離散無記憶情報源に対するHuffman符号の平均符号長が
  エントロピーH(X)以上であること、かつH(X)+1以下であることを確認。
"""

import hashlib
import json
import math
from pathlib import Path


def entropy(probs: list[float]) -> float:
    """Shannon entropy H(X) = -Σ p(x) log2 p(x)"""
    return -sum(p * math.log2(p) for p in probs if p > 0)


def huffman_code(symbols_probs: list[tuple[str, float]]) -> dict[str, str]:
    """Huffman符号を構築。返り値: {symbol: codeword}"""
    if len(symbols_probs) <= 1:
        return {symbols_probs[0][0]: "0"} if symbols_probs else {}

    # ノードリスト: (prob, symbol_or_subtree)
    nodes = [(p, [(s, "")]) for s, p in symbols_probs]

    while len(nodes) > 1:
        nodes.sort(key=lambda x: x[0])
        lo = nodes.pop(0)
        hi = nodes.pop(0)
        merged_symbols = [(s, "0" + code) for s, code in lo[1]] + [(s, "1" + code) for s, code in hi[1]]
        nodes.append((lo[0] + hi[0], merged_symbols))

    return {s: code for s, code in nodes[0][1]}


def avg_code_length(codes: dict[str, str], probs: dict[str, float]) -> float:
    """平均符号長 L = Σ p(x) * len(code(x))"""
    return sum(probs[s] * len(c) for s, c in codes.items())


def run_verification() -> dict:
    """複数の確率分布でH(X) <= L <= H(X)+1を検証"""
    test_cases = [
        ("uniform_4", {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}),
        ("skewed", {"A": 0.5, "B": 0.25, "C": 0.125, "D": 0.125}),
        ("highly_skewed", {"A": 0.9, "B": 0.05, "C": 0.03, "D": 0.02}),
        ("binary", {"0": 0.7, "1": 0.3}),
        ("uniform_8", {chr(65+i): 1/8 for i in range(8)}),
    ]

    results = []
    all_pass = True

    for name, probs in test_cases:
        H = entropy(list(probs.values()))
        symbols_probs = [(s, p) for s, p in probs.items()]
        codes = huffman_code(symbols_probs)
        L = avg_code_length(codes, probs)

        # Shannon bound: H(X) <= L <= H(X) + 1
        lower_ok = L >= H - 1e-9
        upper_ok = L <= H + 1 + 1e-9
        passed = lower_ok and upper_ok

        if not passed:
            all_pass = False

        results.append({
            "name": name,
            "H": round(H, 6),
            "L": round(L, 6),
            "gap": round(L - H, 6),
            "lower_bound_ok": lower_ok,
            "upper_bound_ok": upper_ok,
            "passed": passed,
            "codes": codes,
        })

    return {
        "all_pass": all_pass,
        "n_cases": len(test_cases),
        "results": results,
    }


if __name__ == "__main__":
    result = run_verification()

    # コードハッシュ
    code = Path(__file__).read_text(encoding="utf-8")
    code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]

    output = {
        "simulator": "mvp_huffman_sim.py",
        "code_hash": code_hash,
        "verification": result,
    }

    out_path = Path(__file__).parent / "work" / "mvp_huffman_result.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"=== Huffman Coding Verification ===")
    print(f"Code hash: {code_hash}")
    print(f"Cases: {result['n_cases']}, All pass: {result['all_pass']}")
    print()

    for r in result["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['name']}: H={r['H']:.4f}, L={r['L']:.4f}, gap={r['gap']:.4f}")
        print(f"         codes: {r['codes']}")

    print(f"\nResult saved to {out_path}")
