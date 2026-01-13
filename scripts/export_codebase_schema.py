#!/usr/bin/env python3
"""
Export the canonical codebase schema from codebase_schema.js to a JSON file.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone


def _extract_json(text: str, source_path: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Could not locate JSON object in {source_path}")
    return text[start : end + 1]


def _default_output_path(root: str) -> str:
    return os.path.join(root, "codebase_schema.json")


def export_schema(source_path: str, output_path: str, pretty: bool) -> None:
    with open(source_path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    schema_text = _extract_json(raw, source_path)
    schema = json.loads(schema_text)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        if pretty:
            json.dump(schema, handle, indent=2, sort_keys=False, ensure_ascii=True)
            handle.write("\n")
        else:
            json.dump(schema, handle, separators=(",", ":"), ensure_ascii=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export codebase_schema.js to a JSON file."
    )
    parser.add_argument(
        "--source",
        default="codebase_schema.js",
        help="Path to the canonical schema source (default: codebase_schema.js).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path for the JSON schema (default: codebase_schema.json).",
    )
    parser.add_argument(
        "--minify",
        action="store_true",
        help="Write minified JSON instead of pretty output.",
    )
    parser.add_argument(
        "--timestamped",
        action="store_true",
        help="Append UTC timestamp to the output filename.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = os.getcwd()
    source_path = args.source
    output_path = args.out or _default_output_path(root)

    if args.timestamped:
        base, ext = os.path.splitext(output_path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
        output_path = f"{base}_{stamp}{ext or '.json'}"

    export_schema(source_path, output_path, pretty=not args.minify)
    print(f"Wrote schema to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
