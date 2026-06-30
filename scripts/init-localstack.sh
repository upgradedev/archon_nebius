#!/usr/bin/env bash
# Runs inside LocalStack on startup — creates the archon-bucket S3 bucket.
# Name matches the anchor in docker-compose.yml and .env.example so the local
# stack writes to a bucket that actually exists (no Nebius account needed).
awslocal s3 mb s3://archon-bucket --region us-east-1
echo "LocalStack: archon-bucket bucket created."
