/*
 * 交易管理模块 - 订单存储过程
 */

-- sp_CreateOrder: 创建新订单
-- 功能: 验证买家和商品信息，扣减库存，创建订单记录
DROP PROCEDURE IF EXISTS [sp_CreateOrder];
GO
CREATE PROCEDURE [sp_CreateOrder]
    @BuyerID UNIQUEIDENTIFIER,
    @ProductID UNIQUEIDENTIFIER,
    @Quantity INT,
    @TradeTime DATETIME,        -- 新增：交易时间
    @TradeLocation NVARCHAR(255) -- 新增：交易地点
    -- @NewOrderID_Output UNIQUEIDENTIFIER OUTPUT -- 移除此行
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @NewOrderID UNIQUEIDENTIFIER; -- 重新引入局部变量
    DECLARE @ProductPrice DECIMAL(10, 2); -- 移除：不再需要内部计算商品价格
    DECLARE @ProductStock INT;
    DECLARE @SellerID UNIQUEIDENTIFIER;
    DECLARE @OrderStatus NVARCHAR(50) = 'PendingSellerConfirmation'; -- 初始状态为待处理
    DECLARE @ErrorMessage NVARCHAR(4000);

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查买家是否存在
        IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @BuyerID)
        BEGIN
            SET @ErrorMessage = '创建订单失败：买家不存在。';
            THROW 50001, @ErrorMessage, 1;
        END

        -- 获取商品信息并锁定商品行以防止并发问题
        SELECT @ProductStock = Quantity, @SellerID = OwnerID
        FROM [Product]
        WITH (UPDLOCK) -- 在事务中锁定行，直到事务结束
        WHERE ProductID = @ProductID AND Status = 'Active';

        IF @ProductStock IS NULL -- 检查商品是否存在
        BEGIN
            SET @ErrorMessage = '创建订单失败：商品不存在或非在售状态。';
            THROW 50002, @ErrorMessage, 1;
        END

        -- 检查库存是否充足
        IF @ProductStock < @Quantity
        BEGIN
            SET @ErrorMessage = '创建订单失败：商品库存不足。当前库存: ' + CAST(@ProductStock AS NVARCHAR(10)) + ', 购买数量: ' + CAST(@Quantity AS NVARCHAR(10));
            THROW 50003, @ErrorMessage, 1;
        END

        -- 扣减库存
        EXEC sp_DecreaseProductQuantity @productId = @ProductID, @quantityToDecrease = @Quantity;

        -- 生成新的 OrderID 并创建订单
        SET @NewOrderID = NEWID(); -- 赋值给局部变量
        INSERT INTO [Order] (OrderID, BuyerID, SellerID, ProductID, Quantity, TradeTime, TradeLocation, CreateTime, Status)
        VALUES (@NewOrderID, @BuyerID, @SellerID, @ProductID, @Quantity, @TradeTime, @TradeLocation, GETDATE(), @OrderStatus);

        -- 返回新创建的订单ID，显式转换为 NVARCHAR(36)
        SELECT CAST(@NewOrderID AS NVARCHAR(36)) AS 订单ID; -- 确保通过 SELECT 返回

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        
        THROW; -- 重新抛出错误，包含原始错误信息和行号
    END CATCH
END;
GO

-- sp_ConfirmOrder: 卖家确认订单
-- 功能: 卖家确认订单，订单状态变为 'Confirmed'
DROP PROCEDURE IF EXISTS [sp_ConfirmOrder];
GO
CREATE PROCEDURE [sp_ConfirmOrder]
    @OrderID UNIQUEIDENTIFIER,
    @SellerID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CurrentStatus NVARCHAR(50);
    DECLARE @ErrorMessage NVARCHAR(4000);

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @CurrentStatus = Status FROM [Order] WHERE OrderID = @OrderID AND SellerID = @SellerID;

        IF @CurrentStatus IS NULL
        BEGIN
            SET @ErrorMessage = '确认订单失败：订单不存在或您不是该订单的卖家。';
            THROW 50004, @ErrorMessage, 1;
        END

        IF @CurrentStatus != 'PendingSellerConfirmation'
        BEGIN
            SET @ErrorMessage = '确认订单失败：订单状态不是"待卖家确认"，无法确认。当前状态：' + @CurrentStatus;
            THROW 50005, @ErrorMessage, 1;
        END

        UPDATE [Order]
        SET Status = 'ConfirmedBySeller' -- 状态更新
        WHERE OrderID = @OrderID;
        
        -- 返回被确认的订单ID
        SELECT @OrderID AS 订单ID, '订单已确认' AS 消息;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_CompleteOrder: 订单完成
