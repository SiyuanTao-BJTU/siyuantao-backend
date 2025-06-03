/*
 * 商品相关存储过程
 */

-- 获取商品详情
DROP PROCEDURE IF EXISTS [sp_GetProductById];
GO
CREATE PROCEDURE [sp_GetProductById]
    @ProductID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查商品是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @ProductID)
    BEGIN
        -- 可以选择不RAISERROR，而是返回空结果集，让服务层处理商品未找到的逻辑
        -- RAISERROR('商品不存在。', 16, 1);
        SELECT NULL AS 商品ID WHERE 1 = 0; -- 返回空结果集
        RETURN;
    END

    -- 获取商品详情 (SQL语句2)
    SELECT
        P.ProductID AS 商品ID,
        P.ProductName AS 商品名称,
        P.Description AS 描述,
        P.Quantity AS 数量,
        P.Price AS 价格,
        P.PostTime AS 发布时间,
        P.Status AS 商品状态,
        P.OwnerID AS 卖家ID,
        P.CategoryName AS 分类名称, -- 修改 CategoryID to CategoryName based on table structure
        (SELECT TOP 1 ImageURL FROM [ProductImage] WHERE ProductID = P.ProductID ORDER BY SortOrder) AS 主图URL,
        STUFF((SELECT ',' + ImageURL FROM [ProductImage] WHERE ProductID = P.ProductID ORDER BY SortOrder FOR XML PATH('')), 1, 1, '') AS 图片URL列表,
        U.UserName AS 卖家用户名,
        P.Condition AS 成色
    FROM [Product] P
    -- JOIN [Category] C ON P.CategoryID = C.CategoryID -- Removed join with Category as CategoryName is directly in Product
    JOIN [User] U ON P.OwnerID = U.UserID
    WHERE P.ProductID = @ProductID;

END;
GO

