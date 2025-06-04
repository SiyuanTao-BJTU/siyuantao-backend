# 思源淘 - 项目开发 TODO 列表

---

## Git 工作流集成约定

当你开始一个 TODO 任务时（例如：`[ ] TODO: 实现商品创建API`），请创建一个对应的 Git 分支。分支名可以与任务关联，例如 `feature/B-create-product-api` (其中 `B` 代表开发者，`create-product-api` 描述任务)。这有助于将代码提交与任务关联，提高协作效率。

---

## 项目总览

本文档旨在提供【思源淘】项目的开发任务总览，按照技术层级进行划分，并细化到具体的功能模块和文件路径。请各位开发者根据分配的模块，及时更新相关任务的状态。

## 团队分工

*   **开发者 A:** 主要负责：用户模块 (SQL, DAL, Service, API, Frontend)
*   **开发者 B:** 主要负责：商品浏览与收藏 (SQL, DAL, Service, API, Frontend)
*   **开发者 C:** 主要负责：商品操作与交易评价 (SQL, DAL, Service, API, Frontend)
*   **开发者 D:** 主要负责：实时通讯与退货 (SQL, DAL, Service, API, Frontend)
*   **开发者 E:** 主要负责：通知、举报及通用基础设施 (SQL, DAL, Service, API, Frontend, Common)

## 约定

*   **状态标记:**
    *   `[√] DONE:`：任务已完成。
    *   `[ ] TODO:`：任务待完成。
    *   `[!] OPTIONAL:`：可选任务或未来优化项。
    *   `[#] PENDING:`: 任务暂停/等待依赖。
*   **更新频率:** 每日站会前更新个人负责的任务状态。
*   **Git Commit:** 提交代码时，在 commit message 中引用相关 TODO 项（例如：`feat(user): implements user registration API (TODO: #Backend-API-User-1)`）。

---

## 1. SQL 数据库层

**概述:** 本层负责所有数据库表结构、存储过程、函数和触发器的设计与实现。

### 1.1 用户模块

*   文件: `backend/sql/01_create_tables.sql`
    *   `[√] DONE:` `CREATE TABLE [User]`: 用户基础信息表，包含 `UserID`, `UserName`, `Password` (哈希), `Email`, `Major`, `IsVerified`, `VerificationToken`, `TokenExpireTime`, `Status`, `Credit`, `IsStaff`, `JoinTime`, `AvatarUrl`, `Bio`, `PhoneNumber` 等字段。
        *   **备注:** 确认所有字段类型、长度和约束符合要求。
        *   **Major 字段备注:** 考虑到表数量限制，Major 字段将在前端进行硬编码下拉列表，数据库层面保留 `NVARCHAR(100)` 类型。
*   文件: `backend/sql/db_init.py`
    *   `[√] DONE:` 在数据库初始化脚本中添加为5位开发者自动创建管理员账户的逻辑。
*   文件: `backend/sql/01_user_procedures.sql`
    *   `[√] DONE:` `sp_GetUserProfileById (@userId)`: 根据用户ID获取用户公开信息，用于展示个人主页等。
    *   `[√] DONE:` `sp_GetUserByUsernameWithPassword (@username)`: 根据用户名获取用户（包含密码哈希），用于登录验证。
    *   `[√] DONE:` `sp_CreateUser (@username, @passwordHash, @email)`: 创建新用户，检查用户名和邮箱唯一性，设置初始状态和信用分。
    *   `[√] DONE:` `sp_UpdateUserProfile (@userId, ...)`: 更新用户个人信息（专业、头像、简介、手机号），检查手机号唯一性。
    *   `[√] DONE:` `sp_GetUserPasswordHashById (@userId)`: 根据用户ID获取密码哈希，用于密码修改等场景。
    *   `[√] DONE:` `sp_UpdateUserPassword (@userId, @newPasswordHash)`: 更新用户密码。
    *   `[√] DONE:` `sp_RequestMagicLink (@email)`: 用户请求魔术链接，用于无密码登录或注册。查找用户，如果是新用户则创建，老用户则更新 token。
    *   `[√] DONE:` `sp_VerifyMagicLink (@token)`: 验证魔术链接，完成用户邮箱认证（`IsVerified = 1`），清除 token。
    *   `[√] DONE:` `sp_GetSystemNotificationsByUserId (@userId)`: 获取某个用户的系统通知列表。
    *   `[√] DONE:` `sp_MarkNotificationAsRead (@notificationId, @userId)`: 将指定系统通知标记为已读，验证操作者是通知接收者。
    *   `[!] OPTIONAL:` `sp_GetUserByEmail (email)`: 用于注册时检查邮箱重复，或找回密码。
*   文件: `backend/sql/05_admin_procedures.sql` (管理员用户管理部分)
    *   `[√] DONE:` `sp_ChangeUserStatus (@userId, @newStatus, @adminId)`: 管理员禁用/启用用户账户。
    *   `[√] DONE:` `sp_AdjustUserCredit (@userId, @creditAdjustment, @adminId, @reason)`: 管理员手动调整用户信用分。
    *   `[√] DONE:` `sp_GetAllUsers (@adminId)`: 管理员获取所有用户列表。
*   文件: `backend/sql/07_chat_procedures.sql` (ChatMessage 逻辑删除部分)
    *   `[√] DONE:` `sp_SetChatMessageVisibility (@messageId, @userId, @visibleTo, @isVisible)`: 设置消息对发送者或接收者的可见性（逻辑删除）。
*   文件: `backend/sql/drop_all.sql`
    *   `[√] DONE:` 包含所有用户模块相关对象的删除语句。

### 1.2 商品模块

*   文件: `backend/sql/02_create_tables.sql`
    *   `[ ] TODO:` `CREATE TABLE [Product]`: 商品信息表，包含 `ProductID`, `OwnerID`, `CategoryName`, `ProductName`, `Description`, `Quantity`, `Price`, `PostTime`, `Status`。
        *   **细节:** 确保 `OwnerID` 外键关联 `User` 表，`Quantity` 和 `Price` 检查约束，`Status` 枚举值符合定义。
    *   `[ ] TODO:` `CREATE TABLE [ProductImage]`: 商品图片表，包含 `ImageID`, `ProductID`, `ImageURL`, `UploadTime`, `SortOrder`。
        *   **细节:** 确保 `ProductID` 外键关联 `Product` 表，`SortOrder` 默认值和用途明确。
    *   `[ ] TODO:` `CREATE TABLE [UserFavorite]`: 用户收藏表，包含 `FavoriteID`, `UserID`, `ProductID`, `FavoriteTime`。
        *   **细节:** 确保 `UserID` 和 `ProductID` 外键关联，并添加 `UQ_UserFavorite_UserProduct` 复合唯一约束。
*   文件: `backend/sql/02_product_procedures.sql`
    *   `[ ] TODO:` `sp_CreateProduct (@ownerId, @categoryName, @productName, @description, @quantity, @price)`: 创建新商品，初始化状态为 'PendingReview'。
    *   `[ ] TODO:` `sp_UpdateProduct (@productId, @ownerId, @categoryName, @productName, @description, @quantity, @price)`: 更新商品信息，只允许商品所有者更新。
    *   `[ ] TODO:` `sp_DeleteProduct (@productId, @ownerId)`: 删除商品，只允许商品所有者或管理员删除。
    *   `[ ] TODO:` `sp_ActivateProduct (@productId, @adminId)`: 管理员审核通过商品，设置状态为 'Active'。
    *   `[ ] TODO:` `sp_RejectProduct (@productId, @adminId)`: 管理员拒绝商品，设置状态为 'Rejected'。
    *   `[ ] TODO:` `sp_WithdrawProduct (@productId, @ownerId)`: 商品所有者下架商品，设置状态为 'Withdrawn'。
    *   `[ ] TODO:` `sp_GetProductList (@categoryId, @status, @keyword, @minPrice, @maxPrice, @orderBy, @pageNumber, @pageSize)`: 获取商品列表，支持筛选、搜索、分页。
    *   `[ ] TODO:` `sp_GetProductById (@productId)`: 根据商品ID获取商品详细信息。
    *   `[ ] TODO:` `sp_GetImagesByProduct (@productId)`: 获取指定商品的所有图片URL。
    *   `[ ] TODO:` `sp_AddUserFavorite (@userId, @productId)`: 用户收藏商品，检查是否已收藏。
    *   `[ ] TODO:` `sp_RemoveUserFavorite (@userId, @productId)`: 用户取消收藏商品。
    *   `[ ] TODO:` `sp_GetUserFavoriteProducts (@userId)`: 获取用户收藏的商品列表。
    *   `[ ] TODO:` `sp_DecreaseProductQuantity (@productId, @quantityToDecrease)`: 减少商品库存（用于订单创建）。
    *   `[ ] TODO:` `sp_IncreaseProductQuantity (@productId, @quantityToIncrease)`: 增加商品库存（用于订单取消或退货）。
