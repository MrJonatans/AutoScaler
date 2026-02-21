#!/bin/bash

# AutoScaler Local Deployment Script
# Builds Docker image and deploys to Kubernetes (k3s compatible)

set -e

IMAGE_NAME="autoscaler-app"
IMAGE_TAG="latest"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building Docker image: ${FULL_IMAGE}"
docker build -t "${FULL_IMAGE}" .

echo "Deploying to Kubernetes"
kubectl apply -f deployment/

echo "Deployment complete. Check status with: kubectl get pods"