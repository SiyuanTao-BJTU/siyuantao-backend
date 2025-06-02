/*
 * 管理员功能模块 - 存储过程
 * 功能: 用户管理（禁用/启用/调整信用）、举报处理、系统通知发布
 */

-- sp_ChangeUserStatus: 管理员禁用/启用用户账户
-- 输入: @userId UNIQUEIDENTIFIER, @newStatus NVARCHAR(20) ('Active'或'Disabled'), @adminId UNIQUEIDENTIFIER
-- 逻辑: 检查管理员权限，检查用户是否存在，更新用户 Status。
DROP PROCEDURE IF EXISTS [sp_ChangeUserStatus];
GO
CREATE PROCEDURE [sp_ChangeUserStatus]
    @userId UNIQUEIDENTIFIER,
    @newStatus NVARCHAR(20), -- 'Active' 或 'Disabled'
    @adminId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @adminIsStaff BIT;
    DECLARE @userExists BIT;
    DECLARE @currentStatus NVARCHAR(20);

    -- 检查 @adminId 是否为管理员 (SQL语句1)
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以更改用户状态。', 16, 1);
        RETURN;
    END

    -- 检查 @newStatus 是否有效 (控制流 IF)
    IF @newStatus NOT IN ('Active', 'Disabled')
    BEGIN
        RAISERROR('无效的用户状态，状态必须是 Active 或 Disabled。', 16, 1);
        RETURN;
    END

    -- 检查用户是否存在并获取当前状态 (SQL语句2)
    SELECT @userExists = 1, @currentStatus = Status FROM [User] WHERE UserID = @userId;
    IF @userExists IS NULL
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- 如果状态没有变化，直接返回 (控制流 IF)
    IF @currentStatus = @newStatus
    BEGIN
        -- RAISERROR('用户状态已经是 %s，无需更改。', 16, 1, @newStatus); -- 可选提示
        SELECT '用户状态已经是 ' + @newStatus + '，无需更改。' AS 结果, @userId AS 用户ID, @newStatus AS 当前状态;
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 更新用户 Status (SQL语句3)
        UPDATE [User]
        SET Status = @newStatus
        WHERE UserID = @userId;

        -- 通知用户账户状态已更改 (插入系统通知 - SQL语句4)
        DECLARE @notificationTitle NVARCHAR(200);
        DECLARE @notificationContent NVARCHAR(MAX);

        IF @newStatus = 'Disabled'
        BEGIN
            SET @notificationTitle = '您的账户状态已被更改为禁用';
            SET @notificationContent = '您的账户已被管理员禁用。如有疑问，请联系平台客服。'; -- 移除 GUID
        END
        ELSE -- @newStatus = 'Active'
        BEGIN
             SET @notificationTitle = '您的账户状态已被更改为活跃';
            SET @notificationContent = '您的账户已被管理员重新启用。'; -- 移除 GUID
        END

        INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
        VALUES (NEWID(), @userId, @notificationTitle, @notificationContent, GETDATE(), 0);


        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句5, 面向UI)
        SELECT '用户状态更新成功。' AS 结果, @userId AS 用户ID, @newStatus AS 新状态;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_AdjustUserCredit: 管理员手动调整用户信用分