*   文件: `backend/sql/drop_all.sql`
    *   `[ ] TODO:` 添加所有商品模块相关对象的删除语句。
*   *   `[ ] **重要：删除产品时，在应用层需要先删除 ProductImage 和 UserFavorite 表中关联的记录，因为数据库层将 FK_UserFavorite_Product 的 ON DELETE CASCADE 改为了 ON DELETE NO ACTION 以解决循环引用问题`

### 1.3 评价模块

*   文件: `backend/sql/03_create_tables.sql`
    *   `[ ] TODO:` `CREATE TABLE [Evaluation]`: 交易评价表，包含 `EvaluationID`, `OrderID`, `SellerID`, `BuyerID`, `Rating`, `Content`, `CreateTime`。
        *   **细节:** 确保 `OrderID`、`SellerID`、`BuyerID` 外键关联，`Rating` 检查约束，并添加 `UQ_Evaluation_OrderID` 唯一约束。
*   文件: `backend/sql/03_evaluation_procedures.sql`
    *   `[ ] TODO:` `sp_CreateEvaluation (@orderId, @sellerId, @buyerId, @rating, @content)`: 创建评价，确保只有买家可以评价已完成订单，且一个订单只能评价一次。
    *   `[ ] TODO:` `sp_GetEvaluationsBySeller (@sellerId, @pageNumber, @pageSize)`: 获取某个卖家的所有评价列表。
    *   `[ ] TODO:` `sp_GetEvaluationByOrderId (@orderId)`: 根据订单ID获取评价详情。
*   文件: `backend/sql/03_evaluation_triggers.sql`
    *   `[ ] TODO:` `tr_Evaluation_AfterInsert_UpdateSellerCredit`: 在评价插入后，根据评分自动更新卖家的信用分 (`User.Credit`)。
        *   **细节:** 考虑评分对信用分的影响规则（例如：5星+2，1星-5）。
*   文件: `backend/sql/drop_all.sql`
    *   `[ ] TODO:` 添加所有评价模块相关对象的删除语句。

### 1.4 交易模块

*   文件: `backend/sql/04_create_tables.sql`
    *   `[ ] TODO:` `CREATE TABLE [Order]`: 订单表，包含 `OrderID`, `SellerID`, `BuyerID`, `ProductID`, `Quantity`, `CreateTime`, `Status`, `CompleteTime`, `CancelTime`, `CancelReason`。
        *   **细节:** 确保所有外键关联正确，`Quantity` 检查约束，`Status` 枚举值符合定义。
*   文件: `backend/sql/04_order_procedures.sql`
    *   `[ ] TODO:` `sp_CreateOrder (@buyerId, @productId, @quantity)`: 买家创建订单，扣减商品库存。
    *   `[ ] TODO:` `sp_ConfirmOrder (@orderId, @sellerId)`: 卖家确认订单，状态变为 'ConfirmedBySeller'。
    *   `[ ] TODO:` `sp_CompleteOrder (@orderId, @buyerId)`: 买家确认收货，订单状态变为 'Completed'。
    *   `[ ] TODO:` `sp_CancelOrder (@orderId, @userId, @cancelReason)`: 取消订单（买家或卖家），恢复商品库存，设置取消原因。
    *   `[ ] TODO:` `sp_GetOrdersByUser (@userId, @isSeller, @status, @pageNumber, @pageSize)`: 获取用户的买家或卖家订单列表，支持状态筛选和分页。
    *   `[ ] TODO:` `sp_GetOrderById (@orderId)`: 根据订单ID获取订单详情。
*   文件: `backend/sql/04_order_triggers.sql`
    *   `[ ] TODO:` `tr_Order_AfterCancel_RestoreQuantity`: 订单取消后，自动恢复对应商品的库存数量。
*   文件: `backend/sql/drop_all.sql`
    *   `[ ] TODO:` 添加所有交易模块相关对象的删除语句。

### 1.5 消息与退货模块

*   文件: `backend/sql/05_create_tables.sql`
    *   `[ ] TODO:` `CREATE TABLE [ChatMessage]`: 聊天消息表，包含 `MessageID`, `SenderID`, `ReceiverID`, `ProductID`, `Content`, `SendTime`, `IsRead`, `SenderVisible`, `ReceiverVisible`。
        *   **细节:** 确保所有外键关联，消息逻辑删除字段。
    *   `[ ] TODO:` `CREATE TABLE [ReturnRequest]`: 退货请求表，包含 `ReturnRequestID`, `OrderID`, `ReturnReason`, `ApplyTime`, `SellerAgree`, `BuyerApplyIntervene`, `AuditTime`, `AuditStatus`, `AuditIdea`。
        *   **细节:** 确保 `OrderID` 唯一约束和外键关联，`AuditStatus` 枚举值符合定义。
*   文件: `backend/sql/05_chat_procedures.sql`
    *   `[ ] TODO:` `sp_SendMessage (@senderId, @receiverId, @productId, @content)`: 发送聊天消息。
    *   `[ ] TODO:` `sp_GetUserConversations (@userId)`: 获取用户的所有会话列表（按商品分组，显示最新消息）。
    *   `[ ] TODO:` `sp_GetChatMessagesByProductAndUsers (@productId, @userId1, @userId2, @pageNumber, @pageSize)`: 获取指定商品ID和两个用户之间的聊天记录。
    *   `[ ] TODO:` `sp_MarkMessageAsRead (@messageId, @userId)`: 将指定消息标记为已读。
    *   `[ ] TODO:` `sp_HideConversation (@productId, @userId)`: 用户隐藏与某个商品的会话（通过逻辑删除相关消息）。
*   文件: `backend/sql/05_return_procedures.sql`
    *   `[ ] TODO:` `sp_CreateReturnRequest (@orderId, @returnReason)`: 买家发起退货请求。
    *   `[ ] TODO:` `sp_HandleReturnRequest (@returnRequestId, @sellerId, @isAgree, @auditIdea)`: 卖家处理退货请求（同意/拒绝）。
    *   `[ ] TODO:` `sp_BuyerRequestIntervention (@returnRequestId, @buyerId)`: 买家申请管理员介入。
    *   `[ ] TODO:` `sp_AdminResolveReturnRequest (@returnRequestId, @adminId, @status, @auditIdea)`: 管理员处理退货介入。
    *   `[ ] TODO:` `sp_GetReturnRequestById (@returnRequestId)`: 获取退货请求详情。
    *   `[ ] TODO:` `sp_GetReturnRequestsByUserId (@userId)`: 获取用户的退货请求列表（买家/卖家）。
*   文件: `backend/sql/drop_all.sql`
    *   `[ ] TODO:` 添加所有消息与退货模块相关对象的删除语句。

- 退货请求（ReturnRequest）支持买家发起、卖家处理、买家申请管理员介入。
- 管理员介入处理时，需将当前管理员的 UserID 写入 ProcessorAdminID 字段（外键约束，关联 User 表）。
- 只有管理员（IsStaff=1）才有权限处理介入请求，应用层和存储过程均有权限校验。
- 相关存储过程：sp_AdminProcessReturnIntervention。 

### 1.6 通知与举报模块

*   文件: `backend/sql/06_create_tables.sql`
    *   `[ ] TODO:` `CREATE TABLE [SystemNotification]`: 系统通知表，包含 `NotificationID`, `UserID`, `Title`, `Content`, `CreateTime`, `IsRead`。
        *   **细节:** 确保 `UserID` 外键关联。
    *   `[ ] TODO:` `CREATE TABLE [Report]`: 举报表，包含 `ReportID`, `ReporterUserID`, `ReportedUserID`, `ReportedProductID`, `ReportedOrderID`, `ReportContent`, `ReportTime`, `ProcessingStatus`, `ProcessorAdminID`, `ProcessingTime`, `ProcessingResult`。
        *   **细节:** 确保所有外键关联，`ProcessingStatus` 枚举值符合定义。
