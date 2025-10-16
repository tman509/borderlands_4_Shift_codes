# Shift Code Bot

An automated system for discovering, validating, and announcing Borderlands Shift Codes to Discord communities. The bot crawls multiple web sources, extracts new codes with metadata, deduplicates against a database, and posts formatted announcements.

## Features

- 🔍 **Multi-Source Discovery**: Crawls HTML pages, RSS feeds, Reddit, and APIs
- 🎯 **Intelligent Parsing**: Advanced code extraction with confidence scoring
- 🗄️ **Smart Deduplication**: Prevents duplicate announcements
- 📢 **Discord Integration**: Rich notifications with expiration tracking
- ⚡ **High Performance**: Efficient crawling with rate limiting and caching
- 🛡️ **Robust Error Handling**: Comprehensive error recovery and monitoring
- 📊 **Observability**: Built-in metrics, health checks, and performance monitoring
- 🐳 **Docker Ready**: Production-ready containerization
- 🔧 **Easy Configuration**: JSON-based configuration with environment variables

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Discord webhook URL

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd shift-code-bot
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Discord webhook URL
   ```

3. **Deploy with Docker**
   ```bash
   # Linux/macOS
   ./scripts/deploy.sh
   
   # Windows PowerShell
   .\scripts\deploy.ps1
   ```

4. **Verify deployment**
   ```bash
   curl http://localhost:8080/health
   ```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_WEBHOOK_URL` | Yes | Discord webhook for notifications |
| `REDDIT_CLIENT_ID` | No | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | No | Reddit API client secret |
| `DATABASE_URL` | No | Database connection string |
| `LOG_LEVEL` | No | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Configuration Files

The bot uses JSON configuration files in the `config/` directory:

- `config/production.json` - Production settings
- `config/development.json` - Development settings

Example source configuration:
```json
{
  "sources": [
    {
      "id": 1,
      "name": "Gearbox Official Twitter",
      "url": "https://twitter.com/GearboxOfficial",
      "type": "html",
      "enabled": true,
      "parser_hints": {
        "selectors": [".tweet-text", ".content"],
        "fallback_regex": true
      }
    }
  ]
}
```

## Usage

### Command Line Interface

```bash
# Run in scheduled mode (default)
python main.py

# Run single cycle
python main.py --run-once

# Health check
python main.py --health-check

# Run maintenance
python main.py --maintenance

# Show statistics
python main.py --statistics --json
```

### Docker Usage

```bash
# Start the bot
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down

# Run maintenance
docker-compose exec shift-code-bot python maintenance.py cleanup --all
```

### Management Tools

**Database Migrations:**
```bash
# Check migration status
python migrate.py status

# Run migrations
python migrate.py migrate

# Rollback to version
python migrate.py rollback 002
```

**Maintenance Operations:**
```bash
# Database cleanup
python maintenance.py cleanup --all

# Performance report
python maintenance.py report --hours 24

# Create backup
python maintenance.py backup

# Health check
python health_check.py
```

## Architecture

The bot follows a modular architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Scheduler     │    │  Orchestrator   │    │ Error Handler   │
│                 │    │                 │    │                 │
│ • Cron-like     │    │ • Coordinates   │    │ • Recovery      │
│ • Job tracking  │    │ • Lifecycle     │    │ • Classification│
│ • Health checks │    │ • Dependencies  │    │ • Monitoring    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
    ┌────────────────────────────┼────────────────────────────┐
    │                            │                            │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Fetchers      │    │   Processing    │    │ Notifications   │
│                 │    │                 │    │                 │
│ • HTML/RSS      │    │ • Code parsing  │    │ • Discord       │
│ • Reddit API    │    │ • Validation    │    │ • Rate limiting │
│ • Rate limiting │    │ • Deduplication │    │ • Templates     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │    Database     │
                    │                 │
                    │ • SQLite        │
                    │ • Migrations    │
                    │ • Repositories  │
                    └─────────────────┘
