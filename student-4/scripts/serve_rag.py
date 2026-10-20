"""Compatibility entry point; implementation moved to scripts/orders/."""
from pathlib import Path
import runpy
import sys
_target = Path(__file__).resolve().parents[2] / "scripts/orders" / Path(__file__).name
sys.path.insert(0, str(_target.parent))
globals().update(runpy.run_path(str(_target), run_name=__name__))
