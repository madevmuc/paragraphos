"""Test bootstrap: expose hyphenated dir as importable package root."""
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent  # scripts/paragraphos/
sys.path.insert(0, str(PKG_ROOT))
