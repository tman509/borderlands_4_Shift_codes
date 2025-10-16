#!/bin/bash
# Deployment script for Shift Code Bot

set -e

# Configuration
IMAGE_NAME="shift-code-bot"
CONTAINER_NAME="shift-code-bot"
BACKUP_DIR="./backups"
DATA_DIR="./data"
CONFIG_DIR="./config"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed or not in PATH"
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running"
    fi
    
    log "Docker is available"
}

# Create necessary directories
setup_directories() {
    log "Setting up directories..."
    
    mkdir -p "$DATA_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "./logs"
    
    log "Directories created"
}

# Check if .env file exists
check_environment() {
    if [ ! -f ".env" ]; then
        warn ".env file not found"
        if [ -f ".env.example" ]; then
            log "Copying .env.example to .env"
            cp .env.example .env
            warn "Please edit .env file with your configuration before running the bot"
        else
            error ".env.example file not found. Please create .env file manually."
        fi
    else
        log "Environment configuration found"
    fi
}

# Create backup of current database
backup_database() {
    if [ -f "$DATA_DIR/shift_codes.db" ]; then
        log "Creating database backup..."
        
        BACKUP_FILE="$BACKUP_DIR/shift_codes_$(date +%Y%m%d_%H%M%S).db"
        cp "$DATA_DIR/shift_codes.db" "$BACKUP_FILE"
        
        log "Database backed up to $BACKUP_FILE"
    else
        log "No existing database found, skipping backup"
    fi
}

# Build Docker image
build_image() {
    log "Building Docker image..."
    
    docker build -t "$IMAGE_NAME" .
    
    log "Docker image built successfully"
}

# Stop existing container
stop_container() {
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        log "Stopping existing container..."
        docker stop "$CONTAINER_NAME"
        docker rm "$CONTAINER_NAME"
        log "Existing container stopped and removed"
    else
        log "No existing container found"
    fi
}

# Run database migrations
run_migrations() {
    log "Running database migrations..."
    
    docker run --rm \
        -v "$(pwd)/$DATA_DIR:/app/data" \
        -v "$(pwd)/$CONFIG_DIR:/app/config:ro" \
        --env-file .env \
        "$IMAGE_NAME" \
        python migrate.py migrate
    
    log "Database migrations completed"
}

# Start new container
start_container() {
    log "Starting new container..."
    
    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -v "$(pwd)/$DATA_DIR:/app/data" \
        -v "$(pwd)/logs:/app/logs" \
        -v "$(pwd)/$BACKUP_DIR:/app/backups" \
        -v "$(pwd)/$CONFIG_DIR:/app/config:ro" \
        -p 8080:8080 \
        --env-file .env \
        "$IMAGE_NAME"
    
    log "Container started successfully"
}

# Wait for container to be healthy
wait_for_health() {
    log "Waiting for container to be healthy..."
    
    for i in {1..30}; do
        if docker exec "$CONTAINER_NAME" python health_check.py --json > /dev/null 2>&1; then
            log "Container is healthy"
            return 0
        fi
        
        echo -n "."
        sleep 2
    done
    
    error "Container failed to become healthy within 60 seconds"
}

# Show container status
show_status() {
    log "Container status:"
    docker ps -f name="$CONTAINER_NAME"
    
    log "Container logs (last 10 lines):"
    docker logs --tail 10 "$CONTAINER_NAME"
    
    log "Health check:"
    docker exec "$CONTAINER_NAME" python health_check.py
}

# Main deployment function
deploy() {
    log "Starting deployment of Shift Code Bot..."
    
    check_docker
    setup_directories
    check_environment
    backup_database
    build_image
    stop_container
    run_migrations
    start_container
    wait_for_health
    show_status
    
    log "Deployment completed successfully!"
    log "Health check endpoint: http://localhost:8080/health"
}

# Handle command line arguments
case "${1:-deploy}" in
    "deploy")
        deploy
        ;;
    "stop")
        log "Stopping container..."
        docker stop "$CONTAINER_NAME" || true
        docker rm "$CONTAINER_NAME" || true
        log "Container stopped"
        ;;
    "start")
        log "Starting container..."
        start_container
        wait_for_health
        show_status
        ;;
    "restart")
        log "Restarting container..."
        docker restart "$CONTAINER_NAME"
        wait_for_health
        show_status
        ;;
    "status")
        show_status
        ;;
    "logs")
        docker logs -f "$CONTAINER_NAME"
        ;;
    "backup")
        backup_database
        ;;
    "health")
        docker exec "$CONTAINER_NAME" python health_check.py
        ;;
    *)
        echo "Usage: $0 {deploy|stop|start|restart|status|logs|backup|health}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Full deployment (build, migrate, start)"
        echo "  stop    - Stop the container"
        echo "  start   - Start the container"
        echo "  restart - Restart the container"
        echo "  status  - Show container status"
        echo "  logs    - Show container logs"
        echo "  backup  - Create database backup"
        echo "  health  - Run health check"
        exit 1
        ;;
esac