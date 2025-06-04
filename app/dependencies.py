# app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError, ExpiredSignatureError
from typing import Optional, Callable, Awaitable
from uuid import UUID
import pyodbc

from app.config import settings
from app.services.user_service import UserService
from app.services.product_service import ProductService
from app.services.order_service import OrderService
from app.services.evaluation_service import EvaluationService
from app.dal.user_dal import UserDAL
from app.dal.product_dal import ProductDAL, ProductImageDAL, UserFavoriteDAL
from app.dal.orders_dal import OrdersDAL
from app.dal.evaluation_dal import EvaluationDAL
from app.dal.base import execute_query
from app.dal.connection import get_db_connection
from app.utils.email_sender import send_email
from app.schemas.user_schemas import UserResponseSchema, TokenData
from app.exceptions import NotFoundError, IntegrityError, ForbiddenError, PermissionError, DALError

import logging
logger = logging.getLogger(__name__)

async def get_user_service() -> UserService:
    """Dependency injector for UserService, injecting UserDAL with execute_query."""
    logger.debug("Attempting to get UserService instance.")
    user_dal_instance = UserDAL(execute_query_func=execute_query)
    logger.debug("UserDAL instance created.")
    service = UserService(user_dal=user_dal_instance, email_sender=send_email)
    logger.debug("UserService instance created.")
    return service

async def get_product_service() -> ProductService:
    """Dependency injector for ProductService, injecting DALs with execute_query."""
    logger.debug("Attempting to get ProductService instance.")
    product_dal_instance = ProductDAL(execute_query_func=execute_query)
    product_image_dal_instance = ProductImageDAL(execute_query_func=execute_query)
    user_favorite_dal_instance = UserFavoriteDAL(execute_query_func=execute_query)
    logger.debug("Product DAL instances created.")
    service = ProductService(
        product_dal=product_dal_instance,
        product_image_dal=product_image_dal_instance,
        user_favorite_dal=user_favorite_dal_instance
    )
    logger.debug("ProductService instance created.")
    return service

async def get_order_service() -> OrderService:
    """Dependency injector for OrderService, injecting DALs with execute_query."""
    logger.debug("Attempting to get OrderService instance.")
    order_dal_instance = OrdersDAL(execute_query_func=execute_query)
    product_dal_instance = ProductDAL(execute_query_func=execute_query)
    logger.debug("Order and Product DAL instances for OrderService created.")
    service = OrderService(
        order_dal=order_dal_instance,
        product_dal=product_dal_instance
    )
    logger.debug("OrderService instance created.")
    return service

async def get_evaluation_service() -> EvaluationService:
    """Dependency injector for EvaluationService, injecting EvaluationDAL with execute_query."""
    logger.debug("Attempting to get EvaluationService instance.")
    evaluation_dal_instance = EvaluationDAL(execute_query_func=execute_query)
    logger.debug("EvaluationDAL instance created.")
    service = EvaluationService(evaluation_dal=evaluation_dal_instance)
    logger.debug("EvaluationService instance created.")
    return service

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证的凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            user_id_str = payload.get("user_id")
            if user_id_str is None:
                raise credentials_exception
        
        try:
            user_uuid = UUID(user_id_str)
        except ValueError:
             raise credentials_exception

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception

    user_payload = {
        "user_id": user_uuid,
        "is_staff": payload.get("is_staff", False),
        "is_verified": payload.get("is_verified", False),
        "is_super_admin": payload.get("is_super_admin", False)
    }
    
    return user_payload

async def get_current_active_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user is None or not current_user.get('is_staff', False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user

async def get_current_authenticated_user(
    token_payload: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
    conn: pyodbc.Connection = Depends(get_db_connection)
) -> dict:
    """
    Returns the current authenticated and active user as a dictionary.
    """
    logger.debug(f"get_current_authenticated_user received token_payload: {token_payload} (Type: {type(token_payload)})")
    user_id_str = token_payload.get("user_id")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials (user ID missing in token payload)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = user_id_str

    try:
        user_profile = await user_service.get_user_profile_by_id(conn, user_id)
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_dict = user_profile.model_dump()

        if user_dict.get("账户状态") != "Active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_dict

    except (NotFoundError, DALError, PermissionError) as e:
        # Handle specific service errors
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Error fetching authenticated user profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_super_admin_user(current_user_dict: dict = Depends(get_current_user)) -> dict:
    logger.debug(f"get_current_super_admin_user received current_user: {current_user_dict}")
    is_super_admin = current_user_dict.get('is_super_admin', False)
    logger.debug(f"get_current_super_admin_user check result: {is_super_admin}")
    if current_user_dict is None or not is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return current_user_dict