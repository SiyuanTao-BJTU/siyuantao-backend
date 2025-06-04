import uuid
from typing import Optional, List, Dict, Any

# DAL imports - adjust paths as necessary
try:
    from ..dal.return_request_dal import ReturnRequestDAL
    # Using placeholders for OrderDAL and ProductDAL as their full code is not provided.
    # In a real application, these would be proper DAL classes.
    class OrderDALPlaceholder: # pragma: no cover
        def get_order_status(self, order_id: str) -> Optional[str]: 
            print(f"OrderDALPlaceholder: Mock check for order {order_id} status.")
            # Simulate some statuses for testing purposes if needed
            if order_id == "00000000-0000-0000-0000-000000000001": return "已完成"
            return "已发货" # Default mock status
        def update_order_status(self, order_id: str, new_status: str) -> bool: 
            print(f"OrderDALPlaceholder: Mock update order {order_id} to status {new_status}.")
            return True
        def get_order_details(self, order_id: str) -> Optional[Dict[str, Any]]:
            print(f"OrderDALPlaceholder: Mock get details for order {order_id}.")
            # Simulate order details including ProductID and BuyerID
            return {"OrderID": order_id, "ProductID": str(uuid.uuid4()), "BuyerID": str(uuid.uuid4()), "OrderStatus": "已完成"}

    class ProductDALPlaceholder: # pragma: no cover
        def get_product_owner(self, product_id: str) -> Optional[str]: 
            print(f"ProductDALPlaceholder: Mock get owner for product {product_id}.")
            return str(uuid.uuid4()) # Return a mock seller ID
        def increase_stock(self, product_id: str, quantity: int) -> bool: 
            print(f"ProductDALPlaceholder: Mock increase stock for product {product_id} by {quantity}.")
            return True
    
    OrderDAL = OrderDALPlaceholder
    ProductDAL = ProductDALPlaceholder

