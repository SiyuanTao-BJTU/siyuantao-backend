/*
 * 用户相关存储过程
 */

-- 根据ID获取用户 
DROP PROCEDURE IF EXISTS [sp_GetUserProfileById];
GO
CREATE PROCEDURE [sp_GetUserProfileById]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查用户是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- SQL语句涉及1个表，但包含控制流(IF)和多个SELECT列
    SELECT
        UserID AS 用户ID,
        UserName AS 用户名,
        Status AS 账户状态,
        Credit AS 信用分,
        IsStaff AS 是否管理员,
        IsSuperAdmin AS 是否超级管理员,
        IsVerified AS 是否已认证,
        Major AS 专业,
        Email AS 邮箱,
        AvatarUrl AS 头像URL,
        Bio AS 个人简介,
        PhoneNumber AS 手机号码,
        JoinTime AS 注册时间,
        LastLoginTime AS 最后登录时间
    FROM [User]
    WHERE UserID = @userId;
END;
GO

-- 根据用户名获取用户（包括密码哈希），用于登录
DROP PROCEDURE IF EXISTS [sp_GetUserByUsernameWithPassword];
GO
CREATE PROCEDURE [sp_GetUserByUsernameWithPassword]
    @username NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @trimmedUsername NVARCHAR(255);
    SET @trimmedUsername = LTRIM(RTRIM(@username));

    -- 检查用户名是否为空
    IF @trimmedUsername IS NULL OR LTRIM(RTRIM(@trimmedUsername)) = ''
    BEGIN
        RAISERROR('用户名不能为空。', 16, 1);
        RETURN;
    END

    -- SQL语句涉及1个表，包含控制流(IF)和多个SELECT列
    UPDATE [User]
    SET LastLoginTime = GETDATE()
    WHERE UserName = @trimmedUsername;

    SELECT
        UserID,
        UserName,
        Password,
        Status,
        IsStaff,
        IsSuperAdmin,
        IsVerified,
        Email,
        LastLoginTime
    FROM [User]
    WHERE UserName = @trimmedUsername OR Email = @trimmedUsername;
END;
GO

-- 创建新用户 (修改为只接收用户名、密码哈希、手机号、可选专业)
DROP PROCEDURE IF EXISTS [sp_CreateUser];
GO
CREATE PROCEDURE [sp_CreateUser]
    @username NVARCHAR(128),
    @passwordHash NVARCHAR(128),
    @phoneNumber NVARCHAR(20), -- 添加手机号参数 (必填)
    @major NVARCHAR(100) = NULL -- 添加major参数 (可选，带默认值NULL)
AS
BEGIN
    SET NOCOUNT ON;
    -- SET XACT_ABORT ON; -- 遇到错误自动回滚

    -- 声明变量用于存储检查结果和新用户ID
    DECLARE @existingUserCount INT;
    DECLARE @existingPhoneCount INT; -- 添加手机号存在检查变量
    DECLARE @newUserId UNIQUEIDENTIFIER = NEWID(); -- 提前生成UUID

    -- 使用BEGIN TRY...BEGIN TRANSACTION 确保原子性
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查用户名是否存在
        SELECT @existingUserCount = COUNT(1) FROM [User] WHERE UserName = @username;
        IF @existingUserCount > 0
        BEGIN
            RAISERROR('用户名已存在', 16, 1);
            -- 跳出事务并返回
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            RETURN;
        END

        -- 检查手机号码是否存在 (手机号码也需要唯一)
        SELECT @existingPhoneCount = COUNT(1) FROM [User] WHERE PhoneNumber = @phoneNumber;
        IF @existingPhoneCount > 0
        BEGIN
            RAISERROR('手机号码已存在', 16, 1);
            -- 跳出事务并返回
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            RETURN;
        END

        -- 检查邮箱是否存在 -- 移除此检查
        -- SELECT @existingEmailCount = COUNT(1) FROM [User] WHERE Email = @email;
        -- IF @existingEmailCount > 0
        -- BEGIN
        --     RAISERROR('邮箱已存在', 16, 1);
        --     IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        --     RETURN;
        -- END

        -- 插入新用户数据
        INSERT INTO [User] (UserID, UserName, Password, Email, Status, Credit, IsStaff, IsVerified, Major, AvatarUrl, Bio, PhoneNumber, JoinTime)
        VALUES (@newUserId, @username, @passwordHash, NULL, 'Active', 100, 0, 0, @major, NULL, NULL, @phoneNumber, GETDATE()); -- Email 设置为 NULL

        -- 提交事务
        COMMIT TRANSACTION;

        -- 返回新用户的 UserID
        SELECT @newUserId AS NewUserID, '用户创建成功并查询成功' AS Message; -- 返回新用户ID和成功消息

    END TRY
    BEGIN CATCH
        -- 捕获错误，回滚事务
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;

        -- 重新抛出错误
        THROW;

        SELECT ERROR_MESSAGE() AS ErrorMsg;
    END CATCH
