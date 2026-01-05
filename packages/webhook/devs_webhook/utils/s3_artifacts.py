"""S3 artifact upload utilities for test results."""

import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class S3ArtifactUploader:
    """Uploads test artifacts to S3 as tar archives."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "devs-artifacts",
        region: str = "us-east-1"
    ):
        """Initialize S3 artifact uploader.

        Args:
            bucket: S3 bucket name
            prefix: S3 key prefix for artifacts
            region: AWS region
        """
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
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

    def upload_directory_as_tar(
        self,
        directory: Path,
        repo_name: str,
        task_id: str,
        dev_name: str,
        task_type: str = "tests"
    ) -> Optional[str]:
        """Upload a directory as a tar.gz archive to S3.

        Args:
            directory: Path to directory to upload
            repo_name: Repository name (owner/repo format)
            task_id: Unique task identifier
            dev_name: Container/dev name
            task_type: Type of task (e.g., "tests", "claude")

        Returns:
            S3 URL of the uploaded artifact, or None if upload failed
        """
        if not directory.exists():
            logger.warning("Bridge directory does not exist, skipping artifact upload",
                          directory=str(directory))
            return None

        # Check if directory has any contents
        contents = list(directory.iterdir())
        if not contents:
            logger.info("Bridge directory is empty, skipping artifact upload",
                       directory=str(directory))
            return None

        # Generate S3 key with timestamp for uniqueness
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        safe_repo_name = repo_name.replace("/", "-")
        s3_key = f"{self.prefix}/{safe_repo_name}/{task_type}/{timestamp}-{task_id}-{dev_name}.tar.gz"

        try:
            s3_client = self._get_s3_client()

            # Create tar.gz in a temporary file
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            try:
                # Create tar archive
                with tarfile.open(tmp_path, "w:gz") as tar:
                    tar.add(directory, arcname=directory.name)

                # Upload to S3
                logger.info("Uploading artifacts to S3",
                           bucket=self.bucket,
                           key=s3_key,
                           directory=str(directory),
                           file_count=len(contents))

                s3_client.upload_file(
                    str(tmp_path),
                    self.bucket,
                    s3_key
                )

                s3_url = f"s3://{self.bucket}/{s3_key}"
                logger.info("Artifact upload successful",
                           s3_url=s3_url,
                           task_id=task_id)

                return s3_url

            finally:
                # Clean up temporary file
                if tmp_path.exists():
                    tmp_path.unlink()

        except ImportError:
            # boto3 not installed - already logged
            return None
        except Exception as e:
            logger.error("Failed to upload artifacts to S3",
                        bucket=self.bucket,
                        key=s3_key,
                        error=str(e),
                        exc_info=True)
            return None


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
        region=config.aws_region
    )
