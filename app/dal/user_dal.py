# app/dal/user_dal.py
import pyodbc
# Keep for type hinting, but not for direct calls within methods
from app.dal.base import execute_query
from app.exceptions import NotFoundError, IntegrityError, DALError, ForbiddenError
from uuid import UUID
import logging
from datetime import datetime
from typing import Optional, Dict, Any
# from datetime import datetime # 如果存储过程返回 datetime 对象

logger = logging.getLogger(__name__)


class UserDAL:
    def __init__(self, execute_query_func):  # Accept execute_query as a dependency
        # DAL 类本身不持有连接，连接由 Service 层或 API 层的依赖注入提供
        # Store the injected execute_query function
        self.execute_query_func = execute_query_func

    async def get_user_by_id(self, conn: pyodbc.Connection, user_id: UUID) -> dict | None:
        """从数据库获取指定 ID 的用户（获取完整资料）。"""
        logger.debug(
            f"DAL: Attempting to get user by ID: {user_id}")  # Add logging
        # 调用 sp_GetUserProfileById 存储过程
        sql = "{CALL sp_GetUserProfileById(?)}"
        try:
            # Use the injected execute_query function
            result = await self.execute_query_func(conn, sql, (user_id,), fetchone=True)
            # Add logging
            logger.debug(
                f"DAL: sp_GetUserProfileById for ID {user_id} returned: {result}")
            # Check for specific messages indicating user not found, handle potential variations
            if result and isinstance(result, dict):
                if '用户不存在。' in result.values() or 'User not found.' in result.values() or (result.get('OperationResultCode') == -1 if result.get('OperationResultCode') is not None else False):
                    # Add logging
                    logger.debug(
                        f"DAL: User with ID {user_id} not found according to SP.")
                    return None  # 用户不存在
                 # If it's a dictionary and not an error message, return the result
                return result
            # Add logging
            logger.warning(
                f"DAL: sp_GetUserProfileById for ID {user_id} returned unexpected type or None: {result}")
            return None  # Handle cases where result is not a dict as expected

        except Exception as e:
            # Add logging
            logger.error(f"DAL: Error getting user by ID {user_id}: {e}")
            raise DALError(
                f"Database error while fetching user profile: {e}") from e

    async def get_user_public_profile_by_id(
        self, conn: pyodbc.Connection, user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """从数据库获取指定 ID 的用户公开信息。"""
        logger.debug(f"DAL: Attempting to get public user profile by ID: {user_id}")
        sql = "{CALL sp_GetUserPublicProfileById(?)}"
        try:
            result = await self.execute_query_func(conn, sql, (user_id,), fetchone=True)
            logger.debug(
                f"DAL: sp_GetUserPublicProfileById for ID {user_id} returned: {result}"
            )
            if result and isinstance(result, dict):
                # Check for explicit error messages from SP indicating user not found
                if (
                    "用户不存在。" in result.values()
                    or "User not found." in result.values()
                ):
                    logger.debug(f"DAL: Public user profile with ID {user_id} not found according to SP.")
                    return None  # 用户不存在
                return result
            logger.warning(
                f"DAL: sp_GetUserPublicProfileById for ID {user_id} returned unexpected type or None: {result}"
            )
            return None
        except pyodbc.Error as e:
            logger.error(f"DAL: Database error getting public user profile by ID {user_id}: {e}")
            raise DALError(
                f"Database error while fetching public user profile: {e}"
            ) from e
        except Exception as e:
            logger.error(
                f"DAL: Unexpected error getting public user profile by ID {user_id}: {e}"
            )
            raise e

    async def get_user_by_username_with_password(self, conn: pyodbc.Connection, username: str) -> dict | None:
        """从数据库获取指定用户名的用户（包含密码哈希），用于登录。"""
        logger.debug(
            # Add logging
            f"DAL: Attempting to get user by username with password: {username}")
        # 调用 sp_GetUserByUsernameWithPassword 存储过程
        sql = "{CALL sp_GetUserByUsernameWithPassword(?)}"
        try:
            # Use the injected execute_query function
            result = await self.execute_query_func(conn, sql, (username,), fetchone=True)
            # Add logging
            logger.debug(
                f"DAL: sp_GetUserByUsernameWithPassword for {username} returned: {result}")
            if result and isinstance(result, dict):
                 if '用户名不能为空。' in result.values() or 'Username cannot be empty.' in result.values():  # 根据存储过程的错误返回判断
                     # Add logging
                     logger.debug(
                         f"DAL: User with username {username} not found according to SP.")
                     return None  # 用户名为空
                 return result  # Assuming a dict result is the user data
            # Add logging
            logger.warning(
                f"DAL: sp_GetUserByUsernameWithPassword for {username} returned unexpected type or None: {result}")
            return None
        except Exception as e:
            # Add logging
            logger.error(
                f"DAL: Error getting user by username {username}: {e}")
            raise DALError(
                f"Database error while fetching user by username: {e}") from e

    async def create_user(self, conn: pyodbc.Connection, username: str, hashed_password: str, phone_number: str, major: Optional[str] = None) -> dict:
        """在数据库中创建新用户并返回其数据。"""
        logger.debug(f"DAL: Attempting to create user: {username}")
        sql = "{CALL sp_CreateUser(?, ?, ?, ?)}"
        try:
            # 调用 sp_CreateUser 存储过程
            logger.debug(
                f"DAL: Executing sp_CreateUser for {username} with phone: {phone_number}, major: {major}")
            # sp_CreateUser returns a single row with NewUserID and potentially Message/Error
            result = await self.execute_query_func(conn, sql, (username, hashed_password, phone_number, major), fetchone=True)
            logger.debug(
                f"DAL: sp_CreateUser for {username} returned raw result: {result}")

            # 1. 检查结果是否为 None 或非字典类型
            if not result or not isinstance(result, dict):
                logger.error(
                    f"DAL: sp_CreateUser for {username} returned invalid result: {result}")
                raise DALError(
                    f"User creation failed: Unexpected response from database: {result}")

            # Get potential NewUserID, error message, and result code
            new_user_id_raw = result.get('新用户ID')
            error_message = result.get('Error') or result.get('Message') or result.get('')
            result_code = result.get('OperationResultCode')

            # Prioritize handling explicit error messages from the stored procedure
            if error_message:
                logger.debug(f"DAL: sp_CreateUser for {username} returned message: {error_message}")
                if '用户名已存在' in error_message or 'Duplicate username' in error_message:
                    raise IntegrityError("Username already exists.")
                elif '手机号码已存在' in error_message or '手机号已存在' in error_message or 'Duplicate phone' in error_message:
                    raise IntegrityError("Phone number already exists.")
                # Handle other potential SP-specific errors
                raise DALError(
                    f"Stored procedure error during user creation: {error_message}")

            # If no explicit error message, check result code if available and non-zero
            if result_code is not None and result_code != 0:  # Assuming 0 is success
                logger.error(f"DAL: sp_CreateUser for {username} returned non-zero result code: {result_code}. Result: {result}")
                # Map result code to specific error if possible, otherwise raise generic DALError
                if result_code == -1: # Example: User already exists
                    raise IntegrityError("User already exists (code -1).")
                else:
                    raise DALError(
                        f"Stored procedure failed with result code: {result_code}")

            # If no explicit error and no non-zero result code, expect NewUserID to be present for success
            if not new_user_id_raw:
                logger.error(
                    f"DAL: sp_CreateUser for {username} completed but did not return '新用户ID'. Result: {result}")
                raise DALError(
                    "User creation failed: User ID not returned from database.")

            # Validate and convert NewUserID
            if not isinstance(new_user_id_raw, UUID):
                try:
                    new_user_id = UUID(str(new_user_id_raw))
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"DAL: Returned '新用户ID' is not a valid UUID: {new_user_id_raw}. Error: {e}")
                    raise DALError(
                        f"User creation failed: Invalid User ID format returned: {new_user_id_raw}") from e
            else:
                new_user_id = new_user_id_raw

            logger.info(
                f"DAL: User {username} created with '新用户ID': {new_user_id}. Fetching full info.")

            # 获取完整用户信息 using the created ID
            full_user_info = await self.get_user_by_id(conn, new_user_id)
            logger.debug(
                f"DAL: get_user_by_id for new user {new_user_id} returned: {full_user_info}")

            if not full_user_info:
                logger.error(
                    f"DAL: Failed to retrieve full user info after creation for ID: {new_user_id}")
                raise DALError(
                    f"Failed to retrieve full user info after creation for ID: {new_user_id}")

            logger.info(f"DAL: Full info retrieved for new user: {username}")
            return full_user_info  # Return the fetched dictionary

        except IntegrityError:
            raise  # Re-raise known integrity errors
        except DALError:
            raise  # Re-raise DAL errors originating from our checks
        except pyodbc.IntegrityError as e:
            # Catch pyodbc.IntegrityError raised by the driver for constraint violations
            logger.error(
                f"DAL: pyodbc.IntegrityError during user creation for {username}: {e}")
            error_message = str(e)
            # Check for specific error messages related to unique constraints
            error_message_lower = error_message.lower()
            if ('duplicate key' in error_message_lower or '违反唯一约束' in error_message_lower) and ('username' in error_message_lower or '用户名' in error_message_lower):
                raise IntegrityError("Username already exists.") from e
            elif ('duplicate key' in error_message_lower or '违反唯一约束' in error_message_lower) and ('phone' in error_message_lower or '手机' in error_message_lower):
                 raise IntegrityError("Phone number already exists.") from e
            else:
                logger.error(
                    f"DAL: Unexpected pyodbc.IntegrityError during user creation: {e}")
                raise DALError(
                    f"Database integrity error during user creation: {e}") from e
        except Exception as e:
            logger.error(f"DAL: Generic Error creating user {username}: {e}")
            # Catch any other unexpected exceptions during the DAL operation
            raise DALError(f"Database error during user creation: {e}") from e

    async def update_user_profile(self, conn: pyodbc.Connection, user_id: UUID, *, username: Optional[str] = None, major: Optional[str] = None, avatar_url: Optional[str] = None, bio: Optional[str] = None, phone_number: Optional[str] = None, email: Optional[str] = None) -> dict | None:
        """更新现有用户的个人资料，返回更新后的用户数据。"""
        logger.debug(
            # Add logging
            f"DAL: Attempting to update profile for user ID: {user_id}")
        sql = "{CALL sp_UpdateUserProfile(?, ?, ?, ?, ?, ?, ?)}"
        try:
            # Add logging
            logger.debug(
                f"DAL: Executing sp_UpdateUserProfile for ID {user_id}")
            # sp_UpdateUserProfile should return the updated user data (a dict) or indicate error/not found
            result = await self.execute_query_func(
                conn, sql,
                (user_id, major, avatar_url, bio, phone_number, email, username),
                fetchone=True
            )
            # Add logging
            logger.debug(
                f"DAL: sp_UpdateUserProfile for ID {user_id} returned: {result}")

            # Assuming SP returns the updated user data or a success indicator
            if result and isinstance(result, dict):
                error_message = result.get('') or result.get(
                    'Error') or result.get('Message')
                # Assuming SP might return this
                result_code = result.get('OperationResultCode')

                if error_message:
                    # Add logging
                    logger.warning(
                        f"DAL: sp_UpdateUserProfile for ID {user_id} returned error: {error_message}")
                    if '用户未找到' in error_message or 'User not found.' in error_message:
                        raise NotFoundError(
                            f"User with ID {user_id} not found for update.")
                    # Prioritize checking for specific duplicate phone error message from SP
                    elif '此手机号码已被其他用户使用' in error_message or '手机号码已存在' in error_message or 'Phone number already in use' in error_message or '手机号已存在' in error_message:
                         raise IntegrityError(
                             "Phone number already in use by another user.")
                    else:
                         # If it's an error from SP but not specific to user not found or duplicate phone
                         raise DALError(
                             f"Stored procedure error during profile update: {error_message}")

                if result_code is not None and result_code != 0:
                    logger.warning(
                        f"DAL: sp_UpdateUserProfile for ID {user_id} returned non-zero result code: {result_code}. Result: {result}")
                    # Handle specific result codes if necessary
                    raise DALError(
                        f"Stored procedure failed with result code: {result_code}")

                # If no error message and no non-zero result code, assume success and return the fetched data
                # Add logging
                logger.debug(
                    f"DAL: Profile update for ID {user_id} successful.")
                # Return the dictionary fetched by execute_query(fetchone=True) which should be the updated user data
                return result
            elif result is None:
                 # Add logging
                 logger.debug(
                     f"DAL: Profile update for ID {user_id} returned None.")
                 # If SP is designed to return None for user not found
                 raise NotFoundError(
                     f"User with ID {user_id} not found for update.")

            # If result is not None and not a dict with an error message, assume success and return the data
            # Add logging
            logger.warning(
                f"DAL: Profile update for ID {user_id} returned unexpected non-dict result: {result}")
            # Decide how to handle this - maybe raise an error or return None assuming failure
            raise DALError(
                f"Database error during profile update: {result}")

        except (NotFoundError, IntegrityError) as e:
             # Add logging
             logger.error(
                 f"DAL: Specific Error during profile update for ID {user_id}: {e}")
             raise e  # Re-raise specific errors caught from our checks
        except pyodbc.IntegrityError as e:
             # Catch pyodbc.IntegrityError raised by the driver
             # Add logging
             logger.error(
                 f"DAL: pyodbc.IntegrityError during profile update for ID {user_id}: {e}")
             error_message = str(e)
             # Check for specific error messages related to duplicate phone number from the driver
             # These might be different depending on the database and driver configuration
             error_message_lower = error_message.lower()
             # Example patterns for duplicate key errors, specifically looking for phone number context
             if ('duplicate key' in error_message_lower or '违反唯一约束' in error_message_lower) and ('phone' in error_message_lower or '手机' in error_message_lower):
                 raise IntegrityError(
                     "Phone number already in use by another user.") from e
             else:
                 # Re-raise other IntegrityErrors as DALError or a more specific error
                 logger.error(
                     f"DAL: Unexpected pyodbc.IntegrityError during profile update: {e}")
                 raise DALError(
                     f"Database integrity error during profile update: {e}") from e
        except Exception as e:
            # Add logging
            logger.error(
                f"DAL: Generic Error updating user profile for {user_id}: {e}")
            # Catch any other unexpected exceptions during the DAL operation
            raise DALError(
                f"Database error during user profile update: {e}") from e

    async def update_user_password(self, conn: pyodbc.Connection, user_id: UUID, hashed_password: str) -> bool:
        """更新用户密码。"""
        logger.debug(
            # Add logging
            f"DAL: Attempting to update password for user ID: {user_id}")
        sql = "{CALL sp_UpdateUserPassword(?, ?)}"
        try:
            # 调用 sp_UpdateUserPassword 存储过程
            # Use the injected execute_query function. SP returns a single row result.
            # Add logging
            logger.debug(
                f"DAL: Executing sp_UpdateUserPassword for ID {user_id}")
            result = await self.execute_query_func(conn, sql, (user_id, hashed_password), fetchone=True)
            # Add logging
            logger.debug(
                f"DAL: sp_UpdateUserPassword for ID {user_id} returned: {result}")

            if result and isinstance(result, dict):
                 error_message = result.get('') or result.get(
                     'Error') or result.get('Message')
                 result_code = result.get('OperationResultCode')

                 if error_message:
                     logger.warning(
                         f"DAL: Password update failed for ID {user_id}: SP returned error: {error_message}")
                     if '用户未找到。' in error_message and result_code == -1: # Check code as well
                          raise NotFoundError(
                              f"User with ID {user_id} not found for password update.")
                     elif '密码更新失败。' in error_message or 'Password update failed.' in error_message: # Add a specific code check if SP provides one
                           # This indicates an internal SP logic error, not user input
                          raise DALError(
                              "Password update failed in stored procedure.")
                     # If the message is a success message but caught here as an error, it's a logic error in the SP/DAL mapping
                     if '密码更新成功' in error_message or 'Password updated successfully' in error_message:
                          logger.info(f"DAL: Password updated successfully for user ID: {user_id} (via success message)")
                          return True # Indicate success based on success message

                 # If result is a dict and no handled error_message was found, assume success if result_code is 0 or absent.
                 if result_code is None or result_code == 0:
                     logger.info(f"DAL: Password updated successfully for user ID: {user_id}")
                     return True # Indicate success
                 else:
                      # If there's an unhandled error message or a non-zero result code, raise generic DALError
                      raise DALError(f"Stored procedure error during password update: {error_message if error_message else f'Code: {result_code}. Result: {result}'}")

            # If result is None or not a dict (and no exception from execute_query_func), it's an unexpected scenario.
            logger.error(
                f"DAL: sp_UpdateUserPassword for ID {user_id} returned unexpected result: {result}")
            raise DALError("Password update failed: Unexpected response from database.")

        except (NotFoundError, DALError) as e:
             # Re-raise known errors
             raise e
        except Exception as e:
             # Catch any other unexpected exceptions during the DAL operation
             logger.error(f"DAL: Unexpected error updating password for ID {user_id}: {e}")
             raise DALError(f"Database error during password update: {e}") from e

    # New method: Get user password hash by ID
    async def get_user_password_hash_by_id(self, conn: pyodbc.Connection, user_id: UUID) -> str | None:
        """根据用户 ID 获取密码哈希。"""
        logger.debug(
            # Add logging
            f"DAL: Attempting to get password hash for user ID: {user_id}")
        sql = "{CALL sp_GetUserPasswordHashById(?)}"
        try:
            # Use the injected execute_query function
            # Add logging
            logger.debug(
                f"DAL: Executing sp_GetUserPasswordHashById for ID {user_id}")
            # SP returns a single row with the Password hash or an error message
            result = await self.execute_query_func(conn, sql, (user_id,), fetchone=True)
            # Add logging
            logger.debug(
                f"DAL: sp_GetUserPasswordHashById for ID {user_id} returned: {result}")

            if result and isinstance(result, dict):
                error_message = result.get('') or result.get(
                    'Error') or result.get('Message')

                if error_message:
                     # Add logging
                     logger.debug(
                         f"DAL: Password hash not found for ID {user_id}: SP returned message: {error_message}")
                     # If message indicates user not found specifically
                     if '用户不存在。' in error_message or 'User not found.' in error_message:
                          return None  # User not found
                     # Handle other potential errors from SP
                     raise DALError(
                         f"Stored procedure error fetching password hash: {error_message}")

                if 'Password' in result:
                    # Add logging
                    logger.debug(f"DAL: Password hash found for ID {user_id}.")
                    return result['Password']

                if 'PasswordHash' in result: # Also check for PasswordHash key
                    # Add logging
                    logger.debug(f"DAL: Password hash found for ID {user_id} (using PasswordHash key).")
                    return result['PasswordHash']

                # If result is a dict but doesn't contain 'Password' and no error message, unexpected
                # Add logging
                logger.warning(
                    f"DAL: sp_GetUserPasswordHashById for ID {user_id} returned dict without 'Password' key or error: {result}")
                # Treat as not found or DAL error? Let's return None assuming hash wasn't found as expected
                return None

            # If result is None or not a dict
            # Add logging
            logger.warning(
                f"DAL: sp_GetUserPasswordHashById for ID {user_id} returned unexpected result: {result}")
            return None  # Assume hash not found due to unexpected result

        except DALError:
             raise  # Re-raise DAL errors
        except Exception as e:
            # Add logging
            logger.error(
                f"DAL: Generic Error getting password hash for user ID {user_id}: {e}")
            raise DALError(
                f"Database error while fetching password hash: {e}") from e

    async def delete_user(self, conn: pyodbc.Connection, user_id: UUID) -> bool:
        """
        Deletes a user by their ID by performing a soft delete.
        This updates the user's email to a unique placeholder and sets their status to 'Disabled'.
        """
        logger.info(f"DAL: Attempting soft delete for user with ID: {user_id}")

        # Generate a unique placeholder email to ensure uniqueness after deletion
        # Format: deleted_<user_id_short_hash>@deleted.invalid
        unique_suffix = str(user_id).replace("-", "")[:12] # Use part of UUID for uniqueness
        placeholder_email = f"deleted_{unique_suffix}@{datetime.now().strftime('%Y%m%d%H%M%S')}.invalid"
        placeholder_username = f"deleted_user_{unique_suffix}"
        # Generate a placeholder phone number that starts with '2' and is within typical phone number length (e.g., 11-15 digits)
        # Using a shorter, unique suffix to ensure it fits NVARCHAR(20)
        phone_suffix = str(user_id).replace("-", "")[-8:] # Use last 8 chars for a shorter unique part
        placeholder_phone_number = f"2{phone_suffix}"

        # Update SQL to perform soft delete: update email, username, phone number, and status
        sql = """
        UPDATE [User]
        SET
            Email = ?,
            UserName = ?,
            PhoneNumber = ?,
            Status = 'Disabled'
        WHERE UserID = ?;
        """
        params = (placeholder_email, placeholder_username, placeholder_phone_number, str(user_id))

        try:
            # Use execute_query_func for non-query operations, it returns rows affected for UPDATE/DELETE
            rows_affected = await self.execute_query_func(conn, sql, params, fetchone=False, fetchall=False)

            if rows_affected == 0:
                logger.warning(f"DAL: User {user_id} not found for soft deletion or no rows affected.")
                raise NotFoundError(f"User with ID {user_id} not found for deletion.")
            
            logger.info(f"DAL: User {user_id} soft deleted successfully (rows affected: {rows_affected}). Email set to {placeholder_email}, status set to Disabled.")
            return True

        except NotFoundError as e:
            logger.error(f"DAL: User soft deletion failed for {user_id}: {e}")
            raise e
        except pyodbc.Error as e:
            logger.error(f"DAL: Database error during user soft deletion for {user_id}: {e}")
            raise DALError(f"Database error during user soft deletion: {e}") from e
        except Exception as ex:
            logger.error(f"DAL: Unexpected Python error during user soft deletion for {user_id}: {ex}")
            raise DALError(f"Unexpected server error during user soft deletion: {ex}") from ex

    async def get_system_notifications_by_user_id(self, conn: pyodbc.Connection, user_id: UUID) -> list[dict]:
        """获取某个用户的系统通知列表。"""
        logger.debug(f"DAL: Getting system notifications for user {user_id}.")
        sql = "{CALL sp_GetSystemNotificationsByUserId(?)}"
        try:
            # Use the injected execute_query function
            result = await self.execute_query_func(conn, sql, (user_id,), fetchall=True)
            logger.debug(f"DAL: sp_GetSystemNotificationsByUserId for user {user_id} returned: {result}")

            if result and isinstance(result, list):
                 # Check if the list contains an error message indicator from SP
                 if any(isinstance(row, dict) and ('用户不存在。' in row.values() or 'User not found.' in row.values()) for row in result):
                      logger.debug(f"DAL: User {user_id} not found according to SP, no notifications returned.")
                      return [] # User not found or no notifications
                 # Assuming a list of dicts is the expected notification data
                 # Map keys if necessary (though SP columns seem mapped in Service)
                 return result
            elif result is None:
                 logger.debug(f"DAL: sp_GetSystemNotificationsByUserId for user {user_id} returned None.")
                 return [] # No users or no notifications
            else:
                 logger.warning(f"DAL: sp_GetSystemNotificationsByUserId for user {user_id} returned unexpected result type: {result}")
                 # Decide how to handle unexpected types - empty list or raise error
                 raise DALError("Database error while fetching system notifications: Unexpected data format.")

        except DALError:
             raise # Re-raise DAL errors
        except Exception as e:
            logger.error(f"Error getting system notifications for user {user_id}: {e}")
            raise DALError(f"Database error while fetching system notifications: {e}") from e

    async def mark_notification_as_read(self, conn: pyodbc.Connection, notification_id: UUID, user_id: UUID) -> bool:
        """标记系统通知为已读。"""
        logger.debug(f"DAL: Marking notification {notification_id} as read for user {user_id}")
        sql = "{CALL sp_MarkNotificationAsRead(?, ?)}"
        try:
            # Use the injected execute_query function. SP returns a single row result.
            result = await self.execute_query_func(conn, sql, (notification_id, user_id), fetchone=True)
            logger.debug(f"DAL: sp_MarkNotificationAsRead for notification {notification_id}, user {user_id} returned: {result}")

            if result and isinstance(result, dict):
                error_message = result.get('') or result.get('Error') or result.get('Message')
                result_code = result.get('OperationResultCode')

                if error_message:
                     logger.warning(f"DAL: Mark notification as read failed: SP returned error: {error_message}")
                     if '通知不存在。' in error_message or 'Notification not found.' in error_message:
                          raise NotFoundError(f"Notification with ID {notification_id} not found.")
                     if '无权标记此通知为已读。' in error_message or 'No permission to mark this notification as read.' in error_message:
                          raise ForbiddenError(f"User {user_id} does not have permission to mark notification {notification_id} as read.")
                     raise DALError(f"Stored procedure error marking notification as read: {error_message}")

                if result_code is not None and result_code != 0:
                      logger.warning(f"DAL: sp_MarkNotificationAsRead for notif {notification_id}, user {user_id} returned non-zero result code: {result_code}. Result: {result}")
                      raise DALError(f"Stored procedure failed with result code: {result_code}")


                if '通知标记为已读成功。' in result.values() or 'Notification marked as read successfully.' in result.values():
                     logger.info(f"DAL: Notification {notification_id} marked as read for user {user_id}")
                     return True
                else:
                     logger.warning(f"DAL: sp_MarkNotificationAsRead for notif {notification_id}, user {user_id} returned ambiguous success indicator: {result}")
                     # Assume success if no error and result is a dict
                     return True

            # If result is None or not a dict
            logger.warning(f"DAL: sp_MarkNotificationAsRead for notif {notification_id}, user {user_id} returned unexpected result: {result}")
            # If not found/forbidden, an exception should have been raised by message check.
            # If update truly failed without an SP error message, return False or raise DAL error.
            raise DALError(f"Database error while marking notification as read: {result}")

        except (NotFoundError, ForbiddenError, DALError) as e:
            raise e # Re-raise specific exceptions
        except Exception as e:
            logger.error(f"DAL: Error marking notification {notification_id} as read for user {user_id}: {e}")
            raise DALError(f"Database error while marking notification as read: {e}") from e

    async def set_chat_message_visibility(self, conn: pyodbc.Connection, message_id: UUID, user_id: UUID, visible_to: str, is_visible: bool) -> bool:
        """设置聊天消息对发送者或接收者的可见性（逻辑删除）。"""
        logger.debug(f"DAL: Setting chat message {message_id} visibility for user {user_id}.")
        sql = "{CALL sp_SetChatMessageVisibility(?, ?, ?, ?)}"
        try:
            # Use the injected execute_query function. SP returns a single row result.
            result = await self.execute_query_func(conn, sql, (message_id, user_id, visible_to, is_visible), fetchone=True)
            logger.debug(f"DAL: sp_SetChatMessageVisibility for message {message_id}, user {user_id} returned: {result}")

            if result and isinstance(result, dict):
                 error_message = result.get('') or result.get('Error') or result.get('Message')
                 result_code = result.get('OperationResultCode')

                 if error_message:
                     logger.warning(f"DAL: Set message visibility failed: SP returned error: {error_message}")
                     if '消息不存在。' in error_message or 'Message not found.' in error_message:
                          raise NotFoundError(f"Message with ID {message_id} not found.")
                     if '无权修改此消息的可见性。' in error_message or 'No permission to modify this message visibility.' in error_message:
                          raise ForbiddenError(f"User {user_id} does not have permission to modify visibility of message {message_id}.")
                     raise DALError(f"Stored procedure error setting message visibility: {error_message}")

                 if result_code is not None and result_code != 0:
                      logger.warning(f"DAL: sp_SetChatMessageVisibility for msg {message_id}, user {user_id} returned non-zero result code: {result_code}. Result: {result}")
                      raise DALError(f"Stored procedure failed with result code: {result_code}")


                 if '消息可见性设置成功' in result.values() or 'Message visibility set successfully' in result.values():
                      logger.info(f"DAL: Message {message_id} visibility set successfully for user {user_id}.")
                      return True
                 else:
                      logger.warning(f"DAL: sp_SetChatMessageVisibility for msg {message_id}, user {user_id} returned ambiguous success indicator: {result}")
                      return True

            # If result is None or not a dict
            logger.warning(f"DAL: sp_SetChatMessageVisibility for msg {message_id}, user {user_id} returned unexpected result: {result}")
            raise DALError(f"Database error while setting message visibility: {result}")


        except (NotFoundError, ForbiddenError, DALError) as e:
             raise e # Re-raise specific exceptions
        except Exception as e:
            logger.error(f"DAL: Error setting message visibility for message {message_id}, user {user_id}: {e}")
            raise DALError(f"Database error while setting message visibility: {e}") from e

    # New admin methods for user management
    async def change_user_status(self, conn: pyodbc.Connection, user_id: UUID, new_status: str, admin_id: UUID) -> bool:
        """管理员禁用/启用用户账户。"""
        logger.debug(f"DAL: Admin {admin_id} attempting to change status of user {user_id} to {new_status}")
        sql = "{CALL sp_ChangeUserStatus(?, ?, ?)}"
        try:
            # Use the injected execute_query function. SP returns a single row result.
            result = await self.execute_query_func(conn, sql, (user_id, new_status, admin_id), fetchone=True)
            logger.debug(f"DAL: sp_ChangeUserStatus for user {user_id}, admin {admin_id} returned: {result}")

            if result and isinstance(result, dict):
                 error_message = result.get('') or result.get('Error') or result.get('Message')
                 result_code = result.get('OperationResultCode')

                 if error_message:
                     logger.warning(f"DAL: Change user status failed: SP returned error: {error_message}")
                     if '用户不存在。' in error_message or 'User not found.' in error_message:
                          raise NotFoundError(f"User with ID {user_id} not found.")
                     if '无权限执行此操作' in error_message or 'Only administrators can change user status.' in error_message:
                          raise ForbiddenError("只有管理员可以更改用户状态。")
                     if '无效的用户状态' in error_message or 'Invalid user status.' in error_message:
                          raise ValueError("无效的用户状态，状态必须是 Active 或 Disabled。") # Use ValueError for bad input value

                     raise DALError(f"Stored procedure error changing user status: {error_message}")

                 if result_code is not None and result_code != 0:
                      logger.warning(f"DAL: sp_ChangeUserStatus for user {user_id}, admin {admin_id} returned non-zero result code: {result_code}. Result: {result}")
                      raise DALError(f"Stored procedure failed with result code: {result_code}")

                 if '用户状态更新成功。' in result.values() or 'User status updated successfully.' in result.values():
                      logger.info(f"DAL: User {user_id} status changed to {new_status} by admin {admin_id}")
                      return True
                 else:
                      logger.warning(f"DAL: sp_ChangeUserStatus for user {user_id}, admin {admin_id} returned ambiguous success indicator: {result}")
                      return True

            # If result is None or not a dict
            logger.warning(f"DAL: sp_ChangeUserStatus for user {user_id}, admin {admin_id} returned unexpected result: {result}")
            raise DALError(f"Database error while changing user status: {result}")


        except (NotFoundError, ForbiddenError, ValueError, DALError) as e:
             raise e # Re-raise specific exceptions
        except Exception as e:
            logger.error(f"DAL: Error changing user status for user {user_id}, admin {admin_id}: {e}")
            raise DALError(f"Database error while changing user status: {e}") from e

    async def adjust_user_credit(self, conn: pyodbc.Connection, user_id: UUID, credit_adjustment: int, admin_id: UUID, reason: str) -> bool:
        """管理员手动调整用户信用分。"""
        logger.debug(f"DAL: Admin {admin_id} attempting to adjust credit for user {user_id} by {credit_adjustment} with reason: {reason}")
        sql = "{CALL sp_AdjustUserCredit(?, ?, ?, ?)}"
        try:
            # Use the injected execute_query function. SP returns a single row result.
            result = await self.execute_query_func(conn, sql, (user_id, credit_adjustment, admin_id, reason), fetchone=True)
            logger.debug(f"DAL: sp_AdjustUserCredit for user {user_id}, admin {admin_id} returned: {result}")

            if result and isinstance(result, dict):
                 error_message = result.get('') or result.get('Error') or result.get('Message')
                 result_code = result.get('OperationResultCode')

                 # Check for known error messages first
                 if error_message:
                      logger.warning(f"DAL: sp_AdjustUserCredit for user {user_id}, admin {admin_id}: SP returned message: {error_message}") # Log as message
                      if '用户未找到。' in error_message:
                           raise NotFoundError(f"User with ID {user_id} not found for credit adjustment.") # More specific message
                      if '无权限执行此操作' in error_message or 'Only administrators can adjust user credit.' in error_message:
                            raise ForbiddenError("只有管理员可以调整用户信用分。")
                      if '调整信用分必须提供原因。' in error_message or 'Reason for credit adjustment must be provided.' in error_message:
                            raise ValueError("调整信用分必须提供原因。")

                       # If the message is a success message but caught here, it's a logic error in the SP/DAL
                       # If it's an unknown error message, raise a generic DALError
                       # Only raise DALError if result_code is non-zero or message is clearly an unhandled error
                      if result_code is None or result_code != 0:
                           # If there's an error message AND non-zero code or no code, it's likely an error
                           raise DALError(f"Stored procedure error adjusting user credit: {error_message if error_message else f'Code: {result_code}. Result: {result}'}")

                 # If no error message, assume success if result is a dictionary and result_code is 0 or absent.
                 # The SP is expected to return a dictionary like {'OperationResultCode': 0, '': '成功消息'} on success.
                 # We don't need to check OperationResultCode specifically here if the error message checks handle failures.
                 if result_code is None or result_code == 0:
                      logger.info(f"DAL: Credit adjusted successfully for user ID: {user_id}")
                      return True # Indicate success
                 else:
                      # If there's an unhandled error message or a non-zero result code, raise generic DALError
                      raise DALError(f"Stored procedure error adjusting user credit: {error_message if error_message else f'Code: {result_code}. Result: {result}'}")

            # If result is None or not a dict, it's an unexpected scenario.
            logger.error(
                f"DAL: sp_AdjustUserCredit for user {user_id} returned unexpected result: {result}")
            raise DALError("Credit adjustment failed: Unexpected response from database.")

        except (NotFoundError, ForbiddenError, ValueError, DALError) as e:
             # Re-raise known errors
             raise e
        except Exception as e:
             logger.error(f"DAL: Unexpected error adjusting user credit for user {user_id}: {e}")
             raise DALError(f"Database error during user credit adjustment: {e}") from e

    async def get_all_users(self, conn: pyodbc.Connection, admin_id: UUID) -> list[dict]:
        """DAL: 管理员获取所有用户列表。"""
        logger.debug(f"DAL: Attempting to get all users by admin {admin_id}")
        sql = "{CALL sp_GetAllUsers(?)}"
        try:
            results = await self.execute_query_func(conn, sql, (admin_id,), fetchall=True)
            logger.debug(f"DAL: sp_GetAllUsers returned {len(results) if results else 0} users.")
            return results
        except Exception as e:
            logger.error(f"DAL: Error getting all users: {e}")
            raise DALError(f"Failed to get all users: {e}") from e

    async def update_user_staff_status(self, conn: pyodbc.Connection, user_id: UUID, new_is_staff: bool, admin_id: UUID) -> bool:
        """DAL: 更新用户的staff状态。"""
        logger.debug(f"DAL: Attempting to update staff status for user {user_id} to {new_is_staff} by admin {admin_id}")
        sql = "{CALL sp_UpdateUserStaffStatus(?, ?, ?)}"
        try:
            # sp_UpdateUserStaffStatus returns 1 for success, -1 if user not found, -2 if admin not found/not super admin
            result = await self.execute_query_func(conn, sql, (user_id, new_is_staff, admin_id), fetchone=True)
            logger.debug(f"DAL: sp_UpdateUserStaffStatus returned: {result}")
            
            # 检查存储过程是否返回成功消息
            if result and isinstance(result, dict) and result.get('消息') == '用户管理员状态更新成功':
                 logger.info(f"DAL: Staff status updated successfully for user {user_id}.")
                 return True
            
            # 处理存储过程返回的错误消息（如果存在）
            error_message = result.get('消息')
            if error_message:
                if '只有超级管理员才能修改用户的管理员状态。' in error_message:
                    raise PermissionError("只有超级管理员才能更改用户管理员状态。")
                elif '要修改的用户不存在。' in error_message:
                    raise NotFoundError(f"User with ID {user_id} not found.")
                elif '未能更新用户管理员状态，可能用户ID不正确或状态未改变。' in error_message:
                    raise DALError(f"Failed to update staff status for user {user_id}: {error_message}")
                else:
                    # 对于其他未预期的错误消息，抛出通用DALError
                    logger.error(f"DAL: Unexpected error message from sp_UpdateUserStaffStatus: {error_message}")
                    raise DALError(f"Failed to update staff status for user {user_id}: {error_message}")
            else:
                 # Log unexpected result and raise a generic error if no specific message
                 logger.error(f"DAL: Unexpected result from sp_UpdateUserStaffStatus: {result}")
                 raise DALError(f"Failed to update staff status for user {user_id}: Unexpected response from database.")

        except (pyodbc.ProgrammingError, pyodbc.IntegrityError) as e:
            logger.error(f"DAL: Database error updating staff status for user {user_id}: {e}")
            raise DALError(f"Database error updating staff status for user {user_id}: {e}") from e
        except Exception as e:
            logger.error(f"DAL: Unexpected error updating staff status for user {user_id}: {e}")
            raise DALError(f"Failed to update staff status for user {user_id}: {e}") from e

    async def get_user_by_email_with_password(self, conn: pyodbc.Connection, email: str) -> dict | None:
        """DAL: 根据邮箱获取用户（包括密码哈希）。"""
        logger.debug(f"DAL: Attempting to get user by email {email}")
        sql = "{CALL sp_GetUserByEmailWithPassword(?)}"
        try:
            result = await self.execute_query_func(conn, sql, (email,), fetchone=True)
            logger.debug(f"DAL: sp_GetUserByEmailWithPassword returned: {result}")
            return result
        except Exception as e:
            logger.error(f"DAL: Error getting user by email {email}: {e}")
            raise DALError(f"Failed to get user by email {email}: {e}") from e

    async def create_otp(self, conn: pyodbc.Connection, user_id: UUID, otp_code: str, expires_at: datetime, otp_type: str) -> dict | None:
        """DAL: 为指定用户创建并存储 OTP。"""
        logger.debug(f"DAL: Attempting to create OTP for user {user_id} with type {otp_type}")
        sql = "{CALL sp_CreateOtpForPasswordReset(?, ?, ?, ?)}"
        try:
            result = await self.execute_query_func(conn, sql, (user_id, otp_code, expires_at, otp_type), fetchone=True)
            logger.debug(f"DAL: sp_CreateOtpForPasswordReset returned: {result}")
            logger.debug(f"DAL: Full raw result from SP in create_otp: {result}") # Added for deeper debugging

            if result and isinstance(result, dict):
                if '操作结果代码' not in result: # Explicitly check if the key exists
                    logger.warning(f"DAL: '操作结果代码' key missing in SP result for create_otp: {result}")
                    raise DALError("Stored procedure result missing '操作结果代码' key.")

                operation_result_code = result.get('操作结果代码') # Changed key to '操作结果代码'
                debug_message = result.get('消息')

                # Ensure operation_result_code is an integer for robust comparison
                if operation_result_code is not None:
                    try:
                        operation_result_code = int(operation_result_code)
                    except ValueError:
                        logger.error(f"DAL: Could not convert OperationResultCode to int: {operation_result_code}")
                        operation_result_code = -999 # Assign a non-zero value to trigger error handling
                
                logger.debug(f"DAL: In create_otp, operation_result_code after conversion: {operation_result_code}, type: {type(operation_result_code)}")
                
                if operation_result_code == 0:
                    logger.info(f"DAL: OTP created successfully for user {user_id}.")
                    return result
                elif operation_result_code == -1:
                    raise NotFoundError(f"User with ID {user_id} not found for OTP creation.")
                else: # This will now catch any non-zero or invalid integer codes, including -99 (from CATCH block in SP)
                    raise DALError(f"Stored procedure error creating OTP: {debug_message}")
            
            logger.error(f"DAL: sp_CreateOtpForPasswordReset returned unexpected result: {result}")
            raise DALError("Failed to create OTP: Unexpected database response.")

        except (NotFoundError, DALError) as e:
            raise e
        except Exception as e:
            logger.error(f"DAL: Error creating OTP for user {user_id}: {e}")
            raise DALError(f"Database error creating OTP: {e}") from e

    async def get_otp_details(self, conn: pyodbc.Connection, email: str, otp_code: str) -> dict | None:
        """DAL: 根据邮箱和 OTP 获取 OTP 详情并验证有效性。"""
        logger.debug(f"DAL: Attempting to get OTP details for email {email} with code {otp_code}")
        sql = "{CALL sp_GetOtpDetailsAndValidate(?, ?)}"
        try:
            result = await self.execute_query_func(conn, sql, (email, otp_code), fetchone=True)
            logger.debug(f"DAL: sp_GetOtpDetailsAndValidate returned: {result}")
            
            if result and isinstance(result, dict) and '操作结果代码' in result: # Changed key to '操作结果代码'
                op_code = result.get('操作结果代码') # Get the Chinese key
                if op_code is not None:
                    try:
                        op_code = int(op_code) # Cast to int
                    except ValueError:
                        logger.error(f"DAL: Could not convert '操作结果代码' to int: {op_code}")
                        op_code = -999 # Default to an error code

                if op_code == -1: # Use the casted value
                    # Specific error from SP indicating invalid/expired OTP
                    return None # Indicate not found/invalid OTP
            elif result and isinstance(result, dict):
                # Valid OTP details found (if no '操作结果代码' or it's not -1)
                return result
            else:
                # Unexpected result from SP
                logger.warning(f"DAL: sp_GetOtpDetailsAndValidate returned unexpected type or None: {result}")
                return None # Treat as not found/invalid
        except Exception as e:
            logger.error(f"DAL: Error getting OTP details for email {email} with code {otp_code}: {e}")
            raise DALError(f"Database error while fetching OTP details: {e}") from e

    async def mark_otp_as_used(self, conn: pyodbc.Connection, otp_id: UUID) -> bool:
        """DAL: 标记 OTP 为已使用。"""
        logger.debug(f"DAL: Attempting to mark OTP {otp_id} as used")
        sql = "{CALL sp_MarkOtpAsUsed(?)}"
        try:
            result = await self.execute_query_func(conn, sql, (otp_id,), fetchone=True)
            logger.debug(f"DAL: sp_MarkOtpAsUsed returned: {result}")

            if result and isinstance(result, dict):
                operation_result_code = result.get('操作结果代码') # Changed key to '操作结果代码'
                debug_message = result.get('消息')

                # Ensure operation_result_code is an integer for robust comparison
                if operation_result_code is not None:
                    try:
                        operation_result_code = int(operation_result_code)
                    except ValueError:
                        logger.error(f"DAL: Could not convert OperationResultCode to int: {operation_result_code}")
                        operation_result_code = -999 # Assign a non-zero value to trigger error handling

                if operation_result_code == 0:
                    logger.info(f"DAL: OTP {otp_id} successfully marked as used.")
                    return True
                elif operation_result_code == -1:
                    logger.warning(f"DAL: OTP {otp_id} not found or already used when marking as used. Debug: {debug_message}")
                    return False # Not found or already used
                else:
                    raise DALError(f"Stored procedure error marking OTP as used: {debug_message}")
            
            logger.error(f"DAL: sp_MarkOtpAsUsed returned unexpected result: {result}")
            raise DALError("Failed to mark OTP as used: Unexpected database response.")

        except DALError as e:
            raise e
        except Exception as e:
            logger.error(f"DAL: Error marking OTP {otp_id} as used: {e}")
            raise DALError(f"Database error marking OTP as used: {e}") from e

    async def update_user_last_login_time(self, conn: pyodbc.Connection, user_id: UUID) -> bool:
        """更新用户的最后登录时间。"""
        logger.debug(f"DAL: Attempting to update last login time for user ID: {user_id}")
        sql = "{CALL sp_UpdateUserLastLoginTime(?)}"
        params = (user_id,)
        try:
            rowcount = await self.execute_query_func(conn, sql, params, fetchone=False, fetchall=False)
            if rowcount == 0:
                logger.warning(f"DAL: Update last login time for user {user_id} returned 0 rows affected, user not found.")
                return False
            logger.info(f"DAL: User {user_id} last login time updated successfully.")
            return True
        except Exception as e:
            logger.error(f"DAL: Error updating last login time for user {user_id}: {e}")
            raise DALError(f"Database error updating last login time: {e}") from e 