import uuid
from typing import List, Dict, Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status, Request
from pydantic import BaseModel, Field

from unittest.mock import MagicMock # Keep for User model default if needed
from app.services.return_request_service import (
    ReturnRequestService,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    OperationConflictError,
    ReturnOperationError,
    ReturnRequestServiceError
)
from app.dal.return_request_dal import ReturnRequestDAL
from app.dal.order_dal import OrderDAL # Placeholder
from app.dal.product_dal import ProductDAL # Placeholder
# from your_db_connector import db_pool # Example
from app.models.enums import ReturnReasonCode, AdminResolutionAction # Added Enum imports

# --- Placeholder Authentication ---
class User(BaseModel): # General User Model
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str = "testuser"
    roles: List[str] = []

# Specific dependency for regular user
async def get_current_user_dep() -> User:
    # Simulate fetching a regular user. In a real app, this decodes a token.
    # For testing, we can assume a user.
    return User(id=str(uuid.uuid4()), username="testbuyer", roles=["user"])

# Specific dependency for admin user
async def get_current_active_admin_user_dep() -> User:
    # Simulate fetching an admin user.
    admin_id = str(uuid.uuid4())
    user = User(id=admin_id, username="testadmin", roles=["admin", "user"]) # Admins are also users
    if "admin" not in user.roles: # This is the "active admin" check
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have admin privileges.")
    return user

# Dependency for routes that can be accessed by either a regular user or an admin
async def get_requesting_user_for_details(request: Request) -> User:
    # This is a mock for testing. A real implementation would parse a token
    # and determine roles from the token's claims.
    # We can use a header to simulate different users for testing this endpoint.
    user_id_header = request.headers.get("X-Test-User-Id", str(uuid.uuid4()))
    user_roles_header = request.headers.get("X-Test-User-Roles", "user") # e.g., "user" or "admin,user"
    
    roles = [role.strip() for role in user_roles_header.split(',')]
    
    return User(id=user_id_header, username=f"testuser_{user_id_header[:4]}", roles=roles)


# --- Pydantic Models ---
class ReturnRequestCreateRequest(BaseModel):
    order_id: str = Field(..., description="ID of the order for which return is requested.")
    request_reason_detail: str = Field(..., min_length=10, max_length=2000, description="Detailed reason for the return request.")
    return_reason_code: ReturnReasonCode = Field(..., description="Standardized reason code for the return.")

class ReturnRequestCreateResponse(BaseModel):
    Result: str
    NewReturnRequestID: str

# Standard Error Response Model
class HTTPErrorDetail(BaseModel):
    detail: Any # Can be str or dict or list of dicts for validation errors

class ReturnRequestHandleRequest(BaseModel):
    is_agree: bool = Field(..., description="Whether the seller agrees to the return.")
    audit_idea: Optional[str] = Field(None, max_length=1000, description="Seller\'s comments or reasons for the decision.")

class ReturnRequestHandleResponse(BaseModel):
    Result: str

# New model for buyer intervention request body
class ReturnRequestInterventionBody(BaseModel):
    intervention_reason: str = Field(..., min_length=10, max_length=1000, description="Reason for requesting admin intervention.")

class ReturnRequestInterveneResponse(BaseModel): 
    Result: str

class AdminReturnResolveRequest(BaseModel):
    resolution_action: AdminResolutionAction = Field(..., description="The resolution action taken by the admin.")
    admin_notes: Optional[str] = Field(None, max_length=1000, description="Admin\'s comments or reasons for the resolution.")

class AdminReturnResolveResponse(BaseModel):
    Result: str

class ReturnRequestDetailResponse(BaseModel):
    退货请求ID: str
    订单ID: str
    买家ID: str
    卖家ID: str 
    商品ID: Optional[str] = None
    创建时间: Any 
    状态: str
    退货原因详细说明: str # Renamed from 退货原因 to map to RequestReason (detail text)
    退货原因代码: Optional[ReturnReasonCode] = None # Added
    卖家处理意见: Optional[str] = None # Maps to SellerNotes
    卖家处理时间: Optional[Any] = None # Maps to SellerActionDate
    # 管理员介入时间: Optional[Any] = None # This specific field might not exist; ResolutionDetails will have timestamps
    管理员处理意见: Optional[str] = None # Maps to AdminNotes
    管理员处理时间: Optional[Any] = None # Maps to ResolutionDate / AdminActionDate
    处理日志: Optional[str] = Field(None, alias="resolution_details", description="Detailed log of actions.") # Added ResolutionDetails

class ReturnRequestListItemResponse(BaseModel): 
    退货请求ID: str
    订单ID: str
    商品名称: Optional[str] = None 
    创建时间: Any
    状态: str
    买家ID: str 
    卖家ID: str 
    退货原因代码: Optional[ReturnReasonCode] = None # Added


# --- Router Definition ---
router = APIRouter(
    prefix="/api/v1/returns",
    tags=["Return Requests"]
)

