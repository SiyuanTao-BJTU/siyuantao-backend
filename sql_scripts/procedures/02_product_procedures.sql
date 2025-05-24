/*
 * 商品相关存储过程
 */

-- 获取商品列表（带分页和过滤，面向UI）
DROP PROCEDURE IF EXISTS [sp_GetProductList];
GO
CREATE PROCEDURE [sp_GetProductList]
    @searchQuery NVARCHAR(200) = NULL,
    @categoryName NVARCHAR(100) = NULL,
    @minPrice DECIMAL(10, 2) = NULL,
    @maxPrice DECIMAL(10, 2) = NULL,
    @page INT = 1,
    @pageSize INT = 20,
    @sortBy NVARCHAR(50) = 'PostTime', -- 默认按发布时间排序
    @sortOrder NVARCHAR(10) = 'DESC',  -- 默认降序
    @status NVARCHAR(20) = 'Active'   -- 默认只查询Active状态的商品
AS
BEGIN
    SET NOCOUNT ON;

    -- 确保页码和页大小有效 (控制流 IF)
    IF @page < 1 SET @page = 1;
    IF @pageSize < 1 SET @pageSize = 20; -- 最小页大小
    IF @pageSize > 100 SET @pageSize = 100; -- 最大页大小限制

    DECLARE @offset INT = (@page - 1) * @pageSize;
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @paramDefinition NVARCHAR(MAX);

    -- 构建基础查询和WHERE子句
    -- SQL语句涉及2个表 (Product, User)，我们将尝试构建一个涉及3个表的JOIN语句来满足最低要求
    SET @sql = '
    SELECT
        p.ProductID AS 商品ID,
        p.ProductName AS 商品名称,
        p.Description AS 商品描述,
        p.Quantity AS 库存,
        p.Price AS 价格,
        p.PostTime AS 发布时间,
        p.Status AS 商品状态,
        u.UserName AS 发布者用户名,
        p.CategoryName AS 商品类别,
        -- 获取主图URL (假设SortOrder=0表示主图)
        pi.ImageURL AS 主图URL,
        COUNT(p.ProductID) OVER() AS 总商品数 -- 添加窗口函数计算总数 (SQL语句1，涉及Product, User, ProductImage 3个表)
    FROM [Product] p
    JOIN [User] u ON p.OwnerID = u.UserID
    LEFT JOIN [ProductImage] pi ON p.ProductID = pi.ProductID AND pi.SortOrder = 0 -- LEFT JOIN 以便没有图片的商品也能查出
    WHERE 1=1'; -- 1=1 恒真条件，方便后续追加 AND


    -- 添加过滤条件 (控制流 IF)
    IF @status IS NOT NULL AND @status <> ''
        SET @sql = @sql + ' AND p.Status = @status';

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


    -- 构建参数定义
    SET @paramDefinition = '
        @searchQuery NVARCHAR(200),
        @categoryName NVARCHAR(100),
        @minPrice DECIMAL(10, 2),
        @maxPrice DECIMAL(10, 2),
        @offset INT,
        @pageSize INT,
        @status NVARCHAR(20)';

    -- 执行动态SQL (SQL语句2)
    EXEC sp_executesql @sql,
        @paramDefinition,
        @searchQuery = @searchQuery,
        @categoryName = @categoryName,
        @minPrice = @minPrice,
        @maxPrice = @maxPrice,
        @offset = @offset,
        @pageSize = @pageSize,
        @status = @status;

END;
GO

-- 获取单个商品详情（包括图片，面向UI）
DROP PROCEDURE IF EXISTS [sp_GetProductDetail];
GO
CREATE PROCEDURE [sp_GetProductDetail]
    @productId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查商品是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    -- 获取商品基本信息 (SQL语句2，涉及 Product, User 2个表，但后续还有图片查询)
    SELECT
        p.ProductID AS 商品ID,
        p.ProductName AS 商品名称,
        p.Description AS 商品描述,
        p.Quantity AS 库存,
        p.Price AS 价格,
        p.PostTime AS 发布时间,
        p.Status AS 商品状态,
        u.UserName AS 发布者用户名,
        u.AvatarUrl AS 发布者头像URL,
        p.CategoryName AS 商品类别
    FROM [Product] p
    JOIN [User] u ON p.OwnerID = u.UserID
    WHERE p.ProductID = @productId;

    -- 获取商品图片 (SQL语句3)
    SELECT
        ImageID AS 图片ID,
        ProductID AS 商品ID,
        ImageURL AS 图片URL,
        UploadTime AS 上传时间,
        SortOrder AS 显示顺序
    FROM [ProductImage]
    WHERE ProductID = @productId
    ORDER BY SortOrder ASC, UploadTime ASC; -- 按排序顺序和上传时间排序

END;
GO