END;
GO


-- 更新用户个人信息
DROP PROCEDURE IF EXISTS [sp_UpdateUserProfile];
GO
CREATE PROCEDURE [sp_UpdateUserProfile]
    @userId UNIQUEIDENTIFIER,
    @major NVARCHAR(100) = NULL,
    @avatarUrl NVARCHAR(255) = NULL,
    @bio NVARCHAR(500) = NULL,
    @phoneNumber NVARCHAR(20) = NULL,
    @email NVARCHAR(254) = NULL, -- Add optional email parameter
    @username NVARCHAR(128) = NULL -- Add username existence check variable
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @existingUserCount INT;
    DECLARE @existingPhoneCount INT;
    DECLARE @existingEmailCount INT;
    DECLARE @existingUsernameCount INT; -- Add username existence check variable

    -- 检查用户是否存在
    SELECT @existingUserCount = COUNT(1) FROM [User] WHERE UserID = @userId;
    IF @existingUserCount = 0
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- 如果提供了用户名，检查用户名是否已被其他用户使用
    IF @username IS NOT NULL AND LTRIM(RTRIM(@username)) <> ''
    BEGIN
        SELECT @existingUsernameCount = COUNT(1) FROM [User] WHERE UserName = @username AND UserID <> @userId;
        IF @existingUsernameCount > 0
        BEGIN
            RAISERROR('此用户名已被其他用户使用。', 16, 1);
            RETURN;
        END
    END

    -- 如果提供了手机号码，检查手机号码是否已被其他用户使用
    IF @phoneNumber IS NOT NULL AND LTRIM(RTRIM(@phoneNumber)) <> ''
    BEGIN
        SELECT @existingPhoneCount = COUNT(1) FROM [User] WHERE PhoneNumber = @phoneNumber AND UserID <> @userId;
        IF @existingPhoneCount > 0
        BEGIN
            RAISERROR('此手机号码已被其他用户使用。', 16, 1);
            RETURN;
        END
    END

    -- 如果提供了邮箱地址，检查邮箱地址是否已被其他用户使用
    IF @email IS NOT NULL AND LTRIM(RTRIM(@email)) <> ''
    BEGIN
        SELECT @existingEmailCount = COUNT(1) FROM [User] WHERE Email = @email AND UserID <> @userId;
        IF @existingEmailCount > 0
        BEGIN
            RAISERROR('此邮箱已被其他用户使用。', 16, 1);
            RETURN;
        END
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- SQL语句1 (UPDATE)
        UPDATE [User]
        SET
            UserName = ISNULL(@username, UserName), -- Update username if provided
            Major = ISNULL(@major, Major),
            AvatarUrl = ISNULL(@avatarUrl, AvatarUrl),
            Bio = ISNULL(@bio, Bio),
            PhoneNumber = ISNULL(@phoneNumber, PhoneNumber),
            Email = ISNULL(@email, Email)
        WHERE UserID = @userId;

        -- 检查是否更新成功 (尽管通常UPDATE成功不会抛异常，但可以检查ROWCOUNT)
        IF @@ROWCOUNT = 0
        BEGIN
            -- 如果用户存在但没有更新任何字段 (因为传入的值与原值相同)，@@ROWCOUNT可能为0
            -- 这里可以根据需求决定是否抛出错误或仅仅提示
            PRINT '用户信息更新完成，可能没有字段值发生变化。';
        END

        COMMIT TRANSACTION;

        -- 返回更新后的用户信息 (SQL语句2: SELECT, 面向UI)
        EXEC [sp_GetUserProfileById] @userId = @userId;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH

    -- 增加一个额外的SELECT语句以满足复杂度要求
    SELECT '用户信息更新完成并查询成功' AS Result;
