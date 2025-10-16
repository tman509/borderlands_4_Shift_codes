"""
Operational maintenance and cleanup jobs for the Shift Code Bot.
"""

import logging
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceResult:
    """Result of a maintenance operation."""
    operation: str
    success: bool
    records_affected: int = 0
    execution_time_ms: float = 0.0
    details: Dict[str, Any] = None
    error_message: Optional[str] = None


class DatabaseMaintenance:
    """Database maintenance and cleanup operations."""
    
    def __init__(self, database):
        self.database = database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def cleanup_expired_codes(self, days_old: int = 30) -> MaintenanceResult:
        """Clean up expired codes older than specified days."""
        start_time = datetime.now(timezone.utc)
        
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            with self.database.get_connection() as conn:
                # First, get count of codes to be cleaned up
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM codes 
                    WHERE status = 'expired' 
                    AND (expires_at_utc < ? OR last_updated_at < ?)
                """, (cutoff_date.isoformat(), cutoff_date.isoformat()))
                
                count_to_delete = cursor.fetchone()[0]
                
                if count_to_delete == 0:
                    return MaintenanceResult(
                        operation="cleanup_expired_codes",
                        success=True,
                        records_affected=0,
                        execution_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                        details={"message": "No expired codes to clean up"}
                    )
                
                # Delete old expired codes
                cursor = conn.execute("""
                    DELETE FROM codes 
                    WHERE status = 'expired' 
                    AND (expires_at_utc < ? OR last_updated_at < ?)
                """, (cutoff_date.isoformat(), cutoff_date.isoformat()))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Cleaned up {deleted_count} expired codes older than {days_old} days")
                
                return MaintenanceResult(
                    operation="cleanup_expired_codes",
                    success=True,
                    records_affected=deleted_count,
                    execution_time_ms=execution_time,
                    details={
                        "cutoff_date": cutoff_date.isoformat(),
                        "days_old": days_old
                    }
                )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to cleanup expired codes: {error_msg}")
            
            return MaintenanceResult(
                operation="cleanup_expired_codes",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def cleanup_old_metrics(self, days_old: int = 90) -> MaintenanceResult:
        """Clean up old metrics data."""
        start_time = datetime.now(timezone.utc)
        
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            with self.database.get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM metrics 
                    WHERE timestamp < ?
                """, (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Cleaned up {deleted_count} old metrics records")
                
                return MaintenanceResult(
                    operation="cleanup_old_metrics",
                    success=True,
                    records_affected=deleted_count,
                    execution_time_ms=execution_time,
                    details={
                        "cutoff_date": cutoff_date.isoformat(),
                        "days_old": days_old
                    }
                )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to cleanup old metrics: {error_msg}")
            
            return MaintenanceResult(
                operation="cleanup_old_metrics",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def cleanup_old_crawl_history(self, days_old: int = 30) -> MaintenanceResult:
        """Clean up old crawl history records."""
        start_time = datetime.now(timezone.utc)
        
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            with self.database.get_connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM crawl_history 
                    WHERE started_at < ? AND status IN ('completed', 'failed')
                """, (cutoff_date.isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Cleaned up {deleted_count} old crawl history records")
                
                return MaintenanceResult(
                    operation="cleanup_old_crawl_history",
                    success=True,
                    records_affected=deleted_count,
                    execution_time_ms=execution_time,
                    details={
                        "cutoff_date": cutoff_date.isoformat(),
                        "days_old": days_old
                    }
                )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to cleanup old crawl history: {error_msg}")
            
            return MaintenanceResult(
                operation="cleanup_old_crawl_history",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def vacuum_database(self) -> MaintenanceResult:
        """Vacuum database to reclaim space and optimize performance."""
        start_time = datetime.now(timezone.utc)
        
        try:
            with self.database.get_connection() as conn:
                # Get database size before vacuum
                cursor = conn.execute("PRAGMA page_count")
                pages_before = cursor.fetchone()[0]
                cursor = conn.execute("PRAGMA page_size")
                page_size = cursor.fetchone()[0]
                size_before = pages_before * page_size
                
                # Perform vacuum
                conn.execute("VACUUM")
                
                # Get database size after vacuum
                cursor = conn.execute("PRAGMA page_count")
                pages_after = cursor.fetchone()[0]
                size_after = pages_after * page_size
                
                space_reclaimed = size_before - size_after
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Database vacuum completed, reclaimed {space_reclaimed} bytes")
                
                return MaintenanceResult(
                    operation="vacuum_database",
                    success=True,
                    execution_time_ms=execution_time,
                    details={
                        "size_before_bytes": size_before,
                        "size_after_bytes": size_after,
                        "space_reclaimed_bytes": space_reclaimed,
                        "pages_before": pages_before,
                        "pages_after": pages_after
                    }
                )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to vacuum database: {error_msg}")
            
            return MaintenanceResult(
                operation="vacuum_database",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def analyze_database(self) -> MaintenanceResult:
        """Analyze database to update statistics for query optimization."""
        start_time = datetime.now(timezone.utc)
        
        try:
            with self.database.get_connection() as conn:
                conn.execute("ANALYZE")
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info("Database analysis completed")
                
                return MaintenanceResult(
                    operation="analyze_database",
                    success=True,
                    execution_time_ms=execution_time,
                    details={"message": "Database statistics updated"}
                )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to analyze database: {error_msg}")
            
            return MaintenanceResult(
                operation="analyze_database",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def check_database_integrity(self) -> MaintenanceResult:
        """Check database integrity."""
        start_time = datetime.now(timezone.utc)
        
        try:
            with self.database.get_connection() as conn:
                cursor = conn.execute("PRAGMA integrity_check")
                results = cursor.fetchall()
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                # Check if integrity check passed
                is_ok = len(results) == 1 and results[0][0] == "ok"
                
                if is_ok:
                    self.logger.info("Database integrity check passed")
                    return MaintenanceResult(
                        operation="check_database_integrity",
                        success=True,
                        execution_time_ms=execution_time,
                        details={"status": "ok", "issues": []}
                    )
                else:
                    issues = [result[0] for result in results]
                    self.logger.warning(f"Database integrity issues found: {issues}")
                    return MaintenanceResult(
                        operation="check_database_integrity",
                        success=False,
                        execution_time_ms=execution_time,
                        details={"status": "issues_found", "issues": issues},
                        error_message=f"Integrity issues: {', '.join(issues)}"
                    )
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to check database integrity: {error_msg}")
            
            return MaintenanceResult(
                operation="check_database_integrity",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )


class PerformanceMonitor:
    """Monitor system performance and generate reports."""
    
    def __init__(self, database):
        self.database = database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def get_performance_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            with self.database.get_connection() as conn:
                report = {
                    "report_generated_at": datetime.now(timezone.utc).isoformat(),
                    "time_period_hours": hours,
                    "database_stats": self._get_database_stats(conn),
                    "crawl_performance": self._get_crawl_performance(conn, cutoff_time),
                    "code_discovery": self._get_code_discovery_stats(conn, cutoff_time),
                    "system_health": self._get_system_health_indicators(conn, cutoff_time)
                }
                
                return report
        
        except Exception as e:
            self.logger.error(f"Failed to generate performance report: {e}")
            return {"error": str(e)}
    
    def _get_database_stats(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {}
        
        # Table sizes
        tables = ["codes", "sources", "announcements", "crawl_history", "metrics"]
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            stats[f"{table}_count"] = cursor.fetchone()[0]
        
        # Database size
        cursor = conn.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor = conn.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        stats["database_size_bytes"] = page_count * page_size
        stats["database_size_mb"] = round((page_count * page_size) / (1024 * 1024), 2)
        
        return stats
    
    def _get_crawl_performance(self, conn: sqlite3.Connection, cutoff_time: datetime) -> Dict[str, Any]:
        """Get crawl performance statistics."""
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_crawls,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_crawls,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_crawls,
                AVG(execution_time_seconds) as avg_execution_time,
                MAX(execution_time_seconds) as max_execution_time,
                SUM(codes_found) as total_codes_found
            FROM crawl_history 
            WHERE started_at > ?
        """, (cutoff_time.isoformat(),))
        
        row = cursor.fetchone()
        
        return {
            "total_crawls": row[0] or 0,
            "successful_crawls": row[1] or 0,
            "failed_crawls": row[2] or 0,
            "success_rate": (row[1] or 0) / max(row[0] or 1, 1),
            "avg_execution_time_seconds": round(row[3] or 0, 2),
            "max_execution_time_seconds": round(row[4] or 0, 2),
            "total_codes_found": row[5] or 0
        }
    
    def _get_code_discovery_stats(self, conn: sqlite3.Connection, cutoff_time: datetime) -> Dict[str, Any]:
        """Get code discovery statistics."""
        # New codes discovered
        cursor = conn.execute("""
            SELECT COUNT(*) FROM codes 
            WHERE first_seen_at > ?
        """, (cutoff_time.isoformat(),))
        new_codes = cursor.fetchone()[0]
        
        # Codes by status
        cursor = conn.execute("""
            SELECT status, COUNT(*) FROM codes 
            WHERE first_seen_at > ?
            GROUP BY status
        """, (cutoff_time.isoformat(),))
        codes_by_status = dict(cursor.fetchall())
        
        # Codes by reward type
        cursor = conn.execute("""
            SELECT reward_type, COUNT(*) FROM codes 
            WHERE first_seen_at > ? AND reward_type IS NOT NULL
            GROUP BY reward_type
        """, (cutoff_time.isoformat(),))
        codes_by_reward = dict(cursor.fetchall())
        
        return {
            "new_codes_discovered": new_codes,
            "codes_by_status": codes_by_status,
            "codes_by_reward_type": codes_by_reward
        }
    
    def _get_system_health_indicators(self, conn: sqlite3.Connection, cutoff_time: datetime) -> Dict[str, Any]:
        """Get system health indicators."""
        # Recent errors (from crawl history)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM crawl_history 
            WHERE started_at > ? AND status = 'failed'
        """, (cutoff_time.isoformat(),))
        recent_errors = cursor.fetchone()[0]
        
        # Source health
        cursor = conn.execute("""
            SELECT s.name, 
                   COUNT(ch.id) as crawl_count,
                   COUNT(CASE WHEN ch.status = 'failed' THEN 1 END) as failed_count
            FROM sources s
            LEFT JOIN crawl_history ch ON s.id = ch.source_id AND ch.started_at > ?
            WHERE s.enabled = TRUE
            GROUP BY s.id, s.name
        """, (cutoff_time.isoformat(),))
        
        source_health = {}
        for row in cursor.fetchall():
            source_name, crawl_count, failed_count = row
            source_health[source_name] = {
                "crawl_count": crawl_count,
                "failed_count": failed_count,
                "success_rate": (crawl_count - failed_count) / max(crawl_count, 1)
            }
        
        return {
            "recent_errors": recent_errors,
            "source_health": source_health
        }


class BackupManager:
    """Manage database backups and restore operations."""
    
    def __init__(self, database):
        self.database = database
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def create_backup(self, backup_path: str) -> MaintenanceResult:
        """Create database backup."""
        start_time = datetime.now(timezone.utc)
        
        try:
            import shutil
            
            # For SQLite, we can simply copy the database file
            if self.database.database_url.startswith("sqlite:///"):
                source_path = self.database.database_url[10:]  # Remove "sqlite:///"
                
                # Ensure backup directory exists
                backup_file = Path(backup_path)
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Create backup
                shutil.copy2(source_path, backup_path)
                
                # Get backup file size
                backup_size = Path(backup_path).stat().st_size
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Database backup created: {backup_path}")
                
                return MaintenanceResult(
                    operation="create_backup",
                    success=True,
                    execution_time_ms=execution_time,
                    details={
                        "backup_path": backup_path,
                        "backup_size_bytes": backup_size,
                        "source_path": source_path
                    }
                )
            else:
                raise NotImplementedError("Backup not implemented for non-SQLite databases")
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to create backup: {error_msg}")
            
            return MaintenanceResult(
                operation="create_backup",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )
    
    def restore_backup(self, backup_path: str) -> MaintenanceResult:
        """Restore database from backup."""
        start_time = datetime.now(timezone.utc)
        
        try:
            import shutil
            
            if not Path(backup_path).exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            if self.database.database_url.startswith("sqlite:///"):
                target_path = self.database.database_url[10:]  # Remove "sqlite:///"
                
                # Create backup of current database before restore
                current_backup = f"{target_path}.pre_restore_{int(datetime.now().timestamp())}"
                if Path(target_path).exists():
                    shutil.copy2(target_path, current_backup)
                
                # Restore from backup
                shutil.copy2(backup_path, target_path)
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                self.logger.info(f"Database restored from backup: {backup_path}")
                
                return MaintenanceResult(
                    operation="restore_backup",
                    success=True,
                    execution_time_ms=execution_time,
                    details={
                        "backup_path": backup_path,
                        "target_path": target_path,
                        "current_backup": current_backup
                    }
                )
            else:
                raise NotImplementedError("Restore not implemented for non-SQLite databases")
        
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            error_msg = str(e)
            
            self.logger.error(f"Failed to restore backup: {error_msg}")
            
            return MaintenanceResult(
                operation="restore_backup",
                success=False,
                execution_time_ms=execution_time,
                error_message=error_msg
            )