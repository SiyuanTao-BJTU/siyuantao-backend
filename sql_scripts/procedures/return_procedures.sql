/*
 * 退货流程相关存储过程
 */

-- sp_CreateReturnRequest: 买家发起退货请求
-- 输入: @orderId UNIQUEIDENTIFIER, @buyerId UNIQUEIDENTIFIER, @returnReason NVARCHAR(MAX)
-- 逻辑: 检查订单是否存在、买家是否匹配、订单状态是否允许退货。
--       检查是否已存在此订单的退货请求。
--       插入新的 ReturnRequest 记录，状态设为 '等待卖家处理'。
--       更新订单状态为 '退货申请中'。
DROP PROCEDURE IF EXISTS [sp_CreateReturnRequest];
GO
CREATE PROCEDURE [sp_CreateReturnRequest]
    @orderId UNIQUEIDENTIFIER,
    @buyerId UNIQUEIDENTIFIER,
    @returnReason NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentOrderStatus NVARCHAR(50);
    DECLARE @productId UNIQUEIDENTIFIER;
    DECLARE @sellerId UNIQUEIDENTIFIER;

    -- 检查买家是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @buyerId)
    BEGIN
        RAISERROR('买家用户不存在。', 16, 1);
        RETURN;
    END

    -- 检查订单是否存在，是否属于该买家，并获取当前状态和商品ID
    SELECT @currentOrderStatus = O.OrderStatus, @productId = O.ProductID
    FROM [Order] O
    WHERE O.OrderID = @orderId AND O.BuyerID = @buyerId;

    IF @currentOrderStatus IS NULL
    BEGIN
        RAISERROR('订单不存在或不属于该买家。', 16, 1);
        RETURN;
    END

    -- TODO: 根据实际业务逻辑，定义允许发起退货的订单状态
    -- 例如: \'已发货\', \'已完成\'
    IF @currentOrderStatus NOT IN (N\'已发货\', N\'已完成\')
    BEGIN
        RAISERROR('当前订单状态不允许发起退货。', 16, 1);
        RETURN;
    END

    -- 检查是否已存在针对此订单的未关闭的退货请求
    IF EXISTS (SELECT 1 FROM [ReturnRequest] WHERE OrderID = @orderId AND Status NOT IN (N\'退款完成\', N\'请求已关闭\'))
    BEGIN
        RAISERROR('此订单已存在处理中的退货请求。', 16, 1);
        RETURN;
    END

    -- 获取卖家ID
    SELECT @sellerId = P.OwnerID FROM [Product] P WHERE P.ProductID = @productId;
    IF @sellerId IS NULL
    BEGIN
        RAISERROR('无法找到订单关联商品的卖家信息。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        INSERT INTO [ReturnRequest] (
            OrderID,
            BuyerID,
            SellerID,
            RequestReason,
            RequestDate,
            Status
        )
        VALUES (
            @orderId,
            @buyerId,
            @sellerId,
            @returnReason,
            GETDATE(),
            N\'等待卖家处理\' -- 初始状态
        );

        UPDATE [Order]
        SET OrderStatus = N\'退货申请中\'
        WHERE OrderID = @orderId;

        COMMIT TRANSACTION;
        SELECT \'退货请求已成功创建。\' AS Result, SCOPE_IDENTITY() AS NewReturnRequestID; -- 注意: SCOPE_IDENTITY() 可能不适用UNIQUEIDENTIFIER PK，应返回基于NEWID()的值
                                                                                    -- 考虑返回刚插入的ID，如果ReturnRequestID是NEWID()生成的，需要先生成再插入
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_HandleReturnRequest: 卖家处理退货请求
-- 输入: @returnRequestId UNIQUEIDENTIFIER, @sellerId UNIQUEIDENTIFIER, @isAgree BIT, @auditIdea NVARCHAR(MAX)
-- 逻辑: 检查退货请求是否存在、是否属于该卖家、状态是否为 '等待卖家处理'。
--       根据 @isAgree 更新 ReturnRequest 状态 ('卖家同意退货' 或 '卖家拒绝退货') 和 Order 状态。
--       记录卖家处理意见和时间。
DROP PROCEDURE IF EXISTS [sp_HandleReturnRequest];
GO
CREATE PROCEDURE [sp_HandleReturnRequest]
    @returnRequestId UNIQUEIDENTIFIER,
    @sellerId UNIQUEIDENTIFIER,
    @isAgree BIT,
    @auditIdea NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;
    DECLARE @requestSellerId UNIQUEIDENTIFIER;

    -- 检查卖家是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @sellerId)
    BEGIN
        RAISERROR('卖家用户不存在。', 16, 1);
        RETURN;
    END

    SELECT @currentReturnStatus = RR.Status, @orderId = RR.OrderID, @requestSellerId = RR.SellerID
    FROM [ReturnRequest] RR
    WHERE RR.ReturnRequestID = @returnRequestId;

    IF @currentReturnStatus IS NULL
    BEGIN
        RAISERROR('退货请求不存在。', 16, 1);
        RETURN;
    END

    IF @requestSellerId != @sellerId
    BEGIN
        RAISERROR('您无权处理此退货请求，因为您不是该请求对应的卖家。', 16, 1);
        RETURN;
    END

    IF @currentReturnStatus != N\'等待卖家处理\'
    BEGIN
        RAISERROR(\'此退货请求当前状态不是"等待卖家处理"，无法操作。\' , 16, 1);
        RETURN;
    END

    DECLARE @newReturnStatus NVARCHAR(50);
    DECLARE @newOrderStatus NVARCHAR(50);

    IF @isAgree = 1
    BEGIN
        SET @newReturnStatus = N\'卖家同意退货\';
        SET @newOrderStatus = N\'退货中\'; -- 或 \'等待买家退货\'
    END
    ELSE
    BEGIN
        SET @newReturnStatus = N\'卖家拒绝退货\';
        SET @newOrderStatus = N\'退货申请被拒\'; -- 或恢复到申请前状态，或保持 \'退货申请中\' 并由买家决定下一步
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = @newReturnStatus,
            SellerNotes = @auditIdea,
            SellerActionDate = GETDATE()
        WHERE ReturnRequestID = @returnRequestId;

        UPDATE [Order]
        SET OrderStatus = @newOrderStatus
        WHERE OrderID = @orderId;

        COMMIT TRANSACTION;
        SELECT \'退货请求处理成功。\' AS Result;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_BuyerRequestIntervention: 买家申请管理员介入
-- 输入: @returnRequestId UNIQUEIDENTIFIER, @buyerId UNIQUEIDENTIFIER
-- 逻辑: 检查退货请求是否存在、是否属于该买家、状态是否允许介入 (例如 '卖家拒绝退货')。
--       更新 ReturnRequest 状态为 '等待管理员介入'。
DROP PROCEDURE IF EXISTS [sp_BuyerRequestIntervention];
GO
CREATE PROCEDURE [sp_BuyerRequestIntervention]
    @returnRequestId UNIQUEIDENTIFIER,
    @buyerId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;
    DECLARE @requestBuyerId UNIQUEIDENTIFIER;

    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @buyerId)
    BEGIN RAISERROR(\'买家用户不存在。\', 16, 1); RETURN; END

    SELECT @currentReturnStatus = RR.Status, @orderId = RR.OrderID, @requestBuyerId = RR.BuyerID
    FROM [ReturnRequest] RR
    WHERE RR.ReturnRequestID = @returnRequestId;

    IF @currentReturnStatus IS NULL
    BEGIN RAISERROR(\'退货请求不存在。\', 16, 1); RETURN; END

    IF @requestBuyerId != @buyerId
    BEGIN RAISERROR(\'您无权操作此退货请求，因为您不是该请求的发起人。\', 16, 1); RETURN; END

    -- TODO: 明确哪些状态下允许买家申请介入
    IF @currentReturnStatus NOT IN (N\'卖家拒绝退货\') -- , N\'卖家超时未处理\' 等
    BEGIN
        RAISERROR(\'当前退货请求状态不允许申请管理员介入。\', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = N\'等待管理员介入\'
        WHERE ReturnRequestID = @returnRequestId;

        -- 可选：更新订单状态
        UPDATE [Order]
        SET OrderStatus = N\'等待管理员介入\' -- 或保持原样，由ReturnRequest状态驱动
        WHERE OrderID = @orderId;

        COMMIT TRANSACTION;
        SELECT \'申请管理员介入成功。\' AS Result;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_AdminResolveReturnRequest: 管理员处理退货介入
-- 输入: @returnRequestId UNIQUEIDENTIFIER, @adminId UNIQUEIDENTIFIER, @status NVARCHAR(50), @auditIdea NVARCHAR(MAX)
-- 逻辑: 检查退货请求是否存在、管理员是否有效、状态是否为 '等待管理员介入'。
--       根据 @status (新的退货请求状态) 更新 ReturnRequest。
--       相应更新 Order 状态 (例如 '已退款', '退货关闭' 等)。
DROP PROCEDURE IF EXISTS [sp_AdminResolveReturnRequest];
GO
CREATE PROCEDURE [sp_AdminResolveReturnRequest]
    @returnRequestId UNIQUEIDENTIFIER,
    @adminId UNIQUEIDENTIFIER,
    @newStatus NVARCHAR(50), -- 例如：'管理员同意退款', '管理员支持卖家', '退款完成', '请求已关闭'
    @auditIdea NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;

    -- 检查管理员是否存在 (可选，也可在应用层校验)
    -- IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @adminId AND UserType = \'Admin\')
    -- BEGIN RAISERROR(\'管理员用户不存在或无权限。\', 16, 1); RETURN; END

    SELECT @currentReturnStatus = RR.Status, @orderId = RR.OrderID
    FROM [ReturnRequest] RR
    WHERE RR.ReturnRequestID = @returnRequestId;

    IF @currentReturnStatus IS NULL
    BEGIN RAISERROR(\'退货请求不存在。\', 16, 1); RETURN; END

    IF @currentReturnStatus != N\'等待管理员介入\'
    BEGIN
        RAISERROR(\'此退货请求当前状态不是"等待管理员介入"，无法由管理员处理。\', 16, 1);
        RETURN;
    END

    -- 校验 @newStatus 是否是合法的管理员处理后状态
    IF @newStatus NOT IN (N\'管理员同意退款\', N\'管理员支持卖家\', N\'退款完成\', N\'请求已关闭\')
    BEGIN
        RAISERROR(\'无效的管理员处理状态。\', 16, 1);
        RETURN;
    END

    DECLARE @newOrderStatus NVARCHAR(50);
    IF @newStatus IN (N\'管理员同意退款\', N\'退款完成\')
    BEGIN
        SET @newOrderStatus = N\'已退款\';
    END
    ELSE IF @newStatus = N\'管理员支持卖家\' OR @newStatus = N\'请求已关闭\' -- 支持卖家，则订单可能恢复原状或关闭
    BEGIN
        -- 这里的逻辑需要根据业务确定，例如订单恢复到 \'已完成\' (如果之前是) 或 \'已关闭\'
        -- 为简化，我们统一设置为 \'已关闭\' (如果退货流程结束且未退款)
        -- 或者，订单状态可能不需要改变，只改变退货请求状态
        SET @newOrderStatus = N\'已完成\'; -- 假设支持卖家，则退货流程结束，订单状态回归
        IF (SELECT OrderStatus FROM [Order] WHERE OrderID = @orderId) = N\'退货申请中\' OR
           (SELECT OrderStatus FROM [Order] WHERE OrderID = @orderId) = N\'等待管理员介入\'
        BEGIN
             -- 根据业务逻辑决定订单的最终状态，这里暂定为 '已完成'
             -- 或者查找退货申请前的状态并恢复
             -- 此处简化处理，如果管理员支持卖家，则订单可以认为交易完成。
             SET @newOrderStatus = N\'已完成\';
        END
    END


    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = @newStatus,
            AdminID = @adminId,
            AdminNotes = @auditIdea,
            AdminActionDate = GETDATE()
        WHERE ReturnRequestID = @returnRequestId;

        IF @newOrderStatus IS NOT NULL
        BEGIN
            UPDATE [Order]
            SET OrderStatus = @newOrderStatus
            WHERE OrderID = @orderId;
        END
        -- TODO: 如果是 \'退款完成\'，可能需要触发实际的退款操作或记录。

        COMMIT TRANSACTION;
        SELECT \'管理员处理退货请求成功。\' AS Result;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetReturnRequestById: 获取退货请求详情
-- 输入: @returnRequestId UNIQUEIDENTIFIER
-- 输出: 退货请求的详细信息，包括订单、商品、买家、卖家、管理员（如果已处理）信息。
DROP PROCEDURE IF EXISTS [sp_GetReturnRequestById];
GO
CREATE PROCEDURE [sp_GetReturnRequestById]
    @returnRequestId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        RR.ReturnRequestID AS 退货请求ID,
        RR.OrderID AS 订单ID,
        O.OrderDate AS 订单日期,
        O.OrderStatus AS 当前订单状态,
        P.ProductID AS 商品ID,
        P.ProductName AS 商品名称,
        RR.BuyerID AS 买家ID,
        Buyer.UserName AS 买家用户名,
        RR.SellerID AS 卖家ID,
        Seller.UserName AS 卖家用户名,
        RR.RequestReason AS 退货原因,
        RR.RequestDate AS 请求日期,
        RR.Status AS 退货状态,
        RR.SellerNotes AS 卖家备注,
        RR.SellerActionDate AS 卖家处理日期,
        RR.AdminID AS 管理员ID,
        AdminUser.UserName AS 管理员用户名,
        RR.AdminNotes AS 管理员备注,
        RR.AdminActionDate AS 管理员处理日期
    FROM [ReturnRequest] RR
    JOIN [Order] O ON RR.OrderID = O.OrderID
    JOIN [Product] P ON O.ProductID = P.ProductID
    JOIN [User] Buyer ON RR.BuyerID = Buyer.UserID
    JOIN [User] Seller ON RR.SellerID = Seller.UserID
    LEFT JOIN [User] AdminUser ON RR.AdminID = AdminUser.UserID
    WHERE RR.ReturnRequestID = @returnRequestId;

    IF @@ROWCOUNT = 0
    BEGIN
        RAISERROR(\'未找到指定的退货请求。\', 16, 1);
        RETURN;
    END
END;
GO

-- sp_GetReturnRequestsByUserId: 获取用户的退货请求列表（作为买家或卖家）
-- 输入: @userId UNIQUEIDENTIFIER
-- 输出: 用户相关的退货请求列表。
DROP PROCEDURE IF EXISTS [sp_GetReturnRequestsByUserId];
GO
CREATE PROCEDURE [sp_GetReturnRequestsByUserId]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR(\'用户不存在。\', 16, 1);
        RETURN;
    END

    SELECT
        RR.ReturnRequestID AS 退货请求ID,
        RR.OrderID AS 订单ID,
        P.ProductName AS 商品名称,
        RR.RequestDate AS 请求日期,
        RR.Status AS 退货状态,
        CASE
            WHEN RR.BuyerID = @userId THEN \'买家\'
            WHEN RR.SellerID = @userId THEN \'卖家\'
            ELSE \'未知角色\'
        END AS 用户角色,
        OtherUser.UserName AS 对方用户名,
        O.OrderStatus AS 订单状态
    FROM [ReturnRequest] RR
    JOIN [Order] O ON RR.OrderID = O.OrderID
    JOIN [Product] P ON O.ProductID = P.ProductID
    LEFT JOIN [User] OtherUser ON (RR.BuyerID = @userId AND OtherUser.UserID = RR.SellerID) OR (RR.SellerID = @userId AND OtherUser.UserID = RR.BuyerID)
    WHERE RR.BuyerID = @userId OR RR.SellerID = @userId
    ORDER BY RR.RequestDate DESC;

END;
GO 