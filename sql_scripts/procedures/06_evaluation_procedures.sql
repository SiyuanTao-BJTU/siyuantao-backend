/*
 * 交易管理模块 - 评价存储过程
 */

-- sp_CreateEvaluation: 创建评价
-- 功能: 买家对已完成的订单进行评价
DROP PROCEDURE IF EXISTS [sp_CreateEvaluation];
GO
CREATE PROCEDURE [sp_CreateEvaluation]
    @OrderID UNIQUEIDENTIFIER,
    @Rating INT,
    @Content NVARCHAR(500) NULL,
    @BuyerID UNIQUEIDENTIFIER -- 仍然需要买家ID来验证权限
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ActualBuyerID UNIQUEIDENTIFIER; -- 实际订单中的买家ID
    DECLARE @SellerID UNIQUEIDENTIFIER;
    DECLARE @OrderStatus NVARCHAR(50);
    DECLARE @ErrorMessage NVARCHAR(4000);
    DECLARE @NewEvaluationID UNIQUEIDENTIFIER = NEWID(); -- 预先生成新的评价ID
    DECLARE @ProductID UNIQUEIDENTIFIER; -- 用于返回商品ID
    DECLARE @ProductName NVARCHAR(255); -- 用于返回商品名称

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查订单是否存在，是否属于该买家，以及是否已完成
        SELECT @OrderStatus = O.Status, 
               @SellerID = O.SellerID, 
               @ActualBuyerID = O.BuyerID,
               @ProductID = O.ProductID -- 获取商品ID
        FROM [Order] O
        WHERE O.OrderID = @OrderID;

        IF @OrderStatus IS NULL
        BEGIN
            SET @ErrorMessage = '创建评价失败：订单不存在。';
            THROW 50012, @ErrorMessage, 1;
        END

        IF @ActualBuyerID != @BuyerID -- 验证传入的买家ID是否与订单的买家ID一致
        BEGIN
            SET @ErrorMessage = '创建评价失败：您不是该订单的买家。';
            THROW 50013, @ErrorMessage, 1;
        END

        IF @OrderStatus != 'Completed'
        BEGIN
            SET @ErrorMessage = '创建评价失败：只有已完成的订单才能评价。当前订单状态：' + @OrderStatus;
            THROW 50014, @ErrorMessage, 1;
        END

        -- 检查是否已评价过该订单
        IF EXISTS (SELECT 1 FROM [Evaluation] WHERE OrderID = @OrderID)
        BEGIN
            SET @ErrorMessage = '创建评价失败：您已评价过此订单。';
            THROW 50015, @ErrorMessage, 1;
        END

        -- 检查评分是否在有效范围内 (1-5)
        IF @Rating NOT BETWEEN 1 AND 5
        BEGIN
            SET @ErrorMessage = '创建评价失败：评分必须在1到5之间。';
            THROW 50016, @ErrorMessage, 1;
        END

        -- 插入评价
        INSERT INTO [Evaluation] (EvaluationID, OrderID, Rating, Content, CreateTime)
        VALUES (@NewEvaluationID, @OrderID, @Rating, @Content, GETDATE());

        -- 查询商品名称以返回
        SELECT @ProductName = ProductName FROM [Product] WHERE ProductID = @ProductID;

        -- 返回新创建评价的完整信息，包括买家和卖家用户名
        SELECT 
            @NewEvaluationID AS 评价ID, 
            E.OrderID AS 订单ID, 
            @ProductID AS 商品ID,
            @ProductName AS 商品名称,
            UB.UserName AS 买家用户名,
            US.UserName AS 卖家用户名,
            E.Rating AS 评分,
            E.Content AS 评价内容,
            E.CreateTime AS 创建时间
        FROM [Evaluation] E
        JOIN [Order] O ON E.OrderID = O.OrderID
        JOIN [User] UB ON O.BuyerID = UB.UserID
        JOIN [User] US ON O.SellerID = US.UserID
        WHERE E.EvaluationID = @NewEvaluationID;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO


-- sp_GetAllEvaluations: 获取所有评价列表 (管理员视图)
-- 功能: 获取所有评价的列表，可根据商品ID、卖家ID、买家ID、评分范围筛选和分页
DROP PROCEDURE IF EXISTS [sp_GetAllEvaluations];
GO
CREATE PROCEDURE [sp_GetAllEvaluations]
    @ProductIDFilter UNIQUEIDENTIFIER = NULL,
    @SellerIDFilter UNIQUEIDENTIFIER = NULL, -- 筛选现在基于订单表的SellerID
    @BuyerIDFilter UNIQUEIDENTIFIER = NULL,  -- 筛选现在基于订单表的BuyerID
    @MinRating INT = NULL,
    @MaxRating INT = NULL,
    @PageNumber INT = 1,
    @PageSize INT = 10
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Sql NVARCHAR(MAX);
    DECLARE @Params NVARCHAR(MAX);
    DECLARE @WhereClause NVARCHAR(MAX) = N' WHERE 1=1'; -- Start with a true condition to easily append AND

    IF @ProductIDFilter IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND O.ProductID = @InnerProductIDFilter'; -- 修改为 O.ProductID
    IF @SellerIDFilter IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND O.SellerID = @InnerSellerIDFilter'; -- 修改为 O.SellerID
    IF @BuyerIDFilter IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND O.BuyerID = @InnerBuyerIDFilter';   -- 修改为 O.BuyerID
    IF @MinRating IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.Rating >= @InnerMinRating';
    IF @MaxRating IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.Rating <= @InnerMaxRating';

    SET @Sql = N'
    SELECT E.EvaluationID AS 评价ID,
           E.OrderID AS 订单ID,
           O.BuyerID AS 买家ID, -- 从订单表获取买家ID
           UB.UserName AS 买家用户名,
           O.SellerID AS 卖家ID, -- 从订单表获取卖家ID
           US.UserName AS 卖家用户名,
           E.Rating AS 评分,
           E.Content AS 评价内容,
           E.CreateTime AS 创建时间,
           O.ProductID AS 商品ID,
           P.ProductName AS 商品名称
    FROM [Evaluation] E
    JOIN [Order] O ON E.OrderID = O.OrderID -- 加入订单表
    LEFT JOIN [Product] P ON O.ProductID = P.ProductID -- 新增：连接 Product 表以获取商品名称
    JOIN [User] UB ON O.BuyerID = UB.UserID -- 联接买家用户表
    JOIN [User] US ON O.SellerID = US.UserID -- 联接卖家用户表' + @WhereClause + N'
    ORDER BY E.CreateTime DESC
    OFFSET @InnerOffset ROWS FETCH NEXT @InnerPageSize ROWS ONLY;';

    SET @Params = N'@InnerProductIDFilter UNIQUEIDENTIFIER, @InnerSellerIDFilter UNIQUEIDENTIFIER, @InnerBuyerIDFilter UNIQUEIDENTIFIER, @InnerMinRating INT, @InnerMaxRating INT, @InnerOffset INT, @InnerPageSize INT';

    DECLARE @Offset INT = (@PageNumber - 1) * @PageSize;

    EXEC sp_executesql @Sql, @Params,
                       @InnerProductIDFilter = @ProductIDFilter,
                       @InnerSellerIDFilter = @SellerIDFilter,
                       @InnerBuyerIDFilter = @BuyerIDFilter,
                       @InnerMinRating = @MinRating,
                       @InnerMaxRating = @MaxRating,
                       @InnerOffset = @Offset,
                       @InnerPageSize = @PageSize;
END;
GO

-- sp_DeleteEvaluation: 管理员删除评价
-- 功能: 根据评价ID删除评价
DROP PROCEDURE IF EXISTS [sp_DeleteEvaluation];
GO
CREATE PROCEDURE [sp_DeleteEvaluation]
    @EvaluationID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ErrorMessage NVARCHAR(4000);

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查评价是否存在
        IF NOT EXISTS (SELECT 1 FROM [Evaluation] WHERE EvaluationID = @EvaluationID)
        BEGIN
            SET @ErrorMessage = '删除评价失败：评价不存在。';
            THROW 50001, @ErrorMessage, 1; -- 使用自定义错误码
        END

        DELETE FROM [Evaluation]
        WHERE EvaluationID = @EvaluationID;

        IF @@ROWCOUNT = 0
        BEGIN
            SET @ErrorMessage = '删除评价失败：未能删除记录。';
            THROW 50002, @ErrorMessage, 1; -- 使用自定义错误码
        END

        COMMIT TRANSACTION;
        SELECT '评价删除成功' AS 消息;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetEvaluationsBySellerId: 根据卖家ID获取该卖家的所有评价
DROP PROCEDURE IF EXISTS [sp_GetEvaluationsBySellerId];
GO
CREATE PROCEDURE [sp_GetEvaluationsBySellerId]
    @SellerID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        E.EvaluationID AS 评价ID,
        E.OrderID AS 订单ID,
        O.ProductID AS 商品ID, -- 从订单表获取商品ID
        P.ProductName AS 商品名称, -- 从商品表获取商品名称
        UB.UserName AS 买家用户名,
        US.UserName AS 卖家用户名,
        E.Rating AS 评分,
        E.Content AS 评价内容,
        E.CreateTime AS 创建时间
    FROM [Evaluation] E
    JOIN [Order] O ON E.OrderID = O.OrderID
    LEFT JOIN [Product] P ON O.ProductID = P.ProductID -- 连接商品表以获取商品名称
    JOIN [User] UB ON O.BuyerID = UB.UserID
    JOIN [User] US ON O.SellerID = US.UserID
    WHERE O.SellerID = @SellerID;
END;
GO

-- sp_GetEvaluationsByBuyerId: 根据买家ID获取该买家的所有评价
DROP PROCEDURE IF EXISTS [sp_GetEvaluationsByBuyerId];
GO
CREATE PROCEDURE [sp_GetEvaluationsByBuyerId]
    @BuyerID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        E.EvaluationID AS 评价ID,
        E.OrderID AS 订单ID,
        O.ProductID AS 商品ID, -- 从订单表获取商品ID
        P.ProductName AS 商品名称, -- 从商品表获取商品名称
        UB.UserName AS 买家用户名,
        US.UserName AS 卖家用户名,
        E.Rating AS 评分,
        E.Content AS 评价内容,
        E.CreateTime AS 创建时间
    FROM [Evaluation] E
    JOIN [Order] O ON E.OrderID = O.OrderID
    LEFT JOIN [Product] P ON O.ProductID = P.ProductID -- 连接商品表以获取商品名称
    JOIN [User] UB ON O.BuyerID = UB.UserID
    JOIN [User] US ON O.SellerID = US.UserID
    WHERE O.BuyerID = @BuyerID;
END;
GO