*   文件: `backend/sql/06_notification_procedures.sql`
    *   `[ ] TODO:` `sp_SendSystemNotification (@userId, @title, @content)`: 发送系统通知给指定用户。
    *   `[ ] TODO:` `sp_GetUserNotifications (@userId, @isRead, @pageNumber, @pageSize)`: 获取用户通知列表，支持已读/未读筛选和分页。
    *   `[ ] TODO:` `sp_MarkNotificationAsRead (@notificationId, @userId)`: 标记通知为已读。
    *   `[ ] TODO:` `sp_DeleteNotification (@notificationId, @userId)`: 用户删除通知（逻辑删除）。
*   文件: `backend/sql/06_report_procedures.sql`
    *   `[ ] TODO:` `sp_CreateReport (@reporterUserId, @reportedUserId, @reportedProductId, @reportedOrderId, @reportContent)`: 用户提交举报。
    *   `[ ] TODO:` `sp_GetReportList (@status, @pageNumber, @pageSize)`: 管理员获取举报列表，支持状态筛选和分页。
    *   `[ ] TODO:` `sp_HandleReport (@reportId, @adminId, @newStatus, @processingResult)`: 管理员处理举报。
*   文件: `backend/sql/drop_all.sql`
    *   `[ ] TODO:` 添加所有通知与举报模块相关对象的删除语句。

---

## 2. 后端 DAL 层 (Python)

**概述:** 本层负责封装所有直接的数据库操作，通过调用存储过程与数据库交互。

### 2.1 用户模块

*   文件: `backend/src/modules/user/dal/user_dal.py`
    *   `[√] DONE:` `UserDAL` 类定义，注入数据库连接池。
    *   `[√] DONE:` `create_user(...)`: 封装 `sp_CreateUser`。
    *   `[√] DONE:` `get_user_by_username_with_password(...)`: 封装 `sp_GetUserByUsernameWithPassword`。
    *   `[√] DONE:` `get_user_by_id(...)`: 封装 `sp_GetUserProfileById`。
    *   `[√] DONE:` `update_user_profile(...)`: 封装 `sp_UpdateUserProfile`。
    *   `[√] DONE:` `update_user_password(...)`: 封装 `sp_UpdateUserPassword`。
    *   `[√] DONE:` `get_user_password_hash_by_id(...)`: 封装 `sp_GetUserPasswordHashById`。
    *   `[√] DONE:` `delete_user(...)`: 封装 `sp_DeleteUser`。
    *   `[√] DONE:` `request_verification_link(...)`: 封装 `sp_RequestMagicLink`。
    *   `[√] DONE:` `verify_email(...)`: 封装 `sp_VerifyMagicLink`。
    *   `[√] DONE:` `get_system_notifications_by_user_id(...)`: 封装 `sp_GetSystemNotificationsByUserId`。
    *   `[√] DONE:` `mark_notification_as_read(...)`: 封装 `sp_MarkNotificationAsRead`。
    *   `[√] DONE:` `set_chat_message_visibility(...)`: 封装 `sp_SetChatMessageVisibility`。
    *   `[√] DONE:` `change_user_status(...)`: 封装 `sp_ChangeUserStatus`。
    *   `[√] DONE:` `adjust_user_credit(...)`: 封装 `sp_AdjustUserCredit`。
    *   `[√] DONE:` `get_all_users(...)`: 封装 `sp_GetAllUsers`。
    *   `[!] OPTIONAL:` `get_user_by_email(...)`: 封装 `sp_GetUserByEmail`。
*   文件: `backend/tests/modules/user/test_user_dal.py`
    *   `[√] DONE:` 编写 `UserDAL` 中所有方法的单元测试，使用 Mocking (如 `pytest-mock`) 模拟数据库交互。

### 2.2 商品模块

*   文件: `backend/src/modules/product/dal/product_dal.py`
    *   `[√] TODO:` `ProductDAL` 类定义，注入数据库连接池。
    *   `[√] TODO:` `create_product(...)`: 封装 `sp_CreateProduct`。
    *   `[√] TODO:` `update_product(...)`: 封装 `sp_UpdateProduct`。
    *   `[√] TODO:` `delete_product(...)`: 封装 `sp_DeleteProduct`。
    *   `[√] TODO:` `activate_product(...)`: 封装 `sp_ActivateProduct`。
    *   `[√] TODO:` `reject_product(...)`: 封装 `sp_RejectProduct`。
    *   `[√] TODO:` `withdraw_product(...)`: 封装 `sp_WithdrawProduct`。
    *   `[√] TODO:` `get_product_list(...)`: 封装 `sp_GetProductList`。
    *   `[√] TODO:` `get_product_by_id(...)`: 封装 `sp_GetProductById`。
    *   `[√] TODO:` `decrease_product_quantity(...)`: 封装 `sp_DecreaseProductQuantity`。
    *   `[√] TODO:` `increase_product_quantity(...)`: 封装 `sp_IncreaseProductQuantity`。
*   文件: `backend/src/modules/product/dal/product_image_dal.py`
    *   `[√] TODO:` `ProductImageDAL` 类定义，注入数据库连接池。
    *   `[√] TODO:` `add_product_image(...)`: 封装图片插入逻辑。
    *   `[√] TODO:` `get_images_by_product_id(...)`: 封装 `sp_GetImagesByProduct`。
    *   `[√] TODO:` `delete_product_image(...)`: 封装图片删除逻辑。
*   文件: `backend/src/modules/product/dal/user_favorite_dal.py`
    *   `[√] TODO:` `UserFavoriteDAL` 类定义，注入数据库连接池。
    *   `[√] TODO:` `add_user_favorite(...)`: 封装 `sp_AddUserFavorite`.
    *   `[√] TODO:` `remove_user_favorite(...)`: 封装 `sp_RemoveUserFavorite`。
    *   `[√] TODO:` `get_user_favorite_products(...)`: 封装 `sp_GetUserFavoriteProducts`。
*   文件: `backend/tests/modules/product/test_product_dal.py`
    *   `[√] TODO:` 编写 `ProductDAL`、`ProductImageDAL`、`UserFavoriteDAL` 的单元测试。

### 2.3 评价模块

*   文件: `backend/src/modules/evaluation/dal/evaluation_dal.py`
    *   `[ ] TODO:` `EvaluationDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `create_evaluation(...)`: 封装 `sp_CreateEvaluation`。
    *   `[ ] TODO:` `get_evaluations_by_seller_id(...)`: 封装 `sp_GetEvaluationsBySeller`。
    *   `[ ] TODO:` `get_evaluation_by_order_id(...)`: 封装 `sp_GetEvaluationByOrderId`。
*   文件: `backend/tests/modules/evaluation/test_evaluation_dal.py`
    *   `[ ] TODO:` 编写 `EvaluationDAL` 的单元测试。

### 2.4 交易模块

*   文件: `backend/src/modules/order/dal/order_dal.py`
    *   `[ ] TODO:` `OrderDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `create_order(...)`: 封装 `sp_CreateOrder`。
    *   `[ ] TODO:` `confirm_order(...)`: 封装 `sp_ConfirmOrder`。
    *   `[ ] TODO:` `complete_order(...)`: 封装 `sp_CompleteOrder`。
    *   `[ ] TODO:` `cancel_order(...)`: 封装 `sp_CancelOrder`。
    *   `[ ] TODO:` `get_orders_by_user_id(...)`: 封装 `sp_GetOrdersByUser`。
    *   `[ ] TODO:` `get_order_by_id(...)`: 封装 `sp_GetOrderById`。
*   文件: `backend/tests/modules/order/test_order_dal.py`
    *   `[ ] TODO:` 编写 `OrderDAL` 的单元测试。

### 2.5 消息与退货模块

