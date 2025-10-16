"""
Comprehensive database migration system for the Shift Code Bot.
"""

import sqlite3
import logging
import json
import hashlib
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class MigrationRecord:
    """Record of a migration execution."""
    version: str
    name: str
    applied_at: datetime
    execution_time_ms: float
    checksum: str
    success: bool = True
    error_message: Optional[str] = None
    rollback_available: bool = False


class Migration(ABC):
    """Base class for database migrations."""
    
    def __init__(self, version: str, name: str):
        self.version = version
        self.name = name
        self.checksum = self._calculate_checksum()
    
    @abstractmethod
    def up(self, connection: sqlite3.Connection) -> None:
        """Apply the migration."""
        pass
    
    def down(self, connection: sqlite3.Connection) -> None:
        """Rollback the migration (optional)."""
        raise NotImplementedError(f"Rollback not implemented for migration {self.version}")
    
    def _calculate_checksum(self) -> str:
        """Calculate checksum of migration content."""
        content = f"{self.version}:{self.name}:{self.__class__.__name__}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def can_rollback(self) -> bool:
        """Check if migration supports rollback."""
        try:
            # Check if down method is implemented
            return self.down.__func__ is not Migration.down
        except AttributeError:
            return False


class CreateInitialSchema(Migration):
    """Initial schema creation migration."""
    
    def __init__(self):
        super().__init__("001", "create_initial_schema")
    
    def up(self, connection: sqlite3.Connection) -> None:
        """Create initial database schema."""
        # Sources table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                type TEXT CHECK(type IN ('html', 'rss', 'api', 'reddit')) NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                parser_hints TEXT, -- JSON configuration
                last_crawl_at TIMESTAMP,
                last_content_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Codes table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_canonical TEXT UNIQUE NOT NULL,
                code_display TEXT NOT NULL,
                reward_type TEXT,
                platforms TEXT, -- JSON array
                expires_at_utc TIMESTAMP,
                first_seen_at TIMESTAMP NOT NULL,
                last_updated_at TIMESTAMP NOT NULL,
                source_id INTEGER REFERENCES sources(id),
                status TEXT CHECK(status IN ('new', 'announced', 'expired', 'updated', 'duplicate')) DEFAULT 'new',
                confidence_score REAL DEFAULT 1.0,
                context TEXT,
                metadata TEXT -- JSON for extensibility
            )
        """)
        
        # Announcements table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER REFERENCES codes(id),
                channel_id TEXT NOT NULL,
                message_id TEXT,
                announced_at TIMESTAMP NOT NULL,
                update_of_announcement_id INTEGER REFERENCES announcements(id),
                status TEXT DEFAULT 'sent',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT
            )
        """)
        
        # Crawl history table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS crawl_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER REFERENCES sources(id),
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status TEXT CHECK(status IN ('running', 'completed', 'failed')) DEFAULT 'running',
                codes_found INTEGER DEFAULT 0,
                error_message TEXT,
                execution_time_seconds REAL
            )
        """)
        
        # Metrics table
        connection.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                tags TEXT, -- JSON for additional dimensions
                source_id INTEGER REFERENCES sources(id)
            )
        """)


class AddIndexes(Migration):
    """Add performance indexes."""
    
    def __init__(self):
        super().__init__("002", "add_performance_indexes")
    
    def up(self, connection: sqlite3.Connection) -> None:
        """Add database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_codes_canonical ON codes(code_canonical)",
            "CREATE INDEX IF NOT EXISTS idx_codes_status ON codes(status)",
            "CREATE INDEX IF NOT EXISTS idx_codes_source_id ON codes(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_codes_first_seen ON codes(first_seen_at)",
            "CREATE INDEX IF NOT EXISTS idx_codes_expires_at ON codes(expires_at_utc)",
            "CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled)",
            "CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(type)",
            "CREATE INDEX IF NOT EXISTS idx_announcements_code_id ON announcements(code_id)",
            "CREATE INDEX IF NOT EXISTS idx_announcements_channel_id ON announcements(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_announcements_announced_at ON announcements(announced_at)",
            "CREATE INDEX IF NOT EXISTS idx_crawl_history_source_id ON crawl_history(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_crawl_history_started_at ON crawl_history(started_at)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name)"
        ]
        
        for index_sql in indexes:
            connection.execute(index_sql)
    
    def down(self, connection: sqlite3.Connection) -> None:
        """Remove indexes."""
        indexes_to_drop = [
            "idx_codes_canonical", "idx_codes_status", "idx_codes_source_id",
            "idx_codes_first_seen", "idx_codes_expires_at", "idx_sources_enabled",
            "idx_sources_type", "idx_announcements_code_id", "idx_announcements_channel_id",
            "idx_announcements_announced_at", "idx_crawl_history_source_id",
            "idx_crawl_history_started_at", "idx_metrics_timestamp", "idx_metrics_name"
        ]
        
        for index_name in indexes_to_drop:
            connection.execute(f"DROP INDEX IF EXISTS {index_name}")


class AddDefaultSources(Migration):
    """Add default sources configuration."""
    
    def __init__(self):
        super().__init__("003", "add_default_sources")
    
    def up(self, connection: sqlite3.Connection) -> None:
        """Add default sources."""
        default_sources = [
            {
                "name": "Gearbox Official Twitter",
                "url": "https://twitter.com/GearboxOfficial",
                "type": "html",
                "enabled": True,
                "parser_hints": json.dumps({
                    "selectors": [".tweet-text", ".content"],
                    "fallback_regex": True
                })
            },
            {
                "name": "Borderlands Reddit",
                "url": "https://www.reddit.com/r/borderlands3",
                "type": "reddit",
                "enabled": False,
                "parser_hints": json.dumps({
                    "subreddit": "borderlands3",
                    "post_limit": 25,
                    "include_comments": True
                })
            },
            {
                "name": "Borderlands Official Site",
                "url": "https://borderlands.com/en-US/news/",
                "type": "html",
                "enabled": True,
                "parser_hints": json.dumps({
                    "selectors": [".news-content", ".article-body"],
                    "fallback_regex": True
                })
            }
        ]
        
        for source in default_sources:
            # Check if source already exists
            cursor = connection.execute("SELECT id FROM sources WHERE name = ?", (source["name"],))
            if not cursor.fetchone():
                connection.execute("""
                    INSERT INTO sources (name, url, type, enabled, parser_hints, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    source["name"],
                    source["url"],
                    source["type"],
                    source["enabled"],
                    source["parser_hints"],
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))


