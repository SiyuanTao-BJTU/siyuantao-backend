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
    mock_return_service.reset_mock() # This will reset side_effect and return_value of children too
    # Set default return values for methods that might be called without specific test setup
    # or where an empty list is a safe default.
    mock_return_service.get_all_return_requests.return_value = []
    mock_return_service.get_user_return_requests.return_value = []
    # For other methods, they will default to returning a new MagicMock if called without setup,
    # which is often fine, or tests will explicitly set their return_value/side_effect.

# --- Test Cases ---

# POST /api/v1/returns
def test_create_return_request_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    payload = {"order_id": str(uuid.uuid4()), "return_reason": "Item defective."}
    new_rr_id = str(uuid.uuid4())
    expected_response_data = {"Result": "退货请求已成功创建。", "NewReturnRequestID": new_rr_id}
    
    pydantic_response_instance = ReturnRequestCreateResponse(**expected_response_data)
    # mock_return_service.create_return_request = MagicMock(return_value=pydantic_response_instance) # Old way
    mock_return_service.create_return_request.return_value = pydantic_response_instance
    mock_return_service.create_return_request.side_effect = None


    response = client.post("/api/v1/returns", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == expected_response_data
    mock_return_service.create_return_request.assert_called_once_with(
        order_id=payload["order_id"],
        buyer_id=mock_current_buyer.id,
        return_reason=payload["return_reason"]
    )
    # app.dependency_overrides.clear() # Clear after test

# Renamed and refocused test for Pydantic validation failure (reason too short)
def test_create_return_request_pydantic_validation_fails_on_short_reason():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    
    payload = {"order_id": str(uuid.uuid4()), "return_reason": "short"} # "short" is 5 chars, min_length is 10

    # Reset specific mock for this method to ensure Pydantic validation is tested, not a prior side_effect
    mock_return_service.create_return_request.return_value = MagicMock() # Default MagicMock
    mock_return_service.create_return_request.side_effect = None


    response = client.post("/api/v1/returns", json=payload)
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in response.json()
    found_reason_error = False
    # FastAPI's 422 error detail is a list of error objects
    for error in response.json()["detail"]: 
        if error.get("type") == "string_too_short" and "return_reason" in error.get("loc", []):
            found_reason_error = True
            # Pydantic v2 places min_length in ctx. For v1 it might be different.
            # Adjust if necessary based on actual error structure from Pydantic version.
            assert error.get("ctx", {}).get("min_length") == 10 
            break
    assert found_reason_error, "Validation error for return_reason's min_length not found in 422 response detail."

    # app.dependency_overrides.clear() # Clear after test

# PUT /api/v1/returns/{request_id}/handle
def test_handle_return_request_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": True, "audit_idea": "Approved by seller."}
    expected_response_data = {"Result": "退货请求处理成功。"}
    
    # Explicitly create a MagicMock for the method and set its return_value
    # pydantic_response_instance = ReturnRequestHandleResponse(**expected_response_data)
    # mock_return_service.handle_return_request = MagicMock(return_value=pydantic_response_instance) # Old way
    # mock_return_service.handle_return_request.return_value = pydantic_response_instance
    mock_return_service.handle_return_request.return_value = expected_response_data # Return dict directly
    mock_return_service.handle_return_request.side_effect = None

    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.handle_return_request.assert_called_once_with(
        return_request_id=request_id,
        seller_id=mock_current_seller.id,
        is_agree=payload["is_agree"],
        audit_idea=payload["audit_idea"]
    )
    # app.dependency_overrides.clear() # Clear after test

def test_handle_return_request_permission_denied():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": False, "audit_idea": "Attempting to handle"}
    # mock_return_service.handle_return_request.side_effect = PermissionDeniedError("Not your request to handle") # Old way - partly correct
    mock_return_service.handle_return_request.side_effect = PermissionDeniedError("Not your request to handle")
    mock_return_service.handle_return_request.return_value = MagicMock() # Ensure return_value is not the previous success one


    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Not your request to handle"
    # app.dependency_overrides.clear() # Clear after test

# PUT /api/v1/returns/{request_id}/intervene
def test_buyer_request_intervention_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    request_id = str(uuid.uuid4())
    expected_response_data = {"Result": "申请管理员介入成功。"}
    
    # pydantic_response_instance = ReturnRequestInterveneResponse(**expected_response_data)
    # mock_return_service.buyer_request_intervention = MagicMock(return_value=pydantic_response_instance) # Old way
    # mock_return_service.buyer_request_intervention.return_value = pydantic_response_instance
    mock_return_service.buyer_request_intervention.return_value = expected_response_data # Return dict directly
    mock_return_service.buyer_request_intervention.side_effect = None

    response = client.put(f"/api/v1/returns/{request_id}/intervene")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.buyer_request_intervention.assert_called_once_with(
        return_request_id=request_id,
        buyer_id=mock_current_buyer.id
    )
    # app.dependency_overrides.clear() # Clear after test

# GET /api/v1/returns/admin
def test_admin_get_all_return_requests_success():
    app.dependency_overrides[get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep
    mock_requests_list_data = [
        {"退货请求ID": str(uuid.uuid4()), "订单ID": str(uuid.uuid4()), "商品名称": "Test Item 1", "创建时间": "2023-01-01T12:00:00Z", "状态": "等待处理", "买家ID": str(uuid.uuid4()), "卖家ID": str(uuid.uuid4())}
    ]
    # pydantic_list = [ReturnRequestListItemResponse(**item) for item in mock_requests_list_data]
    # mock_return_service.get_all_return_requests = MagicMock(return_value=pydantic_list) # Old way
    # mock_return_service.get_all_return_requests.return_value = pydantic_list
    mock_return_service.get_all_return_requests.return_value = mock_requests_list_data # Return list of dicts directly
    mock_return_service.get_all_return_requests.side_effect = None

    response = client.get("/api/v1/returns/admin?page=1&page_size=10")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_requests_list_data # Assert against the original data dict
    mock_return_service.get_all_return_requests.assert_called_once_with(admin_id=mock_current_admin.id, page=1, page_size=10)
    # app.dependency_overrides.clear() # Clear after test

# PUT /api/v1/returns/{request_id}/admin/resolve
def test_admin_resolve_return_request_success():
    app.dependency_overrides[get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep
    request_id = str(uuid.uuid4())
    payload = {"new_status": "管理员同意退款", "audit_idea": "Resolved by admin."}
    expected_response_data = {"Result": "管理员处理退货请求成功。"}
    
    # mock_return_service.admin_resolve_return_request = MagicMock(return_value=pydantic_response_instance) # Old way
    # mock_return_service.admin_resolve_return_request.return_value = pydantic_response_instance
    mock_return_service.admin_resolve_return_request.return_value = expected_response_data # Return dict directly
    mock_return_service.admin_resolve_return_request.side_effect = None

    response = client.put(f"/api/v1/returns/{request_id}/admin/resolve", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    mock_return_service.admin_resolve_return_request.assert_called_once_with(
        return_request_id=request_id,
        admin_id=mock_current_admin.id,
        new_status=payload["new_status"],
        audit_idea=payload["audit_idea"]
    )
    # app.dependency_overrides.clear()

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
    # pydantic_response_instance = ReturnRequestDetailResponse(**mock_details_data)
    # mock_return_service.get_return_request_detail = MagicMock(return_value=pydantic_response_instance) # Old way
    mock_return_service.get_return_request_detail.return_value = mock_details_data # Return dict directly
    mock_return_service.get_return_request_detail.side_effect = None

    headers = {"X-Test-User-Id": user_id_for_test, "X-Test-User-Roles": "user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_details_data
    mock_return_service.get_return_request_detail.assert_called_once_with(
        return_request_id=request_id,
        requesting_user_id=user_id_for_test,
        requesting_user_roles=["user"] # Updated assertion
    )
    # app.dependency_overrides.clear() # This was missing from original snippet but likely exists, remove if so. Will check full file.

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
    # pydantic_response_instance = ReturnRequestDetailResponse(**mock_details_data)
    # mock_return_service.get_return_request_detail = MagicMock(return_value=pydantic_response_instance) # Old way
    mock_return_service.get_return_request_detail.return_value = mock_details_data # Return dict directly
    mock_return_service.get_return_request_detail.side_effect = None

    headers = {"X-Test-User-Id": admin_id_for_test, "X-Test-User-Roles": "admin,user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_details_data
    mock_return_service.get_return_request_detail.assert_called_once_with(
        return_request_id=request_id,
        requesting_user_id=admin_id_for_test,
        requesting_user_roles=["admin", "user"] # Updated assertion
    )
    # app.dependency_overrides.clear() # This was missing from original snippet but likely exists, remove if so. Will check full file.

def test_get_return_request_detail_not_found():
    request_id = str(uuid.uuid4())
    user_id_for_test = str(uuid.uuid4())
    # mock_return_service.get_return_request_detail.side_effect = NotFoundError("Return request not found") # Old way - partly correct
    mock_return_service.get_return_request_detail.side_effect = NotFoundError("Return request not found")
    mock_return_service.get_return_request_detail.return_value = MagicMock() # Ensure return_value is not a previous success one

    headers = {"X-Test-User-Id": user_id_for_test, "X-Test-User-Roles": "user"}
    response = client.get(f"/api/v1/returns/{request_id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Return request not found"
    # app.dependency_overrides.clear() # This was missing from original snippet but likely exists, remove if so. Will check full file.

# GET /api/v1/returns/me/requests
def test_get_my_return_requests_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    mock_user_requests_data = [
        {"退货请求ID": str(uuid.uuid4()), "订单ID": "order789", "商品名称": "My Test Item", "创建时间": "2023-01-03T10:00:00Z", "状态": "已解决", "买家ID": mock_current_buyer.id, "卖家ID": str(uuid.uuid4())}
    ]
    mock_return_service.get_user_return_requests.return_value = mock_user_requests_data
    mock_return_service.get_user_return_requests.side_effect = None

    response = client.get("/api/v1/returns/me/requests")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_user_requests_data # Assert against the original data dict
    mock_return_service.get_user_return_requests.assert_called_once_with(
        user_id=mock_current_buyer.id
    ) # page and page_size are not passed by the route
    # app.dependency_overrides.clear()

def test_get_my_return_requests_service_error():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    # mock_return_service.get_user_return_requests.side_effect = ReturnOperationError("DB connection failed") # Old way - partly correct
    mock_return_service.get_user_return_requests.side_effect = ReturnOperationError("DB connection failed")
    mock_return_service.get_user_return_requests.return_value = MagicMock() # Ensure return_value is not a previous success one

    response = client.get("/api/v1/returns/me/requests")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "DB connection failed"
    # app.dependency_overrides.clear()

# Test for service layer InvalidInputError resulting in HTTP 400
def test_create_return_request_service_layer_invalid_input_returns_400():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer

    payload = {"order_id": str(uuid.uuid4()), "return_reason": "This reason is perfectly valid for Pydantic."}
    expected_field_errors = {"custom_field": "Service layer validation failed for this field."}

    mock_return_service.create_return_request.side_effect = InvalidInputError("Service level input error.", field_errors=expected_field_errors)
    mock_return_service.create_return_request.return_value = MagicMock()

    response = client.post("/api/v1/returns", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_json = response.json()
    assert "detail" in response_json
    assert response_json["detail"] == expected_field_errors

    # app.dependency_overrides.clear()
    # Ensure the correct user ID was passed to the service for create_return_request
    mock_return_service.create_return_request.assert_called_once_with(
        order_id=payload["order_id"],
        buyer_id=mock_current_buyer.id,
        return_reason=payload["return_reason"]
    )
    # The following erroneous lines, if they exist from a previous incorrect merge/edit, will be effectively removed 
    # by not re-stating them if the apply model correctly targets the section based on the surrounding correct code.
    # Specifically, any mock_return_service.get_return_request_detail.assert_called_once_with(...) 
    # and associated app.dependency_overrides.clear() lines within THIS TEST FUNCTION will be gone if not re-specified.

# Ensure this test is the last one or handle overrides carefully if more tests follow in this file.
# No more tests after this in the provided snippet. 