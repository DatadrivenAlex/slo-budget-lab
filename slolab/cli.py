"""Offline report CLI. Exit 1 means an alert fires, 3 means insufficient data."""

import argparse
import json
import sys
from pathlib import Path

from .core import InputError, evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate offline SLO burn-rate snapshots")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(json.loads(args.snapshot.read_text()))
    except (OSError, UnicodeError, json.JSONDecodeError, InputError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return {"clear": 0, "firing": 1, "insufficient_data": 3}[report["state"]]


if __name__ == "__main__":
    raise SystemExit(main())