-- 功能: 订单交易完成，状态变为 'Completed'
DROP PROCEDURE IF EXISTS [sp_CompleteOrder];
GO
CREATE PROCEDURE [sp_CompleteOrder]
    @OrderID UNIQUEIDENTIFIER,
    @ActorID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CurrentStatus NVARCHAR(50);
    DECLARE @BuyerID UNIQUEIDENTIFIER;
    DECLARE @SellerID UNIQUEIDENTIFIER;
    DECLARE @IsAdmin BIT = 0;
    DECLARE @ErrorMessage NVARCHAR(4000);

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @CurrentStatus = Status, @BuyerID = BuyerID, @SellerID = SellerID FROM [Order] WHERE OrderID = @OrderID;
        
        IF EXISTS (SELECT 1 FROM [User] WHERE UserID = @ActorID AND IsStaff = 1)
            SET @IsAdmin = 1;

        IF @CurrentStatus IS NULL
        BEGIN
            SET @ErrorMessage = '完成订单失败：订单不存在。';
            THROW 50006, @ErrorMessage, 1;
        END

        IF (@ActorID != @BuyerID AND @IsAdmin = 0)
        BEGIN
            SET @ErrorMessage = '完成订单失败：您无权完成此订单。';
            THROW 50007, @ErrorMessage, 1;
        END

        IF @CurrentStatus NOT IN ('ConfirmedBySeller')
        BEGIN
            SET @ErrorMessage = '完成订单失败：订单状态不正确，无法完成。当前状态：' + @CurrentStatus;
            THROW 50008, @ErrorMessage, 1;
        END

        UPDATE [Order]
        SET Status = 'Completed', CompleteTime = GETDATE()
        WHERE OrderID = @OrderID;

        -- 注意：卖家信用分更新逻辑已移至触发器 tr_Order_AfterComplete_UpdateSellerCredit
        SELECT @OrderID AS 订单ID, '订单已完成' AS 消息;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_RejectOrder: 卖家拒绝订单