-- 获取商品列表（带分页和过滤，面向UI）
DROP PROCEDURE IF EXISTS [sp_GetProductList];
GO
CREATE PROCEDURE [sp_GetProductList]
    @searchQuery NVARCHAR(200) = NULL,
    @categoryName NVARCHAR(100) = NULL,
    @minPrice DECIMAL(10, 2) = NULL,
    @maxPrice DECIMAL(10, 2) = NULL,
    @page INT = 1,
    @pageSize INT = 10,
    @sortBy NVARCHAR(50) = 'PostTime',
    @sortOrder NVARCHAR(10) = 'DESC',
    @status NVARCHAR(20) = NULL, -- 可以是 'Active', 'PendingReview', 'Rejected', 'Sold', 'Withdrawn', 或 '_FETCH_ALL_PRODUCTS_'
    @ownerId NVARCHAR(36) = NULL -- 将 UNIQUEIDENTIFIER 改为 NVARCHAR(36)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @offset INT = (@page - 1) * @pageSize;
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @paramDefinition NVARCHAR(MAX);

    SET @sql = N'
    SELECT
        p.ProductID AS 商品ID,
        p.ProductName AS 商品名称,
        p.Description AS 描述,
        p.Quantity AS 数量,
        p.Price AS 价格,
        p.PostTime AS 发布时间,
        p.Status AS 商品状态,
        u.UserName AS 卖家用户名,
        p.CategoryName AS 分类名称,
        pi.ImageURL AS 主图URL,
        COUNT(p.ProductID) OVER() AS 总商品数
    FROM [Product] p
    JOIN [User] u ON p.OwnerID = u.UserID
    LEFT JOIN [ProductImage] pi ON p.ProductID = pi.ProductID AND pi.SortOrder = 0
    WHERE 1=1';

    -- 新增：添加过滤条件（按 ownerId 或按 status 过滤）
    IF @ownerId IS NOT NULL AND @ownerId <> ''
        SET @sql = @sql + ' AND p.OwnerID = CONVERT(UNIQUEIDENTIFIER, @ownerId)'; -- 显式转换
    ELSE IF @status IS NOT NULL AND @status <> '' AND @status <> '_FETCH_ALL_PRODUCTS_'
        -- 仅在 ownerId 为 NULL 且 status 提供且不为特殊值时应用 status 过滤
        SET @sql = @sql + ' AND p.Status = @status';
    ELSE IF @status IS NULL OR @status = '' -- 如果 status 是 NULL 或空字符串 (且没有 ownerId)
        -- 默认只查询 'Active' 状态的商品
        SET @sql = @sql + ' AND p.Status = ''Active''';
    -- 如果 @status 是 '_FETCH_ALL_PRODUCTS_'，则不添加任何额外的状态过滤，获取所有商品

    IF @searchQuery IS NOT NULL AND @searchQuery <> ''
        SET @sql = @sql + ' AND (p.ProductName LIKE ''%'' + @searchQuery + ''%'' OR p.Description LIKE ''%'' + @searchQuery + ''%'')';

    IF @categoryName IS NOT NULL AND @categoryName <> ''
        SET @sql = @sql + ' AND p.CategoryName = @categoryName';

    IF @minPrice IS NOT NULL
        SET @sql = @sql + ' AND p.Price >= @minPrice';

    IF @maxPrice IS NOT NULL
        SET @sql = @sql + ' AND p.Price <= @maxPrice';

    -- 构建排序子句 (注意：对用户输入的sortBy和sortOrder进行白名单检查以防止注入)
    DECLARE @orderBySql NVARCHAR(100);
    -- 使用 IF/CASE 进行白名单检查 (控制流 IF/CASE)
    SET @orderBySql = ' ORDER BY ';
    IF @sortBy = 'PostTime' SET @orderBySql = @orderBySql + 'p.PostTime';
    ELSE IF @sortBy = 'Price' SET @orderBySql = @orderBySql + 'p.Price';
    ELSE IF @sortBy = 'ProductName' SET @orderBySql = @orderBySql + 'p.ProductName';
    ELSE SET @orderBySql = @orderBySql + 'p.PostTime'; -- 默认排序

    IF @sortOrder = 'ASC' SET @orderBySql = @orderBySql + ' ASC';
    ELSE SET @orderBySql = @orderBySql + ' DESC'; -- 默认降序

    SET @sql = @sql + @orderBySql;

    -- 添加分页子句
    SET @sql = @sql + ' OFFSET @offset ROWS FETCH NEXT @pageSize ROWS ONLY;';

        -- 构建参数定义 (新增 @ownerId)
    SET @paramDefinition = N'
        @searchQuery NVARCHAR(200),
        @categoryName NVARCHAR(100),
        @minPrice DECIMAL(10, 2),
        @maxPrice DECIMAL(10, 2),
        @page INT,          
        @pageSize INT,       
        @sortBy NVARCHAR(50), 
        @sortOrder NVARCHAR(10),
        @status NVARCHAR(20),
        @ownerId NVARCHAR(36), -- 将 UNIQUEIDENTIFIER 改为 NVARCHAR(36)
        @offset INT'; 

    -- 执行动态SQL (新增 @ownerId 参数的传递)
    EXEC sp_executesql @sql,
        @paramDefinition,
        @searchQuery = @searchQuery,
        @categoryName = @categoryName,
        @minPrice = @minPrice,
        @maxPrice = @maxPrice,
        @page = @page,
        @pageSize = @pageSize,
        @sortBy = @sortBy,        
        @sortOrder = @sortOrder,   
        @status = @status,
        @ownerId = @ownerId,
        @offset = @offset;

END;
GO


