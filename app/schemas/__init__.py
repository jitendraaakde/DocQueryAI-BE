"""Pydantic schemas for request/response validation."""

from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    Token,
    TokenPayload
)
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentListResponse,
    DocumentChunkResponse
)
from app.schemas.query import (
    QueryCreate,
    QueryResponse,
    QueryHistoryResponse
)
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionWithMessages,
    ChatSessionList,
    ChatMessageResponse,
    SessionQueryRequest,
    SessionQueryResponse,
    MessageFeedback,
    ChatExportRequest,
    ChatExportResponse,
)
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

__all__ = [
    # User
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "Token",
    "TokenPayload",
    # Document
    "DocumentCreate",
    "DocumentResponse",
    "DocumentListResponse",
    "DocumentChunkResponse",
    # Query
    "QueryCreate",
    "QueryResponse",
    "QueryHistoryResponse",
    # Chat
    "ChatSessionCreate",
    "ChatSessionUpdate",
    "ChatSessionResponse",
    "ChatSessionWithMessages",
    "ChatSessionList",
    "ChatMessageResponse",
    "SessionQueryRequest",
    "SessionQueryResponse",
    "MessageFeedback",
    "ChatExportRequest",
    "ChatExportResponse",
    # Collection
    "CollectionCreate",
    "CollectionUpdate",
    "CollectionResponse",
    "CollectionWithDocuments",
    "CollectionList",
    "CollectionShareCreate",
    "CollectionShareResponse",
    "CollectionShareUpdate",
    "CollectionDocumentsUpdate",
]
