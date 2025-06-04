import pyodbc
from uuid import UUID
from typing import Optional, List

from app.dal.evaluation_dal import EvaluationDAL # Assuming EvaluationDAL is in app.dal.evaluation_dal
from app.schemas.evaluation_schemas import ( # Assuming evaluation-related Pydantic schemas are in app.schemas.evaluation_schemas
    EvaluationCreateSchema,
    EvaluationResponseSchema
)
# If needed, import Order related schemas or services for validation (e.g., to check if order can be evaluated)
# from app.services.order_service import OrderService 
from app.exceptions import DALError, NotFoundError, ForbiddenError, IntegrityError # Import IntegrityError

class EvaluationService:
    """Service layer for evaluation management."""

    def __init__(self, evaluation_dal: EvaluationDAL):
        """
        Initializes the EvaluationService with an EvaluationDAL instance.

        Args:
            evaluation_dal: An instance of EvaluationDAL for database interactions.
        """
        self.evaluation_dal = evaluation_dal
        # If cross-service logic is needed, e.g., to check order status before allowing evaluation:
        # self.order_service = order_service 

    async def create_evaluation(
        self,
        conn: pyodbc.Connection,
        evaluation_data: EvaluationCreateSchema,
        buyer_id: UUID
    ) -> EvaluationResponseSchema:
        """
        Creates a new evaluation for an order.

        Args:
            conn: The database connection object.
            evaluation_data: Data for creating the evaluation (order_id, rating, comment).
            buyer_id: The ID of the user (buyer) submitting the evaluation.

        Returns:
            The created evaluation details.

        Raises:
            DALError: If there's an issue with database interaction.
            NotFoundError: If the order to be evaluated is not found.
            ValueError: If input data is invalid (e.g., rating out of range).
            ForbiddenError: If the user is not authorized to evaluate the order (e.g., not the buyer).
            IntegrityError: If the order has already been evaluated.
        """
        try:
            # 1. Validate rating (e.g., 1-5). Pydantic schema handles this, but service layer can add extra validation.
            if not (1 <= evaluation_data.rating <= 5):
                # Although Pydantic schema has gt/le, this ensures robust service-level validation.
                raise ValueError("评分必须在 1 到 5 之间。")

            new_evaluation_data = await self.evaluation_dal.create_evaluation(
                conn=conn,
                order_id=evaluation_data.order_id,
                buyer_id=buyer_id, # Pass the authenticated buyer_id
                rating=evaluation_data.rating,
                comment=evaluation_data.comment
            )

            # DAL's create_evaluation now returns the full evaluation dictionary on success.
            if not new_evaluation_data or not isinstance(new_evaluation_data, dict):
                raise DALError("Evaluation creation failed: Unexpected response from database.")

            # Convert the dictionary result to the EvaluationResponseSchema
            return EvaluationResponseSchema(**new_evaluation_data)

        except (NotFoundError, ValueError, ForbiddenError, IntegrityError, DALError): # Catch IntegrityError here
            raise # Re-raise specific business logic or DAL errors
        except Exception as e:
            raise DALError(f"创建评价时发生意外错误: {e}") from e

    async def get_evaluations_by_product_id(
        self,
        conn: pyodbc.Connection,
        product_id: UUID
    ) -> List[EvaluationResponseSchema]:
        """获取指定商品的评价列表。"""
        evaluations_data = await self.evaluation_dal.get_evaluations_by_product_id(conn, product_id)
        return [EvaluationResponseSchema(**e) for e in evaluations_data]

    async def get_evaluations_by_buyer_id(
        self,
        conn: pyodbc.Connection,
        buyer_id: UUID
    ) -> List[EvaluationResponseSchema]:
        """获取指定买家的评价列表。"""
        evaluations_data = await self.evaluation_dal.get_evaluations_by_buyer_id(conn, buyer_id)
        return [EvaluationResponseSchema(**e) for e in evaluations_data]

    async def get_evaluations_by_seller_id(
        self,
        conn: pyodbc.Connection,
        seller_id: UUID
    ) -> List[EvaluationResponseSchema]:
        """获取指定卖家的评价列表。"""
        evaluations_data = await self.evaluation_dal.get_evaluations_by_seller_id(conn, seller_id)
        return [EvaluationResponseSchema(**e) for e in evaluations_data]

    async def get_evaluation_by_id(
        self,
        conn: pyodbc.Connection,
        evaluation_id: UUID
    ) -> Optional[EvaluationResponseSchema]:
        """根据评价ID获取评价详情。"""
        evaluation_data = await self.evaluation_dal.get_evaluation_by_id(conn, evaluation_id)
        if evaluation_data:
            return EvaluationResponseSchema(**evaluation_data)
        return None


    async def get_all_evaluations_for_admin(
        self,
        conn: pyodbc.Connection,
        product_id: Optional[UUID] = None,
        seller_id: Optional[UUID] = None,
        buyer_id: Optional[UUID] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        page_number: int = 1,
        page_size: int = 10
    ) -> List[EvaluationResponseSchema]:
        """
        Retrieves a list of all evaluations for administrative purposes, with optional filters and pagination.
        """
        try:
            evaluations_data = await self.evaluation_dal.get_all_evaluations(
                conn,
                product_id,
                seller_id,
                buyer_id,
                min_rating,
                max_rating,
                page_number,
                page_size
            )
            return [EvaluationResponseSchema(**e) for e in evaluations_data]
        except DALError as e:
            raise DALError(f"获取所有评价失败: {e}") from e
        except Exception as e:
            raise DALError(f"获取所有评价时发生意外错误: {e}") from e


    async def delete_evaluation_by_admin(
        self,
        conn: pyodbc.Connection,
        evaluation_id: UUID,
        admin_id: UUID # For authorization, though actual check happens in router/middleware
    ) -> None:
        """
        Deletes an evaluation by its ID, for administrative purposes.
        """
        try:
            # No need for explicit admin permission check here if it's handled in the router/middleware
            await self.evaluation_dal.delete_evaluation(conn, evaluation_id)
        except (NotFoundError, DALError): # Re-raise specific exceptions
            raise
        except Exception as e:
            raise DALError(f"管理员删除评价 {evaluation_id} 时发生意外错误: {e}") from e