-- 更新商品信息
DROP PROCEDURE IF EXISTS [sp_UpdateProduct];
GO
CREATE PROCEDURE [sp_UpdateProduct]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER, -- 用于权限检查
    @productName NVARCHAR(200) = NULL,
    @description NVARCHAR(MAX) = NULL,
    @quantity INT = NULL,
    @price DECIMAL(10, 2) = NULL,
    @categoryName NVARCHAR(100) = NULL,
    @condition NVARCHAR(50) = NULL, -- 添加 condition 参数
    @invokedByAdmin BIT = 0 -- 新增参数，标记是否由管理员调用
    -- 图片的增删改查通过独立的图片存储过程处理
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentStatus NVARCHAR(20);

    -- 检查商品是否存在并获取当前所有者和状态 (SQL语句1)
    SELECT @productOwnerId = OwnerID, @currentStatus = Status
    FROM [Product]
    WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    -- 检查操作用户是否是商品所有者 (控制流 IF)
    IF @invokedByAdmin = 0 AND @productOwnerId != @userId -- 新的检查，如果不是管理员调用，则检查所有权
    BEGIN
        RAISERROR('无权修改此商品。', 16, 1);
        RETURN;
    END

    -- 检查商品状态是否允许修改 (控制流 IF)
    -- 例如，Active, PendingReview, Rejected, Withdrawn 状态下可以修改，Sold 状态下不能
    IF @currentStatus = 'Sold'
    BEGIN
        RAISERROR('商品已售罄，不允许修改。', 16, 1);
        RETURN;
    END

    -- 检查数量和价格是否有效 (如果传入了新值) (控制流 IF)
    IF @quantity IS NOT NULL AND @quantity < 0 -- 允许数量为0，但不允许负数
    BEGIN
        RAISERROR('商品数量不能为负数。', 16, 1);
        RETURN;
    END
     IF @price IS NOT NULL AND @price < 0
    BEGIN
        RAISERROR('商品价格不能为负数。', 16, 1);
        RETURN;
    END


    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 更新商品信息 (SQL语句2)
        UPDATE [Product]
        SET
            ProductName = ISNULL(@productName, ProductName),
            Description = ISNULL(@description, Description),
            Quantity = ISNULL(@quantity, Quantity),
            Price = ISNULL(@price, Price),
            CategoryName = ISNULL(@categoryName, CategoryName),
            Condition = ISNULL(@condition, Condition) -- 更新 Condition
            -- Status 不通过此SP修改，审核和下架有独立的SP
        WHERE ProductID = @productId;

        -- TODO: 如果更新了Quantity为0，触发器 tr_Product_AfterUpdate_QuantityStatus 会自动更新Status为Sold

        -- 返回更新后的商品基本信息 (SQL语句3, 面向UI)
        -- 这里复用sp_GetProductDetail的一部分逻辑或调用它
        SELECT
            p.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            p.Description AS 描述,
            p.Quantity AS 数量,
            p.Price AS 价格,
            p.PostTime AS 发布时间,
            p.Status AS 商品状态,
            u.UserName AS 卖家用户名,
            p.CategoryName AS 分类名称
        FROM [Product] p
        JOIN [User] u ON p.OwnerID = u.UserID
        WHERE p.ProductID = @productId;


        COMMIT TRANSACTION; -- 提交事务

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- 删除商品 (卖家)
DROP PROCEDURE IF EXISTS [sp_DeleteProduct];
GO
CREATE PROCEDURE [sp_DeleteProduct]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER, -- 卖家ID 或 管理员ID
    @invokedByAdmin BIT = 0 -- 新增参数，标记是否由管理员调用
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @productOwnerId UNIQUEIDENTIFIER;

    -- 检查商品是否存在 (SQL语句1)
    SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @productId;

    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    IF @invokedByAdmin = 0 AND @productOwnerId != @userId
    BEGIN
        RAISERROR('无权删除此商品，您不是该商品的发布者。', 16, 1);
        RETURN;
    END

    -- 检查商品是否存在于任何订单中
    IF EXISTS (SELECT 1 FROM [Order] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('无法删除商品，因为它已关联到一个或多个订单。请先处理相关订单。', 16, 1);
        RETURN;
    END

    -- 检查商品是否存在于任何用户的收藏夹中
    IF EXISTS (SELECT 1 FROM [UserFavorite] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('无法删除商品，因为它已被一个或多个用户收藏。请先通知用户或进行其他处理。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 删除商品 (SQL语句2)
        -- 由于 ProductImage 对 Product 有 ON DELETE CASCADE 外键约束，删除 Product 会自动删除关联的 ProductImage
        DELETE FROM [Product] WHERE ProductID = @productId;

        -- 检查删除是否成功 (控制流 IF)
        IF @@ROWCOUNT = 0
        BEGIN
             -- 这应该不会发生，因为上面已经检查了商品存在和所有权
             RAISERROR('商品删除失败。', 16, 1);
             IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
             RETURN;
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回删除结果 (SQL语句3, 面向UI)
        SELECT '商品删除成功' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_ReviewProduct: 管理员审核商品
-- 输入: @productId UNIQUEIDENTIFIER, @adminId UNIQUEIDENTIFIER, @newStatus NVARCHAR(20) ('Active'或'Rejected'), @reason NVARCHAR(500) (如果拒绝)
DROP PROCEDURE IF EXISTS [sp_ReviewProduct];
GO
CREATE PROCEDURE [sp_ReviewProduct]
    @productId UNIQUEIDENTIFIER,
    @adminId UNIQUEIDENTIFIER,
    @newStatus NVARCHAR(20), -- 'Active' 或 'Rejected'
    @reason NVARCHAR(500) = NULL -- 如果拒绝，提供原因
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentStatus NVARCHAR(20);
    DECLARE @adminIsStaff BIT;
    DECLARE @productName NVARCHAR(200);


    -- 检查 @adminId 对应的用户是否为管理员 (SQL语句1)
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以审核商品。', 16, 1);
        RETURN;
    END

    -- 检查 @newStatus 是否有效 (控制流 IF)
    IF @newStatus NOT IN ('Active', 'Rejected')
    BEGIN
        RAISERROR('无效的审核状态，状态必须是 Active 或 Rejected。', 16, 1);
        RETURN;
    END

    -- 检查 @productId 对应的商品是否存在且状态为 'PendingReview' (SQL语句2)
    SELECT @productOwnerId = OwnerID, @currentStatus = Status, @productName = ProductName
    FROM [Product]
    WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    IF @currentStatus != 'PendingReview'
    BEGIN
        RAISERROR('商品当前状态 (%s) 不允许审核。', 16, 1, @currentStatus);
        RETURN;
    END

    -- 如果状态是 Rejected 但未提供原因 (控制流 IF)
    IF @newStatus = 'Rejected' AND (@reason IS NULL OR LTRIM(RTRIM(@reason)) = '')
    BEGIN
         RAISERROR('拒绝商品必须提供原因。', 16, 1);
         RETURN;
    END


    BEGIN TRY
        BEGIN TRANSACTION;

        -- 更新 [Product] 表的状态 (SQL语句3)
        UPDATE [Product]
        SET Status = @newStatus,
            AuditReason = CASE WHEN @newStatus = 'Rejected' THEN @reason ELSE AuditReason END -- 只有拒绝时才更新 AuditReason
        WHERE ProductID = @productId;

        -- 插入系统通知 (SQL语句4)
        DECLARE @notificationTitle NVARCHAR(200);
        DECLARE @notificationContent NVARCHAR(MAX);

        -- 使用 IF ELSE 进行控制流
        IF @newStatus = 'Active'
        BEGIN
            SET @notificationTitle = '商品审核通过';
            SET @notificationContent = '您的商品 "' + @productName + '" 已审核通过，当前状态为 Active (在售)。';
        END
        ELSE -- @newStatus = 'Rejected'
        BEGIN
            SET @notificationTitle = '商品审核未通过';
            SET @notificationContent = '您的商品 "' + @productName + '" 未通过审核，状态为 Rejected (已拒绝)。原因: ' + ISNULL(@reason, '未说明');
        END

        -- 通知商品发布者 (SQL语句4 - 调整语句序号)
        INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
        VALUES (NEWID(), @productOwnerId, @notificationTitle, @notificationContent, GETDATE(), 0);

        COMMIT TRANSACTION;

        -- 返回审核成功的消息 (SQL语句5 - 调整语句序号)
        SELECT '商品审核完成。' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_WithdrawProduct: 卖家主动下架商品
-- 输入: @productId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (卖家ID 或 管理员ID)
DROP PROCEDURE IF EXISTS [sp_WithdrawProduct];
GO
CREATE PROCEDURE [sp_WithdrawProduct]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER,
    @invokedByAdmin BIT = 0 -- 新增参数
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentStatus NVARCHAR(20);

    -- 检查商品是否存在 (SQL语句1)
    SELECT @productOwnerId = OwnerID, @currentStatus = Status
    FROM [Product]
    WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    -- 如果不是管理员调用，则检查所有权
    IF @invokedByAdmin = 0 AND @productOwnerId != @userId
    BEGIN
        RAISERROR('无权下架此商品，您不是该商品的发布者。', 16, 1);
        RETURN;
    END

    -- 只允许下架 Active, PendingReview, Rejected 状态的商品 (控制流 IF)
    -- 管理员下架时也应遵循此逻辑，或者如果管理员有特殊权限可以下架任何状态的商品，则此处逻辑需要调整
    IF @currentStatus NOT IN ('Active', 'PendingReview', 'Rejected')
    BEGIN
        RAISERROR('商品当前状态 (%s) 不允许下架。', 16, 1, @currentStatus);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 更新商品状态为 Withdrawn (SQL语句2)
        UPDATE [Product]
        SET Status = 'Withdrawn'
        WHERE ProductID = @productId;

        COMMIT TRANSACTION;

        -- 返回成功消息 (SQL语句3)
        SELECT '商品下架成功。' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_AddFavoriteProduct: 添加商品到收藏
-- 输入: @userId UNIQUEIDENTIFIER, @productId UNIQUEIDENTIFIER
DROP PROCEDURE IF EXISTS [sp_AddFavoriteProduct];
GO
CREATE PROCEDURE [sp_AddFavoriteProduct]
    @userId UNIQUEIDENTIFIER,
    @productId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @userExists INT;
    DECLARE @productExists INT;
    DECLARE @alreadyFavorited INT;

    -- 检查 @userId 和 @productId 是否存在 (SQL语句1, 2)
    SELECT @userExists = COUNT(1) FROM [User] WHERE UserID = @userId;
    SELECT @productExists = COUNT(1) FROM [Product] WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @userExists = 0
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END
    IF @productExists = 0
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    -- 检查 UserFavorite 表中是否已存在该收藏记录 (SQL语句3)
    SELECT @alreadyFavorited = COUNT(1) FROM [UserFavorite] WHERE UserID = @userId AND ProductID = @productId;
    -- 控制流 IF
    IF @alreadyFavorited > 0
    BEGIN
        RAISERROR('该商品已被您收藏。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- INSERT INTO [UserFavorite] (...) VALUES (...); (SQL语句4)
        INSERT INTO [UserFavorite] (FavoriteID, UserID, ProductID, FavoriteTime)
        VALUES (NEWID(), @userId, @productId, GETDATE());

        COMMIT TRANSACTION; -- 提交事务

        -- 返回收藏成功的消息 (SQL语句5)
        SELECT '商品收藏成功。' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        -- 检查是否是唯一约束冲突错误 (错误号2627) - UNIQUE约束更优先于手动检查
        IF ERROR_NUMBER() = 2627
        BEGIN
             RAISERROR('该商品已被您收藏（通过唯一约束检查）。', 16, 1);
        END
        ELSE
        BEGIN
            THROW; -- 重新抛出其他错误
        END
    END CATCH
END;
GO

-- sp_RemoveFavoriteProduct: 移除商品收藏
-- 输入: @userId UNIQUEIDENTIFIER, @productId UNIQUEIDENTIFIER
DROP PROCEDURE IF EXISTS [sp_RemoveFavoriteProduct];
GO
CREATE PROCEDURE [sp_RemoveFavoriteProduct]
    @userId UNIQUEIDENTIFIER,
    @productId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @userExists INT;
    DECLARE @productExists INT;

    -- 检查 @userId 和 @productId 是否存在 (SQL语句1, 2)
    SELECT @userExists = COUNT(1) FROM [User] WHERE UserID = @userId;
    SELECT @productExists = COUNT(1) FROM [Product] WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @userExists = 0
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END
    IF @productExists = 0
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 删除收藏记录 (SQL语句3)
        DELETE FROM [UserFavorite]
        WHERE UserID = @userId AND ProductID = @productId;

        -- 检查是否删除了记录 (控制流 IF)
        IF @@ROWCOUNT = 0
        BEGIN
            -- 如果没有删除任何行，可能是用户没有收藏过该商品
            RAISERROR('该商品不在您的收藏列表中。', 16, 1);
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            RETURN;
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句4)
        SELECT '商品收藏移除成功。' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetUserFavoriteProducts: 获取用户收藏的商品列表 (面向UI)
-- 输入: @userId UNIQUEIDENTIFIER
-- 输出: 收藏商品列表
DROP PROCEDURE IF EXISTS [sp_GetUserFavoriteProducts];
GO
CREATE PROCEDURE [sp_GetUserFavoriteProducts]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查用户是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- 获取用户收藏的商品列表 (SQL语句2, 涉及 UserFavorite, Product 2个表，可以通过JOIN User表达到3个表)
    SELECT
        p.ProductID AS 商品ID,
        p.ProductName AS 商品名称,
        p.Description AS 描述,
        p.Quantity AS 数量,
        p.Price AS 价格,
        p.PostTime AS 发布时间,
        p.Status AS 商品状态,
        u_owner.UserName AS 卖家用户名,
        p.CategoryName AS 分类名称,
        uf.FavoriteTime AS 收藏时间,
        -- 获取主图URL (SQL语句3, 涉及 ProductImage)
        (SELECT TOP 1 ImageURL FROM [ProductImage] pi WHERE pi.ProductID = p.ProductID AND pi.SortOrder = 0 ORDER BY UploadTime ASC) AS 主图URL
    FROM [UserFavorite] uf
    JOIN [Product] p ON uf.ProductID = p.ProductID -- JOIN Product
    JOIN [User] u_owner ON p.OwnerID = u_owner.UserID -- JOIN User (达到3个表要求)
    WHERE uf.UserID = @userId
    ORDER BY uf.FavoriteTime DESC;

END;
GO

-- sp_DecreaseProductQuantity: 减少商品库存
-- 新增存储过程
DROP PROCEDURE IF EXISTS [sp_DecreaseProductQuantity];
GO
CREATE PROCEDURE [sp_DecreaseProductQuantity]
    @productId UNIQUEIDENTIFIER,
    @quantityToDecrease INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @currentQuantity INT;

    -- 检查商品是否存在并获取当前库存
    SELECT @currentQuantity = Quantity FROM [Product] WHERE ProductID = @productId;

    IF @currentQuantity IS NULL
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    -- 检查库存是否足够
    IF @currentQuantity < @quantityToDecrease
    BEGIN
        RAISERROR('库存不足，无法减少指定数量', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 减少库存
        UPDATE [Product]
        SET Quantity = Quantity - @quantityToDecrease
        WHERE ProductID = @productId;

        -- TODO: 触发器 tr_Product_AfterUpdate_QuantityStatus 会处理 Quantity=0 时状态变为Sold

        COMMIT TRANSACTION;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_IncreaseProductQuantity: 增加商品库存
-- 新增存储过程
DROP PROCEDURE IF EXISTS [sp_IncreaseProductQuantity];
GO
CREATE PROCEDURE [sp_IncreaseProductQuantity]
    @productId UNIQUEIDENTIFIER,
    @quantityToIncrease INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @currentQuantity INT;

    -- 检查商品是否存在并获取当前库存
    SELECT @currentQuantity = Quantity FROM [Product] WHERE ProductID = @productId;

    IF @currentQuantity IS NULL
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    -- 检查增加数量是否有效 (不允许增加负数)
    IF @quantityToIncrease < 0
    BEGIN
         RAISERROR('增加数量不能为负数。', 16, 1);
         RETURN;
    END
    -- 检查增加后是否超出库存上限 (如果需要限制，例如 INT 最大值)
    -- SELECT @currentQuantity + @quantityToIncrease ... 可以检查溢出

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 增加库存
        UPDATE [Product]
        SET Quantity = Quantity + @quantityToIncrease
        WHERE ProductID = @productId;

         -- TODO: 触发器 tr_Product_AfterUpdate_QuantityStatus 会处理 Quantity > 0 时状态变为Active (如果原状态是Sold)

        COMMIT TRANSACTION;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- 删除指定商品的所有图片
DROP PROCEDURE IF EXISTS [sp_DeleteProductImagesByProductId];
GO
CREATE PROCEDURE [sp_DeleteProductImagesByProductId]
    @productId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM [ProductImage]
    WHERE ProductID = @productId;
    SELECT @@ROWCOUNT AS 已删除图片数量; -- 可以选择返回删除了多少张图片
END;
GO

DROP PROCEDURE IF EXISTS [sp_CreateProduct];
GO
CREATE PROCEDURE [sp_CreateProduct]
    @ownerId UNIQUEIDENTIFIER,
    @productName NVARCHAR(200),
    @description NVARCHAR(MAX),
    @quantity INT,
    @price FLOAT,
    @categoryName NVARCHAR(100),
    @condition NVARCHAR(50), -- 新增成色参数
    @imageUrls NVARCHAR(MAX) = NULL -- 逗号分隔的图片URL字符串
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @productId UNIQUEIDENTIFIER = NEWID();

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 插入商品信息
        INSERT INTO [Product] (ProductID, OwnerID, ProductName, Description, Quantity, Price, PostTime, Status, CategoryName, Condition, AuditReason) -- 添加 Condition 列, AuditReason
        VALUES (@productId, @ownerId, @productName, @description, @quantity, @price, GETDATE(), 'PendingReview', @categoryName, @condition, NULL); -- 默认状态为 PendingReview, AuditReason is NULL

        -- 处理图片URL
        IF @imageUrls IS NOT NULL AND LTRIM(RTRIM(@imageUrls)) <> ''
        BEGIN
            DECLARE @imageUrl NVARCHAR(MAX);
            DECLARE @pos INT;
            DECLARE @currentSortOrder INT = 0;

            SET @imageUrls = LTRIM(RTRIM(@imageUrls)) + ','; -- Ensure it ends with a comma
            SET @pos = CHARINDEX(',', @imageUrls, 1);

            WHILE @pos > 0
            BEGIN
                SET @imageUrl = LTRIM(RTRIM(SUBSTRING(@imageUrls, 1, @pos - 1)));

                IF @imageUrl <> ''
                BEGIN
                    INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, UploadTime, SortOrder)
                    VALUES (NEWID(), @productId, @imageUrl, GETDATE(), @currentSortOrder);
                    SET @currentSortOrder = @currentSortOrder + 1;
                END

                SET @imageUrls = SUBSTRING(@imageUrls, @pos + 1, LEN(@imageUrls));
                SET @pos = CHARINDEX(',', @imageUrls, 1);
            END
        END

        COMMIT TRANSACTION;

        SELECT @productId AS 新商品ID; -- 返回新生成的商品ID

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_ActivateProduct: 激活商品（管理员审核通过或卖家重新上架）
DROP PROCEDURE IF EXISTS [sp_ActivateProduct];
GO
CREATE PROCEDURE [sp_ActivateProduct]
    @ProductID UNIQUEIDENTIFIER,
    @OperatorID UNIQUEIDENTIFIER, -- 操作者ID (可以是管理员或商品所有者)
    @IsAdminRequest BIT = 0        -- 标记是否由管理员发起此操作
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ErrorMessage NVARCHAR(4000);
    DECLARE @ProductOwnerID UNIQUEIDENTIFIER;
    DECLARE @CurrentStatus NVARCHAR(50);

    -- 检查商品是否存在并获取当前所有者和状态
    SELECT @ProductOwnerID = OwnerID, @CurrentStatus = Status
    FROM [Product]
    WHERE ProductID = @ProductID;

    IF @ProductOwnerID IS NULL
    BEGIN
        SET @ErrorMessage = '商品不存在。';
        THROW 50000, @ErrorMessage, 1;
    END

    -- 管理员操作逻辑
    IF @IsAdminRequest = 1
    BEGIN
        -- 验证操作者是否为管理员
        IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @OperatorID AND (IsStaff = 1 OR IsSuperAdmin = 1))
        BEGIN
            SET @ErrorMessage = '只有管理员才能执行此激活操作。';
            THROW 50001, @ErrorMessage, 1;
        END

        -- 只有处于 'PendingReview' 或 'Withdrawn' 状态的商品才能被管理员激活
        IF @CurrentStatus NOT IN ('PendingReview', 'Withdrawn')
        BEGIN
            SET @ErrorMessage = '管理员无法激活当前状态为 "' + @CurrentStatus + '" 的商品。';
            THROW 50002, @ErrorMessage, 1;
        END
    END
    -- 卖家操作逻辑 (重新上架)
    ELSE
    BEGIN
        -- 验证操作者是否为商品所有者
        IF @ProductOwnerID != @OperatorID
        BEGIN
            SET @ErrorMessage = '您无权上架此商品。';
            THROW 50003, @ErrorMessage, 1;
        END

        -- 只有处于 'Withdrawn' 状态的商品才能被卖家重新上架
        IF @CurrentStatus != 'Withdrawn'
        BEGIN
            SET @ErrorMessage = '只有已下架的商品才能由卖家重新上架。当前商品状态为 "' + @CurrentStatus + '"。';
            THROW 50004, @ErrorMessage, 1;
        END
    END

    -- 执行状态更新
    UPDATE [Product]
    SET Status = 'Active'
    WHERE ProductID = @ProductID;

    IF @@ROWCOUNT = 0
    BEGIN
        SET @ErrorMessage = '更新商品状态失败，商品可能不存在或不符合激活条件。';
        THROW 50005, @ErrorMessage, 1;
    END

    SELECT '商品激活成功' AS 消息; -- 返回成功消息
END;
GO

DROP PROCEDURE IF EXISTS [sp_RejectProduct];
GO
CREATE PROCEDURE [sp_RejectProduct]
    @productId UNIQUEIDENTIFIER,
    @adminId UNIQUEIDENTIFIER,
    @reason NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END;

    IF (SELECT Status FROM [Product] WHERE ProductID = @productId) = 'Rejected'
    BEGIN
        RAISERROR('商品已是拒绝状态，无需重复操作。', 16, 1);
        RETURN;
    END;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [Product]
        SET
            Status = 'Rejected',
            AuditReason = @reason
        WHERE ProductID = @productId;

        -- 记录审核操作
        -- INSERT INTO [AuditLog] (Action, EntityType, EntityId, ActorId, Timestamp, Details)
        -- VALUES ('ProductRejected', 'Product', @productId, @adminId, GETDATE(), N'商品审核被拒绝。原因：' + ISNULL(@reason, '无'));

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(MAX) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        DECLARE @ErrorState INT = ERROR_STATE();
        RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END;
GO

DROP PROCEDURE IF EXISTS [sp_BatchActivateProducts];
GO
CREATE PROCEDURE [sp_BatchActivateProducts]
    @productIds NVARCHAR(MAX), -- 逗号分隔的ProductID字符串
    @adminId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 使用 STRING_SPLIT 来解析逗号分隔的ProductID字符串
        UPDATE P
        SET P.Status = 'Active',
            P.AuditReason = NULL -- 激活时清除拒绝原因
        FROM [Product] P
        JOIN STRING_SPLIT(@productIds, ',') AS IDList ON P.ProductID = TRY_CAST(IDList.value AS UNIQUEIDENTIFIER)
        WHERE P.Status = 'PendingReview'; -- 只激活待审核的商品

        -- 记录批量审核操作
        -- INSERT INTO [AuditLog] (Action, EntityType, EntityId, ActorId, Timestamp, Details)
        -- VALUES ('BatchProductActivated', 'Product', NULL, @adminId, GETDATE(), N'批量商品审核通过并上架。产品ID：' + @productIds);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(MAX) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        DECLARE @ErrorState INT = ERROR_STATE();
        RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END;
GO

DROP PROCEDURE IF EXISTS [sp_BatchRejectProducts];
GO
CREATE PROCEDURE [sp_BatchRejectProducts]
    @productIds NVARCHAR(MAX), -- 逗号分隔的ProductID字符串
    @adminId UNIQUEIDENTIFIER,
    @reason NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE P
        SET
            P.Status = 'Rejected',
            P.AuditReason = @reason
        FROM [Product] P
        JOIN STRING_SPLIT(@productIds, ',') AS IDList ON P.ProductID = TRY_CAST(IDList.value AS UNIQUEIDENTIFIER)
        WHERE P.Status = 'PendingReview'; -- 只拒绝待审核的商品

        -- 记录批量审核操作
        -- INSERT INTO [AuditLog] (Action, EntityType, EntityId, ActorId, Timestamp, Details)
        -- VALUES ('BatchProductRejected', 'Product', NULL, @adminId, GETDATE(), N'批量商品审核被拒绝。产品ID：' + @productIds + N'. 原因：' + ISNULL(@reason, '无'));

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        DECLARE @ErrorMessage NVARCHAR(MAX) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        DECLARE @ErrorState INT = ERROR_STATE();
        RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
    END CATCH
END;
GO

-- sp_UpdateProductStatus: 更新商品状态
DROP PROCEDURE IF EXISTS [sp_UpdateProductStatus];
GO
CREATE PROCEDURE [sp_UpdateProductStatus]
    @ProductID UNIQUEIDENTIFIER,
    @NewStatus NVARCHAR(50),
    @AuditReason NVARCHAR(500) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ErrorMessage NVARCHAR(4000);

    -- 验证新状态是否有效
    IF @NewStatus NOT IN ('PendingReview', 'Active', 'Rejected', 'Sold', 'Withdrawn')
    BEGIN
        SET @ErrorMessage = '无效的商品状态: ' + @NewStatus;
        THROW 50000, @ErrorMessage, 1;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [Product]
        SET Status = @NewStatus,
            AuditReason = CASE WHEN @NewStatus = 'Rejected' THEN @AuditReason ELSE NULL END -- 只有拒绝时才设置原因，其他情况清除
        WHERE ProductID = @ProductID;

        IF @@ROWCOUNT = 0
        BEGIN
            SET @ErrorMessage = '更新商品状态失败，商品可能不存在。';
            THROW 50001, @ErrorMessage, 1;
        END

        COMMIT TRANSACTION;
        SELECT '商品状态更新成功' AS 消息;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO