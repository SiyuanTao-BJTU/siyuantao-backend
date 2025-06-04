import uuid
from typing import Optional, List, Dict, Any
import logging

# Corrected DAL imports and Enum imports
from app.dal.return_request_dal import ReturnRequestDAL
# Assuming placeholder DALs might also move to app.dal or be actual implementations
# For now, let placeholders be defined if direct app.dal import fails or they are simple enough here
try:
    from app.dal.order_dal import OrderDAL # Placeholder path
    from app.dal.product_dal import ProductDAL # Placeholder path
except ImportError:
    class OrderDALPlaceholder: # pragma: no cover
        def get_order_status(self, order_id: str) -> Optional[str]: return "已发货"
        def update_order_status(self, order_id: str, new_status: str) -> bool: return True
        def get_order_details(self, order_id: str) -> Optional[Dict[str, Any]]:
            return {"OrderID": order_id, "ProductID": str(uuid.uuid4()), "BuyerID": str(uuid.uuid4()), "OrderStatus": "已完成"}
    class ProductDALPlaceholder: # pragma: no cover
        def get_product_owner(self, product_id: str) -> Optional[str]: return str(uuid.uuid4())
        def increase_stock(self, product_id: str, quantity: int) -> bool: return True
    OrderDAL = OrderDALPlaceholder
    ProductDAL = ProductDALPlaceholder

from app.models.enums import ReturnReasonCode, AdminResolutionAction # Added

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# TODO: Move to config
MAX_REASON_LENGTH = 1000 
MAX_NOTES_LENGTH = 1000

