# Task Sources Architecture

The `devs-webhook` package supports multiple task sources for receiving webhook events. This allows flexible deployment options from simple VPS setups to scalable cloud architectures.

## Overview

The webhook handler has been refactored to separate task ingestion from task processing:

```
┌─────────────────────────────────────────────┐
│         Task Sources (pluggable)            │
├─────────────────────────────────────────────┤
│  WebhookTaskSource  │  SQSTaskSource        │
│  (FastAPI endpoint) │  (SQS polling)        │
└──────────────┬──────┴──────────┬────────────┘
               │                 │
               └────────┬────────┘
                        │
                        ▼
               ┌────────────────┐
               │ TaskProcessor  │  (parsing, validation, queuing)
               └────────┬───────┘
                        │
                        ▼
               ┌────────────────┐
               │ ContainerPool  │  (unchanged)
               └────────┬───────┘
                        │
                        ▼
               ┌────────────────┐
               │ClaudeDispatcher│  (unchanged)
               └────────────────┘
```

## Task Sources

### Webhook Source (Default)

Receives GitHub webhooks via a FastAPI HTTP endpoint.

**Use Case**: Simple VPS deployment, traditional webhook handler

**Configuration**:
```bash
export TASK_SOURCE=webhook  # or omit, it's the default
export GITHUB_WEBHOOK_SECRET=your_webhook_secret
export WEBHOOK_HOST=0.0.0.0
export WEBHOOK_PORT=8000
```

**Start Server**:
```bash
devs-webhook serve
```

**Advantages**:
- Simple deployment
- No additional infrastructure required
- Low latency

**Disadvantages**:
- Single point of failure
- Must be publicly accessible
- Webhook receiver and processor are coupled

### SQS Source

Polls AWS SQS queue for webhook events.

**Use Case**: Decoupled architecture, scalable processing, AWS deployments

**Configuration**:
```bash
export TASK_SOURCE=sqs
export AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/devs-webhook-queue
export AWS_SQS_DLQ_URL=https://sqs.us-east-1.amazonaws.com/123456789/devs-webhook-dlq  # optional
export AWS_REGION=us-east-1
```

**Start Server**:
```bash
devs-webhook serve --source sqs
```

**Advantages**:
- Decoupled webhook receiver from processor
- Can scale processors independently
- Built-in retry logic via SQS
- Dead-letter queue for failed messages
- Multiple workers can poll same queue

**Disadvantages**:
- Requires AWS infrastructure
- Additional costs (SQS)
- Slightly higher latency

## SQS Message Format

When using the SQS source, messages should contain the raw GitHub webhook payload:

```json
{
  "headers": {
    "x-github-event": "issues",
    "x-github-delivery": "12345-67890-abcde",
    "x-hub-signature-256": "sha256=..."
  },
  "payload": {
    "action": "opened",
    "issue": { ... },
    "repository": { ... }
  }
}
```

**Notes**:
- The `payload` can be a JSON object, JSON string, or base64-encoded string
- Signature verification is optional for SQS (set `sqs_verify_signatures=false` by default)
- The webhook receiver service should put messages in this format into SQS

## Deployment Patterns

### Pattern 1: Simple VPS (Webhook Source)

```
GitHub → VPS (devs-webhook) → Docker Containers
```

```bash
# On your VPS
devs-webhook serve --dev
```

### Pattern 2: Decoupled with SQS

```
GitHub → API Gateway/Lambda → SQS → devs-webhook (SQS polling) → Docker Containers
```

**Webhook Receiver** (Lambda):
```python
import json
import boto3

sqs = boto3.client('sqs')

def lambda_handler(event, context):
    # Forward GitHub webhook to SQS
    sqs.send_message(
        QueueUrl='https://sqs.us-east-1.amazonaws.com/123/devs-webhook-queue',
        MessageBody=json.dumps({
            'headers': dict(event['headers']),
            'payload': event['body']
        })
    )
    return {'statusCode': 200}
```

**Processing Worker**:
```bash
# Can run on ECS, EC2, or any server with Docker
export TASK_SOURCE=sqs
export AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/devs-webhook-queue
devs-webhook serve
```

### Pattern 3: Multiple Workers

```
                    ┌─→ Worker 1 (eamonn, harry, darren)
GitHub → SQS Queue ─┼─→ Worker 2 (eamonn, harry, darren)
                    └─→ Worker 3 (eamonn, harry, darren)
```

