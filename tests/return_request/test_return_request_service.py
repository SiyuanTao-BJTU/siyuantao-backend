import unittest
from unittest.mock import MagicMock, patch
import uuid

# Corrected import paths
from app.services.return_request_service import (
    ReturnRequestService,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    OperationConflictError,
    ReturnOperationError,
    MAX_REASON_LENGTH, # For testing boundaries
    MAX_NOTES_LENGTH
)
from app.dal.return_request_dal import ReturnRequestDAL
from app.models.enums import ReturnReasonCode, AdminResolutionAction

# Using MagicMock for placeholder DALs in tests is sufficient
# No need to import OrderDALPlaceholder, ProductDALPlaceholder from service if not exported

class TestReturnRequestService(unittest.TestCase):

    def setUp(self):
        self.mock_rr_dal = MagicMock(spec=ReturnRequestDAL) # Renamed for clarity
        self.mock_order_dal = MagicMock() 
        self.mock_product_dal = MagicMock()

        self.service = ReturnRequestService(
            return_request_dal=self.mock_rr_dal,
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
        
        # Updated and new fields for tests
        self.request_reason_detail = "Item was defective upon arrival."
        self.return_reason_code_enum = ReturnReasonCode.DEFECTIVE
        self.seller_notes = "Seller approves the return."
        self.intervention_reason = "Seller rejected unfairly and is not responding."
        self.resolution_action_enum = AdminResolutionAction.REFUND_APPROVED
        self.admin_notes = "Admin reviewed and approved refund."

    # --- create_return_request --- 
    def test_create_return_request_success(self):
        mock_new_id = str(uuid.uuid4())
        self.mock_rr_dal.create_return_request.return_value = {
            'Result': '退货请求已成功创建。', 'NewReturnRequestID': mock_new_id
        }
        result = self.service.create_return_request(
            self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code_enum
        )
        self.mock_rr_dal.create_return_request.assert_called_once_with(
            self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code_enum.value
        )
        self.assertEqual(result['NewReturnRequestID'], mock_new_id)

    def test_create_return_request_invalid_order_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.create_return_request(
                "invalid-oid", self.buyer_id, self.request_reason_detail, self.return_reason_code_enum
            )
        self.assertIn("order_id", cm.exception.field_errors)
        self.mock_rr_dal.create_return_request.assert_not_called()

    def test_create_return_request_empty_reason_detail(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.create_return_request(
                self.order_id, self.buyer_id, "   ", self.return_reason_code_enum
            )
        self.assertIn("request_reason_detail", cm.exception.field_errors)
    
    def test_create_return_request_reason_detail_too_long(self):
        long_reason = "a" * (MAX_REASON_LENGTH + 1)
        with self.assertRaises(InvalidInputError) as cm:
            self.service.create_return_request(
                self.order_id, self.buyer_id, long_reason, self.return_reason_code_enum
            )
        self.assertIn("request_reason_detail", cm.exception.field_errors)

    # DAL failure propagation tests (no change needed in call, only checking exception type/message)
    def test_create_return_request_dal_fails_order_not_found(self):
        self.mock_rr_dal.create_return_request.return_value = {'Result': '订单不存在或不属于该买家。'}
        with self.assertRaises(NotFoundError) as cm:
            self.service.create_return_request(self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code_enum)
        self.assertIn("Order not found", cm.exception.message)

    # --- handle_return_request ---
    def test_handle_return_request_success_agree_with_notes(self):
        self.mock_rr_dal.handle_return_request.return_value = {'Result': '退货请求处理成功。'}
        result = self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.seller_notes)
        self.mock_rr_dal.handle_return_request.assert_called_once_with(self.return_request_id, self.seller_id, True, self.seller_notes)
        self.assertEqual(result['Result'], '退货请求处理成功。')

    def test_handle_return_request_success_agree_no_notes(self):
        self.mock_rr_dal.handle_return_request.return_value = {'Result': '退货请求处理成功。'}
        result = self.service.handle_return_request(self.return_request_id, self.seller_id, True, None)
        self.mock_rr_dal.handle_return_request.assert_called_once_with(self.return_request_id, self.seller_id, True, None)
        self.assertEqual(result['Result'], '退货请求处理成功。')

    def test_handle_return_request_audit_idea_too_long(self):
        long_notes = "a" * (MAX_NOTES_LENGTH + 1)
        with self.assertRaises(InvalidInputError) as cm:
            self.service.handle_return_request(self.return_request_id, self.seller_id, True, long_notes)
        self.assertIn("audit_idea", cm.exception.field_errors)

    # --- buyer_request_intervention ---
    def test_buyer_request_intervention_success(self):
        self.mock_rr_dal.buyer_request_intervention.return_value = {'Result': '申请管理员介入成功。'}
        result = self.service.buyer_request_intervention(self.return_request_id, self.buyer_id, self.intervention_reason)
        self.mock_rr_dal.buyer_request_intervention.assert_called_once_with(self.return_request_id, self.buyer_id, self.intervention_reason)
        self.assertEqual(result['Result'], '申请管理员介入成功。')

    def test_buyer_request_intervention_empty_reason(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.buyer_request_intervention(self.return_request_id, self.buyer_id, "  ")
        self.assertIn("intervention_reason", cm.exception.field_errors)

    def test_buyer_request_intervention_reason_too_long(self):
        long_reason = "a" * (MAX_REASON_LENGTH + 1)
        with self.assertRaises(InvalidInputError) as cm:
            self.service.buyer_request_intervention(self.return_request_id, self.buyer_id, long_reason)
        self.assertIn("intervention_reason", cm.exception.field_errors)

    # --- admin_resolve_return_request ---
    def test_admin_resolve_return_request_success_with_notes(self):
        self.mock_rr_dal.admin_resolve_return_request.return_value = {'Result': '管理员处理成功。'}
        result = self.service.admin_resolve_return_request(
            self.return_request_id, self.admin_id, self.resolution_action_enum, self.admin_notes
        )
        self.mock_rr_dal.admin_resolve_return_request.assert_called_once_with(
            self.return_request_id, self.admin_id, self.resolution_action_enum.value, self.admin_notes
        )
        self.assertEqual(result['Result'], '管理员处理成功。')

    def test_admin_resolve_return_request_success_no_notes(self):
        self.mock_rr_dal.admin_resolve_return_request.return_value = {'Result': '管理员处理成功。'}
        result = self.service.admin_resolve_return_request(
            self.return_request_id, self.admin_id, self.resolution_action_enum, None
        )
        self.mock_rr_dal.admin_resolve_return_request.assert_called_once_with(
            self.return_request_id, self.admin_id, self.resolution_action_enum.value, None
        )
        self.assertEqual(result['Result'], '管理员处理成功。')

    def test_admin_resolve_return_request_admin_notes_too_long(self):
        long_notes = "a" * (MAX_NOTES_LENGTH + 1)
        with self.assertRaises(InvalidInputError) as cm:
            self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, self.resolution_action_enum, long_notes)
        self.assertIn("admin_notes", cm.exception.field_errors)

    # Existing tests for DAL failure propagation (NotFoundError, PermissionDeniedError, etc.)
    # generally do not need changes in their assert_called_once_with parts unless the method signature changed.
    # For example, test_create_return_request_dal_fails_order_not_found already updated above.
    # Ensure all other DAL failure tests call the service method with its new signature.

    def test_handle_return_request_dal_not_found(self):
        self.mock_rr_dal.handle_return_request.return_value = {'Result': '退货请求不存在。'}
        with self.assertRaises(NotFoundError):
            self.service.handle_return_request(self.return_request_id, self.seller_id, True, self.seller_notes)

    def test_buyer_request_intervention_dal_permission_denied(self):
        self.mock_rr_dal.buyer_request_intervention.return_value = {'Result': '您无权操作此退货请求'}
        with self.assertRaises(PermissionDeniedError):
            self.service.buyer_request_intervention(self.return_request_id, self.buyer_id, self.intervention_reason)

    def test_admin_resolve_return_request_dal_status_conflict(self):
        self.mock_rr_dal.admin_resolve_return_request.return_value = {'Result': '此退货请求当前状态不是\'等待管理员介入\''}
        with self.assertRaises(OperationConflictError):
            self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, self.resolution_action_enum, self.admin_notes)

    def test_admin_resolve_return_request_dal_invalid_action_code_msg(self):
        # Test if service correctly translates a specific DAL error message for invalid action code
        self.mock_rr_dal.admin_resolve_return_request.return_value = {'Result': '无效的管理员操作代码。'}
        with self.assertRaises(InvalidInputError) as cm:
            self.service.admin_resolve_return_request(self.return_request_id, self.admin_id, self.resolution_action_enum, self.admin_notes)
        self.assertIn(f"Invalid resolution action: {self.resolution_action_enum.value}", str(cm.exception))

    # --- get_return_request_detail ---
    def test_get_return_request_detail_success_buyer(self):
        mock_details = {'ReturnRequestID': self.return_request_id, 'BuyerID': self.buyer_id, 'SellerID': self.seller_id, 'Status': '一些状态'}
        self.mock_rr_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.buyer_id, requesting_user_roles=['user'])
        self.mock_rr_dal.get_return_request_by_id.assert_called_once_with(self.return_request_id)
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_success_seller(self):
        mock_details = {'ReturnRequestID': self.return_request_id, 'BuyerID': self.buyer_id, 'SellerID': self.seller_id}
        self.mock_rr_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.seller_id, requesting_user_roles=['user'])
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_success_admin(self):
        mock_details = {'ReturnRequestID': self.return_request_id, 'BuyerID': self.buyer_id, 'SellerID': self.seller_id}
        self.mock_rr_dal.get_return_request_by_id.return_value = mock_details
        result = self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.admin_id, requesting_user_roles=['admin', 'user'])
        self.assertEqual(result, mock_details)

    def test_get_return_request_detail_not_found(self):
        self.mock_rr_dal.get_return_request_by_id.return_value = None
        with self.assertRaises(NotFoundError):
            # Pass roles to satisfy new signature, specific roles don't matter for this path
            self.service.get_return_request_detail(self.return_request_id, requesting_user_id=self.buyer_id, requesting_user_roles=['user'])

    def test_get_return_request_detail_permission_denied_unrelated_user(self):
        unrelated_user_id = str(uuid.uuid4())
        mock_details = {'ReturnRequestID': self.return_request_id, 'BuyerID': self.buyer_id, 'SellerID': self.seller_id}
        self.mock_rr_dal.get_return_request_by_id.return_value = mock_details
        with self.assertRaises(PermissionDeniedError):
            self.service.get_return_request_detail(self.return_request_id, requesting_user_id=unrelated_user_id, requesting_user_roles=['user'])
    
    def test_get_return_request_detail_dal_raises_not_found_msg(self):
        self.mock_rr_dal.get_return_request_by_id.side_effect = Exception("未找到指定的退货请求")
        # Service layer currently wraps general DAL exceptions into ReturnOperationError
        with self.assertRaises(ReturnOperationError) as cm:
            self.service.get_return_request_detail(self.return_request_id, requesting_user_roles=['user'])
        self.assertIn("未找到指定的退货请求", str(cm.exception)) # Check if original message is preserved

    # --- get_user_return_requests ---
    def test_get_user_return_requests_success(self):
        mock_list = [{'id': 'req1'}, {'id': 'req2'}]
        self.mock_rr_dal.get_return_requests_by_user_id.return_value = mock_list
        result = self.service.get_user_return_requests(self.buyer_id)
        self.mock_rr_dal.get_return_requests_by_user_id.assert_called_once_with(self.buyer_id)
        self.assertEqual(result, mock_list)

    def test_get_user_return_requests_invalid_user_id(self):
        with self.assertRaises(InvalidInputError):
            self.service.get_user_return_requests("invalid-uid")

    def test_get_user_return_requests_dal_user_not_found_msg(self):
        # Simulate DAL raising a generic Exception that the service should convert
        self.mock_rr_dal.get_return_requests_by_user_id.side_effect = Exception("用户不存在从DAL层")
        
        with self.assertRaises(NotFoundError) as cm:
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        
        # Check if the service-level NotFoundError contains an appropriate message
        self.assertIn("not found", str(cm.exception).lower()) # Flexible check for "not found"

    def test_get_user_return_requests_dal_returns_none(self):
        self.mock_rr_dal.get_return_requests_by_user_id.return_value = None
        with self.assertRaises(ReturnOperationError) as cm:
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        self.assertIn("DAL returned None", cm.exception.message)

    def test_get_user_return_requests_unexpected_dal_error(self):
        # This test is for generic DAL errors being wrapped into ReturnOperationError
        self.mock_rr_dal.get_return_requests_by_user_id.side_effect = Exception("Generic Unhandled DAL Error")
        with self.assertRaises(ReturnOperationError) as cm: 
            self.service.get_user_return_requests(self.buyer_id) # Removed page/page_size
        self.assertIn("dal error", str(cm.exception).lower()) # Check for a generic DAL error indication

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 