#!/usr/bin/env bash
# ==============================================================================
# HIMS Production Backend Deployment Script (VPS)
# ==============================================================================
set -e

echo "🚀 [HIMS] Starting Production Deployment on Port 8070..."

# Check if .env exists
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    echo "⚠️  .env file not found! Copying from .env.example..."
    cp .env.example .env
    echo "❗ Please edit .env with your actual production credentials before proceeding."
    exit 1
  else
    echo "❌ Neither .env nor .env.example found. Aborting."
    exit 1
  fi
fi

# Ensure uploads folder exists with proper permissions
mkdir -p uploads
chmod 755 uploads

echo "📦 [HIMS] Building Docker images..."
docker compose build --pull

echo "🔄 [HIMS] Restarting containers..."
docker compose down --remove-orphans || true
docker compose up -d

echo "⏳ [HIMS] Waiting for backend API to become healthy on port 8070..."
RETRIES=15
until curl -s -f http://127.0.0.1:8070/health > /dev/null || [ $RETRIES -eq 0 ]; do
  echo "   Waiting for API to answer on port 8070... ($RETRIES retries remaining)"
  sleep 2
  RETRIES=$((RETRIES-1))
done

if [ $RETRIES -eq 0 ]; then
  echo "⚠️ Warning: Backend health endpoint did not return 200 within timeout. Checking logs:"
  docker compose logs --tail=50 hmis-api
  exit 1
fi

echo "✅ [HIMS] Backend API is up and running on port 8070!"
echo "   Healthcheck: http://127.0.0.1:8070/health"
echo "   Status:      http://127.0.0.1:8070/"
docker compose ps
