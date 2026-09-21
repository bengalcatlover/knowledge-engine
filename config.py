"""環境変数の一括読み込み。全モジュールの先頭で import config する。"""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
