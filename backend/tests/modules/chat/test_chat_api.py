import uuid
import pytest
from fastapi import FastAPI, status, Depends
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from typing import List, Tuple, Dict, Any, Optional

# Modules to test
from backend.src.modules.chat.api.chat_routes import router as chat_router
from backend.src.modules.chat.api.chat_routes import get_current_user as chat_api_get_current_user
from backend.src.modules.chat.api.chat_routes import get_chat_service
from backend.src.modules.chat.services.chat_service import (
    ChatService,
    InvalidInputError,
    NotFoundError,
    ChatOperationError,
    ChatServiceError
)
# Ensure these are the correct Pydantic models from your chat_routes.py
from backend.src.modules.chat.api.chat_routes import User as ApiUser
from backend.src.modules.chat.api.chat_routes import (
    MessageCreateRequest,
    # Assuming MessageResponse is the Pydantic model for a successful send_message response
    MessageResponse,  # If this is not the one, replace with the correct model name
    # Assuming ConversationResponseItem is the model for individual conversation items
    ConversationResponseItem,
    # Assuming PaginatedChatMessagesResponse is for paged messages
    PaginatedChatMessagesResponse,
    # Assuming MarkAsReadResponse is for marking as read
    MarkAsReadResponse,
    # Assuming HideConversationResponse is for hiding conversations
    HideConversationResponse,
    # ChatMessageItem is likely used within PaginatedChatMessagesResponse
    ChatMessageItem
)
from pydantic import BaseModel # For placeholder if actual model is not found

# Mock ChatService instance
mock_chat_service = MagicMock()

# Mock current user
mock_user_id = str(uuid.uuid4())
mock_current_user = ApiUser(id=mock_user_id, username="test_api_user")

async def override_get_current_user() -> ApiUser:
    return mock_current_user

# NEW: Override for get_chat_service dependency
def override_get_chat_service() -> ChatService: # Return type hint for clarity
    return mock_chat_service

# Create a FastAPI app instance for testing
app = FastAPI()

# REMOVE: chat_router.chat_service_instance = mock_chat_service

app.include_router(chat_router)

# Setup dependency overrides
app.dependency_overrides[chat_api_get_current_user] = override_get_current_user
app.dependency_overrides[get_chat_service] = override_get_chat_service # <--- ADD OVERRIDE FOR CHAT SERVICE

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_mocks_fixture():
    mock_chat_service.reset_mock()
    methods_to_reset = [
        'send_message', 'get_conversations',
        'get_messages_between_users_for_product',
        'mark_message_as_read', 'hide_conversation'
    ]
    for method_name in methods_to_reset:
        # Since spec is removed, we need to ensure these methods exist as mocks if they are to be called.
        # setattr will create them as MagicMock if they don't exist after reset_mock on the parent.
        # Or, more simply, ensure they are attributes that can be configured.
        # For a plain MagicMock(), accessing an attribute like 'send_message' will create it if it doesn't exist.
        if hasattr(mock_chat_service, method_name):
            method_mock = getattr(mock_chat_service, method_name)
            if isinstance(method_mock, MagicMock):
                method_mock.reset_mock(return_value=True, side_effect=True)
                method_mock.return_value = None 
                method_mock.side_effect = None
        else:
            # If method doesn't exist (e.g. after a full reset_mock() on a plain MagicMock that had methods dynamically added)
            # we might need to re-add it as a MagicMock so it can be configured by tests.
            # However, MagicMock() behavior is that accessing mock.new_method creates it.
            # So, explicit recreation might not be needed unless reset_mock() on parent removes them entirely.
            # For safety and clarity, let's ensure the attributes are fresh mocks if we are to configure them.
            setattr(mock_chat_service, method_name, MagicMock(return_value=None, side_effect=None))


# --- Test Cases ---\n
# POST /api/v1/chat/messages
def test_send_chat_message_success():
    payload = {"receiver_id": str(uuid.uuid4()), "product_id": str(uuid.uuid4()), "content": "Hello there!"}
    
    # Use the Pydantic model (MessageResponse or equivalent) for the expected response
    # Ensure MessageResponse has fields: Result, AffectedRows, NewMessageID
    # The types should match: str, int, uuid.UUID (or str if model expects str for ID)
    new_msg_id_obj = uuid.uuid4()
    expected_model_instance = MessageResponse(
        Result="消息发送成功",
        AffectedRows=1,
        NewMessageID=str(new_msg_id_obj)  # Corrected: Ensure str for NewMessageID
    )
    mock_chat_service.send_message.return_value = expected_model_instance

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    # FastAPI will serialize the Pydantic model instance to JSON
    # UUIDs are typically converted to strings in JSON.
    response_json = response.json()
    assert response_json["Result"] == expected_model_instance.Result
    assert response_json["AffectedRows"] == expected_model_instance.AffectedRows
    assert response_json["NewMessageID"] == str(new_msg_id_obj) # Compare with string version of UUID

    mock_chat_service.send_message.assert_called_once_with(
        sender_id=mock_current_user.id,
        receiver_id=payload["receiver_id"],
        product_id=payload["product_id"],
        content=payload["content"]
    )

