#!/usr/bin/env python3
"""根拠付き知識成長の第1段階: 既存の穴を来歴付きで計画化する。

この段階はネットワーク・LLM・カード生成を行わない。`query_gap_detected`を
質問と穴に投影し、既存草案のレビュー、検索修復、外部探索候補へ分ける。

使い方:
    python kb_grow.py migrate
    python kb_grow.py plan --from-events --offline
    python kb_grow.py plans
    python kb_grow.py review list
    python kb_grow.py review show K-0002
    python kb_grow.py propose --plan .growth/plans/PLAN.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from graph import load_graph
from kb import append_event

ROOT = Path(__file__).resolve().parent
STATE_DB = ROOT / "work" / "state.sqlite3"
GROWTH_ROOT = ROOT / ".growth"
GROWTH_DB = GROWTH_ROOT / "growth.sqlite3"
PLANS = GROWTH_ROOT / "plans"
PROPOSALS = GROWTH_ROOT / "proposals"
WORLD_SEEDS = ROOT / "work" / "world_question_seeds.yaml"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def db() -> sqlite3.Connection:
    GROWTH_ROOT.mkdir(exist_ok=True)
    connection = sqlite3.connect(GROWTH_DB)
    connection.row_factory = sqlite3.Row
    return connection


def migrate() -> None:
    """質問・穴・計画の投影テーブルを作る。既存の台帳を変更しない。"""
    with db() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS question (
            question_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            origin TEXT NOT NULL CHECK(origin IN ('observed_use','human_probe','synthetic','legacy_unknown')),
            generation_depth INTEGER NOT NULL,
            root_id TEXT NOT NULL,
            parent_ids TEXT NOT NULL CHECK(json_valid(parent_ids)),
            status TEXT NOT NULL CHECK(status IN ('new','covered','weak','gap','processed','skipped')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gap (
            gap_id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL REFERENCES question(question_id),
            source_event_id TEXT NOT NULL UNIQUE,
            intent_key TEXT NOT NULL,
            gap_kind TEXT NOT NULL CHECK(gap_kind IN ('retrieval_miss','existing_unreviewed','source_gap','concept_gap','boundary_gap','out_of_scope')),
            status TEXT NOT NULL CHECK(status IN ('new','review_existing','acquire','defer','rejected','planned','processed')),
            reason TEXT NOT NULL,
            related_cards TEXT NOT NULL CHECK(json_valid(related_cards)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS growth_plan (
            plan_id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            input_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('planned','superseded','completed'))
        );
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            gap_id TEXT NOT NULL REFERENCES gap(gap_id),
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            video_id TEXT NOT NULL,
            quote TEXT NOT NULL,
            search_output_hash TEXT NOT NULL,
            verified INTEGER NOT NULL CHECK(verified IN (0,1)),
            created_at TEXT NOT NULL,
            UNIQUE(gap_id, source_id, search_output_hash)
        );
        """)
        if "external_query" not in {row[1] for row in connection.execute("PRAGMA table_info(question)")}:
            connection.execute("ALTER TABLE question ADD COLUMN external_query TEXT")
    print(f"growth migration complete: {GROWTH_DB}")


def card_titles() -> dict[str, str]:
    """既存カードへの明確な言及だけを検出する。草案を根拠としては使わない。"""
    return {card_id: card["title"] for card_id, card in load_graph().items() if card_id.startswith("K-")}


def card_english_query(card_id: str) -> str | None:
    """カードの既存aliasから、MIT検索に使う2〜5語の英語検索語を選ぶ。"""
    graph = load_graph()
    card = graph.get(card_id)
    if not card:
        return None
    path = ROOT / card["path"]
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^aliases:\s*\[(.*)\]", text, re.MULTILINE)
    if not match:
        return None
    aliases = [item.strip().strip('"').strip("'") for item in match.group(1).split(",")]
    for alias in aliases:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", alias)
        if 2 <= len(words) <= 5:
            return " ".join(words)
    return None