except ImportError:
    # This block is for environments where relative imports might fail (e.g. running script directly)
    # Fallback to absolute paths if necessary and available in sys.path
    from backend.src.modules.return_request.dal.return_request_dal import ReturnRequestDAL
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
                 order_dal: Any, # OrderDALPlaceholder or actual OrderDAL
                 product_dal: Any  # ProductDALPlaceholder or actual ProductDAL
                ):
        self.return_request_dal = return_request_dal
        self.order_dal = order_dal
        self.product_dal = product_dal

    def create_return_request(self, order_id: str, buyer_id: str, return_reason: str) -> Dict[str, Any]:
        field_errors = {}
        if not is_valid_uuid(order_id): field_errors["order_id"] = "Invalid order ID format."
        if not is_valid_uuid(buyer_id): field_errors["buyer_id"] = "Invalid buyer ID format."
        if not return_reason or not return_reason.strip(): field_errors["return_reason"] = "Return reason cannot be empty."
        elif len(return_reason) > 1000: field_errors["return_reason"] = "Return reason is too long (max 1000 chars)."
        if field_errors: raise InvalidInputError("Validation failed for creating return request.", field_errors=field_errors)

        # SP sp_CreateReturnRequest handles most underlying checks (order existence, status, ownership, no prior request)
        try:
            result = self.return_request_dal.create_return_request(order_id, buyer_id, return_reason)
            # The DAL should raise an exception if the SP indicates an error via RAISERROR.
            # If result is None or lacks expected success markers, it might indicate an issue not caught as exception.
            if not result or not result.get("NewReturnRequestID"): 
                # This assumes NewReturnRequestID is returned on success from SP. 
                # The SP currently uses SCOPE_IDENTITY which is problematic for UUIDs.
                # Assuming the SP is fixed to return the new ID properly.
                error_message = result.get("Result") if result else "Failed to create return request due to an unknown issue."
                # Check for specific error messages that might come back if SP didn't RAISERROR but returned a message
                if "订单不存在" in error_message: raise NotFoundError("Order not found or does not belong to the buyer.")
                if "不允许发起退货" in error_message: raise OperationConflictError("Order status does not allow return request.")
                if "已存在处理中的退货请求" in error_message: raise OperationConflictError("An active return request already exists.")
                raise ReturnOperationError(error_message)
            return result
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            # Attempt to parse common error messages that might come from DB/DAL if not already service exceptions
            err_str = str(e).lower()
            if "订单不存在" in err_str or "不属于该买家" in err_str: raise NotFoundError("Order not found or does not belong to the buyer.")
            if "不允许发起退货" in err_str: raise OperationConflictError("Order status does not allow return request.")
            if "已存在处理中的退货请求" in err_str: raise OperationConflictError("An active return request already exists for this order.")
            raise ReturnOperationError(f"Database or DAL error during return request creation: {str(e)}")

    def handle_return_request(self, return_request_id: str, seller_id: str, is_agree: bool, audit_idea: str) -> Dict[str, Any]:
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(seller_id): field_errors["seller_id"] = "Invalid seller ID format."
        if not audit_idea or not audit_idea.strip(): field_errors["audit_idea"] = "Audit idea cannot be empty."
        elif len(audit_idea) > 1000: field_errors["audit_idea"] = "Audit idea too long (max 1000 chars)."
        if field_errors: raise InvalidInputError("Validation failed for handling return request.", field_errors=field_errors)

        try:
            # SP sp_HandleReturnRequest checks request existence, seller ownership, and '等待卖家处理' status.
            result = self.return_request_dal.handle_return_request(return_request_id, seller_id, is_agree, audit_idea)
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result") if result else "Failed to handle return request."
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "无权处理" in error_message: raise PermissionDeniedError("Seller not authorized.")
                if "当前状态不是\'等待卖家处理\'" in error_message: raise OperationConflictError("Request not awaiting seller action.")
                raise ReturnOperationError(error_message)
            
            # If agreed and stock needs adjustment (conceptual, SP might handle or another system does)
            # if is_agree:
            #     request_details = self.return_request_dal.get_return_request_by_id(return_request_id)
            #     if request_details and request_details.get('OrderID'):
            #         order_details = self.order_dal.get_order_details(request_details['OrderID'])
            #         if order_details and order_details.get('ProductID'):
            #             self.product_dal.increase_stock(order_details['ProductID'], 1) # Assuming quantity 1
            return result
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "无权处理" in err_str: raise PermissionDeniedError("Seller is not authorized for this request.")
            if "当前状态不是\"等待卖家处理\"" in err_str : raise OperationConflictError("Request is not in '等待卖家处理' state.")
            raise ReturnOperationError(f"Database or DAL error during handling return request: {str(e)}")

    def buyer_request_intervention(self, return_request_id: str, buyer_id: str) -> Dict[str, Any]:
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(buyer_id): field_errors["buyer_id"] = "Invalid buyer ID format."
        if field_errors: raise InvalidInputError("Validation failed for buyer requesting intervention.", field_errors=field_errors)

        try:
            # SP sp_BuyerRequestIntervention checks request existence, buyer ownership, and eligible status (e.g., '卖家拒绝退货').
            result = self.return_request_dal.buyer_request_intervention(return_request_id, buyer_id)
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result") if result else "Failed to request intervention."
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "无权操作" in error_message: raise PermissionDeniedError("Buyer not authorized.")
                if "不允许申请管理员介入" in error_message: raise OperationConflictError("Request status disallows intervention.")
                raise ReturnOperationError(error_message)
            return result
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "无权操作" in err_str: raise PermissionDeniedError("Buyer is not authorized for this request.")
            if "不允许申请管理员介入" in err_str: raise OperationConflictError("Request status does not allow admin intervention.")
            raise ReturnOperationError(f"Database or DAL error during buyer intervention request: {str(e)}")

    def admin_resolve_return_request(self, return_request_id: str, admin_id: str, new_status: str, audit_idea: str) -> Dict[str, Any]:
        field_errors = {}
        if not is_valid_uuid(return_request_id): field_errors["return_request_id"] = "Invalid ID format."
        if not is_valid_uuid(admin_id): field_errors["admin_id"] = "Invalid admin ID format."
        valid_admin_statuses = ['管理员同意退款', '管理员支持卖家', '退款完成', '请求已关闭']
        if not new_status or new_status not in valid_admin_statuses:
            field_errors["new_status"] = f"Invalid status. Must be one of: {valid_admin_statuses}."
        if not audit_idea or not audit_idea.strip(): field_errors["audit_idea"] = "Audit idea cannot be empty."
        elif len(audit_idea) > 1000: field_errors["audit_idea"] = "Audit idea too long (max 1000 chars)."
        if field_errors: raise InvalidInputError("Validation failed for admin resolving request.", field_errors=field_errors)

        # Conceptual: Add admin role check here if UserDAL was available.
        # if not self.user_dal.is_admin(admin_id): raise PermissionDeniedError("User is not an admin.")

        try:
            # SP sp_AdminResolveReturnRequest checks request existence, '等待管理员介入' status, and valid new_status.
            result = self.return_request_dal.admin_resolve_return_request(return_request_id, admin_id, new_status, audit_idea)
            if not result or "成功" not in result.get("Result", ""):
                error_message = result.get("Result") if result else "Failed to resolve return request."
                if "退货请求不存在" in error_message: raise NotFoundError("Return request not found.")
                if "当前状态不是\'等待管理员介入\'" in error_message: raise OperationConflictError("Request not awaiting admin action.")
                if "无效的管理员处理状态" in error_message: raise InvalidInputError("Invalid new status for admin.")
                raise ReturnOperationError(error_message)
            
            # TODO: Post-resolution actions like triggering refunds or adjusting reputation scores.
            return result
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            err_str = str(e).lower()
            if "退货请求不存在" in err_str: raise NotFoundError("Return request not found.")
            if "当前状态不是\"等待管理员介入\"" in err_str: raise OperationConflictError("Request not awaiting admin intervention.")
            if "无效的管理员处理状态" in err_str: raise InvalidInputError("Invalid new status provided for admin resolution.", field_errors={"new_status": "Invalid status value."}) 
            raise ReturnOperationError(f"Database or DAL error during admin resolution: {str(e)}")

    def get_return_request_detail(self, return_request_id: str, requesting_user_id: Optional[str] = None, user_is_admin: bool = False) -> Dict[str, Any]:
        if not is_valid_uuid(return_request_id): 
            raise InvalidInputError("Invalid return request ID format.", field_errors={"return_request_id": "Invalid ID format."})
        
        try:
            request_details = self.return_request_dal.get_return_request_by_id(return_request_id)
            if not request_details:
                # SP sp_GetReturnRequestById raises "未找到指定的退货请求。" if not found.
                raise NotFoundError("Return request not found.")

            # Permission check: User must be buyer, seller, or an admin to view.
            if requesting_user_id:
                if not is_valid_uuid(requesting_user_id):
                    raise InvalidInputError("Invalid requesting user ID format for permission check.")
                
                # Extract IDs using SP's aliased names (or Pythonic if DAL transforms)
                buyer_id_in_req = str(request_details.get('买家ID', request_details.get('BuyerID')))
                seller_id_in_req = str(request_details.get('卖家ID', request_details.get('SellerID')))

                if not (requesting_user_id == buyer_id_in_req or 
                        requesting_user_id == seller_id_in_req or 
                        user_is_admin):
                    raise PermissionDeniedError("User not authorized to view this return request.")
            elif not user_is_admin: # If no user_id, must be admin to view arbitrarily
                # This case might be disallowed entirely if unauthenticated access is not desired.
                # For now, if no user_id is given, and not explicitly admin, deny.
                # Consider if this path should even exist without a requesting_user_id.
                 pass # Allowing internal/unrestricted access if no user context, otherwise needs a rule.

            return request_details
        except Exception as e:
            if isinstance(e, ReturnRequestServiceError): raise e
            if "未找到指定的退货请求" in str(e): raise NotFoundError("Return request not found.")
            raise ReturnOperationError(f"Database or DAL error fetching return request details: {str(e)}")

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