#!/usr/bin/env python3
"""
Simple database import script for CI environments
No interactive prompts, designed for GitHub Actions
"""

import sqlite3
import os
import sys
import re
from datetime import datetime, timezone

def normalize_code(code: str) -> str:
    """Normalize code format for better duplicate detection"""
    return re.sub(r'[^A-Z0-9]', '', code.upper())

def import_database(old_db_path: str, new_db_path: str):
    """Import codes from old database to new database"""
    
    print(f"🔄 Starting import...")
    print(f"  Old: {old_db_path}")
    print(f"  New: {new_db_path}")
    
    # Check old database exists
    if not os.path.exists(old_db_path):
        raise FileNotFoundError(f"Old database not found: {old_db_path}")
    
    # Read old database
    print("📖 Reading old database...")
    old_conn = sqlite3.connect(old_db_path)
    old_cursor = old_conn.cursor()
    
    # Get old database info
    old_cursor.execute("SELECT COUNT(*) FROM codes")
    old_count = old_cursor.fetchone()[0]
    print(f"  Found {old_count} codes in old database")
    
    # Get all codes from old database
    old_cursor.execute("SELECT code, reward_type, source, context, date_found_utc FROM codes")
    old_codes = old_cursor.fetchall()
    old_conn.close()
    
    # Create/open new database
    print("📝 Setting up new database...")
    new_conn = sqlite3.connect(new_db_path)
    
    # Create new schema if needed
    new_conn.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            normalized_code TEXT NOT NULL,
            reward_type TEXT,
            source TEXT,
            context TEXT,
            date_found_utc TEXT,
            expiry_date TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes
    new_conn.execute("CREATE INDEX IF NOT EXISTS idx_code ON codes(code)")
    new_conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_code ON codes(normalized_code)")
    new_conn.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON codes(is_active)")
    new_conn.execute("CREATE INDEX IF NOT EXISTS idx_date_found ON codes(date_found_utc)")
    
    # Get existing codes in new database
    new_cursor = new_conn.cursor()
    new_cursor.execute("SELECT normalized_code FROM codes")
    existing_normalized = {row[0] for row in new_cursor.fetchall()}
    
    print(f"  New database has {len(existing_normalized)} existing codes")
    
    # Process old codes
    print("🔄 Processing codes...")
    codes_to_import = []
    duplicates = 0
    
    for old_code in old_codes:
        code = old_code[0]
        reward_type = old_code[1] if len(old_code) > 1 else None
        source = old_code[2] if len(old_code) > 2 else "imported"
        context = old_code[3] if len(old_code) > 3 else ""
        date_found = old_code[4] if len(old_code) > 4 else datetime.now(timezone.utc).isoformat()
        
        # Normalize for duplicate checking
        normalized = normalize_code(code)
        
        if normalized in existing_normalized:
            duplicates += 1
            continue
        
        codes_to_import.append((
            code,
            normalized,
            reward_type,
            source,
            context,
            date_found,
            None,  # expiry_date
            1,     # is_active
            datetime.now(timezone.utc).isoformat()  # created_at
        ))
        
        existing_normalized.add(normalized)
    
    # Import new codes
    if codes_to_import:
        print(f"📥 Importing {len(codes_to_import)} new codes...")
        new_cursor.executemany(
            """INSERT INTO codes 
               (code, normalized_code, reward_type, source, context, date_found_utc, expiry_date, is_active, created_at) 
               VALUES (?,?,?,?,?,?,?,?,?)""",
            codes_to_import
        )
        new_conn.commit()
    
    # Get final count
    new_cursor.execute("SELECT COUNT(*) FROM codes")
    final_count = new_cursor.fetchone()[0]
    
    new_conn.close()
    
    # Report results
    print(f"✅ Import completed!")
    print(f"  📥 Imported: {len(codes_to_import)} codes")
    print(f"  🔄 Duplicates skipped: {duplicates}")
    print(f"  📊 Total codes in database: {final_count}")
    
    return len(codes_to_import), duplicates, final_count

def main():
    """Main function for CI import"""
    if len(sys.argv) != 3:
        print("Usage: python import_database_ci.py <old_db_path> <new_db_path>")
        return 1
    
    old_db_path = sys.argv[1]
    new_db_path = sys.argv[2]
    
    try:
        imported, duplicates, total = import_database(old_db_path, new_db_path)
        
        # Set GitHub Actions outputs if available
        if os.getenv('GITHUB_ACTIONS'):
            with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as f:
                f.write(f"imported={imported}\n")
                f.write(f"duplicates={duplicates}\n")
                f.write(f"total={total}\n")
        
        return 0
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())