"""Collection API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionWithDocuments,
    CollectionList,
    CollectionShareCreate,
    CollectionShareResponse,
    CollectionShareUpdate,
    CollectionDocumentsUpdate,
)
from app.services.collection_service import collection_service

router = APIRouter(prefix="/collections", tags=["collections"])


# ==================== COLLECTION CRUD ====================

@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new collection."""
    collection = await collection_service.create_collection(db, current_user.id, data)
    return collection


@router.get("", response_model=CollectionList)
async def list_collections(
    include_shared: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all collections for the current user."""
    collections = await collection_service.get_user_collections(
        db, current_user.id, include_shared=include_shared
    )
    return CollectionList(collections=collections, total=len(collections))


@router.get("/{collection_id}", response_model=CollectionWithDocuments)
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a collection with document IDs."""
    collection = await collection_service.get_collection(
        db, collection_id, current_user.id, include_documents=True
    )
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Add document_ids to response
    response = CollectionWithDocuments(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        color=collection.color,
        icon=collection.icon,
        is_public=collection.is_public,
        document_count=len(collection.documents),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        document_ids=[doc.id for doc in collection.documents]
    )
    return response


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: int,
    data: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a collection."""
    collection = await collection_service.update_collection(
        db, collection_id, current_user.id, data
    )
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found or you don't have permission"
        )
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a collection."""
    success = await collection_service.delete_collection(db, collection_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found or you don't have permission"
        )


# ==================== DOCUMENT MANAGEMENT ====================

@router.post("/{collection_id}/documents", status_code=status.HTTP_204_NO_CONTENT)
async def update_collection_documents(
    collection_id: int,
    data: CollectionDocumentsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add or remove documents from a collection."""
    if data.action == "add":
        success = await collection_service.add_documents(
            db, collection_id, current_user.id, data.document_ids
        )
    else:
        success = await collection_service.remove_documents(
            db, collection_id, current_user.id, data.document_ids
        )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )


@router.get("/{collection_id}/documents", response_model=List[int])
async def get_collection_document_ids(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all document IDs in a collection."""
    doc_ids = await collection_service.get_collection_document_ids(
        db, collection_id, current_user.id
    )
    return doc_ids


# ==================== SHARING ====================

@router.post("/{collection_id}/shares", response_model=CollectionShareResponse, status_code=status.HTTP_201_CREATED)
async def share_collection(
    collection_id: int,
    data: CollectionShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Share a collection with another user."""
    share = await collection_service.share_collection(
        db, collection_id, current_user.id, data
    )
    if not share:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not share collection. User not found or already shared."
        )
    
    return CollectionShareResponse(
        id=share.id,
        collection_id=share.collection_id,
        shared_with_user_id=share.shared_with_user_id,
        shared_with_email=share.shared_with_user.email,
        shared_with_username=share.shared_with_user.username,
        permission=share.permission,
        created_at=share.created_at
    )


@router.get("/{collection_id}/shares", response_model=List[CollectionShareResponse])
async def list_collection_shares(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all shares for a collection."""
    shares = await collection_service.get_collection_shares(
        db, collection_id, current_user.id
    )
    
    return [
        CollectionShareResponse(
            id=share.id,
            collection_id=share.collection_id,
            shared_with_user_id=share.shared_with_user_id,
            shared_with_email=share.shared_with_user.email,
            shared_with_username=share.shared_with_user.username,
            permission=share.permission,
            created_at=share.created_at
        )
        for share in shares
    ]


@router.patch("/shares/{share_id}", response_model=CollectionShareResponse)
async def update_share(
    share_id: int,
    data: CollectionShareUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update share permission."""
    share = await collection_service.update_share_permission(
        db, share_id, current_user.id, data
    )
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found or you don't have permission"
        )
    
    return CollectionShareResponse(
        id=share.id,
        collection_id=share.collection_id,
        shared_with_user_id=share.shared_with_user_id,
        shared_with_email=share.shared_with_user.email,
        shared_with_username=share.shared_with_user.username,
        permission=share.permission,
        created_at=share.created_at
    )


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a share."""
    success = await collection_service.remove_share(db, share_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found or you don't have permission"
        )