*   文件: `backend/src/modules/chat/dal/chat_message_dal.py`
    *   `[ ] TODO:` `ChatMessageDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `send_message(...)`: 封装 `sp_SendMessage`。
    *   `[ ] TODO:` `get_user_conversations(...)`: 封装 `sp_GetUserConversations`。
    *   `[ ] TODO:` `get_chat_messages_by_product_and_users(...)`: 封装 `sp_GetChatMessagesByProductAndUsers`。
    *   `[ ] TODO:` `mark_message_as_read(...)`: 封装 `sp_MarkMessageAsRead`。
    *   `[ ] TODO:` `hide_conversation(...)`: 封装 `sp_HideConversation`。
*   文件: `backend/src/modules/return_request/dal/return_request_dal.py`
    *   `[ ] TODO:` `ReturnRequestDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `create_return_request(...)`: 封装 `sp_CreateReturnRequest`。
    *   `[ ] TODO:` `handle_return_request(...)`: 封装 `sp_HandleReturnRequest`。
    *   `[ ] TODO:` `buyer_request_intervention(...)`: 封装 `sp_BuyerRequestIntervention`。
    *   `[ ] TODO:` `admin_resolve_return_request(...)`: 封装 `sp_AdminResolveReturnRequest`。
    *   `[ ] TODO:` `get_return_request_by_id(...)`: 封装 `sp_GetReturnRequestById`。
    *   `[ ] TODO:` `get_return_requests_by_user_id(...)`: 封装 `sp_GetReturnRequestsByUserId`。
*   文件: `backend/tests/modules/chat/test_chat_message_dal.py`
    *   `[ ] TODO:` 编写 `ChatMessageDAL` 的单元测试。
*   文件: `backend/tests/modules/return_request/test_return_request_dal.py`
    *   `[ ] TODO:` 编写 `ReturnRequestDAL` 的单元测试。

### 2.6 通知与举报模块