-- 输入: @userId UNIQUEIDENTIFIER, @creditAdjustment INT (调整的数值，正数增加，负数减少), @adminId UNIQUEIDENTIFIER, @reason NVARCHAR(500)
-- 逻辑: 检查管理员权限，检查用户是否存在，根据调整值更新信用分，确保在0-100范围内。记录操作（可选）。
DROP PROCEDURE IF EXISTS [sp_AdjustUserCredit];
GO
CREATE PROCEDURE [sp_AdjustUserCredit]
    @userId UNIQUEIDENTIFIER,
    @creditAdjustment INT, -- 正数增加，负数减少
    @adminId UNIQUEIDENTIFIER,
    @reason NVARCHAR(500)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @adminIsStaff BIT;
    DECLARE @userExists BIT;
    DECLARE @currentCredit INT;
    DECLARE @newCredit INT;

    -- 检查 @adminId 是否为管理员 (SQL语句1)
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以调整用户信用分。', 16, 1);
        RETURN;
    END

    -- 检查用户是否存在并获取当前信用分 (SQL语句2)
    SELECT @userExists = 1, @currentCredit = Credit FROM [User] WHERE UserID = @userId;
    IF @userExists IS NULL
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

     -- 检查调整原因是否为空 (控制流 IF)
     IF @reason IS NULL OR LTRIM(RTRIM(@reason)) = ''
     BEGIN
          RAISERROR('调整信用分必须提供原因。', 16, 1);
          RETURN;
     END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 计算新的信用分，并确保在0-100范围内 (控制流 CASE)
        SET @newCredit = @currentCredit + @creditAdjustment;
        SET @newCredit = CASE WHEN @newCredit > 100 THEN 100 WHEN @newCredit < 0 THEN 0 ELSE @newCredit END;

        -- 如果信用分没有变化，直接返回 (控制流 IF)
        IF @newCredit = @currentCredit
        BEGIN
             -- PRINT '用户信用分没有变化，无需更新。'; -- 可选提示
             COMMIT TRANSACTION; -- 虽然没有更新，但也应提交事务
             SELECT '用户信用分没有变化，无需更新。' AS 结果, @userId AS 用户ID, @newCredit AS 当前信用分;
             RETURN;
        END

        -- 更新用户信用分 (SQL语句3)
        UPDATE [User]
        SET Credit = @newCredit
        WHERE UserID = @userId;

        -- TODO: 记录信用分调整日志（例如到单独的审计表 - 在应用层或单独SP）
        -- INSERT INTO [CreditAdjustmentLog] (LogID, UserID, AdminID, Adjustment, NewCredit, Reason, AdjustmentTime)
        -- VALUES (NEWID(), @userId, @adminId, @creditAdjustment, @newCredit, @reason, GETDATE());

        -- 通知用户信用分已被调整 (插入系统通知 - SQL语句4)
        DECLARE @notificationTitle NVARCHAR(200) = '您的信用分已被调整';
        DECLARE @notificationContent NVARCHAR(MAX) = '您的信用分已从 ' + CAST(@currentCredit AS NVARCHAR(10)) + ' 调整为 ' + CAST(@newCredit AS NVARCHAR(10)) + '。原因: ' + @reason;

        INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
        VALUES (NEWID(), @userId, @notificationTitle, @notificationContent, GETDATE(), 0);


        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句5, 面向UI)
        SELECT '用户信用分调整成功。' AS 结果, @userId AS 用户ID, @newCredit AS 新信用分;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_ProcessReport: 管理员处理举报
