import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from app.schemas.order_schemas import OrderCreateSchema, OrderResponseSchema, OrderStatusUpdateSchema
from app.dependencies import get_current_user, get_order_service, get_db_connection
from app.services.order_service import OrderService
from app.exceptions import IntegrityError, ForbiddenError, NotFoundError, DALError
from fastapi import HTTPException, status
import pytest_mock
import pyodbc
import fastapi

# 假设这是你为 order_service 准备的 mock fixture 定义 (通常放在 conftest.py)
# 为了测试方便，这里直接定义，实际项目中应放在 conftest.py
@pytest.fixture
def mock_order_service(mocker: pytest_mock.MockerFixture) -> AsyncMock:
    """Mock the OrderService dependency."""
    mock_service = AsyncMock(spec=OrderService)
    return mock_service

# Helper function to create a dummy OrderResponseSchema instance
def create_dummy_order_response_schema(status_val: str, order_id: uuid4 = None, cancel_reason: Optional[str] = None) -> OrderResponseSchema:
    return OrderResponseSchema(
        order_id=order_id if order_id else uuid4(),
        buyer_id=uuid4(),
        product_id=uuid4(),
        quantity=1,
        total_price=10.0,
        status=status_val,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        seller_id=uuid4(),
        cancel_reason=cancel_reason,
        trade_id=None,
        complete_time=None,
        cancel_time=None,
    )

# --- POST /orders/ - 创建订单 ---

def test_create_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功创建一个订单。
    'client' fixture 会自动处理认证，模拟一个普通用户已登录。
    'mock_order_service' fixture 提供了 Service 层的 Mock。
    """
    order_data = OrderCreateSchema(product_id=uuid4(), quantity=1, total_price=100.0)
    # mock_buyer_id is implicitly handled by the client fixture's get_current_user override

    expected_created_order_schema = OrderResponseSchema(
        order_id=uuid4(),
        buyer_id=client.test_user_id,
        product_id=order_data.product_id,
        quantity=order_data.quantity,
        total_price=order_data.total_price,
        status="Pending",
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        seller_id=uuid4(),
        trade_id=None,
        complete_time=None,
        cancel_time=None,
        cancel_reason=None
    )
    mock_order_service.create_order.return_value = expected_created_order_schema

    response = client.post("/api/v1/orders/", json=order_data.model_dump(mode="json"), headers={
        "Authorization": f"Bearer fake-token-{client.test_user_id}"
    })

    assert response.status_code == fastapi.status.HTTP_201_CREATED
    response_data = response.json()
    expected_json_data = expected_created_order_schema.model_dump(mode='json', by_alias=True)
    assert response_data == expected_json_data

    mock_order_service.create_order.assert_called_once_with(
        mock_db_connection,
        order_data,
        client.test_user_id
    )

def test_create_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理。
    """
    mock_order_service.create_order.side_effect = ValueError("订单数量必须大于0")

    # OrderCreateSchema 应该有 quantity > 0 的验证
    order_data = OrderCreateSchema(product_id=uuid4(), quantity=1, total_price=100.0)

    response = client.post(
        "/api/v1/orders/",
        json=order_data.model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer fake-token-{client.test_user_id}"
        }
    )

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST # Expect 400 for ValueError from service
    assert response.json() == {"detail": "订单数量必须大于0"}
    mock_order_service.create_order.assert_called_once_with(
        mock_db_connection,
        order_data,
        client.test_user_id
    )

def test_create_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，商品库存不足）。
    """
    order_data = OrderCreateSchema(product_id=uuid4(), quantity=1, total_price=100.0)
    mock_order_service.create_order.side_effect = IntegrityError("商品库存不足")

    response = client.post("/api/v1/orders/", json=order_data.model_dump(mode="json"), headers={
        "Authorization": f"Bearer fake-token-{client.test_user_id}"
    })

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "商品库存不足"
    mock_order_service.create_order.assert_called_once_with(
        mock_db_connection,
        order_data,
        client.test_user_id
    )

def test_create_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出NotFoundError时，Router是否正确处理（例如，商品不存在）。
    """
    order_data = OrderCreateSchema(product_id=uuid4(), quantity=1, total_price=100.0)
    mock_order_service.create_order.side_effect = NotFoundError("商品不存在")

    response = client.post("/api/v1/orders/", json=order_data.model_dump(mode="json"), headers={
        "Authorization": f"Bearer fake-token-{client.test_user_id}"
    })

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "商品不存在"
    mock_order_service.create_order.assert_called_once_with(
        mock_db_connection,
        order_data,
        client.test_user_id
    )

