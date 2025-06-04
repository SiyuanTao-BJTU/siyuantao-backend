import uuid
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status
from fastapi.responses import JSONResponse # Added for dynamic status codes
from pydantic import BaseModel, Field

# Placeholder for ChatService - In a real app, this would be properly injected
# from ..services.chat_service import ChatService, InvalidInputError, ChatOperationError, NotFoundError
# For now, let's use MagicMock for the service in the route definition for structure.
# Actual instantiation/injection would happen in main.py or similar.
from unittest.mock import MagicMock
# Assuming ChatService and its exceptions are defined in chat_service.py
from app.services.chat_service import (
    ChatService,
    InvalidInputError,
    ChatOperationError,
    NotFoundError,
    ChatServiceError  # Import base service error
)
# Placeholder for DAL and DB Pool for actual service instantiation
# from backend.src.modules.chat.dal.chat_message_dal import ChatMessageDAL
# from your_db_connector import db_pool # Example

# --- Placeholder Authentication ---
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str = "testuser"
    # roles: List[str] = [] # If roles are needed

async def get_current_user() -> User:
    """Placeholder for current user dependency."""
    return User()

# --- Pydantic Models ---
class MessageCreateRequest(BaseModel):
    receiver_id: str = Field(..., description="ID of the message receiver.")
    product_id: str = Field(..., description="ID of the product related to the chat.")
    content: str = Field(..., min_length=1, max_length=4000, description="Message content.")
    client_message_id: Optional[str] = Field(None, description="Client-generated unique ID for idempotency.")

class SendMessageResponse(BaseModel):
    message_id: str = Field(..., description="The ID of the sent or existing message.")
    is_newly_created: bool = Field(..., description="True if the message was newly created, False if it already existed (idempotent hit).")

class MessageResponse(BaseModel):
    # Define based on the actual output of sp_SendMessage as mapped by DAL/Service
    Result: str
    AffectedRows: Optional[int] = None # Example from existing DAL
    NewMessageID: Optional[str] = None # Example from original SP if it returned ID

class ConversationResponseItem(BaseModel):
    # Define based on the actual output of sp_GetUserConversations
    商品ID: str
    商品名称: str
    商品所有者ID: Optional[str] = None
    商品所有者用户名: Optional[str] = None
    聊天对象ID: str
    聊天对象用户名: str
    最新消息内容: str
    最新消息时间: Any # Or datetime
    未读消息数量: int

class ChatMessageItem(BaseModel):
    # Define based on sp_GetChatMessagesByProductAndUsers
    消息ID: str
    发送者ID: str
    发送者用户名: str
    接收者ID: str
    接收者用户名: str
    商品ID: str
    商品名称: Optional[str] = None # If included
    内容: str
    发送时间: Any # Or datetime
    是否已读: bool

class PaginatedChatMessagesResponse(BaseModel):
    messages: List[ChatMessageItem]
    total_count: int
    page: int
    page_size: int

class MarkAsReadResponse(BaseModel):
    MarkedAsReadMessageID: str
    Result: str

class HideConversationResponse(BaseModel):
    Result: str
    ProductID: Optional[str] = None
    UserID: Optional[str] = None


# --- Router Definition ---
router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Chat"]
)

# This is a placeholder. In a real app, use FastAPI's dependency injection system.
# Example: 
# db_pool_instance = ...
# chat_dal_instance = ChatMessageDAL(db_pool_instance)
# chat_service_instance = ChatService(chat_dal_instance)

# --- ChatService Dependency ---
# This is where you would normally instantiate your actual ChatService with its dependencies (e.g., DAL)
# For now, it's a placeholder that will be overridden in tests.
# In a real app, you might have a more complex DI setup or a singleton factory.
# For the purpose of this file being runnable stand-alone (e.g. for schema generation),
# we can provide a default mock or raise an error if not overridden.

# REMOVE: chat_service_instance = MagicMock(spec=ChatService)

