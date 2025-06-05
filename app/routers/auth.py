# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
import pyodbc
from uuid import UUID

from app.schemas.user_schemas import (
    UserRegisterSchema,
    UserLoginSchema, # Keep for schema definition reference if needed elsewhere, but not for login input
    UserResponseSchema,
    Token,
    # VerifyEmail, # Removed - no longer used for magic link verification
    # RequestVerificationEmail, # Removed - replaced by RequestOtpSchema
    UserPasswordUpdate, # Ensure all necessary schemas are imported
    RequestOtpSchema, # Import new schema for requesting OTP
    VerifyOtpAndResetPasswordSchema, # Import new schema for verifying OTP and resetting password
    VerifyOtpSchema, # Import new schema for general OTP verification
    RequestLoginOtpSchema, # Import new schema for requesting login OTP
    VerifyLoginOtpSchema # Import new schema for verifying login OTP
)
from app.services.user_service import UserService
from app.dal.connection import get_db_connection # Import the DB connection dependency
from app.dependencies import get_user_service # Import the Service dependency
from app.exceptions import AuthenticationError, ForbiddenError, IntegrityError, DALError # Import exceptions, including DALError

from fastapi.security import OAuth2PasswordRequestForm # Import OAuth2PasswordRequestForm

import logging # Import logging
logger = logging.getLogger(__name__) # Get logger instance

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/register", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegisterSchema,
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    新用户注册。
    """
    logger.info(f"API: Received registration request for username: {user_data.username}") # Add logging
    try:
        # Call Service layer function, passing the connection
        created_user = await user_service.create_user(conn, user_data)
        logger.info(f"API: User {user_data.username} registered successfully. User ID: {created_user.用户ID}") # Changed from .user_id to .用户ID
        return created_user
    except IntegrityError as e:
        logger.warning(f"API: Registration failed for {user_data.username} due to integrity error: {e}") # Add logging
        # Catch specific DAL errors and convert to HTTP exceptions
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DALError as e:
        logger.error(f"API: Registration failed for {user_data.username} due to DAL error: {e}") # Add logging
        # Catch other DAL errors
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"API: Registration failed for {user_data.username} due to unexpected error: {e}", exc_info=True) # Add logging with exc_info
        # Catch any other unexpected errors
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), # Use OAuth2PasswordRequestForm for form data
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    用户登录并获取 JWT Token。
    OAuth2PasswordRequestForm 默认只接收 username 和 password。我们修改 Service 层来同时处理 username 和 email。
    """
    logger.info(f"API: Received login request for username: {form_data.username}") # Add logging
    
    # Determine if the input is likely an email or a username
    # A simple check based on the presence of '@'
    is_email = '@' in form_data.username
    
    try:
        # Call Service layer function, passing the connection
        # Service returns the access token string
        if is_email:
             # If it looks like an email, pass email to service
             access_token_string = await user_service.authenticate_user_and_create_token(conn, password=form_data.password, email=form_data.username)
             logger.info(f"API: Attempting login with email: {form_data.username}")
        else:
             # Otherwise, pass username to service
             access_token_string = await user_service.authenticate_user_and_create_token(conn, password=form_data.password, username=form_data.username)
             logger.info(f"API: Attempting login with username: {form_data.username}")

        # If authentication fails, service.authenticate_user_and_create_token should ideally raise an exception
        # If it returns None or similar on failure, handle that case
        if not access_token_string:
             # This case might be covered by exceptions from Service, but as a safeguard
             logger.warning(f"API: Login failed for {form_data.username}: Service returned no token.") # Add logging
             raise HTTPException(
                 status_code=status.HTTP_401_UNAUTHORIZED,
                 detail="用户名或密码不正确",
                 headers={"WWW-Authenticate": "Bearer"},
             )

        logger.info(f"API: Login successful for user: {form_data.username}") # Add logging
        return {"access_token": access_token_string, "token_type": "bearer"}
    except (AuthenticationError, ForbiddenError) as e:
         logger.warning(f"API: Login failed for {form_data.username} due to auth/forbidden error: {e}") # Add logging
         # Catch authentication and forbidden errors from Service
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationError) else status.HTTP_403_FORBIDDEN,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"} if isinstance(e, AuthenticationError) else None
        )
    except DALError as e:
        logger.error(f"API: Login failed for {form_data.username} due to DAL error: {e}") # Add logging
        # Catch DAL errors
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        logger.error(f"API: Login failed for {form_data.username} due to unexpected error: {e}", exc_info=True) # Add logging with exc_info
        # Catch any other unexpected errors
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/request-verification-email", status_code=status.HTTP_200_OK, summary="请求学生身份验证OTP") # Changed summary
async def request_verification_email_api(
    request_data: RequestOtpSchema, # Changed schema to RequestOtpSchema
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    请求发送学生身份验证OTP。
    接收用户的邮箱地址，生成 OTP 并发送包含验证码的邮件。
    """
    logger.info(f"API: Received request for student verification OTP for email: {request_data.email}")
    try:
        result = await user_service.request_verification_email(conn, request_data.email)
        return {"message": result.get("message", "如果邮箱存在或已注册，验证码已发送。请检查您的收件箱。")}
    except ValueError as e:
        logger.warning(f"API: Request verification email failed for {request_data.email} due to validation error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (DALError, AuthenticationError, ForbiddenError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        if isinstance(e, ForbiddenError): status_code = status.HTTP_403_FORBIDDEN
        logger.error(f"API: Request verification email failed for {request_data.email} due to error: {e}", exc_info=True)
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"API: Request verification email failed for {request_data.email} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/verify-email-otp", status_code=status.HTTP_200_OK, summary="验证邮箱OTP") # New endpoint
async def verify_email_otp_api(
    verify_data: VerifyOtpSchema,
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    使用OTP验证邮箱。
    """
    logger.info(f"API: Received email OTP verification request for email: {verify_data.email}")
    try:
        verification_result = await user_service.verify_email_otp(conn, verify_data.email, verify_data.otp)
        if verification_result and verification_result.get('is_verified') is True:
             return {"message": "邮箱验证成功！您现在可以登录。", "user_id": str(verification_result.get('user_id')), "is_verified": True}
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="邮箱验证失败：内部处理异常。")
    except (DALError, AuthenticationError, ValueError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, ValueError): status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        logger.error(f"API: Email OTP verification failed for {verify_data.email} due to error: {e}", exc_info=True)
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"API: Email OTP verification failed for {verify_data.email} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/request-password-reset", status_code=status.HTTP_200_OK)
async def request_password_reset_api(
    request_data: RequestOtpSchema, # Changed schema to RequestOtpSchema
    conn: pyodbc.Connection = Depends(get_db_connection), # Inject DB connection
    user_service: UserService = Depends(get_user_service) # Inject Service
):
    """
    请求发送密码重置邮件。
    接收用户的邮箱地址，生成密码重置 token 并发送包含链接的邮件。
    """
    logger.info(f"API: Received password reset request for email: {request_data.email}")
    try:
        # Call Service layer function. The service now handles OTP generation and email sending.
        result = await user_service.request_password_reset(conn, request_data.email)
        
        # Service handles logging internal errors (like email sending failure) but returns a consistent message
        return result # Return the message provided by the service
        
    except (DALError, Exception) as e:
        # Catch any potential database or unexpected errors from the service
        logger.error(f"API: Password reset request failed for {request_data.email} due to error: {e}", exc_info=True)
        # For security, still return a generic success message, even if an error occurred after the initial user check
        return {"message": "如果邮箱存在，您将很快收到一封包含密码重置链接的邮件。"}

