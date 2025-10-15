# Shift Code Bot v2.0

An automated system for discovering, validating, and announcing Borderlands Shift Codes to Discord communities.

## Features

- **Multi-source crawling**: HTML pages, RSS feeds, Reddit, and API endpoints
- **Intelligent parsing**: Multiple regex patterns with fallback strategies
- **Smart deduplication**: Canonical code normalization and metadata comparison
- **Discord integration**: Rich message formatting with rate limiting
- **Robust error handling**: Retry logic with exponential backoff
- **Comprehensive logging**: Structured JSON logging with metrics
- **Flexible configuration**: Environment variables and JSON config files

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements-new.txt
   ```

2. **Create configuration**:
   ```bash
   cp config.example.json config.json
   # Edit config.json with your settings
   ```

3. **Run the bot**:
   ```bash
   python main.py --config config.json
   ```

## Configuration

The bot uses a JSON configuration file with the following structure:

- `database_url`: SQLite database path
- `sources`: List of sources to crawl (HTML, RSS, Reddit, API)
- `discord_channels`: Discord webhook configurations
- `notification_settings`: Rate limiting and notification preferences
- `scheduler_config`: Cron schedule and execution settings
- `observability_config`: Logging and monitoring settings

See `config.example.json` for a complete example.

## Environment Variables

Key environment variables (override config file):

- `DATABASE_URL`: Database connection string
- `DISCORD_WEBHOOK_URL`: Discord webhook URL
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `ENVIRONMENT`: Environment name (development, staging, production)

## Architecture

The bot follows a modular architecture:

```
src/
├── models/          # Data models and structures
├── core/            # Core orchestration and configuration
├── fetchers/        # Source-specific content fetchers
├── processing/      # Code parsing and validation
├── storage/         # Database and caching (TODO)
├── notifications/   # Discord and webhook notifications (TODO)
└── utils/           # Utility functions and helpers
```

## Development Status

This is a complete rewrite of the original bot with improved architecture. Current status:

✅ **Completed**:
- Project structure and core interfaces
- Configuration management with environment overrides
- Base fetcher interface with rate limiting
- Code parsing with multiple patterns and metadata extraction
- Code validation and normalization
- Structured logging with JSON formatting
- Retry utilities with exponential backoff

🚧 **In Progress**:
- Database schema and repository layer
- HTML and RSS fetchers
- Deduplication engine
- Discord notification system
- Scheduler and orchestration

📋 **Planned**:
- Reddit API integration
- Expiration reminder system
- Metrics collection and health monitoring
- Comprehensive test suite
- Docker containerization

## Usage Examples

### Basic execution:
```bash
python main.py
```

### With custom config and logging:
```bash
python main.py --config my-config.json --log-level DEBUG --log-format json
```

### Health check:
```bash
python main.py --health-check
```

### With log file:
```bash
python main.py --log-file bot.log
```

## Contributing

This project follows the specification-driven development approach. See the `.kiro/specs/shift-code-bot/` directory for detailed requirements, design, and implementation tasks.

## License

MIT License - see LICENSE file for details.