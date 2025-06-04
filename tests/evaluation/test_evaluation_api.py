import pytest
from fastapi import status, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone
import pytest_mock
import pyodbc
import uuid

from app.main import app
from app.dependencies import get_evaluation_service, get_current_user, get_db_connection
from app.services.evaluation_service import EvaluationService
from app.schemas.evaluation_schemas import EvaluationCreateSchema, EvaluationResponseSchema
from app.exceptions import IntegrityError, ForbiddenError, NotFoundError, DALError

# Helper function to create a dummy EvaluationResponseSchema instance
def create_dummy_evaluation_response_schema(buyer_id: uuid.UUID) -> EvaluationResponseSchema:
    return EvaluationResponseSchema(
        evaluation_id=uuid4(),
        order_id=uuid4(),
        product_id=uuid4(),
        buyer_id=buyer_id,
        seller_id=uuid4(),
        rating=5,
        comment="很棒的评价！",
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )

@pytest.fixture
def mock_evaluation_service(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Mock the EvaluationService dependency."""
    mock_service = AsyncMock(spec=EvaluationService)
    return mock_service

@pytest.fixture
def mock_db_connection() -> MagicMock:
    """Mock the database connection."""
    return MagicMock(spec=pyodbc.Connection)

@pytest.mark.asyncio
async def test_create_new_evaluation_success(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试成功创建新评价。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=5,
        comment="非常好"
    )

    expected_evaluation_response = create_dummy_evaluation_response_schema(buyer_id)
    mock_evaluation_service.create_evaluation.return_value = expected_evaluation_response

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={f"Authorization": f"Bearer fake-token-{buyer_id}"}
    )

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["evaluation_id"] == str(expected_evaluation_response.evaluation_id)
    assert response.json()["buyer_id"] == str(buyer_id)
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_unauthorized(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试未认证用户创建评价的失败情况。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=uuid4(), # 任意用户ID
        rating=3,
        comment="一般"
    )

    # Temporarily override get_current_user to simulate unauthorized access
    async def mock_get_current_user_unauthorized():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Use app.dependency_overrides directly for this test
    app.dependency_overrides[get_current_user] = mock_get_current_user_unauthorized

    try:
        # 不设置 Authorization header
        response = client.post(
            "/api/v1/evaluations/",
            json=evaluation_data.model_dump(mode="json")
        )

        # Assert
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json().get("detail") == "Not authenticated"
        mock_evaluation_service.create_evaluation.assert_not_called()
    finally:
        # Clean up the override after the test
        app.dependency_overrides.pop(get_current_user)

@pytest.mark.asyncio
async def test_create_new_evaluation_integrity_error(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """Test handling of IntegrityError during evaluation creation."""
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=5,
        comment="Excellent product!"
    )
    mock_evaluation_service.create_evaluation.side_effect = IntegrityError("该订单已评价过，不能重复评价")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{buyer_id}"
        }
    )

    # Assert
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("detail") == "该订单已评价过，不能重复评价"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_value_error(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试Service层抛出ValueError时，Router是否正确处理。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=1, # Changed to 1 to pass Pydantic validation
        comment="无效评分"
    )

    mock_evaluation_service.create_evaluation.side_effect = ValueError("评分必须在1到5之间")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={f"Authorization": f"Bearer fake-token-{buyer_id}"}
    )

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("detail") == "评分必须在1到5之间"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_forbidden_error(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试Service层抛出ForbiddenError时，Router是否正确处理。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=4,
        comment="不错"
    )

    mock_evaluation_service.create_evaluation.side_effect = ForbiddenError("您无权评价此订单")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{buyer_id}"
        }
    )

    # Assert
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json().get("detail") == "您无权评价此订单"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_not_found_error(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试Service层抛出NotFoundError时，Router是否正确处理。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=5,
        comment=""
    )

    mock_evaluation_service.create_evaluation.side_effect = NotFoundError("订单未找到或无法评价")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{buyer_id}"
        }
    )

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("detail") == "订单未找到或无法评价"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_dal_error(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=5,
        comment=""
    )

    mock_evaluation_service.create_evaluation.side_effect = DALError("评价创建异常")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{buyer_id}"
        }
    )

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "数据库操作失败: 评价创建异常"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_create_new_evaluation_generic_exception(client: TestClient, mock_evaluation_service: AsyncMock, mock_db_connection: MagicMock, mocker: pytest_mock.MockerFixture):
    """
    测试Service层抛出其他通用异常时，Router是否正确处理。
    """
    # Arrange
    order_id = uuid4()
    product_id = uuid4()
    buyer_id = client.test_user_id # Use client.test_user_id
    evaluation_data = EvaluationCreateSchema(
        order_id=order_id,
        product_id=product_id,
        user_id=buyer_id,
        rating=5,
        comment=""
    )

    mock_evaluation_service.create_evaluation.side_effect = Exception("未知错误")

    # Act
    response = client.post(
        "/api/v1/evaluations/",
        json=evaluation_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{buyer_id}"
        }
    )

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "服务器内部错误: 未知错误"
    mock_evaluation_service.create_evaluation.assert_called_once_with(
        mock_db_connection,
        evaluation_data,
        mocker.ANY
    )

@pytest.mark.asyncio
async def test_get_evaluation_by_id_success(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过评价ID获取单个评价详情。
    """
    # Arrange
    evaluation_id = uuid4()
    mock_response_data = EvaluationResponseSchema(
        evaluation_id=evaluation_id,
        order_id=uuid4(),
        product_id=uuid4(),
        buyer_id=uuid4(),
        seller_id=uuid4(),
        rating=4,
        comment="不错！",
        created_at=datetime.now()
    )
    mock_evaluation_service.get_evaluation_by_id.return_value = mock_response_data

    # Act
    response = client.get(f"/api/v1/evaluations/{evaluation_id}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == mock_response_data.model_dump(mode="json")
    mock_evaluation_service.get_evaluation_by_id.assert_called_once_with(mocker.ANY, evaluation_id)

@pytest.mark.asyncio
async def test_get_evaluation_by_id_not_found(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过评价ID获取评价详情，但评价不存在。
    """
    # Arrange
    evaluation_id = uuid4()
    mock_evaluation_service.get_evaluation_by_id.return_value = None

    # Act
    response = client.get(f"/api/v1/evaluations/{evaluation_id}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("detail") == f"评价ID {evaluation_id} 未找到"
    mock_evaluation_service.get_evaluation_by_id.assert_called_once_with(mocker.ANY, evaluation_id)

@pytest.mark.asyncio
async def test_get_evaluation_by_id_dal_error(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过评价ID获取评价详情，但DAL层发生错误。
    """
    # Arrange
    evaluation_id = uuid4()
    mock_evaluation_service.get_evaluation_by_id.side_effect = DALError("数据库查询失败")

    # Act
    response = client.get(f"/api/v1/evaluations/{evaluation_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "数据库操作失败: 数据库查询失败"
    mock_evaluation_service.get_evaluation_by_id.assert_called_once_with(mocker.ANY, evaluation_id)

@pytest.mark.asyncio
async def test_get_evaluation_by_id_general_exception(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过评价ID获取评价详情，但发生通用异常。
    """
    # Arrange
    evaluation_id = uuid4()
    mock_evaluation_service.get_evaluation_by_id.side_effect = Exception("未知服务器错误")

    # Act
    response = client.get(f"/api/v1/evaluations/{evaluation_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "服务器内部错误: 未知服务器错误"
    mock_evaluation_service.get_evaluation_by_id.assert_called_once_with(mocker.ANY, evaluation_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_success(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过商品ID获取评价列表。
    """
    # Arrange
    product_id = uuid4()
    mock_evaluations_list = [
        EvaluationResponseSchema(evaluation_id=uuid4(), order_id=uuid4(), product_id=product_id, buyer_id=uuid4(), seller_id=uuid4(), rating=5, comment="非常好", created_at=datetime.now()),
        EvaluationResponseSchema(evaluation_id=uuid4(), order_id=uuid4(), product_id=product_id, buyer_id=uuid4(), seller_id=uuid4(), rating=4, comment="还不错", created_at=datetime.now()),
    ]
    mock_evaluation_service.get_evaluations_by_product_id.return_value = mock_evaluations_list

    # Act
    response = client.get(f"/api/v1/evaluations/product/{product_id}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 2
    assert response.json()[0]["product_id"] == str(product_id)
    mock_evaluation_service.get_evaluations_by_product_id.assert_called_once_with(mocker.ANY, product_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_not_found(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过商品ID获取评价列表，但未找到任何评价。
    """
    # Arrange
    product_id = uuid4()
    mock_evaluation_service.get_evaluations_by_product_id.return_value = []

    # Act
    response = client.get(f"/api/v1/evaluations/product/{product_id}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("detail") == f"未找到商品 {product_id} 的任何评价"
    mock_evaluation_service.get_evaluations_by_product_id.assert_called_once_with(mocker.ANY, product_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_dal_error(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过商品ID获取评价列表，但DAL层发生错误。
    """
    # Arrange
    product_id = uuid4()
    mock_evaluation_service.get_evaluations_by_product_id.side_effect = DALError("数据库查询商品评价失败")

    # Act
    response = client.get(f"/api/v1/evaluations/product/{product_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "数据库操作失败: 数据库查询商品评价失败"
    mock_evaluation_service.get_evaluations_by_product_id.assert_called_once_with(mocker.ANY, product_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_product_id_general_exception(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过商品ID获取评价列表，但发生通用异常。
    """
    # Arrange
    product_id = uuid4()
    mock_evaluation_service.get_evaluations_by_product_id.side_effect = Exception("商品评价未知错误")

    # Act
    response = client.get(f"/api/v1/evaluations/product/{product_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "服务器内部错误: 商品评价未知错误"
    mock_evaluation_service.get_evaluations_by_product_id.assert_called_once_with(mocker.ANY, product_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_success(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过买家ID获取评价列表。
    """
    # Arrange
    buyer_id = uuid4()
    mock_evaluations_list = [
        EvaluationResponseSchema(evaluation_id=uuid4(), order_id=uuid4(), product_id=uuid4(), buyer_id=buyer_id, seller_id=uuid4(), rating=5, comment="买家评价1", created_at=datetime.now()),
        EvaluationResponseSchema(evaluation_id=uuid4(), order_id=uuid4(), product_id=uuid4(), buyer_id=buyer_id, seller_id=uuid4(), rating=3, comment="买家评价2", created_at=datetime.now()),
    ]
    mock_evaluation_service.get_evaluations_by_buyer_id.return_value = mock_evaluations_list

    # Act
    response = client.get(f"/api/v1/evaluations/buyer/{buyer_id}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 2
    assert response.json()[0]["buyer_id"] == str(buyer_id)
    mock_evaluation_service.get_evaluations_by_buyer_id.assert_called_once_with(mocker.ANY, buyer_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_not_found(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过买家ID获取评价列表，但未找到任何评价。
    """
    # Arrange
    buyer_id = uuid4()
    mock_evaluation_service.get_evaluations_by_buyer_id.return_value = []

    # Act
    response = client.get(f"/api/v1/evaluations/buyer/{buyer_id}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("detail") == f"未找到买家 {buyer_id} 的任何评价"
    mock_evaluation_service.get_evaluations_by_buyer_id.assert_called_once_with(mocker.ANY, buyer_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_dal_error(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过买家ID获取评价列表，但DAL层发生错误。
    """
    # Arrange
    buyer_id = uuid4()
    mock_evaluation_service.get_evaluations_by_buyer_id.side_effect = DALError("数据库查询买家评价失败")

    # Act
    response = client.get(f"/api/v1/evaluations/buyer/{buyer_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "数据库操作失败: 数据库查询买家评价失败"
    mock_evaluation_service.get_evaluations_by_buyer_id.assert_called_once_with(mocker.ANY, buyer_id)

@pytest.mark.asyncio
async def test_get_evaluations_by_buyer_id_general_exception(client: TestClient, mock_evaluation_service: AsyncMock, mocker: pytest_mock.MockerFixture):
    """
    测试通过买家ID获取评价列表，但发生通用异常。
    """
    # Arrange
    buyer_id = uuid4()
    mock_evaluation_service.get_evaluations_by_buyer_id.side_effect = Exception("买家评价未知错误")

    # Act
    response = client.get(f"/api/v1/evaluations/buyer/{buyer_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get("detail") == "服务器内部错误: 买家评价未知错误"
    mock_evaluation_service.get_evaluations_by_buyer_id.assert_called_once_with(mocker.ANY, buyer_id)

# Restore original dependencies after all tests are run
@pytest.fixture(autouse=True)
def restore_dependencies():
    yield
    # app.dependency_overrides.clear() # Removed redundant clear, conftest handles restoration