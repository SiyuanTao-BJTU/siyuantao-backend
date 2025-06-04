/*
 * 退货流程相关存储过程
 */

-- sp_CreateReturnRequest: 买家发起退货请求
-- 输入: @orderId UNIQUEIDENTIFIER, @buyerId UNIQUEIDENTIFIER, @requestReasonDetail NVARCHAR(MAX), @returnReasonCode VARCHAR(100)
-- 逻辑: 检查订单是否存在、买家是否匹配、订单状态是否允许退货。
--       检查是否已存在此订单的退货请求。
--       插入新的 ReturnRequest 记录，状态设为 '等待卖家处理'。
--       更新订单状态为 '退货申请中'。
DROP PROCEDURE IF EXISTS [sp_CreateReturnRequest];
GO
CREATE PROCEDURE [sp_CreateReturnRequest]
    @orderId UNIQUEIDENTIFIER,
    @buyerId UNIQUEIDENTIFIER,
    @requestReasonDetail NVARCHAR(MAX), -- Renamed from @returnReason for clarity, this is the detailed text by user
    @returnReasonCode VARCHAR(100)    -- New: Standardized reason code
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentOrderStatus NVARCHAR(50);
    DECLARE @productId UNIQUEIDENTIFIER;
    DECLARE @sellerId UNIQUEIDENTIFIER;
    DECLARE @newReturnRequestId UNIQUEIDENTIFIER = NEWID(); -- Generate ID upfront
    DECLARE @initialLog NVARCHAR(MAX);

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

        SET @initialLog = FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss') + N' - Buyer (ID: ' + CAST(@buyerId AS VARCHAR(36)) + N') initiated return. Reason Code: ' + ISNULL(@returnReasonCode, 'N/A') + N'. Details: ' + @requestReasonDetail;

        INSERT INTO [ReturnRequest] (
            ReturnRequestID, -- Use pre-generated ID
            OrderID,
            BuyerID,
            SellerID,
            RequestReason, -- Store the detailed text reason here
            ReturnReasonCode, -- Store the standardized code
            RequestDate,
            Status,
            ResolutionDetails -- Initial log entry
        )
        VALUES (
            @newReturnRequestId,
            @orderId,
            @buyerId,
            @sellerId,
            @requestReasonDetail,
            @returnReasonCode,
            GETDATE(),
            N'等待卖家处理',
            @initialLog
        );

        UPDATE [Order]
        SET OrderStatus = N'退货申请中'
        WHERE OrderID = @orderId;

        COMMIT TRANSACTION;
        SELECT @newReturnRequestId AS NewReturnRequestID, N'退货请求已成功创建。' AS Result;
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
    @auditIdea NVARCHAR(MAX) -- Seller's notes or comments
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;
    DECLARE @requestSellerId UNIQUEIDENTIFIER;
    DECLARE @currentResolutionDetails NVARCHAR(MAX);
    DECLARE @logEntry NVARCHAR(MAX);

    -- 检查卖家是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @sellerId)
    BEGIN
        RAISERROR('卖家用户不存在。', 16, 1);
        RETURN;
    END

    SELECT @currentReturnStatus = RR.Status, 
           @orderId = RR.OrderID, 
           @requestSellerId = RR.SellerID,
           @currentResolutionDetails = ISNULL(RR.ResolutionDetails, N'')
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
    DECLARE @actionTaken NVARCHAR(50);

    IF @isAgree = 1
    BEGIN
        SET @newReturnStatus = N\'卖家同意退货\';
        SET @newOrderStatus = N\'退货中\'; -- 或 \'等待买家退货\'
        SET @actionTaken = N\'AGREED\';
    END
    ELSE
    BEGIN
        SET @newReturnStatus = N\'卖家拒绝退货\';
        SET @newOrderStatus = N\'退货申请被拒\'; -- 或恢复到申请前状态，或保持 \'退货申请中\' 并由买家决定下一步
        SET @actionTaken = N\'REJECTED\';
    END

    SET @logEntry = CHAR(13) + CHAR(10) + FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss') + 
                    N' - Seller (ID: ' + CAST(@sellerId AS VARCHAR(36)) + 
                    N') processed: ' + @actionTaken + 
                    N'. Notes: ' + ISNULL(@auditIdea, 'N/A');

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = @newReturnStatus,
            SellerNotes = @auditIdea, -- Keep this for seller specific private notes if different from public log
            ResolutionDetails = @currentResolutionDetails + @logEntry, -- Append to the log
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
-- 输入: @returnRequestId UNIQUEIDENTIFIER, @buyerId UNIQUEIDENTIFIER, @interventionReason NVARCHAR(MAX)
-- 逻辑: 检查退货请求是否存在、是否属于该买家、状态是否允许介入 (例如 '卖家拒绝退货')。
--       更新 ReturnRequest 状态为 '等待管理员介入'。
DROP PROCEDURE IF EXISTS [sp_BuyerRequestIntervention];
GO
CREATE PROCEDURE [sp_BuyerRequestIntervention]
    @returnRequestId UNIQUEIDENTIFIER,
    @buyerId UNIQUEIDENTIFIER,
    @interventionReason NVARCHAR(MAX) -- Reason for requesting intervention
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;
    DECLARE @requestBuyerId UNIQUEIDENTIFIER;
    DECLARE @currentResolutionDetails NVARCHAR(MAX);
    DECLARE @logEntry NVARCHAR(MAX);

    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @buyerId)
    BEGIN RAISERROR(\'买家用户不存在。\', 16, 1); RETURN; END

    SELECT @currentReturnStatus = RR.Status, 
           @orderId = RR.OrderID, 
           @requestBuyerId = RR.BuyerID,
           @currentResolutionDetails = ISNULL(RR.ResolutionDetails, N'')
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

    SET @logEntry = CHAR(13) + CHAR(10) + FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss') + 
                    N' - Buyer (ID: ' + CAST(@buyerId AS VARCHAR(36)) + 
                    N') requested admin intervention. Reason: ' + ISNULL(@interventionReason, 'N/A');

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = N\'等待管理员介入\',
            ResolutionDetails = @currentResolutionDetails + @logEntry -- Append to the log
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
-- 输入: @returnRequestId UNIQUEIDENTIFIER, @adminId UNIQUEIDENTIFIER, @resolutionAction NVARCHAR(100), @adminNotes NVARCHAR(MAX)
-- 逻辑: 检查退货请求是否存在、管理员是否有效、状态是否为 '等待管理员介入'。
--       根据 @resolutionAction (新的退货请求状态) 更新 ReturnRequest。
--       相应更新 Order 状态 (例如 '已退款', '退货关闭' 等)。
DROP PROCEDURE IF EXISTS [sp_AdminResolveReturnRequest];
GO
CREATE PROCEDURE [sp_AdminResolveReturnRequest]
    @returnRequestId UNIQUEIDENTIFIER,
    @adminId UNIQUEIDENTIFIER,
    @resolutionAction NVARCHAR(100), -- e.g., 'REFUND_APPROVED', 'RETURN_DECLINED_BY_ADMIN', 'PARTIAL_REFUND'
    @adminNotes NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @currentReturnStatus NVARCHAR(50);
    DECLARE @orderId UNIQUEIDENTIFIER;
    DECLARE @newReturnStatus NVARCHAR(50);
    DECLARE @newOrderStatus NVARCHAR(50);
    DECLARE @currentResolutionDetails NVARCHAR(MAX);
    DECLARE @logEntry NVARCHAR(MAX);

    -- Check admin (Assuming Admin is a User with a specific role, or a separate AdminUsers table)
    -- For simplicity, we'll just check if @adminId exists in User table. Add role check in service layer.
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @adminId)
    BEGIN
        RAISERROR(N'管理员用户不存在。', 16, 1);
        RETURN;
    END

    SELECT @currentReturnStatus = RR.Status, 
           @orderId = RR.OrderID,
           @currentResolutionDetails = ISNULL(RR.ResolutionDetails, N'')
    FROM [ReturnRequest] RR
    WHERE RR.ReturnRequestID = @returnRequestId;

    IF @currentReturnStatus IS NULL
    BEGIN RAISERROR(\'退货请求不存在。\', 16, 1); RETURN; END

    IF @currentReturnStatus != N\'等待管理员介入\'
    BEGIN
        RAISERROR(\'此退货请求当前状态不是 \"等待管理员介入\"，无法操作。\', 16, 1);
        RETURN;
    END

    -- Determine new statuses based on @resolutionAction
    -- This logic might be more complex and involve Order status updates too
    IF @resolutionAction = N\'REFUND_APPROVED\' -- Example action
    BEGIN
        SET @newReturnStatus = N\'退款完成\';
        SET @newOrderStatus = N\'已退款\'; -- Or relevant order status
    END
    ELSE IF @resolutionAction = N\'RETURN_DECLINED_BY_ADMIN\' -- Example action
    BEGIN
        SET @newReturnStatus = N\'请求已关闭\'; -- Or '管理员拒绝退货'
        SET @newOrderStatus = N\'退货已关闭\'; -- Or revert to a pre-return status
    END
    ELSE
    BEGIN
        -- Handle other actions or raise error for unknown action
        RAISERROR(N\'无效的管理员操作代码。\', 16, 1);
        RETURN;
    END;

    SET @logEntry = CHAR(13) + CHAR(10) + FORMAT(GETDATE(), 'yyyy-MM-dd HH:mm:ss') + 
                    N' - Admin (ID: ' + CAST(@adminId AS VARCHAR(36)) + 
                    N') resolved: ' + @resolutionAction + 
                    N'. Notes: ' + ISNULL(@adminNotes, 'N/A');

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE [ReturnRequest]
        SET Status = @newReturnStatus,
            AdminNotes = @adminNotes, -- Keep specific admin notes if needed
            ResolutionDetails = @currentResolutionDetails + @logEntry, -- Append to the log
            ResolutionDate = GETDATE()
        WHERE ReturnRequestID = @returnRequestId;

        UPDATE [Order]
        SET OrderStatus = @newOrderStatus -- Update order status accordingly
        WHERE OrderID = @orderId;

        -- TODO: Consider further actions like triggering refund process, updating stock etc.
        -- These would typically be handled by the service layer calling other services/DALs.

        COMMIT TRANSACTION;
        SELECT N\'退货请求已由管理员处理。\' AS Result;
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