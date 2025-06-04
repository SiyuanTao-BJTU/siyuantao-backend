import unittest
from unittest.mock import MagicMock
import uuid

# Corrected import path
from app.dal.return_request_dal import ReturnRequestDAL

class TestReturnRequestDAL(unittest.TestCase):

    def setUp(self):
        self.mock_db_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()

        self.mock_db_pool.getconn.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

        self.dal = ReturnRequestDAL(self.mock_db_pool)

        # Common test data
        self.order_id = str(uuid.uuid4())
        self.buyer_id = str(uuid.uuid4())
        self.seller_id = str(uuid.uuid4())
        self.admin_id = str(uuid.uuid4())
        self.return_request_id = str(uuid.uuid4())
        
        # Updated and new fields for tests
        self.request_reason_detail = "Item is defective and smells weird."
        self.return_reason_code = "DEFECTIVE"
        self.seller_notes_agree = "Agreed. Please return the item."
        self.seller_notes_disagree = "Rejected. User damaged item."
        self.intervention_reason = "Seller is unresponsive after rejection."
        self.resolution_action = "REFUND_APPROVED"
        self.admin_notes = "Admin approved full refund after reviewing evidence."

    def tearDown(self):
        pass

    def test_create_return_request_success(self):
        mock_new_return_id = str(uuid.uuid4())
        expected_result = {'NewReturnRequestID': mock_new_return_id, 'Result': '退货请求已成功创建。'}
        self.mock_cursor.description = [('NewReturnRequestID',), ('Result',)] # Order matters for zip
        self.mock_cursor.fetchone.return_value = (mock_new_return_id, '退货请求已成功创建。')

        result = self.dal.create_return_request(
            self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_CreateReturnRequest ?, ?, ?, ?", # Expect 4 placeholders
            (self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code)
        )
        self.assertEqual(result, expected_result)
        self.mock_cursor.close.assert_called_once()
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_create_return_request_db_error(self):
        self.mock_cursor.execute.side_effect = Exception("DB Error")
        with self.assertRaisesRegex(Exception, "DB Error"):
            self.dal.create_return_request(
                self.order_id, self.buyer_id, self.request_reason_detail, self.return_reason_code
            )
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_handle_return_request_success_agree(self):
        expected_result = {'Result': '退货请求处理成功。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求处理成功。',)
        is_agree = True

        result = self.dal.handle_return_request(
            self.return_request_id, self.seller_id, is_agree, self.seller_notes_agree
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HandleReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.seller_id, is_agree, self.seller_notes_agree)
        )
        self.assertEqual(result, expected_result)

    def test_handle_return_request_success_disagree_with_notes(self):
        expected_result = {'Result': '退货请求处理成功。'} 
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求处理成功。',)
        is_agree = False

        result = self.dal.handle_return_request(
            self.return_request_id, self.seller_id, is_agree, self.seller_notes_disagree
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HandleReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.seller_id, is_agree, self.seller_notes_disagree)
        )
        self.assertEqual(result, expected_result)

    def test_handle_return_request_success_agree_no_notes(self):
        expected_result = {'Result': '退货请求处理成功。'} 
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求处理成功。',)
        is_agree = True

        result = self.dal.handle_return_request(
            self.return_request_id, self.seller_id, is_agree, None # Test with None notes
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HandleReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.seller_id, is_agree, None)
        )
        self.assertEqual(result, expected_result)

    def test_buyer_request_intervention_success(self):
        expected_result = {'Result': '申请管理员介入成功。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('申请管理员介入成功。',)

        result = self.dal.buyer_request_intervention(
            self.return_request_id, self.buyer_id, self.intervention_reason
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_BuyerRequestIntervention ?, ?, ?", # Expect 3 placeholders
            (self.return_request_id, self.buyer_id, self.intervention_reason)
        )
        self.assertEqual(result, expected_result)

    def test_admin_resolve_return_request_success(self):
        expected_result = {'Result': '退货请求已由管理员处理。'} # Updated SP message
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求已由管理员处理。',)

        result = self.dal.admin_resolve_return_request(
            self.return_request_id, self.admin_id, self.resolution_action, self.admin_notes
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_AdminResolveReturnRequest ?, ?, ?, ?", # Expect 4 placeholders
            (self.return_request_id, self.admin_id, self.resolution_action, self.admin_notes)
        )
        self.assertEqual(result, expected_result)
    
    def test_admin_resolve_return_request_success_no_notes(self):
        expected_result = {'Result': '退货请求已由管理员处理。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求已由管理员处理。',)

        result = self.dal.admin_resolve_return_request(
            self.return_request_id, self.admin_id, self.resolution_action, None # Test with None notes
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_AdminResolveReturnRequest ?, ?, ?, ?", 
            (self.return_request_id, self.admin_id, self.resolution_action, None)
        )
        self.assertEqual(result, expected_result)

    def test_get_return_request_by_id_success(self):
        mock_request_data = (self.return_request_id, self.order_id, 'Product Name', self.buyer_id, 'BuyerName') # Truncated for brevity
        columns = ['退货请求ID', '订单ID', '商品名称', '买家ID', '买家用户名'] # Match actual SP output columns
        self.mock_cursor.description = [(col,) for col in columns]
        self.mock_cursor.fetchone.return_value = mock_request_data
        expected_result = dict(zip(columns, mock_request_data))

        result = self.dal.get_return_request_by_id(self.return_request_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_GetReturnRequestById ?",
            (self.return_request_id,)
        )
        self.assertEqual(result, expected_result)

    def test_get_return_request_by_id_not_found(self):
        self.mock_cursor.description = [('退货请求ID',)] # Needs description for DAL to process columns
        self.mock_cursor.fetchone.return_value = None
        result = self.dal.get_return_request_by_id(self.return_request_id)
        self.assertIsNone(result)

    def test_get_return_requests_by_user_id_success(self):
        mock_requests_data = [
            (str(uuid.uuid4()), self.order_id, 'Product1', 'Buyer', 'SellerName', 'Status1'),
            (str(uuid.uuid4()), str(uuid.uuid4()), 'Product2', 'Seller', 'BuyerName', 'Status2')
        ]
        # Adjust columns based on the actual sp_GetReturnRequestsByUserId output
        columns = ['退货请求ID', '订单ID', '商品名称', '用户角色', '对方用户名', '退货状态'] 
        self.mock_cursor.description = [(col,) for col in columns]
        self.mock_cursor.fetchall.return_value = mock_requests_data
        expected_results = [dict(zip(columns, row)) for row in mock_requests_data]

        results = self.dal.get_return_requests_by_user_id(self.buyer_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_GetReturnRequestsByUserId ?",
            (self.buyer_id,)
        )
        self.assertEqual(results, expected_results)

    def test_get_return_requests_by_user_id_empty(self):
        self.mock_cursor.description = [('退货请求ID',)] # Minimal description
        self.mock_cursor.fetchall.return_value = []
        results = self.dal.get_return_requests_by_user_id(self.buyer_id)
        self.assertEqual(results, [])

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 