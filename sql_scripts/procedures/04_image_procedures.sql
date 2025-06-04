/*
 * 商品图片管理模块 - 存储过程
 * 功能: 图片上传、查询、更新、删除
 * 注意: 文件实际上传/删除在应用层处理，这里只记录URL
 */

-- sp_GetImageById: 根据ID获取图片
-- 输入: @imageId UNIQUEIDENTIFIER
-- 输出: 图片信息
DROP PROCEDURE IF EXISTS [sp_GetImageById];
GO
CREATE PROCEDURE [sp_GetImageById]
    @imageId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- ProductImage 表结构: ImageID, ProductID, ImageURL, UploadTime, SortOrder
    -- 检查图片是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [ProductImage] WHERE ImageID = @imageId)
    BEGIN
        RAISERROR('图片不存在。', 16, 1);
        RETURN;
    END

    -- SQL语句涉及1个表，但包含控制流(IF)和多个SELECT列
    SELECT
        ImageID AS 图片ID,
        ProductID AS 商品ID,
        ImageURL AS 图片URL,
        UploadTime AS 上传时间,
        SortOrder AS 显示顺序
    FROM [ProductImage]
    WHERE ImageID = @imageId;
END;
GO

-- sp_GetImagesByProduct: 获取某个商品的所有图片 (面向UI)
-- 输入: @productId UNIQUEIDENTIFIER
-- 输出: 图片列表
DROP PROCEDURE IF EXISTS [sp_GetImagesByProduct];
GO
CREATE PROCEDURE [sp_GetImagesByProduct]
    @productId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查商品是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END

    -- 获取图片列表 (SQL语句2)
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

-- sp_CreateImage: 为商品创建新图片记录 (通常由 sp_CreateProduct 或独立的图片上传服务调用)
-- 输入: @productId UNIQUEIDENTIFIER, @imageUrl NVARCHAR(255), @sortOrder INT
-- 输出: 新图片记录的ID
-- 注意: 文件实际上传在应用层处理，这里只记录URL
DROP PROCEDURE IF EXISTS [sp_CreateImage];
GO
CREATE PROCEDURE [sp_CreateImage]
    @productId UNIQUEIDENTIFIER,
    @imageUrl NVARCHAR(255),
    @sortOrder INT = 0 -- 默认 SortOrder = 0 表示主图
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @newImageId UNIQUEIDENTIFIER = NEWID();
    DECLARE @productExists INT;

    -- 检查商品是否存在 (SQL语句1)
    SELECT @productExists = COUNT(1) FROM [Product] WHERE ProductID = @productId;
    IF @productExists = 0
    BEGIN
        RAISERROR('关联的商品不存在。', 16, 1);
        RETURN;
    END

     -- 检查图片URL是否为空 (控制流 IF)
     IF @imageUrl IS NULL OR LTRIM(RTRIM(@imageUrl)) = ''
     BEGIN
          RAISERROR('图片URL不能为空。', 16, 1);
          RETURN;
     END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 插入 ProductImage 记录 (SQL语句2)
        INSERT INTO [ProductImage] (ImageID, ProductID, ImageURL, UploadTime, SortOrder)
        VALUES (@newImageId, @productId, @imageUrl, GETDATE(), @sortOrder);

        COMMIT TRANSACTION; -- 提交事务

        -- 返回新创建图片的ID (SQL语句3, 面向UI)
        SELECT @newImageId AS 新图片ID;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_UpdateImageSortOrder: 更新图片显示顺序 (SortOrder)
