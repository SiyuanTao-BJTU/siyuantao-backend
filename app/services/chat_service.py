import uuid
from typing import Optional, Tuple, List, Dict, Any
import logging # Added for logging

# Updated and simplified import for ChatMessageDAL
from app.dal.chat_message_dal import ChatMessageDAL

# Configure basic logging
# In a real app, this would be configured in a central place (e.g., main.py or logging config file)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# TODO: Move this to a configuration file/setting
MAX_CHAT_MESSAGE_LENGTH = 1000

class ChatServiceError(Exception):
    """Base exception for ChatService errors."""
    def __init__(self, message="An error occurred in ChatService", status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class InvalidInputError(ChatServiceError):
    """Exception for invalid input data."""
    def __init__(self, message="Invalid input provided.", field_errors: Optional[Dict[str, str]] = None):
        super().__init__(message, status_code=400)
        self.field_errors = field_errors or {}

class NotFoundError(ChatServiceError):
    """Exception for when a resource is not found."""
    def __init__(self, message="Resource not found."):
        super().__init__(message, status_code=404)

class ChatOperationError(ChatServiceError):
    """Exception for errors during chat operations after validation."""
    def __init__(self, message="Chat operation failed."):
        super().__init__(message, status_code=500)


def is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

class ChatService:
    def __init__(self, chat_message_dal: ChatMessageDAL):
        """
        Initializes the ChatService with a ChatMessageDAL instance.
        :param chat_message_dal: An instance of ChatMessageDAL.
        """
        self.dal = chat_message_dal

    def send_message(self, sender_id: str, receiver_id: str, product_id: str, content: str, client_message_id: Optional[str] = None) -> Tuple[str, bool]:
        """
        Sends a chat message after validating inputs.
        Returns a tuple (message_id, is_newly_created).
        """
        logger.info(
            f"Attempting to send message from {sender_id} to {receiver_id} for product {product_id} (ClientMsgId: {client_message_id})"
        )
        field_errors = {}
        if not is_valid_uuid(sender_id):
            field_errors["sender_id"] = "Invalid sender ID format."
        if not is_valid_uuid(receiver_id):
            field_errors["receiver_id"] = "Invalid receiver ID format."
        if not is_valid_uuid(product_id):
            field_errors["product_id"] = "Invalid product ID format."
        
        if client_message_id and not is_valid_uuid(client_message_id):
            field_errors["client_message_id"] = "Invalid client message ID format."

        if not content or not content.strip():
            field_errors["content"] = "Message content cannot be empty."
        elif len(content) > MAX_CHAT_MESSAGE_LENGTH:
            field_errors["content"] = f"Message content exceeds maximum length of {MAX_CHAT_MESSAGE_LENGTH} characters."
        
        if sender_id == receiver_id:
            field_errors["receiver_id"] = "Sender and receiver cannot be the same."

        if field_errors:
            logger.warning(f"Validation failed for sending message: {field_errors}")
            raise InvalidInputError("Validation failed for sending message.", field_errors=field_errors)

        try:
            message_id, is_newly_created = self.dal.send_message(
                sender_id, receiver_id, product_id, content, client_message_id
            )
            
            logger.info(
                f"Message sent successfully. MessageID: {message_id}, NewlyCreated: {is_newly_created}"
            )
            
            # TODO: Trigger asynchronous notification to receiver_id about new message message_id
            # Example: background_tasks.add_task(notify_user, receiver_id, message_id)
            
            return str(message_id), is_newly_created
        
        except ChatOperationError as e:
            logger.error(f"ChatOperationError in send_message: {e.message}", exc_info=True)
            raise # Re-raise specific, already categorised errors
        except Exception as e: 
            logger.error(f"Unexpected error in send_message: {str(e)}", exc_info=True)
            # Wrap unexpected DAL errors or other issues into a ChatOperationError
            raise ChatOperationError(f"An error occurred while sending the message: {str(e)}")


    def get_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all conversations for a given user.
        :param user_id: The ID of the user.
        :return: A list of conversation objects.
        :raises InvalidInputError: If user_id is invalid.
        :raises ChatOperationError: If the DAL operation fails.
        """
        if not is_valid_uuid(user_id):
            raise InvalidInputError("Invalid user ID format.", field_errors={"user_id": "Invalid user ID format."})
        
        try:
            conversations = self.dal.get_user_conversations(user_id)
            if conversations is None: # DAL might return None on error
                raise ChatOperationError("Failed to retrieve conversations from DAL.")
            return conversations
        except Exception as e:
            raise ChatOperationError(f"An error occurred while fetching conversations: {str(e)}")

    def get_messages_between_users_for_product(
        self, product_id: str, user_id1: str, user_id2: str, 
        page_number: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Retrieves chat messages between two users for a specific product, with pagination.
        :param product_id: The ID of the product.
        :param user_id1: The ID of the first user.
        :param user_id2: The ID of the second user.
        :param page_number: The page number for pagination (1-indexed).
        :param page_size: The number of messages per page.
        :return: A tuple containing a list of message objects and the total number of messages.
        :raises InvalidInputError: If any input is invalid.
        :raises ChatOperationError: If the DAL operation fails.
        """
        field_errors = {}
        if not is_valid_uuid(product_id):
            field_errors["product_id"] = "Invalid product ID format."
        if not is_valid_uuid(user_id1):
            field_errors["user_id1"] = "Invalid user ID (1) format."
        if not is_valid_uuid(user_id2):
            field_errors["user_id2"] = "Invalid user ID (2) format."
        if page_number < 1:
            field_errors["page_number"] = "Page number must be positive."
        if page_size < 1 or page_size > 100: # Example max page size
            field_errors["page_size"] = "Page size must be between 1 and 100."
        
        if user_id1 == user_id2: # Though SP handles this, service layer can also check
            field_errors["user_id2"] = "User IDs cannot be the same for fetching mutual messages."

        if field_errors:
            raise InvalidInputError("Validation failed for fetching messages.", field_errors=field_errors)

        try:
            messages, total_count = self.dal.get_chat_messages_by_product_and_users(
                product_id, user_id1, user_id2, page_number, page_size
            )
            if messages is None or total_count is None: # Check if DAL had an issue
                raise ChatOperationError("Failed to retrieve messages from DAL.")
            return messages, total_count
        except Exception as e:
            raise ChatOperationError(f"An error occurred while fetching messages: {str(e)}")

    def mark_message_as_read(self, message_id: str, user_id: str) -> Dict[str, Any]:
        """
        Marks a specific message as read by the user.
        :param message_id: The ID of the message to mark as read.
        :param user_id: The ID of the user (receiver) marking the message.
        :return: A dictionary with the result of the operation.
        :raises InvalidInputError: If any input is invalid.
        :raises ChatOperationError: If the DAL operation fails.
        :raises NotFoundError: If the message to mark as read is not found or user is not receiver.
        """
        field_errors = {}
        if not is_valid_uuid(message_id):
            field_errors["message_id"] = "Invalid message ID format."
        if not is_valid_uuid(user_id):
            field_errors["user_id"] = "Invalid user ID format."

        if field_errors:
            raise InvalidInputError("Validation failed for marking message as read.", field_errors=field_errors)

        try:
            result = self.dal.mark_message_as_read(message_id, user_id)
            # The SP `sp_MarkMessageAsRead` raises errors for "message not found" or "no permission".
            # If the DAL re-raises these as specific exceptions, we can catch them.
            # Otherwise, we might infer from the result if it indicates failure.
            # For example, if result is None or contains an error message from the SP.
            if not result: # Simplified check; depends on DAL/SP error propagation
                raise ChatOperationError("Failed to mark message as read. Operation returned no result.")
            # If SP uses RAISERROR, it should be caught by DAL and re-raised.
            # Example: if SP returns a specific message for "not found" or "no permission"
            if "消息不存在" in result.get("Result", "") or "无权标记" in result.get("Result", ""):
                 raise NotFoundError(result.get("Result")) # Or a more generic "Operation not permitted"
            
            return result
        except ChatServiceError: # Re-raise specific service errors
            raise
        except Exception as e:
            # Log e
            raise ChatOperationError(f"An error occurred while marking message as read: {str(e)}")


    def hide_conversation(self, product_id: str, user_id: str) -> Dict[str, Any]:
        """
        Hides a conversation related to a product for a specific user.
        :param product_id: The ID of the product for the conversation.
        :param user_id: The ID of the user hiding the conversation.
        :return: A dictionary with the result of the operation.
        :raises InvalidInputError: If any input is invalid.
        :raises ChatOperationError: If the DAL operation fails.
        """
        field_errors = {}
        if not is_valid_uuid(product_id):
            field_errors["product_id"] = "Invalid product ID format."
        if not is_valid_uuid(user_id):
            field_errors["user_id"] = "Invalid user ID format."

        if field_errors:
            raise InvalidInputError("Validation failed for hiding conversation.", field_errors=field_errors)

        try:
            result = self.dal.hide_conversation(product_id, user_id)
            if not result:
                raise ChatOperationError("Failed to hide conversation. Operation returned no result.")
            # Potentially check result message for specific outcomes from SP like "no conversation to hide"
            if "无需隐藏" in result.get("Result", ""): # Example based on sp_HideConversation output
                # This might not be an error, but a status. Decide how to handle.
                pass # Or return a specific status/message to the caller
            return result
        except Exception as e:
            # Log e
            raise ChatOperationError(f"An error occurred while hiding conversation: {str(e)}") 