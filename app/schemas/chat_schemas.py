from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ChatMessageCreateSchema(BaseModel):
    receiver_id: UUID = Field(..., description="消息接收者ID")
    product_id: UUID = Field(..., description="消息关联的商品ID")
    content: str = Field(..., min_length=1, description="消息内容")

class ChatMessageResponseSchema(BaseModel):
    消息ID: UUID = Field(..., alias="message_id", description="消息唯一ID")
    会话标识符: UUID = Field(..., alias="conversation_identifier", description="聊天会话的唯一标识符")
    发送者ID: UUID = Field(..., alias="sender_id", description="消息发送者用户ID")
    发送者用户名: Optional[str] = Field(None, alias="sender_username", description="消息发送者用户名")
    接收者ID: UUID = Field(..., alias="receiver_id", description="消息接收者用户ID")
    接收者用户名: Optional[str] = Field(None, alias="receiver_username", description="消息接收者用户名")
    商品ID: UUID = Field(..., alias="product_id", description="消息相关的商品ID")
    商品名称: Optional[str] = Field(None, alias="product_name", description="消息关联的商品名称")
    消息内容: str = Field(..., alias="content", description="消息内容")
    发送时间: datetime = Field(..., alias="send_time", description="消息发送时间")
    是否已读: bool = Field(..., alias="is_read", description="消息是否已读")
    发送者可见: bool = Field(..., alias="sender_visible", description="消息在发送者端是否可见")
    接收者可见: bool = Field(..., alias="receiver_visible", description="消息在接收者端是否可见")

    class Config:
        from_attributes = True
        populate_by_name = True

class ChatSessionResponseSchema(BaseModel):
    会话ID: UUID = Field(..., alias="session_id", description="聊天会话ID (即 ConversationIdentifier)")
    对方用户ID: UUID = Field(..., alias="other_user_id", description="会话中对方的用户ID")
    对方用户名: Optional[str] = Field(None, alias="other_username", description="会话中对方的用户名")
    对方头像URL: Optional[str] = Field(None, alias="other_avatar_url", description="会话中对方的头像URL")
    相关商品ID: UUID = Field(..., alias="product_id", description="会话关联的商品ID")
    相关商品名称: Optional[str] = Field(None, alias="product_name", description="会话关联的商品名称")
    最近一条消息: Optional[str] = Field(None, alias="last_message_content", description="会话的最近一条消息内容")
    最近消息时间: Optional[datetime] = Field(None, alias="last_message_time", description="会话的最近一条消息时间")
    未读消息数: int = Field(..., alias="unread_count", description="当前用户在该会话中的未读消息数")

    class Config:
        from_attributes = True
        populate_by_name = True

# 新增：分页聊天消息响应Schema
class PaginatedChatMessagesResponseSchema(BaseModel):
    messages: List[ChatMessageResponseSchema] = Field(..., description="聊天消息列表")
    total_count: int = Field(..., description="总消息数")

    class Config:
        from_attributes = True
        populate_by_name = True