"""
Scheduler with cron-like functionality for the Shift Code Bot.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import re

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobExecution:
    """Record of a job execution."""
    job_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: JobStatus = JobStatus.RUNNING
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_seconds: float = 0.0
    
    def complete(self, result: Any = None, error: str = None) -> None:
        """Mark job execution as completed."""
        self.completed_at = datetime.now(timezone.utc)
        self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()
        
        if error:
            self.status = JobStatus.FAILED
            self.error = error
        else:
            self.status = JobStatus.COMPLETED
            self.result = result


@dataclass
class ScheduledJob:
    """A scheduled job with cron-like configuration."""
    id: str
    name: str
    cron_expression: str
    callback: Callable
    enabled: bool = True
    max_execution_time: int = 300  # 5 minutes default
    retry_count: int = 0
    retry_delay: int = 60  # 1 minute default
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    execution_history: List[JobExecution] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize job after creation."""
        if not self.next_run:
            self.next_run = self._calculate_next_run()
    
    def _calculate_next_run(self) -> datetime:
        """Calculate next run time based on cron expression."""
        return CronParser.next_run_time(self.cron_expression)
    
    def should_run(self, current_time: datetime = None) -> bool:
        """Check if job should run at the current time."""
        if not self.enabled:
            return False
        
        if not self.next_run:
            return False
        
        current_time = current_time or datetime.now(timezone.utc)
        return current_time >= self.next_run
    
    def update_next_run(self) -> None:
        """Update next run time after execution."""
        self.last_run = datetime.now(timezone.utc)
        self.next_run = self._calculate_next_run()
    
    def add_execution(self, execution: JobExecution) -> None:
        """Add execution record and maintain history limit."""
        self.execution_history.append(execution)
        
        # Keep only last 50 executions
        if len(self.execution_history) > 50:
            self.execution_history = self.execution_history[-50:]
    
    def get_recent_executions(self, count: int = 10) -> List[JobExecution]:
        """Get recent job executions."""
        return self.execution_history[-count:] if self.execution_history else []
    
    def get_success_rate(self, last_n: int = 10) -> float:
        """Calculate success rate for last N executions."""
        recent = self.get_recent_executions(last_n)
        if not recent:
            return 1.0
        
        successful = sum(1 for exec in recent if exec.status == JobStatus.COMPLETED)
        return successful / len(recent)