-- 输入: @reportId UNIQUEIDENTIFIER, @adminId UNIQUEIDENTIFIER, @newStatus NVARCHAR(20) ('Resolved'或'Rejected'), @processingResult NVARCHAR(500)
-- 逻辑: 检查管理员权限，检查举报是否存在且为 'Pending' 状态。更新 Report 表。根据举报类型和处理结果，执行相应的操作（禁用用户/下架商品/扣信用分等）。通知相关方。
DROP PROCEDURE IF EXISTS [sp_ProcessReport];
GO
CREATE PROCEDURE [sp_ProcessReport]
    @reportId UNIQUEIDENTIFIER,
    @adminId UNIQUEIDENTIFIER,
    @newStatus NVARCHAR(20), -- 'Resolved' 或 'Rejected'
    @processingResult NVARCHAR(500)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @adminIsStaff BIT;
    DECLARE @reportExists BIT;
    DECLARE @currentStatus NVARCHAR(20);
    DECLARE @reporterUserId UNIQUEIDENTIFIER; -- 添加举报者ID
    DECLARE @reportedUserId UNIQUEIDENTIFIER;
    DECLARE @reportedProductId UNIQUEIDENTIFIER;
    -- DECLARE @reportedOrderId UNIQUEIDENTIFIER; -- 虽然举报表有 ReportdOrderID，但通常不直接处理订单，而是处理与订单相关的用户或商品

    -- 检查 @adminId 是否为管理员 (SQL语句1)
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以处理举报。', 16, 1);
        RETURN;
    END

    -- 检查 @newStatus 是否有效 (控制流 IF)
    IF @newStatus NOT IN ('Resolved', 'Rejected')
    BEGIN
        RAISERROR('无效的举报处理状态，必须是 Resolved 或 Rejected。', 16, 1);
        RETURN;
    END

    -- 检查举报是否存在并获取当前状态、举报者和被举报对象 (SQL语句2)
    SELECT @reportExists = 1, @currentStatus = ProcessingStatus, @reporterUserId = ReporterUserID, @reportedUserId = ReportedUserID, @reportedProductId = ReportedProductID--, @reportedOrderId = ReportedOrderID
    FROM [Report]
    WHERE ReportID = @reportId;

    IF @reportExists IS NULL
    BEGIN
        RAISERROR('举报不存在。', 16, 1);
        RETURN;
    END

    IF @currentStatus != 'Pending'
    BEGIN
        -- RAISERROR('举报当前状态 (%s) 不允许处理。', 16, 1, @currentStatus);
        SELECT '举报当前状态为 ' + @currentStatus + '，不允许再次处理。' AS 结果, @reportId AS 举报ID, @currentStatus AS 当前状态;
        RETURN;
    END

    -- 检查处理结果描述是否为空 (控制流 IF)
     IF @processingResult IS NULL OR LTRIM(RTRIM(@processingResult)) = ''
     BEGIN
          RAISERROR('处理举报必须提供结果描述。', 16, 1);
          RETURN;
     END


    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 更新 Report 表 (SQL语句3)
        UPDATE [Report]
        SET
            ProcessingStatus = @newStatus,
            ProcessorAdminID = @adminId,
            ProcessingTime = GETDATE(),
            ProcessingResult = @processingResult
        WHERE ReportID = @reportId;

        -- 5. 根据举报类型和处理结果，执行相应的操作（通常在应用层调用其他SP）：
        IF @newStatus = 'Resolved' -- 如果举报被认定有效
        BEGIN
            -- 处理被举报的用户
            IF @reportedUserId IS NOT NULL
            BEGIN
                -- TODO: 在应用层调用其他SP执行对被举报用户的操作，例如禁用或调整信用分
                -- EXEC [sp_ChangeUserStatus] @userId = @reportedUserId, @newStatus = 'Disabled', @adminId = @adminId;
                -- EXEC [sp_AdjustUserCredit] @userId = @reportedUserId, @creditAdjustment = -10, @adminId = @adminId, @reason = '因被举报并查证属实，扣除信用分。';
                 PRINT 'TODO: Execute actions on reported user in application layer.'; -- 打印提示
            END

            -- 处理被举报的商品
            IF @reportedProductId IS NOT NULL
            BEGIN
                -- TODO: 在应用层调用SP或直接更新商品状态为 Withdrawn
                 -- DECLARE @productOwnerId UNIQUEIDENTIFIER;
                 -- SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @reportedProductId;
                 -- IF @productOwnerId IS NOT NULL
                 --    EXEC [sp_WithdrawProduct] @productId = @reportedProductId, @userId = @productOwnerId; -- 或者使用一个不需要ownerId的管理员下架SP
                 -- 或者直接更新状态为 Withdrawn
                UPDATE [Product] SET Status = 'Withdrawn' WHERE ProductID = @reportedProductId; -- (SQL语句4)
                 PRINT 'TODO: Notify product owner in application layer.'; -- 打印提示
            END

            -- TODO: 处理被举报的订单（通常是对订单关联的用户或商品进行处理，在应用层实现）
            -- IF @reportedOrderId IS NOT NULL
            -- BEGIN
            --      PRINT 'TODO: Handle reported order in application layer.';
            -- END
        END -- IF @newStatus = 'Resolved'

        -- 6. 通知举报者和被举报者处理结果 (通过 SystemNotification)。
        -- 通知逻辑通常在应用层根据处理结果和被举报对象类型发送不同的通知。
        PRINT 'TODO: Send notifications to reporter and reported parties in application layer.';

        -- 插入系统通知给举报者 (SQL语句5)
        DECLARE @notificationTitle NVARCHAR(200);
        DECLARE @notificationContent NVARCHAR(MAX);

        SET @notificationTitle = '您的举报有了处理结果';
        SET @notificationContent = '您提交的举报 (ID: ' + CAST(@reportId AS NVARCHAR(36)) + ') 已被管理员处理。结果: ' + CASE @newStatus WHEN 'Resolved' THEN '已解决' ELSE '已驳回' END + '。详情: ' + @processingResult;

        INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
        VALUES (NEWID(), @reporterUserId, @notificationTitle, @notificationContent, GETDATE(), 0);

        -- 如果举报被解决，且存在被举报用户或商品，通知被举报方 (SQL语句6)
        IF @newStatus = 'Resolved'
        BEGIN
            IF @reportedUserId IS NOT NULL
            BEGIN
                 SET @notificationTitle = '您的账户/商品因举报被处理';
                 SET @notificationContent = '管理员已处理涉及您的举报，并采取了相应措施。原因: ' + @processingResult;
                 INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
                 VALUES (NEWID(), @reportedUserId, @notificationTitle, @notificationContent, GETDATE(), 0);
            END
            -- 如果举报的是商品，通知商品所有者
            IF @reportedProductId IS NOT NULL
            BEGIN
                 DECLARE @productOwnerId UNIQUEIDENTIFIER;
                 SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @reportedProductId;
                 IF @productOwnerId IS NOT NULL AND (@reportedUserId IS NULL OR @productOwnerId != @reportedUserId) -- 避免重复通知同一个人
                 BEGIN
                     SET @notificationTitle = '您的商品因举报被处理';
                     SET @notificationContent = '您的商品 (' + CAST(@reportedProductId AS NVARCHAR(36)) + ') 因举报已被下架。原因: ' + @processingResult;
                     INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
                     VALUES (NEWID(), @productOwnerId, @notificationTitle, @notificationContent, GETDATE(), 0);
                 END
            END
        END


        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句 n, 面向UI)
        SELECT '举报处理完成。' AS 结果, @reportId AS 举报ID, @newStatus AS 新状态;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_CreateSystemNotification: 发布系统通知
