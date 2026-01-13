#!/usr/bin/env python3
"""
Fix relative imports in test files to use absolute imports.

This script converts relative imports like:
    from ..models import Model
    from ..service import Service
    from ..api import ViewSet

To absolute imports like:
    from src.modules.{module_name}.models import Model
    from src.modules.{module_name}.service import Service
    from src.modules.{module_name}.api import ViewSet
"""
import re
import sys
from pathlib import Path


def get_module_path(file_path: Path) -> str:
    """Extract module path from file path."""
    parts = file_path.parts
    if "src" not in parts:
        return None
    
    src_idx = parts.index("src")
    module_parts = parts[src_idx:]
    
    # Remove 'tests' and filename
    module_parts = [p for p in module_parts if p != "tests" and not p.endswith(".py")]
    
    return ".".join(module_parts)


def fix_imports_in_file(file_path: Path) -> bool:
    """Fix relative imports in a test file."""
    try:
        content = file_path.read_text()
        original_content = content
        
        # Get module path
        module_path = get_module_path(file_path)
        if not module_path:
            return False
        
        # Pattern: from ..{name} import {items}
        pattern = r"from \.\.(\w+) import"
        replacement = f"from {module_path}.\\1 import"
        content = re.sub(pattern, replacement, content)
        
        # Pattern: from ...{name} import {items} (three dots)
        pattern = r"from \.\.\.(\w+) import"
        # For three dots, go up one more level
        parts = module_path.split(".")
        if len(parts) > 1:
            parent_module = ".".join(parts[:-1])
            replacement = f"from {parent_module}.\\1 import"
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            file_path.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Main function."""
    backend_dir = Path(__file__).parent.parent
    src_dir = backend_dir / "src"
    
    if not src_dir.exists():
        print(f"Error: {src_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    test_files = list(src_dir.rglob("test_*.py"))
    fixed_count = 0
    
    for test_file in test_files:
        if fix_imports_in_file(test_file):
            print(f"Fixed: {test_file.relative_to(backend_dir)}")
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
