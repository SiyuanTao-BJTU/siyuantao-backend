# app/routers/users.py
from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Request
# from app.schemas.user_schemas import UserCreate, UserResponse, UserLogin, Token, UserUpdate, RequestVerificationEmail, VerifyEmail, UserPasswordUpdate # Import schemas from here
from app.schemas.user_schemas import (
    UserResponseSchema, 
    UserProfileUpdateSchema, 
    UserPasswordUpdate, # Import necessary schemas
    UserStatusUpdateSchema, # Added for new admin endpoint
    UserCreditAdjustmentSchema, # Added for new admin endpoint
    RequestVerificationEmail, # Import the schema for requesting verification email
    UserPublicProfileResponseSchema # 新增：导入公共用户资料Schema
)
# from app.dal import users as user_dal # No longer needed
# from app.services import user_service # No longer needed (using dependency)
from app.services.user_service import UserService # Import Service class for type hinting
from app.dal.connection import get_db_connection
# from app.exceptions import NotFoundError, IntegrityError, DALError # Import exceptions directly or via dependencies
import pyodbc
from uuid import UUID
# from datetime import timedelta # Not directly needed in router for this logic
import os # Import the 'os' module

# Import auth dependencies from dependencies.py
from app.dependencies import (
    get_current_user, # For authenticated endpoints
    get_current_active_admin_user, # For admin-only endpoints
    get_user_service, # Dependency for UserService
    get_current_authenticated_user, # For active authenticated users
    get_current_super_admin_user # Added for super admin authentication
)
from app.exceptions import NotFoundError, IntegrityError, DALError, AuthenticationError, ForbiddenError,  PermissionError # Import necessary exceptions

# Import file upload utility
from ..utils.file_upload import save_upload_file, UPLOAD_DIR # Import UPLOAD_DIR to construct the URL

