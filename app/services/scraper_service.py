"""URL scraping service for importing web content."""

import logging
import re
import hashlib
from typing import Optional, Tuple
from urllib.parse import urlparse
import asyncio
from functools import partial

logger = logging.getLogger(__name__)


class ScraperService:
    """Service for scraping and extracting content from URLs."""
    
    async def scrape_url(self, url: str) -> Tuple[bool, str, dict]:
        """
        Scrape content from a URL.
        
        Returns:
            Tuple of (success, content, metadata)
        """
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return False, "Required packages not installed. Run: pip install httpx beautifulsoup4", {}
        
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False, "Invalid URL format", {}
        except Exception:
            return False, "Invalid URL", {}
        
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "")
                
                # Handle different content types
                if "text/html" in content_type:
                    content, metadata = await self._extract_html(response.text, url)
                elif "application/pdf" in content_type:
                    return False, "PDF URLs not supported yet. Upload the PDF directly.", {}
                elif "text/plain" in content_type:
                    content = response.text
                    metadata = {"title": urlparse(url).path.split("/")[-1] or "web_content"}
                else:
                    return False, f"Unsupported content type: {content_type}", {}
                
                return True, content, metadata
                
        except httpx.TimeoutException:
            return False, "Request timed out", {}
        except httpx.HTTPStatusError as e:
            return False, f"HTTP error: {e.response.status_code}", {}
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            return False, f"Failed to scrape URL: {str(e)}", {}
    
    async def _extract_html(self, html: str, url: str) -> Tuple[str, dict]:
        """Extract text content from HTML."""
        from bs4 import BeautifulSoup
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._parse_html_sync, html, url)
        )
    
    def _parse_html_sync(self, html: str, url: str) -> Tuple[str, dict]:
        """Synchronous HTML parsing."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract metadata
        title = ""
        if soup.title:
            title = soup.title.string or ""
        
        # Try Open Graph title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]
        
        # Get description
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"]
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
            element.decompose()
        
        # Try to find main content
        main_content = None
        for selector in ["article", "main", "[role='main']", ".content", "#content", ".post", ".article"]:
            main_content = soup.select_one(selector)
            if main_content:
                break
        
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            # Fall back to body
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)
        
        # Clean up text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)
        
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        metadata = {
            "title": title or urlparse(url).netloc,
            "description": description,
            "url": url,
            "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16]
        }
        
        return text, metadata
    
    def generate_filename(self, metadata: dict) -> str:
        """Generate a filename from scraped content metadata."""
        title = metadata.get("title", "web_content")
        # Clean title for filename
        clean_title = re.sub(r"[^\w\s-]", "", title)
        clean_title = re.sub(r"\s+", "_", clean_title)
        clean_title = clean_title[:50]  # Limit length
        
        return f"{clean_title}.txt"


# Singleton instance
scraper_service = ScraperService()
