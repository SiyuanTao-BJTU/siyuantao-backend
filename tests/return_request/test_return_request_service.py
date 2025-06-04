import unittest
from unittest.mock import MagicMock, patch
import uuid

# Adjust import paths as necessary
from backend.src.modules.return_request.services.return_request_service import (
    ReturnRequestService,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    OperationConflictError,
    ReturnOperationError
)
from backend.src.modules.return_request.dal.return_request_dal import ReturnRequestDAL
# For placeholder DALs, we can mock their interface if strict type checking is desired
# from backend.src.modules.return_request.services.return_request_service import OrderDALPlaceholder, ProductDALPlaceholder

class TestReturnRequestService(unittest.TestCase):

    def setUp(self):
        self.mock_return_request_dal = MagicMock(spec=ReturnRequestDAL)
        self.mock_order_dal = MagicMock() # Using MagicMock for placeholders
        self.mock_product_dal = MagicMock()

        self.service = ReturnRequestService(
            return_request_dal=self.mock_return_request_dal,
            order_dal=self.mock_order_dal,
            product_dal=self.mock_product_dal
        )

        # Common test data
        self.order_id = str(uuid.uuid4())
        self.buyer_id = str(uuid.uuid4())
        self.seller_id = str(uuid.uuid4())
        self.admin_id = str(uuid.uuid4())
        self.return_request_id = str(uuid.uuid4())
        self.product_id = str(uuid.uuid4())
        self.return_reason = "Item was defective upon arrival."
        self.audit_idea = "Seller approves the return."

    # --- create_return_request --- 
    def test_create_return_request_success(self):
        mock_new_id = str(uuid.uuid4())
        self.mock_return_request_dal.create_return_request.return_value = {
            'Result': '退货请求已成功创建。', 'NewReturnRequestID': mock_new_id
        }
        result = self.service.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.mock_return_request_dal.create_return_request.assert_called_once_with(self.order_id, self.buyer_id, self.return_reason)
        self.assertEqual(result['NewReturnRequestID'], mock_new_id)

    def test_create_return_request_invalid_order_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.create_return_request("invalid-oid", self.buyer_id, self.return_reason)
        self.assertIn("order_id", cm.exception.field_errors)
        self.mock_return_request_dal.create_return_request.assert_not_called()

    def test_create_return_request_empty_reason(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, "   ")
        self.assertIn("return_reason", cm.exception.field_errors)

    def test_create_return_request_dal_fails_order_not_found(self):
        # Simulate DAL returning a specific SP error message that the service should parse
        self.mock_return_request_dal.create_return_request.return_value = {'Result': '订单不存在或不属于该买家。'} # No NewReturnRequestID
        with self.assertRaises(NotFoundError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.assertIn("Order not found", cm.exception.message) 

    def test_create_return_request_dal_fails_status_disallows(self):
        self.mock_return_request_dal.create_return_request.return_value = {'Result': '当前订单状态不允许发起退货。'}
        with self.assertRaises(OperationConflictError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.assertIn("Order status does not allow", cm.exception.message)

    def test_create_return_request_dal_fails_already_exists(self):
        self.mock_return_request_dal.create_return_request.return_value = {'Result': '此订单已存在处理中的退货请求。'}
        with self.assertRaises(OperationConflictError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.assertIn("active return request already exists", cm.exception.message)

    def test_create_return_request_dal_generic_exception(self):
        self.mock_return_request_dal.create_return_request.side_effect = Exception("Generic DB Error")
        with self.assertRaises(ReturnOperationError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.assertIn("Database or DAL error", cm.exception.message)

    # --- handle_return_request ---
    def test_handle_return_request_success_agree(self):
        self.mock_return_request_dal.handle_return_request.return_value = {'Result': '退货请求处理成功。'}
        # Mock chained calls if is_agree leads to them (conceptual for now)
        # self.mock_return_request_dal.get_return_request_by_id.return_value = {'OrderID': self.order_id}
        # self.mock_order_dal.get_order_details.return_value = {'ProductID': self.product_id}

        result = self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.audit_idea)
        self.mock_return_request_dal.handle_return_request.assert_called_once_with(self.return_request_id, self.seller_id, True, self.audit_idea)
        self.assertEqual(result['Result'], '退货请求处理成功。')
        # self.mock_product_dal.increase_stock.assert_called_once_with(self.product_id, 1) # If logic was active

    def test_handle_return_request_invalid_id(self):
        with self.assertRaises(InvalidInputError):
            self.service.handle_return_request("invalid-rr-id", self.seller_id, True, self.audit_idea)

    def test_handle_return_request_dal_not_found(self):
        self.mock_return_request_dal.handle_return_request.return_value = {'Result': '退货请求不存在。'}
        with self.assertRaises(NotFoundError):
            self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.audit_idea)

    def test_handle_return_request_dal_permission_denied(self):
        self.mock_return_request_dal.handle_return_request.return_value = {'Result': '您无权处理此退货请求'}
        with self.assertRaises(PermissionDeniedError):
            self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.audit_idea)

    def test_handle_return_request_dal_status_conflict(self):
        self.mock_return_request_dal.handle_return_request.return_value = {'Result': '此退货请求当前状态不是\'等待卖家处理\''}
        with self.assertRaises(OperationConflictError):
            self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.audit_idea)

    # --- buyer_request_intervention ---
    def test_buyer_request_intervention_success(self):
        self.mock_return_request_dal.buyer_request_intervention.return_value = {'Result': '申请管理员介入成功。'}
        result = self.service.buyer_request_intervention(self.return_request_id, self.buyer_id)
        self.mock_return_request_dal.buyer_request_intervention.assert_called_once_with(self.return_request_id, self.buyer_id)
        self.assertEqual(result['Result'], '申请管理员介入成功。')

    def test_buyer_request_intervention_dal_permission_denied(self):
        self.mock_return_request_dal.buyer_request_intervention.return_value = {'Result': '您无权操作此退货请求'}
        with self.assertRaises(PermissionDeniedError):
            self.service.buyer_request_intervention(self.return_request_id, self.buyer_id)

    # --- admin_resolve_return_request ---
    def test_admin_resolve_return_request_success(self):
        new_status = "管理员同意退款"
        self.mock_return_request_dal.admin_resolve_return_request.return_value = {'Result': '管理员处理退货请求成功。'}
        result = self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, new_status, self.audit_idea)
        self.mock_return_request_dal.admin_resolve_return_request.assert_called_once_with(self.return_request_id, self.admin_id, new_status, self.audit_idea)
        self.assertEqual(result['Result'], '管理员处理退货请求成功。')

    def test_admin_resolve_return_request_invalid_status(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, "INVALID_STATUS", self.audit_idea)
        self.assertIn("new_status", cm.exception.field_errors)
    
    def test_admin_resolve_return_request_dal_status_conflict(self):
        self.mock_return_request_dal.admin_resolve_return_request.return_value = {'Result': '此退货请求当前状态不是\'等待管理员介入\''}
        with self.assertRaises(OperationConflictError):
            self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, "管理员同意退款", self.audit_idea)

    # --- get_return_request_detail ---
    def test_get_return_request_detail_success_buyer(self):
        mock_details = {'退货请求ID': self.return_request_id, '买家ID': self.buyer_id, '卖家ID': self.seller_id, 'Status': '一些状态'}
        self.mock_return_request_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.buyer_id)
        self.mock_return_request_dal.get_return_request_by_id.assert_called_once_with(self.return_request_id)
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_success_seller(self):
        mock_details = {'退货请求ID': self.return_request_id, '买家ID': self.buyer_id, '卖家ID': self.seller_id}
        self.mock_return_request_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.seller_id)
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_success_admin(self):
        mock_details = {'退货请求ID': self.return_request_id, '买家ID': self.buyer_id, '卖家ID': self.seller_id}
        self.mock_return_request_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, user_is_admin=True)
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_not_found(self):
        self.mock_return_request_dal.get_return_request_by_id.return_value = None
        with self.assertRaises(NotFoundError):
            self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.buyer_id)

    def test_get_return_request_detail_permission_denied_unrelated_user(self):
        unrelated_user_id = str(uuid.uuid4())
        mock_details = {'退货请求ID': self.return_request_id, '买家ID': self.buyer_id, '卖家ID': self.seller_id}
        self.mock_return_request_dal.get_return_request_by_id.return_value = mock_details
        with self.assertRaises(PermissionDeniedError):
            self.service.get_return_request_detail(self.return_request_id, requesting_user_id=unrelated_user_id)
    
    def test_get_return_request_detail_dal_raises_not_found_msg(self):
        self.mock_return_request_dal.get_return_request_by_id.side_effect = Exception("未找到指定的退货请求")
        with self.assertRaises(NotFoundError):
            self.service.get_return_request_detail(self.return_request_id)

    # --- get_user_return_requests ---
    def test_get_user_return_requests_success(self):
        mock_list = [{'id': 'req1'}, {'id': 'req2'}]
        self.mock_return_request_dal.get_return_requests_by_user_id.return_value = mock_list
        result = self.service.get_user_return_requests(self.buyer_id)
        self.mock_return_request_dal.get_return_requests_by_user_id.assert_called_once_with(self.buyer_id)
        self.assertEqual(result, mock_list)

    def test_get_user_return_requests_invalid_user_id(self):
        with self.assertRaises(InvalidInputError):
            self.service.get_user_return_requests("invalid-uid")

    def test_get_user_return_requests_dal_user_not_found_msg(self):
        # Simulate DAL raising a generic Exception that the service should convert
        self.mock_return_request_dal.get_return_requests_by_user_id.side_effect = Exception("用户不存在从DAL层")
        
        with self.assertRaises(NotFoundError) as cm:
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        
        # Check if the service-level NotFoundError contains an appropriate message
        self.assertIn("not found", str(cm.exception).lower()) # Flexible check for "not found"

    def test_get_user_return_requests_dal_returns_none(self):
        self.mock_return_request_dal.get_return_requests_by_user_id.return_value = None
        with self.assertRaises(ReturnOperationError) as cm:
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        self.assertIn("DAL returned None", cm.exception.message)

    def test_get_user_return_requests_unexpected_dal_error(self):
        # This test is for generic DAL errors being wrapped into ReturnOperationError
        self.mock_return_request_dal.get_return_requests_by_user_id.side_effect = Exception("Generic Unhandled DAL Error")
        with self.assertRaises(ReturnOperationError) as cm: 
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        self.assertIn("dal error", str(cm.exception).lower()) # Check for a generic DAL error indication

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 