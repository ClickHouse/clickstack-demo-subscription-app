#!/bin/bash

# Minimal Flask App Deployment Script

set -e

echo "🚀 Deploying Flask App..."

# Check if required files exist
if [ ! -f "docker-compose.yml" ] || [ ! -f "Dockerfile" ] || [ ! -f "flask_app.py" ]; then
    echo "❌ Missing required files (docker-compose.yml, Dockerfile, flask_app.py)"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Stop, build, and start
echo "🔄 Stopping existing containers..."
docker compose down 2>/dev/null || true

echo "🔨 Building and starting..."
docker compose up -d --build

# Wait and check
echo "⏳ Waiting for startup..."
sleep 10

if docker compose ps | grep -q "Up"; then
    echo "✅ Deployed successfully!"
    
    # Show URL
    if curl -s --max-time 2 http://169.254.169.254/latest/meta-data/public-ipv4 >/dev/null 2>&1; then
        IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
        echo "🌐 http://$IP:8000"
    else
        echo "🌐 http://localhost:8000"
    fi
else
    echo "❌ Deployment failed"
    docker compose logs --tail=10
    exit 1
fi