def duplicate_card_for_query(query: str) -> str | None:
    """既存草案のcanonical/aliasとの明確な英語重複だけを保守的に検出する。"""
    query_words = set(re.findall(r"[a-z][a-z0-9_-]*", query.casefold()))
    if len(query_words) < 2:
        return None
    for card_id, card in load_graph().items():
        if not card_id.startswith("K-"):
            continue
        text = (ROOT / card["path"]).read_text(encoding="utf-8", errors="replace")
        canonical = re.search(r'^canonical_name:\s*"?(.*?)"?\s*$', text, re.MULTILINE)
        aliases = re.search(r"^aliases:\s*\[(.*)\]", text, re.MULTILINE)
        labels = [canonical.group(1)] if canonical else []
        if aliases:
            labels.extend(item.strip().strip('"').strip("'") for item in aliases.group(1).split(","))
        for label in labels:
            label_words = set(re.findall(r"[a-z][a-z0-9_-]*", label.casefold()))
            # 少なくとも2つの専門語が一致する場合だけ、重複レビューへ送る。
            if len(label_words & query_words) >= 2:
                return card_id
    return None


def route_known_duplicates() -> None:
    """根拠収集前に、既存草案と明確に重なる探索をレビューへ戻す。"""
    routed = 0
    with db() as connection:
        rows = connection.execute("""
            SELECT g.gap_id, q.external_query
            FROM gap g JOIN question q ON q.question_id = g.question_id
            WHERE g.gap_kind = 'concept_gap' AND g.status IN ('defer', 'planned')
              AND q.external_query IS NOT NULL AND g.related_cards = '[]'
        """).fetchall()
        for row in rows:
            card_id = duplicate_card_for_query(row["external_query"])
            if not card_id:
                continue
            connection.execute("""
                UPDATE gap
                SET gap_kind = 'existing_unreviewed', status = 'review_existing',
                    related_cards = ?,
                    reason = '既存草案のcanonical_nameと英語探索語が明確に一致した。新規カードではなく根拠レビューへ送る。'
                WHERE gap_id = ?
            """, (json.dumps([card_id]), row["gap_id"]))
            append_event("duplicate_routed", entity_ref=row["gap_id"], payload={"gap_id": row["gap_id"], "card_id": card_id, "query": row["external_query"]}, actor="kb_grow")
            routed += 1
    print(f"known duplicates routed: {routed}")


def reconcile_planned_gaps() -> None:
    """旧版の実行で残ったplanned状態を、証拠台帳から安全に再分類する。"""
    with db() as connection:
        rows = connection.execute("SELECT gap_id FROM gap WHERE status = 'planned'").fetchall()
        acquired = deferred = 0
        for row in rows:
            found = connection.execute(
                "SELECT 1 FROM evidence WHERE gap_id = ? AND verified = 1 LIMIT 1", (row["gap_id"],)
            ).fetchone()
            connection.execute("UPDATE gap SET status = ? WHERE gap_id = ?", ("acquire" if found else "defer", row["gap_id"]))
            acquired += bool(found)
            deferred += not bool(found)
    print(f"planned gaps reconciled: acquire={acquired}, defer={deferred}")


def mark_draft_created(gap_id: str, card_id: str) -> None:
    """根拠付きで生成済みのAI草案に対応する探索穴を閉じる。"""
    card_path = ROOT / "concepts" / "_inbox" / f"{card_id}.md"
    if not card_path.exists():
        raise SystemExit(f"draft card not found: {card_path}")
    with db() as connection:
        row = connection.execute("SELECT status FROM gap WHERE gap_id = ?", (gap_id,)).fetchone()
        if not row:
            raise SystemExit(f"gap not found: {gap_id}")
        connection.execute("UPDATE gap SET status = 'processed' WHERE gap_id = ?", (gap_id,))
    append_event("draft_card_generated", entity_ref=card_id, payload={"card_id": card_id, "gap_id": gap_id, "path": str(card_path.relative_to(ROOT))}, actor="kb_grow")
    print(f"draft linked: {gap_id} -> {card_id}")