*   文件: `backend/src/modules/notification/dal/system_notification_dal.py`
    *   `[ ] TODO:` `SystemNotificationDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `send_system_notification(...)`: 封装 `sp_SendSystemNotification`。
    *   `[ ] TODO:` `get_user_notifications(...)`: 封装 `sp_GetUserNotifications`。
    *   `[ ] TODO:` `mark_notification_as_read(...)`: 封装 `sp_MarkNotificationAsRead`。
    *   `[ ] TODO:` `delete_notification(...)`: 封装 `sp_DeleteNotification`。
*   文件: `backend/src/modules/report/dal/report_dal.py`
    *   `[ ] TODO:` `ReportDAL` 类定义，注入数据库连接池。
    *   `[ ] TODO:` `create_report(...)`: 封装 `sp_CreateReport`。
    *   `[ ] TODO:` `get_report_list(...)`: 封装 `sp_GetReportList`。
    *   `[ ] TODO:` `handle_report(...)`: 封装 `sp_HandleReport`。
*   文件: `backend/tests/modules/notification/test_system_notification_dal.py`
    *   `[ ] TODO:` 编写 `SystemNotificationDAL` 的单元测试。
*   文件: `backend/tests/modules/report/test_report_dal.py`
    *   `[ ] TODO:` 编写 `ReportDAL` 的单元测试。

---

## 3. 后端 Service 层 (Python)

**概述:** 本层包含核心业务逻辑、数据转换、以及协调 DAL 和其他外部服务（如邮件、支付）。

### 3.1 用户模块

*   文件: `backend/src/modules/user/services/user_service.py`
    *   `[√] DONE:` `UserService` 类定义，注入 `UserDAL`。
    *   `[√] DONE:` `create_user(...)`: 业务逻辑（检查重复、密码哈希、调用 DAL 创建用户、生成Token、发送邮件）。
    *   `[√] DONE:` `authenticate_user_and_create_token(...)`: 业务逻辑（验证密码、检查用户状态、生成 JWT）。
    *   `[√] DONE:` `get_user_profile_by_id(...)`: 获取用户详情（可能进行数据转换）。
    *   `[√] DONE:` `update_user_profile(...)`: 业务逻辑（调用 DAL 更新、处理头像URL等）。
    *   `[√] DONE:` `update_user_password(...)`: 业务逻辑（验证旧密码、哈希新密码、调用 DAL 更新）。
    *   `[√] DONE:` `delete_user(...)`: 业务逻辑（调用 DAL 删除）。
    *   `[√] DONE:` `request_verification_email(...)`: 业务逻辑（调用 DAL 生成Token、发送邮件）。
    *   `[√] DONE:` `verify_email(...)`: 业务逻辑（验证Token有效期、更新 DAL 状态）。
    *   `[√] DONE:` `get_system_notifications(...)`: 调用 DAL 获取系统通知。
    *   `[√] DONE:` `mark_system_notification_as_read(...)`: 调用 DAL 标记通知已读。
    *   `[√] DONE:` `change_user_status(...)`: 调用 DAL 更改用户状态（管理员）。
    *   `[√] DONE:` `adjust_user_credit(...)`: 调用 DAL 调整用户信用分（管理员）。
    *   `[√] DONE:` `get_all_users(...)`: 调用 DAL 获取所有用户列表（管理员）。
    *   `[ ] TODO:` 实现用户注册魔术链接的核心逻辑，包括Token生成、邮件发送和验证流程。
*   文件: `backend/tests/modules/user/test_user_service.py`
    *   `[√] DONE:` 编写 `UserService` 中所有业务方法的单元测试，使用 Mocking 模拟 `UserDAL` 及其他外部服务。

### 3.2 商品模块

*   文件: `backend/src/modules/product/services/product_service.py`
    *   `[√] TODO:` `ProductService` 类定义，注入 `ProductDAL`, `ProductImageDAL`, `UserFavoriteDAL`。
    *   `[√] TODO:` `create_product(...)`: 业务逻辑（数据验证、调用 `ProductDAL.create_product`，处理图片上传并调用 `ProductImageDAL.add_product_image`）。
    *   `[√] TODO:` `update_product(...)`: 业务逻辑（数据验证、权限检查、调用 `ProductDAL.update_product`，处理图片更新）。
    *   `[√] TODO:` `delete_product(...)`: 业务逻辑（权限检查、调用 `ProductDAL.delete_product`）。
    *   `[√] TODO:` `activate_product(...)`: 业务逻辑（管理员权限检查、调用 `ProductDAL.activate_product`）。
    *   `[√] TODO:` `reject_product(...)`: 业务逻辑（管理员权限检查、调用 `ProductDAL.reject_product`）。
    *   `[√] TODO:` `withdraw_product(...)`: 业务逻辑（权限检查、调用 `ProductDAL.withdraw_product`）。
    *   `[√] TODO:` `get_product_list(...)`: 业务逻辑（调用 `ProductDAL.get_product_list`，可能包含数据转换或聚合图片信息）。
    *   `[√] TODO:` `get_product_detail(...)`: 业务逻辑（调用 `ProductDAL.get_product_by_id` 和 `ProductImageDAL.get_images_by_product_id`，整合商品和图片信息）。
    *   `[√] TODO:` `add_favorite(...)`: 业务逻辑（调用 `UserFavoriteDAL.add_user_favorite`，处理重复收藏异常）。
    *   `[√] TODO:` `remove_favorite(...)`: 业务逻辑（调用 `UserFavoriteDAL.remove_user_favorite`）。
    *   `[√] TODO:` `get_user_favorites(...)`: 业务逻辑（调用 `UserFavoriteDAL.get_user_favorite_products`）。
*   文件: `backend/tests/modules/product/test_product_service.py`
    *   `[√] TODO:` 编写 `ProductService` 的单元测试。

### 3.3 评价模块

*   文件: `backend/src/modules/evaluation/services/evaluation_service.py`
    *   `[ ] TODO:` `EvaluationService` 类定义，注入 `EvaluationDAL`, `OrderDAL`, `UserDAL`。
    *   `[ ] TODO:` `create_evaluation(...)`: 业务逻辑（检查订单状态是否为已完成，检查是否已评价，调用 `EvaluationDAL.create_evaluation`，触发用户信用分更新）。
    *   `[ ] TODO:` `get_seller_evaluations(...)`: 业务逻辑（调用 `EvaluationDAL.get_evaluations_by_seller_id`）。
*   文件: `backend/tests/modules/evaluation/test_evaluation_service.py`
    *   `[ ] TODO:` 编写 `EvaluationService` 的单元测试。

### 3.4 交易模块

*   文件: `backend/src/modules/order/services/order_service.py`
    *   `[ ] TODO:` `OrderService` 类定义，注入 `OrderDAL`, `ProductDAL`。
    *   `[ ] TODO:` `create_order(...)`: 业务逻辑（检查商品库存、调用 `ProductDAL.decrease_product_quantity`，调用 `OrderDAL.create_order`，处理事务）。
    *   `[ ] TODO:` `confirm_order(...)`: 业务逻辑（权限检查，检查订单状态，调用 `OrderDAL.confirm_order`）。
    *   `[ ] TODO:` `complete_order(...)`: 业务逻辑（权限检查，检查订单状态，调用 `OrderDAL.complete_order`）。
    *   `[ ] TODO:` `cancel_order(...)`: 业务逻辑（权限检查，检查订单状态，调用 `OrderDAL.cancel_order`，调用 `ProductDAL.increase_product_quantity`，处理事务）。
    *   `[ ] TODO:` `get_user_orders(...)`: 业务逻辑（调用 `OrderDAL.get_orders_by_user_id`，可能进行数据聚合）。
    *   `[ ] TODO:` `get_order_detail(...)`: 业务逻辑（调用 `OrderDAL.get_order_by_id`）。
*   文件: `backend/tests/modules/order/test_order_service.py`
    *   `[ ] TODO:` 编写 `OrderService` 的单元测试。

### 3.5 消息与退货模块

*   文件: `backend/src/modules/chat/services/chat_service.py`
    *   `[ ] TODO:` `ChatService` 类定义，注入 `ChatMessageDAL`。
    *   `[ ] TODO:` `send_message(...)`: 业务逻辑（数据验证，调用 `ChatMessageDAL.send_message`）。
    *   `[ ] TODO:` `get_conversations(...)`: 业务逻辑（调用 `ChatMessageDAL.get_user_conversations`）。
    *   `[ ] TODO:` `get_messages_between_users_for_product(...)`: 业务逻辑（调用 `ChatMessageDAL.get_chat_messages_by_product_and_users`）。
    *   `[ ] TODO:` `mark_message_as_read(...)`: 业务逻辑（调用 `ChatMessageDAL.mark_message_as_read`）。
    *   `[ ] TODO:` `hide_conversation(...)`: 业务逻辑（调用 `ChatMessageDAL.hide_conversation`）。
*   文件: `backend/src/modules/return_request/services/return_request_service.py`
    *   `[ ] TODO:` `ReturnRequestService` 类定义，注入 `ReturnRequestDAL`, `OrderDAL`, `ProductDAL`。
    *   `[ ] TODO:` `create_return_request(...)`: 业务逻辑（检查订单状态，调用 `ReturnRequestDAL.create_return_request`）。
    *   `[ ] TODO:` `handle_return_request(...)`: 业务逻辑（卖家权限检查，调用 `ReturnRequestDAL.handle_return_request`，如果同意退货则恢复商品库存并更新订单状态）。
    *   `[ ] TODO:` `buyer_request_intervention(...)`: 业务逻辑（买家权限检查，调用 `ReturnRequestDAL.buyer_request_intervention`）。
    *   `[ ] TODO:` `admin_resolve_return_request(...)`: 业务逻辑（管理员权限检查，调用 `ReturnRequestDAL.admin_resolve_return_request`，可能涉及信用分调整）。
    *   `[ ] TODO:` `get_return_request_detail(...)`: 业务逻辑（调用 `ReturnRequestDAL.get_return_request_by_id`）。
    *   `[ ] TODO:` `get_user_return_requests(...)`: 业务逻辑（调用 `ReturnRequestDAL.get_return_requests_by_user_id`）。
*   文件: `backend/tests/modules/chat/test_chat_service.py`
    *   `[ ] TODO:` 编写 `ChatService` 的单元测试。
*   文件: `backend/tests/modules/return_request/test_return_request_service.py`
    *   `[ ] TODO:` 编写 `ReturnRequestService` 的单元测试。

### 3.6 通知与举报模块

*   文件: `backend/src/modules/notification/services/system_notification_service.py`
    *   `[ ] TODO:` `SystemNotificationService` 类定义，注入 `SystemNotificationDAL`。
    *   `[ ] TODO:` `send_notification(...)`: 业务逻辑（调用 `SystemNotificationDAL.send_system_notification`）。
    *   `[ ] TODO:` `get_user_notifications(...)`: 业务逻辑（调用 `SystemNotificationDAL.get_user_notifications`）。
    *   `[ ] TODO:` `mark_notification_as_read(...)`: 业务逻辑（调用 `SystemNotificationDAL.mark_notification_as_read`）。
    *   `[ ] TODO:` `delete_notification(...)`: 业务逻辑（调用 `SystemNotificationDAL.delete_notification`）。
*   文件: `backend/src/modules/report/services/report_service.py`
    *   `[ ] TODO:` `ReportService` 类定义，注入 `ReportDAL`。
    *   `[ ] TODO:` `create_report(...)`: 业务逻辑（数据验证，调用 `ReportDAL.create_report`）。
    *   `[ ] TODO:` `get_reports(...)`: 业务逻辑（管理员权限检查，调用 `ReportDAL.get_report_list`）。
    *   `[ ] TODO:` `handle_report(...)`: 业务逻辑（管理员权限检查，调用 `ReportDAL.handle_report`，可能触发用户信用分调整或商品下架等联动操作）。
*   文件: `backend/tests/modules/notification/test_system_notification_service.py`
    *   `[ ] TODO:` 编写 `SystemNotificationService` 的单元测试。
*   文件: `backend/tests/modules/report/test_report_service.py`
    *   `[ ] TODO:` 编写 `ReportService` 的单元测试。

---

## 4. 后端 API 层 (Python)

**概述:** 本层负责接收 HTTP 请求，进行请求数据验证，调用 Service 层，并返回 HTTP 响应。

### 4.1 用户认证与账户管理

*   文件: `backend/src/modules/user/api/auth_routes.py`
    *   `[√] DONE:` `APIRouter` 定义。
    *   `[√] DONE:` `POST /api/v1/auth/register`: 调用 `UserService.create_user`。
    *   `[√] DONE:` `POST /api/v1/auth/login`: 调用 `UserService.authenticate_user_and_create_token`。
    *   `[√] DONE:` `POST /api/v1/auth/request-verification-email`: 调用 `UserService.request_verification_email`。
    *   `[√] DONE:` `POST /api/v1/auth/verify-email`: 调用 `UserService.verify_email`。
    *   `[!] OPTIONAL:` `POST /api/v1/auth/resend-verification-email`: 调用 `UserService.resend_verification_email` (如果实现)。
*   文件: `backend/src/modules/user/api/user_profile_routes.py` (当前是 `app/routers/users.py`)
    *   `[√] DONE:` `GET /api/v1/users/me`: 获取当前用户资料 (依赖 `get_current_user` 认证)。
    *   `[√] DONE:` `PUT /api/v1/users/me`: 更新当前用户资料 (依赖 `get_current_user` 认证)。
    *   `[√] DONE:` `PUT /api/v1/users/me/password`: 更新当前用户密码 (依赖 `get_current_user` 认证)。
    *   `[√] DONE:` `GET /api/v1/users/{user_id}`: 管理员获取用户资料 (依赖 `get_current_active_admin_user` 认证)。
    *   `[√] DONE:` `PUT /api/v1/users/{user_id}`: 管理员更新用户资料 (依赖 `get_current_active_admin_user` 认证)。
    *   `[√] DONE:` `DELETE /api/v1/users/{user_id}`: 管理员删除用户 (依赖 `get_current_active_admin_user` 认证)。
    *   `[√] DONE:` `PUT /api/v1/users/{user_id}/status`: 管理员更改用户状态 (依赖 `get_current_active_admin_user` 认证)。
    *   `[√] DONE:` `PUT /api/v1/users/{user_id}/credit`: 管理员调整用户信用分 (依赖 `get_current_active_admin_user` 认证)。
    *   `[√] DONE:` `GET /api/v1/users/`: 管理员获取所有用户列表 (依赖 `get_current_active_admin_user` 认证)。
    *   `[ ] TODO:` `POST /api/v1/users/me/avatar`: 上传用户头像 (文件上传处理，调用 `UserService.update_user_profile`)。
*   文件: `backend/tests/modules/user/test_user_api.py` (当前是 `tests/test_users_api.py`)
    *   `[√] DONE:` 编写 API 接口的集成测试，使用 `httpx.AsyncClient`，可以 Mock `UserService`。
    *   `[ ] TODO:` `/api/v1/users/{user_id}/status`: 测试无效状态值。
    *   `[√] DONE:` `/api/v1/users/{user_id}/credit`: 测试缺少 `reason` 字段。
    *   `[√] DONE:` `/api/v1/users/{user_id}/credit`: 测试信用分调整超出限制（已测试超过最大值和低于最小值）。
    *   `[√] DONE:` 编写管理员获取所有用户列表 `/api/v1/users/` 的测试。

### 4.2 商品接口

*   文件: `backend/src/modules/product/api/product_routes.py`
    *   `[√] TODO:` `APIRouter` 定义。
    *   `[√] TODO:` `POST /api/v1/products`: 发布商品 (依赖 `get_current_user` 认证，调用 `ProductService.create_product`)。
    *   `[√] TODO:` `PUT /api/v1/products/{product_id}`: 编辑商品 (依赖 `get_current_user` 认证，调用 `ProductService.update_product`)。
    *   `[√] TODO:` `DELETE /api/v1/products/{product_id}`: 删除商品 (依赖 `get_current_user` 或 `get_current_active_admin_user` 认证，调用 `ProductService.delete_product`)。
    *   `[√] TODO:` `GET /api/v1/products`: 获取商品列表（带分页、筛选、搜索参数，调用 `ProductService.get_product_list`)。
    *   `[√] TODO:` `GET /api/v1/products/{product_id}`: 获取商品详情 (调用 `ProductService.get_product_detail`)。
    *   `[√] TODO:` `PUT /api/v1/products/{product_id}/status/activate`: 管理员激活商品 (依赖 `get_current_active_admin_user` 认证，调用 `ProductService.activate_product`)。
    *   `[√] TODO:` `PUT /api/v1/products/{product_id}/status/reject`: 管理员拒绝商品 (依赖 `get_current_active_admin_user` 认证，调用 `ProductService.reject_product`)。
    *   `[√] TODO:` `PUT /api/v1/products/{product_id}/status/withdraw`: 商品拥有者下架商品 (依赖 `get_current_user` 认证，调用 `ProductService.withdraw_product`)。
*   文件: `backend/src/modules/product/api/favorite_routes.py`
    *   `[√] TODO:` `APIRouter` 定义。
    *   `[√] TODO:` `POST /api/v1/favorites/{product_id}`: 添加收藏 (依赖 `get_current_user` 认证，调用 `ProductService.add_favorite`)。
    *   `[√] TODO:` `DELETE /api/v1/favorites/{product_id}`: 移除收藏 (依赖 `get_current_user` 认证，调用 `ProductService.remove_favorite`)。
    *   `[√] TODO:` `GET /api/v1/favorites`: 获取用户收藏列表 (依赖 `get_current_user` 认证，调用 `ProductService.get_user_favorites`)。
*   文件: `backend/tests/modules/product/test_product_api.py`
    *   `[ ] TODO:` 编写商品 API 接口的集成测试。
*   文件: `backend/tests/modules/product/test_favorite_api.py`
    *   `[ ] TODO:` 编写收藏 API 接口的集成测试。

### 4.3 评价接口

*   文件: `backend/src/modules/evaluation/api/evaluation_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `POST /api/v1/evaluations`: 创建评价 (依赖 `get_current_user` 认证，调用 `EvaluationService.create_evaluation`)。
    *   `[ ] TODO:` `GET /api/v1/users/{user_id}/evaluations`: 获取卖家收到的评价列表 (调用 `EvaluationService.get_seller_evaluations`)。
