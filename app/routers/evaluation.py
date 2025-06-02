from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from uuid import UUID
import pyodbc # 导入 pyodbc

from app.schemas.evaluation_schemas import EvaluationCreateSchema, EvaluationResponseSchema
from app.dependencies import get_evaluation_service, get_current_user # 导入 Service 的依赖函数
from app.services.evaluation_service import EvaluationService
from app.exceptions import IntegrityError, ForbiddenError, NotFoundError, DALError
from app.dal.connection import get_db_connection # 导入 get_db_connection

router = APIRouter()

@router.post("/", response_model=EvaluationResponseSchema, status_code=status.HTTP_201_CREATED, response_model_by_alias=False)
async def create_new_evaluation(
    evaluation_data: EvaluationCreateSchema, # 请求体数据
    current_user: dict = Depends(get_current_user), # 认证依赖
    conn: pyodbc.Connection = Depends(get_db_connection), # 数据库连接依赖
    evaluation_service: EvaluationService = Depends(get_evaluation_service) # Service 依赖
):
    """
    发布一个新的评价，需要用户登录。
    """
    user_id = current_user.get("用户ID")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无法获取当前用户信息")

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
        if not evaluation:
            raise NotFoundError(f"评价ID {evaluation_id} 未找到")
        return evaluation
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
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
        if not evaluations:
            raise NotFoundError(f"未找到商品 {product_id} 的任何评价")
        return evaluations
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

@router.get("/buyer/{buyer_id}", response_model=List[EvaluationResponseSchema], response_model_by_alias=False)
async def get_evaluations_by_buyer_id_route(
    buyer_id: UUID, # Path parameter
    conn: pyodbc.Connection = Depends(get_db_connection),
    evaluation_service: EvaluationService = Depends(get_evaluation_service)
):
    """
    根据买家ID获取该买家的所有评价。
    """
    try:
        evaluations = await evaluation_service.get_evaluations_by_buyer_id(conn, buyer_id)
        if not evaluations:
            raise NotFoundError(f"未找到买家 {buyer_id} 的任何评价")
        return evaluations
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DALError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库操作失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"服务器内部错误: {e}")

# 您可以在此添加更多评价相关的路由，例如：
# - 获取某个商品的所有评价
# - 获取用户的所有评价
# - 用户删除自己的评价
# - 管理员管理评价等