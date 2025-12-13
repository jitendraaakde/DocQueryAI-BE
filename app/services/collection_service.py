"""Collection management service."""

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.models.collection import Collection, CollectionShare, collection_documents
from app.models.document import Document
from app.models.user import User
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionShareCreate,
    CollectionShareUpdate,
    CollectionDocumentsUpdate,
)


class CollectionService:
    """Service for managing document collections."""
    
    # ==================== COLLECTION CRUD ====================
    
    async def create_collection(
        self,
        db: AsyncSession,
        user_id: int,
        data: CollectionCreate
    ) -> Collection:
        """Create a new collection."""
        collection = Collection(
            user_id=user_id,
            name=data.name,
            description=data.description,
            color=data.color,
            icon=data.icon,
        )
        db.add(collection)
        await db.flush()
        
        # Add documents if provided
        if data.document_ids:
            await self.add_documents(db, collection.id, user_id, data.document_ids)
        
        await db.refresh(collection)
        return collection
    
    async def get_collection(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int,
        include_documents: bool = False
    ) -> Optional[Collection]:
        """Get a collection by ID (owned or shared)."""
        query = select(Collection).where(Collection.id == collection_id)
        
        if include_documents:
            query = query.options(selectinload(Collection.documents))
        
        result = await db.execute(query)
        collection = result.scalar_one_or_none()
        
        if not collection:
            return None
        
        # Check if user owns or has access
        if collection.user_id == user_id:
            return collection
        
        # Check if shared with user
        share_query = select(CollectionShare).where(
            CollectionShare.collection_id == collection_id,
            CollectionShare.shared_with_user_id == user_id
        )
        share_result = await db.execute(share_query)
        if share_result.scalar_one_or_none():
            return collection
        
        # Check if public
        if collection.is_public:
            return collection
        
        return None
    
    async def get_user_collections(
        self,
        db: AsyncSession,
        user_id: int,
        include_shared: bool = True
    ) -> List[Collection]:
        """Get all collections for a user (owned and shared)."""
        # Get owned collections
        owned_query = select(Collection).where(Collection.user_id == user_id)
        result = await db.execute(owned_query)
        collections = list(result.scalars().all())
        
        if include_shared:
            # Get shared collections
            shared_query = (
                select(Collection)
                .join(CollectionShare)
                .where(CollectionShare.shared_with_user_id == user_id)
            )
            shared_result = await db.execute(shared_query)
            collections.extend(shared_result.scalars().all())
        
        return collections
    
    async def update_collection(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int,
        data: CollectionUpdate
    ) -> Optional[Collection]:
        """Update a collection."""
        collection = await self.get_collection(db, collection_id, user_id)
        if not collection or collection.user_id != user_id:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(collection, field, value)
        
        await db.flush()
        await db.refresh(collection)
        return collection
    
    async def delete_collection(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int
    ) -> bool:
        """Delete a collection."""
        collection = await self.get_collection(db, collection_id, user_id)
        if not collection or collection.user_id != user_id:
            return False
        
        await db.delete(collection)
        await db.flush()
        return True
    
    # ==================== DOCUMENT MANAGEMENT ====================
    
    async def add_documents(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int,
        document_ids: List[int]
    ) -> bool:
        """Add documents to a collection."""
        collection = await self.get_collection(db, collection_id, user_id)
        if not collection:
            return False
        
        # Verify user owns documents
        doc_query = select(Document).where(
            Document.id.in_(document_ids),
            Document.user_id == user_id
        )
        result = await db.execute(doc_query)
        valid_docs = result.scalars().all()
        
        for doc in valid_docs:
            if doc not in collection.documents:
                collection.documents.append(doc)
        
        await db.flush()
        return True
    
    async def remove_documents(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int,
        document_ids: List[int]
    ) -> bool:
        """Remove documents from a collection."""
        collection = await self.get_collection(db, collection_id, user_id, include_documents=True)
        if not collection:
            return False
        
        collection.documents = [
            doc for doc in collection.documents
            if doc.id not in document_ids
        ]
        
        await db.flush()
        return True
    
    async def get_collection_document_ids(
        self,
        db: AsyncSession,
        collection_id: int,
        user_id: int
    ) -> List[int]:
        """Get document IDs in a collection."""
        collection = await self.get_collection(db, collection_id, user_id, include_documents=True)
        if not collection:
            return []
        
        return [doc.id for doc in collection.documents]
    
    # ==================== SHARING ====================
    
    async def share_collection(
        self,
        db: AsyncSession,
        collection_id: int,
        owner_id: int,
        data: CollectionShareCreate
    ) -> Optional[CollectionShare]:
        """Share a collection with another user."""
        # Verify ownership
        collection = await self.get_collection(db, collection_id, owner_id)
        if not collection or collection.user_id != owner_id:
            return None
        
        # Find user by email
        user_query = select(User).where(User.email == data.user_email)
        user_result = await db.execute(user_query)
        target_user = user_result.scalar_one_or_none()
        
        if not target_user:
            return None
        
        # Check if already shared
        existing_query = select(CollectionShare).where(
            CollectionShare.collection_id == collection_id,
            CollectionShare.shared_with_user_id == target_user.id
        )
        existing = await db.execute(existing_query)
        if existing.scalar_one_or_none():
            return None  # Already shared
        
        share = CollectionShare(
            collection_id=collection_id,
            shared_with_user_id=target_user.id,
            permission=data.permission,
        )
        db.add(share)
        await db.flush()
        await db.refresh(share)
        return share
    
    async def update_share_permission(
        self,
        db: AsyncSession,
        share_id: int,
        owner_id: int,
        data: CollectionShareUpdate
    ) -> Optional[CollectionShare]:
        """Update share permission."""
        query = select(CollectionShare).join(Collection).where(
            CollectionShare.id == share_id,
            Collection.user_id == owner_id
        )
        result = await db.execute(query)
        share = result.scalar_one_or_none()
        
        if not share:
            return None
        
        share.permission = data.permission
        await db.flush()
        await db.refresh(share)
        return share
    
    async def remove_share(
        self,
        db: AsyncSession,
        share_id: int,
        owner_id: int
    ) -> bool:
        """Remove a share."""
        query = select(CollectionShare).join(Collection).where(
            CollectionShare.id == share_id,
            Collection.user_id == owner_id
        )
        result = await db.execute(query)
        share = result.scalar_one_or_none()
        
        if not share:
            return False
        
        await db.delete(share)
        await db.flush()
        return True
    
    async def get_collection_shares(
        self,
        db: AsyncSession,
        collection_id: int,
        owner_id: int
    ) -> List[CollectionShare]:
        """Get all shares for a collection."""
        query = (
            select(CollectionShare)
            .join(Collection)
            .options(selectinload(CollectionShare.shared_with_user))
            .where(
                CollectionShare.collection_id == collection_id,
                Collection.user_id == owner_id
            )
        )
        result = await db.execute(query)
        return list(result.scalars().all())


# Singleton instance
collection_service = CollectionService()
