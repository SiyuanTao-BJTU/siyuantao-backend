from typing import List, Dict, Any
from uuid import UUID
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from app.dependencies import get_db_connection, get_current_authenticated_user, get_chat_service, get_current_active_admin_user
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import ChatMessageCreateSchema, ChatMessageResponseSchema, ChatSessionResponseSchema
from app.exceptions import NotFoundError, ForbiddenError

router = APIRouter()


@router.post("/messages", response_model=ChatMessageResponseSchema, status_code=status.HTTP_201_CREATED, summary="发送新消息", response_model_by_alias=False)
async def create_chat_message(
    message_data: ChatMessageCreateSchema,
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        new_message = await chat_service.create_message(
            conn, current_user['用户ID'], message_data.receiver_id, message_data.product_id, message_data.content
        )
        return new_message
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建消息失败: {e}")


@router.get("/sessions", response_model=List[ChatSessionResponseSchema], summary="获取用户聊天会话列表", response_model_by_alias=False)
async def get_user_chat_sessions(
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        sessions = await chat_service.get_chat_sessions_for_user(conn, current_user['用户ID'])
        return sessions
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取聊天会话失败: {e}")


@router.get("/messages/{other_user_id}/{product_id}", response_model=List[ChatMessageResponseSchema], summary="获取与特定用户和商品的聊天消息历史", response_model_by_alias=False)
async def get_chat_messages(
    other_user_id: UUID = Path(..., description="对方用户ID"),
    product_id: UUID = Path(..., description="关联商品ID"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        messages = await chat_service.get_messages_for_session(conn, current_user['用户ID'], other_user_id, product_id)
        return messages
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取聊天消息失败: {e}")


@router.put("/messages/read/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="标记单条消息为已读")
async def mark_single_message_read(
    message_id: UUID = Path(..., description="要标记为已读的消息ID"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        # The service will handle marking the message read for the current user if they are the receiver
        await chat_service.mark_messages_read(conn, current_user['用户ID'], [message_id])
        return {} # No content response
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"标记消息为已读失败: {e}")


@router.put("/sessions/hide/{other_user_id}/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="隐藏聊天会话 (标记为用户不可见)")
async def hide_chat_session(
    other_user_id: UUID = Path(..., description="会话中对方的UserID"),
    product_id: UUID = Path(..., description="关联商品ID"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        await chat_service.mark_session_messages_invisible(conn, current_user['用户ID'], other_user_id, product_id)
        return {}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"隐藏聊天会话失败: {e}")


@router.get("/admin/messages", response_model=List[ChatMessageResponseSchema], summary="管理员获取所有聊天消息", response_model_by_alias=False)
async def get_all_chat_messages_for_admin(
    page_number: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    current_admin_user: dict = Depends(get_current_active_admin_user), # Requires admin role
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        messages = await chat_service.get_all_messages_for_admin(conn, page_number, page_size)
        return messages
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"管理员获取所有消息失败: {e}")


@router.put("/admin/messages/{message_id}/visibility", status_code=status.HTTP_204_NO_CONTENT, summary="管理员更新单条消息可见性")
async def admin_update_single_message_visibility(
    message_id: UUID = Path(..., description="要更新可见性的消息ID"),
    sender_visible: bool = Query(..., description="发送者可见性 (true/false)"),
    receiver_visible: bool = Query(..., description="接收者可见性 (true/false)"),
    current_admin_user: dict = Depends(get_current_active_admin_user), # Requires admin role
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        affected_rows = await chat_service.update_single_message_visibility_for_admin(
            conn, message_id, sender_visible, receiver_visible
        )
        if affected_rows == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息未找到或状态未改变。")
        return {} # No content response
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"管理员更新消息可见性失败: {e}")


@router.delete("/admin/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="超级管理员物理删除单条聊天消息")
async def super_admin_delete_chat_message(
    message_id: UUID = Path(..., description="要删除的消息ID"),
    current_super_admin_user: dict = Depends(get_current_active_admin_user), # Requires super_admin role
    conn: pyodbc.Connection = Depends(get_db_connection),
    chat_service: ChatService = Depends(get_chat_service)
):
    try:
        # The service layer will handle the super admin role check
        affected_rows = await chat_service.delete_chat_message_by_super_admin(conn, message_id, current_super_admin_user)
        if affected_rows == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息未找到或已被删除。")
        return {} # No content response
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"物理删除消息失败: {e}")