# Shift Code Bot Deployment Guide

This guide covers deploying the Shift Code Bot in various environments.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git
- Text editor for configuration

### Basic Deployment

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd shift-code-bot
   cp .env.example .env
   ```

2. **Configure Environment**
   Edit `.env` file with your settings:
   ```bash
   # Required: Discord webhook for notifications
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
   
   # Optional: Reddit API (for Reddit sources)
   REDDIT_CLIENT_ID=your_reddit_client_id
   REDDIT_CLIENT_SECRET=your_reddit_client_secret
   ```

3. **Deploy with Docker**
   ```bash
   # Linux/macOS
   ./scripts/deploy.sh
   
   # Windows PowerShell
   .\scripts\deploy.ps1
   ```

4. **Verify Deployment**
   ```bash
   # Check health
   curl http://localhost:8080/health
   
   # View logs
   docker logs shift-code-bot
   ```

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `DISCORD_WEBHOOK_URL` | Yes | Discord webhook URL for notifications | - |
| `REDDIT_CLIENT_ID` | No | Reddit API client ID | - |
| `REDDIT_CLIENT_SECRET` | No | Reddit API client secret | - |
| `DATABASE_URL` | No | Database connection string | `sqlite:///data/shift_codes.db` |
| `LOG_LEVEL` | No | Logging level | `INFO` |
| `ENVIRONMENT` | No | Environment name | `production` |

### Configuration Files

The bot uses JSON configuration files in the `config/` directory:

- `config/production.json` - Production settings
- `config/development.json` - Development settings

Example configuration structure:
```json
{
  "environment": "production",
  "sources": [
    {
      "id": 1,
      "name": "Gearbox Twitter",
      "url": "https://twitter.com/GearboxOfficial",
      "type": "html",
      "enabled": true
    }
  ],
  "discord_channels": [
    {
      "id": "main_channel",
      "webhook_url": "${DISCORD_WEBHOOK_URL}",
      "enabled": true
    }
  ]
}
```

## Deployment Options

### Docker Deployment (Recommended)

**Advantages:**
- Isolated environment
- Easy updates
- Consistent across platforms
- Built-in health checks

**Steps:**
1. Use provided deployment scripts
2. Configure environment variables
3. Run with Docker Compose

### Manual Deployment

**Prerequisites:**
- Python 3.11+
- pip
- SQLite

**Steps:**
1. Install dependencies: `pip install -r requirements.txt`
2. Run migrations: `python migrate.py migrate`
3. Start bot: `python main.py`

### Cloud Deployment

#### AWS ECS
1. Build and push Docker image to ECR
2. Create ECS task definition
3. Configure service with health checks
4. Set up CloudWatch logging

#### Google Cloud Run
1. Build and push to Container Registry
2. Deploy to Cloud Run
3. Configure environment variables
4. Set up monitoring

#### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shift-code-bot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: shift-code-bot
  template:
    metadata:
      labels:
        app: shift-code-bot
    spec:
      containers:
      - name: shift-code-bot
        image: shift-code-bot:latest
        ports:
        - containerPort: 8080
        env:
        - name: DISCORD_WEBHOOK_URL
          valueFrom:
            secretKeyRef:
              name: bot-secrets
              key: discord-webhook
        livenessProbe:
          httpGet:
            path: /live
            port: 8080
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
```

## Monitoring and Maintenance

### Health Checks

The bot provides several health check endpoints:

- `GET /health` - Comprehensive health check
- `GET /ready` - Readiness probe (for Kubernetes)
- `GET /live` - Liveness probe (for Kubernetes)

### Monitoring

**Metrics to Monitor:**
- Health check status
- Code discovery rate
- Notification success rate
- Database size
- Error rates

**Recommended Tools:**
- Prometheus + Grafana
- DataDog
- New Relic
- CloudWatch (AWS)

### Maintenance

**Regular Tasks:**
```bash
# Database cleanup (weekly)
python maintenance.py cleanup --all

# Performance report (daily)
python maintenance.py report --hours 24

# Database backup (daily)
python maintenance.py backup