-- 功能: 卖家拒绝订单，订单状态变为 'Rejected'，库存需要恢复 (通过触发器实现)
DROP PROCEDURE IF EXISTS [sp_RejectOrder];
GO
CREATE PROCEDURE [sp_RejectOrder]
    @OrderID UNIQUEIDENTIFIER,
    @SellerID UNIQUEIDENTIFIER,
    @RejectionReason NVARCHAR(500) NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @CurrentStatus NVARCHAR(50);
    DECLARE @ErrorMessage NVARCHAR(4000);

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @CurrentStatus = Status FROM [Order] WHERE OrderID = @OrderID AND SellerID = @SellerID;

        IF @CurrentStatus IS NULL
        BEGIN
            SET @ErrorMessage = '拒绝订单失败：订单不存在或您不是该订单的卖家。';
            THROW 50009, @ErrorMessage, 1;
        END

        IF @CurrentStatus != 'PendingSellerConfirmation'
        BEGIN
            SET @ErrorMessage = '拒绝订单失败：订单状态不是"待处理"，无法拒绝。当前状态：' + @CurrentStatus;
            THROW 50010, @ErrorMessage, 1;
        END

        UPDATE [Order]
        SET Status = 'Cancelled', CancelTime = GETDATE(), CancelReason = ISNULL(@RejectionReason, 'No reason provided.')
        WHERE OrderID = @OrderID;
        
        SELECT @OrderID AS 订单ID, '订单已取消' AS 消息; 

        -- 库存恢复逻辑已移至触发器 tr_Order_AfterCancel_RestoreQuantity (假设 Rejected 和 Cancelled 都触发库存恢复)
        -- 如果 Rejected 状态的库存恢复逻辑不同，需要单独的触发器或在此处处理。
        -- 根据设计文档，tr_Order_AfterCancel_RestoreQuantity 应该处理 'Cancelled' 和 'Rejected' 状态。

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetOrdersByUser: 根据用户ID获取订单列表
-- 功能: 获取指定用户的订单列表，可根据角色区分买家或卖家订单，并支持状态筛选和分页
DROP PROCEDURE IF EXISTS [sp_GetOrdersByUser];
GO
CREATE PROCEDURE [sp_GetOrdersByUser]
    @UserID UNIQUEIDENTIFIER,
    @UserRole NVARCHAR(50),
    @StatusFilter NVARCHAR(50) = NULL, -- 新增：状态筛选参数
    @PageNumber INT = 1,               -- 新增：页码参数
    @PageSize INT = 10                 -- 新增：每页大小参数
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Sql NVARCHAR(MAX);
    DECLARE @Params NVARCHAR(MAX);
    DECLARE @WhereClause NVARCHAR(MAX) = N'';

    IF @StatusFilter IS NOT NULL AND @StatusFilter <> ''
    BEGIN
        SET @WhereClause = @WhereClause + N' AND O.Status = @InnerStatusFilter';
    END

    IF @UserRole = 'Buyer'
    BEGIN
        SET @Sql = N'
        SELECT O.OrderID AS 订单ID, 
               O.ProductID AS 商品ID, 
               P.ProductName AS 商品名称, 
               O.Quantity AS 数量, 
               O.TradeTime AS 交易时间,
               O.TradeLocation AS 交易地点,
               O.Status AS 订单状态, 
               O.CreateTime AS 创建时间, 
               O.UpdateTime AS 更新时间,
               O.CompleteTime AS 完成时间, 
               O.CancelTime AS 取消时间,
               O.BuyerID AS 买家ID,
               UB.UserName AS 买家用户名,
               O.SellerID AS 卖家ID, 
               US.UserName AS 卖家用户名
        FROM [Order] O
        JOIN [Product] P ON O.ProductID = P.ProductID
        JOIN [User] US ON O.SellerID = US.UserID
        JOIN [User] UB ON O.BuyerID = UB.UserID
        LEFT JOIN [Evaluation] E ON O.OrderID = E.OrderID 
        WHERE O.BuyerID = @InnerUserID' + @WhereClause + N'
        ORDER BY O.CreateTime DESC
        OFFSET @InnerOffset ROWS FETCH NEXT @InnerPageSize ROWS ONLY;';
    END
     ELSE IF @UserRole = 'Seller'
    BEGIN
        SET @Sql = N'
        SELECT O.OrderID AS 订单ID, 
               O.ProductID AS 商品ID, 
               P.ProductName AS 商品名称, 
               O.Quantity AS 数量, 
               O.TradeTime AS 交易时间,
               O.TradeLocation AS 交易地点,
               O.Status AS 订单状态, 
               O.CreateTime AS 创建时间, 
               O.UpdateTime AS 更新时间,
               O.CompleteTime AS 完成时间, 
               O.CancelTime AS 取消时间, 
               O.BuyerID AS 买家ID, 
               UB.UserName AS 买家用户名,
               O.SellerID AS 卖家ID,
               US.UserName AS 卖家用户名
        FROM [Order] O
        JOIN [Product] P ON O.ProductID = P.ProductID
        JOIN [User] UB ON O.BuyerID = UB.UserID
        JOIN [User] US ON O.SellerID = US.UserID
        LEFT JOIN [Evaluation] E ON O.OrderID = E.OrderID
        WHERE O.SellerID = @InnerUserID' + @WhereClause + N'
        ORDER BY O.CreateTime DESC
        OFFSET @InnerOffset ROWS FETCH NEXT @InnerPageSize ROWS ONLY;';
    END
    ELSE
    BEGIN
        DECLARE @ErrorMessage NVARCHAR(4000) = '获取订单失败：无效的用户角色。';
        THROW 50011, @ErrorMessage, 1;
        RETURN;
    END

    SET @Params = N'@InnerUserID UNIQUEIDENTIFIER, @InnerStatusFilter NVARCHAR(50), @InnerOffset INT, @InnerPageSize INT';

    -- 计算 OFFSET 值
    DECLARE @Offset INT = (@PageNumber - 1) * @PageSize;

    EXEC sp_executesql @Sql, @Params, 
                       @InnerUserID = @UserID, 
                       @InnerStatusFilter = @StatusFilter, 
                       @InnerOffset = @Offset, 
                       @InnerPageSize = @PageSize;
