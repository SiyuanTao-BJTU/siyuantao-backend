import uuid
import pytest
from fastapi import FastAPI, status, Depends
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Optional

# Corrected Module imports
from app.routers.return_routes import router as return_router
from app.routers.return_routes import (
    get_return_request_service, 
    get_current_user_dep, 
    get_current_active_admin_user_dep,
    get_requesting_user_for_details # Assuming this remains for header-based user details
)
from app.routers.return_routes import User as ApiUser 
from app.services.return_request_service import (
    ReturnRequestService,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    OperationConflictError,
    ReturnOperationError,
    ReturnRequestServiceError
)
from app.models.enums import ReturnReasonCode, AdminResolutionAction # Import enums

# Import Pydantic models used in tests
from app.routers.return_routes import (
    ReturnRequestCreateRequest, # For payload typing, if needed for clarity
    ReturnRequestCreateResponse,
    ReturnRequestHandleRequest, # For payload typing
    ReturnRequestHandleResponse,
    ReturnRequestInterventionBody, # New request body model
    ReturnRequestInterveneResponse,
    AdminReturnResolveRequest, # For payload typing
    AdminReturnResolveResponse,
    ReturnRequestDetailResponse, 
    ReturnRequestListItemResponse 
)

# Mock ReturnRequestService instance
mock_return_service = MagicMock(spec=ReturnRequestService)

# Mock current user placeholders
mock_buyer_id = str(uuid.uuid4())
mock_seller_id = str(uuid.uuid4())
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin") # Should not happen if mock is admin
    return mock_current_admin

async def override_get_return_request_service(): 
    return mock_return_service

app = FastAPI()
app.include_router(return_router)
# app.dependency_overrides[get_return_request_service] = override_get_return_request_service # Moved to fixture

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_app_overrides_and_reset_mocks(): # Renamed and updated logic
    # 1. Reset the global mock service's state
    mock_return_service.reset_mock() 
    # 2. Ensure all its known method mocks are also thoroughly reset
    methods_on_service_spec = [
        'create_return_request', 'handle_return_request', 'buyer_request_intervention',
        'admin_resolve_return_request', 'get_return_request_detail',
        'get_user_return_requests', 'get_all_return_requests'
    ]
    for method_name in methods_on_service_spec:
        if hasattr(mock_return_service, method_name):
            attribute_mock = getattr(mock_return_service, method_name)
            attribute_mock.reset_mock(return_value=True, side_effect=True) 

    # 3. Re-apply core dependency override before each test
    app.dependency_overrides[get_return_request_service] = override_get_return_request_service
    
    yield # Test execution point

    # 4. Clean up all overrides after the test (good practice)
    app.dependency_overrides.clear()

# --- Test Cases ---

