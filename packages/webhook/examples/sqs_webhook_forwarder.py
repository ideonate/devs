#!/usr/bin/env python3
"""
Example: SQS Webhook Forwarder

This is an example Lambda function that receives GitHub webhooks and forwards
them to an SQS queue for processing by devs-webhook.

Deploy this as an AWS Lambda function behind API Gateway to decouple your
webhook receiver from the processor.
"""

import json
import os
import boto3
from typing import Dict, Any

# Initialize SQS client
sqs = boto3.client('sqs')
QUEUE_URL = os.environ['SQS_QUEUE_URL']


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for forwarding GitHub webhooks to SQS.

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

        # Prepare SQS message with same format as GitHub webhook
        message = {
            'headers': {
                'x-github-event': headers.get('x-github-event', ''),
                'x-github-delivery': headers.get('x-github-delivery', ''),
                'x-hub-signature-256': headers.get('x-hub-signature-256', ''),
            },
            'payload': body  # Keep as string, devs-webhook will parse it
        }

        # Send to SQS
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        print(f"Forwarded webhook to SQS: {response['MessageId']}")

        # Return success to GitHub
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Webhook received',
                'messageId': response['MessageId']
            })
        }

    except Exception as e:
        print(f"Error forwarding webhook: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to process webhook'
            })
        }


# For local testing
if __name__ == '__main__':
    # Example event from API Gateway
    test_event = {
        'headers': {
            'x-github-event': 'issues',
            'x-github-delivery': 'test-12345',
            'x-hub-signature-256': 'sha256=...',
        },
        'body': json.dumps({
            'action': 'opened',
            'issue': {
                'number': 123,
                'title': 'Test issue',
                'body': '@your-bot-username please help!'
            },
            'repository': {
                'full_name': 'test/repo'
            }
        })
    }

    # Set queue URL for testing
    os.environ['SQS_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789/devs-webhook-queue'

    # Test the handler
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
