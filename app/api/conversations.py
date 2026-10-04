"""Conversation history endpoints.

Storage lives in the existing Supabase Postgres database; this router only
authenticates the caller and delegates to ``ConversationService``, which scopes
every read/write to the authenticated user. No RAG logic lives here — a new
question still goes through ``POST /api/query``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.services.conversation_service import (
    ConversationNotFound,
    ConversationService,
    ConversationValidationError,
    DEFAULT_TITLE,
)

router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversations"],
)

_service: ConversationService | None = None


def get_conversation_service() -> ConversationService:
    global _service

    if _service is None:
        _service = ConversationService()

    return _service


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    role: str
    content: str
    query_id: str | None = None
    confidence: float | None = None
    answerable: bool | None = None
    citations: list[dict] | None = None


def _not_found() -> HTTPException:
    # Same answer for "missing" and "not yours": no existence leak.
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found",
    )


def _failure() -> HTTPException:
    # Never expose database errors or stack traces to API clients.
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Conversation storage is unavailable.",
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate | None = None,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.create_conversation(
            user_id=current_user.id,
            title=(payload.title if payload else None) or DEFAULT_TITLE,
        )
    except Exception:
        raise _failure()


@router.get("")
def list_conversations(
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.list_conversations(user_id=current_user.id)
    except Exception:
        raise _failure()


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.get_conversation(current_user.id, conversation_id)
    except ConversationNotFound:
        raise _not_found()
    except Exception:
        raise _failure()


@router.patch("/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.rename_conversation(
            current_user.id, conversation_id, payload.title
        )
    except ConversationNotFound:
        raise _not_found()
    except Exception:
        raise _failure()


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        service.delete_conversation(current_user.id, conversation_id)
    except ConversationNotFound:
        raise _not_found()
    except Exception:
        raise _failure()

    return {"status": "deleted", "id": conversation_id}


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.list_messages(current_user.id, conversation_id)
    except ConversationNotFound:
        raise _not_found()
    except Exception:
        raise _failure()


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    try:
        return service.add_message(
            user_id=current_user.id,
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
            query_id=payload.query_id,
            confidence=payload.confidence,
            answerable=payload.answerable,
            citations=payload.citations,
        )
    except ConversationValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    except ConversationNotFound:
        raise _not_found()
    except Exception:
        raise _failure()
