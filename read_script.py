"""
Print the latest (or specified) AnalyticsBot script as plain spoken text.

Usage:
  python read_script.py                        # latest output file
  python read_script.py 2025030313_preview     # specific game/slot
  python read_script.py output/foo_pre.json    # explicit path
"""

import json
import re
import sys
from pathlib import Path

# Force UTF-8 output so Claude's em-dashes and other Unicode print correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OUTPUT_DIR = Path(__file__).parent / "output"

_BEAT_LABELS = re.compile(
    r"^(HOOK|NARRATIVE|TURN|VERDICT|RETURN HOOK)\s*:\s*",
    re.MULTILINE | re.IGNORECASE,
)


def _find_file(arg: str | None) -> Path:
    if arg is None:
        files = sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            print("No output files found in output/")
            sys.exit(1)
        return files[-1]

    p = Path(arg)
    if p.suffix == ".json" and p.exists():
        return p

    # Try as game_id or game_id_slot
    matches = list(OUTPUT_DIR.glob(f"{arg}*.json"))
    if not matches:
        print(f"No output file matching '{arg}' found in output/")
        sys.exit(1)
    return sorted(matches, key=lambda p: p.stat().st_mtime)[-1]


def _clean_script(body: str) -> str:
    # Strip beat labels, collapse blank lines, strip leading/trailing whitespace
    text = _BEAT_LABELS.sub("", body)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(text.split())


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    path = _find_file(arg)
    data = json.loads(path.read_text(encoding="utf-8"))

    slot = data.get("slot", "?").upper()
    away = data.get("away_team", "?")
    home = data.get("home_team", "?")
    snap = data.get("model_snapshot", {})
    home_prob = snap.get("home_win_prob", 0)
    away_prob = snap.get("away_win_prob", 0)
    total = snap.get("expected_total", 0)
    cal = snap.get("calibration_version", "?")
    edge_summary = data.get("edge_summary", "")
    hook_visual = data.get("hook_visual", "")

    script = _clean_script(data.get("script_body", ""))
    words = _word_count(script)
    seconds = round(words / 3.0)  # ~3 words/sec speaking pace

    separator = "-" * 60
    print(separator)
    print(f"  {slot} -- {away} @ {home}")
    print(f"  Model: {home} {home_prob:.1%} | {away} {away_prob:.1%} | total {total:.2f} ({cal})")
    print(f"  Edge:  {edge_summary}")
    print(f"  Thumb: {hook_visual}")
    print(f"  Words: {words}  (~{seconds}s at speaking pace)")
    print(separator)
    print()
    print(script)
    print()


if __name__ == "__main__":
    main()
