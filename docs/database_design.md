# 交大二手交易平台后端数据库设计文档

本文档详细描述了基于原生 SQL Server 存储过程和触发器的数据库设计，梳理了各个模块的功能及核心业务流程中存储过程和触发器的作用。

## 设计原则概览

本数据库设计遵循以下原则：

*   **数据完整性优先**: 通过主键、外键、唯一约束、检查约束在数据库层面保证数据准确性和一致性。
*   **业务逻辑下沉**: 将核心、原子性的业务操作（如创建订单、更新库存、处理评价）通过存储过程实现，减少应用层与数据库的往返，提高性能。
*   **事件驱动与自动化**: 使用触发器在数据发生特定变化时自动执行相关操作（如库存变化更新商品状态，订单完成更新信用分，评价插入更新信用分），简化应用层逻辑并保证数据同步。
*   **事务管理**: 在涉及多个步骤的复杂操作中使用事务，确保操作的原子性和一致性。
*   **错误处理**: 存储过程包含错误捕获和处理机制，提高系统健壮性。
*   **权限分离**: 在存储过程中区分用户和管理员操作，通过参数验证实现权限控制。

## 模块功能分析

### 1. 用户模块 (User)

负责用户账户管理、认证、基本信息维护、收藏以及系统通知的接收和管理。

**相关表:**

*   `[User]`：用户基本信息、状态、信用分、认证状态等。
*   `[UserFavorite]`：用户收藏的商品。
*   `[SystemNotification]`：系统发送给用户的通知。

**存储过程:**

*   `sp_GetUserProfileById (@userId)`: 根据用户ID获取用户公开信息，用于展示个人主页等。
*   `sp_GetUserByUsernameWithPassword (@username)`: 根据用户名获取用户（包含密码哈希），用于登录验证。
*   `sp_CreateUser (@username, @passwordHash, @email)`: 创建新用户，检查用户名和邮箱唯一性，设置初始状态和信用分。
*   `sp_UpdateUserProfile (@userId, ...)`: 更新用户个人信息（专业、头像、简介、手机号），检查手机号唯一性。
*   `sp_GetUserPasswordHashById (@userId)`: 根据用户ID获取密码哈希，用于密码修改等场景。
*   `sp_UpdateUserPassword (@userId, @newPasswordHash)`: 更新用户密码。
*   `sp_RequestMagicLink (@email)`: 用户请求魔术链接，用于无密码登录或注册。查找用户，如果是新用户则创建，老用户则更新 token。
*   `sp_VerifyMagicLink (@token)`: 验证魔术链接，完成用户邮箱认证（`IsVerified = 1`），清除 token。
*   `sp_GetSystemNotificationsByUserId (@userId)`: 获取某个用户的系统通知列表。
*   `sp_MarkNotificationAsRead (@notificationId, @userId)`: 将指定系统通知标记为已读，验证操作者是通知接收者。

**触发器:**

*   用户模块本身没有直接关联的触发器，但其信用分 (`Credit`) 的变化会受到交易模块和评价模块触发器的影响。

### 2. 商品模块 (Product)

负责商品的发布、查询、更新、删除、审核和下架。

**相关表:**

*   `[Product]`：商品基本信息（名称、描述、价格、数量、状态、发布者等）。
*   `[ProductImage]`：商品的图片信息。
*   `[UserFavorite]`：用户收藏（也与商品相关）。

**存储过程:**

*   `sp_GetProductList (@searchQuery, @categoryName, @minPrice, @maxPrice, @page, @pageSize, @sortBy, @sortOrder, @status)`: 获取商品列表，支持多条件过滤、分页和排序，是核心的商品展示接口。
*   `sp_GetProductDetail (@productId)`: 获取单个商品详细信息，包括发布者信息和所有图片列表。
*   `sp_CreateProduct (@ownerId, @productName, @price, @quantity, @imageUrls)`: 发布新商品。检查发布者认证状态、数量价格有效性，插入 Product 记录，并解析图片URL批量创建 ProductImage 记录。初始状态为 'PendingReview'。
*   `sp_UpdateProduct (@productId, @userId, ...)`: 更新商品信息。检查操作者是否为商品所有者，检查商品状态是否允许修改（Sold 状态不允许），更新指定字段。
*   `sp_DeleteProduct (@productId, @userId)`: 删除商品。检查操作者是否为商品所有者。删除 Product 记录，由于外键约束，关联的 ProductImage 和 UserFavorite 记录也会被级联删除。
*   `sp_ReviewProduct (@productId, @adminId, @newStatus, @reason)`: 管理员审核商品（从 'PendingReview' 到 'Active' 或 'Rejected'）。检查管理员权限，更新商品状态，并通知商品发布者。
*   `sp_WithdrawProduct (@productId, @userId)`: 卖家主动下架商品。检查操作者是否为商品所有者，检查当前状态是否允许下架，更新商品状态为 'Withdrawn'。
*   `sp_AddFavoriteProduct (@userId, @productId)`: 将商品添加到用户的收藏列表。
*   `sp_RemoveFavoriteProduct (@userId, @productId)`: 将商品从用户的收藏列表移除。
*   `sp_GetUserFavoriteProducts (@userId)`: 获取用户收藏的商品列表。

