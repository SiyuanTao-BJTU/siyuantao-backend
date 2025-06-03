import pyodbc
from typing import Optional, Callable, Awaitable, List, Dict, Any
from uuid import UUID

from app.exceptions import DALError, NotFoundError, IntegrityError, ForbiddenError

class EvaluationDAL:
    """Data Access Layer for Evaluations."""

    def __init__(self, execute_query_func: Callable[..., Awaitable[Optional[list[tuple]] | Optional[Dict[str, Any]] | Optional[List[Dict[str, Any]]]]]) -> None:
        """
        Initializes the EvaluationDAL with an asynchronous query execution function.

        Args:
            execute_query_func: An asynchronous function to execute database queries.
                                It should accept a SQL query string and parameters, 
                                and return an optional list of tuples (rows).
        """
        self._execute_query = execute_query_func

    async def create_evaluation(
        self,
        conn: pyodbc.Connection, 
        order_id: UUID,
        buyer_id: UUID,
        rating: int,
        comment: Optional[str]
    ) -> Dict[str, Any]:
        """
        Creates a new evaluation for an order by calling the sp_CreateEvaluation stored procedure.
        Assumes sp_CreateEvaluation is modified to SELECT the newly created evaluation data.
        """
        sql = "{CALL sp_CreateEvaluation (?, ?, ?, ?)}"
        params = (str(order_id), rating, comment, str(buyer_id))

        try:
            result = await self._execute_query(conn, sql, params, fetchone=True)
            if not result or result.get("评价ID") is None:
                raise DALError("创建评价失败，未返回评价ID")
            return result
        except pyodbc.Error as e:
            error_msg = str(e)
            if "50012" in error_msg:
                raise NotFoundError(f"评价创建失败: {error_msg}") from e
            elif "50013" in error_msg:
                raise ForbiddenError(f"评价创建失败: {error_msg}") from e
            elif "50014" in error_msg:
                raise IntegrityError(f"评价创建失败: {error_msg}") from e
            elif "50015" in error_msg:
                raise IntegrityError(f"评价创建失败: {error_msg}") from e
            elif "50016" in error_msg:
                raise ValueError(f"评价创建失败: {error_msg}") from e
            raise DALError(f"评价创建异常: {error_msg}") from e
        except Exception as e:
            raise DALError(f"评价创建时发生意外错误: {e}") from e

    async def get_evaluation_by_id(
        self,
        conn: pyodbc.Connection,
        evaluation_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Fetches a single evaluation by its ID."""
        sql = "{CALL sp_GetEvaluationById (?)}"
        params = (str(evaluation_id),)
        try:
            result = await self._execute_query(conn, sql, params, fetchone=True)
            return result
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"获取评价失败: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取评价时发生意外错误: {e}") from e

    async def get_evaluations_by_product_id(
        self,
        conn: pyodbc.Connection,
        product_id: UUID
    ) -> List[Dict[str, Any]]:
        """Fetches all evaluations for a specific product."""
        sql = "{CALL sp_GetEvaluationsByProductId (?)}"
        params = (str(product_id),)
        try:
            results = await self._execute_query(conn, sql, params, fetchall=True)
            return results
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"获取商品评价失败: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取商品评价时发生意外错误: {e}") from e

    async def get_evaluations_by_buyer_id(
        self,
        conn: pyodbc.Connection,
        buyer_id: UUID
    ) -> List[Dict[str, Any]]:
        """Fetches all evaluations made by a specific buyer."""
        sql = "{CALL sp_GetEvaluationsByBuyerId (?)}"
        params = (str(buyer_id),)
        try:
            results = await self._execute_query(conn, sql, params, fetchall=True)
            return results
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"获取买家评价失败: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取买家评价时发生意外错误: {e}") from e

    async def get_evaluations_by_seller_id(
        self,
        conn: pyodbc.Connection,
        seller_id: UUID
    ) -> List[Dict[str, Any]]:
        """Fetches all evaluations received by a specific seller."""
        sql = "{CALL sp_GetEvaluationsBySellerId (?)}"
        params = (str(seller_id),)
        try:
            results = await self._execute_query(conn, sql, params, fetchall=True)
            return results
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"获取卖家评价失败: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取卖家评价时发生意外错误: {e}") from e

    async def get_all_evaluations(
        self,
        conn: pyodbc.Connection,
        product_id: Optional[UUID] = None,
        seller_id: Optional[UUID] = None,
        buyer_id: Optional[UUID] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        page_number: int = 1,
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetches all evaluations, with optional filters and pagination, for admin view.
        Calls a stored procedure like sp_GetAllEvaluations.
        """
        sql = "{CALL sp_GetAllEvaluations (?, ?, ?, ?, ?, ?, ?)}"
        params = (
            str(product_id) if product_id else None,
            str(seller_id) if seller_id else None,
            str(buyer_id) if buyer_id else None,
            min_rating,
            max_rating,
            page_number,
            page_size
        )
        try:
            results = await self._execute_query(conn, sql, params, fetchall=True)
            return results
        except pyodbc.Error as e:
            error_msg = str(e)
            raise DALError(f"获取所有评价失败: {error_msg}") from e
        except Exception as e:
            raise DALError(f"获取所有评价时发生意外错误: {e}") from e

    async def delete_evaluation(
        self,
        conn: pyodbc.Connection,
        evaluation_id: UUID
    ) -> None:
        """
        Deletes an evaluation by its ID. Typically used by admin.
        Calls a stored procedure like sp_DeleteEvaluation.
        """
        sql = "{CALL sp_DeleteEvaluation (?)}"
        params = (str(evaluation_id),)
        try:
            await self._execute_query(conn, sql, params, fetchone=False) # Non-query execution
        except pyodbc.Error as e:
            error_msg = str(e)
            if "50001" in error_msg: # Assuming specific error code for not found/permission
                raise NotFoundError(f"删除评价失败: {error_msg}") from e
            raise DALError(f"删除评价异常: {error_msg}") from e
        except Exception as e:
            raise DALError(f"删除评价时发生意外错误: {e}") from e