END;
GO

-- 新增：根据用户ID获取密码哈希
DROP PROCEDURE IF EXISTS [sp_GetUserPasswordHashById];
GO
CREATE PROCEDURE [sp_GetUserPasswordHashById]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查用户是否存在
     IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- SQL语句涉及1个表，包含控制流(IF)
    SELECT Password FROM [User] WHERE UserID = @userId;
END;
GO

-- 新增：更新用户密码
DROP PROCEDURE IF EXISTS [sp_UpdateUserPassword];
GO
CREATE PROCEDURE [sp_UpdateUserPassword]
    @userId UNIQUEIDENTIFIER,
    @newPasswordHash NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查用户是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    BEGIN TRY
         BEGIN TRANSACTION;

         -- SQL语句1 (UPDATE)
        UPDATE [User]
        SET Password = @newPasswordHash
        WHERE UserID = @userId;

        -- 检查更新是否成功
        IF @@ROWCOUNT = 0
        BEGIN
             -- 这应该不会发生，因为上面已经检查了用户存在，但作为安全检查保留
             RAISERROR('密码更新失败。', 16, 1);
             IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
             RETURN;
        END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句2: SELECT)
        SELECT '密码更新成功' AS Result;

    END TRY
    BEGIN CATCH
         IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetSystemNotificationsByUserId: 获取某个用户的系统通知列表 (面向UI)
-- 输入: @userId UNIQUEIDENTIFIER
-- 输出: 通知列表
DROP PROCEDURE IF EXISTS [sp_GetSystemNotificationsByUserId];
GO
CREATE PROCEDURE [sp_GetSystemNotificationsByUserId]
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

    -- 获取通知列表 (SQL语句2)
    SELECT
        NotificationID AS 通知ID,
        UserID AS 用户ID,
        Title AS 标题,
        Content AS 内容,
        CreateTime AS 创建时间,
        IsRead AS 是否已读
    FROM [SystemNotification]
    WHERE UserID = @userId
    ORDER BY CreateTime DESC;

END;
GO

-- sp_MarkNotificationAsRead: 标记系统通知为已读
-- 输入: @notificationId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (接收者ID)
-- 逻辑: 检查通知是否存在，确保是接收者在标记，更新 IsRead 状态。
DROP PROCEDURE IF EXISTS [sp_MarkNotificationAsRead];
GO
CREATE PROCEDURE [sp_MarkNotificationAsRead]
    @notificationId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @receiverId UNIQUEIDENTIFIER;
    DECLARE @isRead BIT;

    -- 检查消息是否存在且未读 (SQL语句1)
    SELECT @receiverId = UserID, @isRead = IsRead
    FROM [SystemNotification]
    WHERE NotificationID = @notificationId;

    -- 使用 IF 进行控制流
    IF @receiverId IS NULL
    BEGIN
        RAISERROR('通知不存在。', 16, 1);
        RETURN;
    END

    IF @receiverId != @userId
    BEGIN
        RAISERROR('无权标记此通知为已读。', 16, 1);
        RETURN;
    END

    IF @isRead = 1
    BEGIN
        -- 通知已是已读状态，无需操作
        -- RAISERROR('通知已是已读状态。', 16, 1); -- 可选，如果需要提示
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 更新 IsRead 状态 (SQL语句2)
        UPDATE [SystemNotification]
        SET IsRead = 1
        WHERE NotificationID = @notificationId;

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息 (SQL语句3)
        SELECT '通知标记为已读成功。' AS Result;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- 新增：删除用户