@router.post("/request-otp-password-reset", status_code=status.HTTP_200_OK)
async def request_otp_password_reset_api(
    request_data: RequestOtpSchema,
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    请求发送 OTP 用于密码重置。
    """
    logger.info(f"API: Received request for OTP password reset for email: {request_data.email}")
    try:
        result = await user_service.request_password_reset(conn, request_data.email)
        return result
    except (DALError, AuthenticationError, ForbiddenError, ValueError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, ValueError): status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        if isinstance(e, ForbiddenError): status_code = status.HTTP_403_FORBIDDEN
        logger.error(f"API: Request OTP password reset failed for {request_data.email} due to error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"API: Request OTP password reset failed for {request_data.email} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/verify-otp-and-reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def verify_otp_and_reset_password_api(
    reset_data: VerifyOtpAndResetPasswordSchema,
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    验证 OTP 并重置密码。
    """
    logger.info(f"API: Received OTP verification and password reset request for email: {reset_data.email}")
    try:
        await user_service.verify_otp_and_reset_password(conn, reset_data.email, reset_data.otp, reset_data.new_password)
        logger.info(f"API: Password reset successful for email: {reset_data.email}")
        return {} # 204 No Content
    except (DALError, AuthenticationError, ValueError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, ValueError): status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        logger.warning(f"API: OTP verification and password reset failed for {reset_data.email} due to error: {e}")
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"API: OTP verification and password reset failed for {reset_data.email} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# New endpoint for requesting login OTP
@router.post("/request-login-otp", status_code=status.HTTP_200_OK, summary="请求登录OTP")
async def request_login_otp_api(
    request_data: RequestLoginOtpSchema,
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    请求发送登录OTP。接收用户名或邮箱，生成OTP并发送邮件。
    """
    logger.info(f"API: Received request for login OTP for identifier: {request_data.identifier}")
    try:
        result = await user_service.request_login_otp(conn, request_data.identifier)
        return result
    except (DALError, AuthenticationError, ForbiddenError, ValueError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, ValueError): status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        if isinstance(e, ForbiddenError): status_code = status.HTTP_403_FORBIDDEN
        logger.error(f"API: Request login OTP failed for {request_data.identifier} due to error: {e}", exc_info=True)
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"API: Request login OTP failed for {request_data.identifier} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# New endpoint for verifying login OTP and authenticating
@router.post("/verify-login-otp", response_model=Token, status_code=status.HTTP_200_OK, summary="验证登录OTP并登录")
async def verify_login_otp_api(
    verify_data: VerifyLoginOtpSchema,
    conn: pyodbc.Connection = Depends(get_db_connection),
    user_service: UserService = Depends(get_user_service)
):
    """
    验证登录OTP并完成登录，返回JWT Token。
    """
    logger.info(f"API: Received login OTP verification request for identifier: {verify_data.identifier}")
    try:
        access_token_string = await user_service.verify_login_otp_and_authenticate(conn, verify_data.identifier, verify_data.otp)
        logger.info(f"API: Login successful with OTP for identifier: {verify_data.identifier}")
        return {"access_token": access_token_string, "token_type": "bearer"}
    except (DALError, AuthenticationError, ValueError) as e:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(e, ValueError): status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(e, AuthenticationError): status_code = status.HTTP_401_UNAUTHORIZED
        logger.warning(f"API: Login OTP verification failed for {verify_data.identifier} due to error: {e}")
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"API: Login OTP verification failed for {verify_data.identifier} due to unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# Note: We need to add the authenticate_user_and_create_token method to UserService 
# and ensure it handles the logic of calling DAL and creating the token. 