def route_to_existing_card(gap_id: str, card_id: str, reason: str) -> None:
    """人間が読める理由を残して、候補を既存草案の根拠レビューへ戻す。"""
    if card_id not in load_graph():
        raise SystemExit(f"card not found: {card_id}")
    with db() as connection:
        row = connection.execute("SELECT 1 FROM gap WHERE gap_id = ?", (gap_id,)).fetchone()
        if not row:
            raise SystemExit(f"gap not found: {gap_id}")
        connection.execute("""
            UPDATE gap SET gap_kind = 'existing_unreviewed', status = 'review_existing',
                related_cards = ?, reason = ? WHERE gap_id = ?
        """, (json.dumps([card_id]), reason, gap_id))
    append_event("candidate_routed", entity_ref=gap_id, payload={"gap_id": gap_id, "card_id": card_id, "reason": reason}, actor="kb_grow")
    print(f"routed: {gap_id} -> {card_id}")


def defer_gap(gap_id: str, reason: str) -> None:
    """二者レビュー等で根拠不足になった候補を、理由付きで保留する。"""
    with db() as connection:
        row = connection.execute("SELECT 1 FROM gap WHERE gap_id = ?", (gap_id,)).fetchone()
        if not row:
            raise SystemExit(f"gap not found: {gap_id}")
        connection.execute("UPDATE gap SET status = 'defer', reason = ? WHERE gap_id = ?", (reason, gap_id))
    append_event("gap_deferred", entity_ref=gap_id, payload={"gap_id": gap_id, "reason": reason, "reviewers": ["reviewer-1", "reviewer-2"]}, actor="kb_grow")
    print(f"deferred: {gap_id}")


