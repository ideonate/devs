#!/usr/bin/env python3
"""
Example: SQS Webhook Forwarder

This is an example Lambda function that receives GitHub webhooks and forwards
them to an SQS queue for processing by devs-webhook.

Deploy this as an AWS Lambda function behind API Gateway to decouple your
webhook receiver from the processor.

IMPORTANT: This Lambda validates GitHub webhook signatures before forwarding
to SQS. This is the first line of defense against unauthorized webhook requests.
"""

import json
import os
import hmac
import hashlib
import boto3
from typing import Dict, Any

# Initialize SQS client
sqs = boto3.client('sqs')
QUEUE_URL = os.environ['SQS_QUEUE_URL']
WEBHOOK_SECRET = os.environ['GITHUB_WEBHOOK_SECRET']


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature using HMAC-SHA256.

    GitHub signs webhook payloads with HMAC-SHA256 using the webhook secret.
    The signature is sent in the X-Hub-Signature-256 header as 'sha256=<hex>'.

    Args:
        payload: Raw webhook payload bytes (must be the exact bytes received)
        signature: GitHub signature header (e.g., 'sha256=abc123...')
        secret: Webhook secret configured in GitHub

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature:
        return False

    if not signature.startswith("sha256="):
        return False

    # Compute expected signature
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(signature, expected_signature)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for forwarding GitHub webhooks to SQS.

    This function validates the GitHub webhook signature before forwarding
    to SQS. This is the first line of defense against unauthorized requests.

    Args:
        event: API Gateway proxy event containing the webhook
        context: Lambda context (unused)

    Returns:
        API Gateway response
    """
    try:
        # Extract headers and body from API Gateway event
        headers = event.get('headers', {})
        body = event.get('body', '')

        # Get signature from headers (API Gateway may lowercase header names)
        signature = (
            headers.get('x-hub-signature-256') or
            headers.get('X-Hub-Signature-256', '')
        )

        # Validate GitHub webhook signature BEFORE queuing
        if not verify_github_signature(body.encode('utf-8'), signature, WEBHOOK_SECRET):
            print(f"Invalid webhook signature - rejecting request")
            print(f"Signature received: {signature}")
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Invalid webhook signature'
                })
            }

        print(f"Webhook signature validated successfully")

        # Extract event type for logging
        event_type = headers.get('x-github-event') or headers.get('X-GitHub-Event', 'unknown')
        delivery_id = headers.get('x-github-delivery') or headers.get('X-GitHub-Delivery', 'unknown')

        # Prepare SQS message with same format as GitHub webhook
        message = {
            'headers': {
                'x-github-event': event_type,
                'x-github-delivery': delivery_id,
                'x-hub-signature-256': signature,
            },
            'payload': body  # Keep as string, devs-webhook will parse it
        }

        # Send to SQS (only if signature is valid)
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        print(f"Forwarded {event_type} webhook to SQS: {response['MessageId']}")

        # Return success to GitHub
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Webhook received and validated',
                'messageId': response['MessageId']
            })
        }

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to process webhook'
            })
        }


# For local testing
if __name__ == '__main__':
    # Set environment variables for testing
    os.environ['SQS_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789/devs-webhook-queue'
    os.environ['GITHUB_WEBHOOK_SECRET'] = 'test-secret-12345'

    # Create test payload
    test_payload = {
        'action': 'opened',
        'issue': {
            'number': 123,
            'title': 'Test issue',
            'body': '@your-bot-username please help!'
        },
        'repository': {
            'full_name': 'test/repo'
        }
    }
    test_body = json.dumps(test_payload)

    # Generate valid signature for testing
    test_signature = "sha256=" + hmac.new(
        os.environ['GITHUB_WEBHOOK_SECRET'].encode('utf-8'),
        test_body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Example event from API Gateway
    test_event = {
        'headers': {
            'x-github-event': 'issues',
            'x-github-delivery': 'test-12345',
            'x-hub-signature-256': test_signature,
        },
        'body': test_body
    }

    print("Testing Lambda with valid signature...")
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))

    # Test with invalid signature
    print("\nTesting Lambda with invalid signature...")
    test_event_invalid = test_event.copy()
    test_event_invalid['headers'] = test_event['headers'].copy()
    test_event_invalid['headers']['x-hub-signature-256'] = 'sha256=invalid'
    result_invalid = lambda_handler(test_event_invalid, None)
    print(json.dumps(result_invalid, indent=2))