**触发器:**

*   `tr_Product_AfterUpdate_QuantityStatus`: 在 `[Product]` 表更新后触发。当商品数量 `Quantity` 从 >0 变为 0 时，自动将商品状态 `Status` 设为 'Sold'；当 Quantity 从 0 变为 >0 (例如订单取消恢复库存) 且原状态为 'Sold' 时，自动将 Status 设为 'Active'。这是维护商品在售状态与库存一致性的核心触发器。

### 3. 交易模块 (Trade)

处理用户之间的订单创建、确认、取消、完成以及退货请求和管理员介入。

**相关表:**

*   `[Order]`：记录用户之间的交易订单。
*   `[ReturnRequest]`：记录买家发起的退货请求。

**存储过程:**

*   `sp_GetOrdersByUser (@userId, @role)`: 获取用户（买家或卖家）的订单列表，是用户查看自己交易记录的核心接口。
*   `sp_GetOrderById (@orderId, @userId)`: 获取单个订单详细信息，包含买家、卖家、商品信息，并进行权限检查（买家、卖家或管理员可查看）。
*   `sp_CreateOrder (@buyerId, @productId, @quantity)`: **核心业务流程：买家下单。** 检查买家认证、商品状态和库存。扣减商品库存，插入 Order 记录，状态为 'PendingSellerConfirmation'。保证原子性。
*   `sp_ConfirmOrder (@orderId, @sellerId)`: **核心业务流程：卖家确认订单。** 检查操作者是卖家且订单状态为 'PendingSellerConfirmation'。更新订单状态为 'ConfirmedBySeller'。
*   `sp_RejectOrder (@orderId, @sellerId, @reason)`: **核心业务流程：卖家拒绝订单。** 检查操作者是卖家且订单状态为 'PendingSellerConfirmation'。必须提供原因。更新订单状态为 'Cancelled'。库存恢复由触发器处理。
*   `sp_CompleteOrder (@orderId, @buyerId)`: **核心业务流程：买家确认收货。** 检查操作者是买家且订单状态为 'ConfirmedBySeller'。更新订单状态为 'Completed'。完成后触发信用分更新。
*   `sp_RequestReturn (@orderId, @buyerId, @reason)`: **核心业务流程：买家发起退货请求。** 检查操作者是买家且订单状态允许退货。检查是否已存在请求。插入 ReturnRequest 记录，状态为 'ReturnRequested'。
*   `sp_SellerProcessReturn (@returnRequestId, @sellerId, @agree, @sellerIdea)`: **核心业务流程：卖家处理退货请求。** 检查操作者是卖家且请求状态为 'ReturnRequested'。更新 ReturnRequest 状态 ('ReturnAccepted'/'ReturnRejected')。如果同意，恢复商品库存。
*   `sp_BuyerRequestIntervention (@returnRequestId, @buyerId)`: **核心业务流程：买家申请管理员介入退货。** 检查操作者是买家且请求状态允许介入。更新 ReturnRequest 状态为 'InterventionRequested'。
*   `sp_AdminProcessReturnIntervention (@returnRequestId, @adminId, @finalStatus, @adminResult)`: **核心业务流程：管理员处理介入的退货请求。** 检查管理员权限且请求状态为 'InterventionRequested'。根据最终状态更新 ReturnRequest。如果同意，恢复库存并处理可能的信用分调整。通知相关方。

**触发器:**

*   `tr_Order_AfterCancel_RestoreQuantity`: 在 `[Order]` 表更新后触发。当订单状态从非 'Cancelled' 变为 'Cancelled' 时，恢复关联商品对应的库存数量。与 `tr_Product_AfterUpdate_QuantityStatus` 配合，确保商品状态正确反映库存。
*   `tr_Order_AfterComplete_UpdateSellerCredit`: 在 `[Order]` 表更新后触发。当订单状态从非 'Completed' 变为 'Completed' 时，增加订单卖家对应的信用分（上限 100）。这是完成交易后自动奖励卖家的机制。

### 4. 评价模块 (Evaluation)

负责买家对卖家的交易评价。

**相关表:**

