"""Write the deterministic Cycle 42 local API OpenAPI snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_prediction_lab.service.local_api import openapi_schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/generated/cycle_42_local_api_openapi.json"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(openapi_schema(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    output.write_text(content, encoding="utf-8")
    print(
        json.dumps(
            {"path": "cycle_42_local_api_openapi.json", "bytes": len(content.encode("utf-8"))}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
