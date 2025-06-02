/*
 * 交易管理模块 - 评价存储过程
 */

-- sp_CreateEvaluation: 创建评价
-- 功能: 买家对已完成的订单进行评价
DROP PROCEDURE IF EXISTS [sp_CreateEvaluation];
GO
CREATE PROCEDURE [sp_CreateEvaluation]
    @OrderID UNIQUEIDENTIFIER,
    @BuyerID UNIQUEIDENTIFIER,
    @Rating INT,
    @Content NVARCHAR(500) NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @SellerID UNIQUEIDENTIFIER;
    DECLARE @OrderStatus NVARCHAR(50);
    DECLARE @ErrorMessage NVARCHAR(4000);
    DECLARE @NewEvaluationID UNIQUEIDENTIFIER = NEWID(); -- 预先生成新的评价ID

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查订单是否存在，是否属于该买家，以及是否已完成
        SELECT @OrderStatus = O.Status, @SellerID = O.SellerID
        FROM [Order] O
        WHERE O.OrderID = @OrderID AND O.BuyerID = @BuyerID;

        IF @OrderStatus IS NULL
        BEGIN
            SET @ErrorMessage = '创建评价失败：订单不存在或您不是该订单的买家。';
            THROW 50012, @ErrorMessage, 1;
        END

        IF @OrderStatus != 'Completed'
        BEGIN
            SET @ErrorMessage = '创建评价失败：只有已完成的订单才能评价。当前订单状态：' + @OrderStatus;
            THROW 50013, @ErrorMessage, 1;
        END

        -- 检查是否已评价过该订单
        IF EXISTS (SELECT 1 FROM [Evaluation] WHERE OrderID = @OrderID)
        BEGIN
            SET @ErrorMessage = '创建评价失败：您已评价过此订单。';
            THROW 50014, @ErrorMessage, 1;
        END

        -- 检查评分是否在有效范围内 (1-5)
        IF @Rating NOT BETWEEN 1 AND 5
        BEGIN
            SET @ErrorMessage = '创建评价失败：评分必须在1到5之间。';
            THROW 50015, @ErrorMessage, 1;
        END

        -- 插入评价
        INSERT INTO [Evaluation] (EvaluationID, OrderID, BuyerID, SellerID, Rating, Content, CreateTime)
        VALUES (@NewEvaluationID, @OrderID, @BuyerID, @SellerID, @Rating, @Content, GETDATE());

        -- 卖家信用分更新逻辑已移至触发器 tr_Evaluation_AfterInsert_UpdateSellerCredit
        
        SELECT @NewEvaluationID AS 评价ID, '评价创建成功' AS 消息;

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
    @SellerIDFilter UNIQUEIDENTIFIER = NULL,
    @BuyerIDFilter UNIQUEIDENTIFIER = NULL,
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
        SET @WhereClause = @WhereClause + N' AND E.ProductID = @InnerProductIDFilter';
    IF @SellerIDFilter IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.SellerID = @InnerSellerIDFilter';
    IF @BuyerIDFilter IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.BuyerID = @InnerBuyerIDFilter';
    IF @MinRating IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.Rating >= @InnerMinRating';
    IF @MaxRating IS NOT NULL
        SET @WhereClause = @WhereClause + N' AND E.Rating <= @InnerMaxRating';

    SET @Sql = N'
    SELECT E.EvaluationID AS 评价ID,
           E.OrderID AS 订单ID,
           E.BuyerID AS 买家ID,
           UB.UserName AS 买家用户名,
           E.SellerID AS 卖家ID,
           US.UserName AS 卖家用户名,
           E.Rating AS 评分,
           E.Content AS 内容,
           E.CreateTime AS 创建时间,
           O.ProductID AS 商品ID,
           P.ProductName AS 商品名称
    FROM [Evaluation] E
    JOIN [User] UB ON E.BuyerID = UB.UserID
    JOIN [User] US ON E.SellerID = US.UserID
    JOIN [Order] O ON E.OrderID = O.OrderID
    JOIN [Product] P ON O.ProductID = P.ProductID' + @WhereClause + N'
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