def test_send_chat_message_invalid_input():
    payload = {"receiver_id": "invalid", "product_id": str(uuid.uuid4()), "content": "Short"}
    mock_chat_service.send_message.side_effect = InvalidInputError(message="Validation failed", field_errors={"receiver_id": "Invalid UUID"})

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "receiver_id" in response.json()["detail"]

def test_send_chat_message_service_operation_error():
    payload = {"receiver_id": str(uuid.uuid4()), "product_id": str(uuid.uuid4()), "content": "Test content"}
    mock_chat_service.send_message.side_effect = ChatOperationError(message="DAL failed to send")

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "DAL failed to send"

# GET /api/v1/chat/conversations
def test_get_user_conversations_success():
    convo_product_id_str = str(uuid.uuid4())
    convo_chat_partner_id_str = str(uuid.uuid4())
    
    # Assuming ConversationResponseItem is the Pydantic model for each item
    # Ensure fields match your Pydantic model's definition
    mock_convo_data_models = [
        ConversationResponseItem(
            商品ID=convo_product_id_str, 
            商品名称="Product A", 
            聊天对象ID=convo_chat_partner_id_str, 
            聊天对象用户名="UserB", 
            最新消息内容="Hi", 
            最新消息时间="2023-01-01T10:00:00Z", # Ensure this is datetime or str as per Pydantic model
            未读消息数量=1
        )
    ]
    mock_chat_service.get_conversations.return_value = mock_convo_data_models

    response = client.get("/api/v1/chat/conversations")

    assert response.status_code == status.HTTP_200_OK
    
    # Convert Pydantic models to dicts for comparison if necessary,
    # or compare field by field. FastAPI's response.json() will be list of dicts.
    expected_json_list = [item.model_dump(by_alias=True) for item in mock_convo_data_models] # pydantic v2
    # If using pydantic v1, it would be [item.dict(by_alias=True) for item in mock_convo_data_models]
    assert response.json() == expected_json_list
    
    mock_chat_service.get_conversations.assert_called_once_with(user_id=mock_current_user.id)

def test_get_user_conversations_not_found():
    mock_chat_service.get_conversations.side_effect = NotFoundError(message="No conversations found")

    response = client.get("/api/v1/chat/conversations")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "No conversations found"

# GET /api/v1/chat/messages/{product_id}/{other_user_id}
def test_get_product_chat_messages_success():
    product_id_str = str(uuid.uuid4())
    other_user_id_str = str(uuid.uuid4())
    page_num = 1
    page_size = 10
    
    # Assuming ChatMessageItem is the Pydantic model for individual messages
    msg_id_obj = uuid.uuid4()
    mock_message_item = ChatMessageItem(
        消息ID=str(msg_id_obj),      # Corrected: Ensure str
        发送者ID=mock_current_user.id, 
        发送者用户名="Me", 
        接收者ID=other_user_id_str, 
        接收者用户名="Other", 
        商品ID=product_id_str,
        内容="Msg1", 
        发送时间="2023-01-01T10:00:00Z", # Ensure datetime or str as per model
        是否已读=True
    )
    mock_messages_models = [mock_message_item]
    total_count = 1
    
    # Assuming PaginatedChatMessagesResponse is the Pydantic model for the whole page
    # Ensure it has fields: messages (List[ChatMessageItem]), total_count, page, page_size
    expected_page_response_model = PaginatedChatMessagesResponse(
        messages=mock_messages_models,
        total_count=total_count,
        page=page_num,
        page_size=page_size
    )
    mock_chat_service.get_messages_between_users_for_product.return_value = (mock_messages_models, total_count) # Service might return tuple

    # The route handler should construct PaginatedChatMessagesResponse from service output
    # If service returns (mock_messages_models, total_count), the route should do:
    # return PaginatedChatMessagesResponse(messages=data, total_count=count, page=page_number, page_size=page_size)
    # For the test, we assume the route does this, so the mock_chat_service.get_messages_between_users_for_product
    # is what it is, and we assert the final JSON based on `expected_page_response_model`.

    response = client.get(f"/api/v1/chat/messages/{product_id_str}/{other_user_id_str}?page_number={page_num}&page_size={page_size}")

    assert response.status_code == status.HTTP_200_OK
    
    # Convert the expected Pydantic model to dict for comparison
    # For pydantic v2:
    expected_json = expected_page_response_model.model_dump(by_alias=True)
    # If using pydantic v1:
    # expected_json = expected_page_response_model.dict(by_alias=True)

    # Ensure UUIDs in messages are compared as strings if they are serialized as such
    for msg_dict in expected_json.get("messages", []):
        if isinstance(msg_dict.get("消息ID"), uuid.UUID):
            msg_dict["消息ID"] = str(msg_dict["消息ID"])
        if isinstance(msg_dict.get("发送者ID"), uuid.UUID):
            msg_dict["发送者ID"] = str(msg_dict["发送者ID"])
        # Add other UUID fields if necessary

    assert response.json() == expected_json
    
    mock_chat_service.get_messages_between_users_for_product.assert_called_once_with(
        product_id=product_id_str,
        user_id1=mock_current_user.id,
        user_id2=other_user_id_str,
        page_number=page_num,
        page_size=page_size
    )

