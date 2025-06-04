import unittest
from unittest.mock import MagicMock, patch
import uuid

# Corrected import path
from app.dal.chat_message_dal import ChatMessageDAL

class TestChatMessageDAL(unittest.TestCase):

    def setUp(self):
        self.mock_db_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()

        self.mock_db_pool.getconn.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

        self.dal = ChatMessageDAL(self.mock_db_pool)

        # Common test data
        self.sender_id = str(uuid.uuid4())
        self.receiver_id = str(uuid.uuid4())
        self.product_id = str(uuid.uuid4())
        self.message_id = str(uuid.uuid4())
        self.user_id = str(uuid.uuid4())
        self.client_message_id = str(uuid.uuid4()) # Example client message ID

    def tearDown(self):
        # Ensure mocks are reset if necessary, though unittest does this per test method.
        pass

    def test_send_message_success_newly_created(self):
        # Expected data from SP when message is newly created
        self.mock_cursor.description = [('MessageIdOutput',), ('IsNewlyCreated',)]
        self.mock_cursor.fetchone.return_value = (self.message_id, 1) # 1 for True

        content = "Hello there!"
        result_message_id, result_is_newly_created = self.dal.send_message(
            self.sender_id, self.receiver_id, self.product_id, content, self.client_message_id
        )

        self.mock_db_pool.getconn.assert_called_once()
        self.mock_conn.cursor.assert_called_once()
        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_SendMessage ?, ?, ?, ?, ?", # Expect 5 placeholders
            (self.sender_id, self.receiver_id, self.product_id, content, self.client_message_id)
        )
        self.assertEqual(result_message_id, uuid.UUID(self.message_id))
        self.assertTrue(result_is_newly_created)
        self.mock_cursor.close.assert_called_once()
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_send_message_success_idempotent_hit(self):
        # Expected data from SP when message already exists (idempotent hit)
        self.mock_cursor.description = [('MessageIdOutput',), ('IsNewlyCreated',)]
        self.mock_cursor.fetchone.return_value = (self.message_id, 0) # 0 for False

        content = "Hello there again!" # Content might be same or different
        existing_client_msg_id = str(uuid.uuid4())
        result_message_id, result_is_newly_created = self.dal.send_message(
            self.sender_id, self.receiver_id, self.product_id, content, existing_client_msg_id
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_SendMessage ?, ?, ?, ?, ?", 
            (self.sender_id, self.receiver_id, self.product_id, content, existing_client_msg_id)
        )
        self.assertEqual(result_message_id, uuid.UUID(self.message_id))
        self.assertFalse(result_is_newly_created)

    def test_send_message_success_no_client_id(self):
        # Test when client_message_id is None (SP should handle NULL)
        self.mock_cursor.description = [('MessageIdOutput',), ('IsNewlyCreated',)]
        # Assuming if client_message_id is NULL, it's always a new message (unless other constraints exist)
        # For this test, let's assume it results in a new message. 
        # The SP logic dictates: if @clientMessageId IS NULL, it proceeds to insert (so IsNewlyCreated=1)
        self.mock_cursor.fetchone.return_value = (self.message_id, 1) 

        content = "A message without client ID."
        result_message_id, result_is_newly_created = self.dal.send_message(
            self.sender_id, self.receiver_id, self.product_id, content, None # client_message_id is None
        )

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_SendMessage ?, ?, ?, ?, ?",
            (self.sender_id, self.receiver_id, self.product_id, content, None)
        )
        self.assertEqual(result_message_id, uuid.UUID(self.message_id))
        self.assertTrue(result_is_newly_created)

    def test_send_message_dal_raises_on_missing_sp_results(self):
        self.mock_cursor.description = [('SomeOtherColumn',)] # Missing expected columns
        self.mock_cursor.fetchone.return_value = ('some_value',)
        content = "Test content"
        with self.assertRaisesRegex(Exception, "Failed to send message due to unexpected database response."):
            self.dal.send_message(self.sender_id, self.receiver_id, self.product_id, content, self.client_message_id)

    def test_send_message_db_error(self):
        self.mock_cursor.execute.side_effect = Exception("DB Error")
        content = "Error message"
        with self.assertRaisesRegex(Exception, "DB Error"):
            self.dal.send_message(self.sender_id, self.receiver_id, self.product_id, content, self.client_message_id)
        self.mock_db_pool.putconn.assert_called_once_with(self.mock_conn)

    def test_get_user_conversations_success(self):
        mock_conversation_data = [
            ('conv_id1', 'prod_name1', self.user_id, 'other_user1', 'msg1', 'time1', 0),
            ('conv_id2', 'prod_name2', self.user_id, 'other_user2', 'msg2', 'time2', 1)
        ]
        columns = ['商品ID', '商品名称', '聊天对象ID', '聊天对象用户名', '最新消息内容', '最新消息时间', '未读消息数量']
        self.mock_cursor.description = [(col,) for col in columns]
        self.mock_cursor.fetchall.return_value = mock_conversation_data

        expected_results = [dict(zip(columns, row)) for row in mock_conversation_data]

        results = self.dal.get_user_conversations(self.user_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_GetUserConversations ?",
            (self.user_id,)
        )
        self.assertEqual(results, expected_results)

    def test_get_user_conversations_empty(self):
        self.mock_cursor.description = [('商品ID',)] # Minimal description
        self.mock_cursor.fetchall.return_value = []
        results = self.dal.get_user_conversations(self.user_id)
        self.assertEqual(results, [])

    def test_get_chat_messages_by_product_and_users_success(self):
        # Mock data for messages
        mock_message_list = [
            (self.message_id, self.sender_id, 'Sender', self.receiver_id, 'Receiver', self.product_id, 'Product', 'Content', 'Time', False)
        ]
        msg_cols = ['消息ID', '发送者ID', '发送者用户名', '接收者ID', '接收者用户名', '商品ID', '商品名称', '内容', '发送时间', '是否已读']
        
        # Mock data for total count
        mock_total_count_row = (5,)
        count_cols = ['TotalMessages']

        # Configure cursor for the first result set (messages)
        self.mock_cursor.description = [(col,) for col in msg_cols]
        self.mock_cursor.fetchall.return_value = mock_message_list
        
        # Configure cursor for the second result set (total count)
        # This requires careful mocking of nextset and subsequent calls
        def configure_next_result_set(*args, **kwargs):
            # First call to description is for messages, then fetchall
            # nextset() is called
            # Second call to description is for count, then fetchone
            if not hasattr(self.mock_cursor, '_call_count_description'):
                self.mock_cursor._call_count_description = 0
            
            if self.mock_cursor._call_count_description == 0: # For messages
                self.mock_cursor.description = [(col,) for col in msg_cols]
                self.mock_cursor.fetchall.return_value = mock_message_list
            elif self.mock_cursor._call_count_description == 1: # For count
                self.mock_cursor.description = [(col,) for col in count_cols]
                self.mock_cursor.fetchone.return_value = mock_total_count_row
            
            self.mock_cursor._call_count_description +=1
            return True # for nextset to indicate another result set

        # We will simulate the calls within the DAL method
        self.mock_cursor.nextset.return_value = True # Indicates a second result set is available

        # Since description and fetch* are accessed multiple times, we patch them within the test or make them more dynamic
        # For simplicity, we'll assume the DAL calls them in sequence and our setUp of mocks for description/fetchall/fetchone will be overridden by specific calls if needed
        
        # Initial setup for the first result set
        self.mock_cursor.description = [(col,) for col in msg_cols]
        self.mock_cursor.fetchall.return_value = mock_message_list

        # Setup for when nextset() is called and a new result set is processed
        # We'll rely on the DAL's internal logic to call nextset, then re-query description and fetchone
        # The mock setup for the second result set
        mock_cursor_for_count = MagicMock()
        mock_cursor_for_count.description = [(col,) for col in count_cols]
        mock_cursor_for_count.fetchone.return_value = mock_total_count_row

        # This part is tricky to mock perfectly without deeper changes or more complex side_effect.
        # The DAL's get_chat_messages_by_product_and_users reuses the same cursor object.
        # We'll set up the initial state for messages, and then for total_count after nextset.
        
        # Simpler approach: reset relevant mocks on nextset call
        original_description = self.mock_cursor.description
        original_fetchall = self.mock_cursor.fetchall
        original_fetchone = self.mock_cursor.fetchone

        def nextset_side_effect():
            # Configure for the total count result set
            self.mock_cursor.description = [(col,) for col in count_cols]
            self.mock_cursor.fetchone.return_value = mock_total_count_row
            self.mock_cursor.fetchall.return_value = [] # Should not be called for count
            return True
        
        self.mock_cursor.nextset.side_effect = nextset_side_effect

        page_number = 1
        page_size = 10
        messages, total_count = self.dal.get_chat_messages_by_product_and_users(
            self.product_id, self.sender_id, self.receiver_id, page_number, page_size
        )
        
        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_GetChatMessagesByProductAndUsers ?, ?, ?, ?, ?",
            (self.product_id, self.sender_id, self.receiver_id, page_number, page_size)
        )
        
        expected_messages = [dict(zip(msg_cols, row)) for row in mock_message_list]
        self.assertEqual(messages, expected_messages)
        self.assertEqual(total_count, mock_total_count_row[0])

        # Restore original mock methods if they were changed by side_effect
        self.mock_cursor.description = original_description
        self.mock_cursor.fetchall = original_fetchall
        self.mock_cursor.fetchone = original_fetchone
        self.mock_cursor.nextset.side_effect = None


    def test_get_chat_messages_by_product_and_users_no_second_result_set(self):
        # Mock data for messages
        mock_message_list = [
            (self.message_id, self.sender_id, 'Sender', self.receiver_id, 'Receiver', self.product_id, 'Product', 'Content', 'Time', False)
        ]
        msg_cols = ['消息ID', '发送者ID', '发送者用户名', '接收者ID', '接收者用户名', '商品ID', '商品名称', '内容', '发送时间', '是否已读']
        
        self.mock_cursor.description = [(col,) for col in msg_cols]
        self.mock_cursor.fetchall.return_value = mock_message_list
        self.mock_cursor.nextset.return_value = False # No second result set

        page_number = 1
        page_size = 10
        messages, total_count = self.dal.get_chat_messages_by_product_and_users(
            self.product_id, self.sender_id, self.receiver_id, page_number, page_size
        )
        
        expected_messages = [dict(zip(msg_cols, row)) for row in mock_message_list]
        self.assertEqual(messages, expected_messages)
        self.assertEqual(total_count, 0) # Default if no count result set

    def test_mark_message_as_read_success(self):
        expected_result = {'MarkedAsReadMessageID': self.message_id, 'Result': '消息标记为已读成功。'}
        self.mock_cursor.description = [('MarkedAsReadMessageID',), ('Result',)]
        self.mock_cursor.fetchone.return_value = (self.message_id, '消息标记为已读成功。')

        result = self.dal.mark_message_as_read(self.message_id, self.user_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_MarkMessageAsRead ?, ?",
            (self.message_id, self.user_id)
        )
        self.assertEqual(result, expected_result)

    def test_hide_conversation_success(self):
        expected_result = {'Result': '会话已隐藏。', 'ProductID': self.product_id, 'UserID': self.user_id}
        self.mock_cursor.description = [('Result',), ('ProductID',), ('UserID',)]
        self.mock_cursor.fetchone.return_value = ('会话已隐藏。', self.product_id, self.user_id)

        result = self.dal.hide_conversation(self.product_id, self.user_id)

        self.mock_cursor.execute.assert_called_once_with(
            "EXEC sp_HideConversation ?, ?",
            (self.product_id, self.user_id)
        )
        self.assertEqual(result, expected_result)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 