-- 输入: @adminId UNIQUEIDENTIFIER, @targetUserId UNIQUEIDENTIFIER (NULL表示所有用户), @title NVARCHAR(200), @content NVARCHAR(MAX)
-- 逻辑: 检查管理员权限，检查目标用户是否存在（如果指定），插入 SystemNotification 记录。
DROP PROCEDURE IF EXISTS [sp_CreateSystemNotification];
GO
CREATE PROCEDURE [sp_CreateSystemNotification]
    @adminId UNIQUEIDENTIFIER,
    @targetUserId UNIQUEIDENTIFIER = NULL, -- NULL 表示所有用户
    @title NVARCHAR(200),
    @content NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @adminIsStaff BIT;
    DECLARE @notificationsSent INT = 0; -- 用于记录发送的通知数量

    -- 检查 @adminId 是否为管理员 (SQL语句1)
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以发布系统通知。', 16, 1);
        RETURN;
    END

    -- 检查标题和内容是否为空 (控制流 IF)
     IF @title IS NULL OR LTRIM(RTRIM(@title)) = ''
     BEGIN
          RAISERROR('通知标题不能为空。', 16, 1);
          RETURN;
     END
     IF @content IS NULL OR LTRIM(RTRIM(@content)) = ''
     BEGIN
          RAISERROR('通知内容不能为空。', 16, 1);
          RETURN;
     END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 2. IF @targetUserId IS NULL: 批量插入通知给所有用户 (SQL语句2)
        IF @targetUserId IS NULL
        BEGIN
            INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
            SELECT NEWID(), UserID, @title, @content, GETDATE(), 0
            FROM [User]
            WHERE Status = 'Active'; -- 通常只通知活跃用户，根据需求调整
            SET @notificationsSent = @@ROWCOUNT;
        END
        ELSE -- ELSE: 插入通知给特定用户。
        BEGIN
            -- 检查目标用户是否存在 (SQL语句3)
            IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @targetUserId)
            BEGIN
                RAISERROR('目标用户不存在，无法发送通知。', 16, 1);
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION; -- 如果事务仍在，回滚
                RETURN;
            END

            INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
            VALUES (NEWID(), @targetUserId, @title, @content, GETDATE(), 0); -- (SQL语句4)
            SET @notificationsSent = @@ROWCOUNT;
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句 n, 面向UI)
        SELECT '系统通知发布成功。' AS 结果, @notificationsSent AS 发送数量, @targetUserId AS 目标用户ID; -- 调整了目标用户ID的别名

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- New stored procedure to get all users (for admin)
-- This procedure already exists in 01_user_procedures.sql as sp_GetAllUsers, and its column names have been updated there.
-- We will ensure this one is dropped to avoid duplication and potential conflicts.
DROP PROCEDURE IF EXISTS [sp_GetAllUsers]; 
GO
-- CREATE PROCEDURE [sp_GetAllUsers]
--     @adminId UNIQUEIDENTIFIER -- 需要管理员ID来验证权限
-- AS
-- BEGIN
--     SET NOCOUNT ON;

--     DECLARE @adminIsStaff BIT;

--     -- 检查 @adminId 是否为管理员
--     SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
--     IF @adminIsStaff IS NULL OR @adminIsStaff = 0
--     BEGIN
--         RAISERROR('无权限执行此操作，只有管理员可以查看所有用户。', 16, 1);
--         RETURN;
--     END

--     -- SQL语句涉及1个表，多个SELECT列
--     SELECT
--         UserID AS 用户ID,
--         UserName AS 用户名,
--         Status AS 账户状态,
--         Credit AS 信用分,
--         IsStaff AS 是否管理员,
--         IsSuperAdmin AS 是否超级管理员,
--         IsVerified AS 是否已认证,
--         Major AS 专业,
--         Email AS 邮箱,
--         AvatarUrl AS 头像URL,
--         Bio AS 个人简介,
--         PhoneNumber AS 手机号码,
--         JoinTime AS 注册时间
--     FROM [User];
-- END;
-- GO

-- sp_BatchReviewProducts: 管理员批量审核商品
-- 输入: @productIds NVARCHAR(MAX) (逗号分隔的商品ID字符串), @adminId UNIQUEIDENTIFIER, @newStatus NVARCHAR(20) ('Active'或'Rejected'), @reason NVARCHAR(500) (如果拒绝)
DROP PROCEDURE IF EXISTS [sp_BatchReviewProducts];
GO
CREATE PROCEDURE [sp_BatchReviewProducts]
    @productIds NVARCHAR(MAX),
    @adminId UNIQUEIDENTIFIER,
    @newStatus NVARCHAR(20), -- 'Active' 或 'Rejected'
    @reason NVARCHAR(500) = NULL -- 如果拒绝，提供原因
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @adminIsStaff BIT;
    DECLARE @successCount INT = 0;

    -- 检查 @adminId 对应的用户是否为管理员
    SELECT @adminIsStaff = IsStaff FROM [User] WHERE UserID = @adminId;
    IF @adminIsStaff IS NULL OR @adminIsStaff = 0
    BEGIN
        RAISERROR('无权限执行此操作，只有管理员可以批量审核商品。', 16, 1);
        RETURN;
    END

    -- 检查 @newStatus 是否有效
    IF @newStatus NOT IN ('Active', 'Rejected')
    BEGIN
        RAISERROR('无效的审核状态，状态必须是 Active 或 Rejected。', 16, 1);
        RETURN;
    END

     -- 如果状态是 Rejected 但未提供原因
    IF @newStatus = 'Rejected' AND (@reason IS NULL OR LTRIM(RTRIM(@reason)) = '')
    BEGIN
         RAISERROR('拒绝商品必须提供原因。', 16, 1);
         RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 使用临时表或表变量来存储解析后的 ProductID
        DECLARE @ProductIDsTable TABLE (ProductID UNIQUEIDENTIFIER);

        -- 解析逗号分隔的 @productIds 字符串并插入临时表
        -- 这部分可以使用 STRING_SPLIT 函数 (SQL Server 2016及以上) 或自定义解析逻辑
        -- 假设使用 STRING_SPLIT
        INSERT INTO @ProductIDsTable (ProductID)
        SELECT TRY_CAST(value AS UNIQUEIDENTIFIER)
        FROM STRING_SPLIT(@productIds, ',')
        WHERE TRY_CAST(value AS UNIQUEIDENTIFIER) IS NOT NULL; -- 忽略无效的UUID字符串

        -- 更新符合条件的商品状态
        UPDATE P
        SET
            Status = @newStatus,
            AuditReason = CASE WHEN @newStatus = 'Rejected' THEN @reason ELSE NULL END -- 只有拒绝时设置原因，通过时清除
        FROM [Product] P
        JOIN @ProductIDsTable T ON P.ProductID = T.ProductID
        WHERE P.Status = 'PendingReview'; -- 只处理待审核状态的商品

        -- 获取成功更新的商品数量
        SET @successCount = @@ROWCOUNT;

        -- 插入系统通知 (批量通知)
        -- 可以为每个成功审核的商品发送通知，或者发送一个批量通知
        -- 批量通知需要获取这些商品的OwnerID和ProductName
        INSERT INTO [SystemNotification] (NotificationID, UserID, Title, Content, CreateTime, IsRead)
        SELECT
            NEWID(),
            P.OwnerID,
            CASE
                WHEN @newStatus = 'Active' THEN N'商品批量审核通过'
                WHEN @newStatus = 'Rejected' THEN N'商品批量审核未通过'
            END,
            CASE
                WHEN @newStatus = 'Active' THEN N'您的部分商品已批量审核通过，当前状态为 Active (在售)。商品ID: ' + STRING_AGG(CAST(P.ProductID AS NVARCHAR(36)), ', ') WITHIN GROUP (ORDER BY P.ProductID) -- 聚合商品ID
                WHEN @newStatus = 'Rejected' THEN N'您的部分商品未通过批量审核，状态为 Rejected (已拒绝)。原因: ' + ISNULL(@reason, N'未说明') + N'。商品ID: ' + STRING_AGG(CAST(P.ProductID AS NVARCHAR(36)), ', ') WITHIN GROUP (ORDER BY P.ProductID)
            END,
            GETDATE(),
            0
        FROM [Product] P
        JOIN @ProductIDsTable T ON P.ProductID = T.ProductID -- 仅为本次处理的商品创建通知
        WHERE P.Status = @newStatus -- 只通知那些状态确实被改变了的商品 (已从PendingReview变为新状态)
        GROUP BY P.OwnerID; -- 按OwnerID分组，为每个OwnerID发送一条聚合通知


        COMMIT TRANSACTION;

        -- 返回成功处理的数量
        SELECT @successCount AS 成功数量;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO 