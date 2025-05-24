# 【思源淘】—— 北京交大学子专属二手交易平台 (后端)

---

## 开发快速通道 🚀

* **任务看板**: [TODO.md](./TODO.md) - 查看当前开发任务和分工。
* **开发必读**: [新功能模块开发指南](./docs/功能模块开发指南.md) - **必读！** 包含如何创建新模块的完整流程。
* **测试指南**: [测试指南](./docs/测试指南.md) - 如何运行和编写测试。
* **API 文档**: 启动服务后访问 [/docs](http://127.0.0.1:8000/docs) - 交互式 API 接口。

---

## 项目简介

本项目【思源淘】是一个专为交大学子设计的二手物品交易平台后端服务。核心目标是提供一个高效、便捷、高信任度的线上交流与线下交易的平台，促进校园内闲置物品的有效流通。

后端使用 **Python 和 FastAPI** 构建，核心数据存储基于 **SQL Server 数据库**。

---

## 技术栈与架构

*   **后端框架**: FastAPI (Python)
*   **数据库**: SQL Server
*   **数据访问**: 通过 Python 连接库及 SQL 存储过程/脚本
*   **架构风格**: 采用分层架构 (Routers -> Services -> DAL)

本项目遵循严格的分层开发模式。详细的开发步骤、代码规范和最佳实践，请参考我们的 **[新功能模块开发指南](./docs/功能模块开发指南.md)**。

更详细的技术选型理由请参考 [docs/技术选型.md](./docs/技术选型.md)。

---

## 环境配置

要开始项目开发，请按照以下步骤配置本地环境：

1.  **安装 Python**: 确保您的系统中安装了 Python 3.8 或更高版本。建议从 [Python 官方网站](https://www.python.org/downloads/) 下载并安装。

2.  **创建并激活虚拟环境**: 在项目根目录创建并激活独立的 Python 虚拟环境：

    ```bash
    python3 -m venv .venv
    ```

    激活虚拟环境：

    *   在 macOS 和 Linux 上：

        ```bash
        source .venv/bin/activate
        ```

    *   在 Windows 上：

        ```bash
        .venv\Scripts\activate
        ```

3.  **安装项目依赖**: 激活虚拟环境后，安装 `requirements.txt` 中的依赖：

    ```bash
    pip install -r requirements.txt
    ```

    如果您新增或修改了项目依赖，请运行以下命令更新 `requirements.txt` 文件：

    ```bash
    pip freeze > requirements.txt
    ```

4.  **配置环境变量**: 在项目根目录创建 `.env` 文件，配置数据库连接等信息。请参考 `.env.example` 文件（如果存在）或以下示例：

    ```bash
    # 示例 .env 文件内容 (请根据实际情况修改)
    DATABASE_URL=mssql+pyodbc://user:password@host:port/database?driver=ODBC+Driver+17+for+SQL+Server
    # 其他可能的配置项...
    ```

完成以上步骤后，您的开发环境已准备就绪。

---

## 如何运行项目

完成环境配置后，您可以通过以下步骤启动 FastAPI 后端服务：

1.  **激活虚拟环境**：如果您关闭了终端或新建了终端，请再次激活虚拟环境（参考上一节）。

2.  **运行 FastAPI 应用**：使用 uvicorn 启动应用。假设您的主应用文件是 `app/main.py`。

    ```bash
    uvicorn app.main:app --reload
    ```

    *   `app.main:app` 指的是 `app` 目录下的 `main.py` 文件中的名为 `app` 的 FastAPI 实例。
    *   `--reload` 参数会在代码文件发生变化时自动重启服务器，方便开发。

服务默认会在 `http://127.0.0.1:8000` 启动。您可以在浏览器中访问 `http://127.0.0.1:8000/docs` 查看自动生成的 API 文档（Swagger UI）。

---

## 项目结构

为了方便开发者快速理解项目，以下是后端项目的核心目录结构及其主要作用：

```
backend/
├── app/                  # FastAPI 应用核心代码
│   ├── routers/          # API 路由定义，处理 HTTP 请求和响应
│   ├── services/         # 业务逻辑层，处理具体的业务流程
│   ├── dal/              # 数据访问层 (Data Access Layer)，负责与数据库交互
│   ├── schemas/          # Pydantic 模型定义，用于请求验证和响应序列化
│   ├── utils/            # 通用工具函数
│   ├── main.py           # 应用入口文件，初始化 FastAPI 应用，包含根路由等
│   ├── config.py         # 项目配置文件，如数据库连接信息等
│   ├── exceptions.py     # 自定义异常类
│   └── middleware.py     # FastAPI 中间件
├── sql_scripts/          # SQL 脚本文件，用于数据库建表、存储过程、触发器等
│   ├── tables/           # 表创建脚本
│   ├── procedures/       # 存储过程脚本
│   ├── triggers/         # 触发器脚本
│   ├── db_init.py        # 数据库初始化脚本 (Python)
│   └── drop_all.sql      # 删除所有数据库对象的脚本
├── docs/                 # 项目文档，包括数据库设计、部署指南等
├── tests/                # 应用级测试，如 API 集成测试
│   └── user/             # 用户模块的测试
│   │   ├── test_user_service.py    # 业务逻辑测试
│   │   ├── test_users_api.py       # API 回归测试
│   │   ├── test_users_dal.py       # DAL 单元测试
│   └── conftest.py       # pytest 配置文件，用于测试fixture等
├── README.md             # 项目说明文档
├── requirements.txt      # 项目依赖库列表
└── .gitignore            # Git 忽略文件配置
```

**核心目录说明：**

*   `app/`: 存放所有的后端应用代码，按照功能和职责划分为不同的子目录。
*   `sql_scripts/`: 存放所有与数据库结构和数据操作相关的 SQL 脚本和初始化程序。
*   `docs/`: 存放详细的项目文档，是理解项目设计和背景的重要资源。
*   `tests/`: 存放项目的自动化测试代码，是保证代码质量的重要环节。

---

## 模块划分与开发指导

项目后端遵循了经典的三层架构思想，结合 FastAPI 的特点进行了模块划分，旨在提高代码的可维护性和可扩展性，便于团队协作。

**核心模块及其职责:**

1.  **路由层 (`app/routers/`)**：处理 HTTP 请求和响应，调用 Service 层。
2.  **业务逻辑层 (`app/services/`)**：实现核心业务逻辑，调用 DAL 层。
3.  **数据访问层 (`app/dal/`)**：负责与数据库交互，执行 SQL 操作。
4.  **模型定义 (`app/schemas/`)**：使用 Pydantic 定义数据结构，用于校验和序列化。
5.  **SQL 脚本 (`sql_scripts/`)**：管理数据库结构和存储过程。

**详细的开发流程和各层开发指导，请查阅 [新功能模块开发指南](./docs/功能模块开发指南.md)。**

---

## 相关文档

*   **任务看板**: [TODO.md](./TODO.md)
*   **新功能模块开发指南**: [docs/功能模块开发指南.md](./docs/功能模块开发指南.md)
*   **技术选型**: [docs/技术选型.md](./docs/技术选型.md)
*   **数据库设计文档**: [docs/数据库设计文档.md](./docs/数据库设计文档.md)
*   **API 文档指南**: [docs/API文档指南.md](./docs/API文档指南.md)
*   **测试指南**: [docs/测试指南.md](./docs/测试指南.md)
*   **部署指南**: [docs/部署指南.md](./docs/部署指南.md)

---