"""
Database migration management for the Shift Code Bot.
"""

import sqlite3
import logging
import json
from typing import Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database migrations from old schema to new schema."""
    
    def __init__(self, old_db_path: str, new_database):
        self.old_db_path = old_db_path
        self.new_database = new_database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def migrate_from_old_schema(self) -> Dict[str, Any]:
        """Migrate data from old database schema to new schema."""
        migration_stats = {
            "codes_migrated": 0,
            "sources_created": 0,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Connect to old database
            old_conn = sqlite3.connect(self.old_db_path)
            old_conn.row_factory = sqlite3.Row
            
            self.logger.info(f"Starting migration from {self.old_db_path}")
            
            # Migrate codes
            codes_migrated = self._migrate_codes(old_conn)
            migration_stats["codes_migrated"] = codes_migrated
            
            # Create default sources based on old configuration
            sources_created = self._create_default_sources()
            migration_stats["sources_created"] = sources_created
            
            old_conn.close()
            
            migration_stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            self.logger.info(f"Migration completed: {codes_migrated} codes migrated")
            
        except Exception as e:
            error_msg = f"Migration failed: {e}"
            self.logger.error(error_msg)
            migration_stats["errors"].append(error_msg)
            raise
        
        return migration_stats
    
    def _migrate_codes(self, old_conn: sqlite3.Connection) -> int:
        """Migrate codes from old schema to new schema."""
        codes_migrated = 0
        
        with self.new_database.get_connection() as new_conn:
            try:
                # Get codes from old database
                cursor = old_conn.execute("""
                    SELECT code, normalized_code, reward_type, source, context, 
                           date_found_utc, expiry_date, is_active, created_at
                    FROM codes
                    ORDER BY created_at
                """)
                
                for row in cursor:
                    try:
                        # Map old fields to new schema
                        code_canonical = row["normalized_code"] or self._normalize_code(row["code"])
                        code_display = row["code"]
                        reward_type = row["reward_type"]
                        
                        # Parse source information
                        source_id = self._get_or_create_source_id(new_conn, row["source"])
                        
                        # Parse timestamps
                        first_seen_at = row["date_found_utc"] or row["created_at"]
                        expires_at = row["expiry_date"]
                        
                        # Determine status
                        status = "announced" if row["is_active"] else "expired"
                        
                        # Insert into new schema
                        new_conn.execute("""
                            INSERT OR IGNORE INTO codes (
                                code_canonical, code_display, reward_type, platforms,
                                expires_at_utc, first_seen_at, last_updated_at,
                                source_id, status, context, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            code_canonical,
                            code_display,
                            reward_type,
                            json.dumps(["all"]),  # Default to all platforms
                            expires_at,
                            first_seen_at,
                            first_seen_at,  # Use first_seen as last_updated for migrated data
                            source_id,
                            status,
                            row["context"],
                            json.dumps({"migrated": True, "original_source": row["source"]})
                        ))
                        
                        codes_migrated += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to migrate code {row['code']}: {e}")
                        continue
                
                new_conn.commit()
                
            except Exception as e:
                new_conn.rollback()
                raise
        
        return codes_migrated
    
    def _get_or_create_source_id(self, conn: sqlite3.Connection, source_info: str) -> int:
        """Get or create source ID based on source information."""
        # Try to find existing source
        cursor = conn.execute("SELECT id FROM sources WHERE name = ?", (source_info,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        
        # Create new source
        source_type = self._infer_source_type(source_info)
        cursor = conn.execute("""
            INSERT INTO sources (name, url, type, enabled, parser_hints)
            VALUES (?, ?, ?, ?, ?)
        """, (
            source_info,
            source_info if source_info.startswith("http") else "",
            source_type,
            False,  # Disable migrated sources by default
            json.dumps({"migrated": True})
        ))
        
        return cursor.lastrowid
    
    def _infer_source_type(self, source_info: str) -> str:
        """Infer source type from source information."""
        if "reddit" in source_info.lower():
            return "reddit"
        elif source_info.startswith("http"):
            return "html"
        else:
            return "html"  # Default to HTML
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code format (fallback for missing normalized codes)."""
        import re
        clean_code = re.sub(r'[^A-Z0-9]', '', code.upper())
        
        if len(clean_code) == 25:  # 5x5 format
            return '-'.join([clean_code[i:i+5] for i in range(0, 25, 5)])
        elif len(clean_code) in [16, 20]:  # 4x4 format
            chunk_size = 4
            return '-'.join([clean_code[i:i+chunk_size] for i in range(0, len(clean_code), chunk_size)])
        else:
            return code.upper()
    
    def _create_default_sources(self) -> int:
        """Create default sources for the new system."""
        default_sources = [
            {
                "name": "Gearbox Official Twitter",
                "url": "https://twitter.com/GearboxOfficial",
                "type": "html",
                "enabled": True,
                "parser_hints": {
                    "selectors": [".tweet-text", ".content"],
                    "fallback_regex": True
                }
            },
            {
                "name": "Borderlands Reddit",
                "url": "https://www.reddit.com/r/borderlands3",
                "type": "reddit",
                "enabled": False,  # Requires Reddit API setup
                "parser_hints": {
                    "subreddit": "borderlands3",
                    "post_limit": 25,
                    "include_comments": True
                }
            }
        ]
        
        sources_created = 0
        
        with self.new_database.get_connection() as conn:
            for source_config in default_sources:
                try:
                    # Check if source already exists
                    cursor = conn.execute("SELECT id FROM sources WHERE name = ?", (source_config["name"],))
                    if cursor.fetchone():
                        continue
                    
                    # Insert new source
                    conn.execute("""
                        INSERT INTO sources (name, url, type, enabled, parser_hints)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        source_config["name"],
                        source_config["url"],
                        source_config["type"],
                        source_config["enabled"],
                        json.dumps(source_config["parser_hints"])
                    ))
                    
                    sources_created += 1
                    
                except Exception as e:
                    self.logger.warning(f"Failed to create source {source_config['name']}: {e}")
                    continue
            
            conn.commit()
        
        return sources_created