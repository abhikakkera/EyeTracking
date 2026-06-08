"""
Report service — generates a simple, self-contained HTML report for a session
and provides a helper to open the local results folder in the OS file browser.

The HTML report is intentionally plain and research-oriented. It contains NO
medical interpretation — only task performance metrics and tracking quality.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from backend.paths import DISCLAIMER, get_sessions_dir

logger = logging.getLogger(__name__)


def build_html_report(summary: Dict[str, Any], sessions_dir: Optional[Path] = None) -> Path:
    """Write <sid>_report.html next to the other exports and return its path."""
    d = Path(sessions_dir) if sessions_dir else get_sessions_dir()
    sid = summary["session_id"]
    path = d / f"{sid}_report.html"

    metrics_rows = "".join(
        f"<tr><td>{_label(k)}</td><td>{_fmt(v)}</td></tr>"
        for k, v in (summary.get("task_metrics") or {}).items()
    )
    recs = "".join(f"<li>{r}</li>" for r in summary.get("recommendations", []))

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDEYE Session Report — {sid}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; color:#0b1320;
         max-width: 760px; margin: 40px auto; padding: 0 20px; }}
  h1 {{ color:#1b4fd1; margin-bottom:4px; }}
  .sub {{ color:#5b6675; margin-top:0; }}
  .card {{ border:1px solid #e4e9f2; border-radius:14px; padding:20px; margin:18px 0;
           box-shadow: 0 1px 3px rgba(16,40,90,.05); }}
  table {{ width:100%; border-collapse: collapse; }}
  td {{ padding:8px 6px; border-bottom:1px solid #eef2f8; }}
  td:first-child {{ color:#5b6675; }}
  .badge {{ display:inline-block; background:#eaf1ff; color:#1b4fd1; border-radius:999px;
            padding:4px 12px; font-weight:600; font-size:13px; }}
  .disclaimer {{ background:#f6f8fc; border:1px solid #e4e9f2; border-radius:12px;
                 padding:14px 16px; color:#46506a; font-size:13px; }}
</style></head>
<body>
  <h1>PDEYE</h1>
  <p class="sub">Session report — {summary.get('activity_name','')} ({summary.get('technical_task_name','')})</p>
  <div class="card">
    <p><span class="badge">{summary.get('tracking_quality_label','')}</span></p>
    <table>
      <tr><td>Session ID</td><td>{sid}</td></tr>
      <tr><td>Date</td><td>{summary.get('date_time','—')}</td></tr>
      <tr><td>Rounds completed</td><td>{summary.get('rounds_completed','—')}</td></tr>
      <tr><td>Usable eye-tracking data</td><td>{_fmt(summary.get('usable_data_percent'))}%</td></tr>
      <tr><td>Blink count</td><td>{summary.get('blink_count','—')}</td></tr>
      <tr><td>Average response time</td><td>{_fmt(summary.get('average_response_time_ms'))} ms</td></tr>
    </table>
  </div>
  <div class="card"><h3>Activity metrics</h3><table>{metrics_rows}</table></div>
  <div class="card"><h3>Suggestions</h3><ul>{recs}</ul></div>
  <p class="disclaimer">{DISCLAIMER}</p>
</body></html>"""

    path.write_text(html)
    logger.info("Wrote HTML report: %s", path)
    return path


def open_results_folder(sessions_dir: Optional[Path] = None) -> bool:
    """
    Open the local results folder in the OS file browser.
    Returns True on success.  Best-effort; never raises.
    """
    d = str(Path(sessions_dir) if sessions_dir else get_sessions_dir())
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", d])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", d])
        else:
            subprocess.Popen(["xdg-open", d])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not open results folder: %s", exc)
        return False


def _label(key: str) -> str:
    return key.replace("_", " ").replace("percent", "%").capitalize()


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)
