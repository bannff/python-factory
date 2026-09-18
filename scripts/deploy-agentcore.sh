#!/usr/bin/env bash
# Build, push, and deploy Companion-X to AgentCore.
# Usage: bash scripts/deploy-agentcore.sh
set -euo pipefail

ACCOUNT=647239283265
REGION=us-east-1
REPO=art-companion-x
PROFILE=burner
TAG=$(date -u +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)
URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:${TAG}"

echo "=== Building Docker image ==="
echo "Tag: ${TAG}"
docker build -f projects/companion_x/Dockerfile -t "${REPO}:${TAG}" .

echo ""
echo "=== Logging into ECR ==="
aws ecr get-login-password --region "${REGION}" --profile "${PROFILE}" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

echo ""
echo "=== Tagging and pushing ==="
docker tag "${REPO}:${TAG}" "${URI}"
docker push "${URI}"

echo ""
echo "=== Image pushed: ${URI} ==="
echo "Now run: python3 -u scripts/agentcore-deploy.py ${URI}"
