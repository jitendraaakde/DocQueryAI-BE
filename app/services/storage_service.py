"""Storage service for Supabase S3-compatible bucket operations using direct HTTP calls."""

import logging
import tempfile
import os
from typing import Optional
from datetime import datetime, timezone
import hashlib
import hmac
from urllib.parse import quote, urlencode
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AWSV4Signer:
    """AWS Signature Version 4 signer for S3-compatible APIs."""
    
    def __init__(self, access_key: str, secret_key: str, region: str, service: str = 's3'):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.service = service
    
    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
    
    def _get_signature_key(self, date_stamp: str) -> bytes:
        k_date = self._sign(('AWS4' + self.secret_key).encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing
    
    def get_headers(
        self, 
        method: str, 
        url: str, 
        headers: dict, 
        payload: bytes = b''
    ) -> dict:
        """Generate signed headers for an AWS V4 request."""
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = quote(parsed.path, safe='/')
        canonical_querystring = parsed.query if parsed.query else ''
        
        # Create timestamps
        t = datetime.now(timezone.utc)
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = t.strftime('%Y%m%d')
        
        # Calculate payload hash
        payload_hash = hashlib.sha256(payload).hexdigest()
        
        # Build headers dict
        signed_headers = {
            'host': host,
            'x-amz-content-sha256': payload_hash,
            'x-amz-date': amz_date,
        }
        
        # Add content-type if present
        if 'Content-Type' in headers:
            signed_headers['content-type'] = headers['Content-Type']
        
        # Create canonical headers string
        canonical_headers = ''
        for key in sorted(signed_headers.keys()):
            canonical_headers += f'{key}:{signed_headers[key]}\n'
        
        signed_headers_str = ';'.join(sorted(signed_headers.keys()))
        
        # Create canonical request
        canonical_request = '\n'.join([
            method,
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers_str,
            payload_hash
        ])
        
        # Create string to sign
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f'{date_stamp}/{self.region}/{self.service}/aws4_request'
        string_to_sign = '\n'.join([
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        ])
        
        # Calculate signature
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # Create authorization header
        authorization_header = (
            f'{algorithm} Credential={self.access_key}/{credential_scope}, '
            f'SignedHeaders={signed_headers_str}, Signature={signature}'
        )
        
        # Build final headers
        result_headers = {
            'Host': host,
            'X-Amz-Date': amz_date,
            'X-Amz-Content-SHA256': payload_hash,
            'Authorization': authorization_header
        }
        
        if 'Content-Type' in headers:
            result_headers['Content-Type'] = headers['Content-Type']
        
        return result_headers


class StorageService:
    """Service for Supabase S3-compatible Storage operations using direct HTTP."""
    
    def __init__(self):
        self._signer: Optional[AWSV4Signer] = None
        self._bucket_name = settings.SUPABASE_BUCKET
        self._endpoint = settings.SUPABASE_S3_ENDPOINT
    
    @property
    def signer(self) -> AWSV4Signer:
        """Lazy initialization of AWS V4 signer."""
        if self._signer is None:
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
            
            self._signer = AWSV4Signer(
                access_key=settings.SUPABASE_S3_ACCESS_KEY,
                secret_key=settings.SUPABASE_S3_SECRET_KEY,
                region=settings.SUPABASE_S3_REGION or 'us-east-1'
            )
            logger.info("S3-compatible signer initialized for Supabase Storage")
        
        return self._signer
    
    def _get_object_url(self, path: str) -> str:
        """Get the S3 API URL for an object."""
        return f"{self._endpoint}/{self._bucket_name}/{path}"
    
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
            url = self._get_object_url(path)
            
            headers = {}
            if content_type:
                headers['Content-Type'] = content_type
            
            # Get signed headers
            signed_headers = self.signer.get_headers('PUT', url, headers, content)
            
            # Upload to S3-compatible storage
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.put(url, headers=signed_headers, content=content)
                response.raise_for_status()
            
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
                # Configure timeout: 60s connect, 120s read, 180s total
                timeout = httpx.Timeout(
                    connect=60.0,
                    read=120.0,
                    write=60.0,
                    pool=60.0
                )
                async with httpx.AsyncClient(timeout=timeout) as http_client:
                    response = await http_client.get(path)
                    response.raise_for_status()
                    return response.content
            else:
                # Download using signed request
                url = self._get_object_url(path)
                signed_headers = self.signer.get_headers('GET', url, {})
                
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.get(url, headers=signed_headers)
                    response.raise_for_status()
                    return response.content
                
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
            
            url = self._get_object_url(path)
            signed_headers = self.signer.get_headers('DELETE', url, {})
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(url, headers=signed_headers)
                response.raise_for_status()
            
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
