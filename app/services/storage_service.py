"""Storage service for Supabase S3-compatible bucket operations."""

import logging
import tempfile
import os
from typing import Optional
import httpx
import boto3
from botocore.config import Config as BotoConfig

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for Supabase S3-compatible Storage operations."""
    
    def __init__(self):
        self._client = None
        self._bucket_name = settings.SUPABASE_BUCKET
    
    @property
    def client(self):
        """Lazy initialization of S3 client."""
        if self._client is None:
            if not settings.SUPABASE_S3_ACCESS_KEY or not settings.SUPABASE_S3_SECRET_KEY:
                raise ValueError(
                    "Supabase S3 credentials not configured. "
                    "Set SUPABASE_S3_ACCESS_KEY and SUPABASE_S3_SECRET_KEY in .env"
                )
            
            if not settings.SUPABASE_S3_ENDPOINT:
                raise ValueError(
                    "Supabase S3 endpoint not configured. "
                    "Set SUPABASE_S3_ENDPOINT in .env"
                )
            
            self._client = boto3.client(
                's3',
                endpoint_url=settings.SUPABASE_S3_ENDPOINT,
                aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY,
                aws_secret_access_key=settings.SUPABASE_S3_SECRET_KEY,
                region_name=settings.SUPABASE_S3_REGION,
                config=BotoConfig(signature_version='s3v4')
            )
            logger.info("S3-compatible client initialized for Supabase Storage")
        
        return self._client
    
    def _get_public_url(self, path: str) -> str:
        """
        Generate public URL for a file.
        
        The public URL format for Supabase Storage is:
        https://<project>.supabase.co/storage/v1/object/public/<bucket>/<path>
        """
        # Extract project URL from endpoint
        # Endpoint: https://xxx.storage.supabase.co/storage/v1/s3
        # Public URL: https://xxx.supabase.co/storage/v1/object/public/bucket/path
        endpoint = settings.SUPABASE_S3_ENDPOINT
        if endpoint:
            # Remove /storage/v1/s3 suffix and .storage from subdomain
            base_url = endpoint.replace("/storage/v1/s3", "").replace(".storage.", ".")
            return f"{base_url}/storage/v1/object/public/{self._bucket_name}/{path}"
        return path
    
    async def upload_file(
        self,
        content: bytes,
        path: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to Supabase Storage.
        
        Args:
            content: File content as bytes
            path: Storage path (e.g., "user_id/filename.pdf")
            content_type: MIME type of the file
        
        Returns:
            Public URL of the uploaded file
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Upload to S3-compatible storage
            self.client.put_object(
                Bucket=self._bucket_name,
                Key=path,
                Body=content,
                **extra_args
            )
            
            logger.info(f"File uploaded to Supabase Storage: {path}")
            
            # Return public URL
            public_url = self._get_public_url(path)
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload file to Supabase: {e}")
            raise
    
    async def download_file(self, path: str) -> bytes:
        """
        Download a file from Supabase Storage.
        
        Args:
            path: Storage path or full URL
        
        Returns:
            File content as bytes
        """
        try:
            # If it's a full URL, download directly via HTTP
            if path.startswith("http"):
                async with httpx.AsyncClient() as http_client:
                    response = await http_client.get(path)
                    response.raise_for_status()
                    return response.content
            else:
                # Download using S3 client
                response = self.client.get_object(
                    Bucket=self._bucket_name,
                    Key=path
                )
                return response['Body'].read()
                
        except Exception as e:
            logger.error(f"Failed to download file from Supabase: {e}")
            raise
    
    async def download_to_temp_file(self, path: str, suffix: str = "") -> str:
        """
        Download a file to a temporary location.
        
        Args:
            path: Storage path or URL
            suffix: File suffix (e.g., ".pdf")
        
        Returns:
            Path to temporary file
        """
        content = await self.download_file(path)
        
        # Create temp file
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        
        logger.info(f"Downloaded to temp file: {temp_path}")
        return temp_path
    
    async def delete_file(self, path: str) -> bool:
        """
        Delete a file from Supabase Storage.
        
        Args:
            path: Storage path or full URL
        
        Returns:
            True if deleted successfully
        """
        try:
            # If it's a full URL, extract the path
            if path.startswith("http"):
                # Extract path from URL
                # URL format: https://xxx.supabase.co/storage/v1/object/public/bucket/actual/path
                bucket_marker = f"/object/public/{self._bucket_name}/"
                if bucket_marker in path:
                    path = path.split(bucket_marker)[1]
                else:
                    logger.warning(f"Could not extract path from URL: {path}")
                    return False
            
            self.client.delete_object(
                Bucket=self._bucket_name,
                Key=path
            )
            logger.info(f"File deleted from Supabase: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file from Supabase: {e}")
            return False
    
    def is_supabase_url(self, path: str) -> bool:
        """Check if a path is a Supabase URL."""
        return path.startswith("http") and "supabase" in path


# Global storage service instance
storage_service = StorageService()
