/*
 * 聊天消息相关存储过程
 */

-- sp_SendMessage: 发送消息
-- 输入: @senderId UNIQUEIDENTIFIER, @receiverId UNIQUEIDENTIFIER, @productId UNIQUEIDENTIFIER, @content NVARCHAR(MAX), @conversationIdentifier UNIQUEIDENTIFIER
-- 逻辑: 检查发送者和接收者是否存在，检查商品是否存在。插入 ChatMessage 记录。
DROP PROCEDURE IF EXISTS [sp_SendMessage];
GO
CREATE PROCEDURE [sp_SendMessage]
    @senderId UNIQUEIDENTIFIER,
    @receiverId UNIQUEIDENTIFIER,
    @productId UNIQUEIDENTIFIER,
    @content NVARCHAR(MAX),
    @conversationIdentifier UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    -- 1. 检查发送者和接收者是否存在 (SQL语句1 - SELECT)
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @senderId)
    BEGIN
        RAISERROR('发送者用户不存在。', 16, 1);
        RETURN;
    END
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @receiverId)
    BEGIN
        RAISERROR('接收者用户不存在。', 16, 1);
        RETURN;
    END

    -- 2. 检查商品是否存在 (所有聊天都以产品为中心) (SQL语句2 - SELECT)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('关联的商品不存在。', 16, 1);
        RETURN;
    END

    -- 检查内容是否为空 (控制流 IF)
    IF @content IS NULL OR LTRIM(RTRIM(@content)) = ''
    BEGIN
        RAISERROR('消息内容不能为空。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        DECLARE @messageId UNIQUEIDENTIFIER = NEWID();

        -- 3. 插入 ChatMessage 记录 (SQL语句3 - INSERT)
        INSERT INTO [ChatMessage] (
            MessageID,
            ConversationIdentifier,
            SenderID,
            ReceiverID,
            ProductID,
            Content,
            SendTime,
            IsRead,
            SenderVisible,
            ReceiverVisible
        )
        VALUES (
            @messageId,
            @conversationIdentifier,
            @senderId,
            @receiverId,
            @productId,
            @content,
            GETDATE(),
            0, -- 新消息默认未读
            1, -- 发送者可见
            1  -- 接收者可见
        );

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息（可选）(SQL语句4 - SELECT, 面向UI)
        SELECT '消息发送成功' AS Result, @messageId AS NewMessageID; -- 返回新消息ID

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_GetChatMessagesByProduct: 获取某个商品相关的所有聊天记录
-- 输入: @productId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (用于验证请求者是参与者，并且可以筛选只看自己相关的消息，如果需要)
-- 输出: 聊天消息列表
DROP PROCEDURE IF EXISTS [sp_GetChatMessagesByProduct];
GO
CREATE PROCEDURE [sp_GetChatMessagesByProduct]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER = NULL -- 可选用户ID，用于验证权限或筛选消息
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查商品是否存在 (SQL语句1)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('商品不存在。', 16, 1);
        RETURN;
    END;

    -- 检查请求用户是否有权限查看此商品的聊天记录 (即是商品所有者或聊天参与者)
    DECLARE @productOwnerId UNIQUEIDENTIFIER;
    SELECT @productOwnerId = OwnerID FROM [Product] WHERE ProductID = @productId;

    IF @userId IS NOT NULL AND @productOwnerId IS NOT NULL AND @userId != @productOwnerId -- 如果用户不是商品所有者
    BEGIN
         -- 检查用户是否是与该商品有聊天记录的参与者之一 (发送者或接收者)
         IF NOT EXISTS (SELECT 1 FROM [ChatMessage] WHERE ProductID = @productId AND (SenderID = @userId OR ReceiverID = @userId))
         BEGIN
             RAISERROR('无权查看此商品的聊天记录。', 16, 1);
             RETURN;
         END
    END

    -- 获取消息列表 (SQL语句5)
    -- 将列名改为 PascalCase，并添加中文别名
    SELECT
        M.MessageID AS 消息ID,
        M.SenderID AS 发送者ID,
        S.UserName AS 发送者用户名,
        M.ReceiverID AS 接收者ID,
        R.UserName AS 接收者用户名,
        M.ProductID AS 商品ID,
        M.Content AS 内容,
        M.SendTime AS 发送时间,
        M.IsRead AS 是否已读,
        M.SenderVisible AS 发送者可见,
        M.ReceiverVisible AS 接收者可见
    FROM [ChatMessage] M -- 使用 ChatMessage 表
    JOIN [User] S ON M.SenderID = S.UserID -- JOIN User 表获取发送者用户名
    JOIN [User] R ON M.ReceiverID = R.UserID -- JOIN User 表获取接收者用户名
    WHERE M.ProductID = @productId
    AND ((M.SenderID = @userId AND M.SenderVisible = 1) OR (M.ReceiverID = @userId AND M.ReceiverVisible = 1)) --删除聊天记录
    ORDER BY M.SendTime ASC;
END;
GO

-- sp_MarkMessageAsRead: 标记消息为已读
-- 输入: @messageId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (接收者ID)
-- 逻辑: 检查消息是否存在，确保是接收者在标记，更新 IsRead 状态。
DROP PROCEDURE IF EXISTS [sp_MarkMessageAsRead];
GO
CREATE PROCEDURE [sp_MarkMessageAsRead]
    @messageId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    -- SET XACT_ABORT ON; -- 可选

    DECLARE @receiverId UNIQUEIDENTIFIER;
    DECLARE @isRead BIT;

    -- 检查消息是否存在且未读 (SQL语句1)
    SELECT @receiverId = ReceiverID, @isRead = IsRead
    FROM [ChatMessage]
    WHERE MessageID = @messageId;

    IF @receiverId IS NULL
    BEGIN
        RAISERROR('消息不存在。', 16, 1);
        RETURN;
    END

    IF @receiverId != @userId
    BEGIN
        RAISERROR('无权标记此消息为已读。', 16, 1);
        RETURN;
    END

    IF @isRead = 1
    BEGIN
        -- 消息已是已读状态，无需操作
        -- RAISERROR('消息已是已读状态。', 16, 1); -- 可选，如果需要提示
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 更新 IsRead 状态 (SQL语句2)
        UPDATE [ChatMessage]
        SET IsRead = 1
        WHERE MessageID = @messageId;

        COMMIT TRANSACTION;

        -- 返回成功消息（可选）(SQL语句3)
        SELECT @messageId AS MarkedAsReadMessageID, '消息标记为已读成功' AS Result;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_SetChatMessageVisibility: 设置聊天消息对发送者或接收者的可见性（逻辑删除）
-- 输入: @messageId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (操作者ID), @visibleTo NVARCHAR(10) ('sender' 或 'receiver' 或 'both'), @isVisible BIT
-- 逻辑: 检查消息是否存在，检查操作者是否有权限（是发送者或接收者），根据 @visibleTo 更新相应的 Visible 字段。
DROP PROCEDURE IF EXISTS [sp_SetChatMessageVisibility];
GO
CREATE PROCEDURE [sp_SetChatMessageVisibility]
    @messageId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER,
    @visibleTo NVARCHAR(10), -- 'sender', 'receiver', 'both'
    @isVisible BIT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    DECLARE @senderId UNIQUEIDENTIFIER;
    DECLARE @receiverId UNIQUEIDENTIFIER;

    -- 检查消息是否存在并获取发送者和接收者ID (SQL语句1)
    SELECT @senderId = SenderID, @receiverId = ReceiverID
    FROM [ChatMessage]
    WHERE MessageID = @messageId;

    IF @senderId IS NULL
    BEGIN
        RAISERROR('消息不存在。', 16, 1);
        RETURN;
    END

    -- 检查操作者是否有权限 (必须是发送者或接收者) (控制流 IF)
    IF @userId != @senderId AND @userId != @receiverId
    BEGIN
        RAISERROR('无权修改此消息的可见性。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 根据 @visibleTo 和 @userId 更新可见性字段 (控制流 IF/CASE)
        IF @visibleTo = 'sender' AND @userId = @senderId -- 只能修改自己的可见性
        BEGIN
            UPDATE [ChatMessage]
            SET SenderVisible = @isVisible
            WHERE MessageID = @messageId;
        END
        ELSE IF @visibleTo = 'receiver' AND @userId = @receiverId -- 只能修改自己的可见性
        BEGIN
            UPDATE [ChatMessage]
            SET ReceiverVisible = @isVisible
            WHERE MessageID = @messageId;
        END
        ELSE IF @visibleTo = 'both' AND (@userId = @senderId OR @userId = @receiverId) -- 允许发送者或接收者标记对双方都不可见（彻底删除视角）
        BEGIN
             UPDATE [ChatMessage]
             SET SenderVisible = @isVisible, ReceiverVisible = @isVisible
             WHERE MessageID = @messageId;
        END
        ELSE
        BEGIN
            RAISERROR('无效的可见性设置目标或无权操作。', 16, 1);
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION; RETURN;
        END

        -- 检查更新是否成功 (控制流 IF) - 如果没有行受影响，可能是消息已是目标状态
         -- IF @@ROWCOUNT = 0 AND (@visibleTo = 'sender' OR @visibleTo = 'receiver')
         -- BEGIN
         --      PRINT '消息可见性状态没有变化。'; -- 可选提示
         -- END

        COMMIT TRANSACTION; -- 提交事务

        -- 返回成功消息（可选）(SQL语句2)
        SELECT '消息可见性更新成功。' AS Result, @messageId AS MessageID, @visibleTo AS UpdatedTarget, @isVisible AS NewVisibility;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO