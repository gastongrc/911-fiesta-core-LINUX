#!/usr/bin/env python3
"""
911 Fiesta V7 - Static Import Scanner

Scans the repository using Python AST to detect all import statements.
Produces a JSON report of every module imported, how many times, and where.

Usage:
    python tools/audit/static_import_scan.py [--root /path/to/repo] [--out imports_used.json]
"""
import ast
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


# Known standard-library top-level module names (Python 3.10/3.11).
# We keep a generous set so we can classify imports accurately.
_STDLIB = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "graphlib", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl",
    "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib",
    # common internal aliases
    "_thread", "__future__", "_io", "_collections_abc",
}


def _top_level(module_name: str) -> str:
    """Return the top-level package of a dotted module path."""
    return module_name.split(".")[0]


def scan_file(filepath: str):
    """Parse a single Python file and yield (module_name, alias, lineno)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, alias.asname, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module, None, node.lineno


def scan_directory(root: str, exclude_dirs=None):
    """
    Walk *root* and scan every .py file.

    Returns
    -------
    dict  with keys:
        modules   – {top_level_name: {count, files: [{path, line, full_import}]}}
        stdlib    – set of top-level names that are stdlib
        internal  – set of top-level names that belong to this repo
        third_party – set of top-level names from third-party packages
        files_scanned – list of scanned file paths
    """
    if exclude_dirs is None:
        exclude_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            "env", ".eggs", "*.egg-info", "build", "dist",
            "webapp",  # JS/React — not Python
            "legacy_analyzers",
            "backup_json",
        }

    root_path = Path(root).resolve()

    # Collect internal package names (directories with __init__.py + root-level .py)
    internal_names = set()
    for entry in root_path.iterdir():
        if entry.is_dir() and (entry / "__init__.py").exists():
            internal_names.add(entry.name)
        if entry.is_file() and entry.suffix == ".py":
            internal_names.add(entry.stem)

    modules: dict = defaultdict(lambda: {"count": 0, "files": []})
    files_scanned: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune excluded dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_dirs and not d.endswith(".egg-info")
        ]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root_path)
            files_scanned.append(rel)

            for mod_name, _alias, lineno in scan_file(full):
                top = _top_level(mod_name)
                modules[top]["count"] += 1
                modules[top]["files"].append({
                    "path": rel,
                    "line": lineno,
                    "full_import": mod_name,
                })

    stdlib = set()
    internal = set()
    third_party = set()

    for name in modules:
        if name in _STDLIB:
            stdlib.add(name)
        elif name in internal_names:
            internal.add(name)
        else:
            third_party.add(name)

    return {
        "modules": dict(modules),
        "stdlib": sorted(stdlib),
        "internal": sorted(internal),
        "third_party": sorted(third_party),
        "files_scanned": sorted(files_scanned),
    }


def build_report(scan_result: dict) -> dict:
    """Structure the scan result into the final JSON report."""
    modules = scan_result["modules"]

    third_party_details = {}
    for name in scan_result["third_party"]:
        info = modules[name]
        third_party_details[name] = {
            "count": info["count"],
            "files": sorted(set(f["path"] for f in info["files"])),
            "import_variants": sorted(set(f["full_import"] for f in info["files"])),
        }

    internal_details = {}
    for name in scan_result["internal"]:
        info = modules[name]
        internal_details[name] = {
            "count": info["count"],
            "files": sorted(set(f["path"] for f in info["files"])),
        }

    return {
        "summary": {
            "total_files_scanned": len(scan_result["files_scanned"]),
            "total_unique_imports": len(modules),
            "stdlib_count": len(scan_result["stdlib"]),
            "internal_count": len(scan_result["internal"]),
            "third_party_count": len(scan_result["third_party"]),
        },
        "third_party": third_party_details,
        "internal": internal_details,
        "stdlib": scan_result["stdlib"],
        "files_scanned": scan_result["files_scanned"],
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Static import scanner for 911 Fiesta V7")
    parser.add_argument("--root", default=None, help="Repository root (default: auto-detect)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout summary")
    args = parser.parse_args()

    if args.root:
        root = args.root
    else:
        # Auto-detect: go up from this script's location
        root = str(Path(__file__).resolve().parents[2])

    scan = scan_directory(root)
    report = build_report(scan)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    if not args.quiet:
        s = report["summary"]
        print(f"Files scanned:      {s['total_files_scanned']}")
        print(f"Unique imports:     {s['total_unique_imports']}")
        print(f"  stdlib:           {s['stdlib_count']}")
        print(f"  internal:         {s['internal_count']}")
        print(f"  third-party:      {s['third_party_count']}")
        print()
        print("Third-party packages detected:")
        for name in sorted(report["third_party"], key=lambda n: report["third_party"][n]["count"], reverse=True):
            info = report["third_party"][name]
            print(f"  {name:30s}  refs={info['count']:3d}  files={len(info['files'])}")

    return report


if __name__ == "__main__":
    main()
