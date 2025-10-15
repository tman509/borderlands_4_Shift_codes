"""
Repository classes for database operations.
"""

import json
import logging
import sqlite3
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from ..models.code import ParsedCode, CodeMetadata, CodeStatus
from ..models.config import SourceConfig, SourceType
from .database import Database

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common functionality."""
    
    def __init__(self, database: Database):
        self.database = database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")


class CodeRepository(BaseRepository):
    """Repository for code-related database operations."""
    
    def create_code(self, code: ParsedCode) -> int:
        """Create a new code and return its ID."""
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO codes (
                        code_canonical, code_display, reward_type, platforms,
                        expires_at_utc, first_seen_at, last_updated_at,
                        source_id, status, confidence_score, context, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code.code_canonical,
                    code.code_display,
                    code.reward_type,
                    json.dumps(code.platforms),
                    code.expires_at.isoformat() if code.expires_at else None,
                    code.first_seen_at.isoformat() if code.first_seen_at else datetime.now(timezone.utc).isoformat(),
                    code.last_updated_at.isoformat() if code.last_updated_at else datetime.now(timezone.utc).isoformat(),
                    code.source_id,
                    code.status.value,
                    code.confidence_score,
                    code.context,
                    json.dumps(code.metadata.to_dict())
                ))
                
                code_id = cursor.lastrowid
                conn.commit()
                
                self.logger.debug(f"Created code with ID {code_id}: {code.code_display}")
                return code_id
                
            except sqlite3.IntegrityError as e:
                conn.rollback()
                if "UNIQUE constraint failed" in str(e):
                    self.logger.debug(f"Code already exists: {code.code_canonical}")
                    return self.get_code_by_canonical(code.code_canonical).id
                raise
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to create code {code.code_display}: {e}")
                raise
    
    def get_code_by_id(self, code_id: int) -> Optional[ParsedCode]:
        """Get code by ID."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM codes WHERE id = ?
            """, (code_id,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_parsed_code(row)
            return None
    
    def get_code_by_canonical(self, canonical_code: str) -> Optional[ParsedCode]:
        """Get code by canonical format."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM codes WHERE code_canonical = ?
            """, (canonical_code,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_parsed_code(row)
            return None
    
    def code_exists(self, canonical_code: str) -> bool:
        """Check if code exists by canonical format."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 1 FROM codes WHERE code_canonical = ?
            """, (canonical_code,))
            
            return cursor.fetchone() is not None
    
    def update_code(self, code: ParsedCode) -> bool:
        """Update existing code."""
        if not code.id:
            raise ValueError("Code ID is required for updates")
        
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    UPDATE codes SET
                        code_display = ?, reward_type = ?, platforms = ?,
                        expires_at_utc = ?, last_updated_at = ?, status = ?,
                        confidence_score = ?, context = ?, metadata = ?
                    WHERE id = ?
                """, (
                    code.code_display,
                    code.reward_type,
                    json.dumps(code.platforms),
                    code.expires_at.isoformat() if code.expires_at else None,
                    datetime.now(timezone.utc).isoformat(),
                    code.status.value,
                    code.confidence_score,
                    code.context,
                    json.dumps(code.metadata.to_dict()),
                    code.id
                ))
                
                updated = cursor.rowcount > 0
                conn.commit()
                
                if updated:
                    self.logger.debug(f"Updated code ID {code.id}: {code.code_display}")
                
                return updated
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to update code ID {code.id}: {e}")
                raise
    
    def get_codes_by_status(self, status: CodeStatus, limit: Optional[int] = None) -> List[ParsedCode]:
        """Get codes by status."""
        with self.database.get_connection() as conn:
            query = "SELECT * FROM codes WHERE status = ? ORDER BY first_seen_at DESC"
            params = [status.value]
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_parsed_code(row) for row in cursor.fetchall()]
    
    def get_codes_by_source(self, source_id: int, limit: Optional[int] = None) -> List[ParsedCode]:
        """Get codes by source ID."""
        with self.database.get_connection() as conn:
            query = "SELECT * FROM codes WHERE source_id = ? ORDER BY first_seen_at DESC"
            params = [source_id]
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor = conn.execute(query, params)
            return [self._row_to_parsed_code(row) for row in cursor.fetchall()]
    
    def get_expiring_codes(self, hours_ahead: int = 24) -> List[ParsedCode]:
        """Get codes expiring within specified hours."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM codes 
                WHERE expires_at_utc IS NOT NULL 
                AND expires_at_utc > datetime('now')
                AND expires_at_utc <= datetime('now', '+{} hours')
                AND status IN ('new', 'announced')
                ORDER BY expires_at_utc
            """.format(hours_ahead))
            
            return [self._row_to_parsed_code(row) for row in cursor.fetchall()]
    
    def mark_codes_as_expired(self) -> int:
        """Mark expired codes and return count of updated codes."""
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    UPDATE codes SET 
                        status = 'expired',
                        last_updated_at = datetime('now')
                    WHERE expires_at_utc IS NOT NULL 
                    AND expires_at_utc < datetime('now')
                    AND status NOT IN ('expired', 'duplicate')
                """)
                
                count = cursor.rowcount
                conn.commit()
                
                if count > 0:
                    self.logger.info(f"Marked {count} codes as expired")
                
                return count
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to mark codes as expired: {e}")
                raise
    
    def get_recent_codes(self, hours: int = 24, limit: Optional[int] = None) -> List[ParsedCode]:
        """Get codes found within the last N hours."""
        with self.database.get_connection() as conn:
            query = """
                SELECT * FROM codes 
                WHERE first_seen_at > datetime('now', '-{} hours')
                ORDER BY first_seen_at DESC
            """.format(hours)
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor = conn.execute(query)
            return [self._row_to_parsed_code(row) for row in cursor.fetchall()]
    
    def get_code_stats(self) -> Dict[str, Any]:
        """Get code statistics."""
        with self.database.get_connection() as conn:
            stats = {}
            
            # Total codes
            cursor = conn.execute("SELECT COUNT(*) FROM codes")
            stats["total"] = cursor.fetchone()[0]
            
            # Codes by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) FROM codes GROUP BY status
            """)
            stats["by_status"] = dict(cursor.fetchall())
            
            # Codes by reward type
            cursor = conn.execute("""
                SELECT reward_type, COUNT(*) FROM codes 
                WHERE reward_type IS NOT NULL 
                GROUP BY reward_type
            """)
            stats["by_reward_type"] = dict(cursor.fetchall())
            
            # Recent activity (last 24 hours)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM codes 
                WHERE first_seen_at > datetime('now', '-24 hours')
            """)
            stats["recent_24h"] = cursor.fetchone()[0]
            
            return stats
    
    def _row_to_parsed_code(self, row: sqlite3.Row) -> ParsedCode:
        """Convert database row to ParsedCode object."""
        # Parse timestamps
        first_seen_at = None
        if row["first_seen_at"]:
            first_seen_at = datetime.fromisoformat(row["first_seen_at"])
        
        last_updated_at = None
        if row["last_updated_at"]:
            last_updated_at = datetime.fromisoformat(row["last_updated_at"])
        
        expires_at = None
        if row["expires_at_utc"]:
            expires_at = datetime.fromisoformat(row["expires_at_utc"])
        
        # Parse platforms
        platforms = []
        if row["platforms"]:
            try:
                platforms = json.loads(row["platforms"])
            except json.JSONDecodeError:
                platforms = []
        
        # Parse metadata
        metadata = CodeMetadata()
        if row["metadata"]:
            try:
                metadata_dict = json.loads(row["metadata"])
                metadata = CodeMetadata.from_dict(metadata_dict)
            except json.JSONDecodeError:
                pass
        
        return ParsedCode(
            id=row["id"],
            code_canonical=row["code_canonical"],
            code_display=row["code_display"],
            reward_type=row["reward_type"],
            platforms=platforms,
            expires_at=expires_at,
            source_id=row["source_id"],
            context=row["context"] or "",
            confidence_score=row["confidence_score"] or 1.0,
            metadata=metadata,
            status=CodeStatus(row["status"]),
            first_seen_at=first_seen_at,
            last_updated_at=last_updated_at
        )


class SourceRepository(BaseRepository):
    """Repository for source-related database operations."""
    
    def create_source(self, source: SourceConfig) -> int:
        """Create a new source and return its ID."""
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO sources (
                        name, url, type, enabled, parser_hints,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    source.name,
                    source.url,
                    source.type.value,
                    source.enabled,
                    json.dumps(source.parser_hints),
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))
                
                source_id = cursor.lastrowid
                conn.commit()
                
                self.logger.debug(f"Created source with ID {source_id}: {source.name}")
                return source_id
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to create source {source.name}: {e}")
                raise
    
    def get_source_by_id(self, source_id: int) -> Optional[SourceConfig]:
        """Get source by ID."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM sources WHERE id = ?
            """, (source_id,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_source_config(row)
            return None
    
    def get_all_sources(self) -> List[SourceConfig]:
        """Get all sources."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM sources ORDER BY name
            """)
            
            return [self._row_to_source_config(row) for row in cursor.fetchall()]
    
    def get_enabled_sources(self) -> List[SourceConfig]:
        """Get enabled sources."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM sources WHERE enabled = TRUE ORDER BY name
            """)
            
            return [self._row_to_source_config(row) for row in cursor.fetchall()]
    
    def update_source(self, source: SourceConfig) -> bool:
        """Update existing source."""
        if not source.id:
            raise ValueError("Source ID is required for updates")
        
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    UPDATE sources SET
                        name = ?, url = ?, type = ?, enabled = ?,
                        parser_hints = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    source.name,
                    source.url,
                    source.type.value,
                    source.enabled,
                    json.dumps(source.parser_hints),
                    datetime.now(timezone.utc).isoformat(),
                    source.id
                ))
                
                updated = cursor.rowcount > 0
                conn.commit()
                
                if updated:
                    self.logger.debug(f"Updated source ID {source.id}: {source.name}")
                
                return updated
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to update source ID {source.id}: {e}")
                raise
    
    def update_crawl_info(self, source_id: int, content_hash: Optional[str] = None) -> None:
        """Update source crawl information."""
        with self.database.get_connection() as conn:
            try:
                params = [datetime.now(timezone.utc).isoformat(), source_id]
                query = "UPDATE sources SET last_crawl_at = ?"
                
                if content_hash:
                    query += ", last_content_hash = ?"
                    params.insert(-1, content_hash)
                
                query += " WHERE id = ?"
                
                conn.execute(query, params)
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to update crawl info for source {source_id}: {e}")
                raise
    
    def delete_source(self, source_id: int) -> bool:
        """Delete source by ID."""
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                
                if deleted:
                    self.logger.debug(f"Deleted source ID {source_id}")
                
                return deleted
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to delete source ID {source_id}: {e}")
                raise
    
    def _row_to_source_config(self, row: sqlite3.Row) -> SourceConfig:
        """Convert database row to SourceConfig object."""
        # Parse parser hints
        parser_hints = {}
        if row["parser_hints"]:
            try:
                parser_hints = json.loads(row["parser_hints"])
            except json.JSONDecodeError:
                pass
        
        return SourceConfig(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            type=SourceType(row["type"]),
            enabled=bool(row["enabled"]),
            parser_hints=parser_hints,
            last_crawl_at=row["last_crawl_at"],
            last_content_hash=row["last_content_hash"]
        )


class AnnouncementRepository(BaseRepository):
    """Repository for announcement tracking."""
    
    def create_announcement(self, code_id: int, channel_id: str, message_id: Optional[str] = None) -> int:
        """Create a new announcement record."""
        with self.database.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO announcements (
                        code_id, channel_id, message_id, announced_at, status
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    code_id,
                    channel_id,
                    message_id,
                    datetime.now(timezone.utc).isoformat(),
                    "sent"
                ))
                
                announcement_id = cursor.lastrowid
                conn.commit()
                
                self.logger.debug(f"Created announcement ID {announcement_id} for code {code_id}")
                return announcement_id
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to create announcement for code {code_id}: {e}")
                raise
    
    def announcement_exists(self, code_id: int, channel_id: str) -> bool:
        """Check if announcement already exists for code and channel."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 1 FROM announcements 
                WHERE code_id = ? AND channel_id = ?
            """, (code_id, channel_id))
            
            return cursor.fetchone() is not None
    
    def get_announcements_for_code(self, code_id: int) -> List[Dict[str, Any]]:
        """Get all announcements for a specific code."""
        with self.database.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM announcements 
                WHERE code_id = ? 
                ORDER BY announced_at
            """, (code_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def update_announcement_status(self, announcement_id: int, status: str, error_message: Optional[str] = None) -> None:
        """Update announcement status."""
        with self.database.get_connection() as conn:
            try:
                conn.execute("""
                    UPDATE announcements SET 
                        status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, announcement_id))
                
                conn.commit()
                
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Failed to update announcement {announcement_id}: {e}")
                raise