# Define a function that provides the ChatService.
# This function will be used as a dependency.
# For a real application, this would create and return an actual ChatService instance.
# For testing, we will override this dependency.
def get_chat_service() -> ChatService:
    # In a real app, this would be:
    # dal = ChatMessageDAL(db_pool_instance) # or however you get your DAL
    # return ChatService(dal)
    # For now, so that the app can start without a full DI setup,
    # we can return a basic MagicMock or raise an error.
    # Let's make it clear this needs to be configured/overridden:
    # raise NotImplementedError("ChatService dependency not configured for actual use.")
    # Or, to allow tests to run smoothly by overriding, we can make it a simple mock by default here too,
    # but it's better practice for tests to fully control this.
    # For the routes to be syntactically correct and to define the dependency,
    # we need this function.
    # The test setup will override this to return mock_chat_service.
    # For the module to be importable without a full app setup, we can have it return a temporary mock here
    # if no override is present (though FastAPI's override is usually what's used).
    # A common pattern is to have it raise an error if not properly configured or overridden.
    # However, for simplicity in this context, we'll allow it to be overridden.
    # Let's assume this function will be overridden by app.dependency_overrides.
    # If not overridden, it would ideally raise an error or return a default service.
    # For now, to avoid breaking existing structure too much if this file is imported elsewhere,
    # let's allow it to be callable and be overridden. A placeholder is fine.
    return MagicMock(spec=ChatService) # This default mock will be replaced by the test's mock via dependency_overrides


def handle_chat_service_exception(e: ChatServiceError):
    if isinstance(e, InvalidInputError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.field_errors or e.message)
    if isinstance(e, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    if isinstance(e, ChatOperationError): # More generic operational error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)
    # Fallback for other ChatServiceError or general exceptions
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/messages", response_model=SendMessageResponse) # Removed status_code, updated response_model
async def send_chat_message(
    payload: MessageCreateRequest,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Send a new chat message."""
    try:
        message_id_obj, is_newly = chat_service.send_message(
            sender_id=current_user.id,
            receiver_id=payload.receiver_id,
            product_id=payload.product_id,
            content=payload.content,
            client_message_id=payload.client_message_id # Pass client_message_id
        )
        
        response_data = SendMessageResponse(
            message_id=str(message_id_obj), 
            is_newly_created=is_newly
        )
        
        status_to_return = status.HTTP_201_CREATED if is_newly else status.HTTP_200_OK
        return JSONResponse(content=response_data.model_dump(), status_code=status_to_return)
        
    except ChatServiceError as e:
        handle_chat_service_exception(e)
    except Exception as e: # Catch-all for unexpected errors
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/conversations", response_model=List[ConversationResponseItem])
async def get_user_conversations_list(
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service) # Use dependency injection
):
    """Get the current user's conversation list."""
    try:
        return chat_service.get_conversations(user_id=current_user.id) # Use injected chat_service
    except ChatServiceError as e:
        handle_chat_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/messages/{product_id}/{other_user_id}", response_model=PaginatedChatMessagesResponse)
async def get_product_chat_messages(
    product_id: str = Path(..., description="ID of the product"),
    other_user_id: str = Path(..., description="ID of the other user in the conversation"),
    page_number: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Messages per page"),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service) # Use dependency injection
):
    """Get chat messages for a specific product between the current user and another user."""
    try:
        messages, total_count = chat_service.get_messages_between_users_for_product( # Use injected chat_service
            product_id=product_id,
            user_id1=current_user.id,
            user_id2=other_user_id,
            page_number=page_number,
            page_size=page_size
        )
        return PaginatedChatMessagesResponse(
            messages=messages,
            total_count=total_count,
            page=page_number,
            page_size=page_size
        )
    except ChatServiceError as e:
        handle_chat_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


@router.put("/messages/{message_id}/read", response_model=MarkAsReadResponse)
async def mark_message_read_endpoint( # Renamed to avoid conflict
    message_id: str = Path(..., description="ID of the message to mark as read"),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service) # Use dependency injection
):
    """Mark a message as read by the current user."""
    try:
        result = chat_service.mark_message_as_read( # Use injected chat_service
            message_id=message_id,
            user_id=current_user.id
        )
        return result
    except ChatServiceError as e:
        handle_chat_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.put("/conversations/{product_id}/hide", response_model=HideConversationResponse)
async def hide_user_conversation_endpoint( # Renamed
    product_id: str = Path(..., description="ID of the product related to the conversation to hide"),
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service) # Use dependency injection
):
    """Hide a conversation for the current user related to a specific product."""
    try:
        return chat_service.hide_conversation( # Use injected chat_service
            product_id=product_id,
            user_id=current_user.id
        )
    except ChatServiceError as e:
        handle_chat_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

# Example of how the service might be provided (in main.py or via a dependency system)
# def get_chat_service():
#     # This is where you'd instantiate your DAL and service with real DB connections
#     # For now, this function would need to be defined if used with Depends() directly.
#     # global chat_service_instance 
#     # if chat_service_instance is None:
#     #     # Initialize actual service
#     #     db_pool = ... 
#     #     dal = ChatMessageDAL(db_pool)
#     #     chat_service_instance = ChatService(dal)
#     return chat_service_instance 