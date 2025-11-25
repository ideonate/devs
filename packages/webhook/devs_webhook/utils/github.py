"""GitHub webhook utilities."""

import hmac
import hashlib


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

    Example:
        >>> payload = b'{"action": "opened", ...}'
        >>> signature = request.headers.get('X-Hub-Signature-256')
        >>> secret = os.environ['GITHUB_WEBHOOK_SECRET']
        >>> if verify_github_signature(payload, signature, secret):
        ...     # Process webhook
        ...     pass
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
