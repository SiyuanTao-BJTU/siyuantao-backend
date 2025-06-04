import uuid
import pytest
from fastapi import FastAPI, status, Depends
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from typing import List, Tuple, Dict, Any, Optional

# Corrected Module imports
from app.routers.chat_routes import router as chat_router
from app.routers.chat_routes import get_current_user as chat_api_get_current_user # Renamed for clarity in test file
from app.routers.chat_routes import get_chat_service
from app.services.chat_service import (
    ChatService,
    InvalidInputError,
    NotFoundError,
    ChatOperationError,
    ChatServiceError
)
from app.routers.chat_routes import User as ApiUser # Use User model from chat_routes
from app.routers.chat_routes import (
    MessageCreateRequest,
    SendMessageResponse, # Import new response model
    ConversationResponseItem,
    PaginatedChatMessagesResponse,
    MarkAsReadResponse,
    HideConversationResponse,
    ChatMessageItem
)
# Removed: from pydantic import BaseModel (ApiUser is now imported)

# Mock ChatService instance
mock_chat_service = MagicMock(spec=ChatService) # Use spec for better mocking

# Mock current user
mock_user_id_str = str(uuid.uuid4())
mock_current_user_obj = ApiUser(id=mock_user_id_str, username="test_api_user")

async def override_get_current_user() -> ApiUser:
    return mock_current_user_obj

def override_get_chat_service() -> ChatService:
    return mock_chat_service

app = FastAPI()
app.include_router(chat_router)
app.dependency_overrides[chat_api_get_current_user] = override_get_current_user
app.dependency_overrides[get_chat_service] = override_get_chat_service

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_mocks_fixture():
    mock_chat_service.reset_mock()
    # Ensure methods exist on the mock spec
    # For MagicMock(spec=ChatService), attributes not on ChatService will raise AttributeError
    # If ChatService has these methods, reset them. Otherwise, tests will fail if they call non-existent methods.
    methods_on_chat_service_spec = [
        'send_message', 'get_conversations', 'get_messages_between_users_for_product',
        'mark_message_as_read', 'hide_conversation'
    ]
    for method_name in methods_on_chat_service_spec:
        if hasattr(mock_chat_service, method_name):
            getattr(mock_chat_service, method_name).reset_mock()
            # Set default return values if necessary, or let individual tests configure them
            # getattr(mock_chat_service, method_name).return_value = None 
            # getattr(mock_chat_service, method_name).side_effect = None 

# --- Test Cases ---

# POST /api/v1/chat/messages
def test_send_chat_message_newly_created():
    test_client_msg_id = str(uuid.uuid4())
    payload = {
        "receiver_id": str(uuid.uuid4()), 
        "product_id": str(uuid.uuid4()), 
        "content": "Hello there!",
        "client_message_id": test_client_msg_id
    }
    
    mock_message_id_obj = uuid.uuid4()
    # Service now returns (message_id_uuid, is_newly_created_bool)
    mock_chat_service.send_message.return_value = (mock_message_id_obj, True)

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    response_json = response.json()
    assert response_json["message_id"] == str(mock_message_id_obj)
    assert response_json["is_newly_created"] is True

    mock_chat_service.send_message.assert_called_once_with(
        sender_id=mock_current_user_obj.id,
        receiver_id=payload["receiver_id"],
        product_id=payload["product_id"],
        content=payload["content"],
        client_message_id=test_client_msg_id
    )

def test_send_chat_message_idempotent_hit():
    test_client_msg_id = str(uuid.uuid4())
    payload = {
        "receiver_id": str(uuid.uuid4()), 
        "product_id": str(uuid.uuid4()), 
        "content": "Hello again!",
        "client_message_id": test_client_msg_id
    }
    
    mock_message_id_obj = uuid.uuid4()
    mock_chat_service.send_message.return_value = (mock_message_id_obj, False) # is_newly_created is False

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_200_OK # Idempotent hit should be 200 OK
    response_json = response.json()
    assert response_json["message_id"] == str(mock_message_id_obj)
    assert response_json["is_newly_created"] is False

    mock_chat_service.send_message.assert_called_once_with(
        sender_id=mock_current_user_obj.id,
        receiver_id=payload["receiver_id"],
        product_id=payload["product_id"],
        content=payload["content"],
        client_message_id=test_client_msg_id
    )

def test_send_chat_message_invalid_input_from_service():
    # Service raises InvalidInputError, API should return 400
    test_client_msg_id = str(uuid.uuid4())
    payload = {
        "receiver_id": "invalid-uuid-format", # Example of an error service would catch
        "product_id": str(uuid.uuid4()), 
        "content": "Valid content",
        "client_message_id": test_client_msg_id
    }
    mock_chat_service.send_message.side_effect = InvalidInputError(
        message="Validation failed", field_errors={"receiver_id": "Invalid receiver ID format."}
    )

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "receiver_id" in response.json()["detail"]
    # Ensure service method was called with attempts
    mock_chat_service.send_message.assert_called_once_with(
        sender_id=mock_current_user_obj.id,
        receiver_id=payload["receiver_id"],
        product_id=payload["product_id"],
        content=payload["content"],
        client_message_id=test_client_msg_id
    )

def test_send_chat_message_service_operation_error():
    test_client_msg_id = str(uuid.uuid4())
    payload = {
        "receiver_id": str(uuid.uuid4()), 
        "product_id": str(uuid.uuid4()), 
        "content": "Test content for op error",
        "client_message_id": test_client_msg_id
    }
    mock_chat_service.send_message.side_effect = ChatOperationError(message="DAL failed to send")

    response = client.post("/api/v1/chat/messages", json=payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "DAL failed to send"
    mock_chat_service.send_message.assert_called_once_with(
        sender_id=mock_current_user_obj.id,
        receiver_id=payload["receiver_id"],
        product_id=payload["product_id"],
        content=payload["content"],
        client_message_id=test_client_msg_id
    )

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
    
    mock_chat_service.get_conversations.assert_called_once_with(user_id=mock_current_user_obj.id)

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
        发送者ID=mock_current_user_obj.id, 
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
        user_id1=mock_current_user_obj.id,
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
    
    mock_chat_service.mark_message_as_read.assert_called_once_with(message_id=str(message_id_obj), user_id=mock_current_user_obj.id)

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
        UserID=str(mock_current_user_obj.id) # UserID from model is Optional[str], mock_current_user_obj.id is str
    )
    mock_chat_service.hide_conversation.return_value = expected_model_instance

    response = client.put(f"/api/v1/chat/conversations/{str(product_id_obj)}/hide")

    assert response.status_code == status.HTTP_200_OK
    
    response_json = response.json()
    assert response_json["Result"] == "会话已成功隐藏"
    assert response_json["ProductID"] == str(product_id_obj)
    assert response_json["UserID"] == str(mock_current_user_obj.id) # Corrected variable name
    
    mock_chat_service.hide_conversation.assert_called_once_with(
        product_id=str(product_id_obj),
        user_id=mock_current_user_obj.id
    )

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