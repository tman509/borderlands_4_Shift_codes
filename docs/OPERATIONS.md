# Shift Code Bot Operations Guide

This guide covers day-to-day operations, monitoring, and troubleshooting of the Shift Code Bot.

## Daily Operations

### Health Monitoring

**Daily Health Check:**
```bash
# Quick health check
python health_check.py

# Detailed health with JSON output
python health_check.py --json

# HTTP health check
curl http://localhost:8080/health
```

**Health Status Indicators:**
- `healthy` - All systems operational
- `warning` - Minor issues, bot still functional
- `unhealthy` - Critical issues, intervention required

### Performance Monitoring

**Daily Performance Report:**
```bash
# Generate 24-hour performance report
python maintenance.py report --hours 24 --detailed

# JSON output for monitoring systems
python maintenance.py report --hours 24 --json
```

**Key Metrics to Monitor:**
- Code discovery rate
- Notification success rate
- Database size growth
- Error frequency
- Response times

### Log Review

**Important Log Files:**
- `logs/shift-code-bot.log` - Main application log
- `logs/error.log` - Error-specific log
- `logs/performance.log` - Performance metrics

**Daily Log Review:**
```bash
# Check for errors in last 24 hours
grep "ERROR" logs/shift-code-bot.log | tail -20

# Monitor code discovery
grep "codes found" logs/shift-code-bot.log | tail -10

# Check notification status
grep "notification" logs/shift-code-bot.log | tail -10
```

## Weekly Operations

### Database Maintenance

**Weekly Cleanup:**
```bash
# Full cleanup operation
python maintenance.py cleanup --all

# Individual cleanup operations
python maintenance.py cleanup --expired-codes --days-old 30
python maintenance.py cleanup --old-metrics --metrics-days 90
python maintenance.py cleanup --vacuum
```

**Database Health Check:**
```bash
# Check database integrity
python maintenance.py check

# Performance analysis
python maintenance.py report --hours 168 --detailed
```

### Backup Management

**Weekly Backup:**
```bash
# Create weekly backup
python maintenance.py backup --output "backups/weekly_$(date +%Y%m%d).db"

# Verify backup integrity
python health_check.py --database-url "sqlite:///backups/weekly_$(date +%Y%m%d).db"
```

**Backup Retention:**
```bash
# Keep 4 weekly backups
find backups/ -name "weekly_*.db" -mtime +28 -delete

# Keep 30 daily backups
find backups/ -name "daily_*.db" -mtime +30 -delete
```

## Monthly Operations

### Performance Review

**Monthly Performance Analysis:**
```bash
# Generate monthly report
python maintenance.py report --hours 720 --detailed --json > reports/monthly_$(date +%Y%m).json

# Analyze trends
python -c "
import json
with open('reports/monthly_$(date +%Y%m).json') as f:
    data = json.load(f)
    print(f'Total codes discovered: {data[\"code_discovery\"][\"new_codes_discovered\"]}')
    print(f'Average crawl time: {data[\"crawl_performance\"][\"avg_execution_time_seconds\"]}s')
    print(f'Success rate: {data[\"crawl_performance\"][\"success_rate\"]:.2%}')
"
```

### Configuration Review

**Monthly Configuration Audit:**
1. Review source configurations
2. Check Discord webhook status
3. Validate rate limiting settings
4. Update source URLs if needed
5. Review notification templates

### Security Review

**Monthly Security Checklist:**
- [ ] Rotate Discord webhook URLs
- [ ] Review access logs
- [ ] Check for security updates
- [ ] Validate SSL certificates
- [ ] Review firewall rules

## Monitoring and Alerting

### Key Performance Indicators (KPIs)

**Operational KPIs:**
- **Uptime**: Target 99.9%
- **Code Discovery Rate**: Codes found per hour
- **Notification Success Rate**: Target 99%
- **Response Time**: Average API response time
- **Error Rate**: Errors per hour

**Business KPIs:**
- **New Codes per Day**: Trending analysis
- **Source Reliability**: Success rate per source
- **User Engagement**: Notification click-through rates
- **System Efficiency**: Codes per resource unit

### Alerting Rules

**Critical Alerts (Immediate Response):**
- System health status = unhealthy
- Database connection failures
- All notifications failing
- Disk space < 10%
- Memory usage > 90%

**Warning Alerts (Response within 4 hours):**
- System health status = warning
- Code discovery rate drops > 50%
- Notification success rate < 95%
- Individual source failures
- High error rates

**Info Alerts (Daily review):**
- New codes discovered
- Performance degradation
- Configuration changes
- Backup completion

### Monitoring Setup

**Prometheus Metrics:**
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'shift-code-bot'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

**Grafana Dashboard:**
- System health overview
- Code discovery trends
- Notification success rates
- Database performance
- Error rate tracking

## Troubleshooting

### Common Issues and Solutions

#### Bot Not Discovering Codes

**Symptoms:**
- No new codes in logs
- Zero codes found in reports
- Sources showing as failed

**Diagnosis:**
```bash
# Check source health
python health_check.py --json | jq '.checks.sources'

# Test individual source
python -c "
from src.fetchers.html_fetcher import HtmlFetcher
from src.models.config import SourceConfig, SourceType
config = SourceConfig(1, 'Test', 'https://example.com', SourceType.HTML)
fetcher = HtmlFetcher(config)
print(list(fetcher.fetch()))
"

# Check network connectivity
curl -I https://shift.gearboxsoftware.com
```

