import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.services.evaluation_service import EvaluationService
from app.dal.evaluation_dal import EvaluationDAL
from app.schemas.evaluation_schemas import EvaluationCreateSchema, EvaluationResponseSchema
from app.exceptions import DALError, NotFoundError, ForbiddenError
import pytest_mock

# Mock data
TEST_BUYER_ID = uuid4()
TEST_SELLER_ID = uuid4() # Assuming seller_id is relevant for evaluations (e.g., seller being evaluated)
TEST_PRODUCT_ID = uuid4()
TEST_ORDER_ID = uuid4()
TEST_EVALUATION_ID = uuid4()

@pytest.fixture
def mock_evaluation_dal(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Fixture to mock EvaluationDAL."""
    # Re-create the autospec to include the newly added methods in EvaluationDAL
    return mocker.create_autospec(EvaluationDAL, instance=True, spec_set=True)

@pytest.fixture
def evaluation_service(mock_evaluation_dal: AsyncMock) -> EvaluationService:
    """Fixture to create EvaluationService with mocked DAL."""
    return EvaluationService(evaluation_dal=mock_evaluation_dal)

@pytest.fixture
def mock_conn() -> MagicMock:
    """Fixture for a mock database connection."""
    return MagicMock()

# Mock EvaluationCreateSchema instance
@pytest.fixture
def mock_evaluation_create_schema():
    return EvaluationCreateSchema(
        order_id=TEST_ORDER_ID,
        product_id=TEST_PRODUCT_ID,
        user_id=TEST_BUYER_ID,
        rating=5,
        comment="Great product!"
    )

# Mock EvaluationResponseSchema instance
@pytest.fixture
def base_mock_evaluation_response_schema():
    return EvaluationResponseSchema(
        evaluation_id=TEST_EVALUATION_ID,
        order_id=TEST_ORDER_ID,
        product_id=TEST_PRODUCT_ID,
        buyer_id=TEST_BUYER_ID,
        seller_id=TEST_SELLER_ID, # Include seller_id
        rating=5,
        comment="Great product!",
        created_at=datetime.now(timezone.utc)
    )


# --- Test create_evaluation ---
@pytest.mark.asyncio
async def test_create_evaluation_success(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock,
    mock_evaluation_create_schema: EvaluationCreateSchema, # Use fixture
    base_mock_evaluation_response_schema: EvaluationResponseSchema # Use fixture
):
    """测试成功创建一个评价。"""
    # Arrange
    new_evaluation_id_from_dal = uuid4()
    # Simulate DAL create_evaluation returning the new evaluation ID
    mock_evaluation_dal.create_evaluation.return_value = {'EvaluationID': str(new_evaluation_id_from_dal)} # Assuming SP returns EvaluationID in a dict

    # Simulate DAL get_evaluation_by_id returning the full evaluation data as a dictionary
    mock_dal_return_data = {
        'EvaluationID': str(new_evaluation_id_from_dal),
        'OrderID': str(mock_evaluation_create_schema.order_id),
        'ProductID': str(mock_evaluation_create_schema.product_id),
        'BuyerID': str(mock_evaluation_create_schema.user_id),
        'SellerID': str(TEST_SELLER_ID), # Assuming seller_id is retrieved by DAL or SP
        'Rating': mock_evaluation_create_schema.rating,
        'Comment': mock_evaluation_create_schema.comment,
        'CreatedAt': datetime.now(timezone.utc)
    }
    mock_evaluation_dal.get_evaluation_by_id.return_value = mock_dal_return_data

    # Act
    created_evaluation = await evaluation_service.create_evaluation(
        mock_conn,
        mock_evaluation_create_schema,
        mock_evaluation_create_schema.user_id # Pass buyer_id
    )

    # Assert DAL methods were called correctly
    mock_evaluation_dal.create_evaluation.assert_called_once_with(
        mock_conn,
        order_id=mock_evaluation_create_schema.order_id,
        buyer_id=mock_evaluation_create_schema.user_id,
        rating=mock_evaluation_create_schema.rating,
        comment=mock_evaluation_create_schema.comment
    )
    mock_evaluation_dal.get_evaluation_by_id.assert_called_once_with(
        mock_conn,
        evaluation_id=new_evaluation_id_from_dal
    )

    # Assert the returned object is an EvaluationResponseSchema instance
    assert isinstance(created_evaluation, EvaluationResponseSchema)

    # Assert the returned schema matches the expected data
    expected_evaluation_schema = EvaluationResponseSchema(**mock_dal_return_data)
    # Compare all fields except created_at which might have microsecond differences
    assert created_evaluation.model_dump(mode='json', exclude={'created_at'}) == expected_evaluation_schema.model_dump(mode='json', exclude={'created_at'})
    # Compare created_at separately with tolerance if needed, or just check type/presence
    assert isinstance(created_evaluation.created_at, datetime)
    assert created_evaluation.created_at.tzinfo is not None # Check if timezone-aware

@pytest.mark.asyncio
async def test_create_evaluation_value_error_rating_out_of_range(
    evaluation_service: EvaluationService,
    mock_conn: MagicMock
):
    """测试评分超出范围时抛出ValueError。"""
    invalid_evaluation_data = EvaluationCreateSchema(
        order_id=uuid4(),
        product_id=uuid4(),
        user_id=uuid4(),
        rating=6, # Invalid rating
        comment="Invalid rating test"
    )

    with pytest.raises(ValueError, match="Rating must be between 1 and 5."):
        await evaluation_service.create_evaluation(
            mock_conn,
            invalid_evaluation_data,
            invalid_evaluation_data.user_id
        )


@pytest.mark.asyncio
async def test_create_evaluation_dal_error(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock,
    mock_evaluation_create_schema: EvaluationCreateSchema # Use fixture
):
    """测试DAL创建评价时发生错误。"""
    mock_evaluation_dal.create_evaluation.side_effect = DALError("DB create error")

    with pytest.raises(DALError, match="DB create error"):
        await evaluation_service.create_evaluation(
            mock_conn,
            mock_evaluation_create_schema,
            mock_evaluation_create_schema.user_id
        )
    
    mock_evaluation_dal.create_evaluation.assert_called_once_with(
        mock_conn,
        order_id=mock_evaluation_create_schema.order_id,
        buyer_id=mock_evaluation_create_schema.user_id,
        rating=mock_evaluation_create_schema.rating,
        comment=mock_evaluation_create_schema.comment
    )
    mock_evaluation_dal.get_evaluation_by_id.assert_not_called() # Should not be called if creation fails


@pytest.mark.asyncio
async def test_create_evaluation_not_found_error(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock,
    mock_evaluation_create_schema: EvaluationCreateSchema # Use fixture
):
    """测试创建评价后找不到评价（DAL Get返回None）。"""
    new_evaluation_id_from_dal = uuid4()
    mock_evaluation_dal.create_evaluation.return_value = {'EvaluationID': str(new_evaluation_id_from_dal)}
    mock_evaluation_dal.get_evaluation_by_id.return_value = None # Simulate not found after creation

    with pytest.raises(NotFoundError, match=f"Evaluation with ID {new_evaluation_id_from_dal} not found after creation."):
        await evaluation_service.create_evaluation(
            mock_conn,
            mock_evaluation_create_schema,
            mock_evaluation_create_schema.user_id
        )

    mock_evaluation_dal.create_evaluation.assert_called_once_with(
        mock_conn,
        order_id=mock_evaluation_create_schema.order_id,
        buyer_id=mock_evaluation_create_schema.user_id,
        rating=mock_evaluation_create_schema.rating,
        comment=mock_evaluation_create_schema.comment
    )
    mock_evaluation_dal.get_evaluation_by_id.assert_called_once_with(
        mock_conn,
        evaluation_id=new_evaluation_id_from_dal
    )

@pytest.mark.asyncio
async def test_create_evaluation_forbidden_error(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock,
    mock_evaluation_create_schema: EvaluationCreateSchema # Use fixture
):
    """测试创建评价时DAL抛出ForbiddenError（例如，不是买家）。"""
    mock_evaluation_dal.create_evaluation.side_effect = ForbiddenError("Only buyer can evaluate.")

    with pytest.raises(ForbiddenError, match="Only buyer can evaluate."):
        await evaluation_service.create_evaluation(
            mock_conn,
            mock_evaluation_create_schema,
            mock_evaluation_create_schema.user_id
        )
    
    mock_evaluation_dal.create_evaluation.assert_called_once_with(
        mock_conn,
        order_id=mock_evaluation_create_schema.order_id,
        buyer_id=mock_evaluation_create_schema.user_id,
        rating=mock_evaluation_create_schema.rating,
        comment=mock_evaluation_create_schema.comment
    )
    mock_evaluation_dal.get_evaluation_by_id.assert_not_called() # Should not be called if creation fails

@pytest.mark.asyncio
async def test_create_evaluation_unexpected_exception(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock,
    mock_evaluation_create_schema: EvaluationCreateSchema # Use fixture
):
    """测试创建评价时发生意外异常。"""
    mock_evaluation_dal.create_evaluation.side_effect = Exception("Unexpected error")

    with pytest.raises(Exception, match="Unexpected error"):
        await evaluation_service.create_evaluation(
            mock_conn,
            mock_evaluation_create_schema,
            mock_evaluation_create_schema.user_id
        )
    
    mock_evaluation_dal.create_evaluation.assert_called_once_with(
        mock_conn,
        order_id=mock_evaluation_create_schema.order_id,
        buyer_id=mock_evaluation_create_schema.user_id,
        rating=mock_evaluation_create_schema.rating,
        comment=mock_evaluation_create_schema.comment
    )
    mock_evaluation_dal.get_evaluation_by_id.assert_not_called() # Should not be called if creation fails


# --- Test get_evaluations_by_product_id ---
@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_success(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试成功获取商品评价列表。"""
    product_id = uuid4()
    # Simulate DAL returning a list of evaluation dictionaries
    mock_dal_return_value = [
        {
            'EvaluationID': str(uuid4()),
            'OrderID': str(uuid4()),
            'ProductID': str(product_id),
            'BuyerID': str(uuid4()),
            'SellerID': str(uuid4()),
            'Rating': 5,
            'Comment': 'Good',
            'CreatedAt': datetime.now(timezone.utc)
        },
        {
            'EvaluationID': str(uuid4()),
            'OrderID': str(uuid4()),
            'ProductID': str(product_id),
            'BuyerID': str(uuid4()),
            'SellerID': str(uuid4()),
            'Rating': 4,
            'Comment': 'Okay',
            'CreatedAt': datetime.now(timezone.utc)
        }
    ]
    mock_evaluation_dal.get_evaluations_by_product_id.return_value = mock_dal_return_value

    evaluations = await evaluation_service.get_evaluations_by_product_id(
        mock_conn,
        product_id
    )

    # The Service should convert the dictionaries to schemas
    assert isinstance(evaluations, list)
    assert len(evaluations) == len(mock_dal_return_value)
    assert all(isinstance(e, EvaluationResponseSchema) for e in evaluations)

    # Compare the returned schemas with the expected schemas
    expected_evaluations = [EvaluationResponseSchema(**data) for data in mock_dal_return_value]
    # Compare dictionaries converted from schemas, excluding datetime for simplicity or comparing datetimes separately
    assert [e.model_dump(mode='json', exclude={'created_at'}) for e in evaluations] == [e.model_dump(mode='json', exclude={'created_at'}) for e in expected_evaluations]
    for i in range(len(evaluations)):
         assert evaluations[i].created_at.replace(microsecond=0) == expected_evaluations[i].created_at.replace(microsecond=0)

    mock_evaluation_dal.get_evaluations_by_product_id.assert_called_once_with(
        mock_conn,
        product_id=product_id
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_no_evaluations(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试获取商品评价列表时没有评价。"""
    product_id = uuid4()
    mock_evaluation_dal.get_evaluations_by_product_id.return_value = []

    evaluations = await evaluation_service.get_evaluations_by_product_id(
        mock_conn,
        product_id
    )

    assert isinstance(evaluations, list)
    assert len(evaluations) == 0
    mock_evaluation_dal.get_evaluations_by_product_id.assert_called_once_with(
        mock_conn,
        product_id=product_id
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_dal_error(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试DAL获取商品评价列表时发生错误。"""
    product_id = uuid4()
    mock_evaluation_dal.get_evaluations_by_product_id.side_effect = DALError("DB fetch error")

    with pytest.raises(DALError, match="DB fetch error"):
        await evaluation_service.get_evaluations_by_product_id(
            mock_conn,
            product_id
        )
    
    mock_evaluation_dal.get_evaluations_by_product_id.assert_called_once_with(
        mock_conn,
        product_id=product_id
    )

# --- Test get_evaluations_by_buyer_id ---
@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_success(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试成功获取买家评价列表。"""
    buyer_id = uuid4()
    # Simulate DAL returning a list of evaluation dictionaries
    mock_dal_return_value = [
        {
            'EvaluationID': str(uuid4()),
            'OrderID': str(uuid4()),
            'ProductID': str(uuid4()),
            'BuyerID': str(buyer_id),
            'SellerID': str(uuid4()),
            'Rating': 5,
            'Comment': 'Good',
            'CreatedAt': datetime.now(timezone.utc)
        },
        {
            'EvaluationID': str(uuid4()),
            'OrderID': str(uuid4()),
            'ProductID': str(uuid4()),
            'BuyerID': str(buyer_id),
            'SellerID': str(uuid4()),
            'Rating': 4,
            'Comment': 'Okay',
            'CreatedAt': datetime.now(timezone.utc)
        }
    ]
    mock_evaluation_dal.get_evaluations_by_buyer_id.return_value = mock_dal_return_value

    evaluations = await evaluation_service.get_evaluations_by_buyer_id(
        mock_conn,
        buyer_id
    )

    # The Service should convert the dictionaries to schemas
    assert isinstance(evaluations, list)
    assert len(evaluations) == len(mock_dal_return_value)
    assert all(isinstance(e, EvaluationResponseSchema) for e in evaluations)

    # Compare the returned schemas with the expected schemas
    expected_evaluations = [EvaluationResponseSchema(**data) for data in mock_dal_return_value]
    # Compare dictionaries converted from schemas, excluding datetime for simplicity or comparing datetimes separately
    assert [e.model_dump(mode='json', exclude={'created_at'}) for e in evaluations] == [e.model_dump(mode='json', exclude={'created_at'}) for e in expected_evaluations]
    for i in range(len(evaluations)):
         assert evaluations[i].created_at.replace(microsecond=0) == expected_evaluations[i].created_at.replace(microsecond=0)

    mock_evaluation_dal.get_evaluations_by_buyer_id.assert_called_once_with(
        mock_conn,
        buyer_id=buyer_id
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_no_evaluations(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试获取买家评价列表时没有评价。"""
    buyer_id = uuid4()
    mock_evaluation_dal.get_evaluations_by_buyer_id.return_value = []

    evaluations = await evaluation_service.get_evaluations_by_buyer_id(
        mock_conn,
        buyer_id
    )

    assert isinstance(evaluations, list)
    assert len(evaluations) == 0
    mock_evaluation_dal.get_evaluations_by_buyer_id.assert_called_once_with(
        mock_conn,
        buyer_id=buyer_id
    )

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_dal_error(
    evaluation_service: EvaluationService,
    mock_evaluation_dal: AsyncMock,
    mock_conn: MagicMock
):
    """测试DAL获取买家评价列表时发生错误。"""
    buyer_id = uuid4()
    mock_evaluation_dal.get_evaluations_by_buyer_id.side_effect = DALError("DB fetch error")

    with pytest.raises(DALError, match="DB fetch error"):
        await evaluation_service.get_evaluations_by_buyer_id(
            mock_conn,
            buyer_id
        )
    
    mock_evaluation_dal.get_evaluations_by_buyer_id.assert_called_once_with(
        mock_conn,
        buyer_id=buyer_id
    )
