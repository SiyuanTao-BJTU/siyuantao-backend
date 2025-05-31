# app/services/user_service.py
import pyodbc
from uuid import UUID
from typing import Optional, Callable, Awaitable, List, Dict
import logging
import re # Import regex for email validation
import uuid
import random
import os # Import os for path manipulation

logger = logging.getLogger(__name__) # Initialize logger

from app.dal.user_dal import UserDAL # Import the UserDAL class
from app.schemas.user_schemas import UserRegisterSchema, UserLoginSchema, UserProfileUpdateSchema, UserPasswordUpdate, UserStatusUpdateSchema, UserCreditAdjustmentSchema, UserResponseSchema, RequestVerificationEmail, VerifyEmail # Import necessary schemas
from app.utils.auth import get_password_hash, verify_password, create_access_token # Importing auth utilities
from app.exceptions import NotFoundError, IntegrityError, DALError, AuthenticationError, ForbiddenError, EmailSendingError # Import necessary exceptions
from datetime import timedelta # Needed for token expiry
from app.config import settings # Import settings object
from datetime import datetime # Import datetime for data conversion
from app.utils.email_sender import send_email # Import the generic email sender

# Get the base directory of the current file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the templates directory
EMAIL_TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates", "emails")

# Removed direct instantiation of DAL
# user_dal = UserDAL()