*   `[Evaluation]`：记录评价信息（订单、买家、卖家、评分、内容）。

**存储过程:**

*   `sp_GetEvaluationsByOrder (@orderId)`: 获取某个订单的评价详情。
*   `sp_CreateEvaluation (@orderId, @buyerId, @rating, @content)`: **核心业务流程：买家提交评价。** 检查订单已完成、操作者是买家、评分有效且未评价过该订单。插入 Evaluation 记录。插入后触发信用分更新。

**触发器:**

*   `tr_Evaluation_AfterInsert_UpdateSellerCredit`: 在 `[Evaluation]` 表插入后触发。根据新插入评价的评分 (`Rating`)，自动调整被评价的卖家的信用分（0-100 范围内），是评价直接影响卖家信用分的自动化机制。

### 5. 聊天模块 (Chat)

负责用户之间围绕商品的聊天消息。

**相关表:**

*   `[ChatMessage]`：记录聊天消息（发送者、接收者、商品、内容、时间、状态）。

**存储过程:**

*   `sp_SendMessage (@senderId, @receiverId, @productId, @content)`: 用户发送消息。检查用户和商品存在，插入 ChatMessage 记录。
*   `sp_GetChatMessagesByProduct (@productId, @userId)`: 获取某个商品相关的聊天记录。包含权限检查（商品所有者或参与者），并根据可见性字段过滤逻辑删除的消息。
*   `sp_MarkMessageAsRead (@messageId, @userId)`: 标记指定消息为已读，验证操作者是接收者。
*   `sp_SetChatMessageVisibility (@messageId, @userId, @visibleTo, @isVisible)`: 设置消息对发送者或接收者的可见性（逻辑删除）。

**触发器:**

*   聊天模块没有直接关联的触发器。

### 6. 管理员模块 (Admin)

包含管理员对用户、商品、举报等进行管理的功能。

**相关表:**

*   `[User]` (通过 IsStaff 字段区分管理员)
*   `[Report]`：记录用户或管理员提交的举报。
*   `[SystemNotification]`：管理员可以发布系统通知。

**存储过程:**

*   `sp_ChangeUserStatus (@userId, @newStatus, @adminId)`: 管理员禁用/启用用户账户。验证管理员权限。
*   `sp_AdjustUserCredit (@userId, @creditAdjustment, @adminId, @reason)`: 管理员手动调整用户信用分。验证管理员权限，必须提供原因。
*   `sp_ProcessReport (@reportId, @adminId, @newStatus, @processingResult)`: **核心业务流程：管理员处理举报。** 验证管理员权限且举报状态为 Pending。更新举报状态。根据结果（Resolved/Rejected）执行相应后续操作（如禁用用户、下架商品），并通知相关方（部分操作在应用层调用其他 SP）。
*   `sp_CreateSystemNotification (@adminId, @targetUserId, @title, @content)`: 管理员发布系统通知（定向或广播）。验证管理员权限。

**触发器:**

*   管理员模块没有直接关联的触发器。

### 7. 数据库初始化和删除脚本

*   `sql_scripts/db_init.py`: （在应用层实现）用于连接数据库并执行 `.sql` 脚本的 Python 脚本，自动化数据库的创建和填充过程。
*   `sql_scripts/tables/01_create_tables.sql`: 包含了所有表的 CREATE TABLE 语句，定义了表结构、主键、外键、唯一约束和检查约束。
*   `sql_scripts/procedures/01_user_procedures.sql` 到 `07_chat_procedures.sql`: 包含按模块划分的所有存储过程的定义。
*   `sql_scripts/triggers/01_product_triggers.sql` 到 `03_evaluation_triggers.sql`: 包含按模块划分的所有触发器的定义。
*   `sql_scripts/seed_data/seed.sql`: （待实现）用于填充初始数据的脚本，如管理员账户、商品分类等。
*   `sql_scripts/drop_all.sql`: 用于删除所有已知的数据库对象（触发器、存储过程、表），通常用于开发或测试环境重置数据库。

## 总结

通过将核心业务逻辑封装在存储过程和触发器中，数据库层承担了数据完整性检查、原子性操作和自动化响应变化的关键职责。这种设计有助于提高性能、简化应用层代码（特别是涉及复杂事务和状态同步的场景），并增强数据库的安全性。应用层主要负责用户界面、业务流程编排（调用存储过程）、缓存、消息队列以及与外部服务的集成（如邮件发送验证链接、图片存储等）。

本数据库设计着重体现了用户管理、商品生命周期（发布、审核、交易、下架）、交易流程（下单、确认、完成、退货）、评价对信用的影响以及管理员对平台内容的管理和监督。

---