def test_get_product_chat_messages_invalid_params():
    product_id = str(uuid.uuid4())
    other_user_id = str(uuid.uuid4())
    # Test with invalid page_number (FastAPI will handle this via Query validation)
    response = client.get(f"/api/v1/chat/messages/{product_id}/{other_user_id}?page_number=0&page_size=10")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY # FastAPI's validation error

    # Test with service raising InvalidInputError (if service validation fails for IDs)
    mock_chat_service.get_messages_between_users_for_product.side_effect = InvalidInputError(message="Invalid product ID", field_errors={"product_id": "Not a valid UUID"})
    response = client.get(f"/api/v1/chat/messages/invalid-product-id/{other_user_id}?page_number=1&page_size=10")
    assert response.status_code == status.HTTP_400_BAD_REQUEST # Our handler for InvalidInputError
    assert "product_id" in response.json()["detail"]

# PUT /api/v1/chat/messages/{message_id}/read
def test_mark_message_read_success():
    message_id_obj = uuid.uuid4()
    
    # Assuming MarkAsReadResponse is the Pydantic model
    # Ensure fields: MarkedAsReadMessageID, Result
    expected_model_instance = MarkAsReadResponse(
        MarkedAsReadMessageID=str(message_id_obj), # Corrected: Ensure str
        Result="消息已成功标记为已读"
    )
    mock_chat_service.mark_message_as_read.return_value = expected_model_instance

    response = client.put(f"/api/v1/chat/messages/{str(message_id_obj)}/read")

    assert response.status_code == status.HTTP_200_OK
    
    response_json = response.json()
    assert response_json["MarkedAsReadMessageID"] == str(message_id_obj)
    assert response_json["Result"] == "消息已成功标记为已读"
    
    mock_chat_service.mark_message_as_read.assert_called_once_with(message_id=str(message_id_obj), user_id=mock_current_user.id)

def test_mark_message_read_not_found():
    message_id = str(uuid.uuid4())
    mock_chat_service.mark_message_as_read.side_effect = NotFoundError(message="Message not found or not accessible")

    response = client.put(f"/api/v1/chat/messages/{message_id}/read")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Message not found or not accessible"

# PUT /api/v1/chat/conversations/{product_id}/hide
def test_hide_conversation_success():
    product_id_obj = uuid.uuid4()
    
    # Assuming HideConversationResponse is the Pydantic model
    # Ensure fields: Result, ProductID, UserID
    expected_model_instance = HideConversationResponse(
        Result="会话已成功隐藏",
        ProductID=str(product_id_obj), # Corrected: Ensure str
        UserID=str(mock_current_user.id) # UserID from model is Optional[str], mock_current_user.id is str
    )
    mock_chat_service.hide_conversation.return_value = expected_model_instance

    response = client.put(f"/api/v1/chat/conversations/{str(product_id_obj)}/hide")

    assert response.status_code == status.HTTP_200_OK
    
    response_json = response.json()
    assert response_json["Result"] == "会话已成功隐藏"
    assert response_json["ProductID"] == str(product_id_obj)
    assert response_json["UserID"] == str(mock_current_user.id) # Compare with string version of UUID
    
    mock_chat_service.hide_conversation.assert_called_once_with(product_id=str(product_id_obj), user_id=mock_current_user.id)

def test_hide_conversation_not_found(): # e.g. if product/conversation doesn't exist for user
    product_id = str(uuid.uuid4())
    mock_chat_service.hide_conversation.side_effect = NotFoundError(message="Conversation for this product not found for the user.")

    response = client.put(f"/api/v1/chat/conversations/{product_id}/hide")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Conversation for this product not found for the user."

def test_hide_conversation_op_error():
    product_id = str(uuid.uuid4())
    mock_chat_service.hide_conversation.side_effect = ChatOperationError(message="Failed to update visibility in DB")

    response = client.put(f"/api/v1/chat/conversations/{product_id}/hide")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "Failed to update visibility in DB"

# Example of testing unhandled exception in service converted to 500
# (Though handle_chat_service_exception tries to catch ChatServiceError subtypes specifically)
def test_send_message_unhandled_service_exception():
    payload = {"receiver_id": str(uuid.uuid4()), "product_id": str(uuid.uuid4()), "content": "Risky content"}
    # Simulate an unexpected error not directly subclassing one of the handled ones but still a ChatServiceError
    class UnknownChatError(ChatServiceError):
        pass
    mock_chat_service.send_message.side_effect = UnknownChatError("Some very unique service problem")

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "Some very unique service problem"


def test_send_message_generic_exception_from_service():
    payload = {"receiver_id": str(uuid.uuid4()), "product_id": str(uuid.uuid4()), "content": "Generic error content"}
    mock_chat_service.send_message.side_effect = Exception("A wild generic Python error appeared!")

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred: A wild generic Python error appeared!" 