-- 创建新商品
DROP PROCEDURE IF EXISTS [sp_CreateProduct];
GO
CREATE PROCEDURE [sp_CreateProduct]
    @ownerId UNIQUEIDENTIFIER,
    @productName NVARCHAR(200),
    @description NVARCHAR(MAX) = NULL,
    @price DECIMAL(10, 2),
    @quantity INT,
    @categoryName NVARCHAR(100) = NULL,
    @imageUrls NVARCHAR(MAX) = NULL -- 逗号分隔的URL字符串
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @newProductId UNIQUEIDENTIFIER = NEWID();
    DECLARE @ownerIsVerified BIT;

    -- 检查 @ownerId 对应的用户是否存在且 IsVerified = 1 (SQL语句1)
    SELECT @ownerIsVerified = IsVerified FROM [User] WHERE UserID = @ownerId;
    IF @ownerIsVerified IS NULL
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END
    -- 控制流 IF
    IF @ownerIsVerified = 0
    BEGIN
        RAISERROR('用户未完成邮箱认证，无法发布商品。', 16, 1);
        RETURN;
    END

    -- 检查数量和价格是否有效 (控制流 IF)
    IF @quantity <= 0
    BEGIN
        RAISERROR('商品数量必须大于0。', 16, 1);
        RETURN;
    END
     IF @price < 0
    BEGIN
        RAISERROR('商品价格不能为负数。', 16, 1);
        RETURN;
    END

    -- 检查商品名称是否为空 (控制流 IF)
    IF @productName IS NULL OR LTRIM(RTRIM(@productName)) = ''
    BEGIN
        RAISERROR('商品名称不能为空。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 插入 Product 记录，初始状态 PendingReview (SQL语句2)
        INSERT INTO [Product] (ProductID, OwnerID, CategoryName, ProductName, Description, Quantity, Price, PostTime, Status)
        VALUES (@newProductId, @ownerId, @categoryName, @productName, @description, @quantity, @price, GETDATE(), 'PendingReview');

        -- 解析 @imageUrls 字符串，循环插入 [ProductImage] 表
        -- 使用 WHILE 循环进行控制流
        IF @imageUrls IS NOT NULL AND @imageUrls <> ''
        BEGIN
            DECLARE @imgUrl NVARCHAR(255);
            DECLARE @pos INT = 0;
            DECLARE @nextPos INT = 1;
            DECLARE @sortOrder INT = 0; -- 第一张图设为主图 (SortOrder = 0)

            SET @imageUrls = @imageUrls + ','; -- Add a comma at the end

            WHILE @pos < LEN(@imageUrls) -- 控制流 WHILE
            BEGIN
                SET @nextPos = CHARINDEX(',', @imageUrls, @pos + 1);
                -- 控制流 IF
                IF @nextPos > @pos
                BEGIN
                     SET @imgUrl = SUBSTRING(@imageUrls, @pos + 1, @nextPos - @pos - 1);
                     SET @imgUrl = LTRIM(RTRIM(@imgUrl)); -- 清除前后空白

                     -- 控制流 IF
                     IF @imgUrl <> ''
                     BEGIN
                         -- 插入 ProductImage 记录 (SQL语句3, 4, ...)
                         INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, UploadTime, SortOrder)
                         VALUES (NEWID(), @newProductId, @imgUrl, GETDATE(), @sortOrder);

                         -- 控制流 IF ELSE
                         IF @sortOrder = 0 SET @sortOrder = 1; -- 首张图片设为SortOrder 0，后续从1递增
                         ELSE SET @sortOrder = @sortOrder + 1;
                     END
                END
                SET @pos = @nextPos;
            END
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回新创建商品的ID (SQL语句 n, 面向UI)
        SELECT @newProductId AS 新商品ID;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
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
    @categoryName NVARCHAR(100) = NULL
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
    IF @productOwnerId != @userId
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
            CategoryName = ISNULL(@categoryName, CategoryName)
            -- Status 不通过此SP修改，审核和下架有独立的SP
        WHERE ProductID = @productId;

        -- TODO: 如果更新了Quantity为0，触发器 tr_Product_AfterUpdate_QuantityStatus 会自动更新Status为Sold

        -- 返回更新后的商品基本信息 (SQL语句3, 面向UI)
        -- 这里复用sp_GetProductDetail的一部分逻辑或调用它
        SELECT
            p.ProductID AS 商品ID,
            p.ProductName AS 商品名称,
            p.Description AS 商品描述,
            p.Quantity AS 库存,
            p.Price AS 价格,
            p.PostTime AS 发布时间,
            p.Status AS 商品状态,
            u.UserName AS 发布者用户名,
            p.CategoryName AS 商品类别
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
    @userId UNIQUEIDENTIFIER -- 卖家ID
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @productOwnerId UNIQUEIDENTIFIER;

    -- 检查商品是否存在且属于指定用户 (SQL语句1)
    SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在', 16, 1);
        RETURN;
    END

    IF @productOwnerId != @userId
    BEGIN
        RAISERROR('无权删除此商品，您不是该商品的发布者。', 16, 1);
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
        SELECT '商品删除成功' AS Result;

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
    @adminId UNIQUEIDENTIER,
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
        SET Status = @newStatus
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
        SELECT '商品审核完成。' AS Result;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_WithdrawProduct: 卖家主动下架商品
-- 输入: @productId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (卖家ID)
DROP PROCEDURE IF EXISTS [sp_WithdrawProduct];
GO
CREATE PROCEDURE [sp_WithdrawProduct]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentStatus NVARCHAR(20);

    -- 检查商品是否存在，是否属于该用户，以及当前状态是否允许下架 (SQL语句1)
    SELECT @productOwnerId = OwnerID, @currentStatus = Status
    FROM [Product]
    WHERE ProductID = @productId;

    -- 使用 IF 进行控制流
    IF @productOwnerId IS NULL
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    IF @productOwnerId != @userId
    BEGIN
        RAISERROR('无权下架此商品，您不是该商品的发布者。', 16, 1);
        RETURN;
    END

    -- 只允许下架 Active, PendingReview, Rejected 状态的商品 (控制流 IF)
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
        SELECT '商品下架成功。' AS Result;

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
        SELECT '商品收藏成功。' AS Result;

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
        SELECT '商品收藏移除成功。' AS Result;

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
        p.Description AS 商品描述,
        p.Quantity AS 库存,
        p.Price AS 价格,
        p.PostTime AS 发布时间,
        p.Status AS 商品状态,
        u_owner.UserName AS 发布者用户名,
        p.CategoryName AS 商品类别,
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