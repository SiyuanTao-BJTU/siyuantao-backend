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
        SELECT CAST(@NewOrderID AS NVARCHAR(36)) AS OrderID; -- 确保通过 SELECT 返回

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
        SET Status = 'ConfirmedBySeller'
        WHERE OrderID = @OrderID;

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
-- 功能: 获取指定用户的订单列表，可根据角色区分买家或卖家订单
DROP PROCEDURE IF EXISTS [sp_GetOrdersByUser];
GO
CREATE PROCEDURE [sp_GetOrdersByUser]
    @UserID UNIQUEIDENTIFIER,
    @UserRole NVARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    IF @UserRole = 'Buyer'
    BEGIN
        SELECT O.OrderID, O.ProductID, P.ProductName, O.Quantity, O.Quantity * P.Price AS TotalPrice, O.Status AS OrderStatus, O.CreateTime, O.CompleteTime, O.CancelTime, O.SellerID, US.UserName AS SellerUsername
        FROM [Order] O
        JOIN [Product] P ON O.ProductID = P.ProductID
        JOIN [User] US ON O.SellerID = US.UserID
        WHERE O.BuyerID = @UserID
        ORDER BY O.CreateTime DESC;
    END
    ELSE IF @UserRole = 'Seller'
    BEGIN
        SELECT O.OrderID, O.ProductID, P.ProductName, O.Quantity, O.Quantity * P.Price AS TotalPrice, O.Status AS OrderStatus, O.CreateTime, O.CompleteTime, O.CancelTime, O.BuyerID, UB.UserName AS BuyerUsername
        FROM [Order] O
        JOIN [Product] P ON O.ProductID = P.ProductID
        JOIN [User] UB ON O.BuyerID = UB.UserID
        WHERE O.SellerID = @UserID
        ORDER BY O.CreateTime DESC;
    END
    ELSE
    BEGIN
        DECLARE @ErrorMessage NVARCHAR(4000) = '获取订单失败：无效的用户角色。';
        THROW 50011, @ErrorMessage, 1;
    END
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
        O.OrderID AS order_id,
        O.SellerID AS seller_id,
        O.BuyerID AS buyer_id,
        O.ProductID AS product_id,
        O.Quantity AS quantity,
        O.TradeTime AS trade_time,
        O.TradeLocation AS trade_location,
        O.Status AS status,
        O.CreateTime AS created_at,
        O.UpdateTime AS updated_at,
        O.CompleteTime AS complete_time,
        O.CancelTime AS cancel_time,
        O.CancelReason AS cancel_reason,
        P.ProductName AS product_name,
        US.UserName AS seller_username,
        UB.UserName AS buyer_username
    FROM [Order] O
    JOIN [Product] P ON O.ProductID = P.ProductID
    JOIN [User] US ON O.SellerID = US.UserID
    JOIN [User] UB ON O.BuyerID = UB.UserID
    WHERE O.OrderID = @OrderID;
END;
GO