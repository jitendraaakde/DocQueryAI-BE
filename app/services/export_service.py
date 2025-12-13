"""Export service for generating PDF, Word, and shareable content."""

import logging
import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory share link storage (use Redis in production)
_share_links: Dict[str, dict] = {}


class ExportService:
    """Service for exporting content in various formats."""
    
    def __init__(self):
        self.export_dir = os.path.join(settings.UPLOAD_DIR, "exports")
        os.makedirs(self.export_dir, exist_ok=True)
    
    async def export_chat_to_markdown(
        self,
        session_title: str,
        messages: List[dict],
        include_sources: bool = True
    ) -> str:
        """Export chat session to Markdown format."""
        lines = [
            f"# {session_title}",
            f"\n*Exported on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n",
            "---\n"
        ]
        
        for msg in messages:
            role = "**You**" if msg.get("role") == "user" else "**DocQuery AI**"
            content = msg.get("content", "")
            timestamp = msg.get("created_at", "")
            
            lines.append(f"### {role}")
            if timestamp:
                lines.append(f"*{timestamp}*\n")
            lines.append(f"{content}\n")
            
            # Add sources if available
            if include_sources and msg.get("sources"):
                lines.append("\n**Sources:**")
                for source in msg["sources"]:
                    doc_name = source.get("document_name", "Unknown")
                    page = source.get("page")
                    page_info = f" (Page {page})" if page else ""
                    lines.append(f"- {doc_name}{page_info}")
                lines.append("")
            
            lines.append("---\n")
        
        return "\n".join(lines)
    
    async def export_chat_to_json(
        self,
        session_title: str,
        messages: List[dict],
        include_sources: bool = True
    ) -> str:
        """Export chat session to JSON format."""
        export_data = {
            "title": session_title,
            "exported_at": datetime.utcnow().isoformat(),
            "messages": []
        }
        
        for msg in messages:
            msg_data = {
                "role": msg.get("role"),
                "content": msg.get("content"),
                "created_at": msg.get("created_at")
            }
            if include_sources and msg.get("sources"):
                msg_data["sources"] = msg["sources"]
            export_data["messages"].append(msg_data)
        
        return json.dumps(export_data, indent=2)
    
    async def generate_pdf(
        self,
        content: str,
        title: str,
        output_filename: Optional[str] = None
    ) -> Optional[str]:
        """Generate PDF from content (requires additional packages)."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        except ImportError:
            logger.warning("reportlab not installed. PDF export unavailable.")
            return None
        
        if not output_filename:
            output_filename = f"export_{uuid.uuid4().hex[:8]}.pdf"
        
        filepath = os.path.join(self.export_dir, output_filename)
        
        try:
            doc = SimpleDocTemplate(filepath, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            # Add title
            story.append(Paragraph(title, styles['Title']))
            story.append(Spacer(1, 12))
            
            # Add content paragraphs
            for paragraph in content.split('\n\n'):
                if paragraph.strip():
                    story.append(Paragraph(paragraph, styles['Normal']))
                    story.append(Spacer(1, 6))
            
            doc.build(story)
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}")
            return None
    
    def create_share_link(
        self,
        content_type: str,  # "chat", "document", "answer"
        content_id: int,
        user_id: int,
        expires_hours: int = 24
    ) -> str:
        """Create a shareable link for content."""
        link_id = uuid.uuid4().hex[:12]
        
        _share_links[link_id] = {
            "type": content_type,
            "content_id": content_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()
        }
        
        return link_id
    
    def get_share_link(self, link_id: str) -> Optional[dict]:
        """Get share link data if valid."""
        if link_id not in _share_links:
            return None
        
        link = _share_links[link_id]
        
        # Check expiration
        expires_at = datetime.fromisoformat(link["expires_at"])
        if datetime.utcnow() > expires_at:
            del _share_links[link_id]
            return None
        
        return link
    
    def revoke_share_link(self, link_id: str) -> bool:
        """Revoke a share link."""
        if link_id in _share_links:
            del _share_links[link_id]
            return True
        return False
    
    async def copy_as_markdown(self, content: str, sources: Optional[List[dict]] = None) -> str:
        """Format content as rich Markdown for copying."""
        output = content
        
        if sources:
            output += "\n\n---\n**Sources:**\n"
            for i, source in enumerate(sources, 1):
                doc_name = source.get("document_name", "Unknown")
                page = source.get("page")
                page_info = f" (Page {page})" if page else ""
                output += f"{i}. {doc_name}{page_info}\n"
        
        return output


# Singleton instance
export_service = ExportService()
