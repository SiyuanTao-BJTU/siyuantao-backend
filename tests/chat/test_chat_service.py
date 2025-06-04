import unittest
from unittest.mock import MagicMock, patch
import uuid

# Adjust the import path based on your project structure and how you run tests
from backend.src.modules.chat.services.chat_service import (
    ChatService,
    InvalidInputError,
    ChatOperationError,
    NotFoundError
)
from backend.src.modules.chat.dal.chat_message_dal import ChatMessageDAL # For type hinting if needed

class TestChatService(unittest.TestCase):

    def setUp(self):
        self.mock_chat_message_dal = MagicMock(spec=ChatMessageDAL)
        self.service = ChatService(chat_message_dal=self.mock_chat_message_dal)

        # Common valid test data
        self.sender_id = str(uuid.uuid4())
        self.receiver_id = str(uuid.uuid4())
        self.product_id = str(uuid.uuid4())
        self.message_id = str(uuid.uuid4())
        self.user_id = str(uuid.uuid4())
        self.content = "This is a test message."

    def test_send_message_success(self):
        self.mock_chat_message_dal.send_message.return_value = {'Result': '消息发送成功', 'AffectedRows': 1}
        result = self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content)
        self.mock_chat_message_dal.send_message.assert_called_once_with(self.sender_id, self.receiver_id, self.product_id, self.content)
        self.assertEqual(result, {'Result': '消息发送成功', 'AffectedRows': 1})

    def test_send_message_invalid_sender_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message("invalid-uuid", self.receiver_id, self.product_id, self.content)
        self.assertIn("sender_id", cm.exception.field_errors)
        self.mock_chat_message_dal.send_message.assert_not_called()

    def test_send_message_invalid_receiver_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, "invalid-uuid", self.product_id, self.content)
        self.assertIn("receiver_id", cm.exception.field_errors)

    def test_send_message_invalid_product_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, "invalid-uuid", self.content)
        self.assertIn("product_id", cm.exception.field_errors)

    def test_send_message_empty_content(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, "  ")
        self.assertIn("content", cm.exception.field_errors)

    def test_send_message_too_long_content(self):
        long_content = "a" * 4001
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, long_content)
        self.assertIn("content", cm.exception.field_errors)
    
    def test_send_message_sender_equals_receiver(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.sender_id, self.product_id, self.content)
        self.assertIn("receiver_id", cm.exception.field_errors)
        self.assertEqual(cm.exception.field_errors["receiver_id"], "Sender and receiver cannot be the same.")

    def test_send_message_dal_failure_no_affected_rows(self):
        self.mock_chat_message_dal.send_message.return_value = {'Result': 'Some DB status', 'AffectedRows': 0}
        with self.assertRaisesRegex(ChatOperationError, "Failed to send message. DAL returned no affected rows or error."):
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content)

    def test_send_message_dal_returns_none(self):
        self.mock_chat_message_dal.send_message.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to send message. DAL returned no affected rows or error."):
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content)

    def test_send_message_dal_raises_exception(self):
        self.mock_chat_message_dal.send_message.side_effect = Exception("DAL Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while sending the message: DAL Error"):
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content)

    def test_get_conversations_success(self):
        mock_convos = [{'id': 'convo1'}, {'id': 'convo2'}]
        self.mock_chat_message_dal.get_user_conversations.return_value = mock_convos
        result = self.service.get_conversations(self.user_id)
        self.mock_chat_message_dal.get_user_conversations.assert_called_once_with(self.user_id)
        self.assertEqual(result, mock_convos)

    def test_get_conversations_invalid_user_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_conversations("invalid-user")
        self.assertIn("user_id", cm.exception.field_errors)

    def test_get_conversations_dal_returns_none(self):
        self.mock_chat_message_dal.get_user_conversations.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to retrieve conversations from DAL."):
            self.service.get_conversations(self.user_id)

    def test_get_conversations_dal_raises_exception(self):
        self.mock_chat_message_dal.get_user_conversations.side_effect = Exception("DAL Convo Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while fetching conversations: DAL Convo Error"):
            self.service.get_conversations(self.user_id)
    
    def test_get_messages_between_users_for_product_success(self):
        mock_messages = [{'id': 'msg1'}]
        mock_total_count = 1
        self.mock_chat_message_dal.get_chat_messages_by_product_and_users.return_value = (mock_messages, mock_total_count)
        messages, total_count = self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id, 1, 20)
        self.mock_chat_message_dal.get_chat_messages_by_product_and_users.assert_called_once_with(self.product_id, self.user_id, self.receiver_id, 1, 20)
        self.assertEqual(messages, mock_messages)
        self.assertEqual(total_count, mock_total_count)

    def test_get_messages_invalid_product_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_messages_between_users_for_product("invalid", self.user_id, self.receiver_id)
        self.assertIn("product_id", cm.exception.field_errors)

    def test_get_messages_invalid_page_number(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id, 0, 20)
        self.assertIn("page_number", cm.exception.field_errors)

    def test_get_messages_invalid_page_size(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id, 1, 200)
        self.assertIn("page_size", cm.exception.field_errors)
    
    def test_get_messages_users_are_same(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.user_id)
        self.assertIn("user_id2", cm.exception.field_errors)
        self.assertEqual(cm.exception.field_errors["user_id2"], "User IDs cannot be the same for fetching mutual messages.")

    def test_get_messages_dal_returns_none(self):
        self.mock_chat_message_dal.get_chat_messages_by_product_and_users.return_value = (None, None)
        with self.assertRaisesRegex(ChatOperationError, "Failed to retrieve messages from DAL."):
            self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id)

    def test_mark_message_as_read_success(self):
        self.mock_chat_message_dal.mark_message_as_read.return_value = {'Result': '消息标记为已读成功'}
        result = self.service.mark_message_as_read(self.message_id, self.user_id)
        self.mock_chat_message_dal.mark_message_as_read.assert_called_once_with(self.message_id, self.user_id)
        self.assertEqual(result, {'Result': '消息标记为已读成功'})

    def test_mark_message_as_read_invalid_message_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.mark_message_as_read("invalid", self.user_id)
        self.assertIn("message_id", cm.exception.field_errors)

    def test_mark_message_as_read_dal_returns_not_found(self):
        self.mock_chat_message_dal.mark_message_as_read.return_value = {'Result': '消息不存在'}
        with self.assertRaises(NotFoundError) as cm:
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, '消息不存在')

    def test_mark_message_as_read_dal_returns_no_permission(self):
        self.mock_chat_message_dal.mark_message_as_read.return_value = {'Result': '无权标记此消息'}
        with self.assertRaises(NotFoundError) as cm: # NotFoundError based on current service logic for this
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, '无权标记此消息')

    def test_mark_message_as_read_dal_returns_none(self):
        self.mock_chat_message_dal.mark_message_as_read.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to mark message as read. Operation returned no result."):
            self.service.mark_message_as_read(self.message_id, self.user_id)
    
    def test_mark_message_as_read_dal_raises_chat_service_error(self):
        # Simulate DAL raising an error that should be re-raised
        self.mock_chat_message_dal.mark_message_as_read.side_effect = NotFoundError("Specific DAL Not Found")
        with self.assertRaises(NotFoundError) as cm:
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, "Specific DAL Not Found")

    def test_mark_message_as_read_dal_raises_general_exception(self):
        self.mock_chat_message_dal.mark_message_as_read.side_effect = Exception("Generic DAL Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while marking message as read: Generic DAL Error"):
            self.service.mark_message_as_read(self.message_id, self.user_id)

    def test_hide_conversation_success(self):
        self.mock_chat_message_dal.hide_conversation.return_value = {'Result': '会话已隐藏'}
        result = self.service.hide_conversation(self.product_id, self.user_id)
        self.mock_chat_message_dal.hide_conversation.assert_called_once_with(self.product_id, self.user_id)
        self.assertEqual(result, {'Result': '会话已隐藏'})
    
    def test_hide_conversation_success_no_need_to_hide(self):
        # Test when SP indicates no action was needed but it's not an error
        self.mock_chat_message_dal.hide_conversation.return_value = {'Result': '用户未参与此商品的任何聊天，无需隐藏。'}
        result = self.service.hide_conversation(self.product_id, self.user_id)
        self.mock_chat_message_dal.hide_conversation.assert_called_once_with(self.product_id, self.user_id)
        self.assertEqual(result, {'Result': '用户未参与此商品的任何聊天，无需隐藏。'})

    def test_hide_conversation_invalid_product_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.hide_conversation("invalid", self.user_id)
        self.assertIn("product_id", cm.exception.field_errors)

    def test_hide_conversation_dal_returns_none(self):
        self.mock_chat_message_dal.hide_conversation.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to hide conversation. Operation returned no result."):
            self.service.hide_conversation(self.product_id, self.user_id)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 