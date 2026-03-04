"""
app/services/s3_service.py
All AWS S3 operations wrapped in clean helper functions.
Every function raises a plain Exception on failure so the caller
can catch it and return the appropriate HTTP response.
"""

import os
import logging
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from flask import current_app

logger = logging.getLogger(__name__)


# ── Client factory ────────────────────────────────────────────────────────────

def _client():
    """Create a fresh S3 client from the current app config."""
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
        region_name=current_app.config["AWS_REGION"],
    )


def _bucket() -> str:
    return current_app.config["AWS_S3_BUCKET"]


# ── Public helpers ────────────────────────────────────────────────────────────

def upload_pdf(file_obj: BinaryIO, s3_key: str) -> str:
    """
    Upload a file-like object to S3.

    Parameters
    ----------
    file_obj : file-like
        An open file object (e.g. from request.files).
    s3_key : str
        Destination key inside the bucket.

    Returns
    -------
    str
        The permanent (non-presigned) S3 URL.

    Raises
    ------
    Exception
        On any AWS error.
    """
    try:
        s3 = _client()
        bucket = _bucket()

        s3.upload_fileobj(
            file_obj,
            bucket,
            s3_key,
            ExtraArgs={
                "ContentType": "application/pdf",
                # Store objects as private; serve via presigned URLs
                "ServerSideEncryption": "AES256",
            },
        )

        region = current_app.config["AWS_REGION"]
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
        logger.info("Uploaded %s to s3://%s/%s", file_obj, bucket, s3_key)
        return url

    except NoCredentialsError:
        raise Exception(
            "AWS credentials are missing or invalid. "
            "Check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env."
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        raise Exception(f"S3 upload error [{code}]: {msg}")


def get_presigned_url(s3_key: str, expiry_seconds: int = 3_600) -> str:
    """
    Generate a time-limited presigned GET URL for a private S3 object.

    Parameters
    ----------
    s3_key : str
        The object key in S3.
    expiry_seconds : int
        How long the URL remains valid (default 1 hour).

    Returns
    -------
    str
        The presigned URL.
    """
    try:
        s3 = _client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": s3_key},
            ExpiresIn=expiry_seconds,
        )
        return url
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise Exception(f"S3 presign error [{code}]: {exc.response['Error']['Message']}")


def download_to_path(s3_key: str, local_path: str) -> None:
    """
    Download an S3 object to a local file path.

    Parameters
    ----------
    s3_key : str
        The object key in S3.
    local_path : str
        Absolute path where the file will be saved.
    """
    try:
        s3 = _client()
        s3.download_file(_bucket(), s3_key, local_path)
        logger.info("Downloaded s3://%s/%s → %s", _bucket(), s3_key, local_path)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise Exception(f"S3 download error [{code}]: {exc.response['Error']['Message']}")


def delete_object(s3_key: str) -> None:
    """
    Permanently delete an S3 object.

    Parameters
    ----------
    s3_key : str
        The object key to delete.
    """
    try:
        s3 = _client()
        s3.delete_object(Bucket=_bucket(), Key=s3_key)
        logger.info("Deleted s3://%s/%s", _bucket(), s3_key)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise Exception(f"S3 delete error [{code}]: {exc.response['Error']['Message']}")


def object_exists(s3_key: str) -> bool:
    """
    Return True if a key exists in the configured bucket.
    """
    try:
        _client().head_object(Bucket=_bucket(), Key=s3_key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "404":
            return False
        raise Exception(f"S3 head error: {exc.response['Error']['Message']}")


def ensure_bucket_exists() -> None:
    """
    Create the configured S3 bucket if it does not yet exist.
    Useful for local-dev or first-time setup.
    Only works if the IAM user has s3:CreateBucket permission.
    """
    s3 = _client()
    bucket = _bucket()
    region = current_app.config["AWS_REGION"]

    try:
        s3.head_bucket(Bucket=bucket)
        logger.info("S3 bucket '%s' already exists.", bucket)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            kwargs = {"Bucket": bucket}
            if region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            s3.create_bucket(**kwargs)

            # Block all public access
            s3.put_public_access_block(
                Bucket=bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
            logger.info("Created private S3 bucket '%s' in %s.", bucket, region)
        else:
            raise Exception(f"S3 bucket check failed [{code}]: {exc.response['Error']['Message']}")