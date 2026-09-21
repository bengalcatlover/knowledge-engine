"""第二縦串シード: 情報理論 (Shannon Source Coding)

8ノード / 8エッジ / 3根拠 / 6 support assessments
"""

import hashlib
from pathlib import Path
from mvp_store import (
    init_db, add_node, add_claim, add_edge, add_evidence, add_support, set_status
)


def seed(db):
    # ════════════════════════════════════════════
    # Layer 1: Foundation — Shannon Source Coding Theorem
    # ════════════════════════════════════════════
    add_node(db, "B-0200", 1, "foundation", "FormalPrinciple", subtype="THM", status="approved", data={
        "title": "Shannon Source Coding Theorem",
        "statement": "離散無記憶情報源Xに対し、損失なし符号の平均符号長LはH(X)以上。prefix-free符号でH(X)<=L<H(X)+1を達成可能。",
        "admission": "theorem_import",
        "approval_scope": "model_assertion",
    })

    add_claim(db, "B-0200#c1", "B-0200", 1,
        "離散無記憶情報源に対する任意の一意復号可能符号の平均符号長LはエントロピーH(X)以上である",
        "theorem", epistemic_status="formally_verified")

    # ════════════════════════════════════════════
    # Layer 2: Science — Entropy Bound (scoped law)
    # ════════════════════════════════════════════
    add_node(db, "S-0200", 1, "science", "ScopedLaw", subtype="LAW", status="approved", data={
        "title": "Entropy Bound for Discrete Memoryless Sources",
        "domain_of_validity": "離散・有限アルファベット・無記憶（i.i.d.）情報源",
        "falsification_condition": "i.i.d.情報源でHuffman符号の平均符号長がH(X)を下回る反例",
        "admission": "theorem_import",
        "approval_scope": "model_assertion",
    })

    add_claim(db, "S-0200#c1", "S-0200", 1,
        "離散無記憶情報源において、Huffman符号は最適なprefix-free符号であり、平均符号長はH(X)以上H(X)+1未満",
        "theorem", epistemic_status="formally_verified")

    # ════════════════════════════════════════════
    # Reference asset: K-0017 (既存カード、参照のみ)
    # ════════════════════════════════════════════
    add_node(db, "K-0017", 1, "foundation", "FormalPrinciple", subtype="THY", status="approved", data={
        "title": "情報理論と表現圧縮",
        "admission": "imported_reference",
        "approval_scope": "reference_use",
    })

    # ════════════════════════════════════════════
    # Layer 3: Universe — Discrete Memoryless Source Model
    # ════════════════════════════════════════════
    add_node(db, "U-0200", 1, "universe", "WorldModel", subtype="WM", status="approved", data={
        "title": "Discrete Memoryless Source Model",
        "description": "有限アルファベットΣ上の独立同分布(i.i.d.)情報源。各シンボルの生成確率p(x)が既知。",
    })

    add_claim(db, "U-0200#c1", "U-0200", 1,
        "有限アルファベット上のi.i.d.情報源は、シンボルごとの確率分布p(x)で完全に記述される",
        "definition")

    # ════════════════════════════════════════════
    # Layer 4: Object — Huffman Coder
    # ════════════════════════════════════════════
    add_node(db, "O-0200", 1, "object", "System", status="approved", data={
        "title": "Huffman Coder",
        "implementation": "mvp_huffman_sim.py",
        "description": "Huffman符号化器。確率分布を入力とし、最適prefix-free符号を構築。",
    })

    # ════════════════════════════════════════════
    # Layer 5: Practice — Question / Action / Verification
    # ════════════════════════════════════════════
    add_node(db, "Q-0200", 1, "practice", "Question", subtype="Q", status="approved", data={
        "title": "Huffman符号は理論下限にどこまで近いか？",
        "question": "複数の確率分布に対してHuffman符号の平均符号長L≥H(X)が成立し、gapはどの程度か？",
    })

    add_node(db, "A-0200", 1, "practice", "Action", subtype="ACT", status="approved", data={
        "title": "Huffman符号実装と平均符号長測定",
        "action": "5種の確率分布に対しHuffman符号を構築し、H(X)とLを比較",
    })

    add_node(db, "V-0200", 1, "practice", "Verification", subtype="VER", status="approved", data={
        "title": "Shannon Bound検証結果",
        "result": "5/5ケースでH(X)<=L<H(X)+1を確認",
        "result_file": "work/mvp_huffman_result.json",
    })

    # ════════════════════════════════════════════
    # Evidence
    # ════════════════════════════════════════════

    # Shannon 1948 原論文（DOIあり）
    add_evidence(db, "E-SHANNON-1948", "source_excerpt",
        source_uri="doi:10.1002/j.1538-7305.1948.tb01338.x",
        source_version="1948",
        locator="Theorem 9 (Noiseless Coding Theorem), Section 9, pp.406-407",
        content_hash="pending_verification",
        origin_group="shannon1948",
        reliability_grade="A")

    # 証明書
    proof_path = Path(__file__).parent / "work" / "proof_B0200.md"
    proof_hash = hashlib.sha256(proof_path.read_text(encoding="utf-8").encode()).hexdigest()[:16]
    add_evidence(db, "E-PROOF-B0200", "proof_certificate",
        source_version="1.0",
        locator="work/proof_B0200.md",
        content_hash=proof_hash,
        origin_group="self_proof",
        reliability_grade="A")

    # Huffman実行ログ
    sim_result = Path(__file__).parent / "work" / "mvp_huffman_result.json"
    sim_hash = hashlib.sha256(sim_result.read_text(encoding="utf-8").encode()).hexdigest()[:16]
    add_evidence(db, "E-HUFFMAN-SIM", "execution_log",
        source_version="1.0.0",
        locator="work/mvp_huffman_result.json",
        content_hash=sim_hash,
        origin_group="huffman_sim_v1",
        reliability_grade="C")

    # ════════════════════════════════════════════
    # Support Assessments
    # ════════════════════════════════════════════
    add_support(db, "E-SHANNON-1948", "B-0200", 1, "B-0200#c1", "derivation",
        rationale="Shannon 1948 Theorem 9が定理の原典")
    add_support(db, "E-PROOF-B0200", "B-0200", 1, "B-0200#c1", "derivation",
        rationale="Kraft不等式とKLダイバージェンスの非負性による構成的証明")
    add_support(db, "E-SHANNON-1948", "S-0200", 1, "S-0200#c1", "premise",
        rationale="Shannon 1948がHuffman符号の最適性の基礎")
    add_support(db, "E-PROOF-B0200", "S-0200", 1, "S-0200#c1", "derivation",
        rationale="B-0200の証明がS-0200の上界・下界を直接与える")
    add_support(db, "E-HUFFMAN-SIM", "O-0200", 1, None, "observation",
        rationale="5ケースの実行でH(X)<=L<H(X)+1を確認")
    add_support(db, "E-HUFFMAN-SIM", "V-0200", 1, None, "observation",
        rationale="検証結果ファイルによる実測確認")

    # ════════════════════════════════════════════
    # Edges
    # ════════════════════════════════════════════
    add_edge(db, "ABSTRACTS_FROM", "B-0200", 1, "S-0200", 1,
        rationale="Source Coding Theoremがentropy boundの数学的基盤")
    add_edge(db, "ABSTRACTS_FROM", "S-0200", 1, "U-0200", 1,
        rationale="Entropy boundが離散無記憶情報源モデルに適用")
    add_edge(db, "ABSTRACTS_FROM", "U-0200", 1, "O-0200", 1,
        rationale="情報源モデルがHuffman coder設計の基盤")
    add_edge(db, "HAS_SCOPED_INSTANCE", "K-0017", 1, "U-0200", 1,
        rationale="情報理論の具体的適用例としてのDMS")

    add_edge(db, "ABOUT", "Q-0200", 1, "U-0200", 1)
    add_edge(db, "PLANS", "Q-0200", 1, "A-0200", 1)
    add_edge(db, "EXECUTES_ON", "A-0200", 1, "O-0200", 1)
    add_edge(db, "PRODUCES", "A-0200", 1, "V-0200", 1)

    print("=== Second vertical slice seeded ===")
    print("Nodes: 8 (B-0200, S-0200, K-0017, U-0200, O-0200, Q-0200, A-0200, V-0200)")
    print("Edges: 8")
    print("Evidence: 3 (E-SHANNON-1948, E-PROOF-B0200, E-HUFFMAN-SIM)")
    print("Support assessments: 6")


if __name__ == "__main__":
    db = init_db()
    seed(db)

    # 投入後のグラフダンプ
    from mvp_store import dump_graph
    print()
    dump_graph(db)
