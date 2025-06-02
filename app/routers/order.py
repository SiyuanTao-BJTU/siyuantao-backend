from fastapi import APIRouter, Depends, HTTPException, Path, Body, Query
from typing import List
import pyodbc
import uuid # For User ID and Order ID
import fastapi

# 假设的Schema路径，请根据您的项目结构调整
from app.schemas.order_schemas import OrderCreateSchema, OrderResponseSchema, OrderStatusUpdateSchema 
# 假设的Service和依赖路径，请根据您的项目结构调整
from app.services.order_service import OrderService
from app.dependencies import get_current_authenticated_user, get_db_connection, get_order_service, get_current_active_admin_user 

# 假设的异常类路径，请根据您的项目结构调整
from app.exceptions import IntegrityError, ForbiddenError, NotFoundError, DALError

router = APIRouter()

@router.post("/", response_model=OrderResponseSchema, status_code=fastapi.status.HTTP_201_CREATED, response_model_by_alias=False)
async def create_new_order(
    order_data: OrderCreateSchema,
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    创建一个新订单，需要用户登录。
    对应存储过程: `sp_CreateOrder` (通过Service层调用)
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")
    
    try:
        user_id = user_id_str # 直接使用 UUID 对象
        # Service层负责具体的业务逻辑和调用DAL
        new_order = await order_service.create_order(conn, order_data, user_id)
        return new_order
    except IntegrityError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        # 捕获其他未预期错误
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{order_id}/status", response_model=OrderResponseSchema, response_model_by_alias=False)
async def update_order_status_route(
    status_update: OrderStatusUpdateSchema, # Body first
    order_id: uuid.UUID = Path(..., title="The ID of the order to update"), # Path param with default
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    更新订单状态 (例如：确认、完成、拒绝)。
    需要用户登录，并验证用户是否有权限操作该订单 (通常是买家或卖家)。
    对应存储过程: `sp_ConfirmOrder`, `sp_CompleteOrder`, `sp_RejectOrder` (通过Service层调用)
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        updated_order = await order_service.update_order_status(
            conn, 
            order_id=order_id, 
            new_status=status_update.status, 
            user_id=user_id,
            cancel_reason=status_update.cancel_reason # Pass cancel_reason to service
        )
        return updated_order
    except IntegrityError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e: # 例如，无效的状态转换
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e: # 用户无权修改此订单状态
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e: # 订单未找到
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/mine", response_model=List[OrderResponseSchema], response_model_by_alias=False)
async def get_my_orders(
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service),
    status: str = Query(None), # 添加status查询参数
    page_number: int = Query(1, ge=1), # 添加page_number查询参数
    page_size: int = Query(10, ge=1, le=100), # 添加page_size查询参数
    is_seller: bool = Query(False) # 新增 is_seller 查询参数，默认为 False (获取买家订单)
):
    """
    获取当前登录用户的所有订单列表 (作为买家或卖家)。
    对应存储过程: `sp_GetOrdersByUser` (通过Service层调用)
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        # 使用传入的 is_seller 参数
        orders = await order_service.get_orders_by_user(conn, user_id, is_seller=is_seller, status=status, page_number=page_number, page_size=page_size)
        return orders
    except NotFoundError as e: # 虽然通常返回空列表，但以防service层抛出
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/admin", response_model=List[OrderResponseSchema], response_model_by_alias=False)
async def get_all_orders_for_admin_route(
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service),
    admin_user: dict = Depends(get_current_active_admin_user), # 使用管理员认证依赖
    status: str = Query(None), # 添加status查询参数
    page_number: int = Query(1, ge=1), # 添加page_number查询参数
    page_size: int = Query(10, ge=1, le=100) # 添加page_size查询参数
):
    """
    获取所有订单列表 (管理员视图)。
    对应存储过程: `sp_GetAllOrders` (通过Service层调用)
    """
    # 无需 user_id_str 检查，因为 admin_user 依赖已经确保是管理员
    try:
        orders = await order_service.get_all_orders_for_admin(conn, status=status, page_number=page_number, page_size=page_size)
        return orders
    except NotFoundError as e: 
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e: # 权限不足
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/{order_id}", response_model=OrderResponseSchema, response_model_by_alias=False)
async def get_order_by_id_route(
    order_id: uuid.UUID = Path(..., title="The ID of the order to retrieve"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    根据ID获取单个订单详情。
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        order = await order_service.get_order_by_id(conn, order_id, requesting_user_id=user_id)
        if not order:
            raise NotFoundError("订单未找到")
        return order
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# TODO: 根据《职责划分》，开发者C还负责 Evaluation (评价) 表相关的API。
# 您可能需要在此文件中添加评价相关的路由，或者创建一个新的 `evaluation_router.py`。
# 例如: POST /orders/{order_id}/evaluations/ , GET /products/{product_id}/evaluations/


@router.delete("/{order_id}", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def delete_order_route(
    order_id: uuid.UUID = Path(..., title="The ID of the order to delete"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    删除一个订单。
    需要用户登录，并验证用户是否有权限删除该订单。
    对应存储过程: `sp_DeleteOrder` (通过Service层调用)
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        await order_service.delete_order(conn, order_id, user_id)
        # 成功删除通常返回 204 No Content
        return
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e: # 例如，订单状态不允许删除
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError as e: # Add IntegrityError handling
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.post("/{order_id}/cancel", status_code=fastapi.status.HTTP_204_NO_CONTENT)
async def cancel_order_route(
    cancel_reason_data: dict, # Assuming a simple dict for reason
    order_id: uuid.UUID = Path(..., title="The ID of the order to cancel"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    取消一个订单。
    需要用户登录，并验证用户是否有权限取消该订单。
    对应存储过程: `sp_CancelOrder` (通过Service层调用)
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    cancel_reason = cancel_reason_data.get("cancel_reason")
    if not cancel_reason:
         raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail="取消原因不能为空")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        await order_service.cancel_order(conn, order_id, user_id, cancel_reason)
        # 成功取消通常返回 204 No Content
        return
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        # Note: The test expects a specific detail message for 404, need to ensure consistency
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e: # 例如，订单状态不允许取消
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError as e: # Add IntegrityError handling
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.put("/{order_id}/confirm", response_model=OrderResponseSchema, response_model_by_alias=False)
async def confirm_order_route(
    order_id: uuid.UUID = Path(..., title="The ID of the order to confirm"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    确认一个订单。
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")
    
    try:
        user_id = user_id_str # 直接使用 UUID 对象
        updated_order = await order_service.confirm_order(conn, order_id, user_id)
        return updated_order
    except IntegrityError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")


@router.put("/{order_id}/complete", response_model=OrderResponseSchema, response_model_by_alias=False)
async def complete_order_route(
    order_id: uuid.UUID = Path(..., title="The ID of the order to complete"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service)
):
    """
    完成一个订单。
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        updated_order = await order_service.complete_order(conn, order_id, user_id)
        return updated_order
    except IntegrityError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")


@router.put("/{order_id}/reject", response_model=OrderResponseSchema, response_model_by_alias=False)
async def reject_order_route(
    order_id: uuid.UUID = Path(..., title="The ID of the order to reject"),
    current_user: dict = Depends(get_current_authenticated_user),
    conn: pyodbc.Connection = Depends(get_db_connection),
    order_service: OrderService = Depends(get_order_service),
    rejection_reason_data: dict = Body(..., embed=True) # Assuming reason is in body
):
    """
    拒绝一个订单。
    """
    user_id_str = current_user.get("用户ID")
    if not user_id_str:
        raise HTTPException(status_code=fastapi.status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

    rejection_reason = rejection_reason_data.get("rejection_reason")
    if not rejection_reason:
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail="拒绝原因不能为空")

    try:
        user_id = user_id_str # 直接使用 UUID 对象
        updated_order = await order_service.reject_order(conn, order_id, user_id, rejection_reason)
        return updated_order
    except IntegrityError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail if e.detail else str(e))
    except Exception as e:
        raise HTTPException(status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")