*   文件: `backend/tests/modules/evaluation/test_evaluation_api.py`
    *   `[ ] TODO:` 编写评价 API 接口的集成测试。

### 4.4 交易接口

*   文件: `backend/src/modules/order/api/order_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `POST /api/v1/orders`: 创建订单 (依赖 `get_current_user` 认证，调用 `OrderService.create_order`)。
    *   `[ ] TODO:` `PUT /api/v1/orders/{order_id}/confirm`: 卖家确认订单 (依赖 `get_current_user` 认证，调用 `OrderService.confirm_order`)。
    *   `[ ] TODO:` `PUT /api/v1/orders/{order_id}/complete`: 买家确认收货 (依赖 `get_current_user` 认证，调用 `OrderService.complete_order`)。
    *   `[ ] TODO:` `PUT /api/v1/orders/{order_id}/cancel`: 取消订单 (依赖 `get_current_user` 认证，调用 `OrderService.cancel_order`)。
    *   `[ ] TODO:` `GET /api/v1/orders`: 获取当前用户的订单列表 (依赖 `get_current_user` 认证，支持 `is_seller` 和 `status` 筛选，调用 `OrderService.get_user_orders`)。
    *   `[ ] TODO:` `GET /api/v1/orders/{order_id}`: 获取订单详情 (依赖 `get_current_user` 认证，调用 `OrderService.get_order_detail`)。
*   文件: `backend/tests/modules/order/test_order_api.py`
    *   `[ ] TODO:` 编写交易 API 接口的集成测试。

### 4.5 消息与退货接口

*   文件: `backend/src/modules/chat/api/chat_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `POST /api/v1/chat/messages`: 发送消息 (依赖 `get_current_user` 认证，调用 `ChatService.send_message`)。
    *   `[ ] TODO:` `GET /api/v1/chat/conversations`: 获取用户会话列表 (依赖 `get_current_user` 认证，调用 `ChatService.get_conversations`)。
    *   `[ ] TODO:` `GET /api/v1/chat/messages/{product_id}/{other_user_id}`: 获取指定会话的聊天记录 (依赖 `get_current_user` 认证，调用 `ChatService.get_messages_between_users_for_product`)。
    *   `[ ] TODO:` `PUT /api/v1/chat/messages/{message_id}/read`: 标记消息已读 (依赖 `get_current_user` 认证，调用 `ChatService.mark_message_as_read`)。
    *   `[ ] TODO:` `PUT /api/v1/chat/conversations/{product_id}/hide`: 隐藏会话 (依赖 `get_current_user` 认证，调用 `ChatService.hide_conversation`)。
*   文件: `backend/src/modules/return_request/api/return_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `POST /api/v1/returns`: 提交退货请求 (依赖 `get_current_user` 认证，调用 `ReturnRequestService.create_return_request`)。
    *   `[ ] TODO:` `PUT /api/v1/returns/{request_id}/handle`: 卖家处理退货请求 (依赖 `get_current_user` 认证，调用 `ReturnRequestService.handle_return_request`)。
    *   `[ ] TODO:` `PUT /api/v1/returns/{request_id}/intervene`: 买家申请管理员介入 (依赖 `get_current_user` 认证，调用 `ReturnRequestService.buyer_request_intervention`)。
    *   `[ ] TODO:` `GET /api/v1/returns/admin`: 管理员获取所有退货请求 (依赖 `get_current_active_admin_user` 认证，调用 `ReturnRequestService.get_return_requests`)。
    *   `[ ] TODO:` `PUT /api/v1/returns/{request_id}/admin/resolve`: 管理员处理退货介入 (依赖 `get_current_active_admin_user` 认证，调用 `ReturnRequestService.admin_resolve_return_request`)。
    *   `[ ] TODO:` `GET /api/v1/returns/{request_id}`: 获取退货请求详情 (依赖 `get_current_user` 或 `get_current_active_admin_user` 认证，调用 `ReturnRequestService.get_return_request_detail`)。
    *   `[ ] TODO:` `GET /api/v1/returns/me`: 获取当前用户的退货请求列表 (依赖 `get_current_user` 认证，调用 `ReturnRequestService.get_user_return_requests`)。
*   文件: `backend/tests/modules/chat/test_chat_api.py`
    *   `[ ] TODO:` 编写消息 API 接口的集成测试。
*   文件: `backend/tests/modules/return_request/test_return_api.py`
    *   `[ ] TODO:` 编写退货 API 接口的集成测试。

### 4.6 通知与举报接口

*   文件: `backend/src/modules/notification/api/notification_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `GET /api/v1/notifications/me`: 获取当前用户通知列表 (依赖 `get_current_user` 认证，调用 `SystemNotificationService.get_user_notifications`)。
    *   `[ ] TODO:` `PUT /api/v1/notifications/{notification_id}/read`: 标记通知已读 (依赖 `get_current_user` 认证，调用 `SystemNotificationService.mark_notification_as_read`)。
    *   `[ ] TODO:` `DELETE /api/v1/notifications/{notification_id}`: 删除通知 (依赖 `get_current_user` 认证，调用 `SystemNotificationService.delete_notification`)。
    *   `[ ] TODO:` `POST /api/v1/notifications/send`: 管理员发送系统通知 (依赖 `get_current_active_admin_user` 认证，调用 `SystemNotificationService.send_notification`)。
