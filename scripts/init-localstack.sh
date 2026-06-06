#!/usr/bin/env bash
# Runs inside LocalStack on startup — creates the archon-docs S3 bucket.
awslocal s3 mb s3://archon-docs --region us-east-1
echo "LocalStack: archon-docs bucket created."