class CronParser:
    """Parser for cron expressions."""
    
    @staticmethod
    def parse_cron_field(field: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single cron field."""
        if field == '*':
            return list(range(min_val, max_val + 1))
        
        values = []
        for part in field.split(','):
            if '/' in part:
                # Handle step values (e.g., */5, 0-30/5)
                range_part, step = part.split('/')
                step = int(step)
                
                if range_part == '*':
                    start, end = min_val, max_val
                elif '-' in range_part:
                    start, end = map(int, range_part.split('-'))
                else:
                    start = end = int(range_part)
                
                values.extend(range(start, end + 1, step))
            
            elif '-' in part:
                # Handle ranges (e.g., 1-5)
                start, end = map(int, part.split('-'))
                values.extend(range(start, end + 1))
            
            else:
                # Handle single values
                values.append(int(part))
        
        return sorted(list(set(values)))
    
    @staticmethod
    def next_run_time(cron_expression: str, from_time: datetime = None) -> datetime:
        """Calculate next run time from cron expression."""
        if from_time is None:
            from_time = datetime.now(timezone.utc)
        
        # Parse cron expression: minute hour day month weekday
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        
        minute_str, hour_str, day_str, month_str, weekday_str = parts
        
        # Parse each field
        minutes = CronParser.parse_cron_field(minute_str, 0, 59)
        hours = CronParser.parse_cron_field(hour_str, 0, 23)
        days = CronParser.parse_cron_field(day_str, 1, 31)
        months = CronParser.parse_cron_field(month_str, 1, 12)
        weekdays = CronParser.parse_cron_field(weekday_str, 0, 6)  # 0 = Sunday
        
        # Start from next minute
        next_time = from_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
        
        # Find next valid time (with reasonable limit to prevent infinite loops)
        max_iterations = 366 * 24 * 60  # One year worth of minutes
        iterations = 0
        
        while iterations < max_iterations:
            if (next_time.minute in minutes and
                next_time.hour in hours and
                next_time.day in days and
                next_time.month in months and
                next_time.weekday() in [(d + 1) % 7 for d in weekdays]):  # Convert Sunday=0 to Monday=0
                return next_time
            
            next_time += timedelta(minutes=1)
            iterations += 1
        
        raise ValueError(f"Could not find next run time for cron expression: {cron_expression}")


class Scheduler:
    """Cron-like scheduler for running jobs at specified intervals."""
    
    def __init__(self):
        self.jobs: Dict[str, ScheduledJob] = {}
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # Statistics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        self.start_time: Optional[datetime] = None
    
    def add_job(self, job: ScheduledJob) -> None:
        """Add a job to the scheduler."""
        with self._lock:
            self.jobs[job.id] = job
            self.logger.info(f"Added job '{job.name}' ({job.id}) with schedule: {job.cron_expression}")
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler."""
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs.pop(job_id)
                self.logger.info(f"Removed job '{job.name}' ({job_id})")
                return True
            return False
    
    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        return self.jobs.get(job_id)
    
    def list_jobs(self) -> List[ScheduledJob]:
        """List all jobs."""
        return list(self.jobs.values())
    
    def enable_job(self, job_id: str) -> bool:
        """Enable a job."""
        job = self.get_job(job_id)
        if job:
            job.enabled = True
            self.logger.info(f"Enabled job '{job.name}' ({job_id})")
            return True
        return False
    
    def disable_job(self, job_id: str) -> bool:
        """Disable a job."""
        job = self.get_job(job_id)
        if job:
            job.enabled = False
            self.logger.info(f"Disabled job '{job.name}' ({job_id})")
            return True
        return False
    
    def start(self) -> None:
        """Start the scheduler."""
        if self.running:
            self.logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.start_time = datetime.now(timezone.utc)
        self._stop_event.clear()
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        self.logger.info("Scheduler started")
    
    def stop(self, timeout: float = 30.0) -> None:
        """Stop the scheduler."""
        if not self.running:
            return
        
        self.logger.info("Stopping scheduler...")
        self.running = False
        self._stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                self.logger.warning("Scheduler thread did not stop within timeout")
        
        self.logger.info("Scheduler stopped")
    
    def _run_loop(self) -> None:
        """Main scheduler loop."""
        self.logger.info("Scheduler loop started")
        
        while self.running and not self._stop_event.is_set():
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check each job
                jobs_to_run = []
                with self._lock:
                    for job in self.jobs.values():
                        if job.should_run(current_time):
                            jobs_to_run.append(job)
                
                # Execute jobs that should run
                for job in jobs_to_run:
                    self._execute_job(job)
                
                # Sleep for 30 seconds before next check
                self._stop_event.wait(30)
                
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                self._stop_event.wait(60)  # Wait longer on error
        
        self.logger.info("Scheduler loop ended")
    
    def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a single job."""
        execution = JobExecution(
            job_id=job.id,
            started_at=datetime.now(timezone.utc)
        )
        
        self.logger.info(f"Executing job '{job.name}' ({job.id})")
        self.total_executions += 1
        
        try:
            # Execute job with timeout
            result = self._execute_with_timeout(job.callback, job.max_execution_time)
            
            execution.complete(result=result)
            self.successful_executions += 1
            
            self.logger.info(f"Job '{job.name}' completed successfully in {execution.execution_time_seconds:.2f}s")
            
        except TimeoutError:
            error_msg = f"Job '{job.name}' timed out after {job.max_execution_time}s"
            execution.complete(error=error_msg)
            self.failed_executions += 1
            self.logger.error(error_msg)
            
        except Exception as e:
            error_msg = f"Job '{job.name}' failed: {e}"
            execution.complete(error=str(e))
            self.failed_executions += 1
            self.logger.error(error_msg)
        
        finally:
            # Update job state
            job.add_execution(execution)
            job.update_next_run()
    
    def _execute_with_timeout(self, callback: Callable, timeout: int) -> Any:
        """Execute callback with timeout."""
        result = None
        exception = None
        
        def target():
            nonlocal result, exception
            try:
                result = callback()
            except Exception as e:
                exception = e
        
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # Thread is still running, we can't kill it but we can timeout
            raise TimeoutError(f"Job execution exceeded {timeout} seconds")
        
        if exception:
            raise exception
        
        return result
    
    def run_job_now(self, job_id: str) -> bool:
        """Manually trigger a job to run immediately."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        self.logger.info(f"Manually triggering job '{job.name}' ({job_id})")
        
        # Execute in a separate thread to avoid blocking
        thread = threading.Thread(target=self._execute_job, args=(job,))
        thread.start()
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        uptime = 0.0
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            "running": self.running,
            "uptime_seconds": uptime,
            "total_jobs": len(self.jobs),
            "enabled_jobs": sum(1 for job in self.jobs.values() if job.enabled),
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.successful_executions / max(self.total_executions, 1),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "enabled": job.enabled,
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "next_run": job.next_run.isoformat() if job.next_run else None,
                    "success_rate": job.get_success_rate()
                }
                for job in self.jobs.values()
            ]
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on scheduler."""
        health = {
            "status": "healthy" if self.running else "stopped",
            "running": self.running,
            "thread_alive": self.thread.is_alive() if self.thread else False,
            "job_count": len(self.jobs),
            "recent_failures": 0
        }
        
        # Check for recent failures
        current_time = datetime.now(timezone.utc)
        recent_cutoff = current_time - timedelta(hours=1)
        
        for job in self.jobs.values():
            recent_executions = [
                exec for exec in job.execution_history
                if exec.started_at > recent_cutoff
            ]
            
            failed_recent = sum(
                1 for exec in recent_executions
                if exec.status == JobStatus.FAILED
            )
            
            health["recent_failures"] += failed_recent
        
        if health["recent_failures"] > 5:
            health["status"] = "degraded"
        
        return health


# Predefined common cron expressions
class CronExpressions:
    """Common cron expressions for convenience."""
    
    EVERY_MINUTE = "* * * * *"
    EVERY_5_MINUTES = "*/5 * * * *"
    EVERY_10_MINUTES = "*/10 * * * *"
    EVERY_15_MINUTES = "*/15 * * * *"
    EVERY_30_MINUTES = "*/30 * * * *"
    EVERY_HOUR = "0 * * * *"
    EVERY_2_HOURS = "0 */2 * * *"
    EVERY_6_HOURS = "0 */6 * * *"
    EVERY_12_HOURS = "0 */12 * * *"
    DAILY_MIDNIGHT = "0 0 * * *"
    DAILY_NOON = "0 12 * * *"
    WEEKLY_SUNDAY = "0 0 * * 0"
    MONTHLY = "0 0 1 * *"