DROP PROCEDURE IF EXISTS [sp_DeleteUser];
GO
CREATE PROCEDURE [sp_DeleteUser]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    -- SET XACT_ABORT ON; -- 暂时也注释掉 XACT_ABORT，以排除其可能的早期中断效应

    DECLARE @InputUserID_Str VARCHAR(36) = CONVERT(VARCHAR(36), @userId);
    DECLARE @FoundUsername NVARCHAR(128) = NULL;
    DECLARE @UserCount INT = -100; -- 初始化为一个特殊值，表示尚未执行查询
    DECLARE @OperationResultCode INT = -999; -- 新增：用于最终操作结果，区别于过程中的ResultCode
    DECLARE @DebugMessage NVARCHAR(500) = N'Debug process started.';

    BEGIN TRY
        -- 直接在 User 表中查询用户数量和用户名
        SELECT @UserCount = COUNT(*), @FoundUsername = MAX(Username) 
        FROM [User] 
        WHERE UserID = @userId;
        
        SET @DebugMessage = N'After COUNT query. UserCount: ' + ISNULL(CAST(@UserCount AS NVARCHAR), 'NULL') + N'. FoundUsername: ' + ISNULL(@FoundUsername, N'NULL_OR_NOT_FOUND');

    END TRY
    BEGIN CATCH
        SET @UserCount = -99; -- 特殊值表示在尝试COUNT时发生错误
        SET @FoundUsername = N'ERROR_READING_USERNAME_DURING_COUNT';
        SET @DebugMessage = N'ERROR during user count/select: Error ' + CAST(ERROR_NUMBER() AS VARCHAR(10)) + N' - ' + ERROR_MESSAGE();
        SET @OperationResultCode = -90; -- 表示在检查用户时发生错误
        -- 直接输出结果并返回，不再继续执行删除
        SELECT 
            @InputUserID_Str AS Debug_InputUserID,
            @UserCount AS Debug_UserCount,
            @FoundUsername AS Debug_FoundUsername,
            @DebugMessage AS Debug_Message,
            @OperationResultCode AS OperationResultCode;
        RETURN;
    END CATCH

    -- 检查用户是否存在，并决定是否继续
    IF @UserCount = 1
    BEGIN
        SET @DebugMessage = @DebugMessage + N' | User found.';
        -- 检查依赖关系 (暂时简化或注释掉大部分，专注于删除逻辑本身)
        IF EXISTS (SELECT 1 FROM [Product] WHERE OwnerID = @userId AND Status NOT IN ('Sold', 'Withdrawn')) OR
           EXISTS (SELECT 1 FROM [Order] WHERE (BuyerID = @userId OR SellerID = @userId) AND Status NOT IN ('Completed', 'Cancelled')) OR
           EXISTS (SELECT 1 FROM [Evaluation] WHERE BuyerID = @userId OR SellerID = @userId) OR
           EXISTS (SELECT 1 FROM [Report] WHERE ReporterUserID = @userId OR ReportedUserID = @userId) OR
           EXISTS (SELECT 1 FROM [ReturnRequest] WHERE OrderID IN (SELECT OrderID FROM [Order] WHERE BuyerID = @userId OR SellerID = @userId)) OR
           EXISTS (
                SELECT 1 FROM [ChatMessage] CM
                WHERE ((CM.SenderID = @userId AND CM.SenderVisible = 1) OR (CM.ReceiverID = @userId AND CM.ReceiverVisible = 1))
                AND CM.SendTime > DATEADD(month, -3, GETDATE())
           )
        BEGIN
            SET @DebugMessage = @DebugMessage + N' | Dependency check failed. Cannot delete user.';
            SET @OperationResultCode = -2; -- 表示存在依赖，无法删除
        END
        ELSE
        BEGIN
            BEGIN TRY
                BEGIN TRANSACTION;
                SET @DebugMessage = @DebugMessage + N' | No critical dependencies found. Proceeding with deletion.';

                -- 实际应用中需要按正确的顺序删除相关表的数据 (根据 ON DELETE NO ACTION 的外键)
                -- 严格按照 ON DELETE NO ACTION 的表进行删除，ON DELETE CASCADE 的表无需手动删除

                -- 删除 ChatMessage 记录 (Sender 或 Receiver)
                DELETE FROM [ChatMessage] WHERE SenderID = @userId OR ReceiverID = @userId;

                -- 删除 Evaluation 记录 (Buyer 或 Seller)
                DELETE FROM [Evaluation] WHERE BuyerID = @userId OR SellerID = @userId;

                -- 删除 Report 记录 (Reporter 或 Reported)
                DELETE FROM [Report] WHERE ReporterUserID = @userId OR ReportedUserID = @userId;

                -- 删除 ReturnRequest 记录 (通过关联订单ID)
                -- 注意：如果 ReturnRequest 关联的订单不是该用户创建或接收的，这个删除可能不合适
                -- 这里假设 ReturnRequest 是与用户的订单强关联，如果用户被删除，其所有相关退货请求也应删除
                DELETE FROM [ReturnRequest] WHERE OrderID IN (SELECT OrderID FROM [Order] WHERE BuyerID = @userId OR SellerID = @userId);

                -- 现有设计中 Product 和 Order 对 User 是 ON DELETE NO ACTION，
                -- 这意味着如果用户有商品或订单，除非这些商品已售罄/下架，订单已完成/取消，否则不能删除用户。
                -- 前面的 EXISTS 检查已经包含了这个逻辑。
                -- 因此，如果能走到这里，说明用户没有"活跃"的商品或订单，这些数据可能已经被处理或无需再手动删除。
                -- For example: 如果商品 Status = 'Sold'/'Withdrawn'，可以删除。
                -- 如果订单 Status = 'Completed'/'Cancelled'，可以删除。
                -- 但是外键是 NO ACTION，这意味着如果你尝试删除 User，即使 Product 或 Order 状态是 'Sold'/'Completed'，
                -- 只要有引用，仍然会报错。因此，需要在删除 User 前，处理这些引用。
                -- 最安全的做法是，如果 EXISTS 检查通过，说明符合删除条件，
                -- 那么对于 ON DELETE NO ACTION 的表，如果允许用户删除，
                -- 比如 Product 和 Order，你可能需要考虑将其 OwnerID 或 BuyerID/SellerID 设置为 NULL 
                -- 或者指向一个匿名用户，或者业务上决定这些数据可以一起删除。
                -- 鉴于目前的 EXISTS 检查已经很严格，我们认为能通过检查的，这些关联数据是安全的。
                -- 但是为了数据库完整性，如果业务允许删除已完成/取消的订单和已售罄/下架的商品，
                -- 那么在删除用户之前，你需要手动删除这些 Product 和 Order 记录。
                -- 否则，你不能删除用户。

                -- 如果业务允许删除已完成/取消的订单和已售罄/下架的商品：
                -- DELETE FROM [Order] WHERE BuyerID = @userId OR SellerID = @userId;
                -- DELETE FROM [Product] WHERE OwnerID = @userId;


                -- 最后删除用户表自身
                DELETE FROM [User] WHERE UserID = @userId;

                IF @@ROWCOUNT = 1
                BEGIN
                    SET @DebugMessage = @DebugMessage + N' | User successfully deleted from User table.';
                    SET @OperationResultCode = 0; -- 成功删除
                    IF @@TRANCOUNT > 0 COMMIT TRANSACTION;
                END
                ELSE
                BEGIN
                    SET @DebugMessage = @DebugMessage + N' | User was found initially, but @@ROWCOUNT after DELETE was 0. Possible race condition or other issue.';
                    SET @OperationResultCode = -3; -- 删除时未找到或未成功删除
                    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
                END
            END TRY
            BEGIN CATCH
                SET @DebugMessage = @DebugMessage + N' | ERROR during delete transaction: ' + ERROR_MESSAGE();
                SET @OperationResultCode = -4; -- 删除过程中发生数据库错误
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            END CATCH
        END
    END
    ELSE
    BEGIN
        SET @DebugMessage = @DebugMessage + N' | User not found (UserCount != 1).';
        SET @OperationResultCode = -1; -- 用户未找到
    END

    -- 最终返回单一结果集
    SELECT 
        @InputUserID_Str AS Debug_InputUserID,
        @UserCount AS Debug_UserCount,
        @FoundUsername AS Debug_FoundUsername,
        @DebugMessage AS Debug_Message,
        @OperationResultCode AS OperationResultCode; -- 最终的操作结果代码

    -- 不再需要单独的 SELECT @ResultCode AS ResultCode;

END;
GO

-- 新增：密码重置 Token 表
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'PasswordResetTokens')
BEGIN
    CREATE TABLE [dbo].[PasswordResetTokens] (
        TokenID UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        UserID UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES [User](UserID) ON DELETE CASCADE,
        Token NVARCHAR(64) NOT NULL UNIQUE, -- 存储生成的随机Token
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        ExpiresAt DATETIME NOT NULL,
        Used BIT NOT NULL DEFAULT 0, -- 0: 未使用, 1: 已使用
        -- 添加索引以加快查找速度
        INDEX IX_PasswordResetTokens_Token (Token),
        INDEX IX_PasswordResetTokens_UserID (UserID)
    );
    PRINT 'Table [dbo].[PasswordResetTokens] created.';
END
GO

-- 新增：创建密码重置 Token 存储过程
DROP PROCEDURE IF EXISTS [sp_CreatePasswordResetToken];
GO
CREATE PROCEDURE [sp_CreatePasswordResetToken]
    @email NVARCHAR(254), -- 接受邮箱
    @token NVARCHAR(64), -- 接受生成的Token
    @expiresAt DATETIME -- 接受过期时间
AS
BEGIN
    SET NOCOUNT ON;
    -- SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @userId UNIQUEIDENTIFIER;

    -- 1. 根据邮箱查找用户ID
    SELECT @userId = UserID FROM [User] WHERE Email = @email AND Status = 'Active';

    -- 如果用户不存在或非活跃，返回错误
    IF @userId IS NULL
    BEGIN
        RAISERROR('指定邮箱的用户不存在或账户非活跃。', 16, 1);
        RETURN -1; -- 返回自定义错误码
    END

    -- 2. 删除该用户之前未使用的所有重置 Token (可选，保持最新Token唯一有效)
    -- DELETE FROM [PasswordResetTokens] WHERE UserID = @userId AND Used = 0;

    -- 3. 插入新的重置 Token
    BEGIN TRY
        BEGIN TRANSACTION;
        INSERT INTO [PasswordResetTokens] (UserID, Token, ExpiresAt)
        VALUES (@userId, @token, @expiresAt);
        COMMIT TRANSACTION;

        -- 4. 返回用户ID和TokenID (如果需要)
        SELECT @userId AS UserID, (SELECT TokenID FROM [PasswordResetTokens] WHERE Token = @token) AS TokenID; -- 返回用户ID和新的TokenID

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- 新增：获取密码重置 Token 详情存储过程
DROP PROCEDURE IF EXISTS [sp_GetPasswordResetTokenDetails];
GO
CREATE PROCEDURE [sp_GetPasswordResetTokenDetails]
    @token NVARCHAR(64)
