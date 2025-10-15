"""
Database connection and schema management for the Shift Code Bot.
"""

import sqlite3
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """Database connection and schema management."""
    
    # Current schema version
    SCHEMA_VERSION = 1
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection: Optional[sqlite3.Connection] = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Parse database URL (simplified for SQLite)
        if database_url.startswith("sqlite:///"):
            self.db_path = database_url[10:]  # Remove "sqlite:///"
        else:
            self.db_path = database_url
    
    def connect(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        try:
            # Ensure directory exists
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Set WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode = WAL")
            
            # Set reasonable timeouts
            conn.execute("PRAGMA busy_timeout = 30000")
            
            # Row factory for dict-like access
            conn.row_factory = sqlite3.Row
            
            self.logger.debug(f"Connected to database: {self.db_path}")
            return conn
            
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = self.connect()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def initialize_schema(self) -> None:
        """Initialize database schema."""
        with self.get_connection() as conn:
            try:
                self._create_schema_version_table(conn)
                
                current_version = self._get_schema_version(conn)
                if current_version == 0:
                    self.logger.info("Creating initial database schema")
                    self._create_initial_schema(conn)
                    self._set_schema_version(conn, self.SCHEMA_VERSION)
                elif current_version < self.SCHEMA_VERSION:
                    self.logger.info(f"Upgrading schema from v{current_version} to v{self.SCHEMA_VERSION}")
                    # TODO: Implement schema migrations
                    pass
                
                self._create_indexes(conn)
                conn.commit()
                
                self.logger.info("Database schema initialized successfully")
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to initialize schema: {e}")
                raise
    
    def _create_schema_version_table(self, conn: sqlite3.Connection) -> None:
        """Create schema version tracking table."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _get_schema_version(self, conn: sqlite3.Connection) -> int:
        """Get current schema version."""
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        return result[0] if result[0] is not None else 0
    
    def _set_schema_version(self, conn: sqlite3.Connection, version: int) -> None:
        """Set schema version."""
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    
    def _create_initial_schema(self, conn: sqlite3.Connection) -> None:
        """Create initial database schema."""
        
        # Sources table
        conn.execute("""
            CREATE TABLE sources (
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
        conn.execute("""
            CREATE TABLE codes (
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
        conn.execute("""
            CREATE TABLE announcements (
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
        
        # Crawl history table for tracking source crawls
        conn.execute("""
            CREATE TABLE crawl_history (
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
        
        # Metrics table for performance tracking
        conn.execute("""
            CREATE TABLE metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                tags TEXT, -- JSON for additional dimensions
                source_id INTEGER REFERENCES sources(id)
            )
        """)
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create database indexes for performance."""
        
        # Codes table indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_canonical ON codes(code_canonical)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_status ON codes(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_source_id ON codes(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_first_seen ON codes(first_seen_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codes_expires_at ON codes(expires_at_utc)")
        
        # Sources table indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(type)")
        
        # Announcements table indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_announcements_code_id ON announcements(code_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_announcements_channel_id ON announcements(channel_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_announcements_announced_at ON announcements(announced_at)")
        
        # Crawl history indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_history_source_id ON crawl_history(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_crawl_history_started_at ON crawl_history(started_at)")
        
        # Metrics indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name)")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_connection() as conn:
            stats = {}
            
            # Total codes
            cursor = conn.execute("SELECT COUNT(*) FROM codes")
            stats["total_codes"] = cursor.fetchone()[0]
            
            # Active codes
            cursor = conn.execute("SELECT COUNT(*) FROM codes WHERE status = 'new'")
            stats["new_codes"] = cursor.fetchone()[0]
            
            # Announced codes
            cursor = conn.execute("SELECT COUNT(*) FROM codes WHERE status = 'announced'")
            stats["announced_codes"] = cursor.fetchone()[0]
            
            # Total sources
            cursor = conn.execute("SELECT COUNT(*) FROM sources")
            stats["total_sources"] = cursor.fetchone()[0]
            
            # Enabled sources
            cursor = conn.execute("SELECT COUNT(*) FROM sources WHERE enabled = TRUE")
            stats["enabled_sources"] = cursor.fetchone()[0]
            
            # Recent announcements (last 24 hours)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM announcements 
                WHERE announced_at > datetime('now', '-1 day')
            """)
            stats["recent_announcements"] = cursor.fetchone()[0]
            
            return stats
    
    def health_check(self) -> Dict[str, Any]:
        """Perform database health check."""
        try:
            with self.get_connection() as conn:
                # Test basic connectivity
                cursor = conn.execute("SELECT 1")
                cursor.fetchone()
                
                # Check schema version
                version = self._get_schema_version(conn)
                
                # Get database size
                cursor = conn.execute("PRAGMA page_count")
                page_count = cursor.fetchone()[0]
                cursor = conn.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                db_size_mb = (page_count * page_size) / (1024 * 1024)
                
                return {
                    "status": "healthy",
                    "schema_version": version,
                    "database_size_mb": round(db_size_mb, 2),
                    "connection": "ok"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "connection": "failed"
            }