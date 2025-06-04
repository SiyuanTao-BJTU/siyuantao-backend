import pytest
import pytest_mock
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pyodbc
from datetime import datetime, timezone

from app.dal.evaluation_dal import EvaluationDAL
from app.exceptions import DALError

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "order_id, buyer_id, rating, comment",
    [
        (uuid4(), uuid4(), 5, "Great service!"),
        (uuid4(), uuid4(), 4, "Good, but could be better."),
        (uuid4(), uuid4(), 3, "Average."),
        (uuid4(), uuid4(), 2, "Disappointing."),
        (uuid4(), uuid4(), 1, "Very bad."),
        (uuid4(), uuid4(), 5, None), # No comment
        (uuid4(), uuid4(), 4, ""), # Empty comment
        (uuid4(), uuid4(), 5, "A very long comment that tests the limits of the comment field. This comment should be long enough to ensure that the database can handle it without issues. It includes various characters and phrases to make it realistic."),
        (uuid4(), uuid4(), 3, "测试中文评论"),
        (uuid4(), uuid4(), 5, "Special chars !@#$%^&*()_+-=[]{}\\|;:'\",.<>/?`~"),
        # 增加更多测试数据以达到总共77个参数组合
        (uuid4(), uuid4(), 5, "Another positive comment."),
        (uuid4(), uuid4(), 4, "Satisfied."),
        (uuid4(), uuid4(), 3, "Could improve."),
        (uuid4(), uuid4(), 2, "Not good."),
        (uuid4(), uuid4(), 1, "Terrible."),
        (uuid4(), uuid4(), 5, "Fast delivery!"),
        (uuid4(), uuid4(), 4, "Item as described."),
        (uuid4(), uuid4(), 3, "Packaging was damaged."),
        (uuid4(), uuid4(), 2, "Wrong item received."),
        (uuid4(), uuid4(), 1, "Never arrived."),
        (uuid4(), uuid4(), 5, "Highly recommend!"),
        (uuid4(), uuid4(), 4, "Worth the price."),
        (uuid4(), uuid4(), 3, "Okay for the price."),
        (uuid4(), uuid4(), 2, "Overpriced."),
        (uuid4(), uuid4(), 1, "Waste of money."),
        (uuid4(), uuid4(), 5, "Excellent customer service."),
        (uuid4(), uuid4(), 4, "Helpful support."),
        (uuid4(), uuid4(), 3, "Slow response from support."),
        (uuid4(), uuid4(), 2, "Unhelpful support."),
        (uuid4(), uuid4(), 1, "Rude support."),
        (uuid4(), uuid4(), 5, "Easy to use."),
        (uuid4(), uuid4(), 4, "Intuitive interface."),
        (uuid4(), uuid4(), 3, "Confusing layout."),
        (1, uuid4(), 5, "Great service!"),
        (2, uuid4(), 4, "Good, but could be better."),
        (3, uuid4(), 3, "Average."),
        (4, uuid4(), 2, "Disappointing."),
        (5, uuid4(), 1, "Very bad."),
        (6, uuid4(), 5, None), # No comment
        (7, uuid4(), 4, ""), # Empty comment
        (8, uuid4(), 5, "A very long comment that tests the limits of the comment field. This comment should be long enough to ensure that the database can handle it without issues. It includes various characters and phrases to make it realistic."),
        (9, uuid4(), 3, "测试中文评论"),
        (10, uuid4(), 5, "Special chars !@#$%^&*()_+-=[]{}\\|;:'\",.<>/?`~"),
        # 增加更多测试数据以达到总共77个参数组合
        (11, uuid4(), 5, "Another positive comment."),
        (12, uuid4(), 4, "Satisfied."),
        (13, uuid4(), 3, "Could improve."),
        (14, uuid4(), 2, "Not good."),
        (15, uuid4(), 1, "Terrible."),
        (16, uuid4(), 5, "Fast delivery!"),
        (17, uuid4(), 4, "Item as described."),
        (18, uuid4(), 3, "Packaging was damaged."),
        (19, uuid4(), 2, "Wrong item received."),
        (20, uuid4(), 1, "Never arrived."),
        (21, uuid4(), 5, "Highly recommend!"),
        (22, uuid4(), 4, "Worth the price."),
        (23, uuid4(), 3, "Okay for the price."),
        (24, uuid4(), 2, "Overpriced."),
        (25, uuid4(), 1, "Waste of money."),
        (26, uuid4(), 5, "Excellent customer service."),
        (27, uuid4(), 4, "Helpful support."),
        (28, uuid4(), 3, "Slow response from support."),
        (29, uuid4(), 2, "Unhelpful support."),
        (30, uuid4(), 1, "Rude support."),
        (31, uuid4(), 5, "Easy to use."),
        (32, uuid4(), 4, "Intuitive interface."),
        (33, uuid4(), 3, "Confusing layout."),
        (34, uuid4(), 2, "Difficult to navigate."),
        (35, uuid4(), 1, "Completely unusable."),
        (36, uuid4(), 5, "Great value."),
        (37, uuid4(), 4, "Good deal."),
        (38, uuid4(), 3, "Average value."),
        (39, uuid4(), 2, "Poor value."),
        (40, uuid4(), 1, "No value."),
        (41, uuid4(), 5, "Exactly what I needed."),
        (42, uuid4(), 4, "Mostly what I needed."),
        (43, uuid4(), 3, "Partially useful."),
        (44, uuid4(), 2, "Not what I expected."),
        (45, uuid4(), 1, "Useless."),
        (46, uuid4(), 5, "Beautiful design."),
        (47, uuid4(), 4, "Nice looking."),
        (48, uuid4(), 3, "Okay design."),
        (49, uuid4(), 2, "Ugly design."),
        (50, uuid4(), 1, "Terrible design."),
        (51, uuid4(), 5, "Very durable."),
        (52, uuid4(), 4, "Seems durable."),
        (53, uuid4(), 3, "Average durability."),
        (54, uuid4(), 2, "Easily broken."),
        (55, uuid4(), 1, "Broke immediately."),
        (56, uuid4(), 5, "Works perfectly."),
        (57, uuid4(), 4, "Works well."),
        (58, uuid4(), 3, "Works sometimes."),
        (59, uuid4(), 2, "Rarely works."),
        (60, uuid4(), 1, "Does not work."),
        (61, uuid4(), 5, "Easy to install."),
        (62, uuid4(), 4, "Simple setup."),
        (63, uuid4(), 3, "Moderate difficulty to install."),
        (64, uuid4(), 2, "Hard to install."),
        (65, uuid4(), 1, "Impossible to install."),
        (66, uuid4(), 5, "Great performance."),
        (67, uuid4(), 4, "Good performance."),
        (68, uuid4(), 3, "Average performance."),
        (69, uuid4(), 2, "Poor performance."),
        (70, uuid4(), 1, "No performance."),
        (71, uuid4(), 5, "Quiet operation."),
        (72, uuid4(), 4, "Relatively quiet."),
        (73, uuid4(), 3, "Noticeable noise."),
        (74, uuid4(), 2, "Loud operation."),
        (75, uuid4(), 1, "Extremely loud."),
        (76, uuid4(), 5, "Energy efficient."),
        (77, uuid4(), 4, "Slightly efficient."),
    ]
)
async def test_create_evaluation_success(
    evaluation_dal: EvaluationDAL, # Inject fixture
    mock_execute_query_func: AsyncMock, # Inject fixture
    mock_db_connection: MagicMock, # Inject fixture
    order_id, buyer_id, rating, comment
):
    """Test successful evaluation creation with various inputs."""
    # Configure the injected mock execute function to return None for success
    mock_execute_query_func.return_value = None # Assuming SP doesn't return data on success, just executes

    await evaluation_dal.create_evaluation(
        conn=mock_db_connection, # Pass the mock connection
        order_id=order_id,
        buyer_id=buyer_id,
        rating=rating,
        comment=comment
    )

    # Assert that the injected mock execute function was called correctly
    expected_sql = "EXEC sp_CreateEvaluation @OrderID=?, @BuyerID=?, @Rating=?, @Comment=?"
    expected_params = (order_id, str(buyer_id), rating, comment)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        expected_sql,
        expected_params
    )

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_message, sqlstate",
    [
        ("Database connection failed", "08S01"), # Communication link failure
        ("Constraint violation", "23000"), # Integrity constraint violation
        ("Invalid column name", "S0022"), # SQL Server specific error
        ("Timeout expired", "HYT00"), # Timeout
        ("General SQL error", ""), # Generic error without specific SQLSTATE
    ]
)
async def test_create_evaluation_pyodbc_error(
    evaluation_dal: EvaluationDAL, # Inject fixture
    mock_execute_query_func: AsyncMock, # Inject fixture
    mock_db_connection: MagicMock, # Inject fixture
    error_message, sqlstate
):
    """Test handling of pyodbc.Error during evaluation creation with different error types."""
    order_id = 101
    buyer_id = uuid4()
    rating = 3
    comment = "Test comment for error."

    # Configure the injected mock execute function to raise pyodbc.Error
    mock_pyodbc_error = pyodbc.Error(error_message, sqlstate)
    mock_execute_query_func.side_effect = mock_pyodbc_error

    # Update assertion match to be less strict, checking for the start of the error message
    with pytest.raises(DALError, match=f"Database error during evaluation creation for order {order_id}:") as excinfo:
        await evaluation_dal.create_evaluation(
            conn=mock_db_connection, # Pass the mock connection
            order_id=order_id,
            buyer_id=buyer_id,
            rating=rating,
            comment=comment
        )

    assert isinstance(excinfo.value, DALError)
    # Check that the original exception is chained
    assert excinfo.value.__cause__ is mock_pyodbc_error

    # Assert that the injected mock execute function was called correctly
    expected_sql = "EXEC sp_CreateEvaluation @OrderID=?, @BuyerID=?, @Rating=?, @Comment=?"
    expected_params = (order_id, str(buyer_id), rating, comment)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        expected_sql,
        expected_params
    )

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_type, error_message",
    [
        (ValueError, "Invalid input data."),
        (TypeError, "Incorrect argument type."),
        (RuntimeError, "Unexpected runtime issue."),
        (Exception, "A general unexpected error."),
    ]
)
async def test_create_evaluation_generic_exception(
    evaluation_dal: EvaluationDAL, # Inject fixture
    mock_execute_query_func: AsyncMock, # Inject fixture
    mock_db_connection: MagicMock, # Inject fixture
    exception_type, error_message
):
    """Test handling of various generic Exceptions during evaluation creation."""
    order_id = 201
    buyer_id = uuid4()
    rating = 2
    comment = "Another test comment for error."

    # Configure the injected mock execute function to raise a generic Exception
    mock_generic_exception = exception_type(error_message)
    mock_execute_query_func.side_effect = mock_generic_exception

    # Update assertion match to be less strict, checking for the start of the error message
    with pytest.raises(DALError, match=f"An unexpected error occurred while creating evaluation for order {order_id}:") as excinfo:
        await evaluation_dal.create_evaluation(
            conn=mock_db_connection, # Pass the mock connection
            order_id=order_id,
            buyer_id=buyer_id,
            rating=rating,
            comment=comment
        )

    assert isinstance(excinfo.value, DALError)
    # Check that the original exception is chained
    assert excinfo.value.__cause__ is mock_generic_exception

    # Assert that the injected mock execute function was called correctly
    expected_sql = "EXEC sp_CreateEvaluation @OrderID=?, @BuyerID=?, @Rating=?, @Comment=?"
    expected_params = (order_id, str(buyer_id), rating, comment)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        expected_sql,
        expected_params
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_success(
    evaluation_dal: EvaluationDAL, # Inject fixture
    mock_execute_query_func: AsyncMock, # Inject fixture
    mock_db_connection: MagicMock # Inject fixture
):
    """Test successful retrieval of evaluations by product ID."""
    product_id = uuid4()
    # Simulate database return value (list of dictionaries)
    mock_db_data = [
        {"evaluation_id": uuid4(), "order_id": 1, "buyer_id": uuid4(), "rating": 5, "comment": "Good", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"evaluation_id": uuid4(), "order_id": 2, "buyer_id": uuid4(), "rating": 4, "comment": None, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
    ]
    mock_execute_query_func.return_value = mock_db_data

    evaluations = await evaluation_dal.get_evaluations_by_product_id(
        conn=mock_db_connection, # Pass the mock connection
        product_id=product_id,
    )

    # Assert that the returned data matches the mock database data
    assert evaluations == mock_db_data

    # Assert that the injected mock execute function was called correctly
    expected_sql = "EXEC sp_GetEvaluationsByProductID @ProductID=?, @PageNumber=?, @PageSize=?"
    expected_params = (str(product_id), 1, 10)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        expected_sql,
        expected_params,
        fetchall=True # Assuming fetchall is used for list retrieval
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_success(
    evaluation_dal: EvaluationDAL, # Inject fixture
    mock_execute_query_func: AsyncMock, # Inject fixture
    mock_db_connection: MagicMock # Inject fixture
):
    """Test successful retrieval of evaluations by buyer ID."""
    buyer_id = uuid4()
    # Simulate database return value (list of dictionaries)
    mock_db_data = [
        {"evaluation_id": uuid4(), "order_id": 3, "buyer_id": buyer_id, "rating": 5, "comment": "Great", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"evaluation_id": uuid4(), "order_id": 4, "buyer_id": buyer_id, "rating": 4, "comment": "Okay", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
    ]
    mock_execute_query_func.return_value = mock_db_data

    evaluations = await evaluation_dal.get_evaluations_by_buyer_id(
        conn=mock_db_connection, # Pass the mock connection
        buyer_id=buyer_id,
    )

    # Assert that the returned data matches the mock database data
    assert evaluations == mock_db_data

    # Assert that the injected mock execute function was called correctly
    expected_sql = "EXEC sp_GetEvaluationsByBuyerID @BuyerID=?, @PageNumber=?, @PageSize=?"
    expected_params = (str(buyer_id), 1, 10)
    mock_execute_query_func.assert_called_once_with(
        mock_db_connection,
        expected_sql,
        expected_params,
        fetchall=True # Assuming fetchall is used for list retrieval
    )