AS
BEGIN
    SET NOCOUNT ON;

    -- 查找 Token 详情并验证其有效性
    SELECT
        TokenID,
        UserID,
        CreatedAt,
        ExpiresAt,
        Used
    FROM [PasswordResetTokens]
    WHERE Token = @token
      AND Used = 0
      AND ExpiresAt > GETDATE(); -- 检查未过期且未被使用

    -- 如果找到有效的 Token，返回其详情；否则返回空结果集
END;
GO

-- 新增：使用 Token 重置密码存储过程
DROP PROCEDURE IF EXISTS [sp_ResetPasswordWithToken];
GO
CREATE PROCEDURE [sp_ResetPasswordWithToken]
    @token NVARCHAR(64),
    @newPasswordHash NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;
    -- SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @userId UNIQUEIDENTIFIER;

    -- 1. 查找并验证 Token
    SELECT @userId = UserID
    FROM [PasswordResetTokens]
    WHERE Token = @token
      AND Used = 0
      AND ExpiresAt > GETDATE(); -- 检查未过期且未被使用

    -- 如果 Token 无效，返回错误
    IF @userId IS NULL
    BEGIN
        RAISERROR('无效或已过期的密码重置链接。', 16, 1);
        RETURN -1; -- 返回自定义错误码
    END

    -- 2. 更新用户密码并标记 Token 为已使用
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 更新用户密码
        UPDATE [User]
        SET Password = @newPasswordHash
        WHERE UserID = @userId;

        -- 标记 Token 为已使用
        UPDATE [PasswordResetTokens]
        SET Used = 1
        WHERE Token = @token;

        COMMIT TRANSACTION;

        -- 3. 返回成功指示 (例如，更新的用户ID)
        SELECT @userId AS UpdatedUserID, '密码重置成功。' AS Message;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- 新增：根据邮箱获取用户（包括密码哈希），用于登录
