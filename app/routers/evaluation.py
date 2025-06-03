from fastapi import APIRouter, Depends, HTTPException, status, Query # 导入 Query
from typing import List
from uuid import UUID
import pyodbc # 导入 pyodbc

from app.schemas.evaluation_schemas import EvaluationCreateSchema, EvaluationResponseSchema
from app.dependencies import get_evaluation_service, get_current_authenticated_user, get_current_active_admin_user # 导入 get_current_active_admin_user
from app.services.evaluation_service import EvaluationService
from app.exceptions import IntegrityError, ForbiddenError, NotFoundError, DALError
from app.dal.connection import get_db_connection # 导入 get_db_connection

router = APIRouter()

@router.post("/", response_model=EvaluationResponseSchema, status_code=status.HTTP_201_CREATED, response_model_by_alias=False)
async def create_new_evaluation(
    evaluation_data: EvaluationCreateSchema, # 请求体数据
    current_user: dict = Depends(get_current_authenticated_user), # 认证依赖
    conn: pyodbc.Connection = Depends(get_db_connection), # 数据库连接依赖
    evaluation_service: EvaluationService = Depends(get_evaluation_service) # Service 依赖
):
    """
    发布一个新的评价，需要用户登录。
    """
    # get_current_authenticated_user 已经确保了用户ID的存在，可以直接访问
    user_id = current_user["用户ID"]
    
    try:
        # 调用业务逻辑层 Service 方法
        new_evaluation = await evaluation_service.create_evaluation(conn, evaluation_data, user_id)
        return new_evaluation
    except IntegrityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        # 捕获其他未预期错误
        # 考虑在这里添加日志记录
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/admin", response_model=List[EvaluationResponseSchema], response_model_by_alias=False)
async def get_all_evaluations_for_admin_route(
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    admin_user: dict = Depends(get_current_active_admin_user), # 管理员认证依赖
    product_id: UUID = Query(None), # 可选商品ID筛选
    seller_id: UUID = Query(None),  # 可选卖家ID筛选
    buyer_id: UUID = Query(None),   # 可选买家ID筛选
    min_rating: int = Query(None, ge=1, le=5), # 最小评分筛选
    max_rating: int = Query(None, ge=1, le=5), # 最大评分筛选
    page_number: int = Query(1, ge=1), # 分页页码
    page_size: int = Query(10, ge=1, le=100) # 分页大小
):
    """
    获取所有评价列表 (管理员视图)，支持多重筛选和分页。
    """
    try:
        evaluations = await evaluation_service.get_all_evaluations_for_admin(
            conn,
            product_id=product_id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            min_rating=min_rating,
            max_rating=max_rating,
            page_number=page_number,
            page_size=page_size
        )
        return evaluations
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.delete("/admin/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation_by_admin_route(
    evaluation_id: UUID,
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    admin_user: dict = Depends(get_current_active_admin_user) # 管理员认证依赖
):
    """
    管理员删除指定评价。
    """
    try:
        await evaluation_service.delete_evaluation_by_admin(conn, evaluation_id, admin_user["用户ID"])
        return
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/product/{product_id}", response_model=List[EvaluationResponseSchema], response_model_by_alias=False)
async def get_evaluations_by_product_id_route(
    product_id: UUID, # Path parameter
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service)
):
    """
    根据商品ID获取该商品的所有评价。
    """
    try:
        evaluations = await evaluation_service.get_evaluations_by_product_id(conn, product_id)
        return evaluations
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/made", response_model=List[EvaluationResponseSchema], response_model_by_alias=False)
async def get_my_evaluations_route(
    current_user: dict = Depends(get_current_authenticated_user), # 认证依赖
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service)
):
    """
    获取当前登录买家（我发出）的所有评价。
    """
    buyer_id = current_user["用户ID"]
    try:
        evaluations = await evaluation_service.get_evaluations_by_buyer_id(conn, buyer_id)
        return evaluations
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/received", response_model=List[EvaluationResponseSchema], response_model_by_alias=False)
async def get_my_evaluations_received_route(
    current_user: dict = Depends(get_current_authenticated_user), # 认证依赖
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service)
):
    """
    获取当前登录卖家收到的所有评价。
    """
    seller_id = current_user["用户ID"]
    try:
        evaluations = await evaluation_service.get_evaluations_by_seller_id(conn, seller_id)
        return evaluations
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/{evaluation_id}", response_model=EvaluationResponseSchema, response_model_by_alias=False)
async def get_evaluation_by_id_route(
    evaluation_id: UUID, # Path parameter
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service)
):
    """
    根据评价ID获取单个评价详情。
    """
    try:
        evaluation = await evaluation_service.get_evaluation_by_id(conn, evaluation_id)
        return evaluation
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")