# --- GET /orders/{order_id} - 获取单个订单 ---

def test_get_order_by_id_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功获取单个订单。
    """
    order_id = uuid4()
    expected_order = OrderResponseSchema(
        order_id=order_id,
        buyer_id=client.test_user_id,
        product_id=uuid4(),
        quantity=1,
        total_price=100.0,
        status="Pending",
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        seller_id=uuid4(),
        trade_id=None,
        complete_time=None,
        cancel_time=None,
        cancel_reason=None
    )
    mock_order_service.get_order_by_id.return_value = expected_order

    response = client.get(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json() == expected_order.model_dump(mode='json', by_alias=True)
    mock_order_service.get_order_by_id.assert_called_once_with(mock_db_connection, order_id, requesting_user_id=client.test_user_id)

def test_get_order_by_id_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试获取不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.get_order_by_id.side_effect = NotFoundError("订单未找到")

    response = client.get(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "订单未找到"
    mock_order_service.get_order_by_id.assert_called_once()

def test_get_order_by_id_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权查看订单。
    """
    order_id = uuid4()
    mock_order_service.get_order_by_id.side_effect = ForbiddenError("您无权查看此订单")

    response = client.get(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权查看此订单"
    mock_order_service.get_order_by_id.assert_called_once()

def test_get_order_by_id_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.get_order_by_id.side_effect = DALError("数据库操作失败: 连接中断")

    response = client.get(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "数据库操作失败: 连接中断"
    mock_order_service.get_order_by_id.assert_called_once()

# --- DELETE /orders/{order_id} - 删除订单 ---

def test_delete_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功删除订单。
    """

    order_id = uuid4()
    mock_order_service.delete_order.return_value = None # delete_order 不返回任何值

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_204_NO_CONTENT
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_delete_order_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权删除的订单。
    """
    order_id = uuid4()
    mock_order_service.delete_order.side_effect = ForbiddenError("您无权删除此订单")

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权删除此订单"
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_delete_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试删除不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.delete_order.side_effect = NotFoundError("订单未找到")

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "订单未找到"
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_delete_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理（例如，订单状态不允许删除）。
    """
    order_id = uuid4()
    mock_order_service.delete_order.side_effect = ValueError("订单无法在当前状态下删除")

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json().get('detail') == "订单无法在当前状态下删除"
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_delete_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，DAL层判断订单状态不允许删除）。
    """
    order_id = uuid4()
    mock_order_service.delete_order.side_effect = IntegrityError("订单状态不允许删除")

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "订单状态不允许删除"
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_delete_order_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.delete_order.side_effect = DALError("删除异常")

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "删除异常"
    mock_order_service.delete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

# --- POST /orders/{order_id}/cancel - 取消订单 ---

def test_cancel_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功取消订单。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.return_value = create_dummy_order_response_schema("Cancelled", order_id)

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "买家主动取消"})

    assert response.status_code == fastapi.status.HTTP_204_NO_CONTENT
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "买家主动取消"
    )

def test_cancel_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试取消不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.side_effect = NotFoundError("订单未找到")

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "订单未找到"})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "订单未找到"}
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "订单未找到"
    )

def test_cancel_order_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权取消的订单。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.side_effect = ForbiddenError("您无权取消此订单")

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "测试原因"})

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权取消此订单"
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "测试原因"
    )

def test_cancel_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理（例如，订单状态不允许取消）。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.side_effect = ValueError("订单无法在当前状态下取消")

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "测试原因"})

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json().get('detail') == "订单无法在当前状态下取消"
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "测试原因"
    )

def test_cancel_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，DAL层判断订单状态不允许取消）。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.side_effect = IntegrityError("订单状态不允许取消")

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "测试原因"})

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "订单状态不允许取消"
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "测试原因"
    )

def test_cancel_order_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.cancel_order.side_effect = DALError("取消异常")

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={"cancel_reason": "测试原因"})

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "取消异常"}
    mock_order_service.cancel_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "测试原因"
    )

def test_cancel_order_missing_reason(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试取消订单时缺少取消原因。
    """
    order_id = uuid4()

    response = client.post(f"/api/v1/orders/{order_id}/cancel", json={})

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "取消原因不能为空"}
    mock_order_service.cancel_order.assert_not_called()

# --- PUT /orders/{order_id}/confirm - 确认订单 ---

def test_confirm_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功确认订单。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.return_value = create_dummy_order_response_schema("Confirmed", order_id)

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json()["order_id"] == str(order_id)
    assert response.json()["status"] == "Confirmed"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_confirm_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试确认不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.side_effect = NotFoundError("订单未找到")

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "订单未找到"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_confirm_order_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权确认的订单。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.side_effect = ForbiddenError("您无权确认此订单")

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权确认此订单"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_confirm_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理（例如，订单状态不允许确认）。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.side_effect = ValueError("订单无法在当前状态下确认")

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json().get('detail') == "订单无法在当前状态下确认"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_confirm_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，DAL层判断订单状态不允许确认）。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.side_effect = IntegrityError("订单状态不允许确认")

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "订单状态不允许确认"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_confirm_order_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.confirm_order.side_effect = DALError("确认异常")

    response = client.put(f"/api/v1/orders/{order_id}/confirm")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "确认异常"
    mock_order_service.confirm_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

# --- PUT /orders/{order_id}/complete - 完成订单 ---

def test_complete_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功完成订单。
    """
    order_id = uuid4()
    mock_order_service.complete_order.return_value = create_dummy_order_response_schema("Completed", order_id)

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json()["order_id"] == str(order_id)
    assert response.json()["status"] == "Completed"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_complete_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试完成不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.complete_order.side_effect = NotFoundError("订单未找到")

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "订单未找到"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_complete_order_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权完成的订单。
    """
    order_id = uuid4()
    mock_order_service.complete_order.side_effect = ForbiddenError("您无权完成此订单")

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权完成此订单"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_complete_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理（例如，订单状态不允许完成）。
    """
    order_id = uuid4()
    mock_order_service.complete_order.side_effect = ValueError("订单无法在当前状态下完成")

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json().get('detail') == "订单无法在当前状态下完成"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_complete_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，DAL层判断订单状态不允许完成）。
    """
    order_id = uuid4()
    mock_order_service.complete_order.side_effect = IntegrityError("订单状态不允许完成")

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "订单状态不允许完成"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

def test_complete_order_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.complete_order.side_effect = DALError("数据库操作失败: 完成异常")

    response = client.put(f"/api/v1/orders/{order_id}/complete")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "数据库操作失败: 完成异常"
    mock_order_service.complete_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id
    )

# --- PUT /orders/{order_id}/reject - 拒绝订单 ---

def test_reject_order_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功拒绝订单。
    """
    order_id = uuid4()
    mock_order_service.reject_order.return_value = create_dummy_order_response_schema("Rejected", order_id)

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "商品不符合要求"}})

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json()["order_id"] == str(order_id)
    assert response.json()["status"] == "Rejected"
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "商品不符合要求"
    )

def test_reject_order_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试拒绝不存在的订单。
    """
    order_id = uuid4()
    mock_order_service.reject_order.side_effect = NotFoundError("订单未找到")

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "订单未找到"}})

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "订单未找到"}
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "订单未找到"
    )

def test_reject_order_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权拒绝的订单。
    """
    order_id = uuid4()
    mock_order_service.reject_order.side_effect = ForbiddenError("您无权拒绝此订单")

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "无权操作"}})

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "您无权拒绝此订单"}
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "无权操作"
    )

