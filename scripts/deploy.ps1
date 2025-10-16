# PowerShell deployment script for Shift Code Bot

param(
    [Parameter(Position=0)]
    [ValidateSet("deploy", "stop", "start", "restart", "status", "logs", "backup", "health")]
    [string]$Command = "deploy"
)

# Configuration
$ImageName = "shift-code-bot"
$ContainerName = "shift-code-bot"
$BackupDir = "./backups"
$DataDir = "./data"
$ConfigDir = "./config"

function Write-Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] WARNING: $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Test-Docker {
    Write-Log "Checking Docker availability..."
    
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "Docker is not installed or not in PATH"
    }
    
    try {
        docker info | Out-Null
        Write-Log "Docker is available"
    }
    catch {
        Write-Error "Docker daemon is not running"
    }
}

function Initialize-Directories {
    Write-Log "Setting up directories..."
    
    @($DataDir, $BackupDir, $ConfigDir, "./logs") | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
        }
    }
    
    Write-Log "Directories created"
}

function Test-Environment {
    if (-not (Test-Path ".env")) {
        Write-Warning ".env file not found"
        if (Test-Path ".env.example") {
            Write-Log "Copying .env.example to .env"
            Copy-Item ".env.example" ".env"
            Write-Warning "Please edit .env file with your configuration before running the bot"
        }
        else {
            Write-Error ".env.example file not found. Please create .env file manually."
        }
    }
    else {
        Write-Log "Environment configuration found"
    }
}

function Backup-Database {
    $DbPath = Join-Path $DataDir "shift_codes.db"
    
    if (Test-Path $DbPath) {
        Write-Log "Creating database backup..."
        
        $BackupFile = Join-Path $BackupDir "shift_codes_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
        Copy-Item $DbPath $BackupFile
        
        Write-Log "Database backed up to $BackupFile"
    }
    else {
        Write-Log "No existing database found, skipping backup"
    }
}

function Build-Image {
    Write-Log "Building Docker image..."
    
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed"
    }
    
    Write-Log "Docker image built successfully"
}

function Stop-Container {
    $ExistingContainer = docker ps -q -f "name=$ContainerName"
    
    if ($ExistingContainer) {
        Write-Log "Stopping existing container..."
        docker stop $ContainerName
        docker rm $ContainerName
        Write-Log "Existing container stopped and removed"
    }
    else {
        Write-Log "No existing container found"
    }
}

function Invoke-Migrations {
    Write-Log "Running database migrations..."
    
    $DataPath = (Resolve-Path $DataDir).Path
    $ConfigPath = (Resolve-Path $ConfigDir).Path
    
    docker run --rm `
        -v "${DataPath}:/app/data" `
        -v "${ConfigPath}:/app/config:ro" `
        --env-file .env `
        $ImageName `
        python migrate.py migrate
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Database migrations failed"
    }
    
    Write-Log "Database migrations completed"
}

function Start-Container {
    Write-Log "Starting new container..."
    
    $DataPath = (Resolve-Path $DataDir).Path
    $LogsPath = (Resolve-Path "./logs").Path
    $BackupPath = (Resolve-Path $BackupDir).Path
    $ConfigPath = (Resolve-Path $ConfigDir).Path
    
    docker run -d `
        --name $ContainerName `
        --restart unless-stopped `
        -v "${DataPath}:/app/data" `
        -v "${LogsPath}:/app/logs" `
        -v "${BackupPath}:/app/backups" `
        -v "${ConfigPath}:/app/config:ro" `
        -p 8080:8080 `
        --env-file .env `
        $ImageName
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to start container"
    }
    
    Write-Log "Container started successfully"
}

function Wait-ForHealth {
    Write-Log "Waiting for container to be healthy..."
    
    for ($i = 1; $i -le 30; $i++) {
        try {
            docker exec $ContainerName python health_check.py --json | Out-Null
            Write-Log "Container is healthy"
            return
        }
        catch {
            Write-Host "." -NoNewline
            Start-Sleep 2
        }
    }
    
    Write-Host ""
    Write-Error "Container failed to become healthy within 60 seconds"
}

function Show-Status {
    Write-Log "Container status:"
    docker ps -f "name=$ContainerName"
    
    Write-Log "Container logs (last 10 lines):"
    docker logs --tail 10 $ContainerName
    
    Write-Log "Health check:"
    docker exec $ContainerName python health_check.py
}

function Invoke-Deploy {
    Write-Log "Starting deployment of Shift Code Bot..."
    
    Test-Docker
    Initialize-Directories
    Test-Environment
    Backup-Database
    Build-Image
    Stop-Container
    Invoke-Migrations
    Start-Container
    Wait-ForHealth
    Show-Status
    
    Write-Log "Deployment completed successfully!"
    Write-Log "Health check endpoint: http://localhost:8080/health"
}

# Main script logic
switch ($Command) {
    "deploy" {
        Invoke-Deploy
    }
    "stop" {
        Write-Log "Stopping container..."
        docker stop $ContainerName 2>$null
        docker rm $ContainerName 2>$null
        Write-Log "Container stopped"
    }
    "start" {
        Write-Log "Starting container..."
        Start-Container
        Wait-ForHealth
        Show-Status
    }
    "restart" {
        Write-Log "Restarting container..."
        docker restart $ContainerName
        Wait-ForHealth
        Show-Status
    }
    "status" {
        Show-Status
    }
    "logs" {
        docker logs -f $ContainerName
    }
    "backup" {
        Backup-Database
    }
    "health" {
        docker exec $ContainerName python health_check.py
    }
}

Write-Host ""
Write-Host "Available commands:"
Write-Host "  deploy  - Full deployment (build, migrate, start)"
Write-Host "  stop    - Stop the container"
Write-Host "  start   - Start the container"
Write-Host "  restart - Restart the container"
Write-Host "  status  - Show container status"
Write-Host "  logs    - Show container logs"
Write-Host "  backup  - Create database backup"
Write-Host "  health  - Run health check"