-- 输入: @imageId UNIQUEIDENTIFIER, @newSortOrder INT, @userId UNIQUEIDENTIFIER (操作者ID，用于权限检查)
-- 逻辑: 检查图片是否存在，检查操作者是否有权限 (例如是否是商品所有者)，更新 SortOrder。
-- 注意: 如果将某张图片设为 SortOrder = 0，可能需要将该商品原 SortOrder = 0 的图片调整 SortOrder。
DROP PROCEDURE IF EXISTS [sp_UpdateImageSortOrder];
GO
CREATE PROCEDURE [sp_UpdateImageSortOrder]
    @imageId UNIQUEIDENTIFIER,
    @newSortOrder INT,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 可选，遇到错误自动回滚

    DECLARE @productId UNIQUEIDENTIFIER;
    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentSortOrder INT;

    -- 检查图片是否存在并获取关联的商品ID和当前SortOrder (SQL语句1)
    SELECT @productId = ProductID, @currentSortOrder = SortOrder
    FROM [ProductImage]
    WHERE ImageID = @imageId;

    -- 使用 IF 进行控制流
    IF @productId IS NULL
    BEGIN
        RAISERROR('图片不存在。', 16, 1);
        RETURN;
    END

    -- 检查关联的商品是否存在并获取所有者 (SQL语句2)
    SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @productId;
     -- TODO: 检查操作者是否有权限 (例如是否是商品所有者) - 这部分逻辑已在此处实现，但需要确保调用者传入 @userId 并在此处检查
     -- 当前存储过程已接收 @userId 参数，但未使用其进行权限检查
     -- 应该加入 IF @productOwnerId != @userId 的检查
     IF @productOwnerId IS NULL OR @productOwnerId != @userId
     BEGIN
          RAISERROR('无权修改此图片。', 16, 1);
          IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION; -- 添加回滚
          RETURN;
     END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- TODO: 如果将某张图片设为 SortOrder = 0，需要确保该商品下只有一张 SortOrder 为 0 的图片。
        -- 现有逻辑是直接更新 SortOrder，不会处理多个主图的情况。
        -- 简单的处理方式可以是：如果新 SortOrder 是 0，先将该商品下所有 SortOrder=0 的图片设为 1，再更新当前图片的 SortOrder 为 0。

        -- 如果新的 SortOrder 是 0，先将该商品下所有 SortOrder 为 0 的图片更新为非 0 (例如 1)
        IF @newSortOrder = 0
        BEGIN
            UPDATE [ProductImage]
            SET SortOrder = 1
            WHERE ProductID = @productId AND SortOrder = 0 AND ImageID != @imageId; -- 排除当前图片
        END

        -- 更新 ProductImage 表 (SQL语句3)
        UPDATE [ProductImage]
        SET SortOrder = @newSortOrder
        WHERE ImageID = @imageId;

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句4, 面向UI)
        SELECT '图片显示顺序更新成功。' AS 结果;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_DeleteImage: 删除图片记录
-- 输入: @imageId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (操作者ID，用于权限检查)
-- 逻辑: 检查图片是否存在，检查操作者是否有权限，删除图片记录。
-- 注意: 实际文件删除在应用层处理。
DROP PROCEDURE IF EXISTS [sp_DeleteImage];
GO
CREATE PROCEDURE [sp_DeleteImage]
    @imageId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @productId UNIQUEIDENTIFIER;
    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    DECLARE @currentSortOrder INT; -- 检查是否删除了主图
    -- DECLARE @imageUrl NVARCHAR(255); -- 文件URL，用于应用层删除文件
    DECLARE @productExists INT; -- 用于检查商品是否存在，确保关联有效

    -- 检查图片是否存在并获取关联的商品ID和 SortOrder (SQL语句1)
    SELECT @productId = ProductID, @currentSortOrder = SortOrder
    FROM [ProductImage]
    WHERE ImageID = @imageId;

    -- 使用 IF 进行控制流
    IF @productId IS NULL
    BEGIN
        RAISERROR('图片不存在。', 16, 1);
        RETURN;
    END

    -- 检查关联的商品是否存在并获取所有者 (SQL语句2)
    SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @productId;
     -- 检查操作者是否有权限 (例如是否是商品所有者) (控制流 IF)
     IF @productOwnerId IS NULL OR @productOwnerId != @userId
     BEGIN
          RAISERROR('无权删除此图片。', 16, 1);
          RETURN;
     END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 删除图片记录 (SQL语句3)
        DELETE FROM [ProductImage]
        WHERE ImageID = @imageId;

        -- 检查是否删除了记录 (控制流 IF)
         IF @@ROWCOUNT = 0
         BEGIN
             -- 这应该不会发生，因为上面已经检查了图片存在
             RAISERROR('删除图片记录失败。', 16, 1);
             IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
             RETURN;
         END

        -- 如果删除的是主图 (SortOrder = 0)，尝试指定一个新的主图
        IF @currentSortOrder = 0
        BEGIN
            DECLARE @nextMainImageId UNIQUEIDENTIFIER;

            -- 查找该商品下 SortOrder 最小的图片（如果存在），将其设为新的主图
            SELECT TOP 1 @nextMainImageId = ImageID
            FROM [ProductImage]
            WHERE ProductID = @productId
            ORDER BY SortOrder ASC, UploadTime ASC; -- 按 SortOrder 和 UploadTime 确定下一张主图

            -- 如果找到了新的主图，更新其 SortOrder 为 0
            IF @nextMainImageId IS NOT NULL
            BEGIN
                UPDATE [ProductImage]
                SET SortOrder = 0
                WHERE ImageID = @nextMainImageId;
            END
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句4, 面向UI)
        SELECT '图片删除成功。' AS 结果; -- 返回删除的图片ID或URL可在应用层处理

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO 