## API 文档指南

本项目后端使用 FastAPI 框架开发，API 文档会自动生成。本文档将指导您如何访问和使用这些自动生成的 API 文档。

### 1. 访问 API 文档

启动 FastAPI 应用后，您可以通过以下 URL 访问自动生成的 API 文档：

*   **Swagger UI**: `http://127.0.0.1:8000/docs` 
    *   提供交互式的 API 调试界面，可以直接在浏览器中测试 API。

*   **ReDoc**: `http://127.0.0.1:8000/redoc` 
    *   提供简洁美观的 API 文档展示界面，适合阅读。

### 2. API 设计约定

本项目 API 设计遵循 RESTful 风格，并结合实际需求进行调整。主要约定如下：

*   **命名规范**: 资源路径使用小写字母和中划线（kebab-case），例如 `/users/{user-id}`。
*   **版本控制**: API 版本通过 URL 前缀体现，例如 `/api/v1/users`。
*   **请求方法**: 使用标准的 HTTP 方法，例如 `GET` (获取资源), `POST` (创建资源), `PUT` (更新资源), `DELETE` (删除资源)。
*   **状态码**: 使用标准的 HTTP 状态码表示请求结果，例如 `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error` 等。
*   **请求/响应格式**: 统一使用 JSON 格式进行数据交换。请求体和响应体遵循预定义的 Pydantic 模型，确保数据结构和类型正确性。
*   **字段命名**: JSON 字段名使用驼峰式命名 (camelCase)。
*   **分页**: 对于返回列表的接口，支持通过查询参数 `page` 和 `page_size` 进行分页。响应中应包含总条数和当前页信息。
*   **过滤与排序**: 支持通过查询参数进行资源的过滤和排序。具体的参数名称和支持的字段在每个接口文档中说明。

### 3. 如何调用 API

前端或其他客户端可以通过发送 HTTP 请求来调用后端 API。建议使用现代的 HTTP 客户端库，如 JavaScript 中的 `fetch` 或 `axios`，Python 中的 `requests`。

调用示例 (使用 axios):

```javascript
import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1'; // 根据实际部署地址修改

// 假设已经获取了 access_token
const accessToken = 'your_access_token_here'; 

// 创建一个带有认证头的 axios 实例
const authAxios = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    Authorization: `Bearer ${accessToken}` // 在请求头中携带 Token
  }
});

// 获取用户列表 (示例，需要认证)
async function getUsers(page = 1, pageSize = 10) {
  try {
    const response = await authAxios.get('/users', {
      params: {
        page: page,
        page_size: pageSize
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching users:', error);
    throw error;
  }
}

// 创建新用户 (示例，需要认证)
async function createUser(userData) {
  try {
    const response = await authAxios.post('/users', userData);
    return response.data;
  } catch (error) {
    console.error('Error creating user:', error);
    throw error;
  }
}

// 登录示例 (无需认证头)
async function login(credentials) {
  try {
    const response = await axios.post(`${API_BASE_URL}/auth/login`, credentials); // 登录接口通常不需要认证头
    // 登录成功后，从响应中获取 token 并保存
    const { access_token, token_type } = response.data; // 假设响应体包含 access_token 和 token_type
    console.log('Access Token:', access_token);
    // 可以将 access_token 存储在 localStorage 或 Vuex/Redux store 中
    return response.data;
  } catch (error) {
    console.error('Error during login:', error);
    throw error;
  }
}
```

### 4. 错误处理

后端 API 在处理请求过程中遇到错误时，会返回适当的 HTTP 状态码和统一的 JSON 错误响应体。客户端应根据状态码和错误响应体进行相应的错误处理和提示。

通用的错误响应体格式示例:

```json
{
  "detail": "错误信息描述",
  "code": 1001, // 可选：自定义错误码
  "field": "password" // 可选：如果错误与特定字段相关（常见于 422 错误）
}
```

**常见的 HTTP 状态码和错误场景:**

*   `400 Bad Request`: 请求参数验证失败、请求体格式错误（非 Pydantic 验证）等。
*   `401 Unauthorized`: 未提供认证信息或认证信息无效。
*   `403 Forbidden`: 已认证用户无权访问该资源或执行该操作。
*   `404 Not Found`: 请求的资源不存在。
*   `405 Method Not Allowed`: 使用了不支持的 HTTP 方法。
*   `409 Conflict`: 请求与当前资源状态冲突（例如尝试创建已存在的资源）。
*   `422 Unprocessable Entity`: 请求格式正确但包含语义错误，通常由 Pydantic 模型验证产生。
*   `500 Internal Server Error`: 服务器内部发生未知错误。

客户端在接收到非 2xx 状态码的响应时，应检查响应体获取详细错误信息，并向用户显示友好的错误提示。

### 5. 认证与授权

本项目采用 JWT (JSON Web Token) 进行认证。

*   **认证流程**: 客户端通过登录接口 (`/api/v1/auth/login`) 获取 JWT (`access_token`)。
*   **授权访问**: 客户端在调用受保护的 API 接口时，在 HTTP 请求的 `Header` 中携带 `Authorization: Bearer <access_token>`。

在 Swagger UI (`/docs`) 中，你可以点击右上角的 "Authorize" 按钮，选择 "bearerAuth" (或其他配置的认证方案)，并输入你的 `access_token` 来进行交互式测试。

--- 