# Health check (continuous)
python health_check.py
```

**Automated Maintenance:**
Set up cron jobs or scheduled tasks:
```bash
# Daily cleanup at 2 AM
0 2 * * * /path/to/maintenance.py cleanup --all

# Weekly vacuum at 3 AM Sunday
0 3 * * 0 /path/to/maintenance.py cleanup --vacuum
```

## Troubleshooting

### Common Issues

**Bot not finding codes:**
1. Check source configurations
2. Verify network connectivity
3. Review parsing logs
4. Test individual sources

**Discord notifications not working:**
1. Verify webhook URL
2. Check Discord permissions
3. Review rate limiting logs
4. Test webhook manually

**Database issues:**
1. Check disk space
2. Run integrity check: `python maintenance.py check`
3. Review database logs
4. Consider migration issues

**High resource usage:**
1. Review crawl frequency
2. Check for memory leaks
3. Optimize database queries
4. Consider rate limiting

### Log Analysis

**Important Log Patterns:**
```bash
# Find errors
grep "ERROR" logs/shift-code-bot.log

# Check code discovery
grep "codes found" logs/shift-code-bot.log

# Monitor notifications
grep "notification" logs/shift-code-bot.log

# Database operations
grep "database" logs/shift-code-bot.log
```

### Performance Tuning

**Database Optimization:**
- Regular VACUUM operations
- Proper indexing
- Query optimization
- Connection pooling

**Network Optimization:**
- Adjust rate limits
- Use connection pooling
- Implement caching
- Monitor bandwidth usage

**Memory Optimization:**
- Monitor memory usage
- Implement cleanup routines
- Optimize data structures
- Use streaming for large datasets

## Security Considerations

### Secrets Management

**Environment Variables:**
- Use secure secret storage
- Rotate credentials regularly
- Limit access permissions
- Monitor for leaks

**Docker Secrets:**
```bash
# Create secret
echo "webhook_url" | docker secret create discord_webhook -

# Use in compose
services:
  shift-code-bot:
    secrets:
      - discord_webhook
```

### Network Security

- Use HTTPS for all external connections
- Implement proper firewall rules
- Monitor network traffic
- Use VPN for sensitive deployments

### Access Control

- Run as non-root user
- Limit file permissions
- Use read-only filesystems where possible
- Implement audit logging

## Backup and Recovery

### Database Backups

**Automated Backups:**
```bash
# Daily backup
python maintenance.py backup --output "backups/daily_$(date +%Y%m%d).db"

# Retention policy (keep 30 days)
find backups/ -name "daily_*.db" -mtime +30 -delete
```

**Backup Verification:**
```bash
# Test backup integrity
python maintenance.py check --database-url "sqlite:///backups/backup.db"
```

### Disaster Recovery

**Recovery Steps:**
1. Stop the bot
2. Restore database from backup
3. Verify data integrity
4. Restart bot
5. Monitor for issues

**Recovery Testing:**
- Regular recovery drills
- Backup validation
- Documentation updates
- Team training

## Scaling Considerations

### Horizontal Scaling

The bot is designed as a single-instance application, but can be scaled:

**Multiple Regions:**
- Deploy separate instances per region
- Use different Discord channels
- Coordinate to avoid duplicates

**Load Distribution:**
- Split sources across instances
- Use message queues for coordination
- Implement leader election

### Vertical Scaling

**Resource Requirements:**
- CPU: 0.5-1 core
- Memory: 512MB-1GB
- Storage: 1GB+ (grows with data)
- Network: Minimal bandwidth

**Scaling Triggers:**
- High CPU usage
- Memory pressure
- Database size growth
- Network latency

## Updates and Migrations

### Application Updates

**Update Process:**
1. Create database backup
2. Stop current instance
3. Deploy new version
4. Run migrations
5. Start new instance
6. Verify functionality

**Rollback Process:**
1. Stop new instance
2. Restore database backup
3. Deploy previous version
4. Verify functionality

### Database Migrations

**Migration Commands:**
```bash
# Check migration status
python migrate.py status

# Run migrations
python migrate.py migrate

# Rollback to version
python migrate.py rollback 002
```

**Migration Best Practices:**
- Always backup before migrations
- Test migrations in staging
- Plan rollback procedures
- Monitor post-migration performance