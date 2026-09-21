#!/usr/bin/env python3
"""知識基盤の統治ツール: イベントログ・ライフサイクル・共活性化記録

使い方:
    python kb.py init                              # DB初期化
    python kb.py log-query "クエリ" K-0001,K-0003   # クエリログ記録
    python kb.py promote K-0034                    # candidate → accepted
    python kb.py deprecate K-0012                  # accepted → deprecated
    python kb.py status K-0001                     # カード状態表示
    python kb.py events [--limit 20]               # イベント一覧
    python kb.py coactivation [--min-freq 3]       # 実利用ログの共活性化分析
    python kb.py coactivation --include-synthetic  # 自己生成ログも確認（候補根拠にはしない）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config  # noqa: F401

ROOT = Path(__file__).resolve().parent
STATE_DB = ROOT / "work" / "state.sqlite3"
CONCEPTS_INBOX = ROOT / "concepts" / "_inbox"
CONCEPTS_ACCEPTED = ROOT / "concepts"


# ═══════════════════════════════════════════
# DB初期化
# ═══════════════════════════════════════════

def get_state_db() -> sqlite3.Connection:
    STATE_DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE_DB)
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db() -> None:
    db = get_state_db()

    # 追記専用イベントログ
    db.execute("""
        CREATE TABLE IF NOT EXISTS event (
            event_id   TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            entity_ref TEXT,
            payload    TEXT NOT NULL CHECK(json_valid(payload)),
            occurred_at TEXT NOT NULL,
            actor      TEXT NOT NULL DEFAULT 'system'
        )
    """)

    # 追記専用トリガー
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS event_no_update
        BEFORE UPDATE ON event
        BEGIN
            SELECT RAISE(ABORT, 'event table is append-only');
        END
    """)
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS event_no_delete
        BEFORE DELETE ON event
        BEGIN
            SELECT RAISE(ABORT, 'event table is append-only');
        END
    """)

    # 共活性化テーブル（クエリごとにどのカードが活性化されたか）
    db.execute("""
        CREATE TABLE IF NOT EXISTS activation (
            query_id   TEXT NOT NULL,
            card_id    TEXT NOT NULL,
            rank       INTEGER,
            score      REAL,
            context    TEXT,
            PRIMARY KEY(query_id, card_id)
        )
    """)

    db.commit()
    print(f"DB初期化完了: {STATE_DB}")


# ═══════════════════════════════════════════
# Git SHA取得
# ═══════════════════════════════════════════

def git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(ROOT.parent),
            timeout=5,
        )
        return result.stdout.strip()[:12] if result.returncode == 0 else "no-git"
    except Exception:
        return "no-git"


# ═══════════════════════════════════════════
# イベント記録
# ═══════════════════════════════════════════

def append_event(
    event_type: str,
    entity_ref: str | None = None,
    payload: dict | None = None,
    actor: str = "system",
) -> str:
    db = get_state_db()
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    payload = payload or {}
    payload["git_sha"] = git_head()

    db.execute(
        "INSERT INTO event(event_id, event_type, entity_ref, payload, occurred_at, actor) VALUES (?,?,?,?,?,?)",
        (event_id, event_type, entity_ref, json.dumps(payload, ensure_ascii=False), now, actor),
    )
    db.commit()
    return event_id


# ═══════════════════════════════════════════
# クエリログ + 共活性化記録
# ═══════════════════════════════════════════

def log_query(
    query: str,
    activated_cards: list[str],
    context: str = "",
    actor: str = "system",
    searcher: str = "unknown",
    scores: list[float] | None = None,
) -> str:
    """検索結果を記録。共活性化テーブルにも書く。

    Parameters
    ----------
    searcher : 検索器名 (search_engine / brain_rag / mitocw_rag)
    scores   : 各カードのスコア (activated_cardsと同順)
    """
    query_id = f"q_{uuid.uuid4().hex[:12]}"

    event_id = append_event(
        event_type="query_served",
        payload={
            "query_id": query_id,
            "query": query,
            "activated_cards": activated_cards,
            "context": context,
            "searcher": searcher,
            "scores": scores,
        },
        actor=actor,
    )

    db = get_state_db()
    for rank, card_id in enumerate(activated_cards):
        s = scores[rank] if scores and rank < len(scores) else None
        db.execute(
            "INSERT OR IGNORE INTO activation(query_id, card_id, rank, score, context) VALUES (?,?,?,?,?)",
            (query_id, card_id, rank, s, context),
        )
    db.commit()

    print(f"記録: {query_id} [{searcher}] → {activated_cards}")
    return query_id


# ═══════════════════════════════════════════
# ライフサイクル管理
# ═══════════════════════════════════════════

def find_card_path(card_id: str) -> Path | None:
    """カードIDからファイルパスを探す。"""
    for directory in [CONCEPTS_INBOX, CONCEPTS_ACCEPTED]:
        if not directory.exists():
            continue
        for path in directory.rglob("*.md"):
            if card_id in path.stem:
                return path
    return None


def read_card_status(card_path: Path) -> str:
    """カードのstatusをfrontmatterから読む。"""
    text = card_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'^status:\s*["\']?(\w+)', text, re.MULTILINE)
    return m.group(1) if m else "unknown"


def update_card_status(card_path: Path, new_status: str) -> None:
    """カードのstatusを書き換える。"""
    text = card_path.read_text(encoding="utf-8", errors="replace")
    updated = re.sub(
        r'^(status:\s*)["\']?\w+["\']?',
        f'\\1"{new_status}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    card_path.write_text(updated, encoding="utf-8")


def promote_card(card_id: str, actor: str = "user") -> None:
    """_inbox/ → concepts/ に昇格（candidate → accepted）。"""
    card_path = find_card_path(card_id)
    if not card_path:
        print(f"カード {card_id} が見つかりません")
        return

    current_status = read_card_status(card_path)
    if current_status not in ("draft", "candidate"):
        print(f"{card_id} のステータスは {current_status} です。draft/candidateのみ昇格可能。")
        return

    # ステータスを accepted に変更
    update_card_status(card_path, "accepted")

    # _inbox/ にある場合は concepts/ 直下へ移動
    if "_inbox" in str(card_path):
        dest = CONCEPTS_ACCEPTED / card_path.name
        shutil.move(str(card_path), str(dest))
        print(f"移動: {card_path.relative_to(ROOT)} → {dest.relative_to(ROOT)}")
        card_path = dest

    # authorship を user に変更
    text = card_path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r'^(authorship:\s*)["\']?\w+["\']?', f'\\1"user"', text, count=1, flags=re.MULTILINE)
    card_path.write_text(text, encoding="utf-8")

    append_event(
        event_type="card_promoted",
        entity_ref=card_id,
        payload={"from_status": current_status, "to_status": "accepted", "path": str(card_path.relative_to(ROOT))},
        actor=actor,
    )
    print(f"昇格完了: {card_id} ({current_status} → accepted)")


def deprecate_card(card_id: str, actor: str = "user") -> None:
    """カードを deprecated にする。"""
    card_path = find_card_path(card_id)
    if not card_path:
        print(f"カード {card_id} が見つかりません")
        return

    current_status = read_card_status(card_path)
    update_card_status(card_path, "deprecated")

    append_event(
        event_type="card_deprecated",
        entity_ref=card_id,
        payload={"from_status": current_status, "to_status": "deprecated"},
        actor=actor,
    )
    print(f"非推奨化: {card_id} ({current_status} → deprecated)")


def show_card_status(card_id: str) -> None:
    """カードの状態を表示。"""
    card_path = find_card_path(card_id)
    if not card_path:
        print(f"カード {card_id} が見つかりません")
        return

    status = read_card_status(card_path)
    print(f"カード: {card_id}")
    print(f"パス:   {card_path.relative_to(ROOT)}")
    print(f"状態:   {status}")

    # イベント履歴
    db = get_state_db()
    rows = db.execute(
        "SELECT event_type, occurred_at, actor FROM event WHERE entity_ref = ? ORDER BY occurred_at",
        (card_id,),
    ).fetchall()
    if rows:
        print("履歴:")
        for etype, ts, actor in rows:
            print(f"  {ts[:19]}  {etype}  by {actor}")


# ═══════════════════════════════════════════
# イベント一覧
# ═══════════════════════════════════════════

def list_events(limit: int = 20) -> None:
    db = get_state_db()
    rows = db.execute(
        "SELECT event_id, event_type, entity_ref, occurred_at, actor FROM event ORDER BY occurred_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        print("イベントなし")
        return
    for eid, etype, eref, ts, actor in rows:
        ref_str = f" [{eref}]" if eref else ""
        print(f"  {ts[:19]}  {etype:20s}{ref_str}  ({actor})")


# ═══════════════════════════════════════════
# 共活性化分析
# ═══════════════════════════════════════════

def coactivation_analysis(min_freq: int = 3, include_synthetic: bool = False) -> None:
    """頻出するカードペアを抽出。

    自己生成質問は検索品質の検査・知識の穴の発見には使うが、利用需要や
    Composition候補の根拠にはしない。必要なときだけ明示フラグで表示する。
    """
    db = get_state_db()
    synthetic_filter = "" if include_synthetic else """
        AND NOT EXISTS (
            SELECT 1 FROM event e
            WHERE e.event_type = 'query_served'
              AND json_extract(e.payload, '$.query_id') = a1.query_id
              AND e.actor = 'synthetic_self_amplification'
        )
    """
    rows = db.execute(f"""
        SELECT a1.card_id, a2.card_id, COUNT(DISTINCT a1.query_id) AS freq
        FROM activation a1
        JOIN activation a2
          ON a1.query_id = a2.query_id AND a1.card_id < a2.card_id
        WHERE 1 = 1 {synthetic_filter}
        GROUP BY a1.card_id, a2.card_id
        HAVING freq >= ?
        ORDER BY freq DESC
        LIMIT 30
    """, (min_freq,)).fetchall()

    if not rows:
        print(f"共活性化ペア（頻度>={min_freq}）: なし。ログ蓄積を待ってください。")
        return

    print(f"共活性化ペア（頻度>={min_freq}）:")
    for c1, c2, freq in rows:
        print(f"  {freq:3d}回  {c1} × {c2}")




# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知識基盤 統治ツール")
    cmds = parser.add_subparsers(dest="command", required=True)

    cmds.add_parser("init", help="DB初期化")

    lq = cmds.add_parser("log-query", help="クエリログ記録")
    lq.add_argument("query")
    lq.add_argument("cards", help="カードID（カンマ区切り）")
    lq.add_argument("--context", default="")
    lq.add_argument("--actor", default="system", help="ログの出所（例: synthetic_campaign）")

    pr = cmds.add_parser("promote", help="カード昇格")
    pr.add_argument("card_id")
    pr.add_argument("--actor", default="user")

    dp = cmds.add_parser("deprecate", help="カード非推奨化")
    dp.add_argument("card_id")

    st = cmds.add_parser("status", help="カード状態表示")
    st.add_argument("card_id")

    ev = cmds.add_parser("events", help="イベント一覧")
    ev.add_argument("--limit", type=int, default=20)

    co = cmds.add_parser("coactivation", help="共活性化分析")
    co.add_argument("--min-freq", type=int, default=3)
    co.add_argument("--include-synthetic", action="store_true")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
    elif args.command == "log-query":
        cards = [c.strip() for c in args.cards.split(",")]
        log_query(args.query, cards, args.context, args.actor)
    elif args.command == "promote":
        promote_card(args.card_id, args.actor)
    elif args.command == "deprecate":
        deprecate_card(args.card_id)
    elif args.command == "status":
        show_card_status(args.card_id)
    elif args.command == "events":
        list_events(args.limit)
    elif args.command == "coactivation":
        coactivation_analysis(args.min_freq, args.include_synthetic)
