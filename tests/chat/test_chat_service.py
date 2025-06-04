import unittest
from unittest.mock import MagicMock, patch
import uuid

# Corrected import paths
from app.services.chat_service import (
    ChatService,
    InvalidInputError,
    ChatOperationError,
    NotFoundError,
    MAX_CHAT_MESSAGE_LENGTH # Import for test boundary
)
from app.dal.chat_message_dal import ChatMessageDAL

class TestChatService(unittest.TestCase):

    def setUp(self):
        self.mock_dal = MagicMock(spec=ChatMessageDAL) # Renamed for clarity
        self.service = ChatService(chat_message_dal=self.mock_dal)

        self.sender_id = str(uuid.uuid4())
        self.receiver_id = str(uuid.uuid4())
        self.product_id = str(uuid.uuid4())
        self.message_id = str(uuid.uuid4()) # This will be the string form of UUID from DAL
        self.message_id_uuid = uuid.UUID(self.message_id) # UUID object form
        self.user_id = str(uuid.uuid4())
        self.content = "This is a test message."
        self.client_message_id = str(uuid.uuid4())

    def test_send_message_success_newly_created(self):
        self.mock_dal.send_message.return_value = (self.message_id_uuid, True)
        
        msg_id_str, is_newly = self.service.send_message(
            self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id
        )
        
        self.mock_dal.send_message.assert_called_once_with(
            self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id
        )
        self.assertEqual(msg_id_str, self.message_id)
        self.assertTrue(is_newly)

    def test_send_message_success_idempotent_hit(self):
        self.mock_dal.send_message.return_value = (self.message_id_uuid, False)
        msg_id_str, is_newly = self.service.send_message(
            self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id
        )
        self.mock_dal.send_message.assert_called_once_with(
            self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id
        )
        self.assertEqual(msg_id_str, self.message_id)
        self.assertFalse(is_newly)

    def test_send_message_with_client_id_none(self):
        self.mock_dal.send_message.return_value = (self.message_id_uuid, True) # Assuming new message
        msg_id_str, is_newly = self.service.send_message(
            self.sender_id, self.receiver_id, self.product_id, self.content, client_message_id=None
        )
        self.mock_dal.send_message.assert_called_once_with(
            self.sender_id, self.receiver_id, self.product_id, self.content, None
        )
        self.assertEqual(msg_id_str, self.message_id)
        self.assertTrue(is_newly)

    def test_send_message_invalid_sender_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message("invalid-uuid", self.receiver_id, self.product_id, self.content, self.client_message_id)
        self.assertIn("sender_id", cm.exception.field_errors)
        self.mock_dal.send_message.assert_not_called()

    def test_send_message_invalid_receiver_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, "invalid-uuid", self.product_id, self.content, self.client_message_id)
        self.assertIn("receiver_id", cm.exception.field_errors)

    def test_send_message_invalid_product_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, "invalid-uuid", self.content, self.client_message_id)
        self.assertIn("product_id", cm.exception.field_errors)

    def test_send_message_invalid_client_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content, "invalid-uuid")
        self.assertIn("client_message_id", cm.exception.field_errors)
        self.mock_dal.send_message.assert_not_called()

    def test_send_message_empty_content(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, "  ", self.client_message_id)
        self.assertIn("content", cm.exception.field_errors)

    def test_send_message_too_long_content(self):
        long_content = "a" * (MAX_CHAT_MESSAGE_LENGTH + 1)
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, long_content, self.client_message_id)
        self.assertIn("content", cm.exception.field_errors)
    
    def test_send_message_sender_equals_receiver(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.send_message(self.sender_id, self.sender_id, self.product_id, self.content, self.client_message_id)
        self.assertIn("receiver_id", cm.exception.field_errors)
        self.assertEqual(cm.exception.field_errors["receiver_id"], "Sender and receiver cannot be the same.")

    def test_send_message_dal_failure_unexpected_return_type(self):
        # Test if DAL returns something other than a 2-tuple (e.g., None or a single value)
        self.mock_dal.send_message.return_value = None # Violates contract
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while sending the message: "):
             # The exact error message might be about unpacking None, which is a TypeError initially
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id)

    def test_send_message_dal_raises_chat_operation_error(self):
        self.mock_dal.send_message.side_effect = ChatOperationError("DAL Specific Ops Error")
        with self.assertRaisesRegex(ChatOperationError, "DAL Specific Ops Error"):
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id)

    def test_send_message_dal_raises_general_exception(self):
        self.mock_dal.send_message.side_effect = Exception("DAL General Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while sending the message: DAL General Error"):
            self.service.send_message(self.sender_id, self.receiver_id, self.product_id, self.content, self.client_message_id)

    def test_get_conversations_success(self):
        mock_convos = [{'id': 'convo1'}, {'id': 'convo2'}]
        self.mock_dal.get_user_conversations.return_value = mock_convos
        result = self.service.get_conversations(self.user_id)
        self.mock_dal.get_user_conversations.assert_called_once_with(self.user_id)
        self.assertEqual(result, mock_convos)

    def test_get_conversations_invalid_user_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.get_conversations("invalid-user")
        self.assertIn("user_id", cm.exception.field_errors)

    def test_get_conversations_dal_returns_none(self):
        self.mock_dal.get_user_conversations.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to retrieve conversations from DAL."):
            self.service.get_conversations(self.user_id)

    def test_get_conversations_dal_raises_exception(self):
        self.mock_dal.get_user_conversations.side_effect = Exception("DAL Convo Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while fetching conversations: DAL Convo Error"):
            self.service.get_conversations(self.user_id)
    
    def test_get_messages_between_users_for_product_success(self):
        mock_messages = [{'id': 'msg1'}]
        mock_total_count = 1
        self.mock_dal.get_chat_messages_by_product_and_users.return_value = (mock_messages, mock_total_count)
        messages, total_count = self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id, 1, 20)
        self.mock_dal.get_chat_messages_by_product_and_users.assert_called_once_with(self.product_id, self.user_id, self.receiver_id, 1, 20)
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
        self.mock_dal.get_chat_messages_by_product_and_users.return_value = (None, None)
        with self.assertRaisesRegex(ChatOperationError, "Failed to retrieve messages from DAL."):
            self.service.get_messages_between_users_for_product(self.product_id, self.user_id, self.receiver_id)

    def test_mark_message_as_read_success(self):
        self.mock_dal.mark_message_as_read.return_value = {'Result': '消息标记为已读成功'}
        result = self.service.mark_message_as_read(self.message_id, self.user_id)
        self.mock_dal.mark_message_as_read.assert_called_once_with(self.message_id, self.user_id)
        self.assertEqual(result, {'Result': '消息标记为已读成功'})

    def test_mark_message_as_read_invalid_message_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.mark_message_as_read("invalid", self.user_id)
        self.assertIn("message_id", cm.exception.field_errors)

    def test_mark_message_as_read_dal_returns_not_found(self):
        self.mock_dal.mark_message_as_read.return_value = {'Result': '消息不存在'}
        with self.assertRaises(NotFoundError) as cm:
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, '消息不存在')

    def test_mark_message_as_read_dal_returns_no_permission(self):
        self.mock_dal.mark_message_as_read.return_value = {'Result': '无权标记此消息'}
        with self.assertRaises(NotFoundError) as cm: # NotFoundError based on current service logic for this
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, '无权标记此消息')

    def test_mark_message_as_read_dal_returns_none(self):
        self.mock_dal.mark_message_as_read.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to mark message as read. Operation returned no result."):
            self.service.mark_message_as_read(self.message_id, self.user_id)
    
    def test_mark_message_as_read_dal_raises_chat_service_error(self):
        # Simulate DAL raising an error that should be re-raised
        self.mock_dal.mark_message_as_read.side_effect = NotFoundError("Specific DAL Not Found")
        with self.assertRaises(NotFoundError) as cm:
            self.service.mark_message_as_read(self.message_id, self.user_id)
        self.assertEqual(cm.exception.message, "Specific DAL Not Found")

    def test_mark_message_as_read_dal_raises_general_exception(self):
        self.mock_dal.mark_message_as_read.side_effect = Exception("Generic DAL Error")
        with self.assertRaisesRegex(ChatOperationError, "An error occurred while marking message as read: Generic DAL Error"):
            self.service.mark_message_as_read(self.message_id, self.user_id)

    def test_hide_conversation_success(self):
        self.mock_dal.hide_conversation.return_value = {'Result': '会话已隐藏'}
        result = self.service.hide_conversation(self.product_id, self.user_id)
        self.mock_dal.hide_conversation.assert_called_once_with(self.product_id, self.user_id)
        self.assertEqual(result, {'Result': '会话已隐藏'})
    
    def test_hide_conversation_success_no_need_to_hide(self):
        # Test when SP indicates no action was needed but it's not an error
        self.mock_dal.hide_conversation.return_value = {'Result': '用户未参与此商品的任何聊天，无需隐藏。'}
        result = self.service.hide_conversation(self.product_id, self.user_id)
        self.mock_dal.hide_conversation.assert_called_once_with(self.product_id, self.user_id)
        self.assertEqual(result, {'Result': '用户未参与此商品的任何聊天，无需隐藏。'})

    def test_hide_conversation_invalid_product_id(self):
        with self.assertRaises(InvalidInputError) as cm:
            self.service.hide_conversation("invalid", self.user_id)
        self.assertIn("product_id", cm.exception.field_errors)

    def test_hide_conversation_dal_returns_none(self):
        self.mock_dal.hide_conversation.return_value = None
        with self.assertRaisesRegex(ChatOperationError, "Failed to hide conversation. Operation returned no result."):
            self.service.hide_conversation(self.product_id, self.user_id)

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 