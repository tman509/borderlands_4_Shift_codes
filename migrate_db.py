#!/usr/bin/env python3
"""
Database migration script for Borderlands 4 SHiFT Code Bot
Upgrades existing database schema to support new features
"""

import sqlite3
import os
import re
from datetime import datetime, timezone

def normalize_code(code: str) -> str:
    """Normalize code format for better duplicate detection"""
    return re.sub(r'[^A-Z0-9]', '', code.upper())

def migrate_database(db_path: str = "./shift_codes.db"):
    """Migrate existing database to new schema"""
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist. No migration needed.")
        return
    
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if migration is needed
    cursor.execute("PRAGMA table_info(codes)")
    columns = [col[1] for col in cursor.fetchall()]
    
    migrations_needed = []
    
    if 'normalized_code' not in columns:
        migrations_needed.append('add_normalized_code')
    if 'expiry_date' not in columns:
        migrations_needed.append('add_expiry_date')
    if 'is_active' not in columns:
        migrations_needed.append('add_is_active')
    if 'created_at' not in columns:
        migrations_needed.append('add_created_at')
    
    if not migrations_needed:
        print("Database is already up to date!")
        conn.close()
        return
    
    print(f"Applying {len(migrations_needed)} migrations...")
    
    try:
        # Add new columns
        if 'add_normalized_code' in migrations_needed:
            print("Adding normalized_code column...")
            cursor.execute("ALTER TABLE codes ADD COLUMN normalized_code TEXT")
        
        if 'add_expiry_date' in migrations_needed:
            print("Adding expiry_date column...")
            cursor.execute("ALTER TABLE codes ADD COLUMN expiry_date TEXT")
        
        if 'add_is_active' in migrations_needed:
            print("Adding is_active column...")
            cursor.execute("ALTER TABLE codes ADD COLUMN is_active BOOLEAN DEFAULT 1")
        
        if 'add_created_at' in migrations_needed:
            print("Adding created_at column...")
            cursor.execute("ALTER TABLE codes ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        
        # Populate normalized_code for existing records
        if 'add_normalized_code' in migrations_needed:
            print("Populating normalized codes for existing records...")
            cursor.execute("SELECT id, code FROM codes WHERE normalized_code IS NULL")
            records = cursor.fetchall()
            
            for record_id, code in records:
                normalized = normalize_code(code)
                cursor.execute("UPDATE codes SET normalized_code = ? WHERE id = ?", (normalized, record_id))
            
            print(f"Updated {len(records)} existing records with normalized codes")
        
        # Create new indexes
        print("Creating new indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_normalized_code ON codes(normalized_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON codes(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date_found ON codes(date_found_utc)")
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Show statistics
        cursor.execute("SELECT COUNT(*) FROM codes")
        total_codes = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM codes WHERE is_active = 1")
        active_codes = cursor.fetchone()[0]
        
        print(f"\nDatabase statistics:")
        print(f"  Total codes: {total_codes}")
        print(f"  Active codes: {active_codes}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "./shift_codes.db"
    migrate_database(db_path)