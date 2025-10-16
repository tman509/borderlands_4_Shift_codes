# Multi-stage build for Shift Code Bot
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r shiftbot && useradd -r -g shiftbot shiftbot

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /home/shiftbot/.local

# Copy application code
COPY src/ ./src/
COPY migrate.py .
COPY maintenance.py .
COPY health_check.py .

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/backups && \
    chown -R shiftbot:shiftbot /app

# Switch to non-root user
USER shiftbot

# Add local bin to PATH
ENV PATH=/home/shiftbot/.local/bin:$PATH

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:///data/shift_codes.db
ENV LOG_LEVEL=INFO

# Expose health check port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python health_check.py --port 8080 || exit 1

# Default command
CMD ["python", "-m", "src.main"]