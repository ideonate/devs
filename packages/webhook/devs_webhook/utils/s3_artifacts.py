"""S3 artifact upload utilities for test results."""

import tarfile
import tempfile
import secrets
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import structlog

logger = structlog.get_logger()


def generate_secret_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token for URL obscurity.

    Args:
        length: Length of the token in characters (uses URL-safe base64)

    Returns:
        Random URL-safe token string
    """
    return secrets.token_urlsafe(length)


class S3ArtifactUploader:
    """Uploads test artifacts to S3 as tar archives."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "devs-artifacts",
        region: str = "us-east-1",
        base_url: Optional[str] = None
    ):
        """Initialize S3 artifact uploader.

        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix for artifacts
            region: AWS region
            base_url: Base URL for constructing public artifact URLs (e.g., CloudFront URL).
                      If not provided, S3 URLs (s3://) are returned.
        """
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self.base_url = base_url.rstrip('/') if base_url else None
        self._s3_client = None

    def _get_s3_client(self):
        """Lazily initialize boto3 S3 client.

        Returns:
            boto3 S3 client

        Raises:
            ImportError: If boto3 is not installed
        """
        if self._s3_client is None:
            try:
                import boto3
                self._s3_client = boto3.client('s3', region_name=self.region)
            except ImportError:
                logger.error("boto3 not installed - required for S3 artifact uploads")
                raise ImportError(
                    "boto3 is required for S3 artifact uploads. "
                    "Install with: pip install boto3"
                )
        return self._s3_client

    def _generate_s3_key(
        self,
        repo_name: str,
        task_type: str,
        filename: str
    ) -> str:
        """Generate S3 key with secret token for URL obscurity.

        Args:
            repo_name: Repository name (owner/repo format)
            task_type: Type of task (e.g., "tests", "claude")
            filename: Filename including extension

        Returns:
            S3 key with format: prefix/repo-name/task-type/secret-token/filename
        """
        secret_token = generate_secret_token(32)
        safe_repo_name = repo_name.replace("/", "-")
        return f"{self.prefix}/{safe_repo_name}/{task_type}/{secret_token}/{filename}"

    def _upload_to_s3(
        self,
        local_path: Path,
        s3_key: str,
        description: str,
        task_id: str,
        extra_log_fields: Optional[dict] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Upload a local file to S3 and return URLs.

        Args:
            local_path: Path to the local file to upload
            s3_key: S3 key to upload to
            description: Description for logging (e.g., "artifacts", "file")
            task_id: Task identifier for logging
            extra_log_fields: Additional fields to include in log messages

        Returns:
            Tuple of (s3_url, public_url):
                - s3_url: S3 URL of the uploaded file (s3://bucket/key)
                - public_url: Public HTTP URL if base_url is configured, None otherwise
            Both are None if upload failed.
        """
        log_fields = extra_log_fields or {}

        try:
            s3_client = self._get_s3_client()

            logger.info(f"Uploading {description} to S3",
                       bucket=self.bucket,
                       key=s3_key,
                       **log_fields)

            s3_client.upload_file(
                str(local_path),
                self.bucket,
                s3_key
            )

            s3_url = f"s3://{self.bucket}/{s3_key}"
            public_url = f"{self.base_url}/{s3_key}" if self.base_url else None

            logger.info(f"{description.capitalize()} upload successful",
                       s3_url=s3_url,
                       public_url=public_url,
                       task_id=task_id)

            return s3_url, public_url

        except ImportError:
            # boto3 not installed - already logged
            return None, None
        except Exception as e:
            logger.error(f"Failed to upload {description} to S3",
                        bucket=self.bucket,
                        key=s3_key,
                        error=str(e),
                        exc_info=True)
            return None, None

    def upload_directory_as_tar(
        self,
        directory: Path,
        repo_name: str,
        task_id: str,
        dev_name: str,
        task_type: str = "tests"
    ) -> Tuple[Optional[str], Optional[str]]:
        """Upload a directory as a tar.gz archive to S3.

        The S3 key includes a cryptographically secure random token to make
        the URL difficult to guess, providing security through obscurity for
        sharing artifact URLs with trusted users.

        Args:
            directory: Path to directory to upload
            repo_name: Repository name (owner/repo format)
            task_id: Unique task identifier
            dev_name: Container/dev name
            task_type: Type of task (e.g., "tests", "claude")

        Returns:
            Tuple of (s3_url, public_url):
                - s3_url: S3 URL of the uploaded artifact (s3://bucket/key)
                - public_url: Public HTTP URL if base_url is configured, None otherwise
            Both are None if upload failed or was skipped.
        """
        if not directory.exists():
            logger.warning("Bridge directory does not exist, skipping artifact upload",
                          directory=str(directory))
            return None, None

        # Check if directory has any contents
        contents = list(directory.iterdir())
        if not contents:
            logger.info("Bridge directory is empty, skipping artifact upload",
                       directory=str(directory))
            return None, None

        # Generate S3 key
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{task_id}-{dev_name}.tar.gz"
        s3_key = self._generate_s3_key(repo_name, task_type, filename)

        # Create tar.gz in a temporary file
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            # Create tar archive
            with tarfile.open(tmp_path, "w:gz") as tar:
                tar.add(directory, arcname=directory.name)

            return self._upload_to_s3(
                local_path=tmp_path,
                s3_key=s3_key,
                description="artifacts",
                task_id=task_id,
                extra_log_fields={"directory": str(directory), "file_count": len(contents)}
            )
        finally:
            # Clean up temporary file
            if tmp_path.exists():
                tmp_path.unlink()

    def upload_file(
        self,
        file_path: Path,
        repo_name: str,
        task_id: str,
        dev_name: str,
        task_type: str = "tests",
        file_suffix: str = ""
    ) -> Tuple[Optional[str], Optional[str]]:
        """Upload a single file to S3.

        The S3 key includes a cryptographically secure random token to make
        the URL difficult to guess, providing security through obscurity.

        Args:
            file_path: Path to file to upload
            repo_name: Repository name (owner/repo format)
            task_id: Unique task identifier
            dev_name: Container/dev name
            task_type: Type of task (e.g., "tests", "claude")
            file_suffix: Optional suffix to add before file extension (e.g., "-worker")

        Returns:
            Tuple of (s3_url, public_url):
                - s3_url: S3 URL of the uploaded file (s3://bucket/key)
                - public_url: Public HTTP URL if base_url is configured, None otherwise
            Both are None if upload failed or was skipped.
        """
        if not file_path.exists():
            logger.warning("File does not exist, skipping upload",
                          file_path=str(file_path))
            return None, None

        # Generate S3 key
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        file_ext = file_path.suffix or ".log"
        filename = f"{timestamp}-{task_id}-{dev_name}{file_suffix}{file_ext}"
        s3_key = self._generate_s3_key(repo_name, task_type, filename)

        return self._upload_to_s3(
            local_path=file_path,
            s3_key=s3_key,
            description="file",
            task_id=task_id,
            extra_log_fields={"file_path": str(file_path)}
        )


def create_s3_uploader_from_config(config) -> Optional[S3ArtifactUploader]:
    """Create an S3ArtifactUploader from webhook config if configured.

    Args:
        config: WebhookConfig instance

    Returns:
        S3ArtifactUploader instance if S3 is configured, None otherwise
    """
    if not config.has_s3_artifact_upload():
        return None

    return S3ArtifactUploader(
        bucket=config.aws_s3_artifact_bucket,
        prefix=config.aws_s3_artifact_prefix,
        region=config.aws_region,
        base_url=getattr(config, 'aws_s3_artifact_base_url', None)
    )
