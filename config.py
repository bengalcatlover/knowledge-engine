"""環境変数の一括読み込み。全モジュールの先頭で import config する。"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# ── UTF-8 stdout（Windows対策）──
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 共通LLM設定 ──
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_SECONDARY_KEY = os.environ.get("LLM_SECONDARY_KEY", "")
WORKER_MODEL = os.environ.get("LLM_WORKER_MODEL", "")