def get_return_request_service() -> ReturnRequestService:
    # This service will be overridden in tests by app.dependency_overrides
    # For actual runtime, a real service instance would be returned.
    # Returning a plain MagicMock() here for the default case if not overridden
    # avoids the "attributes are also mocks" issue if this path was ever hit
    # directly by a part of the application not covered by an override during testing.
    return MagicMock()

def handle_return_service_exception(e: ReturnRequestServiceError):
    if isinstance(e, InvalidInputError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.field_errors or e.message)
    if isinstance(e, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    if isinstance(e, PermissionDeniedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    if isinstance(e, OperationConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    if isinstance(e, ReturnOperationError): # More generic
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("", response_model=Union[ReturnRequestCreateResponse, HTTPErrorDetail], status_code=status.HTTP_201_CREATED)
async def create_new_return_request(
    payload: ReturnRequestCreateRequest,
    current_user: User = Depends(get_current_user_dep),
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Submit a new return request (by buyer)."""
    try:
        result = service.create_return_request(
            order_id=payload.order_id,
            buyer_id=current_user.id,
            request_reason_detail=payload.request_reason_detail,
            return_reason_code=payload.return_reason_code
        )
        return result
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.put("/{request_id}/handle", response_model=Union[ReturnRequestHandleResponse, HTTPErrorDetail])
async def handle_seller_return_request(
    request_id: str = Path(..., description="The ID of the return request to handle."),
    payload: ReturnRequestHandleRequest = Body(...),
    current_user: User = Depends(get_current_user_dep), # Seller
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Handle a return request (by seller: agree or disagree)."""
    try:
        result = service.handle_return_request(
            return_request_id=request_id,
            seller_id=current_user.id, 
            is_agree=payload.is_agree,
            audit_idea=payload.audit_idea
        )
        return result
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.put("/{request_id}/intervene", response_model=Union[ReturnRequestInterveneResponse, HTTPErrorDetail])
async def buyer_requests_admin_intervention(
    request_id: str = Path(..., description="ID of the return request for intervention."),
    payload: ReturnRequestInterventionBody = Body(...),
    current_user: User = Depends(get_current_user_dep),
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Buyer requests admin intervention for a return request."""
    try:
        result = service.buyer_request_intervention(
            return_request_id=request_id,
            buyer_id=current_user.id,
            intervention_reason=payload.intervention_reason
        )
        return result
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/admin", response_model=List[ReturnRequestListItemResponse])
async def admin_get_all_return_requests(
    current_admin_user: User = Depends(get_current_active_admin_user_dep),
    service: ReturnRequestService = Depends(get_return_request_service),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """Admin gets all return requests (paginated)."""
    try:
        return service.get_all_return_requests(
            admin_id=current_admin_user.id, 
            page=page, 
            page_size=page_size
        )
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


@router.put("/{request_id}/admin/resolve", response_model=AdminReturnResolveResponse)
async def admin_resolves_intervened_request(
    request_id: str = Path(..., description="ID of the return request to resolve."),
    payload: AdminReturnResolveRequest = Body(...),
    current_admin_user: User = Depends(get_current_active_admin_user_dep),
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Admin resolves a return request that has been intervened."""
    try:
        result = service.admin_resolve_return_request(
            return_request_id=request_id,
            admin_id=current_admin_user.id,
            resolution_action=payload.resolution_action,
            admin_notes=payload.admin_notes
        )
        return result
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/{request_id}", response_model=ReturnRequestDetailResponse)
async def get_single_return_request_detail(
    request_id: str = Path(..., description="ID of the return request."),
    requesting_user: User = Depends(get_requesting_user_for_details),
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Get details of a specific return request (accessible by involved user or admin)."""
    try:
        return service.get_return_request_detail(
            return_request_id=request_id,
            requesting_user_id=requesting_user.id,
            requesting_user_roles=requesting_user.roles
        )
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/me/requests", response_model=Union[List[ReturnRequestListItemResponse], HTTPErrorDetail], dependencies=[Depends(get_current_user_dep)])
async def get_my_return_requests(
    current_user: User = Depends(get_current_user_dep), # Buyer or Seller
    service: ReturnRequestService = Depends(get_return_request_service)
):
    """Get all return requests for the current user (buyer or seller)."""
    try:
        # Assuming the service method can distinguish or handle calls for both buyer and seller based on user_id
        return service.get_user_return_requests(user_id=current_user.id)
    except ReturnRequestServiceError as e:
        handle_return_service_exception(e)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

# Example of how the service might be provided (in main.py or via a dependency system)
# def get_return_service():
#     # Instantiate DALs and service with real DB connections/other dependencies
#     # global return_service_instance # if using a global like in the example
#     # if return_service_instance is None:
#     #     db_pool = ...
#     #     return_dal = ReturnRequestDAL(db_pool)
#     #     order_dal = OrderDALPlaceholder(db_pool) # or actual OrderDAL
#     #     product_dal = ProductDALPlaceholder(db_pool) # or actual ProductDAL
#     #     return_service_instance = ReturnRequestService(return_dal, order_dal, product_dal)
#     return return_service_instance 