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

            # 2. 优先检查是否包含 NewUserID (Assuming this is the primary success indicator from SP)
            new_user_id = result.get('NewUserID')

            if new_user_id:
                 # If NewUserID is present, consider it success and proceed to validation and fetching full info.
                 # Message field is ignored as an error in this case.

                 # 3. Validate NewUserID is a valid UUID string or UUID object
                 if not isinstance(new_user_id, UUID):
                      try:
                          # Attempt to convert to UUID object
                          new_user_id = UUID(str(new_user_id))
                      except (ValueError, TypeError) as e:
                           logger.error(
                               f"DAL: Returned NewUserID is not a valid UUID: {new_user_id}. Error: {e}")
                           raise DALError(
                               f"User creation failed: Invalid User ID format returned: {new_user_id}") from e

                 logger.info(
                     f"DAL: User {username} created with NewUserID: {new_user_id}. Fetching full info.")

                 # 4. 获取完整用户信息 using the created ID
                 # This step is necessary to return the full UserResponseSchema as expected by the service/router
                 full_user_info = await self.get_user_by_id(conn, new_user_id)
                 logger.debug(
                     f"DAL: get_user_by_id for new user {new_user_id} returned: {full_user_info}")

                 if not full_user_info:
                     # This indicates a subsequent read failed right after creation
                     logger.error(
                         f"DAL: Failed to retrieve full user info after creation for ID: {new_user_id}")
                     raise DALError(
                         f"Failed to retrieve full user info after creation for ID: {new_user_id}")

                 logger.info(f"DAL: Full info retrieved for new user: {username}")
                 return full_user_info  # Return the fetched dictionary

            else:
                # If NewUserID is NOT present, check for explicit error messages or result codes.

                # 5. 检查错误消息或操作结果码
                error_message = result.get('Error') or result.get(
                    'Message') or result.get('')
                # Assuming SP might return this
                result_code = result.get('OperationResultCode')

                # Check for error messages from SP
                if error_message:
                    logger.debug(
                        f"DAL: sp_CreateUser for {username} returned message: {error_message}")
                    if '用户名已存在' in error_message or 'Duplicate username' in error_message:
                        logger.warning(f"DAL: Username {username} already exists")
                        raise IntegrityError("Username already exists.")
                    elif '手机号码已存在' in error_message or '手机号已存在' in error_message or 'Duplicate phone' in error_message:
                        logger.warning(
                            f"DAL: Phone number {phone_number} already exists")
                        raise IntegrityError("Phone number already exists.")
                    # Handle other potential SP-specific errors
                    logger.error(
                        f"DAL: Stored procedure error during user creation: {error_message}")
                    raise DALError(
                        f"Stored procedure error during user creation: {error_message}")

                # Check result code if available and no explicit error message
                if result_code is not None:
                     if result_code != 0:  # Assuming 0 is success
                          logger.error(
                              f"DAL: sp_CreateUser for {username} returned non-zero result code: {result_code}. Result: {result}")
                          # Map result code to specific error if possible, otherwise raise generic DALError
                          # Example: User already exists (though messages above should catch this)
                          if result_code == -1:
                               raise IntegrityError(
                                   "User already exists (code -1).")
                          else:
                               raise DALError(
                                   f"Stored procedure failed with result code: {result_code}")

            # 3. 检查是否包含 NewUserID (Assuming this is the primary success indicator from SP)
            new_user_id = result.get('NewUserID')
            if not new_user_id:
                # This could happen if SP executed without explicit error but didn't return the ID as expected
                logger.error(
                    f"DAL: sp_CreateUser for {username} completed but did not return NewUserID. Result: {result}")
                raise DALError(
                    "User creation failed: User ID not returned from database.")

            # 4. Validate NewUserID is a valid UUID string or UUID object
            if not isinstance(new_user_id, UUID):
                 try:
                     # Attempt to convert to UUID object
                     new_user_id = UUID(str(new_user_id))
                 except (ValueError, TypeError) as e:
                      logger.error(
                          f"DAL: Returned NewUserID is not a valid UUID: {new_user_id}. Error: {e}")
                      raise DALError(
                          f"User creation failed: Invalid User ID format returned: {new_user_id}") from e

            logger.info(
                f"DAL: User {username} created with NewUserID: {new_user_id}. Fetching full info.")

            # 5. 获取完整用户信息 using the created ID
            # This step is necessary to return the full UserResponseSchema as expected by the service/router
            full_user_info = await self.get_user_by_id(conn, new_user_id)
            logger.debug(
                f"DAL: get_user_by_id for new user {new_user_id} returned: {full_user_info}")

            if not full_user_info:
                # This indicates a subsequent read failed right after creation
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
        """Deletes a user by their ID using sp_DeleteUser, processing a single combined debug and result code output."""
        logger.info(f"DAL: Attempting to delete user with ID: {user_id}")

        try:
            # Use the injected execute_query function
            # sp_DeleteUser returns a single row result containing OperationResultCode and Debug_Message.
            result_data = await self.execute_query_func(conn, "{CALL sp_DeleteUser(?)}", (user_id,), fetchone=True)

            logger.debug(
                f"DAL: sp_DeleteUser for user {user_id} returned: {result_data}")

            # Process the single result row
            if result_data and isinstance(result_data, dict):
                # Access OperationResultCode from the constructed dictionary
                operation_result_code = result_data.get(
                    'OperationResultCode') if result_data and isinstance(result_data, dict) else None
                debug_message = result_data.get('Debug_Message') if result_data and isinstance(
                    result_data, dict) else "No debug message available."

                if operation_result_code == 0:
                    # conn.commit() # Commit handled by execute_query implicitly if commit=True
                    logger.info(
                        f"DAL: User {user_id} deleted successfully (OperationResultCode: 0).")
                    return True
                elif operation_result_code == -1:
                    logger.warning(
                        f"DAL: User {user_id} not found by sp_DeleteUser (OperationResultCode: -1). Debug: {debug_message}")
                    # conn.rollback() # Rollback handled by execute_query implicitly on error/non-commit
                    raise NotFoundError(
                        f"User with ID {user_id} not found for deletion.")
                elif operation_result_code == -2:
                    logger.warning(
                        f"DAL: User {user_id} could not be deleted due to dependencies (OperationResultCode: -2). Debug: {debug_message}")
                    # conn.rollback()
                    # Raise a specific error for dependencies, or a generic Forbidden/DAL error
                    raise ForbiddenError(
                        f"Cannot delete user with ID {user_id} due to existing dependencies.")
                elif operation_result_code == -3:
                    logger.warning(
                        f"DAL: User {user_id} was found but DELETE operation failed (OperationResultCode: -3). Debug: {debug_message}")
                    # conn.rollback()
                    raise DALError(
                        f"Database failed to delete user with ID {user_id} (code -3).")
                elif operation_result_code == -4:
                    logger.warning(
                        f"DAL: Database error during sp_DeleteUser's transaction (OperationResultCode: -4). Debug: {debug_message}")
                    # conn.rollback()
                    raise DALError(
                        f"Database transaction error during user deletion for ID {user_id} (code -4).")
                elif operation_result_code == -90:
                    logger.warning(
                        f"DAL: Database error during sp_DeleteUser's initial user check (OperationResultCode: -90). Debug: {debug_message}")
                    # conn.rollback()
                    raise DALError(
                        f"Database error during initial user check for ID {user_id} (code -90).")
                elif operation_result_code is None:
                     # Handle case where OperationResultCode was not found in the result
                     logger.error(
                         f"DAL: sp_DeleteUser for user {user_id} returned result data but no OperationResultCode. Result: {result_data}")
                     # conn.rollback()
                     raise DALError(
                         f"Database error during user deletion: Missing result code. Result: {result_data}")
                else:
                    logger.warning(
                        f"DAL: sp_DeleteUser for user {user_id} returned an unexpected OperationResultCode: {operation_result_code}. Debug: {debug_message}. Rolling back.")
                    # conn.rollback()
                    raise DALError(
                        f"Database error during user deletion: Unexpected result code {operation_result_code}. Debug: {debug_message}")

        except (NotFoundError, ForbiddenError, DALError) as e:
             # Catch and re-raise specific exceptions raised above
             logger.error(
                 f"DAL: Specific error during user deletion for {user_id}: {e}")
             # Rollback is handled by execute_query implicitly on exception
             raise e
        except pyodbc.Error as e:
            logger.error(
                f"DAL: Database error during user deletion for {user_id}: {e}")
            # Rollback is handled by execute_query implicitly on exception
            raise DALError(f"Database error during user deletion: {e}") from e
        except Exception as ex:
            logger.error(
                f"DAL: Unexpected Python error during user deletion for {user_id}: {ex}")
            # Rollback is handled by execute_query implicitly on exception
            raise DALError(
                f"Unexpected server error during user deletion: {ex}") from ex
        # No finally block needed for cursor close if using execute_query as it manages cursor.

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
            
            if result and isinstance(result, dict) and result.get('OperationResultCode') == 1:
                 logger.info(f"DAL: Staff status updated successfully for user {user_id}.")
                 return True
            
            # Handle sp specific error codes
            error_code = result.get('OperationResultCode')
            if error_code == -1:
                raise NotFoundError(f"User with ID {user_id} not found.")
            elif error_code == -2:
                 raise PermissionError(f"Admin with ID {admin_id} not authorized or not found.") # Use PermissionError for authorization issues
            else:
                 # Log unexpected result and raise a generic error
                 logger.error(f"DAL: Unexpected result from sp_UpdateUserStaffStatus: {result}")
                 raise DALError(f"Failed to update staff status for user {user_id}: Unexpected result code {error_code}")

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

            if result and isinstance(result, dict):
                operation_result_code = result.get('OperationResultCode')
                debug_message = result.get('Debug_Message')

                if operation_result_code == 0:
                    logger.info(f"DAL: OTP created successfully for user {user_id}.")
                    return result
                elif operation_result_code == -1:
                    raise NotFoundError(f"User with ID {user_id} not found for OTP creation.")
                else:
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
            
            if result and isinstance(result, dict) and 'OperationResultCode' in result and result['OperationResultCode'] == -1:
                # Specific error from SP indicating invalid/expired OTP
                return None # Indicate not found/invalid OTP
            elif result and isinstance(result, dict):
                # Valid OTP details found
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
                operation_result_code = result.get('OperationResultCode')
                debug_message = result.get('Debug_Message')

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