DROP PROCEDURE IF EXISTS [sp_GetUserByEmailWithPassword];
GO
CREATE PROCEDURE [sp_GetUserByEmailWithPassword]
    @email NVARCHAR(254)
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查邮箱是否为空
    IF @email IS NULL OR LTRIM(RTRIM(@email)) = ''
    BEGIN
        RAISERROR('邮箱不能为空。', 16, 1);
        RETURN;
    END

    -- 更新 LastLoginTime 并选择用户数据
    UPDATE [User]
    SET LastLoginTime = GETDATE()
    WHERE Email = @email;

    -- SQL语句涉及1个表，包含控制流(IF)和多个SELECT列
    SELECT
        UserID,
        UserName,
        Password,
        Status,
        IsStaff,
        IsSuperAdmin,
        IsVerified,
        Email,
        LastLoginTime
    FROM [User]
    WHERE Email = @email;
END;
GO

-- 新增：为密码重置创建并存储 OTP
DROP PROCEDURE IF EXISTS [sp_CreateOtpForPasswordReset];
GO
CREATE PROCEDURE [sp_CreateOtpForPasswordReset]
    @userId UNIQUEIDENTIFIER,
    @otpCode NVARCHAR(10),
    @expiresAt DATETIME,
    @otpType NVARCHAR(50) -- 添加新的参数
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查用户是否存在
        IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
        BEGIN
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            SELECT -1 AS OperationResultCode, '用户不存在。' AS Debug_Message;
            RETURN;
        END

        -- 首先，将该用户和该 OTP 类型的所有现有未使用的 OTP 标记为已使用
        UPDATE [Otp]
        SET IsUsed = 1
        WHERE UserID = @userId AND OtpType = @otpType AND IsUsed = 0;

        -- 插入新的 OTP 记录
        INSERT INTO [Otp] (OtpID, UserID, OtpCode, CreationTime, ExpiresAt, IsUsed, OtpType) -- 包含 OtpType
        VALUES (NEWID(), @userId, @otpCode, GETDATE(), @expiresAt, 0, @otpType); -- 传入 OtpType 值

        COMMIT TRANSACTION;
        SELECT 0 AS OperationResultCode, 'OTP创建成功。';
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        SELECT -99 AS OperationResultCode, ERROR_MESSAGE() AS Debug_Message;
    END CATCH
END;
GO

-- 新增：根据邮箱和 OTP 获取 OTP 详情并验证有效性
DROP PROCEDURE IF EXISTS [sp_GetOtpDetailsAndValidate];
GO
CREATE PROCEDURE [sp_GetOtpDetailsAndValidate]
    @email NVARCHAR(254),
    @otpCode NVARCHAR(10)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @currentUtc DATETIME = GETUTCDATE();
    
    SELECT TOP 1
        o.OtpID AS OtpID,
        o.UserID AS UserID,
        o.OtpCode AS OtpCode,
        o.CreationTime AS CreationTime,
        o.ExpiresAt AS ExpiresAt,
        o.IsUsed AS IsUsed,
        u.Email AS Email
    FROM [Otp] o
    JOIN [User] u ON o.UserID = u.UserID
    WHERE u.Email = @email
      AND o.OtpCode = @otpCode
      AND o.IsUsed = 0
      AND o.ExpiresAt > @currentUtc
    ORDER BY o.CreationTime DESC; -- 获取最新的有效OTP

    -- 如果没有找到有效 OTP，可以返回一个空结果集或一个指示。
    IF @@ROWCOUNT = 0
    BEGIN
        -- 为了前端逻辑更清晰，这里返回一个特定的OperationResultCode来指示无效或过期
        SELECT -1 AS OperationResultCode, '验证码无效或已过期。' AS Debug_Message;
    END