END;
GO

-- sp_GetOrderById: 根据订单ID获取订单详情
-- 功能: 获取指定订单的详细信息
DROP PROCEDURE IF EXISTS [sp_GetOrderById];
GO
CREATE PROCEDURE [sp_GetOrderById]
    @OrderID UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        O.OrderID AS 订单ID,
        O.SellerID AS 卖家ID,
        O.BuyerID AS 买家ID,
        O.ProductID AS 商品ID,
        O.Quantity AS 数量,
        O.TradeTime AS 交易时间,
        O.TradeLocation AS 交易地点,
        O.Status AS 订单状态,
        O.CreateTime AS 创建时间,
        O.UpdateTime AS 更新时间,
        O.CompleteTime AS 完成时间,
        O.CancelTime AS 取消时间,
        O.CancelReason AS 取消原因,
        P.ProductName AS 商品名称,
        US.UserName AS 卖家用户名,
        UB.UserName AS 买家用户名
    FROM [Order] O
    JOIN [Product] P ON O.ProductID = P.ProductID
    JOIN [User] US ON O.SellerID = US.UserID
    JOIN [User] UB ON O.BuyerID = UB.UserID
    WHERE O.OrderID = @OrderID;
END;
GO

-- sp_GetAllOrders: 获取所有订单列表 (管理员视图)
-- 功能: 获取所有订单的列表，可根据状态筛选和分页
DROP PROCEDURE IF EXISTS [sp_GetAllOrders];
GO
CREATE PROCEDURE [sp_GetAllOrders]
    @StatusFilter NVARCHAR(50) = NULL, -- 状态筛选参数
    @PageNumber INT = 1,               -- 页码参数
    @PageSize INT = 10                 -- 每页大小参数
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Sql NVARCHAR(MAX);
    DECLARE @Params NVARCHAR(MAX);
    DECLARE @WhereClause NVARCHAR(MAX) = N'';

    IF @StatusFilter IS NOT NULL AND @StatusFilter <> ''
    BEGIN
        SET @WhereClause = @WhereClause + N' WHERE O.Status = @InnerStatusFilter';
    END

    SET @Sql = N'
    SELECT O.OrderID AS 订单ID, 
           O.ProductID AS 商品ID, 
           P.ProductName AS 商品名称, 
           O.Quantity AS 数量, 
           O.TradeTime AS 交易时间,
           O.TradeLocation AS 交易地点,
           O.Status AS 订单状态, 
           O.CreateTime AS 创建时间, 
           O.UpdateTime AS 更新时间,
           O.CompleteTime AS 完成时间, 
           O.CancelTime AS 取消时间, 
           O.BuyerID AS 买家ID, 
           UB.UserName AS 买家用户名,
           O.SellerID AS 卖家ID,
           US.UserName AS 卖家用户名,
           CASE WHEN E.EvaluationID IS NOT NULL THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS 是否已评价
    FROM [Order] O
    JOIN [Product] P ON O.ProductID = P.ProductID
    JOIN [User] UB ON O.BuyerID = UB.UserID
    JOIN [User] US ON O.SellerID = US.UserID
    LEFT JOIN [Evaluation] E ON O.OrderID = E.OrderID' + @WhereClause + N'
    ORDER BY O.CreateTime DESC
    OFFSET @InnerOffset ROWS FETCH NEXT @InnerPageSize ROWS ONLY;';

    SET @Params = N'@InnerStatusFilter NVARCHAR(50), @InnerOffset INT, @InnerPageSize INT';

    -- 计算 OFFSET 值
    DECLARE @Offset INT = (@PageNumber - 1) * @PageSize;

    EXEC sp_executesql @Sql, @Params, 
                       @InnerStatusFilter = @StatusFilter, 
                       @InnerOffset = @Offset, 
                       @InnerPageSize = @PageSize;
END;
GO