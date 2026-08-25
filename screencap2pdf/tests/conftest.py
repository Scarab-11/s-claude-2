import sys
from pathlib import Path

# tests/ の 1 つ上（s2pdf パッケージがある場所）を import 対象にする
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