def mit_search(query: str, limit: int) -> tuple[str, list[dict]]:
    """MIT検索CLIだけを呼び、返却断片から確認可能な証拠候補を抽出する。"""
    result = subprocess.run(
        [sys.executable, str(ROOT / "mitocw_rag.py"), "search", query, "--limit", str(limit)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = result.stdout
    pattern = re.compile(
        r"--- SOURCE \d+ \[(?P<source_id>mitocw:[^\]]+)\] ---\n"
        r"TITLE: (?P<title>[^\n]+)\nURL: (?P<url>[^\n]+)\nVIDEO_ID: (?P<video_id>[^\n]+)\n\n"
        r"(?P<quote>.*?)(?=\n+--- SOURCE |\Z)",
        re.DOTALL,
    )
    records = []
    for match in pattern.finditer(output):
        quote = match.group("quote").strip()
        url = match.group("url").strip()
        video_id = match.group("video_id").strip()
        # URLと取得断片が実際に存在する場合だけ、verified evidenceとして扱う。
        if quote and url.startswith("http") and video_id:
            records.append({
                "source_id": match.group("source_id"),
                "title": match.group("title").strip(),
                "url": url,
                "video_id": video_id,
                "quote": quote,
            })
    return output, records


def collect_evidence(plan_path: Path, max_sources: int, dry_run: bool) -> None:
    """計画対象に、MIT検索断片の証拠台帳を付ける。"""
    if not plan_path.exists():
        raise SystemExit(f"plan not found: {plan_path}")
    if max_sources < 1 or max_sources > 2:
        raise SystemExit("--max-sources は1または2にしてください")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    recorded = 0
    skipped = 0
    for item in plan.get("items", []):
        action = item.get("recommended_action")
        if action not in ("review_existing", "triage_retrieval"):
            skipped += 1
            continue
        cards = item.get("related_cards", [])
        query = item.get("external_query")
        if action == "review_existing":
            if len(cards) != 1:
                skipped += 1
                continue
            query = card_english_query(cards[0])
        if not query:
            print(f"skip {item['gap_id']}: 英語aliasがない")
            skipped += 1
            continue
        if dry_run:
            print(f"would search {item['gap_id']}: {query} (max={max_sources})")
            continue
        output, records = mit_search(query, max_sources)
        output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()
        append_event(
            "mit_search_run",
            entity_ref=item["gap_id"],
            payload={"gap_id": item["gap_id"], "query": query, "plan_id": plan["plan_id"], "source_ids": [r["source_id"] for r in records]},
            actor="kb_grow",
        )
        with db() as connection:
            for source in records:
                evidence_id = stable_id("ev", item["gap_id"], source["source_id"], output_hash)
                before = connection.execute("SELECT 1 FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
                connection.execute("""
                    INSERT OR IGNORE INTO evidence(evidence_id, gap_id, source_id, title, url, video_id, quote, search_output_hash, verified, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (evidence_id, item["gap_id"], source["source_id"], source["title"], source["url"], source["video_id"], source["quote"], output_hash, 1, now()))
                if not before:
                    append_event(
                        "evidence_recorded",
                        entity_ref=evidence_id,
                        payload={"gap_id": item["gap_id"], "source_id": source["source_id"], "url": source["url"], "verified": True},
                        actor="kb_grow",
                    )
                    recorded += 1
            # 検索済みの穴を次回計画に再投入しない。根拠があれば人間確認待ち、
            # なければ検索語見直し待ちとして保持する。
            connection.execute(
                "UPDATE gap SET status = ? WHERE gap_id = ?",
                ("acquire" if records else "defer", item["gap_id"]),
            )
        print(f"{item['gap_id']}: query={query} / evidence={len(records)}")
    print(f"evidence collection complete: recorded={recorded}, skipped={skipped}, network calls=0")


def write_proposals(plan_path: Path, dry_run: bool) -> None:
    """既存草案を上書きせず、確認済み検索断片をレビュー提案として保存する。"""
    if not plan_path.exists():
        raise SystemExit(f"plan not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    PROPOSALS.mkdir(parents=True, exist_ok=True)
    written = 0
    with db() as connection:
        for item in plan.get("items", []):
            if item.get("recommended_action") != "review_existing":
                continue
            card_ids = item.get("related_cards", [])
            if len(card_ids) != 1:
                continue
            evidence = connection.execute("""
                SELECT evidence_id, source_id, title, url, video_id, quote
                FROM evidence WHERE gap_id = ? AND verified = 1 ORDER BY evidence_id
            """, (item["gap_id"],)).fetchall()
            if not evidence:
                print(f"skip {item['gap_id']}: verified evidenceなし")
                continue
            card_id = card_ids[0]
            filename = f"{card_id}_{item['gap_id']}.md"
            path = PROPOSALS / filename
            siblings = connection.execute("""
                SELECT g.gap_id, q.text
                FROM gap g JOIN question q ON q.question_id = g.question_id
                WHERE g.gap_kind = 'existing_unreviewed'
                  AND g.status IN ('review_existing', 'planned', 'acquire')
                  AND g.related_cards = ?
                ORDER BY g.created_at
            """, (json.dumps([card_id]),)).fetchall()
            if path.exists():
                print(f"exists: {path.relative_to(ROOT)}")
                for sibling in siblings:
                    connection.execute("UPDATE gap SET status = 'processed' WHERE gap_id = ?", (sibling["gap_id"],))
                continue
            lines = [
                "---",
                "kind: existing_card_evidence_proposal",
                "status: review_required",
                f"card_id: \"{card_id}\"",
                f"gap_id: \"{item['gap_id']}\"",
                f"plan_id: \"{plan['plan_id']}\"",
                f"origin: \"{item['origin']}\"",
                "generated_by: \"kb_grow\"",
                f"generated_at: \"{now()}\"",
                "---",
                "",
                f"# Evidence proposal for {card_id}",
                "",
                "## Trigger questions",
                "",
                *[f"- {sibling['text']}" for sibling in siblings],
                "",
                "## Review instruction",
                "",
                "既存草案の本文は変更していません。以下はMIT検索で実際に返った断片です。草案の定義・機構・境界条件を支持するか、人間が確認してください。検索断片は候補発見用であり、ここから自動承認しません。",
                "",
                "## Verified search excerpts",
                "",
            ]
            for source in evidence:
                lines.extend([
                    f"### {source['evidence_id']} — {source['title']}",
                    "",
                    f"- Source ID: `{source['source_id']}`",
                    f"- Video ID: `{source['video_id']}`",
                    f"- URL: {source['url']}",
                    "",
                    source["quote"],
                    "",
                ])
            if dry_run:
                print(f"would write: {path.relative_to(ROOT)}")
                continue
            path.write_text("\n".join(lines), encoding="utf-8")
            append_event(
                "review_requested",
                entity_ref=card_id,
                payload={"card_id": card_id, "gap_id": item["gap_id"], "proposal_path": str(path.relative_to(ROOT))},
                actor="kb_grow",
            )
            for sibling in siblings:
                connection.execute("UPDATE gap SET status = 'processed' WHERE gap_id = ?", (sibling["gap_id"],))
            connection.execute("UPDATE gap SET status = 'processed' WHERE gap_id = ?", (item["gap_id"],))
            written += 1
            print(f"proposal: {path.relative_to(ROOT)}")
    print(f"proposal generation complete: written={written}")


def seed_world_questions() -> None:
    """現実起点の探索質問をsyntheticとして登録する。カードや証拠は作らない。"""
    items = yaml.safe_load(WORLD_SEEDS.read_text(encoding="utf-8"))
    added = 0
    with db() as connection:
        for item in items:
            text, query = item["question"].strip(), item["external_query"].strip()
            if not 2 <= len(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", query)) <= 5:
                raise SystemExit(f"invalid external_query: {query}")
            question_id = stable_id("q", normalize(text), "synthetic")
            gap_id = stable_id("gap", question_id)
            exists = connection.execute("SELECT 1 FROM question WHERE question_id = ?", (question_id,)).fetchone()
            connection.execute("""
                INSERT OR IGNORE INTO question(question_id, text, origin, generation_depth, root_id, parent_ids, status, created_at, external_query)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (question_id, text, "synthetic", 1, question_id, "[]", "gap", now(), query))
            connection.execute("""
                INSERT OR IGNORE INTO gap(gap_id, question_id, source_event_id, intent_key, gap_kind, status, reason, related_cards, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (gap_id, question_id, f"seed:{question_id}", stable_id("intent", normalize(text)), "concept_gap", "new", "自己生成の現実起点探索質問。MIT根拠を得るまで新規概念とは扱わない。", "[]", now()))
            if not exists:
                append_event("question_generated", entity_ref=question_id, payload={"question_id": question_id, "origin": "synthetic", "depth": 1, "external_query": query}, actor="kb_grow")
                added += 1
    print(f"world seeds registered: {added}/{len(items)}")


def classify_gap(question: str, titles: dict[str, str]) -> tuple[str, str, list[str]]:
    matched = [card_id for card_id, title in titles.items() if title and title.casefold() in question.casefold()]
    if matched:
        return (
            "existing_unreviewed",
            "既存の未承認草案への明確な言及がある。新カードではなくレビューまたは根拠補強へ送る。",
            sorted(matched),
        )
    return (
        "retrieval_miss",
        "既存カードとの明確な一致を確認できない。新概念とは断定せず、索引・別名・検索語を先に確認する。",
        [],
    )


def origin_from_actor(actor: str) -> str:
    if actor == "synthetic_self_amplification":
        return "synthetic"
    if actor == "user":
        return "human_probe"
    return "legacy_unknown"


def ingest_gap_events() -> tuple[int, int]:
    """既存イベントを冪等に投影する。`event`表には一切書かない。"""
    if not STATE_DB.exists():
        raise SystemExit(f"state DB not found: {STATE_DB}")
    titles = card_titles()
    inserted_questions = 0
    inserted_gaps = 0
    source = sqlite3.connect(STATE_DB)
    source.row_factory = sqlite3.Row
    events = source.execute("""
        SELECT event_id, payload, occurred_at, actor
        FROM event
        WHERE event_type = 'query_gap_detected'
        ORDER BY occurred_at, event_id
    """).fetchall()
    with db() as target:
        for event in events:
            payload = json.loads(event["payload"])
            text = str(payload.get("query", "")).strip()
            if not text:
                continue
            origin = origin_from_actor(event["actor"])
            question_id = stable_id("q", normalize(text), origin)
            root_id = question_id
            question_before = target.execute("SELECT 1 FROM question WHERE question_id = ?", (question_id,)).fetchone()
            target.execute("""
                INSERT OR IGNORE INTO question(question_id, text, origin, generation_depth, root_id, parent_ids, status, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (question_id, text, origin, 1 if origin == "synthetic" else 0, root_id, "[]", "gap", event["occurred_at"]))
            if not question_before:
                inserted_questions += 1

            kind, reason, related_cards = classify_gap(text, titles)
            status = "review_existing" if kind == "existing_unreviewed" else "new"
            gap_id = stable_id("gap", event["event_id"])
            gap_before = target.execute("SELECT 1 FROM gap WHERE gap_id = ?", (gap_id,)).fetchone()
            target.execute("""
                INSERT OR IGNORE INTO gap(gap_id, question_id, source_event_id, intent_key, gap_kind, status, reason, related_cards, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (gap_id, question_id, event["event_id"], stable_id("intent", normalize(text)), kind, status, reason, json.dumps(related_cards, ensure_ascii=False), event["occurred_at"]))
            if not gap_before:
                inserted_gaps += 1
    return inserted_questions, inserted_gaps


def make_plan(max_gaps: int) -> Path:
    """外部通信を含まない、決定的な実行計画をJSONとして固定する。"""
    if max_gaps < 1:
        raise SystemExit("--max-gaps は1以上にしてください")
    with db() as connection:
        rows = connection.execute("""
            SELECT g.*, q.text, q.origin, q.generation_depth, q.root_id, q.external_query
            FROM gap g JOIN question q ON q.question_id = g.question_id
            WHERE g.status IN ('new', 'review_existing')
            ORDER BY CASE q.origin WHEN 'observed_use' THEN 0 WHEN 'human_probe' THEN 1 WHEN 'synthetic' THEN 2 ELSE 3 END,
                     CASE g.gap_kind WHEN 'concept_gap' THEN 0 WHEN 'existing_unreviewed' THEN 1 ELSE 2 END,
                     g.created_at, g.gap_id
            LIMIT ?
        """, (max_gaps * 20,)).fetchall()
        selected = []
        selected_cards: set[str] = set()
        for row in rows:
            related_cards = json.loads(row["related_cards"])
            if row["gap_kind"] == "existing_unreviewed" and related_cards:
                if related_cards[0] in selected_cards:
                    continue
                selected_cards.add(related_cards[0])
            selected.append({
                "gap_id": row["gap_id"],
                "question_id": row["question_id"],
                "question": row["text"],
                "origin": row["origin"],
                "generation_depth": row["generation_depth"],
                "root_id": row["root_id"],
                "gap_kind": row["gap_kind"],
                "recommended_action": "review_existing" if row["gap_kind"] == "existing_unreviewed" else "triage_retrieval",
                "reason": row["reason"],
                "related_cards": related_cards,
                "external_query": row["external_query"],
            })
            if len(selected) >= max_gaps:
                break

        payload = {
            "schema_version": 1,
            "created_at": now(),
            "offline": True,
            "network_allowed": False,
            "llm_allowed": False,
            "limits": {"max_roots": max_gaps, "max_generation_depth": 2, "max_new_cards": 0},
            "items": selected,
        }
        input_hash = hashlib.sha256(json.dumps(selected, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        plan_id = f"plan_{input_hash[:12]}"
        payload["plan_id"] = plan_id
        payload["input_hash"] = input_hash
        PLANS.mkdir(parents=True, exist_ok=True)
        path = PLANS / f"{plan_id}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            connection.execute("INSERT OR IGNORE INTO growth_plan(plan_id, path, input_hash, created_at, status) VALUES (?,?,?,?,?)", (plan_id, str(path.relative_to(ROOT)), input_hash, payload["created_at"], "planned"))
        for item in selected:
            connection.execute("UPDATE gap SET status = 'planned' WHERE gap_id = ?", (item["gap_id"],))
    print(f"plan: {path.relative_to(ROOT)} / items: {len(selected)} / network calls: 0 / LLM calls: 0")
    return path


def list_plans() -> None:
    with db() as connection:
        rows = connection.execute("SELECT plan_id, path, created_at, status FROM growth_plan ORDER BY created_at DESC").fetchall()
    if not rows:
        print("plans: none")
        return
    for row in rows:
        print(f"{row['plan_id']}  {row['status']:9s}  {row['path']}")


def review_list() -> None:
    """既存草案のうち、質問の穴からレビュー対象になったものを表示する。"""
    counts: dict[str, int] = {}
    with db() as connection:
        rows = connection.execute("SELECT related_cards FROM gap WHERE status IN ('review_existing', 'planned')").fetchall()
    for row in rows:
        for card_id in json.loads(row["related_cards"]):
            counts[card_id] = counts.get(card_id, 0) + 1
    if not counts:
        print("review queue: none")
        return
    graph = load_graph()
    for card_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        card = graph.get(card_id, {})
        print(f"{card_id}  gaps={count:3d}  {card.get('title', 'missing')}  {card.get('path', 'missing')}")


def review_show(card_id: str) -> None:
    """承認はせず、レビューに必要な草案と関連する問いだけを表示する。"""
    graph = load_graph()
    card = graph.get(card_id)
    if not card:
        raise SystemExit(f"card not found: {card_id}")
    with db() as connection:
        rows = connection.execute("""
            SELECT q.text, q.origin, g.gap_kind, g.reason
            FROM gap g JOIN question q ON q.question_id = g.question_id
            WHERE instr(g.related_cards, ?) > 0
            ORDER BY g.created_at
        """, (card_id,)).fetchall()
    print(f"{card_id}: {card['title']}")
    print(f"status: {card['status']}")
    print(f"path: {card['path']}")
    print("related questions:")
    for row in rows:
        print(f"  [{row['origin']}/{row['gap_kind']}] {row['text']}")
        print(f"    {row['reason']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="根拠付き知識成長の計画器")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="growth投影DBを初期化")
    plan = commands.add_parser("plan", help="既存の穴からオフライン計画を固定")
    plan.add_argument("--from-events", action="store_true", required=True)
    plan.add_argument("--offline", action="store_true", required=True)
    plan.add_argument("--max-gaps", type=int, default=3)
    commands.add_parser("plans", help="作成済み計画を一覧")
    commands.add_parser("route-duplicates", help="既存草案と明確に重なる探索をレビューへ戻す")
    commands.add_parser("reconcile-plans", help="旧計画で残ったplanned状態を証拠台帳から再分類")
    draft = commands.add_parser("mark-draft-created", help="生成済み草案に対応する探索穴を閉じる")
    draft.add_argument("--gap", required=True)
    draft.add_argument("--card", required=True)
    route = commands.add_parser("route-to-card", help="候補を既存草案の根拠レビューへ戻す")
    route.add_argument("--gap", required=True)
    route.add_argument("--card", required=True)
    route.add_argument("--reason", required=True)
    defer = commands.add_parser("defer-gap", help="根拠不足の候補を理由付きで保留")
    defer.add_argument("--gap", required=True)
    defer.add_argument("--reason", required=True)
    evidence = commands.add_parser("evidence", help="計画対象のMIT検索断片を証拠台帳へ記録")
    evidence.add_argument("--plan", required=True, type=Path)
    evidence.add_argument("--max-sources", type=int, default=2)
    evidence.add_argument("--dry-run", action="store_true")
    proposal = commands.add_parser("propose", help="既存草案の根拠レビュー提案を生成")
    proposal.add_argument("--plan", required=True, type=Path)
    proposal.add_argument("--dry-run", action="store_true")
    commands.add_parser("seed-world", help="現実起点の探索質問を登録")
    review = commands.add_parser("review", help="既存草案のレビュー待ち一覧")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_commands.add_parser("list")
    show = review_commands.add_parser("show")
    show.add_argument("card_id")
    args = parser.parse_args()

    if args.command == "migrate":
        migrate()
    elif args.command == "route-duplicates":
        migrate()
        route_known_duplicates()
    elif args.command == "reconcile-plans":
        migrate()
        reconcile_planned_gaps()
    elif args.command == "mark-draft-created":
        migrate()
        mark_draft_created(args.gap, args.card)
    elif args.command == "route-to-card":
        migrate()
        route_to_existing_card(args.gap, args.card, args.reason)
    elif args.command == "defer-gap":
        migrate()
        defer_gap(args.gap, args.reason)
    elif args.command == "plan":
        migrate()
        questions, gaps = ingest_gap_events()
        print(f"ingested: questions={questions}, gaps={gaps}")
        make_plan(args.max_gaps)
    elif args.command == "plans":
        migrate()
        list_plans()
    elif args.command == "evidence":
        migrate()
        collect_evidence(args.plan, args.max_sources, args.dry_run)
    elif args.command == "propose":
        migrate()
        write_proposals(args.plan, args.dry_run)
    elif args.command == "seed-world":
        migrate()
        seed_world_questions()
    else:
        migrate()
        if args.review_command == "list":
            review_list()
        else:
            review_show(args.card_id)
