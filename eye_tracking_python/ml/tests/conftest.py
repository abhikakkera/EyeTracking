"""Make the eye_tracking_python project root importable for ml.* tests."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # ml/tests -> ml -> eye_tracking_python
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