*   文件: `backend/src/modules/report/api/report_routes.py`
    *   `[ ] TODO:` `APIRouter` 定义。
    *   `[ ] TODO:` `POST /api/v1/reports`: 提交举报 (依赖 `get_current_user` 认证，调用 `ReportService.create_report`)。
    *   `[ ] TODO:` `GET /api/v1/reports/admin`: 管理员获取举报列表 (依赖 `get_current_active_admin_user` 认证，调用 `ReportService.get_reports`)。
    *   `[ ] TODO:` `PUT /api/v1/reports/{report_id}/admin/handle`: 管理员处理举报 (依赖 `get_current_active_admin_user` 认证，调用 `ReportService.handle_report`)。
*   文件: `backend/tests/modules/notification/test_notification_api.py`
    *   `[ ] TODO:` 编写通知 API 接口的集成测试。
*   文件: `backend/tests/modules/report/test_report_api.py`
    *   `[ ] TODO:` 编写举报 API 接口的集成测试。

---

## 5. 后端通用组件与配置 (Python)

**概述:** 存放跨模块使用的工具、辅助函数、全局配置和依赖注入。

*   文件: `backend/src/config/settings.py` (当前是 `app/config.py`)
    *   `[√] DONE:` JWT 密钥和算法配置。
    *   `[ ] TODO:` 数据库连接字符串配置（通常通过环境变量注入，但配置文件中应有读取逻辑）。
    *   `[ ] TODO:` 邮件发送服务配置（SMTP 服务器、端口、用户名、密码）。
    *   `[ ] TODO:` 文件存储配置（例如，本地路径或云存储服务凭据）。
    *   `[ ] TODO:` 日志配置。
*   文件: `backend/src/common/security.py` (当前是 `app/utils/auth.py`)
    *   `[√] DONE:` 密码哈希 (Bcrypt)。
    *   `[√] DONE:` JWT token 生成与验证。
*   文件: `backend/src/common/exceptions.py` (当前是 `app/exceptions.py`)
    *   `[√] DONE:` 自定义 HTTP 异常类定义 (`NotFoundError`, `IntegrityError`, `DALError`, `AuthenticationError`, `ForbiddenError`, `ConflictError` 等)。
*   文件: `backend/src/common/email_sender.py`
    *   `[!] OPTIONAL:` 邮件发送服务封装（待实现，例如使用 `smtplib` 或 SendGrid/Mailgun 客户端）。
        *   方法: `send_verification_email(to_email, verification_link)`
        *   方法: `send_password_reset_email(to_email, reset_link)` (如果实现密码找回功能)
        *   方法: `send_notification_email(to_email, subject, body)`
*   文件: `backend/src/common/file_storage.py`
    *   `[ ] TODO:` 文件存储服务封装（待实现，例如本地文件存储或 S3 客户端）。
        *   方法: `upload_file(file_content, file_name, file_type)`: 上传文件并返回 URL。
        *   方法: `delete_file(file_url)`: 删除文件。
*   文件: `backend/src/dependencies.py`
    *   `[√] DONE:` `get_db_connection`: 数据库连接依赖注入（基于 `pyodbc`）。
    *   `[√] DONE:` `get_user_dal`: DAL 依赖注入。
    *   `[√] DONE:` `get_user_service`: Service 依赖注入。
    *   `[√] DONE:` `get_current_user`: JWT 认证和当前用户解析依赖注入。
    *   `[√] DONE:` `get_current_active_admin_user`: JWT 认证和当前活跃管理员用户解析依赖注入。
    *   `[ ] TODO:` 添加其他模块的 DAL 和 Service 依赖注入。
    *   `[ ] TODO:` 添加文件存储和邮件发送服务的依赖注入。
*   文件: `backend/src/main.py` (当前是 `app/main.py`)
    *   `[√] DONE:` FastAPI 应用实例化。
    *   `[√] DONE:` 注册所有 `APIRouter` (目前包含用户和认证)。
    *   `[√] DONE:` 添加 CORS 中间件。
    *   `[√] DONE:` 添加全局异常处理中间件。
    *   `[ ] TODO:` 注册所有其他模块的 `APIRouter`。
    *   `[ ] TODO:` 配置日志。

---

## 6. 前端 (Vue.js)

**概述:** 负责用户界面、状态管理、路由和与后端 API 的交互。

### 6.1 通用部分

*   文件: `frontend/src/api/client.js`
    *   `[ ] TODO:` Axios 客户端封装：设置 `baseURL`、请求拦截器（添加 JWT Token）、响应拦截器（统一错误处理、Token 过期刷新/重定向）。
    *   `[ ] TODO:` 封装通用 API 调用方法 (`get`, `post`, `put`, `delete`)。
*   文件: `frontend/src/router/index.js`
    *   `[ ] TODO:` 配置全局路由守卫（例如登录状态检查，未登录用户重定向到登录页）。
    *   `[ ] TODO:` 定义所有前端路由（登录、注册、个人主页、商品列表、商品详情、发布商品、订单列表、聊天页面、通知、举报、管理员面板等）。
*   文件: `frontend/src/utils/auth.js` (或 `src/utils/token.js`)
    *   `[ ] TODO:` JWT Token 的本地存储 (`localStorage`)、读取、清除方法。
    *   `[ ] TODO:` 判断用户是否登录 (`isLoggedIn()`)。
    *   `[ ] TODO:` 获取当前用户 ID (`getCurrentUserId()`)。
*   文件: `frontend/src/locales/`
    *   `[ ] TODO:` 国际化配置 (`vue-i18n`) 初始化（如果需要）。
*   文件: `frontend/src/components/common/Header.vue`
    *   `[ ] TODO:` 实现顶部导航栏，包含登录/注册入口、用户信息、发布商品按钮、消息/通知图标。
*   文件: `frontend/src/components/common/Footer.vue`
    *   `[ ] TODO:` 实现底部信息栏。
*   文件: `frontend/src/utils/form_validation.js`
    *   `[ ] TODO:` 封装通用的表单验证规则和方法。

### 6.2 用户模块

*   文件: `frontend/src/store/modules/user.js`
    *   `[ ] TODO:` Vuex `state`: `isLoggedIn`, `userInfo`, `authLoading`, `notifications`, `unreadNotificationCount`。
    *   `[ ] TODO:` Vuex `mutations`: `SET_LOGIN_STATUS`, `SET_USER_INFO`, `SET_NOTIFICATIONS`, `MARK_NOTIFICATION_AS_READ`, `UPDATE_UNREAD_COUNT`。
    *   `[ ] TODO:` Vuex `actions`: `login`, `register`, `logout`, `fetchUserInfo`, `updateUserProfile`, `updatePassword`, `requestVerificationEmail`, `verifyEmail`, `fetchNotifications`, `markNotificationAsRead`, `deleteNotification`。
*   文件: `frontend/src/views/auth/LoginView.vue`
    *   `[ ] TODO:` 实现登录表单及交互，包括表单验证、错误提示、成功跳转。
*   文件: `frontend/src/views/auth/RegisterView.vue`
    *   `[ ] TODO:` 实现注册表单及交互，包括表单验证、错误提示、成功跳转、提示邮箱验证。
*   文件: `frontend/src/views/auth/EmailVerificationView.vue`
    *   `[ ] TODO:` 处理邮箱验证链接的页面，调用后端接口完成验证。
*   文件: `frontend/src/views/user/ProfileView.vue`
    *   `[ ] TODO:` 显示用户个人信息（头像、用户名、信用分、专业、简介、手机号、注册时间）。
    *   `[ ] TODO:` 提供跳转到个人信息编辑、我的发布、我的订单、我的收藏等页面的入口。
*   文件: `frontend/src/views/user/ProfileEditView.vue`
    *   `[ ] TODO:` 实现个人信息编辑表单，包括上传头像功能（调用后端文件上传 API）。
    *   `[ ] TODO:` 实现修改密码功能。
*   文件: `frontend/src/views/user/NotificationsView.vue`
    *   `[ ] TODO:` 显示系统通知列表，支持分页和标记已读。

### 6.3 商品模块

*   文件: `frontend/src/store/modules/product.js`
    *   `[ ] TODO:` Vuex `state`: `productList`, `productDetail`, `userFavorites`, `loading`。
    *   `[ ] TODO:` Vuex `actions`: `fetchProductList`, `fetchProductDetail`, `createProduct`, `updateProduct`, `deleteProduct`, `toggleFavorite`, `fetchUserFavorites`。