# POST /api/v1/returns
def test_create_return_request_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    payload = {
        "order_id": str(uuid.uuid4()), 
        "request_reason_detail": "Item defective.",
        "return_reason_code": ReturnReasonCode.DEFECTIVE.value # Pass enum string value
    }
    new_rr_id = str(uuid.uuid4())
    expected_service_response = {"Result": "退货请求已成功创建。", "NewReturnRequestID": new_rr_id}
    mock_return_service.create_return_request.return_value = expected_service_response

    response = client.post("/api/v1/returns", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json() == expected_service_response # API returns what service returns
    mock_return_service.create_return_request.assert_called_once_with(
        order_id=payload["order_id"],
        buyer_id=mock_current_buyer.id,
        request_reason_detail=payload["request_reason_detail"],
        return_reason_code=ReturnReasonCode.DEFECTIVE # Service expects enum type
    )

def test_create_return_request_pydantic_validation_fails_invalid_enum():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    payload = {
        "order_id": str(uuid.uuid4()), 
        "request_reason_detail": "Valid reason detail.",
        "return_reason_code": "INVALID_ENUM_VALUE"
    }
    response = client.post("/api/v1/returns", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # Check for specific error related to return_reason_code
    error_found = any("return_reason_code" in err.get("loc", []) for err in response.json().get("detail", []))
    assert error_found, "Pydantic validation error for return_reason_code not found."

# PUT /api/v1/returns/{request_id}/handle
def test_handle_return_request_success_with_notes():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": True, "audit_idea": "Approved by seller."}
    expected_response_data = {"Result": "退货请求处理成功。"}
    
    def mock_side_effect(*args, **kwargs):
        return expected_response_data
    
    mock_return_service.handle_return_request.side_effect = mock_side_effect
    mock_return_service.handle_return_request.return_value = None

    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    
    mock_return_service.handle_return_request.assert_called_once_with(
        return_request_id=request_id,
        seller_id=mock_current_seller.id,
        is_agree=payload["is_agree"],
        audit_idea=payload["audit_idea"]
    )
    mock_return_service.handle_return_request.side_effect = None

def test_handle_return_request_success_no_notes():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_seller
    request_id = str(uuid.uuid4())
    payload = {"is_agree": True, "audit_idea": None} 
    expected_response_data = {"Result": "退货请求处理成功。"}
    
    def mock_side_effect(*args, **kwargs):
        return expected_response_data
        
    mock_return_service.handle_return_request.side_effect = mock_side_effect
    mock_return_service.handle_return_request.return_value = None

    response = client.put(f"/api/v1/returns/{request_id}/handle", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    
    mock_return_service.handle_return_request.assert_called_once_with(
        return_request_id=request_id,
        seller_id=mock_current_seller.id,
        is_agree=payload["is_agree"],
        audit_idea=None
    )
    mock_return_service.handle_return_request.side_effect = None

# PUT /api/v1/returns/{request_id}/intervene
def test_buyer_request_intervention_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    request_id = str(uuid.uuid4())
    payload = {"intervention_reason": "Seller rejected without valid cause."}
    expected_response_data = {"Result": "申请管理员介入成功。"}
    
    def mock_side_effect(*args, **kwargs):
        return expected_response_data
        
    mock_return_service.buyer_request_intervention.side_effect = mock_side_effect
    mock_return_service.buyer_request_intervention.return_value = None

    response = client.put(f"/api/v1/returns/{request_id}/intervene", json=payload) 

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    
    mock_return_service.buyer_request_intervention.assert_called_once_with(
        return_request_id=request_id,
        buyer_id=mock_current_buyer.id,
        intervention_reason=payload["intervention_reason"] 
    )
    mock_return_service.buyer_request_intervention.side_effect = None

# PUT /api/v1/returns/{request_id}/admin/resolve
def test_admin_resolve_return_request_success():
    app.dependency_overrides[get_current_active_admin_user_dep] = override_get_current_active_admin_user_dep
    request_id = str(uuid.uuid4())
    payload = {
        "resolution_action": AdminResolutionAction.REFUND_APPROVED.value, # Pass enum string value
        "admin_notes": "Admin resolved, refund approved."
    }
    expected_response_data = {"Result": "管理员处理退货请求成功。"} 

    # 使用 side_effect 来确保返回值
    def mock_admin_resolve_side_effect(*args, **kwargs):
        return expected_response_data

    mock_return_service.admin_resolve_return_request.side_effect = mock_admin_resolve_side_effect
    # Ensure return_value is not something that would interfere (though side_effect takes precedence)
    mock_return_service.admin_resolve_return_request.return_value = None 

    response = client.put(f"/api/v1/returns/{request_id}/admin/resolve", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_response_data
    
    mock_return_service.admin_resolve_return_request.assert_called_once_with(
        return_request_id=request_id,
        admin_id=mock_current_admin.id,
        resolution_action=AdminResolutionAction.REFUND_APPROVED, # Service expects enum type
        admin_notes=payload["admin_notes"]
    )
    mock_return_service.admin_resolve_return_request.side_effect = None

# GET /api/v1/returns/{request_id}
def test_get_return_request_detail_as_user_success():
    app.dependency_overrides[get_requesting_user_for_details] = override_get_current_user_dep_buyer
    request_id = str(uuid.uuid4())
    
    fixed_order_id = str(uuid.uuid4())
    fixed_seller_id = str(uuid.uuid4())
    mock_data_from_service = {
        "退货请求ID": request_id,
        "订单ID": fixed_order_id,
        "买家ID": mock_current_buyer.id, 
        "卖家ID": fixed_seller_id,
        "商品ID": None, 
        "创建时间": "2023-01-01T12:00:00Z", 
        "状态": "等待卖家处理",
        "退货原因详细说明": "Item defective",
        "退货原因代码": ReturnReasonCode.DEFECTIVE.value, 
        "卖家处理意见": None,
        "卖家处理时间": None,
        "管理员处理意见": None,
        "管理员处理时间": None,
        "resolution_details": "Return created by buyer."
    }

    expected_json_from_api = {
        "退货请求ID": request_id,
        "订单ID": fixed_order_id,
        "买家ID": mock_current_buyer.id,
        "卖家ID": fixed_seller_id,
        "商品ID": None,
        "创建时间": "2023-01-01T12:00:00Z",
        "状态": "等待卖家处理",
        "退货原因详细说明": "Item defective",
        "退货原因代码": ReturnReasonCode.DEFECTIVE.value,
        "卖家处理意见": None,
        "卖家处理时间": None,
        "管理员处理意见": None,
        "管理员处理时间": None,
        "resolution_details": "Return created by buyer." 
    }

    def mock_get_detail_side_effect(*args, **kwargs):
        return mock_data_from_service

    mock_return_service.get_return_request_detail.side_effect = mock_get_detail_side_effect
    mock_return_service.get_return_request_detail.return_value = None 

    response = client.get(f"/api/v1/returns/{request_id}")
    
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_json_from_api 

    mock_return_service.get_return_request_detail.assert_called_once_with(
        return_request_id=request_id,
        requesting_user_id=mock_current_buyer.id,
        requesting_user_roles=mock_current_buyer.roles
    )
    mock_return_service.get_return_request_detail.side_effect = None

# GET /api/v1/returns/me/requests
def test_get_my_return_requests_success():
    app.dependency_overrides[get_current_user_dep] = override_get_current_user_dep_buyer
    mock_list_data = [
        {
            "退货请求ID": str(uuid.uuid4()), "订单ID": str(uuid.uuid4()), 
            "商品名称": "Test Item 1", "创建时间": "2023-01-01T12:00:00Z", 
            "状态": "等待处理", "买家ID": mock_current_buyer.id, "卖家ID": str(uuid.uuid4()),
            "退货原因代码": ReturnReasonCode.WRONG_ITEM_RECEIVED.value 
        }
    ]
    
    def mock_side_effect(*args, **kwargs):
        return mock_list_data
        
    mock_return_service.get_user_return_requests.side_effect = mock_side_effect
    mock_return_service.get_user_return_requests.return_value = None

    response = client.get("/api/v1/returns/me/requests")
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["退货原因代码"] == ReturnReasonCode.WRONG_ITEM_RECEIVED.value
    
    mock_return_service.get_user_return_requests.assert_called_once_with(user_id=mock_current_buyer.id)
    mock_return_service.get_user_return_requests.side_effect = None

# Placeholder for other existing tests that might need review for parameter changes
# Example: test_create_return_request_service_layer_invalid_input_returns_400
# This test would need its payload updated if it calls the create endpoint.

# ... (other tests like not_found, permission_denied, etc. should be reviewed
# to ensure their mock service calls are updated if method signatures changed) 