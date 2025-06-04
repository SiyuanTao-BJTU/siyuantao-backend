import unittest
from unittest.mock import MagicMock
import uuid

# Adjust the import path based on your project structure
from backend.src.modules.return_request.dal.return_request_dal import ReturnRequestDAL

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
        self.return_reason = "Item defective"
        self.audit_idea = "Approved by seller"

    def tearDown(self):
        pass

    def test_create_return_request_success(self):
        # Note: The SP's SCOPE_IDENTITY() for NewReturnRequestID with UNIQUEIDENTIFIER
        # might return NULL. The test reflects what the DAL would get if the SP returned a value.
        # A more robust SP would generate UUID, insert, then SELECT it.
        mock_new_return_id = str(uuid.uuid4()) # Assume SP provides this if it worked ideally
        expected_result = {'Result': '退货请求已成功创建。', 'NewReturnRequestID': mock_new_return_id}
        self.mock_cursor.description = [('Result',), ('NewReturnRequestID',)]
        self.mock_cursor.fetchone.return_value = ('退货请求已成功创建。', mock_new_return_id)

        result = self.dal.create_return_request(self.order_id, self.buyer_id, self.return_reason)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_CreateReturnRequest ?, ?, ?",
            (self.order_id, self.buyer_id, self.return_reason)
        )
        self.assertEqual(result, expected_result)
        self.mock_cursor.close.assert_called_once()
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_create_return_request_db_error(self):
        self.mock_cursor.execute.side_effect = Exception("DB Error")
        with self.assertRaisesRegex(Exception, "DB Error"):
            self.dal.create_return_request(self.order_id, self.buyer_id, self.return_reason)
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_handle_return_request_success_agree(self):
        expected_result = {'Result': '退货请求处理成功。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求处理成功。',)
        is_agree = True

        result = self.dal.handle_return_request(self.return_request_id, self.seller_id, is_agree, self.audit_idea)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HandleReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.seller_id, is_agree, self.audit_idea) # pyodbc handles bool to 1/0
        )
        self.assertEqual(result, expected_result)

    def test_handle_return_request_success_disagree(self):
        expected_result = {'Result': '退货请求处理成功。'} # SP result message might be generic
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('退货请求处理成功。',)
        is_agree = False

        result = self.dal.handle_return_request(self.return_request_id, self.seller_id, is_agree, "Rejected by seller")

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HandleReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.seller_id, is_agree, "Rejected by seller")
        )
        self.assertEqual(result, expected_result)

    def test_buyer_request_intervention_success(self):
        expected_result = {'Result': '申请管理员介入成功。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('申请管理员介入成功。',)

        result = self.dal.buyer_request_intervention(self.return_request_id, self.buyer_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_BuyerRequestIntervention ?, ?",
            (self.return_request_id, self.buyer_id)
        )
        self.assertEqual(result, expected_result)

    def test_admin_resolve_return_request_success(self):
        new_status = "管理员同意退款"
        admin_audit_idea = "Admin approved refund."
        expected_result = {'Result': '管理员处理退货请求成功。'}
        self.mock_cursor.description = [('Result',)]
        self.mock_cursor.fetchone.return_value = ('管理员处理退货请求成功。',)

        result = self.dal.admin_resolve_return_request(self.return_request_id, self.admin_id, new_status, admin_audit_idea)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_AdminResolveReturnRequest ?, ?, ?, ?",
            (self.return_request_id, self.admin_id, new_status, admin_audit_idea)
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