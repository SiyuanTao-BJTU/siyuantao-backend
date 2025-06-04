import uuid
import pytest
from fastapi import FastAPI, status, Depends
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Optional

# Modules to test
from backend.src.modules.return_request.api.return_routes import router as return_router
from backend.src.modules.return_request.api.return_routes import get_return_request_service # Added import
from backend.src.modules.return_request.api.return_routes import get_current_user_dep, get_current_active_admin_user_dep # Added imports
from backend.src.modules.return_request.api.return_routes import User as ApiUser # User model from API
from backend.src.modules.return_request.api.return_routes import ReturnRequestDetailResponse # Added import
from backend.src.modules.return_request.services.return_request_service import (
    ReturnRequestService,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    OperationConflictError,
    ReturnOperationError,
    ReturnRequestServiceError
)
# Import Pydantic models for responses
from backend.src.modules.return_request.api.return_routes import (
    ReturnRequestCreateResponse,
    ReturnRequestHandleResponse,
    ReturnRequestInterveneResponse,
    AdminReturnResolveResponse,
    ReturnRequestListItemResponse # For list endpoints later
)
# Import Pydantic models for request/response if needed for constructing payloads/expected responses manually
# from backend.src.modules.return_request.api.return_routes import ReturnRequestCreateRequest, ...

# Mock ReturnRequestService instance
mock_return_service = MagicMock()

# Mock current user placeholders
mock_buyer_id = str(uuid.uuid4())
mock_seller_id = str(uuid.uuid4()) # Assuming seller is also a general user for some endpoints
mock_admin_id = str(uuid.uuid4())

mock_current_buyer = ApiUser(id=mock_buyer_id, username="test_buyer", roles=["user"])
mock_current_seller = ApiUser(id=mock_seller_id, username="test_seller", roles=["user"])
mock_current_admin = ApiUser(id=mock_admin_id, username="test_admin", roles=["admin", "user"])

# Override functions for dependencies
async def override_get_current_user_dep_buyer() -> ApiUser:
    return mock_current_buyer

async def override_get_current_user_dep_seller() -> ApiUser:
    return mock_current_seller

async def override_get_current_active_admin_user_dep() -> ApiUser:
    if "admin" not in mock_current_admin.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin")
    return mock_current_admin

# For get_requesting_user_for_details, tests will set headers.
# So no specific override needed here if dependency reads headers directly.

async def override_get_return_request_service(): # Added override function
    return mock_return_service

app = FastAPI()

# Override the global service instance in return_routes.py for testing
# return_router.return_service_instance = mock_return_service # Removed this line

app.include_router(return_router)
app.dependency_overrides[get_return_request_service] = override_get_return_request_service # Added override

# Set up dependency overrides for specific test contexts if needed,
# otherwise rely on test-specific overrides or header-based mocks for `get_requesting_user_for_details`.
# For routes with fixed dependencies:
# app.dependency_overrides[return_router.get_current_user_dep] = ... # This will be tricky as it's used by multiple roles.
# app.dependency_overrides[return_router.get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_return_mocks():
    mock_return_service.reset_mock()
    # Ensure mocked methods for pagination/all requests are reset or re-mocked if necessary
    if hasattr(mock_return_service, 'get_all_return_requests'):
        mock_return_service.get_all_return_requests.return_value = []
    # For get_user_return_requests which might be mocked in routes if not callable
    mock_return_service.get_user_return_requests.return_value = [] 

# --- Test Cases ---

