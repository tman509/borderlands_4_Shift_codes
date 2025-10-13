# Borderlands 4 SHiFT Code Bot - Improved Version

An enhanced web scraping bot that tracks new Borderlands 4 SHiFT codes, deduplicates against a SQLite database, infers rewards, and sends notifications to Discord/Slack with improved reliability and performance.

## 🚀 New Features & Improvements

### Performance Enhancements
- **Connection Pooling**: Reuses HTTP connections for better performance
- **Batch Database Operations**: Inserts multiple codes in single transactions
- **Caching**: LRU cache for reward inference to reduce computation
- **Improved Code Normalization**: Better duplicate detection

### Reliability Improvements
- **Retry Logic**: Automatic retries with exponential backoff for network operations
- **Comprehensive Logging**: Structured logging with file and console output
- **Configuration Validation**: Startup validation of all configuration parameters
- **Health Checks**: Built-in health monitoring and diagnostics

### Enhanced Database Schema
- **Normalized Codes**: Better duplicate detection with normalized code storage
- **Expiry Tracking**: Support for code expiration dates
- **Activity Status**: Track active/inactive codes
- **Performance Indexes**: Optimized database queries

### Better Notifications
- **Rich Formatting**: Enhanced Discord and Slack message formatting
- **Retry Logic**: Automatic retry for failed webhook deliveries
- **Rate Limiting**: Prevents notification spam
- **Timestamps**: All notifications include discovery timestamps

### Monitoring & Observability
- **Metrics Collection**: Detailed execution metrics saved to JSON
- **Database Statistics**: Track total codes, active codes, and reward types
- **Health Check Script**: Standalone health monitoring
- **Migration Support**: Automatic database schema upgrades

## 📋 Quick Start

### Installation
```bash
# Clone and setup
git clone <repository>
cd borderlands4-shift-bot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements_improved.txt

# Setup configuration
cp .env.improved.example .env
# Edit .env with your settings
```

### Database Migration (if upgrading)
```bash
# Migrate existing database to new schema
python migrate_db.py

# Or specify custom database path
python migrate_db.py /path/to/your/database.db
```

### Configuration
Edit `.env` file with your settings:

```env
# Database
DB_PATH=./shift_codes.db

# Notifications (at least one recommended)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK

# Reddit (optional)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_SUBS=shiftcodes,Borderlands

# HTML Sources
HTML_SOURCES=https://shift.orcicorn.com/,https://mentalmars.com/game-news/borderlands-3-golden-keys/
```

### Running the Bot
```bash
# Single execution
python main_improved.py

# Check health status
python health_check.py

# Health check with JSON output
python health_check.py --json
```

## 🔧 Advanced Usage

### Scheduling with Cron
```bash
# Every 15 minutes
*/15 * * * * cd /path/to/bot && /path/to/bot/.venv/bin/python main_improved.py >> bot.log 2>&1

# Every hour with health check
0 * * * * cd /path/to/bot && /path/to/bot/.venv/bin/python health_check.py || echo "Bot unhealthy" | mail -s "Bot Alert" admin@example.com
```

### Docker Usage
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements_improved.txt .
RUN pip install -r requirements_improved.txt

COPY . .
RUN python migrate_db.py

CMD ["python", "main_improved.py"]
```

### Monitoring Integration
```bash
# Prometheus metrics (example)
python main_improved.py && cat metrics.json | jq '.execution_time_seconds' > /var/lib/prometheus/node-exporter/bot_execution_time.prom

# Nagios/Icinga check
python health_check.py --json | jq -r '.overall_status'
```

## 📊 Database Schema

The improved database includes these tables and indexes:

```sql
CREATE TABLE codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    normalized_code TEXT NOT NULL,        -- New: for better deduplication
    reward_type TEXT,
    source TEXT,
    context TEXT,
    date_found_utc TEXT,
    expiry_date TEXT,                     -- New: track code expiration
    is_active BOOLEAN DEFAULT 1,          -- New: track code status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- New: creation timestamp
);

-- Performance indexes
CREATE INDEX idx_code ON codes(code);
CREATE INDEX idx_normalized_code ON codes(normalized_code);
CREATE INDEX idx_is_active ON codes(is_active);
CREATE INDEX idx_date_found ON codes(date_found_utc);
```

## 🔍 Monitoring & Debugging

### Log Files
- `bot.log`: Comprehensive execution logs
- `metrics.json`: Latest execution metrics

### Health Check
```bash
# Basic health check
python health_check.py

# Detailed JSON output
python health_check.py --json

# Exit codes:
# 0 = Healthy
# 1 = Warning (some issues but functional)
# 2 = Unhealthy (critical issues)
```

### Database Statistics
```python
# Get stats programmatically
from main_improved import init_db, get_stats
conn = init_db()
stats = get_stats(conn)
print(stats)
```

## 🛠️ Troubleshooting

### Common Issues

**No codes found:**
- Check `health_check.py` output
- Verify HTML_SOURCES are accessible
- Check Reddit API credentials
- Review `bot.log` for errors

**Notifications not working:**
- Verify webhook URLs in `.env`
- Check network connectivity
- Review retry attempts in logs

**Database errors:**
- Run `migrate_db.py` to update schema
- Check file permissions
- Verify disk space

**Performance issues:**
- Monitor `metrics.json` execution times
- Check database size and indexes
- Review network latency to sources

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=DEBUG python main_improved.py

# Test individual components
python -c "from main_improved import health_check; print(health_check())"
```

## 📈 Performance Metrics

The bot now tracks detailed metrics:

```json
{
  "codes_found": 3,
  "sources_checked": 2,
  "execution_time_seconds": 4.23,
  "timestamp": "2024-01-15T10:30:00Z",
  "new_codes": [
    {
      "code": "ABCDE-FGHIJ-KLMNO-PQRST-UVWXY",
      "reward": "golden key",
      "source": "HTML:https://shift.orcicorn.com/"
    }
  ]
}
```

## 🔒 Security Considerations

- Never commit `.env` files to version control
- Use environment variables in production
- Regularly rotate API keys and webhook URLs
- Monitor logs for suspicious activity
- Keep dependencies updated

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Update documentation
5. Submit a pull request

## 📄 License

[Your License Here]

## 🆘 Support

- Check the health check output first
- Review `bot.log` for detailed error information
- Ensure all dependencies are installed
- Verify configuration in `.env`
- Test network connectivity to sources