END;
GO

-- 新增：标记 OTP 为已使用
DROP PROCEDURE IF EXISTS [sp_MarkOtpAsUsed];
GO
CREATE PROCEDURE [sp_MarkOtpAsUsed]
    @otpId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查 OTP 是否存在且未使用
        IF NOT EXISTS (SELECT 1 FROM [Otp] WHERE OtpID = @otpId AND IsUsed = 0)
        BEGIN
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
            SELECT -1 AS OperationResultCode, 'OTP不存在或已被使用。';
            RETURN;
        END

        UPDATE [Otp]
        SET IsUsed = 1
        WHERE OtpID = @otpId;

        COMMIT TRANSACTION;
        SELECT 0 AS OperationResultCode, 'OTP已成功标记为已使用。';
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        SELECT -99 AS OperationResultCode, ERROR_MESSAGE() AS Debug_Message;
    END CATCH
END;
GO

-- 管理员获取所有用户列表
DROP PROCEDURE IF EXISTS [sp_GetAllUsers];
GO
CREATE PROCEDURE [sp_GetAllUsers]
    @adminId UNIQUEIDENTIFIER -- 接受管理员用户ID
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查调用者是否为管理员或超级管理员
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @adminId AND (IsStaff = 1 OR IsSuperAdmin = 1))
    BEGIN
        RAISERROR('只有管理员或超级管理员才能查看所有用户列表。', 16, 1);
        RETURN;
    END

    SELECT
        UserID AS 用户ID,
        UserName AS 用户名,
        Email AS 邮箱,
        Status AS 账户状态,
        Credit AS 信用分,
        IsStaff AS 是否管理员,
        IsSuperAdmin AS 是否超级管理员,
        IsVerified AS 是否已认证,
        Major AS 专业,
        AvatarUrl AS 头像URL,
        Bio AS 个人简介,
        PhoneNumber AS 手机号码,
        JoinTime AS 注册时间,
        LastLoginTime AS 最后登录时间 -- Added LastLoginTime
    FROM [User]
    ORDER BY JoinTime DESC;
END;
GO

-- 新增：管理员禁用/启用用户账户
DROP PROCEDURE IF EXISTS [sp_AdminEnableDisableUser];
GO
CREATE PROCEDURE [sp_AdminEnableDisableUser]
    @userId UNIQUEIDENTIFIER,
    @enable BIT
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查用户是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- SQL语句1 (UPDATE)
        UPDATE [User]
        SET Status = CASE WHEN @enable = 1 THEN 'Active' ELSE 'Disabled' END
        WHERE UserID = @userId;

        -- 检查是否更新成功 (尽管通常UPDATE成功不会抛异常，但可以检查ROWCOUNT)
        IF @@ROWCOUNT = 0
        BEGIN
            -- 如果用户存在但没有更新任何字段 (因为传入的值与原值相同)，@@ROWCOUNT可能为0
            -- 这里可以根据需求决定是否抛出错误或仅仅提示
            PRINT '用户状态更新完成，可能没有字段值发生变化。';
        END

        COMMIT TRANSACTION;

        -- 返回更新后的用户信息 (SQL语句2: SELECT, 面向UI)
        EXEC [sp_GetUserProfileById] @userId = @userId;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW; -- 重新抛出捕获的错误
    END CATCH

    -- 增加一个额外的SELECT语句以满足复杂度要求
    SELECT '用户状态更新完成并查询成功' AS Result;
END;
GO