Run multiple instances of `devs-webhook` with SQS source for parallel processing.

## Configuration Reference

### Common Settings

```bash
# Required for all sources
export GITHUB_TOKEN=ghp_...
export GITHUB_MENTIONED_USER=your-bot-username
export ALLOWED_ORGS=org1,org2
export CONTAINER_POOL=eamonn,harry,darren
```

### Webhook Source Settings

```bash
export TASK_SOURCE=webhook
export GITHUB_WEBHOOK_SECRET=your_secret
export WEBHOOK_HOST=0.0.0.0
export WEBHOOK_PORT=8000
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=secret123  # Required in production
```

### SQS Source Settings

```bash
export TASK_SOURCE=sqs
export AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/queue
export AWS_SQS_DLQ_URL=https://sqs.us-east-1.amazonaws.com/123/dlq  # optional
export AWS_REGION=us-east-1
export SQS_WAIT_TIME_SECONDS=20  # Long polling (1-20)
```

### AWS Credentials

The SQS source uses boto3, which supports multiple authentication methods:

1. **Environment variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=AKIA...
   export AWS_SECRET_ACCESS_KEY=...
   ```

2. **IAM role** (recommended for EC2/ECS):
   - Attach IAM role with SQS permissions

3. **AWS credentials file** (`~/.aws/credentials`):
   ```ini
   [default]
   aws_access_key_id = AKIA...
   aws_secret_access_key = ...
   ```

### Required IAM Permissions

For SQS source, the IAM role/user needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:us-east-1:123456789:devs-webhook-queue"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:us-east-1:123456789:devs-webhook-dlq"
    }
  ]
}
```

## Error Handling

### Webhook Source

- Validates GitHub signature
- Returns HTTP 401 for invalid signatures
- Returns HTTP 200 for accepted webhooks
- Processes webhooks in background tasks

### SQS Source

- **Success**: Message is deleted from queue
- **Failure**:
  1. Error is logged
  2. Message is sent to DLQ (if configured)
  3. Message is deleted from main queue
- **Timeout**: Uses SQS visibility timeout (default 30s)
- **Retries**: Configure via SQS queue settings

## Testing

### Webhook Source

```bash
# Start in dev mode
devs-webhook serve --dev

# Send test event
devs-webhook test "Fix the login bug"
```

### SQS Source

```bash
# Start SQS polling
devs-webhook serve --source sqs

# Send test message to SQS
aws sqs send-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/123/devs-webhook-queue \
  --message-body '{
    "headers": {
      "x-github-event": "issues",
      "x-github-delivery": "test-123"
    },
    "payload": {
      "action": "opened",
      "issue": {...},
      "repository": {...}
    }
  }'
```

## Migration Guide

### From Webhook to SQS

1. **Deploy webhook receiver** that forwards to SQS
2. **Configure SQS queue** and DLQ
3. **Update devs-webhook config**:
   ```bash
   export TASK_SOURCE=sqs
   export AWS_SQS_QUEUE_URL=...
   ```
4. **Test with dry run**
5. **Update GitHub webhook URL** to point to new receiver
6. **Start devs-webhook** with SQS source

### Backward Compatibility

The existing webhook endpoint API remains unchanged. Simply running `devs-webhook serve` continues to work as before.

## Troubleshooting

### Webhook Source

**Issue**: Webhooks not being received
- Check firewall rules
- Verify GitHub webhook configuration
- Check webhook secret matches

**Issue**: Authentication failures
- Verify admin credentials are set correctly

### SQS Source

**Issue**: No messages being processed
- Verify SQS queue URL is correct
- Check AWS credentials and permissions
- Verify messages are being sent to queue

**Issue**: Messages going to DLQ
- Check logs for error details
- Verify message format is correct
- Check GitHub token permissions

**Issue**: High latency
- Adjust `SQS_WAIT_TIME_SECONDS` (default 20)
- Consider running multiple workers
- Check if containers are starting slowly

## Dependencies

### Webhook Source

```bash
pip install fastapi uvicorn httpx
```

### SQS Source

```bash
pip install boto3
```

### All Features

```bash
pip install devs-webhook[all]
# or
pip install -e "packages/webhook[all]"
```