# Encapsulate Service functions within a class
class UserService:
    def __init__(self, user_dal: UserDAL, email_sender: Optional[Callable[[str, str, str], Awaitable[None]]] = None):
        self.user_dal = user_dal
        self.email_sender = email_sender or send_email # Use the generic send_email as default

    async def create_user(self, conn: pyodbc.Connection, user_data: UserRegisterSchema) -> UserResponseSchema:
        """创建新用户。

        Args:
            conn: 数据库连接对象。
            user_data: 用户注册数据 Pydantic Schema。

        Returns:
            新创建用户的 UserResponseSchema。

        Raises:
            IntegrityError: 如果用户名或手机号已存在。
            DALError: 如果发生其他数据库错误。
        """
        logger.info(f"Attempting to create user: {user_data.username}") # Add logging

        hashed_password = get_password_hash(user_data.password)
        logger.debug(f"Password hashed for {user_data.username}") # Add logging

        try:
            # Call DAL to create user
            logger.debug(f"Calling DAL.create_user for {user_data.username}") # Add logging
            created_user = await self.user_dal.create_user(
                conn,
                user_data.username,
                hashed_password,
                user_data.phone_number,
                major=user_data.major
            )
            logger.debug(f"DAL.create_user returned: {created_user}") # Add logging

            # After successful creation in DAL, fetch the complete user profile
            # This is needed to populate all fields for UserResponseSchema, including default values etc.
            # Assuming DAL.create_user returns the dictionary representation of the created user.
            # If DAL.create_user only returns ID, we would need get_user_profile_by_id here.

            # Convert the DAL dictionary result to a dictionary matching UserResponseSchema keys
            logger.debug(f"Converting DAL user data to schema for {user_data.username}") # Add logging
            converted_user_data = self._convert_dal_user_to_schema(created_user) # Convert DAL dict to schema dict
            logger.debug(f"Converted user data: {converted_user_data}") # Add logging

            logger.info(f"User created successfully: {user_data.username}") # Add logging
            return converted_user_data # Return the converted dict

        except (IntegrityError, NotFoundError) as e:
            # Re-raise specific exceptions from DAL
            logger.error(f"IntegrityError or NotFoundError during user creation for {user_data.username}: {e}") # Add logging
            raise e
        except DALError as e:
            # Wrap general DAL errors in a Service layer error with more context
            logger.error(f"Database error during user creation for {user_data.username}: {e}") # Add logging
            raise DALError(f"Database error during user creation: {e}") from e # Wrap and re-raise
        except Exception as e:
            # Catch any other unexpected errors
            logger.error(f"Unexpected error during user creation for {user_data.username}: {e}") # Add logging
            raise e # Re-raise other unexpected errors

    async def authenticate_user_and_create_token(self, conn: pyodbc.Connection, password: str, username: Optional[str] = None, email: Optional[str] = None) -> str:
        """
        Service layer function to authenticate a user by username or email and generate a JWT token.
        Calls DAL to get user, verifies password, checks status, and creates token.
        """
        logger.info(f"Attempting to authenticate user: username={username}, email={email}") # Add logging

        user = None
        if username:
             # 1a. Call DAL to get user with password hash by username
             logger.debug(f"Calling DAL.get_user_by_username_with_password for username {username}") # Add logging
             user = await self.user_dal.get_user_by_username_with_password(conn, username)
             logger.debug(f"DAL.get_user_by_username_with_password returned: {user}") # Add logging
        elif email:
             # 1b. Call DAL to get user with password hash by email
             logger.debug(f"Calling DAL.get_user_by_email_with_password for email {email}") # Add logging
             user = await self.user_dal.get_user_by_email_with_password(conn, email)
             logger.debug(f"DAL.get_user_by_email_with_password returned: {user}") # Add logging

        if not user:
            # User not found by either username or email
            logger.warning(f"Authentication failed: User not found for username={username}, email={email}") # Add logging
            raise AuthenticationError("用户名/邮箱或密码不正确")

        # 2. Verify password
        stored_password_hash = user.get('Password')
        logger.debug(f"Verifying password for user: {username}") # Add logging
        if not stored_password_hash or not verify_password(password, stored_password_hash):
            # Password doesn't match
            logger.warning(f"Authentication failed: Incorrect password for user {username}.") # Add logging
            raise AuthenticationError("用户名或密码不正确")

        # 3. Check user status (e.g., Disabled) - Business logic in Service
        logger.debug(f"Checking status for user: {username} (Status: {user.get('Status')})") # Add logging
        if user.get('Status') == 'Disabled':
            logger.warning(f"Authentication failed: Account for user {username} is disabled.") # Add logging
            raise ForbiddenError("账户已被禁用") # Raise a specific exception

        # TODO: Check if user is verified if verification is required for login
        # if not user.get('IsVerified') and require_verification:
        #     raise ForbiddenError("邮箱未验证，请先验证邮箱")

        # 4. Create JWT Token
        logger.debug(f"Creating JWT token for user: {username}") # Add logging
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        # Use user data (like UserID, IsStaff) to create the token payload
        # Ensure UserID is correctly accessed from the user dict returned by DAL
        user_id = user.get('UserID') # Assuming DAL returns 'UserID'
        is_staff = user.get('IsStaff', False) # Assuming DAL returns 'IsStaff'
        is_verified = user.get('IsVerified', False) # Assuming DAL returns 'IsVerified'
        is_super_admin = user.get('IsSuperAdmin', False) # Get IsSuperAdmin from DAL result

        if not user_id:
             # This should not happen if DAL works correctly
             logger.error(f"DAL error: UserID missing for {username} after fetching.") # Add logging
             raise DALError("Failed to retrieve UserID for token creation after authentication.")

        access_token = create_access_token(
            data={
                "user_id": str(user_id), # Ensure user_id is string in token
                "is_staff": is_staff,
                "is_verified": is_verified, # Include verification status in token
                "is_super_admin": is_super_admin # Include super admin status in token
            },
            expires_delta=access_token_expires
        )
        logger.info(f"Authentication successful, token created for user: {username}") # Add logging
        return access_token # Return the token string

    async def get_user_profile_by_id(self, conn: pyodbc.Connection, user_id: UUID) -> UserResponseSchema:
        """
        Service layer function to get user profile by ID.
        Handles NotFoundError from DAL.
        """
        logger.info(f"Attempting to get user profile by ID: {user_id}") # Add logging
        # Pass the connection to the DAL method
        user = await self.user_dal.get_user_by_id(conn, user_id)
        logger.debug(f"DAL.get_user_by_id returned: {user}") # Add logging
        if not user:
            logger.warning(f"User profile not found for ID: {user_id}") # Add logging
            raise NotFoundError(f"User with ID {user_id} not found.")
        
        # Convert DAL response keys to match UserResponseSchema
        logger.debug(f"Converting DAL user data to schema for ID: {user_id}") # Add logging
        return self._convert_dal_user_to_schema(user) # Return the converted dict

    async def update_user_profile(self, conn: pyodbc.Connection, user_id: UUID, user_update_data: UserProfileUpdateSchema) -> UserResponseSchema:
        """
        Service layer function to update user profile.
        """
        logger.info(f"Attempting to update profile for user ID: {user_id}")
        # Filter out None values from the update data to avoid unnecessary updates
        update_data = user_update_data.model_dump(exclude_none=True)

        if not update_data:
            logger.info(f"No update data provided for user ID: {user_id}")
            # If no data to update, just return the current profile
            return await self.get_user_profile_by_id(conn, user_id)

        try:
            logger.debug(f"Calling DAL.update_user_profile for user ID: {user_id} with data: {update_data}")
            updated_dal_user = await self.user_dal.update_user_profile(conn, user_id, **update_data)
            logger.debug(f"DAL.update_user_profile returned: {updated_dal_user}")

            if not updated_dal_user:
                 # This could happen if the user_id was not found in DAL update
                 logger.warning(f"User not found during profile update for ID: {user_id}")
                 raise NotFoundError(f"User with ID {user_id} not found for update.")
            
            logger.debug(f"Converting updated DAL user data to schema for user ID: {user_id}")
            return self._convert_dal_user_to_schema(updated_dal_user)

        except (IntegrityError, NotFoundError) as e:
            logger.error(f"IntegrityError or NotFoundError during profile update for user ID {user_id}: {e}")
            raise e
        except DALError as e:
            logger.error(f"Database error during profile update for user ID {user_id}: {e}")
            raise DALError(f"Database error during profile update: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during profile update for user ID {user_id}: {e}")
            raise e

    async def update_user_password(self, conn: pyodbc.Connection, user_id: UUID, password_update_data: UserPasswordUpdate) -> bool:
        """
        Service layer function to update user password.
        Verifies old password and updates with new hashed password.
        """
        logger.info(f"Attempting to update password for user ID: {user_id}")
        
        # 1. Get current password hash from DAL
        logger.debug(f"Calling DAL.get_user_password_hash_by_id for user ID: {user_id}")
        stored_password_hash = await self.user_dal.get_user_password_hash_by_id(conn, user_id)
        logger.debug(f"DAL.get_user_password_hash_by_id returned hash: {stored_password_hash}")

        if not stored_password_hash:
            logger.warning(f"User not found during password update for ID: {user_id}")
            raise NotFoundError(f"User with ID {user_id} not found.")

        # 2. Verify old password
        logger.debug(f"Verifying old password for user ID: {user_id}")
        if not verify_password(password_update_data.old_password, stored_password_hash):
            logger.warning(f"Password update failed: Incorrect old password for user ID {user_id}.") # Add logging
            raise AuthenticationError("旧密码不正确") # Use AuthenticationError for incorrect password

        # 3. Hash new password
        new_hashed_password = get_password_hash(password_update_data.new_password)
        logger.debug(f"New password hashed for user ID: {user_id}")

        # 4. Update password in DAL
        logger.debug(f"Calling DAL.update_user_password for user ID: {user_id}")
        update_success = await self.user_dal.update_user_password(conn, user_id, new_hashed_password)
        logger.debug(f"DAL.update_user_password returned: {update_success}")

        if not update_success:
             # This could happen if DAL reported no rows affected (user not found etc.), though NotFoundError above should cover user not found on hash retrieval.
             # This might indicate a DAL issue or a race condition.
             logger.error(f"DAL reported password update failed for user ID: {user_id}")
             # Re-fetch user to check existence? Or raise a specific DAL error?
             raise DALError(f"Failed to update password in database for user ID: {user_id}")
             
        logger.info(f"Password updated successfully for user ID: {user_id}")
        return True # Return True on successful update

    async def delete_user(self, conn: pyodbc.Connection, user_id: UUID) -> bool:
        """
        Service layer function to delete a user.
        """
        logger.info(f"Attempting to delete user with ID: {user_id}")
        try:
            # Call DAL to delete user
            logger.debug(f"Calling DAL.delete_user for user ID: {user_id}")
            delete_success = await self.user_dal.delete_user(conn, user_id)
            logger.debug(f"DAL.delete_user returned: {delete_success}")

            if not delete_success:
                logger.warning(f"User deletion failed or user not found for ID: {user_id}")
                # 根据 sp_DeleteUser 的返回码决定抛出哪种异常
                # -1: 用户未找到
                # -2: 存在依赖，无法删除
                # 其他负数: 数据库错误
                if delete_success == -1: # Assuming -1 means user not found
                     raise NotFoundError(f"User with ID {user_id} not found for deletion.")
                elif delete_success == -2: # Assuming -2 means dependencies exist
                     raise IntegrityError(f"User with ID {user_id} cannot be deleted due to existing active products or orders. Please ensure all related products are sold/withdrawn and orders are completed/cancelled.")
                else: # Other DAL errors
                     raise DALError(f"Database error during user deletion for user ID {user_id}.")

            logger.info(f"User deleted successfully: {user_id}")
            return True
        except (NotFoundError, IntegrityError, DALError) as e:
            logger.error(f"Error during user deletion for ID {user_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during user deletion for ID {user_id}: {e}")
            raise e
    
    async def toggle_user_staff_status(self, conn: pyodbc.Connection, target_user_id: UUID, super_admin_id: UUID) -> bool:
        """
        Service layer function for a super admin to toggle a user's staff status.
        Only a super admin can make another user a staff member or revoke staff status.
        """
        logger.info(f"Super admin {super_admin_id} attempting to toggle staff status for user {target_user_id}.")
        try:
            # 1. Check if the super_admin_id is indeed a super admin
            super_admin_profile = await self.user_dal.get_user_by_id(conn, super_admin_id)
            if not super_admin_profile or not super_admin_profile.get('是否超级管理员'):
                logger.warning(f"Unauthorized attempt: User {super_admin_id} is not a super admin.")
                raise ForbiddenError("只有超级管理员才能更改用户管理员状态。")

            # 2. Get the target user's current status and IsStaff status
            target_user_profile = await self.user_dal.get_user_by_id(conn, target_user_id)
            if not target_user_profile:
                logger.warning(f"Target user {target_user_id} not found for staff status toggle.")
                raise NotFoundError(f"User with ID {target_user_id} not found.")

            current_is_staff = target_user_profile.get('是否管理员', False)
            new_is_staff_status = not current_is_staff # Toggle the status

            # Prevent a super admin from revoking their own super admin status via this method
            # This method only toggles IsStaff, not IsSuperAdmin.
            # A super admin might want to toggle their own IsStaff if they also hold that role.
            # However, direct super admin role removal should be separate.
            if target_user_id == super_admin_id and target_user_profile.get('是否超级管理员'):
                logger.warning(f"Super admin {super_admin_id} attempted to toggle their own staff status. Not allowed for super admins via this route.")
                raise ForbiddenError("超级管理员不能通过此操作修改自己的管理员状态。") # Specific error

            # 3. Call DAL to update the IsStaff status
            update_success = await self.user_dal.update_user_staff_status(conn, target_user_id, new_is_staff_status, super_admin_id)

            if not update_success:
                logger.error(f"Failed to toggle staff status for user {target_user_id} in DAL.")
                raise DALError(f"数据库操作失败：无法更新用户 {target_user_id} 的管理员状态。")

            logger.info(f"Super admin {super_admin_id} successfully toggled staff status for user {target_user_id} to {new_is_staff_status}.")
            return True

        except (NotFoundError, ForbiddenError, DALError) as e:
            logger.error(f"Error toggling staff status for user {target_user_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error toggling staff status for user {target_user_id}: {e}")
            raise e

    async def request_verification_email(self, conn: pyodbc.Connection, email: str, user_id: Optional[UUID] = None) -> dict:
        """
        请求发送邮箱验证 OTP。
        如果用户已登录 (user_id 提供), 则更新该用户的验证 OTP。
        如果用户未登录 (user_id 为 None) 且邮箱已存在, 则更新现有用户的验证 OTP。
        如果用户未登录且邮箱不存在, 则创建一个新用户并发送验证 OTP。
        """
        logger.info(f"Attempting to request verification OTP for email: {email}, user_id: {user_id}")

        if not re.match(r"[^@]+@bjtu\.edu\.cn$", email):
            logger.warning(f"Invalid BJTU email format for: {email}")
            raise ValueError("只允许使用北京交通大学邮箱地址进行验证 (@bjtu.edu.cn)")

        try:
            # 1. 查找用户或为新用户创建 OTP
            # 使用 DAL 的 request_verification_link 方法获取用户ID
            user_info = await self.user_dal.request_verification_link(conn, user_id, email) # This DAL method now returns UserID
            target_user_id = user_info.get('UserID')

            if not target_user_id:
                # If user not found, and it's not a new user scenario (which DAL would handle implicitly)
                # This means the email isn't registered and no user ID was generated.
                logger.warning(f"User not found for email {email} when requesting verification OTP. Returning generic success message.")
                # For security, return generic success message.
                return {"message": "如果邮箱存在，您将很快收到一封包含验证码的邮件。"}

            # 2. 生成 OTP
            otp_code = str(random.randint(100000, 999999)) # Generate a 6-digit OTP
            expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

            # 3. 存储 OTP
            await self.user_dal.create_otp(conn, target_user_id, otp_code, expires_at, 'EmailVerification')
            logger.debug(f"OTP {otp_code} created for user {target_user_id}")

            # 4. 发送包含 OTP 的邮件
            email_subject = "思源淘学生身份认证"
            
            template_path = os.path.join(EMAIL_TEMPLATES_DIR, "student_verification_email.html")
            with open(template_path, "r", encoding="utf-8") as f:
                email_body_template = f.read()
            
            email_body = email_body_template.format(otp_code=otp_code, expire_minutes=settings.OTP_EXPIRE_MINUTES)
            
            logger.debug(f"Sending verification OTP email to {email}")
            await self.email_sender(email, email_subject, email_body)
            logger.info(f"Verification OTP email sent to {email}")

            return {"message": "验证码已发送，请检查您的邮箱。", "user_id": target_user_id, "is_new_user": user_info.get('IsNewUser', False)}

        except ValueError as e:
            logger.warning(f"Value error during email request: {e}")
            raise e
        except DALError as e:
            logger.error(f"Database error during email request for {email}: {e}")
            raise e
        except EmailSendingError as e:
            logger.error(f"Failed to send verification email to {email}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during email verification request for {email}: {e}")
            raise e

    # New method to verify email with OTP
    async def verify_email_otp(self, conn: pyodbc.Connection, email: str, otp_code: str) -> dict:
        """
        Service layer function to verify email using OTP.
        """
        logger.info(f"Attempting to verify email with OTP for email: {email}")
        try:
            # 1. Get OTP details from DAL and validate
            otp_details = await self.user_dal.get_otp_details(conn, email, otp_code)

            if not otp_details:
                logger.warning(f"OTP verification failed: Invalid, expired, or used OTP for email {email}.")
                raise AuthenticationError("验证码无效或已过期，请重新获取。")
            
            user_id = otp_details.get('UserID')
            otp_id = otp_details.get('OtpID')

            if not user_id or not otp_id:
                logger.error(f"DAL error: UserID or OtpID missing from OTP details for email {email}.")
                raise DALError("Failed to retrieve user ID or OTP ID from OTP details.")

            # 2. Mark user email as verified
            await self.user_dal.verify_email(conn, user_id) # Call the updated DAL verify_email
            logger.info(f"Email marked as verified for user ID: {user_id} after OTP verification.")

            # 3. Mark OTP as used
            mark_success = await self.user_dal.mark_otp_as_used(conn, otp_id)
            if not mark_success:
                logger.warning(f"Failed to mark OTP {otp_id} as used after email verification for user {user_id}.")

            return {"user_id": user_id, "is_verified": True, "message": "邮箱验证成功。"}

        except (AuthenticationError, DALError) as e:
            logger.error(f"Error during email OTP verification for email {email}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during email OTP verification for email {email}: {e}")
            raise e

    async def get_system_notifications(self, conn: pyodbc.Connection, user_id: UUID) -> list[dict]:
        """
        获取某个用户的系统通知列表。
        """
        logger.info(f"Attempting to get system notifications for user ID: {user_id}")
        try:
            notifications = await self.user_dal.get_system_notifications_by_user_id(conn, user_id)
            logger.debug(f"DAL returned {len(notifications)} notifications for user ID: {user_id}")
            # DAL already returns dicts with PascalCase, convert to camelCase for API if needed
            # For now, assuming DAL returns keys as they are defined in SQL SP results
            return notifications
        except NotFoundError as e:
            logger.warning(f"No notifications found or user not found for ID: {user_id}")
            return [] # Return empty list if no notifications or user not found (as per DAL behavior)
        except DALError as e:
            logger.error(f"Database error getting notifications for user ID {user_id}: {e}")
            raise DALError(f"获取系统通知失败：{e}") from e
        except Exception as e:
            logger.error(f"Unexpected error getting notifications for user ID {user_id}: {e}")
            raise e

    async def mark_system_notification_as_read(self, conn: pyodbc.Connection, notification_id: UUID, user_id: UUID) -> bool:
        """
        标记系统通知为已读。
        """
        logger.info(f"Attempting to mark notification {notification_id} as read for user {user_id}")
        try:
            success = await self.user_dal.mark_notification_as_read(conn, notification_id, user_id)
            if not success:
                logger.warning(f"Failed to mark notification {notification_id} as read for user {user_id}.")
                # DAL might return False if notification not found or not owned by user, need to differentiate
                # Assuming DAL throws specific NotFoundError or ForbiddenError if applicable
                raise DALError(f"标记通知 {notification_id} 为已读失败。") # Generic error for now
            logger.info(f"Notification {notification_id} marked as read for user {user_id}.")
            return True
        except (NotFoundError, ForbiddenError, DALError) as e: # Catch specific DAL errors
            logger.error(f"Error marking notification {notification_id} as read for user {user_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error marking notification {notification_id} as read for user {user_id}: {e}")
            raise e

    async def change_user_status(self, conn: pyodbc.Connection, user_id: UUID, new_status: str, admin_id: UUID) -> bool:
        """
        Service layer function for an admin to change a user's account status.
        """
        logger.info(f"Admin {admin_id} attempting to change status of user {user_id} to {new_status}")
        try:
            # DAL method handles admin permission check and status update
            success = await self.user_dal.change_user_status(conn, user_id, new_status, admin_id)
            if not success:
                logger.warning(f"DAL reported failure changing status for user {user_id} by admin {admin_id}.")
                raise DALError(f"数据库操作失败：无法更改用户 {user_id} 的状态。")
            logger.info(f"User {user_id} status changed to {new_status} by admin {admin_id}.")
            return True
        except (ForbiddenError, NotFoundError, DALError) as e:
            logger.error(f"Error changing user status for {user_id} by admin {admin_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error changing user status for {user_id} by admin {admin_id}: {e}")
            raise e
    
    async def adjust_user_credit(self, conn: pyodbc.Connection, user_id: UUID, credit_adjustment: int, admin_id: UUID, reason: str) -> bool:
        """
        Service layer function for an admin to adjust a user's credit score.
        """
        logger.info(f"Admin {admin_id} attempting to adjust credit for user {user_id} by {credit_adjustment}.")
        try:
            # DAL method handles admin permission check and credit adjustment
            success = await self.user_dal.adjust_user_credit(conn, user_id, credit_adjustment, admin_id, reason)
            if not success:
                logger.warning(f"DAL reported failure adjusting credit for user {user_id} by admin {admin_id}.")
                raise DALError(f"数据库操作失败：无法调整用户 {user_id} 的信用分。")
            logger.info(f"User {user_id} credit adjusted by {credit_adjustment} by admin {admin_id}.")
            return True
        except (ForbiddenError, NotFoundError, DALError) as e:
            logger.error(f"Error adjusting user credit for {user_id} by admin {admin_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error adjusting user credit for {user_id} by admin {admin_id}: {e}")
            raise e

    async def get_all_users(self, conn: pyodbc.Connection, admin_id: UUID) -> list[UserResponseSchema]:
        """
        Service layer function for an admin to retrieve all user profiles.
        """
        logger.info(f"Admin {admin_id} attempting to retrieve all user profiles.")
        try:
            # DAL method handles admin permission check and fetching all users
            dal_users = await self.user_dal.get_all_users(conn, admin_id)
            logger.debug(f"DAL returned {len(dal_users)} users for admin {admin_id}.")
            
            # Convert DAL results to UserResponseSchema
            return [self._convert_dal_user_to_schema(user_data) for user_data in dal_users]
        except (ForbiddenError, DALError) as e:
            logger.error(f"Error retrieving all users by admin {admin_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error retrieving all users by admin {admin_id}: {e}")
            raise e

    async def update_user_avatar(self, conn: pyodbc.Connection, user_id: UUID, avatar_url: str) -> UserResponseSchema:
        """
        Service layer function to update a user's avatar URL.
        """
        logger.info(f"Attempting to update avatar for user ID: {user_id}")
        
        if not avatar_url:
            logger.warning(f"No avatar URL provided for user ID: {user_id}")
            raise ValueError("头像URL不能为空。")

        try:
            # Update only the avatar_url field
            updated_dal_user = await self.user_dal.update_user_profile(conn, user_id, avatar_url=avatar_url)

            if not updated_dal_user:
                logger.warning(f"User not found during avatar update for ID: {user_id}")
                raise NotFoundError(f"User with ID {user_id} not found for avatar update.")
            
            logger.info(f"Avatar updated successfully for user ID: {user_id}.")
            return self._convert_dal_user_to_schema(updated_dal_user)

        except (NotFoundError, DALError) as e:
            logger.error(f"Error updating avatar for user ID {user_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error updating avatar for user ID {user_id}: {e}")
            raise e

    def _convert_dal_user_to_schema(self, dal_user_data: dict) -> UserResponseSchema:
        """
        Converts a dictionary from DAL (e.g., SQL row) to UserResponseSchema.
        Handles key mapping from PascalCase (SQL) to snake_case (Pydantic/Python) and type conversions.
        """
        if not dal_user_data:
            return None # Or raise ValueError if an empty dict is not expected

        # Map DAL keys (PascalCase from SQL SPs) to schema keys (snake_case)
        # Ensure UUIDs and datetimes are correctly parsed if they come as strings
        # Pydantic's from_attributes should handle most of this if DAL returns correct types,
        # but explicit conversion ensures robustness.
        
        # Manually construct dict for UserResponseSchema, ensuring all fields are present
        # and types are correct.
        converted_data = {
            "user_id": dal_user_data.get("用户ID"),
            "username": dal_user_data.get("用户名"),
            "email": dal_user_data.get("邮箱"),
            "status": dal_user_data.get("账户状态"),
            "credit": dal_user_data.get("信用分"),
            "is_staff": dal_user_data.get("是否管理员", False),
            "is_super_admin": dal_user_data.get("是否超级管理员", False),
            "is_verified": dal_user_data.get("是否已认证", False),
            "major": dal_user_data.get("专业"),
            "avatar_url": dal_user_data.get("头像URL"),
            "bio": dal_user_data.get("个人简介"),
            "phone_number": dal_user_data.get("手机号码"),
            "join_time": dal_user_data.get("注册时间"),
            "last_login_time": dal_user_data.get("最后登录时间") # Added for admin view
        }

        # Validate with Pydantic schema to ensure correctness
        try:
            return UserResponseSchema(**converted_data)
        except Exception as e:
            logger.error(f"Error converting DAL user data to UserResponseSchema: {e}")
            logger.debug(f"DAL Data: {dal_user_data}")
            logger.debug(f"Converted Data: {converted_data}")
            raise ValueError(f"Failed to convert user data to response schema: {e}") from e

    async def _send_email(self, to_email: str, subject: str, body: str):
        """Default email sender function, primarily for internal use if no external sender is provided."""
        logger.info(f"Default email sender: Sending email to {to_email} with subject '{subject}'")
        try:
            await send_email(to_email, subject, body)
            logger.info(f"Default email sender: Email sent successfully to {to_email}")
        except Exception as e:
            logger.error(f"Default email sender: Failed to send email to {to_email}: {e}")
            raise EmailSendingError(f"Failed to send email to {to_email}") from e

    # New method to request password reset
    async def request_password_reset(self, conn: pyodbc.Connection, email: str) -> dict:
        """
        Service layer function to handle password reset request.
        Finds user by email, creates a reset token, and sends an email with the reset link.
        """
        logger.info(f"Attempting to initiate password reset for email: {email}")

        # 1. Find user by email
        user = await self.user_dal.get_user_by_email_with_password(conn, email)

        if not user or not user.get('UserID'):
            # User not found by email. For security, don't reveal if email exists or not.
            logger.warning(f"Password reset request for non-existent email: {email}")
            return {"message": "如果邮箱存在，您将很快收到一封包含密码重置链接的邮件。"}
            
        user_id = user['UserID']

        # 2. Generate a unique OTP (e.g., 6-digit number)
        otp_code = str(random.randint(100000, 999999)) # Generate a 6-digit OTP
        logger.debug(f"Generated OTP for email {email}: {otp_code}")

        # 3. Calculate OTP expiry time
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES) # Use new setting
        logger.debug(f"OTP for email {email} expires at: {expires_at}")

        # 4. Store OTP in the database
        try:
            logger.debug(f"Calling DAL.create_otp for user ID {user_id}")
            otp_record = await self.user_dal.create_otp(conn, user_id, otp_code, expires_at, 'PasswordReset')
            if not otp_record:
                logger.error(f"DAL.create_otp returned None for email {email}. User ID was {user_id}")
                return {"message": "如果邮箱存在，您将很快收到一封包含密码重置链接的邮件。"}
            logger.debug(f"DAL.create_otp returned: {otp_record}")

        except DALError as e:
            logger.error(f"Database error creating OTP for email {email}: {e}")
            raise DALError(f"Database error creating OTP: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error creating OTP for email {email}: {e}")
            return {"message": "如果邮箱存在，您将很快收到一封包含密码重置链接的邮件。"}

        # 5. Send email with the OTP
        try:
            subject = "思源淘 - 密码重置验证码"
            
            template_path = os.path.join(EMAIL_TEMPLATES_DIR, "password_reset_email.html")
            with open(template_path, "r", encoding="utf-8") as f:
                email_body_template = f.read()
            
            email_body = email_body_template.format(otp_code=otp_code, expire_minutes=settings.OTP_EXPIRE_MINUTES)
            
            logger.debug(f"Sending OTP email to {email}")
            await self.email_sender(email, subject, email_body)
            logger.info(f"OTP email sent to {email}")
            
        except EmailSendingError as e:
             logger.error(f"Email sending failed for OTP to {email}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending OTP email to {email}: {e}")
             
        logger.info(f"Password reset request (OTP) processed for email: {email}")
        return {"message": "如果邮箱存在，您将很快收到一封包含密码重置链接的邮件。"}

    # New method to verify OTP and reset password
    async def verify_otp_and_reset_password(self, conn: pyodbc.Connection, email: str, otp_code: str, new_password: str) -> bool:
        """
        Service layer function to verify OTP and reset user's password.
        """
        logger.info(f"Attempting to verify OTP and reset password for email: {email}")

        # 1. Get OTP details from DAL and validate
        logger.debug(f"Calling DAL.get_otp_details for email {email} and OTP {otp_code}")
        otp_details = await self.user_dal.get_otp_details(conn, email, otp_code)
        logger.debug(f"DAL.get_otp_details returned: {otp_details}")

        if not otp_details:
            logger.warning(f"OTP verification failed: Invalid, expired, or used OTP for email {email}.")
            raise AuthenticationError("验证码无效或已过期，请重新获取。")
        
        user_id = otp_details.get('UserID')
        otp_id = otp_details.get('OtpID')

        if not user_id or not otp_id:
            logger.error(f"DAL error: UserID or OtpID missing from OTP details for email {email}.")
            raise DALError("Failed to retrieve user ID or OTP ID from OTP details.")

        # 2. Hash the new password
        new_hashed_password = get_password_hash(new_password)
        logger.debug(f"New password hashed for user ID {user_id}")

        # 3. Update password in DAL
        try:
            logger.debug(f"Calling DAL.update_user_password for user ID {user_id}")
            update_success = await self.user_dal.update_user_password(conn, user_id, new_hashed_password)
            if not update_success:
                logger.error(f"Failed to update password for user {user_id} after OTP verification.")
                raise DALError("密码重置失败：无法更新用户密码。")
            logger.info(f"Password updated successfully for user ID: {user_id} after OTP verification.")
        except DALError as e:
            logger.error(f"Database error updating password after OTP verification for user {user_id}: {e}")
            raise DALError(f"数据库错误：密码重置失败。") from e
        except Exception as e:
            logger.error(f"Unexpected error updating password after OTP verification for user {user_id}: {e}")
            raise e

        # 4. Mark OTP as used in DAL
        try:
            logger.debug(f"Marking OTP {otp_id} as used.")
            mark_success = await self.user_dal.mark_otp_as_used(conn, otp_id)
            if not mark_success:
                logger.warning(f"Failed to mark OTP {otp_id} as used after password reset for user {user_id}.")
                # This is a non-critical error, password reset is successful but OTP might be reusable.
                # Decide if this should raise an error or just be logged.
        except Exception as e:
            logger.error(f"Error marking OTP {otp_id} as used: {e}")
            # Log but don't re-raise as password reset was successful.

        return True # Indicate overall success

    # New method to request OTP for passwordless login
    async def request_login_otp(self, conn: pyodbc.Connection, identifier: str) -> dict:
        """
        Service layer function to request OTP for passwordless login.
        Finds user by identifier (email or username), creates an OTP, and sends an email with the OTP.
        """
        logger.info(f"Attempting to request login OTP for identifier: {identifier}")

        user = None
        if "@" in identifier: # Simple check for email
            user = await self.user_dal.get_user_by_email_with_password(conn, identifier) # Reuse existing DAL method
        else:
            user = await self.user_dal.get_user_by_username_with_password(conn, identifier) # Reuse existing DAL method

        if not user or not user.get('UserID'):
            logger.warning(f"Login OTP request for non-existent identifier: {identifier}")
            # For security, return a generic success message even if user not found
            return {"message": "如果账户存在，您将很快收到一封包含登录验证码的邮件。"}

        user_id = user['UserID']
        email = user.get('Email') # Assuming DAL returns Email field

        if not email:
            logger.warning(f"User {user_id} does not have an associated email for OTP login.")
            raise ValueError("您的账户未绑定邮箱，无法使用OTP登录。请使用密码登录。")

        # Generate OTP
        otp_code = str(random.randint(100000, 999999)) # 6-digit OTP
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES) # Use OTP_EXPIRE_MINUTES

        try:
            await self.user_dal.create_otp(conn, user_id, otp_code, expires_at, 'Login')
            logger.debug(f"Login OTP {otp_code} created for user {user_id}")
        except DALError as e:
            logger.error(f"Database error creating login OTP for {identifier}: {e}")
            raise DALError(f"数据库错误：无法生成登录OTP。") from e
        except Exception as e:
            logger.error(f"Unexpected error creating login OTP for {identifier}: {e}")
            return {"message": "如果账户存在，您将很快收到一封包含登录验证码的邮件。"}

        # Send email with OTP
        try:
            subject = "思源淘 - 登录验证码"
            
            template_path = os.path.join(EMAIL_TEMPLATES_DIR, "login_otp_email.html")
            with open(template_path, "r", encoding="utf-8") as f:
                email_body_template = f.read()
            
            email_body = email_body_template.format(otp_code=otp_code, expire_minutes=settings.OTP_EXPIRE_MINUTES)
            
            logger.debug(f"Sending login OTP email to {email}")
            await self.email_sender(email, subject, email_body)
            logger.info(f"Login OTP email sent to {email}")
        except EmailSendingError as e:
            logger.error(f"Email sending failed for login OTP to {email}: {e}")
            # This is a non-critical error for the user who might still be trying to log in
            # But we should log it and possibly return a message indicating email issues.
            return {"message": "验证码已发送，但邮件发送失败，请检查邮箱设置。"}
        except Exception as e:
            logger.error(f"Unexpected error sending login OTP email to {email}: {e}")
            return {"message": "如果账户存在，您将很快收到一封包含登录验证码的邮件。"}

        logger.info(f"Login OTP request processed for identifier: {identifier}")
        return {"message": "如果账户存在，您将很快收到一封包含登录验证码的邮件。"}

    # New method to verify login OTP and authenticate
    async def verify_login_otp_and_authenticate(self, conn: pyodbc.Connection, identifier: str, otp_code: str) -> str:
        """
        Service layer function to verify login OTP and authenticate user.
        Returns a JWT token on success.
        """
        logger.info(f"Attempting to verify login OTP and authenticate for identifier: {identifier}")

        # 1. Get OTP details from DAL and validate
        logger.debug(f"Calling DAL.get_otp_details for identifier {identifier} with OTP {otp_code}")
        # get_otp_details currently takes email and otp_code. We need to adapt it.
        # If identifier is username, we need to first get email.
        user = None
        if "@" in identifier:
            user = await self.user_dal.get_user_by_email_with_password(conn, identifier)
            if not user: raise NotFoundError(f"User with email {identifier} not found.")
            email = identifier
        else: # Assume username
            user = await self.user_dal.get_user_by_username_with_password(conn, identifier)
            if not user: raise NotFoundError(f"User with username {identifier} not found.")
            email = user.get('Email')
            if not email: raise ValueError("账户未绑定邮箱，无法使用OTP登录。请使用密码登录。")

        otp_details = await self.user_dal.get_otp_details(conn, email, otp_code)
        logger.debug(f"DAL.get_otp_details returned: {otp_details}")

        if not otp_details:
            logger.warning(f"Login OTP verification failed: Invalid, expired, or used OTP for identifier {identifier}.")
            raise AuthenticationError("验证码无效或已过期，请重新获取。")
        
        user_id = otp_details.get('UserID')
        otp_id = otp_details.get('OtpID')

        if not user_id or not otp_id:
            logger.error(f"DAL error: UserID or OtpID missing from login OTP details for identifier {identifier}.")
            raise DALError("Failed to retrieve user ID or OTP ID from OTP details.")

        # 2. Check user account status
        # Reuse existing user object fetched by get_user_by_email_with_password or get_user_by_username_with_password
        if user.get('Status') == 'Disabled':
            logger.warning(f"Authentication failed: Account for user {identifier} is disabled.")
            raise ForbiddenError("账户已被禁用")

        # 3. Mark OTP as used
        try:
            mark_success = await self.user_dal.mark_otp_as_used(conn, otp_id)
            if not mark_success:
                logger.warning(f"Failed to mark OTP {otp_id} as used after login for user {user_id}.")
        except Exception as e:
            logger.error(f"Error marking OTP {otp_id} as used: {e}")

        # 4. Generate JWT Token
        logger.debug(f"Creating JWT token for user: {identifier}")
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        is_staff = user.get('IsStaff', False)
        is_verified = user.get('IsVerified', False)
        is_super_admin = user.get('IsSuperAdmin', False)

        access_token = create_access_token(
            data={
                "user_id": str(user_id),
                "is_staff": is_staff,
                "is_verified": is_verified,
                "is_super_admin": is_super_admin
            },
            expires_delta=access_token_expires
        )
        logger.info(f"Authentication successful with OTP for user: {identifier}")
        return access_token

# TODO: Add service functions for admin operations (get all users, disable/enable user etc.)