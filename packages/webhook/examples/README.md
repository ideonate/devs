# devs-webhook Examples

This directory contains example implementations for different deployment scenarios.

## Examples

### `sqs_webhook_forwarder.py`

An AWS Lambda function that receives GitHub webhooks and forwards them to SQS.

**Use Case**: Decouple webhook receiver from processor for better scalability.

**Deployment**:
```bash
# 1. Package the Lambda function
zip lambda.zip sqs_webhook_forwarder.py

# 2. Create Lambda function
aws lambda create-function \
  --function-name github-webhook-forwarder \
  --runtime python3.11 \
  --role arn:aws:iam::123456789:role/lambda-sqs-role \
  --handler sqs_webhook_forwarder.lambda_handler \
  --zip-file fileb://lambda.zip \
  --environment Variables={SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/queue}

# 3. Create API Gateway trigger
aws apigatewayv2 create-api \
  --name github-webhooks \
  --protocol-type HTTP \
  --target arn:aws:lambda:us-east-1:123456789:function:github-webhook-forwarder

# 4. Configure GitHub webhook to point to API Gateway URL
```

**Architecture**:
```
GitHub → API Gateway → Lambda → SQS → devs-webhook worker
```

## Running Examples

### Local Testing

Test the Lambda function locally:
```bash
python sqs_webhook_forwarder.py
```

### Production Setup

1. **Deploy Lambda** with the example code
2. **Create SQS queue** for webhook events
3. **Configure devs-webhook** to poll SQS:
   ```bash
   export TASK_SOURCE=sqs
   export AWS_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123/queue
   devs-webhook serve
   ```

## IAM Permissions

### Lambda Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:us-east-1:123456789:devs-webhook-queue"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### Worker Role

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
    }
  ]
}
```

## Further Reading

See [TASK_SOURCES.md](../docs/TASK_SOURCES.md) for detailed documentation on task sources.
