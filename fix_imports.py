#!/usr/bin/env python3
"""
Script to fix relative imports in the src directory.
"""

import os
import re
from pathlib import Path

def fix_relative_imports(file_path):
    """Fix relative imports in a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Fix ..models imports
    content = re.sub(r'from \.\.models\.', 'from models.', content)
    
    # Fix ..storage imports  
    content = re.sub(r'from \.\.storage\.', 'from storage.', content)
    
    # Fix ..processing imports
    content = re.sub(r'from \.\.processing\.', 'from processing.', content)
    
    # Fix ..fetchers imports
    content = re.sub(r'from \.\.fetchers\.', 'from fetchers.', content)
    
    # Fix ..notifications imports
    content = re.sub(r'from \.\.notifications\.', 'from notifications.', content)
    
    # Fix ..monitoring imports
    content = re.sub(r'from \.\.monitoring\.', 'from monitoring.', content)
    
    # Fix ..utils imports
    content = re.sub(r'from \.\.utils\.', 'from utils.', content)
    
    # Fix ..core imports
    content = re.sub(r'from \.\.core\.', 'from core.', content)
    
    if content != original_content:
        print(f"Fixing imports in {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    
    return False

def main():
    """Main function to fix all imports."""
    src_dir = Path("src")
    
    if not src_dir.exists():
        print("src directory not found!")
        return
    
    fixed_count = 0
    
    # Find all Python files in src directory
    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue  # Skip __init__.py files for now
            
        if fix_relative_imports(py_file):
            fixed_count += 1
    
    print(f"Fixed imports in {fixed_count} files")

if __name__ == "__main__":
    main()