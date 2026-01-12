#!/usr/bin/env python3
"""
SARAISE Raw SQL Tenant Filter Linter

This script checks for raw SQL statements that may be missing tenant_id
filtering, which could lead to cross-tenant data leakage.

Rule: SARAISE-33006
Authority: saraise-documentation/rules/agent-rules/33-tenant-isolation-enforcement.md

Usage:
    python scripts/lint-tenant-filter.py [--path PATH]

Exit codes:
    0 - All raw SQL includes tenant_id filter (or no raw SQL found)
    1 - One or more raw SQL statements missing tenant_id filter
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns that indicate raw SQL usage
RAW_SQL_PATTERNS = [
    re.compile(r'cursor\.execute\s*\(', re.IGNORECASE),
    re.compile(r'connection\.cursor\s*\(\s*\)', re.IGNORECASE),
    re.compile(r'\.raw\s*\(', re.IGNORECASE),
    re.compile(r'RawSQL\s*\(', re.IGNORECASE),
    re.compile(r'\.extra\s*\(', re.IGNORECASE),
]

# Pattern to detect tenant_id in the query
TENANT_FILTER_PATTERN = re.compile(r'tenant_id', re.IGNORECASE)

# Files/directories to skip
SKIP_PATTERNS = [
    '__pycache__',
    '.git',
    'migrations',
    'tests',  # Tests may intentionally test without tenant filter
    'conftest.py',
    'health.py',  # Health checks use SELECT 1 for connectivity, no tenant filter needed
]

# Patterns that indicate intentionally unfiltered SQL (allow exceptions)
EXCEPTION_PATTERNS = [
    re.compile(r'SARAISE-33006', re.IGNORECASE),  # Documented exception
    re.compile(r'SELECT\s+1', re.IGNORECASE),  # Health check query
    re.compile(r'health\s*check', re.IGNORECASE),  # Health check context
]


def should_skip(filepath: Path) -> bool:
    """Check if file should be skipped."""
    path_str = str(filepath)
    return any(skip in path_str for skip in SKIP_PATTERNS)


def check_file(filepath: Path) -> List[Tuple[int, str, str]]:
    """
    Check a Python file for raw SQL without tenant_id.

    Returns list of (line_number, matched_pattern, context) tuples.
    """
    issues = []

    try:
        content = filepath.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return issues

    lines = content.split('\n')

    for pattern in RAW_SQL_PATTERNS:
        for match in pattern.finditer(content):
            # Get line number
            line_num = content[:match.start()].count('\n') + 1

            # Get surrounding context (5 lines before and after, or until statement end)
            start_line = max(0, line_num - 5)
            end_line = min(len(lines), line_num + 10)
            context = '\n'.join(lines[start_line:end_line])

            # Check if tenant_id is in the context
            if not TENANT_FILTER_PATTERN.search(context):
                # Check for documented exceptions
                has_exception = any(
                    exc_pattern.search(context) for exc_pattern in EXCEPTION_PATTERNS
                )
                if not has_exception:
                    issues.append((
                        line_num,
                        match.group().strip(),
                        lines[line_num - 1].strip() if line_num <= len(lines) else ''
                    ))

    return issues


def main():
    parser = argparse.ArgumentParser(
        description='Check raw SQL statements for tenant_id filtering'
    )
    parser.add_argument(
        '--path',
        type=Path,
        default=Path('backend/src'),
        help='Path to search (default: backend/src)'
    )
    args = parser.parse_args()

    print("🔍 SARAISE Raw SQL Tenant Filter Check")
    print("======================================")
    print("")

    all_issues = []
    files_checked = 0

    if not args.path.exists():
        print(f"⚠️  Path not found: {args.path}")
        print("Skipping check (path may not exist in this context)")
        sys.exit(0)

    for filepath in args.path.rglob('*.py'):
        if should_skip(filepath):
            continue

        files_checked += 1
        issues = check_file(filepath)

        if issues:
            for line_num, pattern, line_content in issues:
                all_issues.append((filepath, line_num, pattern, line_content))

    print(f"Files checked: {files_checked}")
    print("")

    if all_issues:
        print("❌ Raw SQL tenant filter check FAILED")
        print("")
        print("The following raw SQL statements may be missing tenant_id filter:")
        print("")

        for filepath, line_num, pattern, line_content in all_issues:
            print(f"  {filepath}:{line_num}")
            print(f"    Pattern: {pattern}")
            print(f"    Line: {line_content[:80]}...")
            print("")

        print("Action Required:")
        print("  1. Add tenant_id filter to all raw SQL queries")
        print("  2. Or mark as intentionally unfiltered with a comment:")
        print("     # SARAISE-33006: Intentionally unfiltered - [reason]")
        print("")
        print("See: saraise-documentation/rules/agent-rules/33-tenant-isolation-enforcement.md")
        sys.exit(1)

    print("✅ All raw SQL includes tenant_id filter (or no raw SQL found)")
    sys.exit(0)


if __name__ == '__main__':
    main()