# --- Custom Exceptions ---
class ReturnRequestServiceError(Exception):
    """Base exception for ReturnRequestService errors."""
    def __init__(self, message="An error occurred in ReturnRequestService", status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class InvalidInputError(ReturnRequestServiceError):
    """Exception for invalid input data."""
    def __init__(self, message="Invalid input provided.", field_errors: Optional[Dict[str, str]] = None):
        super().__init__(message, status_code=400)
        self.field_errors = field_errors or {}

class NotFoundError(ReturnRequestServiceError):
    """Exception for when a resource (like order or return request) is not found."""
    def __init__(self, message="Resource not found."):
        super().__init__(message, status_code=404)

class PermissionDeniedError(ReturnRequestServiceError):
    """Exception for when a user is not authorized to perform an action."""
    def __init__(self, message="Permission denied."):
        super().__init__(message, status_code=403)

class OperationConflictError(ReturnRequestServiceError):
    """Exception for when an operation cannot be performed due to current state."""
    def __init__(self, message="Operation conflicts with the current state."):
        super().__init__(message, status_code=409) # HTTP 409 Conflict

class ReturnOperationError(ReturnRequestServiceError):
    """General exception for errors during return operations after validation."""
    def __init__(self, message="Return operation failed."):
        super().__init__(message, status_code=500)

# --- Helper Function ---
def is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

# --- Service Class ---
class ReturnRequestService:
    def __init__(self,
                 return_request_dal: ReturnRequestDAL,
                 order_dal: Any, 
                 product_dal: Any 
                ):
        self.return_request_dal = return_request_dal
        self.order_dal = order_dal
        self.product_dal = product_dal

    def create_return_request(self, order_id: str, buyer_id: str, 
                              request_reason_detail: str, return_reason_code: ReturnReasonCode
                             ) -> Dict[str, Any]:
        logger.info(f"Attempting to create return request for order {order_id} by buyer {buyer_id}.")
        field_errors = {}
        if not is_valid_uuid(order_id): field_errors["order_id"] = "Invalid order ID format."
        if not is_valid_uuid(buyer_id): field_errors["buyer_id"] = "Invalid buyer ID format."
        if not request_reason_detail or not request_reason_detail.strip(): 
            field_errors["request_reason_detail"] = "Return reason detail cannot be empty."
        elif len(request_reason_detail) > MAX_REASON_LENGTH: 
            field_errors["request_reason_detail"] = f"Return reason detail is too long (max {MAX_REASON_LENGTH} chars)."
        # return_reason_code is an enum, FastAPI/Pydantic handles its validation if passed from API

        if field_errors: 
            logger.warning(f"Validation failed for creating return request: {field_errors}")
            raise InvalidInputError("Validation failed for creating return request.", field_errors=field_errors)

        try:
            result = self.return_request_dal.create_return_request(
                order_id, buyer_id, request_reason_detail, return_reason_code.value
            )
            if not result or not result.get("NewReturnRequestID"):
                error_message = result.get("Result", "Failed to create return request due to an unknown issue.") if result else "..."
                logger.error(f"DAL failed to create return request for order {order_id}: {error_message}")
                # (Error parsing logic from original code remains here)
                if "订单不存在" in error_message: raise NotFoundError("Order not found or does not belong to the buyer.")
                if "不允许发起退货" in error_message: raise OperationConflictError("Order status does not allow return request.")
                if "已存在处理中的退货请求" in error_message: raise OperationConflictError("An active return request already exists.")
                raise ReturnOperationError(error_message)
            logger.info(f"Return request {result.get('NewReturnRequestID')} created successfully for order {order_id}.")
            return result
        except Exception as e:
            logger.error(f"Exception in create_return_request for order {order_id}: {str(e)}", exc_info=True)
            if isinstance(e, ReturnRequestServiceError): raise e
            err_str = str(e).lower()
            if "订单不存在" in err_str or "不属于该买家" in err_str: raise NotFoundError("Order not found or does not belong to the buyer.")
            if "不允许发起退货" in err_str: raise OperationConflictError("Order status does not allow return request.")
            if "已存在处理中的退货请求" in err_str: raise OperationConflictError("An active return request already exists for this order.")
            raise ReturnOperationError(f"Database or DAL error during return request creation: {str(e)}")

    def handle_return_request(self, return_request_id: str, seller_id: str, is_agree: bool, audit_idea: Optional[str]) -> Dict[str, Any]:
        logger.info(f"Seller {seller_id} handling return request {return_request_id}. Agree: {is_agree}.")
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(seller_id): field_errors["seller_id"] = "Invalid seller ID format."
        # audit_idea is optional in SP, but if provided, can have validation
        if audit_idea and len(audit_idea) > MAX_NOTES_LENGTH: 
            field_errors["audit_idea"] = f"Audit idea too long (max {MAX_NOTES_LENGTH} chars)."
        # Removed: audit_idea cannot be empty if it was mandatory.
        # If audit_idea is truly optional, empty string might be fine or None. SP takes NVARCHAR(MAX).

        if field_errors: 
            logger.warning(f"Validation failed for handling return request {return_request_id}: {field_errors}")
            raise InvalidInputError("Validation failed for handling return request.", field_errors=field_errors)

        try:
            result = self.return_request_dal.handle_return_request(return_request_id, seller_id, is_agree, audit_idea)
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result", "Failed to handle return request.") if result else "..."
                logger.error(f"DAL failed to handle return request {return_request_id}: {error_message}")
                # (Error parsing logic from original code remains here)
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "无权处理" in error_message: raise PermissionDeniedError("Seller not authorized.")
                if "当前状态不是\'等待卖家处理\'" in error_message: raise OperationConflictError("Request not awaiting seller action.")
                raise ReturnOperationError(error_message)
            logger.info(f"Return request {return_request_id} handled by seller {seller_id}. Result: {result.get('Result')}")
            return result
        except Exception as e:
            logger.error(f"Exception in handle_return_request for {return_request_id}: {str(e)}", exc_info=True)
            if isinstance(e, ReturnRequestServiceError): raise e
            # (Error parsing logic from original code remains here)
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "无权处理" in err_str: raise PermissionDeniedError("Seller is not authorized for this request.")
            if "当前状态不是\"等待卖家处理\"" in err_str : raise OperationConflictError("Request is not in '等待卖家处理' state.")
            raise ReturnOperationError(f"Database or DAL error during handling return request: {str(e)}")

    def buyer_request_intervention(self, return_request_id: str, buyer_id: str, intervention_reason: str) -> Dict[str, Any]:
        logger.info(f"Buyer {buyer_id} requesting intervention for return request {return_request_id}.")
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(buyer_id): field_errors["buyer_id"] = "Invalid buyer ID format."
        if not intervention_reason or not intervention_reason.strip():
            field_errors["intervention_reason"] = "Intervention reason cannot be empty."
        elif len(intervention_reason) > MAX_REASON_LENGTH:
            field_errors["intervention_reason"] = f"Intervention reason is too long (max {MAX_REASON_LENGTH} chars)."
        
        if field_errors: 
            logger.warning(f"Validation failed for buyer requesting intervention on {return_request_id}: {field_errors}")
            raise InvalidInputError("Validation failed for buyer requesting intervention.", field_errors=field_errors)

        try:
            result = self.return_request_dal.buyer_request_intervention(return_request_id, buyer_id, intervention_reason)
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result", "Failed to request intervention.") if result else "..."
                logger.error(f"DAL failed for buyer intervention on {return_request_id}: {error_message}")
                # (Error parsing logic from original code remains here)
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "无权操作" in error_message: raise PermissionDeniedError("Buyer not authorized.")
                if "不允许申请管理员介入" in error_message: raise OperationConflictError("Request status disallows intervention.")
                raise ReturnOperationError(error_message)
            logger.info(f"Intervention requested by buyer {buyer_id} for {return_request_id} successfully.")
            return result
        except Exception as e:
            logger.error(f"Exception in buyer_request_intervention for {return_request_id}: {str(e)}", exc_info=True)
            if isinstance(e, ReturnRequestServiceError): raise e
            # (Error parsing logic from original code remains here)
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "无权操作" in err_str: raise PermissionDeniedError("Buyer is not authorized for this request.")
            if "不允许申请管理员介入" in err_str: raise OperationConflictError("Request status does not allow admin intervention.")
            raise ReturnOperationError(f"Database or DAL error during buyer intervention request: {str(e)}")

    def admin_resolve_return_request(self, return_request_id: str, admin_id: str, 
                                     resolution_action: AdminResolutionAction, admin_notes: Optional[str]
                                    ) -> Dict[str, Any]:
        logger.info(f"Admin {admin_id} resolving return request {return_request_id} with action {resolution_action.value}.")
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(admin_id): field_errors["admin_id"] = "Invalid admin ID format."
        # resolution_action is an enum, Pydantic/FastAPI handles its validation.
        # admin_notes is optional in SP, can be validated if provided
        if admin_notes and len(admin_notes) > MAX_NOTES_LENGTH: 
            field_errors["admin_notes"] = f"Admin notes too long (max {MAX_NOTES_LENGTH} chars)."

        if field_errors: 
            logger.warning(f"Validation failed for admin resolving request {return_request_id}: {field_errors}")
            raise InvalidInputError("Validation failed for admin resolving request.", field_errors=field_errors)

        try:
            result = self.return_request_dal.admin_resolve_return_request(
                return_request_id, admin_id, resolution_action.value, admin_notes
            )
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result", "Failed to resolve return request.") if result else "..."
                logger.error(f"DAL failed for admin resolving {return_request_id}: {error_message}")
                # (Error parsing logic from original code remains here)
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "当前状态不是\'等待管理员介入\'" in error_message: raise OperationConflictError("Request not awaiting admin action.")
                if "无效的管理员操作代码" in error_message: # SP was updated to use @resolutionAction with specific codes
                    raise InvalidInputError(f"Invalid resolution action: {resolution_action.value}") 
                raise ReturnOperationError(error_message)
            logger.info(f"Return request {return_request_id} resolved by admin {admin_id}. Result: {result.get('Result')}")
            return result
        except Exception as e:
            logger.error(f"Exception in admin_resolve_return_request for {return_request_id}: {str(e)}", exc_info=True)
            if isinstance(e, ReturnRequestServiceError): raise e
            # (Error parsing logic from original code remains here)
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "当前状态不是\"等待管理员介入\"" in err_str: raise OperationConflictError("Request not awaiting admin intervention.")
            if "无效的管理员操作代码" in err_str or "无效的管理员处理状态" in err_str : # SP was updated
                raise InvalidInputError("Invalid resolution action value for admin resolution.", field_errors={"resolution_action": "Invalid action value."}) 
            raise ReturnOperationError(f"Database or DAL error during admin resolution: {str(e)}")

    def get_return_request_detail(self, return_request_id: str, requesting_user_id: Optional[str] = None, requesting_user_roles: Optional[List[str]] = None) -> Dict[str, Any]:
        if not is_valid_uuid(return_request_id): 
            raise InvalidInputError("Invalid return request ID format.", field_errors={"return_request_id": "Invalid ID format."})
        
        # Derive user_is_admin from roles
        user_is_admin = bool(requesting_user_roles and "admin" in requesting_user_roles)
        logger.info(f"Getting details for return request {return_request_id}. Requesting user: {requesting_user_id}, IsAdmin: {user_is_admin}, Roles: {requesting_user_roles}")

        try:
            request_details = self.return_request_dal.get_return_request_by_id(return_request_id)
            if not request_details:
                # SP sp_GetReturnRequestById raises "未找到指定的退货请求。" if not found.
                raise NotFoundError("Return request not found.")

            # Permission check: Admin can see any, user can see their own (as buyer or seller)
            if not user_is_admin:
                # Ensure requesting_user_id is provided if not admin, for permission check
                if not requesting_user_id: # Should ideally not happen if logic is correct in router
                    logger.error(f"Non-admin access attempt for return request {return_request_id} without user ID.")
                    raise PermissionDeniedError("User ID required for non-admin access.")
                
                if requesting_user_id != request_details.get("BuyerID") and requesting_user_id != request_details.get("SellerID"):
                    logger.warning(f"User {requesting_user_id} (not admin) attempted to access return request {return_request_id} not belonging to them.")
                    raise PermissionDeniedError("You are not authorized to view this return request.")
            
            logger.info(f"Successfully retrieved details for return request {return_request_id}.")
            return request_details
        except NotFoundError: # Re-raise specific errors for clarity
             logger.warning(f"Return request {return_request_id} not found during detail retrieval.")
             raise
        except PermissionDeniedError: # Re-raise specific errors for clarity
            logger.warning(f"Permission denied for user {requesting_user_id} on return request {return_request_id}.")
            raise
        except Exception as e:
            logger.error(f"Exception in get_return_request_detail for {return_request_id}: {str(e)}", exc_info=True)
            if isinstance(e, ReturnRequestServiceError): # Propagate known service errors
                raise e
            # Handle unexpected errors
            raise ReturnOperationError(f"Database or DAL error retrieving return request details: {str(e)}")

    def get_user_return_requests(self, user_id: str) -> List[Dict[str, Any]]:
        if not is_valid_uuid(user_id): 
            raise InvalidInputError("Invalid user ID format.", field_errors={"user_id": "Invalid user ID format."})

        try:
            # SP sp_GetReturnRequestsByUserId raises "用户不存在。" if user ID is not found in User table.
            requests = self.return_request_dal.get_return_requests_by_user_id(user_id)
            if requests is None: # Should not happen if DAL raises on DB error from SP
                raise ReturnOperationError("Failed to retrieve user return requests, DAL returned None.")
            return requests # Returns empty list if user exists but has no requests.
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            if "用户不存在" in str(e): raise NotFoundError("User not found when fetching their return requests.")
            raise ReturnOperationError(f"Database or DAL error fetching user's return requests: {str(e)}") 