*   文件: `frontend/src/views/product/ProductListView.vue`
    *   `[ ] TODO:` 实现商品列表展示页面，包含搜索、筛选（分类、价格区间、状态）功能。
    *   `[ ] TODO:` 商品卡片展示（图片、标题、价格、发布者）。
    *   `[ ] TODO:` 分页功能。
*   文件: `frontend/src/views/product/ProductDetailView.vue`
    *   `[ ] TODO:` 实现商品详情页面，包含商品图片轮播、详细描述、价格、发布者信息。
    *   `[ ] TODO:` 收藏/取消收藏按钮。
    *   `[ ] TODO:` "立即购买"按钮（跳转到订单确认或聊天）。
    *   `[ ] TODO:` "联系卖家"按钮（跳转到聊天页面）。
*   文件: `frontend/src/views/product/ProductPostView.vue`
    *   `[ ] TODO:` 实现商品发布/编辑表单，包括图片上传组件、分类选择。
*   文件: `frontend/src/views/product/UserProductsView.vue`
    *   `[ ] TODO:` 显示当前用户发布的商品列表，支持上下架操作。
*   文件: `frontend/src/views/product/UserFavoritesView.vue`
    *   `[ ] TODO:` 显示当前用户收藏的商品列表。

### 6.4 评价模块

*   文件: `frontend/src/store/modules/evaluation.js`
    *   `[ ] TODO:` Vuex `state`: `sellerEvaluations`。
    *   `[ ] TODO:` Vuex `actions`: `createEvaluation`, `fetchSellerEvaluations`。
*   文件: `frontend/src/components/evaluation/EvaluationForm.vue`
    *   `[ ] TODO:` 实现评价表单（星级选择、内容输入），通常用于订单完成页。
*   文件: `frontend/src/components/evaluation/EvaluationList.vue`
    *   `[ ] TODO:` 实现评价列表展示组件（例如在卖家主页或商品详情页）。

### 6.5 交易模块

*   文件: `frontend/src/store/modules/order.js`
    *   `[ ] TODO:` Vuex `state`: `myOrders` (买家), `sellerOrders` (卖家)。
    *   `[ ] TODO:` Vuex `actions`: `createOrder`, `confirmOrder`, `completeOrder`, `cancelOrder`, `fetchMyOrders`, `fetchSellerOrders`, `fetchOrderDetail`。
*   文件: `frontend/src/views/order/OrderConfirmationView.vue`
    *   `[ ] TODO:` 订单确认页面（展示商品信息、价格、数量，确认购买）。
*   文件: `frontend/src/views/order/OrderListView.vue`
    *   `[ ] TODO:` 买家订单列表页面，支持状态筛选。
    *   `[ ] TODO:` 卖家订单列表页面，支持状态筛选。
*   文件: `frontend/src/views/order/OrderDetailView.vue`
    *   `[ ] TODO:` 订单详情页面，展示订单状态、商品信息、买家/卖家信息。
    *   `[ ] TODO:` 根据订单状态显示不同操作按钮（如"确认收货"、"取消订单"、"联系卖家"、"发起退货"）。

### 6.6 消息与退货模块

*   文件: `frontend/src/store/modules/chat.js`
    *   `[ ] TODO:` Vuex `state`: `conversations`, `currentChatMessages`.
    *   `[ ] TODO:` Vuex `actions`: `fetchConversations`, `fetchChatMessages`, `sendMessage`, `markMessageAsRead`, `hideConversation`。
*   文件: `frontend/src/views/chat/ChatListView.vue`
    *   `[ ] TODO:` 聊天会话列表页面（显示与不同商品/用户的会话）。
*   文件: `frontend/src/views/chat/ChatRoomView.vue`
    *   `[ ] TODO:` 聊天室页面，显示消息记录，输入框发送消息。
    *   `[ ] TODO:` 实时消息更新（WebSocket 集成）。
*   文件: `frontend/src/store/modules/return.js`
    *   `[ ] TODO:` Vuex `state`: `myReturnRequests`, `sellerReturnRequests`, `adminReturnRequests`。
    *   `[ ] TODO:` Vuex `actions`: `createReturnRequest`, `handleReturnRequest`, `buyerRequestIntervention`, `adminResolveReturnRequest`, `fetchMyReturnRequests`, `fetchReturnRequestDetail`。
*   文件: `frontend/src/views/return/ReturnRequestForm.vue`
    *   `[ ] TODO:` 发起退货请求表单（填写退货原因）。
*   文件: `frontend/src/views/return/ReturnRequestListView.vue`
    *   `[ ] TODO:` 买家退货请求列表页面。
    *   `[ ] TODO:` 卖家待处理退货请求列表页面。
*   文件: `frontend/src/views/return/ReturnRequestDetailView.vue`
    *   `[ ] TODO:` 退货请求详情页面，展示退货状态、原因、处理意见。
    *   `[ ] TODO:` 根据状态显示操作按钮（如"同意退货"、"拒绝退货"、"申请介入"）。

### 6.7 举报模块

*   文件: `frontend/src/store/modules/report.js`
    *   `[ ] TODO:` Vuex `state`: `reportList` (管理员)。
    *   `[ ] TODO:` Vuex `actions`: `createReport`, `fetchReportList` (管理员), `handleReport` (管理员)。
*   文件: `frontend/src/components/report/ReportForm.vue`
    *   `[ ] TODO:` 举报表单（选择举报对象：用户/商品/订单，填写举报内容）。
*   文件: `frontend/src/views/admin/ReportManagementView.vue`
    *   `[ ] TODO:` 管理员举报管理页面，显示所有举报列表，支持处理操作。

---

## 7. 其他待办事项

*   `[ ] TODO:` 完成 `sql_scripts/TODO.md` 中剩余的数据库层待办事项。
*   `[ ] TODO:` 完成商品、评价、交易、消息与退货、通知与举报模块的 DAL、Service 和 API 实现。
*   `[ ] TODO:` 为所有 Service 和 API 方法编写单元测试。
*   `[ ] TODO:` 实现文件上传服务（后端接口及前端调用）。
*   `[ ] TODO:` 实现邮件发送服务（后端封装及与 Service 层的集成）。
*   `[ ] TODO:` 实现 WebSocket 实时通讯（后端 WebSocket 服务器和前端客户端）。
*   `[ ] TODO:` 实现管理员后台界面：
    *   `[ ] TODO:` 用户管理（禁用/启用用户、调整信用分）。
    *   `[ ] TODO:` 商品审核（激活/拒绝商品）。
    *   `[ ] TODO:` 退货申请管理（介入处理）。
    *   `[ ] TODO:` 举报管理（查看、处理举报）。
    *   `[ ] TODO:` 系统通知发送。
*   `[ ] TODO:` 编写前后端集成测试用例。
*   `[ ] TODO:` 完善部署指南。
*   `[ ] TODO:` 完善 API 文档。
*   `[ ] TODO:` 性能优化：数据库索引、缓存机制。
*   `[ ] TODO:` 安全加固：输入验证、速率限制、XSS/CSRF 防护。
*   `[ ] TODO:` 错误日志和监控系统集成。
*   `[ ] TODO:` **考虑将用户注册时的魔术链接发送逻辑放在后端实现，以增强安全性和鲁棒性。**

---

### **如何使用这个 TODO 文档：**

1.  **初始填充:** 团队领导或架构师最初填充好所有已知任务、文件路径和预期的层级职责。
2.  **团队认领:** 团队成员根据分配的模块或技能特长，在相应任务后添加自己的姓名/缩写，表示认领。
3.  **每日更新:** 每位开发者在完成任务、开始新任务或遇到阻塞时，更新对应的 TODO 项状态（`[ ]` 到 `[√] DONE:`，或者 `[!] OPTIONAL:`，`[#] PENDING:`）。
4.  **定期评审:** 在每周的项目会议中，团队可以过一遍这个文档，了解整体进度，讨论阻塞点，并重新分配任务。
5.  **Git 版本控制:** 将这个 `TODO.md` 文件纳入 Git 版本控制，确保所有成员都在同一个最新版本上工作。每次更新后提交。

这种详细的 TODO 文档结构，将为你们的"思源淘"项目提供卓越的可见性和协作效率。祝你们项目顺利！ 