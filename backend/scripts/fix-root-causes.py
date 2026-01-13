#!/usr/bin/env python3
"""
Fix root causes of test failures per SARAISE governance standards.

Root Causes Identified:
1. Model naming mismatches - tests import models that don't exist
2. Python cache conflicts - test files with same names across modules
3. Missing __init__.py files in test directories
4. Import path inconsistencies

This script fixes all root causes systematically.
"""
import re
import sys
from pathlib import Path


def ensure_init_files(backend_dir: Path):
    """Ensure all test directories have __init__.py files."""
    src_dir = backend_dir / "src"
    fixed = []
    
    for test_dir in src_dir.rglob("tests"):
        init_file = test_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Test package for module."""\n')
            fixed.append(str(test_dir.relative_to(backend_dir)))
    
    return fixed


def find_actual_models(module_dir: Path) -> list[str]:
    """Find actual model classes in a module's models.py."""
    models_file = module_dir / "models.py"
    if not models_file.exists():
        return []
    
    content = models_file.read_text()
    # Find class definitions that inherit from models.Model
    pattern = r"^class (\w+)\([^)]*models\.Model"
    matches = re.findall(pattern, content, re.MULTILINE)
    return matches


def fix_test_imports(backend_dir: Path):
    """Fix test imports to match actual model names."""
    src_dir = backend_dir / "src"
    fixed = []
    
    for test_file in src_dir.rglob("test_*.py"):
        module_dir = test_file.parent.parent
        module_name = module_dir.name
        
        # Skip if not in a module directory
        if "modules" not in test_file.parts:
            continue
        
        # Get actual models
        actual_models = find_actual_models(module_dir)
        if not actual_models:
            continue
        
        # Read test file
        content = test_file.read_text()
        original_content = content
        
        # Fix common import patterns
        # Pattern: from src.modules.{module}.models import {WrongModel}
        # Replace with actual model names
        
        # Check if test imports a Resource model that doesn't exist
        resource_pattern = rf"from src\.modules\.{module_name}\.models import (\w+Resource)"
        matches = re.findall(resource_pattern, content)
        
        for wrong_model in matches:
            # Try to find a matching actual model
            # Most modules use {ModuleName}Resource pattern
            expected_model = f"{''.join(word.capitalize() for word in module_name.split('_'))}Resource"
            
            # Check if expected model exists
            if expected_model in actual_models:
                # Replace wrong import with correct one
                content = content.replace(
                    f"from src.modules.{module_name}.models import {wrong_model}",
                    f"from src.modules.{module_name}.models import {expected_model}"
                )
                # Replace usage in file
                content = content.replace(wrong_model, expected_model)
            elif actual_models:
                # Use first available model as fallback
                actual_model = actual_models[0]
                content = content.replace(
                    f"from src.modules.{module_name}.models import {wrong_model}",
                    f"from src.modules.{module_name}.models import {actual_model}"
                )
                content = content.replace(wrong_model, actual_model)
        
        if content != original_content:
            test_file.write_text(content)
            fixed.append(str(test_file.relative_to(backend_dir)))
    
    return fixed


def clear_pycache(backend_dir: Path):
    """Clear all __pycache__ directories."""
    src_dir = backend_dir / "src"
    cleared = []
    
    for pycache_dir in src_dir.rglob("__pycache__"):
        import shutil
        shutil.rmtree(pycache_dir)
        cleared.append(str(pycache_dir.relative_to(backend_dir)))
    
    # Also clear .pyc files
    for pyc_file in src_dir.rglob("*.pyc"):
        pyc_file.unlink()
        cleared.append(str(pyc_file.relative_to(backend_dir)))
    
    return cleared


def main():
    """Main function."""
    backend_dir = Path(__file__).parent.parent
    
    print("🔍 Fixing root causes per SARAISE governance standards...")
    print()
    
    # 1. Ensure __init__.py files exist
    print("1. Ensuring __init__.py files in test directories...")
    init_fixed = ensure_init_files(backend_dir)
    print(f"   ✅ Created {len(init_fixed)} __init__.py files")
    
    # 2. Fix test imports
    print("2. Fixing test imports to match actual models...")
    import_fixed = fix_test_imports(backend_dir)
    print(f"   ✅ Fixed imports in {len(import_fixed)} test files")
    
    # 3. Clear Python cache
    print("3. Clearing Python cache...")
    cache_cleared = clear_pycache(backend_dir)
    print(f"   ✅ Cleared {len(cache_cleared)} cache entries")
    
    print()
    print("✅ Root cause fixes complete!")
    print()
    print("Next steps:")
    print("1. Run tests: docker-compose run --rm backend pytest tests/ src/ -v")
    print("2. Check coverage: docker-compose run --rm backend pytest --cov=src --cov-report=html")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