# POST /api/v1/returns
def test_create_return_request_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    payload = {"order_id": str(uuid.uuid4()), "return_reason": "Item defective."}
    new_rr_id = str(uuid.uuid4())
    expected_response_data = {"Result": "退货请求已成功创建。", "NewReturnRequestID": new_rr_id}
    
    pydantic_response_instance = ReturnRequestCreateResponse(**expected_response_data)
    mock_return_service.create_return_request = MagicMock(return_value=pydantic_response_instance)

    response = client.post("/api/v1/returns", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == expected_response_data
    mock_return_service.create_return_request.assert_called_once_with(
        order_id=payload["order_id"],
        buyer_id=mock_current_buyer.id,
        return_reason=payload["return_reason"]
    )
    app.dependency_overrides.clear() # Clear after test

def test_create_return_request_invalid_input():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    payload = {"order_id": "not-uuid", "return_reason": "Too short"} # FastAPI validation might catch order_id
    # Test service layer validation for reason
    mock_return_service.create_return_request.side_effect = InvalidInputError("Reason too short", field_errors={"return_reason": "too short"})
    
    # If order_id is caught by Pydantic first
    response_pydantic = client.post("/api/v1/returns", json={"order_id": "not-uuid", "return_reason": "Valid reason length........."})
    if response_pydantic.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        print("Pydantic validation for order_id worked as expected.")
    
    response = client.post("/api/v1/returns", json={"order_id": str(uuid.uuid4()), "return_reason": "short"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "return_reason" in response.json()["detail"]
    app.dependency_overrides.clear()

# PUT /api/v1/returns/{request_id}/handle
def test_handle_return_request_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": True, "audit_idea": "Approved by seller."}
    expected_response_data = {"Result": "退货请求处理成功。"}
    
    # Explicitly create a MagicMock for the method and set its return_value
    pydantic_response_instance = ReturnRequestHandleResponse(**expected_response_data)
    mock_return_service.handle_return_request = MagicMock(return_value=pydantic_response_instance)

    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.handle_return_request.assert_called_once_with(
        return_request_id=request_id,
        seller_id=mock_current_seller.id,
        is_agree=payload["is_agree"],
        audit_idea=payload["audit_idea"]
    )
    app.dependency_overrides.clear()

def test_handle_return_request_permission_denied():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": False, "audit_idea": "Attempting to handle"}
    mock_return_service.handle_return_request.side_effect = PermissionDeniedError("Not your request to handle")

    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Not your request to handle"
    app.dependency_overrides.clear()

# PUT /api/v1/returns/{request_id}/intervene
def test_buyer_request_intervention_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    request_id = str(uuid.uuid4())
    expected_response_data = {"Result": "申请管理员介入成功。"}
    
    pydantic_response_instance = ReturnRequestInterveneResponse(**expected_response_data)
    mock_return_service.buyer_request_intervention = MagicMock(return_value=pydantic_response_instance)

    response = client.put(f"/api/v1/returns/{request_id}/intervene")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.buyer_request_intervention.assert_called_once_with(
        return_request_id=request_id,
        buyer_id=mock_current_buyer.id
    )
    app.dependency_overrides.clear()

# GET /api/v1/returns/admin
def test_admin_get_all_return_requests_success():
    app.dependency_overrides[get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep
    mock_requests_list_data = [
        {"退货请求ID": str(uuid.uuid4()), "订单ID": str(uuid.uuid4()), "商品名称": "Test Item 1", "创建时间": "2023-01-01T12:00:00Z", "状态": "等待处理", "买家ID": str(uuid.uuid4()), "卖家ID": str(uuid.uuid4())}
    ]
    # Ensure the mock for get_all_return_requests is correctly set up
    # if not hasattr(mock_return_service, 'get_all_return_requests') or not isinstance(mock_return_service.get_all_return_requests, MagicMock):
    #     mock_return_service.get_all_return_requests = MagicMock() # This check might be redundant now
    
    pydantic_list = [ReturnRequestListItemResponse(**item) for item in mock_requests_list_data]
    mock_return_service.get_all_return_requests = MagicMock(return_value=pydantic_list)

    response = client.get("/api/v1/returns/admin?page=1&page_size=10")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_requests_list_data # Assert against the original data dict
    mock_return_service.get_all_return_requests.assert_called_once_with(admin_id=mock_current_admin.id, page=1, page_size=10)
    app.dependency_overrides.clear()

# PUT /api/v1/returns/{request_id}/admin/resolve
def test_admin_resolve_return_request_success():
    app.dependency_overrides[get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep
    request_id = str(uuid.uuid4())
    payload = {"new_status": "管理员同意退款", "audit_idea": "Resolved by admin."}
    expected_response_data = {"Result": "管理员处理退货请求成功。"}
    
    pydantic_response_instance = AdminReturnResolveResponse(**expected_response_data)
    mock_return_service.admin_resolve_return_request = MagicMock(return_value=pydantic_response_instance)

    response = client.put(f"/api/v1/returns/{request_id}/admin/resolve", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.admin_resolve_return_request.assert_called_once_with(
        return_request_id=request_id,
        admin_id=mock_current_admin.id,
        new_status=payload["new_status"],
        audit_idea=payload["audit_idea"]
    )
    app.dependency_overrides.clear()

# GET /api/v1/returns/{request_id}
def test_get_return_request_detail_as_user_success():
    request_id = str(uuid.uuid4())
    user_id_for_test = str(uuid.uuid4())
    mock_details_data = {
        "退货请求ID": request_id, 
        "订单ID": "order123", 
        "买家ID": user_id_for_test, 
        "卖家ID": str(uuid.uuid4()), 
        "商品ID": None, 
        "创建时间": "2023-01-01T12:00:00Z", 
        "状态": "处理中", 
        "退货原因": "test reason",
        "处理意见": None, 
        "处理时间": None, 
        "管理员介入时间": None, 
        "管理员处理意见": None, 
        "管理员处理时间": None
    }
    pydantic_response_instance = ReturnRequestDetailResponse(**mock_details_data)
    mock_return_service.get_return_request_detail = MagicMock(return_value=pydantic_response_instance)

    headers = {"X-Test-User-Id": user_id_for_test, "X-Test-User-Roles": "user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_details_data
    mock_return_service.get_return_request_detail.assert_called_once_with(
        return_request_id=request_id,
        requesting_user_id=user_id_for_test,
        requesting_user_roles=["user"] # Updated assertion
    )

def test_get_return_request_detail_as_admin_success():
    request_id = str(uuid.uuid4())
    admin_id_for_test = str(uuid.uuid4())
    mock_details_data = {
        "退货请求ID": request_id, 
        "订单ID": "order456", 
        "买家ID": str(uuid.uuid4()), 
        "卖家ID": str(uuid.uuid4()), 
        "商品ID": "itemX", 
        "创建时间": "2023-01-02T14:30:00Z", 
        "状态": "待管理员介入", 
        "退货原因": "test admin reason",
        "处理意见": "Seller rejected, awaiting admin.", 
        "处理时间": "2023-01-02T10:00:00Z", 
        "管理员介入时间": None, 
        "管理员处理意见": None, 
        "管理员处理时间": None
    }
    pydantic_response_instance = ReturnRequestDetailResponse(**mock_details_data)
    mock_return_service.get_return_request_detail = MagicMock(return_value=pydantic_response_instance)

    headers = {"X-Test-User-Id": admin_id_for_test, "X-Test-User-Roles": "admin,user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_details_data
    mock_return_service.get_return_request_detail.assert_called_once_with(
        return_request_id=request_id,
        requesting_user_id=admin_id_for_test,
        requesting_user_roles=["admin", "user"] # Updated assertion
    )

def test_get_return_request_detail_not_found():
    request_id = str(uuid.uuid4())
    user_id_for_test = str(uuid.uuid4())
    mock_return_service.get_return_request_detail.side_effect = NotFoundError("Return request not found")
    headers = {"X-Test-User-Id": user_id_for_test, "X-Test-User-Roles": "user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Return request not found"

# GET /api/v1/returns/me/requests
def test_get_my_return_requests_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    mock_user_requests_data = [
        {"退货请求ID": str(uuid.uuid4()), "订单ID": "order789", "商品名称": "My Test Item", "创建时间": "2023-01-03T10:00:00Z", "状态": "已解决", "买家ID": mock_current_buyer.id, "卖家ID": str(uuid.uuid4())}
    ]
    pydantic_list = [ReturnRequestListItemResponse(**item) for item in mock_user_requests_data]
    mock_return_service.get_user_return_requests = MagicMock(return_value=pydantic_list)

    response = client.get("/api/v1/returns/me/requests") 
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_user_requests_data # Assert against the original data dict
    mock_return_service.get_user_return_requests.assert_called_once_with(
        user_id=mock_current_buyer.id
    )
    app.dependency_overrides.clear()

def test_get_my_return_requests_service_error():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    mock_return_service.get_user_return_requests.side_effect = ReturnOperationError("DB connection failed")
    response = client.get("/api/v1/returns/me/requests")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "DB connection failed"
    app.dependency_overrides.clear() 