def test_reject_order_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出ValueError时，Router是否正确处理（例如，订单状态不允许拒绝）。
    """
    order_id = uuid4()
    mock_order_service.reject_order.side_effect = ValueError("订单无法在当前状态下拒绝")

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "订单状态不正确"}})

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "订单无法在当前状态下拒绝"}
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "订单状态不正确"
    )

def test_reject_order_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，DAL层判断订单状态不允许拒绝）。
    """
    order_id = uuid4()
    mock_order_service.reject_order.side_effect = IntegrityError("订单状态不允许拒绝")

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "DAL层拒绝异常"}})

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json() == {"detail": "订单状态不允许拒绝"}
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "DAL层拒绝异常"
    )

def test_reject_order_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    mock_order_service.reject_order.side_effect = DALError("数据库操作失败: 拒绝异常")

    response = client.put(f"/api/v1/orders/{order_id}/reject", json={"rejection_reason_data": {"rejection_reason": "数据库拒绝失败"}})

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "数据库操作失败: 拒绝异常"
    mock_order_service.reject_order.assert_called_once_with(
        mock_db_connection,
        order_id,
        client.test_user_id,
        "数据库拒绝失败"
    )

# --- PUT /orders/{order_id}/status - 更新订单状态 ---

def test_update_order_status_success(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功更新订单状态。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="Cancelled", cancel_reason="用户不再需要")
    mock_order_service.update_order_status.return_value = create_dummy_order_response_schema("Cancelled", order_id, cancel_reason="用户不再需要")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_200_OK
    assert response.json()["order_id"] == str(order_id)
    assert response.json()["status"] == "Cancelled"
    assert response.json()["cancel_reason"] == "用户不再需要"
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="Cancelled",
        user_id=client.test_user_id,
        cancel_reason="用户不再需要"
    )

def test_update_order_status_value_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试无效的状态转换。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="InvalidStatus")
    mock_order_service.update_order_status.side_effect = ValueError("无效的订单状态转换")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "无效的订单状态转换"}
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="InvalidStatus",
        user_id=client.test_user_id,
        cancel_reason=None # Ensure None is passed for cancel_reason
    )

def test_update_order_status_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试更新不存在的订单状态。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="Completed")
    mock_order_service.update_order_status.side_effect = NotFoundError("订单未找到")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get("detail") == "订单未找到"
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="Completed",
        user_id=client.test_user_id,
        cancel_reason=None # Ensure None is passed for cancel_reason
    )

def test_update_order_status_forbidden(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试用户无权更新订单状态。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="Completed")
    mock_order_service.update_order_status.side_effect = ForbiddenError("您无权更新此订单状态")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_403_FORBIDDEN
    assert response.json().get('detail') == "您无权更新此订单状态"
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="Completed",
        user_id=client.test_user_id,
        cancel_reason=None # Ensure None is passed for cancel_reason
    )

def test_update_order_status_integrity_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出IntegrityError时，Router是否正确处理（例如，订单状态转换冲突）。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="Completed")
    mock_order_service.update_order_status.side_effect = IntegrityError("订单状态转换冲突")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_409_CONFLICT
    assert response.json().get('detail') == "订单状态转换冲突"
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="Completed",
        user_id=client.test_user_id,
        cancel_reason=None # Ensure None is passed for cancel_reason
    )

def test_update_order_status_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    order_id = uuid4()
    status_update_data = OrderStatusUpdateSchema(status="Completed")
    mock_order_service.update_order_status.side_effect = DALError("数据库操作失败: 更新异常")

    response = client.put(f"/api/v1/orders/{order_id}/status", json=status_update_data.model_dump(mode='json'))

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "数据库操作失败: 更新异常"
    mock_order_service.update_order_status.assert_called_once_with(
        mock_db_connection,
        order_id=order_id,
        new_status="Completed",
        user_id=client.test_user_id,
        cancel_reason=None # Ensure None is passed for cancel_reason
    )

