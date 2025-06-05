from typing import List, Dict, Any, Optional
from uuid import UUID
import pyodbc
from datetime import datetime
import hashlib # For generating ConversationIdentifier
import uuid # For generating ConversationIdentifier

from app.dal.chat_dal import ChatDAL
from app.dal.user_dal import UserDAL
from app.dal.product_dal import ProductDAL 
from app.dal.transaction import transaction # Import the transaction context manager

from app.schemas.chat_schemas import ChatMessageResponseSchema, ChatSessionResponseSchema
from app.exceptions import NotFoundError, ForbiddenError

class ChatService:
    def __init__(self, chat_dal: ChatDAL, user_dal: UserDAL, product_dal: ProductDAL):
        self.chat_dal = chat_dal
        self.user_dal = user_dal
        self.product_dal = product_dal

    def _generate_conversation_id(self, user_id1: UUID, user_id2: UUID, product_id: UUID) -> UUID:
        """
        Generates a consistent ConversationIdentifier for a given pair of users and a product.
        Ensures that the order of user IDs does not affect the generated ID.
        """
        sorted_user_ids = sorted([str(user_id1), str(user_id2)])
        unique_string = f"{sorted_user_ids[0]}-{sorted_user_ids[1]}-{product_id}"
        return uuid.UUID(hashlib.sha256(unique_string.encode('utf-8')).hexdigest()[:32])

    async def create_message(
        self, conn: pyodbc.Connection, sender_id: UUID, receiver_id: UUID, product_id: UUID, content: str
    ) -> ChatMessageResponseSchema:
        # Start a database transaction for the entire message creation process
        async with transaction(conn):
            sender_user = await self.user_dal.get_user_by_id(conn, sender_id)
            if not sender_user:
                raise NotFoundError(f"发送者用户ID {sender_id} 不存在。")
            
            receiver_user = await self.user_dal.get_user_by_id(conn, receiver_id)
            if not receiver_user:
                raise NotFoundError(f"接收者用户ID {receiver_id} 不存在。")
                
            product = await self.product_dal.get_product_by_id(conn, product_id)
            if not product:
                raise NotFoundError(f"商品ID {product_id} 不存在。")

            message_id = uuid.uuid4()
            new_message_data = await self.chat_dal.create_chat_message(
                conn, message_id, sender_id, receiver_id, product_id, content
            )
            
            # After sending a new message, ensure the session is visible for both participants
            await self.chat_dal.mark_session_messages_invisible(conn, sender_id, receiver_id, product_id, visible=True)
            await self.chat_dal.mark_session_messages_invisible(conn, receiver_id, sender_id, product_id, visible=True)
            
            # Populate sender/receiver/product names for the response schema
            new_message_data['发送者用户名'] = sender_user.get('用户名')
            new_message_data['接收者用户名'] = receiver_user.get('用户名')
            new_message_data['商品名称'] = product.get('商品名称')

            return ChatMessageResponseSchema(**new_message_data)

    async def get_messages_for_session(self, conn: pyodbc.Connection, current_user_id: UUID, other_user_id: UUID, product_id: UUID) -> List[ChatMessageResponseSchema]:
        # First, mark messages as read if the current user is the receiver and they are unread
        messages = await self.chat_dal.get_chat_messages(conn, current_user_id, other_user_id, product_id)
        
        unread_message_ids_to_mark_read = [
            msg['消息ID'] for msg in messages 
            if msg['接收者ID'] == current_user_id and msg['是否已读'] == False
        ]
        
        if unread_message_ids_to_mark_read:
            await self.chat_dal.mark_messages_read(conn, current_user_id, unread_message_ids_to_mark_read)
            # Re-fetch messages or update 'IsRead' status in the already fetched list
            # For simplicity, re-fetching is reliable, but for performance, update in-memory
            messages = await self.chat_dal.get_chat_messages(conn, current_user_id, other_user_id, product_id)


        formatted_messages = []
        for msg in messages:
            # Populate sender/receiver/product names if not already done by DAL
            sender_user_details = await self.user_dal.get_user_by_id(conn, msg['发送者ID'])
            receiver_user_details = await self.user_dal.get_user_by_id(conn, msg['接收者ID'])
            product_details = await self.product_dal.get_product_by_id(conn, msg['商品ID'])

            msg['发送者用户名'] = sender_user_details.get('用户名') if sender_user_details else '未知用户'
            msg['接收者用户名'] = receiver_user_details.get('用户名') if receiver_user_details else '未知用户'
            msg['商品名称'] = product_details.get('商品名称') if product_details else '未知商品'

            formatted_messages.append(ChatMessageResponseSchema(**msg))
        return formatted_messages

    async def get_chat_sessions_for_user(self, conn: pyodbc.Connection, user_id: UUID) -> List[ChatSessionResponseSchema]:
        user = await self.user_dal.get_user_by_id(conn, user_id)
        if not user:
            raise NotFoundError(f"用户ID {user_id} 不存在。")

        sessions_data = await self.chat_dal.get_chat_sessions_for_user(conn, user_id)
        print(f"ChatService: get_chat_sessions_for_user - sessions_data from DAL: {sessions_data}")
        if not sessions_data:
            print(f"ChatService: No chat sessions found for user {user_id}.")
            return []

        formatted_sessions = []
        for session_dict in sessions_data:
            # DAL query should now provide:
            # 对方用户名, 对方头像URL, 相关商品名称, 相关商品图片URL
            # So, no need for separate DB calls for these here.

            # Ensure all keys for ChatSessionResponseSchema are present or have defaults
            session_dict_for_schema = {
                '会话ID': session_dict['会话ID'],
                '对方用户ID': session_dict['对方用户ID'],
                '对方用户名': session_dict.get('对方用户名', '未知用户'),
                '对方头像URL': session_dict.get('对方头像URL'), # Can be None
                '相关商品ID': session_dict['相关商品ID'],
                '相关商品名称': session_dict.get('相关商品名称', '未知商品'),
                '相关商品图片URL': session_dict.get('相关商品图片URL'), # Can be None
                '最近一条消息': session_dict.get('最近一条消息'),
                '最近消息时间': session_dict.get('最近消息时间'),
                '未读消息数': session_dict.get('未读消息数', 0)
            }
            formatted_sessions.append(ChatSessionResponseSchema(**session_dict_for_schema))
        
        return formatted_sessions

    async def mark_session_messages_invisible(self, conn: pyodbc.Connection, user_id: UUID, other_user_id: UUID, product_id: UUID):
        """
        将特定会话中与用户相关的消息标记为不可见。
        """
        # Verify the user has access to this session by checking if they are sender or receiver in any message
        conversation_id = self._generate_conversation_id(user_id, other_user_id, product_id)
        
        # This check might be redundant if the DAL query implicitly handles user ownership
        # However, for explicit security, it's good to have a check.
        # Simplistic check: If there's any message in this conversation involving the user, they have access.
        # A more robust check might involve fetching the conversation and ensuring user_id is part of it.
        # For now, let's trust the DAL's update logic to only affect messages relevant to user_id.
        
        affected_rows = await self.chat_dal.mark_session_messages_invisible(conn, user_id, other_user_id, product_id)
        if affected_rows == 0:
            # This might mean no messages were found for the session for this user, or they were already invisible.
            # Depending on strictness, could raise NotFoundError or ForbiddenError.
            # For now, let's assume it means no relevant messages, or already hidden.
            # print(f"No messages found or updated for user {user_id} in session with {other_user_id} for product {product_id}")
            pass # Or raise a specific error if hiding a non-existent session is an error.

    async def get_all_messages_for_admin(
        self, conn: pyodbc.Connection, page_number: int = 1, page_size: int = 10
    ) -> List[ChatMessageResponseSchema]:
        """
        管理员获取所有聊天消息的业务逻辑。
        """
        messages_data = await self.chat_dal.get_all_chat_messages_for_admin(conn, page_number, page_size)
        
        formatted_messages = []
        for msg_data in messages_data:
            # DAL already joins user and product names, so directly create schema
            formatted_messages.append(ChatMessageResponseSchema(**msg_data))
        
        return formatted_messages 

    async def update_single_message_visibility_for_admin(
        self, conn: pyodbc.Connection, message_id: UUID, sender_visible: bool, receiver_visible: bool
    ) -> int:
        """
        管理员更新单条消息的发送者和接收者可见性。
        """
        # 可以在这里添加权限检查，确保操作者是管理员
        # ...

        # 检查消息是否存在
        message = await self.chat_dal.get_message_by_id(conn, message_id)
        if not message:
            raise NotFoundError(f"消息ID {message_id} 不存在。")
        
        affected_rows = await self.chat_dal.update_single_message_visibility_for_admin(
            conn, message_id, sender_visible, receiver_visible
        )
        return affected_rows

    async def delete_chat_message_by_super_admin(self, conn: pyodbc.Connection, message_id: UUID, current_admin_user: dict) -> int:
        """
        超级管理员根据消息ID物理删除单条聊天消息。
        """
        if not current_admin_user.get('是否超级管理员'):
            raise ForbiddenError("只有超级管理员才能物理删除聊天消息。")

        # 检查消息是否存在
        message = await self.chat_dal.get_message_by_id(conn, message_id)
        if not message:
            raise NotFoundError(f"消息ID {message_id} 不存在。")
        
        affected_rows = await self.chat_dal.delete_chat_message_by_id(conn, message_id)
        return affected_rows