#!/usr/bin/env python3
"""
Generate a minimal codebase schema map with functions, classes, imports, and vars.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


FILE_TYPE_MAP = {
    ".py": "python",
    ".sh": "script",
    ".yml": "config",
    ".yaml": "config",
    ".json": "config",
    ".js": "script",
    ".md": "markdown",
    ".txt": "text",
}


def classify_file(path: str) -> str:
    _, ext = os.path.splitext(path)
    return FILE_TYPE_MAP.get(ext.lower(), "other")


def collect_packages(root: str) -> Set[str]:
    packages: Set[str] = set()
    for dirpath, _, filenames in os.walk(root):
        if "__pycache__" in dirpath.split(os.sep):
            continue
        if "__init__.py" in filenames:
            rel = os.path.relpath(dirpath, root)
            pkg = rel.replace(os.sep, ".")
            packages.add(pkg)
            packages.add(pkg.split(".")[0])
    return packages


def _classify_import(module: Optional[str], level: int, internal_roots: Set[str]) -> str:
    if level and level > 0:
        return "internal"
    if not module:
        return "stdlib"
    root = module.split(".")[0]
    if root in internal_roots:
        return "internal"
    if root in getattr(sys_modules(), "stdlib", set()):
        return "stdlib"
    return "third_party"


def sys_modules() -> Any:
    try:
        import sys

        stdlib = getattr(sys, "stdlib_module_names", None)
        return type("StdLib", (), {"stdlib": set(stdlib) if stdlib else set()})
    except Exception:
        return type("StdLib", (), {"stdlib": set()})


def parse_python_file(
    path: str, internal_roots: Set[str]
) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]], List[str], List[str], Optional[str]]:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        source = handle.read()

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return (
            {"stdlib": [], "third_party": [], "internal": []},
            [],
            [],
            [],
            f"SyntaxError: {exc.msg}",
        )

    imports: Dict[str, List[str]] = {"stdlib": [], "third_party": [], "internal": []}
    classes: List[Dict[str, Any]] = []
    functions: List[str] = []
    variables: List[str] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                kind = _classify_import(alias.name, 0, internal_roots)
                imports[kind].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            kind = _classify_import(node.module, node.level, internal_roots)
            module_name = node.module or ""
            imports[kind].append(module_name)
        elif isinstance(node, ast.ClassDef):
            methods = [
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({"name": node.name, "methods": methods})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    variables.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                variables.append(node.target.id)

    for key in imports:
        imports[key] = sorted(set(filter(None, imports[key])))

    return imports, classes, functions, sorted(set(variables)), None


def build_schema(root: str, include_env: bool) -> Dict[str, Any]:
    internal_roots = collect_packages(root)
    files: List[Dict[str, Any]] = []

    for dirpath, _, filenames in os.walk(root):
        if "__pycache__" in dirpath.split(os.sep):
            continue
        for filename in filenames:
            if filename.endswith(".pyc"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root)
            file_type = classify_file(rel)

            record: Dict[str, Any] = {"path": rel, "type": file_type}
            if file_type == "python":
                (
                    imports,
                    classes,
                    functions,
                    variables,
                    parse_error,
                ) = parse_python_file(
                    path, internal_roots
                )
                record.update(
                    {
                        "imports": imports,
                        "classes": classes,
                        "functions": functions,
                        "variables": variables,
                    }
                )
                if parse_error:
                    record["parse_error"] = parse_error
            files.append(record)

    schema: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": root,
        "scope": "all_folders",
        "files": sorted(files, key=lambda item: item["path"]),
    }

    if include_env:
        schema["api_key_files"] = [
            {
                "path": ".env",
                "type": "config",
                "purpose": "API key and secret storage",
            }
        ]

    return schema


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate minimal codebase schema map."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    parser.add_argument(
        "--out",
        default="codebase_minimal_schema.json",
        help="Output JSON path (default: codebase_minimal_schema.json).",
    )
    parser.add_argument(
        "--include-env",
        action="store_true",
        help="Include .env as API key file entry.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    schema = build_schema(root, include_env=args.include_env)

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(schema, handle, indent=2, sort_keys=False, ensure_ascii=True)
        handle.write("\n")

    print(f"Wrote minimal schema to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