```

### Key Components

- **Orchestrator**: Coordinates all bot operations and manages lifecycle
- **Scheduler**: Handles cron-like job scheduling with health monitoring
- **Fetchers**: Modular content fetching from various sources
- **Parser**: Intelligent code extraction with confidence scoring
- **Validator**: Code format validation and normalization
- **Deduplicator**: Prevents duplicate code announcements
- **Notifier**: Discord integration with rich formatting
- **Database**: SQLite with migrations and repositories
- **Error Handler**: Comprehensive error recovery and monitoring

## Monitoring

### Health Checks

The bot provides HTTP endpoints for monitoring:

- `GET /health` - Comprehensive health check
- `GET /ready` - Readiness probe (Kubernetes)
- `GET /live` - Liveness probe (Kubernetes)

### Metrics

Key metrics tracked:
- Code discovery rate
- Notification success rate
- Database performance
- Error rates
- Response times

### Logging

Structured logging with multiple formats:
- JSON format for log aggregation
- Text format for human readability
- Configurable log levels
- Correlation IDs for request tracing

## Development

### Project Structure

```
shift-code-bot/
├── src/                    # Source code
│   ├── core/              # Core application logic
│   ├── fetchers/          # Content fetching modules
│   ├── processing/        # Code processing pipeline
│   ├── notifications/     # Notification system
│   ├── storage/           # Database and repositories
│   ├── monitoring/        # Observability components
│   ├── utils/             # Utility modules
│   └── operations/        # Maintenance operations
├── config/                # Configuration files
├── docs/                  # Documentation
├── scripts/               # Deployment scripts
├── tests/                 # Test suite
├── docker-compose.yml     # Docker orchestration
├── Dockerfile            # Container definition
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

### Local Development

1. **Setup environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate     # Windows
   
   pip install -r requirements.txt
   ```

2. **Configure for development**
   ```bash
   cp .env.example .env
   # Edit .env for development settings
   ```

3. **Run migrations**
   ```bash
   python migrate.py migrate
   ```

4. **Start development server**
   ```bash
   python main.py --config config/development.json --log-level DEBUG
   ```

### Testing

```bash
# Run unit tests
python -m pytest tests/unit/

# Run integration tests
python -m pytest tests/integration/

# Run with coverage
python -m pytest --cov=src tests/
```

## Deployment

### Production Deployment

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for comprehensive deployment guide.

**Quick production setup:**
1. Configure production environment variables
2. Use `config/production.json` configuration
3. Deploy with Docker Compose
4. Set up monitoring and alerting
5. Configure backup procedures

### Scaling Considerations

- **Single Instance**: Designed for single-instance deployment
- **Resource Requirements**: 0.5 CPU, 512MB RAM, 1GB storage
- **Database**: SQLite suitable for moderate loads
- **Horizontal Scaling**: Multiple instances with coordination

## Operations

### Daily Operations

- Monitor health status
- Review performance reports
- Check error logs
- Verify notifications

### Weekly Maintenance

- Database cleanup
- Performance analysis
- Backup verification
- Configuration review

See [OPERATIONS.md](docs/OPERATIONS.md) for detailed operations guide.

## Troubleshooting

### Common Issues

**Bot not finding codes:**
1. Check source configurations
2. Verify network connectivity
3. Review parsing logs
4. Test individual sources

**Discord notifications failing:**
1. Verify webhook URL
2. Check Discord permissions
3. Review rate limiting
4. Test webhook manually

**Performance issues:**
1. Run database maintenance
2. Check resource usage
3. Review error rates
4. Optimize configurations

### Getting Help

1. Check the logs: `docker logs shift-code-bot`
2. Run health check: `python health_check.py`
3. Review documentation in `docs/`
4. Check GitHub issues

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add docstrings to all functions
- Include type hints
- Write tests for new features
- Update documentation

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Gearbox Software for Borderlands and Shift Codes
- Discord for webhook API
- Reddit for API access
- Open source community for tools and libraries

## Changelog

### Version 2.0.0
- Complete rewrite with modular architecture
- Enhanced error handling and recovery
- Comprehensive monitoring and observability
- Docker containerization
- Advanced code parsing with confidence scoring
- Improved notification system
- Database migrations and maintenance tools

### Version 1.0.0
- Initial release
- Basic code discovery and notification
- Simple Discord integration
- SQLite database storage