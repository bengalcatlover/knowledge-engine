#!/usr/bin/env python3
"""入試問題PDFを知識調査の待ち行列へ取り込む。外部APIや秘密情報は不要。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader
import fitz

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parent
INBOX = ROOT / "exam-inbox"
WORK = ROOT / "work"
EXTRACTIONS = WORK / "extractions"
MANIFEST_PATH = WORK / "manifest.json"
QUEUE_PATH = WORK / "research-queue.json"
TESSERACT = Path(os.environ.get("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
OCR_DATA = ROOT / "ocr-data"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_embedded_text(pdf: Path) -> tuple[str, int]:
    reader = PdfReader(str(pdf))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(f"--- page {index + 1} ---\n{text}" for index, text in enumerate(pages)), len(pages)


def extract_with_ocr(pdf: Path) -> tuple[str, int]:
    if not TESSERACT.exists():
        raise RuntimeError("OCRが必要ですが、Tesseractが見つかりません")
    if not (OCR_DATA / "jpn.traineddata").exists():
        raise RuntimeError("OCRが必要ですが、日本語OCRデータが見つかりません")

    document = fitz.open(pdf)
    pages: list[str] = []
    with tempfile.TemporaryDirectory(prefix="exam-ocr-") as temporary:
        temporary_path = Path(temporary)
        for index, page in enumerate(document):
            image_path = temporary_path / f"page-{index + 1}.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pixmap.save(str(image_path))
            result = subprocess.run(
                [str(TESSERACT), str(image_path), "stdout", "-l", "jpn+eng", "--psm", "6"],
                env={**os.environ, "TESSDATA_PREFIX": str(OCR_DATA)},
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"OCR失敗（{index + 1}ページ）: {result.stderr.strip()}")
            pages.append(result.stdout.strip())
    return "\n\n".join(f"--- page {index + 1} [OCR] ---\n{text}" for index, text in enumerate(pages)), len(pages)


def extract_pdf(pdf: Path) -> tuple[str, int, str]:
    text, pages = extract_embedded_text(pdf)
    # 問題PDFでは、ページごとに50文字未満なら画像PDFとみなす。
    if len(text.replace("--- page", "").strip()) >= pages * 50:
        return text, pages, "embedded_text"
    text, pages = extract_with_ocr(pdf)
    return text, pages, "ocr"


def new_queue_item(pdf: Path, digest: str, extraction_path: Path, pages: int, text: str, extraction_method: str) -> dict:
    return {
        "id": digest[:16],
        "source_pdf": str(pdf),
        "sha256": digest,
        "extraction": str(extraction_path),
        "pages": pages,
        "characters_extracted": len(text),
        "extraction_method": extraction_method,
        "state": "needs_topic_extraction" if text.strip() else "needs_ocr",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "research_rule": "research-policy.md",
        "notes": "AI must derive scientific claims and research queries from the extracted text. Do not use generic web pages or corporate sources.",
    }


def scan() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    EXTRACTIONS.mkdir(parents=True, exist_ok=True)
    manifest = load_json(MANIFEST_PATH, {})
    queue = load_json(QUEUE_PATH, [])
    known_ids = {item["id"] for item in queue}
    added = 0

    for pdf in sorted(INBOX.rglob("*.pdf")):
        digest = sha256(pdf)
        key = str(pdf.relative_to(ROOT))
        if manifest.get(key, {}).get("sha256") == digest:
            continue

        try:
            text, pages, extraction_method = extract_pdf(pdf)
            extraction_path = EXTRACTIONS / f"{digest[:16]}.txt"
            extraction_path.write_text(text, encoding="utf-8")
            item = new_queue_item(pdf, digest, extraction_path, pages, text, extraction_method)
            if item["id"] not in known_ids:
                queue.append(item)
                known_ids.add(item["id"])
                added += 1
            manifest[key] = {
                "sha256": digest,
                "pages": pages,
                "characters_extracted": len(text),
                "extraction_method": extraction_method,
                "extraction": str(extraction_path),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }
            print(f"取り込み: {pdf.name} ({pages}ページ、{len(text)}文字)")
        except Exception as error:
            manifest[key] = {
                "sha256": digest,
                "error": str(error),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }
            print(f"失敗: {pdf.name}: {error}")

    save_json(MANIFEST_PATH, manifest)
    save_json(QUEUE_PATH, queue)
    print(f"完了: 新規・更新PDF {added}件。待ち行列は {len(queue)}件。")


def status() -> None:
    queue = load_json(QUEUE_PATH, [])
    counts: dict[str, int] = {}
    for item in queue:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    print(json.dumps({"inbox": str(INBOX), "queue": counts, "total": len(queue)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["scan", "status"])
    args = parser.parse_args()
    {"scan": scan, "status": status}[args.command]()