def test_update_order_status_cancel_missing_reason(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试取消订单时缺少取消原因。
    """
    order_id = uuid4()
    # Note: No cancel_reason in the payload to trigger the validation error
    # The OrderStatusUpdateSchema model_validator will raise ValueError if status is 'Cancelled' and reason is None
    # FastAPI's Pydantic integration translates ValueError from model_validator to 422 Unprocessable Entity
    response = client.put(f"/api/v1/orders/{order_id}/status", json={"status": "Cancelled"})

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body"],
                "msg": "Value error, 取消原因不能为空",
                "input": {"status": "Cancelled"},
                "ctx": {"error": {}}
            }
        ]
    }
    mock_order_service.update_order_status.assert_not_called()

# --- GET /orders/mine - 获取当前用户订单 ---

def test_get_my_orders_success_with_orders(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功获取当前用户订单列表 (有订单)。
    """
    mock_user_id = client.test_user_id
    orders_list = [
        OrderResponseSchema(
            order_id=uuid4(),
            buyer_id=client.test_user_id,
            product_id=uuid4(),
            quantity=1,
            total_price=100.0,
            status="Pending",
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
            updated_at=datetime.now(timezone.utc).replace(microsecond=0),
            seller_id=uuid4(),
            trade_id=None,
            complete_time=None,
            cancel_time=None,
            cancel_reason=None
        ),
        OrderResponseSchema(
            order_id=uuid4(),
            buyer_id=client.test_user_id,
            product_id=uuid4(),
            quantity=2,
            total_price=200.0,
            status="Completed",
            created_at=datetime.now(timezone.utc).replace(microsecond=0),
            updated_at=datetime.now(timezone.utc).replace(microsecond=0),
            seller_id=uuid4(),
            trade_id=uuid4(),
            complete_time=datetime.now(timezone.utc).replace(microsecond=0),
            cancel_time=None,
            cancel_reason=None
        ),
    ]
    mock_order_service.get_orders_by_user.return_value = orders_list

    response = client.get("/api/v1/orders/mine")

    assert response.status_code == 200
    response_data = response.json()
    # Convert the list of schemas to a list of dictionaries for comparison
    expected_json_data = [order.model_dump(mode='json', by_alias=True) for order in orders_list]
    assert response_data == expected_json_data

    mock_order_service.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        client.test_user_id,
        is_seller=False,
        status=None,
        page_number=1,
        page_size=10
    )

def test_get_my_orders_success_no_orders(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试成功获取当前用户订单列表 (无订单)。
    """
    mock_order_service.get_orders_by_user.return_value = []

    response = client.get("/api/v1/orders/mine")

    assert response.status_code == 200
    assert response.json() == []
    mock_order_service.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        client.test_user_id,
        is_seller=False,
        status=None,
        page_number=1,
        page_size=10
    )

def test_get_my_orders_not_found(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出NotFoundError时，Router是否正确处理。
    """
    mock_order_service.get_orders_by_user.side_effect = NotFoundError("未找到任何订单")

    response = client.get("/api/v1/orders/mine")

    assert response.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert response.json().get('detail') == "未找到任何订单"
    mock_order_service.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        client.test_user_id,
        is_seller=False,
        status=None,
        page_number=1,
        page_size=10
    )

def test_get_my_orders_dal_error(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出DALError时，Router是否正确处理。
    """
    mock_order_service.get_orders_by_user.side_effect = DALError("数据库操作失败: 查询订单异常")

    response = client.get("/api/v1/orders/mine")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "数据库操作失败: 查询订单异常"
    mock_order_service.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        client.test_user_id,
        is_seller=False,
        status=None,
        page_number=1,
        page_size=10
    )

def test_get_my_orders_general_exception(client: TestClient, mock_order_service: AsyncMock, mocker: pytest_mock.MockerFixture, mock_db_connection: MagicMock):
    """
    测试Service层抛出其他通用异常时，Router是否正确处理。
    """
    mock_order_service.get_orders_by_user.side_effect = Exception("未知错误")

    response = client.get("/api/v1/orders/mine")

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json().get('detail') == "服务器内部错误: 未知错误"
    mock_order_service.get_orders_by_user.assert_called_once_with(
        mock_db_connection,
        client.test_user_id,
        is_seller=False,
        status=None,
        page_number=1,
        page_size=10
    )