import logging # Import logging
logger = logging.getLogger(__name__) # Get logger instance

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=UserResponseSchema, response_model_by_alias=False)
async def read_users_me(
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    logger.debug(f"API /me: current_user from dependency: {current_user}")
    # The current_user dict from get_current_authenticated_user is already
    # a dictionary representation of UserResponseSchema (with Chinese keys as primary).
    # FastAPI will correctly serialize this back to the UserResponseSchema, respecting aliases.
    return current_user

@router.put("/me", response_model=UserResponseSchema, response_model_by_alias=False)
async def update_current_user_profile(
    user_update_data: UserProfileUpdateSchema, # Request body here
    # current_user: dict = Depends(get_current_user) # Requires JWT authentication
    current_user: UserResponseSchema = Depends(get_current_authenticated_user), # Use dependency from dependencies.py
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    更新当前登录用户的个人资料 (不包括密码)。
    """
    user_id = current_user['用户ID'] # Access with Chinese key as current_user is dict with Chinese keys

    try:
        # Call Service layer function, passing the connection and user_id
        updated_user = await user_service.update_user_profile(conn, user_id, user_update_data) # Pass user_id directly (expected to be UUID)
        return updated_user # Service should return the updated user profile
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except IntegrityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    # Authentication and Forbidden errors are handled by get_current_authenticated_user dependency
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_current_user_password(
    password_update_data: UserPasswordUpdate, # Request body here
    # current_user: dict = Depends(get_current_user) # Requires JWT authentication
    current_user: UserResponseSchema = Depends(get_current_authenticated_user), # Use dependency from dependencies.py
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    更新当前登录用户的密码。
    """
    user_id = current_user['用户ID'] # Access with Chinese key as current_user is dict with Chinese keys

    try:
        # Call Service layer function, passing the connection and user_id
        update_success = await user_service.update_user_password(conn, user_id, password_update_data) # Pass user_id directly (expected to be UUID)
        # Service.update_user_password should return True on success and raise exception on failure
        if not update_success:
             # This case should ideally be covered by exceptions from Service, but as a safeguard
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密码更新失败")

        # Password update successful returns 204 No Content
        return {}
    except (NotFoundError, AuthenticationError, DALError, ForbiddenError) as e:
         # Catch specific errors from Service
         raise HTTPException(
             status_code=status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else
                           (status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationError) else
                            (status.HTTP_403_FORBIDDEN if isinstance(e, ForbiddenError) else status.HTTP_500_INTERNAL_SERVER_ERROR)),
             detail=str(e),
             # Include WWW-Authenticate header for AuthenticationError (401)
             headers={"WWW-Authenticate": "Bearer"} if isinstance(e, AuthenticationError) else None
         )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/me/avatar", response_model=UserResponseSchema, response_model_by_alias=False)
async def upload_my_avatar(
    avatar_file: UploadFile = File(...), # Let FastAPI handle the file upload directly
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    上传或更新当前登录用户的头像。
    """
    user_id = current_user['用户ID'] # Access with Chinese key
    
    try:
        # 1. Save the uploaded file using the utility function
        file_path = await save_upload_file(avatar_file)
        
        # 2. Construct the URL for the saved file
        file_name = os.path.basename(file_path)
        avatar_url = f"/{UPLOAD_DIR}/{file_name}"
        
        # 3. Call the UserService method to update the user's avatar URL in the database
        updated_user = await user_service.update_user_avatar(conn, user_id, avatar_url)
        
        # Return the updated user profile (which includes the new avatar URL)
        return updated_user
        
    except NotFoundError as e:
        # This should be caught by the service layer, but handle as a safeguard
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        # Catch any other exceptions during file upload or service call
        logger.exception(f"Error uploading avatar for user {user_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload avatar: {e}")

# Admin endpoints for user management by ID

@router.get("/{user_id}", response_model=UserResponseSchema, response_model_by_alias=False)
async def get_user_profile_by_id(
    user_id: UUID, # Path parameter here
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service), # Inject Service
    # Note: Authentication check is handled by the dependency itself.
    current_admin_user: dict = Depends(get_current_active_admin_user)
):
    """
    管理员根据用户 ID 获取用户个人资料。
    """
    try:
        # Call Service layer function, passing the connection
        user = await user_service.get_user_profile_by_id(conn, user_id) # Pass user_id directly
        return user
    except NotFoundError as e:
        # This exception is raised by the Service layer if user is not found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (AuthenticationError, ForbiddenError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationError) else status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{user_id}", response_model=UserResponseSchema, response_model_by_alias=False)
async def update_user_profile_by_id(
    user_id: UUID, # Path parameter here
    user_update_data: UserProfileUpdateSchema, # Request body here
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service),
    current_admin_user: dict = Depends(get_current_active_admin_user)
):
    """
    管理员根据用户 ID 更新用户个人资料。
    """
    try:
        # Call Service layer function, passing the connection
        updated_user = await user_service.update_user_profile(conn, user_id, user_update_data) # Pass user_id directly
        return updated_user
    except (NotFoundError, IntegrityError, DALError, AuthenticationError, ForbiddenError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if isinstance(e, NotFoundError) else
                          (status.HTTP_409_CONFLICT if isinstance(e, IntegrityError) else
                           (status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationError) else
                            (status.HTTP_403_FORBIDDEN if isinstance(e, ForbiddenError) else status.HTTP_500_INTERNAL_SERVER_ERROR))),
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_by_id(
    user_id: UUID, # Path parameter here
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service), # Inject Service
    current_admin_user: dict = Depends(get_current_super_admin_user)
):
    """
    管理员根据用户 ID 删除用户。
    """
    try:
        # Call Service layer function, passing the connection
        await user_service.delete_user(conn, user_id) # Pass user_id directly
        return {} # 204 No Content returns an empty body
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (AuthenticationError, ForbiddenError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationError) else status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# Removed email verification routes as they are in auth.py
# @router.post("/request-verification-email", status_code=status.HTTP_200_OK)
# async def request_verification_email_api(

# TODO: Add admin-only endpoints for user management like listing all users, disabling/enabling accounts, etc. 

# Admin endpoint to get all users
@router.get("/", response_model=list[UserResponseSchema], response_model_by_alias=False)
async def get_all_users_api(
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service),
    current_admin_user: dict = Depends(get_current_active_admin_user) # Requires admin authentication
):
    """
    Retrieve all users. Only accessible by admin users.
    """
    try:
        # Log the admin user dictionary to understand its structure
        logger.debug(f"API /users (GET ALL): current_admin_user: {current_admin_user}")
        if not current_admin_user or not current_admin_user.get("is_staff"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权执行此操作")

        # Correctly access the admin_id using the English key from the token
        admin_id = current_admin_user.get('user_id')
        if not admin_id:
            logger.error("Admin user_id not found in token data.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法识别管理员身份")

        users = await user_service.get_all_users(conn, admin_id)
        return users
    except HTTPException as e: # Re-raise HTTPExceptions to maintain status code and detail
        logger.error(f"HTTPException in get_all_users_api: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error in get_all_users_api: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取所有用户失败")

# Admin endpoint to change user status
@router.put("/{user_id}/status", status_code=status.HTTP_204_NO_CONTENT)
async def change_user_status_by_id(
    user_id: UUID, # Path parameter here
    status_update_data: UserStatusUpdateSchema, # Request body here
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service),
    current_admin_user: dict = Depends(get_current_active_admin_user)
):
    """
    Change a user's status (Active/Disabled). Only accessible by admin users.
    """
    try:
        logger.info(f"Attempting to change status for user {user_id} by admin {current_admin_user.get('user_id')}")
        admin_id = current_admin_user.get('user_id') # Use English key 'user_id'
        if not admin_id:
            logger.error(f"Admin ID not found in token for status change operation on user {user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员身份未能识别")

        success = await user_service.change_user_status(conn, user_id, status_update_data.status, admin_id)
        if not success:
            # This case might be redundant if service layer raises specific exceptions for failure
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="更新用户状态失败")
        # No content returned on success, as per HTTP_204_NO_CONTENT
    except NotFoundError as e:
        logger.warning(f"NotFoundError in change_user_status_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e: # Specific error for permission issues from service
        logger.warning(f"PermissionError in change_user_status_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e: # Catch potential ValueErrors, e.g. invalid status string
        logger.warning(f"ValueError in change_user_status_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error changing status for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新用户状态时发生内部错误")

# Super Admin endpoint to toggle user staff status
@router.put("/{user_id}/toggle_staff", status_code=status.HTTP_204_NO_CONTENT)
async def toggle_user_staff_status(
    user_id: UUID, # Path parameter
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service),
    current_super_admin: dict = Depends(get_current_super_admin_user) # Requires super admin authentication
):
    """
    Toggle a user's staff status. Only accessible by super admin users.
    """
    try:
        logger.info(f"Attempting to toggle staff status for user {user_id} by super_admin {current_super_admin.get('user_id')}")
        super_admin_id = current_super_admin.get('user_id') # Use English key 'user_id'
        if not super_admin_id:
            logger.error(f"Super Admin ID not found in token for toggle_staff operation on user {user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="超级管理员身份未能识别")

        success = await user_service.toggle_user_staff_status(conn, user_id, super_admin_id) # Pass UUID
        if not success:
            # This case might be redundant if service layer raises specific exceptions for failure
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="切换用户管理员状态失败")
        # No content returned on success
    except NotFoundError as e:
        logger.warning(f"NotFoundError in toggle_user_staff_status for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"PermissionError in toggle_user_staff_status for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error toggling staff status for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="切换用户管理员状态时发生内部错误")

# Admin endpoint to adjust user credit
@router.put("/{user_id}/credit", status_code=status.HTTP_204_NO_CONTENT)
async def adjust_user_credit_by_id(
    user_id: UUID, # Path parameter here
    credit_adjustment_data: UserCreditAdjustmentSchema, # Request body here
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service),
    current_admin_user: dict = Depends(get_current_active_admin_user)
):
    """
    Adjust a user's credit score. Only accessible by admin users.
    """
    try:
        logger.info(f"Attempting to adjust credit for user {user_id} by admin {current_admin_user.get('user_id')}")
        admin_id = current_admin_user.get('user_id') # Use English key 'user_id'
        if not admin_id:
            logger.error(f"Admin ID not found in token for credit adjustment operation on user {user_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员身份未能识别")

        success = await user_service.adjust_user_credit(
            conn,
            user_id,
            credit_adjustment_data.credit_adjustment,
            admin_id, # Pass UUID
            credit_adjustment_data.reason
        )
        if not success:
            # This case might be redundant if service layer raises specific exceptions for failure
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="调整用户信用分失败")
        # No content returned on success
    except NotFoundError as e:
        logger.warning(f"NotFoundError in adjust_user_credit_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        logger.warning(f"PermissionError in adjust_user_credit_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e: # Catch potential ValueErrors from Pydantic model or service layer
        logger.warning(f"ValueError in adjust_user_credit_by_id for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error adjusting credit for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="调整用户信用分时发生内部错误")

# 公开的用户资料接口
@router.get("/{user_id}/public_profile", response_model=UserPublicProfileResponseSchema, response_model_by_alias=False)
async def get_public_user_profile_by_id(
    user_id: UUID, # Path parameter
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    根据用户 ID 获取用户公开的个人资料 (无需认证)。
    """
    try:
        public_profile = await user_service.get_user_public_profile(conn, user_id)
        if not public_profile:
            raise NotFoundError("用户未找到")
        return public_profile
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting public user profile for ID {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")