**Solutions:**
1. Verify source URLs are accessible
2. Check for website structure changes
3. Update parser configurations
4. Review rate limiting settings
5. Check network connectivity

#### Discord Notifications Failing

**Symptoms:**
- Notifications not appearing in Discord
- Webhook errors in logs
- High notification failure rate

**Diagnosis:**
```bash
# Test webhook directly
curl -X POST "${DISCORD_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message from Shift Code Bot"}'

# Check notification queue
python -c "
from src.notifications.queue import NotificationQueue
queue = NotificationQueue()
print(f'Queue size: {queue.size()}')
print(f'Failed notifications: {queue.get_failed_count()}')
"
```

**Solutions:**
1. Verify webhook URL is correct
2. Check Discord server permissions
3. Review rate limiting logs
4. Test webhook manually
5. Check for Discord API outages

#### High Resource Usage

**Symptoms:**
- High CPU usage
- Memory leaks
- Slow response times
- Database locks

**Diagnosis:**
```bash
# Check system resources
docker stats shift-code-bot

# Database performance
python maintenance.py report --hours 1 --json | jq '.crawl_performance'

# Memory usage analysis
python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

**Solutions:**
1. Optimize database queries
2. Adjust crawl frequency
3. Implement connection pooling
4. Review memory usage patterns
5. Scale resources if needed

#### Database Issues

**Symptoms:**
- Database connection errors
- Slow query performance
- Integrity check failures
- Disk space warnings

**Diagnosis:**
```bash
# Database integrity check
python maintenance.py check

# Database statistics
python -c "
from src.storage.database import Database
db = Database('sqlite:///data/shift_codes.db')
stats = db.get_stats()
print(f'Database size: {stats}')
"

# Disk space check
df -h data/
```

**Solutions:**
1. Run database cleanup
2. Perform VACUUM operation
3. Check disk space
4. Review query performance
5. Consider database migration

### Emergency Procedures

#### System Down

**Immediate Actions:**
1. Check system health: `python health_check.py`
2. Review recent logs: `tail -100 logs/shift-code-bot.log`
3. Restart if necessary: `docker restart shift-code-bot`
4. Verify functionality: `curl http://localhost:8080/health`

#### Data Corruption

**Recovery Steps:**
1. Stop the bot: `docker stop shift-code-bot`
2. Backup current state: `cp data/shift_codes.db data/shift_codes_corrupted.db`
3. Restore from backup: `python maintenance.py restore backups/latest.db`
4. Verify integrity: `python maintenance.py check`
5. Restart bot: `docker start shift-code-bot`

#### Security Incident

**Response Plan:**
1. Isolate the system
2. Rotate all credentials
3. Review access logs
4. Update security configurations
5. Monitor for suspicious activity

## Performance Optimization

### Database Optimization

**Regular Maintenance:**
```bash
# Weekly optimization
python maintenance.py cleanup --all
python maintenance.py cleanup --analyze

# Monthly deep clean
python maintenance.py cleanup --vacuum
```

**Query Optimization:**
- Monitor slow queries
- Add appropriate indexes
- Optimize data structures
- Use prepared statements

### Network Optimization

**Rate Limiting:**
- Adjust per-source rate limits
- Implement adaptive rate limiting
- Monitor API quotas
- Use connection pooling

**Caching:**
- Implement content caching
- Cache parsed results
- Use HTTP caching headers
- Cache database queries

### Memory Optimization

**Memory Management:**
- Monitor memory usage patterns
- Implement garbage collection
- Optimize data structures
- Use streaming for large datasets

## Capacity Planning

### Growth Projections

**Data Growth:**
- Codes: ~10-50 new codes per month
- Database: ~1MB growth per month
- Logs: ~100MB per month

**Resource Requirements:**
- CPU: Linear with source count
- Memory: Stable with cleanup
- Storage: Linear with data retention
- Network: Minimal bandwidth

### Scaling Triggers

**Scale Up When:**
- CPU usage > 80% sustained
- Memory usage > 85%
- Response time > 5 seconds
- Error rate > 5%

**Scale Out When:**
- Single instance limits reached
- Geographic distribution needed
- High availability required
- Load balancing beneficial

## Compliance and Auditing

### Audit Trail

**Logged Events:**
- Configuration changes
- Code discoveries
- Notification deliveries
- System errors
- Performance metrics

**Audit Reports:**
```bash
# Generate audit report
python -c "
from datetime import datetime, timedelta
from src.storage.repositories import CrawlHistoryRepository
from src.storage.database import Database

db = Database('sqlite:///data/shift_codes.db')
repo = CrawlHistoryRepository(db)

# Last 30 days activity
recent = repo.get_recent_crawls(limit=1000)
print(f'Total crawls: {len(recent)}')
print(f'Successful: {sum(1 for r in recent if r[\"status\"] == \"completed\")}')
print(f'Failed: {sum(1 for r in recent if r[\"status\"] == \"failed\")}')
"
```

### Compliance Requirements

**Data Retention:**
- Logs: 90 days minimum
- Metrics: 1 year minimum
- Audit trail: 2 years minimum
- Backups: 30 days minimum

**Privacy Considerations:**
- No personal data collection
- Anonymous usage metrics
- Secure credential storage
- Data minimization practices