"""Export the OpenAPI contract; --check detects stale generated artifacts."""

import argparse
import json
from pathlib import Path

from infralens_backend.contract import openapi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"
    rendered = json.dumps(openapi(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(
                "Run uv run --project backend python backend/scripts/export_contract.py"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