class MigrationEngine:
    """Engine for managing and executing database migrations."""
    
    def __init__(self, database):
        self.database = database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.migrations: List[Migration] = []
        self._register_migrations()
    
    def _register_migrations(self) -> None:
        """Register all available migrations."""
        self.migrations = [
            CreateInitialSchema(),
            AddIndexes(),
            AddDefaultSources()
        ]
        
        # Sort by version
        self.migrations.sort(key=lambda m: m.version)
    
    def _ensure_migration_table(self, connection: sqlite3.Connection) -> None:
        """Ensure migration tracking table exists."""
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP NOT NULL,
                execution_time_ms REAL NOT NULL,
                checksum TEXT NOT NULL,
                success BOOLEAN NOT NULL DEFAULT TRUE,
                error_message TEXT,
                rollback_available BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
    
    def get_applied_migrations(self) -> List[MigrationRecord]:
        """Get list of applied migrations."""
        with self.database.get_connection() as conn:
            self._ensure_migration_table(conn)
            
            cursor = conn.execute("""
                SELECT version, name, applied_at, execution_time_ms, checksum, 
                       success, error_message, rollback_available
                FROM schema_migrations
                ORDER BY version
            """)
            
            records = []
            for row in cursor.fetchall():
                records.append(MigrationRecord(
                    version=row[0],
                    name=row[1],
                    applied_at=datetime.fromisoformat(row[2]),
                    execution_time_ms=row[3],
                    checksum=row[4],
                    success=bool(row[5]),
                    error_message=row[6],
                    rollback_available=bool(row[7])
                ))
            
            return records
    
    def get_pending_migrations(self) -> List[Migration]:
        """Get list of pending migrations."""
        applied = {record.version for record in self.get_applied_migrations()}
        return [migration for migration in self.migrations if migration.version not in applied]
    
    def migrate(self, target_version: Optional[str] = None) -> Dict[str, Any]:
        """Run migrations up to target version."""
        start_time = datetime.now(timezone.utc)
        results = {
            "started_at": start_time.isoformat(),
            "migrations_applied": [],
            "errors": [],
            "success": True
        }
        
        try:
            pending = self.get_pending_migrations()
            
            # Filter to target version if specified
            if target_version:
                pending = [m for m in pending if m.version <= target_version]
            
            if not pending:
                self.logger.info("No pending migrations to apply")
                results["message"] = "No pending migrations"
                return results
            
            self.logger.info(f"Applying {len(pending)} migrations")
            
            for migration in pending:
                migration_result = self._apply_migration(migration)
                results["migrations_applied"].append(migration_result)
                
                if not migration_result["success"]:
                    results["success"] = False
                    results["errors"].append(migration_result["error"])
                    break
            
            end_time = datetime.now(timezone.utc)
            results["completed_at"] = end_time.isoformat()
            results["total_time_ms"] = (end_time - start_time).total_seconds() * 1000
            
            if results["success"]:
                self.logger.info(f"Successfully applied {len(results['migrations_applied'])} migrations")
            else:
                self.logger.error(f"Migration failed: {results['errors']}")
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            self.logger.error(f"Migration process failed: {e}")
        
        return results
    
    def _apply_migration(self, migration: Migration) -> Dict[str, Any]:
        """Apply a single migration."""
        start_time = datetime.now(timezone.utc)
        result = {
            "version": migration.version,
            "name": migration.name,
            "success": False,
            "error": None,
            "execution_time_ms": 0.0
        }
        
        try:
            self.logger.info(f"Applying migration {migration.version}: {migration.name}")
            
            with self.database.get_connection() as conn:
                self._ensure_migration_table(conn)
                
                # Apply migration
                migration.up(conn)
                
                # Record migration
                end_time = datetime.now(timezone.utc)
                execution_time_ms = (end_time - start_time).total_seconds() * 1000
                
                conn.execute("""
                    INSERT INTO schema_migrations 
                    (version, name, applied_at, execution_time_ms, checksum, success, rollback_available)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    migration.version,
                    migration.name,
                    end_time.isoformat(),
                    execution_time_ms,
                    migration.checksum,
                    True,
                    migration.can_rollback()
                ))
                
                conn.commit()
                
                result["success"] = True
                result["execution_time_ms"] = execution_time_ms
                
                self.logger.info(f"Migration {migration.version} applied successfully in {execution_time_ms:.2f}ms")
        
        except Exception as e:
            error_msg = str(e)
            result["error"] = error_msg
            
            # Record failed migration
            try:
                with self.database.get_connection() as conn:
                    self._ensure_migration_table(conn)
                    
                    end_time = datetime.now(timezone.utc)
                    execution_time_ms = (end_time - start_time).total_seconds() * 1000
                    
                    conn.execute("""
                        INSERT INTO schema_migrations 
                        (version, name, applied_at, execution_time_ms, checksum, success, error_message, rollback_available)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        migration.version,
                        migration.name,
                        end_time.isoformat(),
                        execution_time_ms,
                        migration.checksum,
                        False,
                        error_msg,
                        migration.can_rollback()
                    ))
                    
                    conn.commit()
            except Exception as record_error:
                self.logger.error(f"Failed to record migration failure: {record_error}")
            
            self.logger.error(f"Migration {migration.version} failed: {error_msg}")
        
        return result
    
    def rollback(self, target_version: str) -> Dict[str, Any]:
        """Rollback migrations to target version."""
        start_time = datetime.now(timezone.utc)
        results = {
            "started_at": start_time.isoformat(),
            "migrations_rolled_back": [],
            "errors": [],
            "success": True
        }
        
        try:
            applied = self.get_applied_migrations()
            
            # Find migrations to rollback (in reverse order)
            to_rollback = [
                record for record in reversed(applied)
                if record.version > target_version and record.success and record.rollback_available
            ]
            
            if not to_rollback:
                self.logger.info("No migrations to rollback")
                results["message"] = "No migrations to rollback"
                return results
            
            self.logger.info(f"Rolling back {len(to_rollback)} migrations")
            
            for record in to_rollback:
                # Find migration class
                migration = next((m for m in self.migrations if m.version == record.version), None)
                if not migration:
                    error_msg = f"Migration class not found for version {record.version}"
                    results["errors"].append(error_msg)
                    results["success"] = False
                    break
                
                rollback_result = self._rollback_migration(migration, record)
                results["migrations_rolled_back"].append(rollback_result)
                
                if not rollback_result["success"]:
                    results["success"] = False
                    results["errors"].append(rollback_result["error"])
                    break
            
            end_time = datetime.now(timezone.utc)
            results["completed_at"] = end_time.isoformat()
            results["total_time_ms"] = (end_time - start_time).total_seconds() * 1000
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            self.logger.error(f"Rollback process failed: {e}")
        
        return results
    
    def _rollback_migration(self, migration: Migration, record: MigrationRecord) -> Dict[str, Any]:
        """Rollback a single migration."""
        start_time = datetime.now(timezone.utc)
        result = {
            "version": migration.version,
            "name": migration.name,
            "success": False,
            "error": None,
            "execution_time_ms": 0.0
        }
        
        try:
            self.logger.info(f"Rolling back migration {migration.version}: {migration.name}")
            
            with self.database.get_connection() as conn:
                # Rollback migration
                migration.down(conn)
                
                # Remove migration record
                conn.execute("DELETE FROM schema_migrations WHERE version = ?", (migration.version,))
                
                conn.commit()
                
                end_time = datetime.now(timezone.utc)
                execution_time_ms = (end_time - start_time).total_seconds() * 1000
                
                result["success"] = True
                result["execution_time_ms"] = execution_time_ms
                
                self.logger.info(f"Migration {migration.version} rolled back successfully")
        
        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"Rollback of migration {migration.version} failed: {e}")
        
        return result
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get comprehensive migration status."""
        applied = self.get_applied_migrations()
        pending = self.get_pending_migrations()
        
        return {
            "current_version": applied[-1].version if applied else "000",
            "latest_version": self.migrations[-1].version if self.migrations else "000",
            "applied_count": len(applied),
            "pending_count": len(pending),
            "applied_migrations": [
                {
                    "version": record.version,
                    "name": record.name,
                    "applied_at": record.applied_at.isoformat(),
                    "success": record.success,
                    "rollback_available": record.rollback_available
                }
                for record in applied
            ],
            "pending_migrations": [
                {
                    "version": migration.version,
                    "name": migration.name,
                    "rollback_available": migration.can_rollback()
                }
                for migration in pending
            ]
        }