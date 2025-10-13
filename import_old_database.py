#!/usr/bin/env python3
"""
Import tool to migrate old SHiFT code database to new improved format
This will preserve all your existing codes and prevent duplicate notifications
"""

import sqlite3
import os
import sys
import re
from datetime import datetime, timezone
from typing import List, Tuple

def normalize_code(code: str) -> str:
    """Normalize code format for better duplicate detection"""
    return re.sub(r'[^A-Z0-9]', '', code.upper())

def check_old_database(old_db_path: str) -> bool:
    """Check if old database exists and has the expected schema"""
    if not os.path.exists(old_db_path):
        print(f"❌ Old database not found: {old_db_path}")
        return False
    
    try:
        conn = sqlite3.connect(old_db_path)
        cursor = conn.cursor()
        
        # Check if codes table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='codes'")
        if not cursor.fetchone():
            print("❌ No 'codes' table found in old database")
            conn.close()
            return False
        
        # Check schema
        cursor.execute("PRAGMA table_info(codes)")
        columns = [col[1] for col in cursor.fetchall()]
        
        required_columns = ['code', 'reward_type', 'source', 'context', 'date_found_utc']
        missing_columns = [col for col in required_columns if col not in columns]
        
        if missing_columns:
            print(f"⚠️ Old database missing columns: {missing_columns}")
            print("This might still work, but some data may be lost")
        
        # Count records
        cursor.execute("SELECT COUNT(*) FROM codes")
        count = cursor.fetchone()[0]
        print(f"✅ Found old database with {count} codes")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking old database: {e}")
        return False

def create_new_database(new_db_path: str):
    """Create new database with improved schema"""
    conn = sqlite3.connect(new_db_path)
    
    # Create new schema
    conn.execute("""
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_code ON codes(code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_normalized_code ON codes(normalized_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON codes(is_active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date_found ON codes(date_found_utc)")
    
    conn.commit()
    return conn

def import_codes(old_db_path: str, new_db_path: str) -> Tuple[int, int, int]:
    """Import codes from old database to new database"""
    
    # Connect to old database
    old_conn = sqlite3.connect(old_db_path)
    old_cursor = old_conn.cursor()
    
    # Get all codes from old database
    try:
        old_cursor.execute("SELECT code, reward_type, source, context, date_found_utc FROM codes")
        old_codes = old_cursor.fetchall()
    except sqlite3.OperationalError as e:
        # Handle missing columns gracefully
        print(f"⚠️ Schema difference detected: {e}")
        old_cursor.execute("SELECT code, reward_type, source, context, date_found_utc FROM codes")
        old_codes = old_cursor.fetchall()
    
    old_conn.close()
    
    # Connect to new database
    new_conn = create_new_database(new_db_path)
    new_cursor = new_conn.cursor()
    
    # Check what codes already exist in new database
    new_cursor.execute("SELECT normalized_code FROM codes")
    existing_normalized = {row[0] for row in new_cursor.fetchall()}
    
    # Prepare data for import
    codes_to_import = []
    duplicates_skipped = 0
    errors = 0
    
    for old_code in old_codes:
        try:
            code = old_code[0]
            reward_type = old_code[1] if len(old_code) > 1 else None
            source = old_code[2] if len(old_code) > 2 else "imported"
            context = old_code[3] if len(old_code) > 3 else ""
            date_found = old_code[4] if len(old_code) > 4 else datetime.now(timezone.utc).isoformat()
            
            # Normalize code for duplicate checking
            normalized = normalize_code(code)
            
            # Skip if already exists
            if normalized in existing_normalized:
                duplicates_skipped += 1
                continue
            
            # Add to import list
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
            
        except Exception as e:
            print(f"⚠️ Error processing code {old_code}: {e}")
            errors += 1
    
    # Import codes in batch
    if codes_to_import:
        new_cursor.executemany(
            """INSERT INTO codes 
               (code, normalized_code, reward_type, source, context, date_found_utc, expiry_date, is_active, created_at) 
               VALUES (?,?,?,?,?,?,?,?,?)""",
            codes_to_import
        )
        new_conn.commit()
    
    new_conn.close()
    
    return len(codes_to_import), duplicates_skipped, errors

def main():
    """Main import function"""
    print("🔄 SHiFT Code Database Import Tool")
    print("=" * 50)
    
    # Get file paths
    if len(sys.argv) > 1:
        old_db_path = sys.argv[1]
    else:
        old_db_path = input("Enter path to old database (or press Enter for './shift_codes.db'): ").strip()
        if not old_db_path:
            old_db_path = "./shift_codes.db"
    
    if len(sys.argv) > 2:
        new_db_path = sys.argv[2]
    else:
        new_db_path = input("Enter path for new database (or press Enter for './shift_codes_new.db'): ").strip()
        if not new_db_path:
            new_db_path = "./shift_codes_new.db"
    
    print(f"\n📂 Import Settings:")
    print(f"  Old database: {old_db_path}")
    print(f"  New database: {new_db_path}")
    
    # Check if new database already exists
    if os.path.exists(new_db_path):
        response = input(f"\n⚠️ New database already exists. Merge with existing data? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Import cancelled")
            return 1
    
    # Validate old database
    print(f"\n🔍 Checking old database...")
    if not check_old_database(old_db_path):
        return 1
    
    # Perform import
    print(f"\n🚀 Starting import...")
    try:
        imported, duplicates, errors = import_codes(old_db_path, new_db_path)
        
        print(f"\n✅ Import completed!")
        print(f"  📥 Imported: {imported} codes")
        print(f"  🔄 Duplicates skipped: {duplicates}")
        print(f"  ❌ Errors: {errors}")
        
        if imported > 0:
            print(f"\n🎉 Success! Your old codes have been imported.")
            print(f"📁 New database saved as: {new_db_path}")
            print(f"\n💡 Next steps:")
            print(f"  1. Backup your old database: cp {old_db_path} {old_db_path}.backup")
            print(f"  2. Replace with new database: mv {new_db_path} {old_db_path}")
            print(f"  3. Run the bot - it will only notify about NEW codes!")
        else:
            print(f"\n⚠️ No new codes to import (all codes already exist in target database)")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())