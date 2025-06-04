/*
 * 聊天消息相关存储过程
 */

-- sp_SendMessage: 发送消息
-- 输入: @senderId UNIQUEIDENTIFIER, @receiverId UNIQUEIDENTIFIER, @productId UNIQUEIDENTIFIER, @content NVARCHAR(MAX)
-- 逻辑: 检查发送者和接收者是否存在，检查商品是否存在。插入 ChatMessage 记录。
DROP PROCEDURE IF EXISTS [sp_SendMessage];
GO
CREATE PROCEDURE [sp_SendMessage]
    @senderId UNIQUEIDENTIFIER,
    @receiverId UNIQUEIDENTIFIER,
    @productId UNIQUEIDENTIFIER,
    @content NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON; -- 遇到错误自动回滚

    -- 1. 检查发送者和接收者是否存在
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

    -- 2. 检查商品是否存在 (所有聊天都以产品为中心)
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN
        RAISERROR('关联的商品不存在。', 16, 1);
        RETURN;
    END

    -- 检查内容是否为空
     IF @content IS NULL OR LTRIM(RTRIM(@content)) = ''
    BEGIN
        RAISERROR('消息内容不能为空。', 16, 1);
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION; -- 开始事务

        -- 3. 插入 ChatMessage 记录
        INSERT INTO [ChatMessage] (
            MessageID,
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
            NEWID(),
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

        -- 返回成功消息（可选）
        SELECT '消息发送成功' AS Result, @@ROWCOUNT AS AffectedRows;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        THROW; -- 重新抛出捕获的错误
    END CATCH
END;
GO

-- sp_GetUserConversations: 获取用户的所有会话列表（按商品分组，显示最新消息）
-- 输入: @userId UNIQUEIDENTIFIER
-- 输出: 会话列表，包含商品信息、最新消息摘要、最新消息时间、聊天对象信息、未读消息数
DROP PROCEDURE IF EXISTS [sp_GetUserConversations];
GO
CREATE PROCEDURE [sp_GetUserConversations]
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. 检查用户是否存在
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN
        RAISERROR('用户不存在。', 16, 1);
        RETURN;
    END

    -- 2. 获取会话列表
    WITH UserConversations AS (
        SELECT
            CM.ProductID,
            CM.Content,
            CM.SendTime,
            -- 确定聊天对象ID
            CASE
                WHEN CM.SenderID = @userId THEN CM.ReceiverID
                ELSE CM.SenderID
            END AS OtherUserID,
            -- 对每个商品和聊天对象组合，根据最新消息时间排序
            ROW_NUMBER() OVER(PARTITION BY CM.ProductID,
                CASE WHEN CM.SenderID = @userId THEN CM.ReceiverID ELSE CM.SenderID END
                ORDER BY CM.SendTime DESC) AS rn
        FROM [ChatMessage] CM
        WHERE (CM.SenderID = @userId AND CM.SenderVisible = 1) -- 用户发送的，且对用户可见
           OR (CM.ReceiverID = @userId AND CM.ReceiverVisible = 1) -- 用户接收的，且对用户可见
    )
    SELECT
        UC.ProductID AS 商品ID,
        P.ProductName AS 商品名称,
        P.OwnerID AS 商品所有者ID,
        POwner.UserName AS 商品所有者用户名,
        UC.OtherUserID AS 聊天对象ID,
        OU.UserName AS 聊天对象用户名,
        UC.Content AS 最新消息内容,
        UC.SendTime AS 最新消息时间,
        (SELECT COUNT(*)
         FROM ChatMessage CM_unread
         WHERE CM_unread.ProductID = UC.ProductID
           AND CM_unread.ReceiverID = @userId          -- 消息是发给当前用户的
           AND CM_unread.SenderID = UC.OtherUserID    -- 消息是由对话的另一方发送的
           AND CM_unread.IsRead = 0                   -- 消息未读
           AND CM_unread.ReceiverVisible = 1          -- 消息对当前用户可见
        ) AS 未读消息数量
    FROM UserConversations UC
    JOIN [Product] P ON UC.ProductID = P.ProductID
    JOIN [User] OU ON UC.OtherUserID = OU.UserID
    LEFT JOIN [User] POwner ON P.OwnerID = POwner.UserID -- 商品所有者信息
    WHERE UC.rn = 1 -- 只取每个会话组合的最新一条消息
    ORDER BY UC.SendTime DESC; -- 按最新消息时间降序排列会话

END;
GO

-- sp_GetChatMessagesByProductAndUsers: 获取指定商品ID和两个用户之间的聊天记录 (分页)
-- 输入: @productId UNIQUEIDENTIFIER, @userId1 UNIQUEIDENTIFIER, @userId2 UNIQUEIDENTIFIER, @pageNumber INT, @pageSize INT
-- 输出: 聊天消息列表 (分页), 及总消息数
DROP PROCEDURE IF EXISTS [sp_GetChatMessagesByProductAndUsers];
GO
CREATE PROCEDURE [sp_GetChatMessagesByProductAndUsers]
    @productId UNIQUEIDENTIFIER,
    @userId1 UNIQUEIDENTIFIER,
    @userId2 UNIQUEIDENTIFIER,
    @pageNumber INT = 1,
    @pageSize INT = 20
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN RAISERROR('商品不存在。', 16, 1); RETURN; END
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId1)
    BEGIN RAISERROR('用户1不存在。', 16, 1); RETURN; END
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId2)
    BEGIN RAISERROR('用户2不存在。', 16, 1); RETURN; END

    IF @pageNumber < 1 SET @pageNumber = 1;
    IF @pageSize < 1 SET @pageSize = 1;
    -- IF @pageSize > 100 SET @pageSize = 100; -- Optional: Limit max page size

    DECLARE @offset INT = (@pageNumber - 1) * @pageSize;

    -- 获取消息列表
    SELECT
        M.MessageID AS 消息ID,
        M.SenderID AS 发送者ID,
        S.UserName AS 发送者用户名,
        M.ReceiverID AS 接收者ID,
        R.UserName AS 接收者用户名,
        M.ProductID AS 商品ID,
        P.ProductName AS 商品名称,
        M.Content AS 内容,
        M.SendTime AS 发送时间,
        M.IsRead AS 是否已读
    FROM [ChatMessage] M
    JOIN [User] S ON M.SenderID = S.UserID
    JOIN [User] R ON M.ReceiverID = R.UserID
    JOIN [Product] P ON M.ProductID = P.ProductID
    WHERE M.ProductID = @productId
      AND (
            (M.SenderID = @userId1 AND M.ReceiverID = @userId2 AND M.SenderVisible = 1) OR -- userId1 发送给 userId2, 且对 userId1 可见
            (M.SenderID = @userId2 AND M.ReceiverID = @userId1 AND M.SenderVisible = 1)    -- userId2 发送给 userId1, 且对 userId2 可见
          )
    ORDER BY M.SendTime ASC
    OFFSET @offset ROWS
    FETCH NEXT @pageSize ROWS ONLY;

    -- 返回总记录数
    SELECT COUNT(*) AS TotalMessages
    FROM [ChatMessage] M
    WHERE M.ProductID = @productId
      AND (
            (M.SenderID = @userId1 AND M.ReceiverID = @userId2 AND M.SenderVisible = 1) OR
            (M.SenderID = @userId2 AND M.ReceiverID = @userId1 AND M.SenderVisible = 1)
          );
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

    DECLARE @receiverIdCurrent UNIQUEIDENTIFIER;
    DECLARE @isReadCurrent BIT;

    SELECT @receiverIdCurrent = ReceiverID, @isReadCurrent = IsRead
    FROM [ChatMessage]
    WHERE MessageID = @messageId;

    IF @receiverIdCurrent IS NULL
    BEGIN
        RAISERROR('消息不存在。', 16, 1);
        RETURN;
    END

    IF @receiverIdCurrent != @userId
    BEGIN
        RAISERROR('无权标记此消息为已读，您不是该消息的接收者。', 16, 1);
        RETURN;
    END

    IF @isReadCurrent = 1
    BEGIN
        -- RAISERROR('消息已经是已读状态。', 10, 1); -- Informational, not an error
        SELECT @messageId AS MarkedAsReadMessageID, '消息已是已读状态。' AS Result;
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;
        UPDATE [ChatMessage]
        SET IsRead = 1
        WHERE MessageID = @messageId AND ReceiverID = @userId; -- Double check receiver

        COMMIT TRANSACTION;
        SELECT @messageId AS MarkedAsReadMessageID, '消息标记为已读成功。' AS Result;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_HideConversation: 用户隐藏与某个商品的会话（通过逻辑删除相关消息）
-- 输入: @productId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER
-- 逻辑: 将该用户在此商品相关会话中的所有消息标记为对自己不可见。
DROP PROCEDURE IF EXISTS [sp_HideConversation];
GO
CREATE PROCEDURE [sp_HideConversation]
    @productId UNIQUEIDENTIFIER,
    @userId UNIQUEIDENTIFIER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @userId)
    BEGIN RAISERROR('用户不存在。', 16, 1); RETURN; END
    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN RAISERROR('商品不存在。', 16, 1); RETURN; END

    IF NOT EXISTS (SELECT 1 FROM [ChatMessage] WHERE ProductID = @productId AND (SenderID = @userId OR ReceiverID = @userId))
    BEGIN
        -- RAISERROR('用户未参与此商品的任何聊天，无需隐藏。', 10, 1); -- Informational
        SELECT '用户未参与此商品的任何聊天，无需隐藏。' AS Result, @productId AS ProductID, @userId AS UserID;
        RETURN;
    END

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 将用户作为发送者的消息，对自己设置为不可见
        UPDATE [ChatMessage]
        SET SenderVisible = 0
        WHERE ProductID = @productId
          AND SenderID = @userId
          AND SenderVisible = 1;

        -- 将用户作为接收者的消息，对自己设置为不可见
        UPDATE [ChatMessage]
        SET ReceiverVisible = 0
        WHERE ProductID = @productId
          AND ReceiverID = @userId
          AND ReceiverVisible = 1;

        COMMIT TRANSACTION;

        SELECT '与该商品的会话已成功隐藏。' AS Result, @productId AS ProductID, @userId AS UserID;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- sp_GetChatMessagesByProduct: 获取某个商品相关的所有聊天记录 (对请求用户可见的)
-- 输入: @productId UNIQUEIDENTIFIER, @userId UNIQUEIDENTIFIER (用于验证请求者是参与者，并筛选只看自己相关的消息)
-- 输出: 聊天消息列表
DROP PROCEDURE IF EXISTS [sp_GetChatMessagesByProduct];
GO
CREATE PROCEDURE [sp_GetChatMessagesByProduct]
    @productId UNIQUEIDENTIFIER,
    @requestingUserId UNIQUEIDENTIFIER -- Renamed @userId to be more explicit
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM [Product] WHERE ProductID = @productId)
    BEGIN RAISERROR('商品不存在。', 16, 1); RETURN; END
    IF NOT EXISTS (SELECT 1 FROM [User] WHERE UserID = @requestingUserId)
    BEGIN RAISERROR('请求用户不存在。', 16, 1); RETURN; END

    -- 检查请求用户是否有权限查看此商品的聊天记录 (是商品所有者或聊天参与者)
    -- This check might be too broad or complex here if the goal is just to get messages *for* the requestingUser.
    -- The WHERE clause in the main query already filters by requestingUserId's involvement and visibility.
    -- For simplicity, if the user is not involved in any chat for this product, the query will return empty, which is fine.

    SELECT
        M.MessageID AS 消息ID,
        M.SenderID AS 发送者ID,
        S.UserName AS 发送者用户名,
        M.ReceiverID AS 接收者ID,
        R.UserName AS 接收者用户名,
        M.ProductID AS 商品ID,
        P.ProductName AS 商品名称,
        M.Content AS 内容,
        M.SendTime AS 发送时间,
        M.IsRead AS 是否已读
    FROM [ChatMessage] M
    JOIN [User] S ON M.SenderID = S.UserID
    JOIN [User] R ON M.ReceiverID = R.UserID
    JOIN [Product] P ON M.ProductID = P.ProductID
    WHERE M.ProductID = @productId
      AND (
            (M.SenderID = @requestingUserId AND M.SenderVisible = 1) OR -- Messages sent by requestingUser and visible to them
            (M.ReceiverID = @requestingUserId AND M.ReceiverVisible = 1) -- Messages received by requestingUser and visible to them
          )
    ORDER BY M.SendTime ASC;
END;
GO

-- sp_SetChatMessageVisibility: 设置单条聊天消息对发送者或接收者的可见性（逻辑删除）
-- 输入: @messageId UNIQUEIDENTIFIER, @operatingUserId UNIQUEIDENTIFIER (操作者ID), @visibleToTarget NVARCHAR(10) ('sender' 或 'receiver'), @isVisible BIT
-- 逻辑: 检查消息是否存在，检查操作者是否有权限（是发送者或接收者），根据 @visibleToTarget 更新相应的 Visible 字段。
DROP PROCEDURE IF EXISTS [sp_SetChatMessageVisibility];
GO
CREATE PROCEDURE [sp_SetChatMessageVisibility]
    @messageId UNIQUEIDENTIFIER,
    @operatingUserId UNIQUEIDENTIFIER,
    @visibleToTarget NVARCHAR(10), -- 'sender' (for SenderVisible), 'receiver' (for ReceiverVisible)
    @isVisible BIT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @msgSenderId UNIQUEIDENTIFIER;
    DECLARE @msgReceiverId UNIQUEIDENTIFIER;

    SELECT @msgSenderId = SenderID, @msgReceiverId = ReceiverID
    FROM [ChatMessage]
    WHERE MessageID = @messageId;

    IF @msgSenderId IS NULL
    BEGIN RAISERROR('消息不存在。', 16, 1); RETURN; END

    IF @visibleToTarget NOT IN ('sender', 'receiver')
    BEGIN RAISERROR('无效的可见性目标。请使用 ''sender'' 或 ''receiver''。', 16, 1); RETURN; END

    BEGIN TRY
        BEGIN TRANSACTION;

        IF @visibleToTarget = 'sender'
        BEGIN
            IF @operatingUserId != @msgSenderId
            BEGIN
                RAISERROR('无权修改发送者对此消息的可见性。', 16, 1);
                IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION; RETURN;
            END
            UPDATE [ChatMessage] SET SenderVisible = @isVisible WHERE MessageID = @messageId;
        END
        ELSE IF @visibleToTarget = 'receiver'
        BEGIN
            IF @operatingUserId != @msgReceiverId
        BEGIN
                RAISERROR('无权修改接收者对此消息的可见性。', 16, 1);
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION; RETURN;
            END
            UPDATE [ChatMessage] SET ReceiverVisible = @isVisible WHERE MessageID = @messageId;
        END

        COMMIT TRANSACTION;
        SELECT '消息可见性更新成功。' AS Result, @messageId AS MessageID, @visibleToTarget AS UpdatedTarget, @isVisible AS NewVisibility;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

PRINT 'Finished creating sp_SetChatMessageVisibility';
GO

-- =============================================
-- Indexes for ChatMessages Table
-- =============================================
PRINT 'Creating indexes for ChatMessages table...';
GO

-- Index to optimize fetching user conversations (supporting sp_GetUserConversations)
-- Covers scenarios where the user is either a sender or receiver, grouped by product, and ordered by time for latest message.
-- Including IsRead for unread count optimization.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessages_SenderProductReceiver_TimestampDesc' AND object_id = OBJECT_ID('dbo.ChatMessages'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_ChatMessages_SenderProductReceiver_TimestampDesc
    ON dbo.ChatMessages (SenderID, ProductID, ReceiverID, MessageTimestamp DESC)
    INCLUDE (MessageContent, IsRead, MimeType, FileUrl, FileSize, FileName);
    PRINT 'Created index IX_ChatMessages_SenderProductReceiver_TimestampDesc';
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessages_ReceiverProductSender_TimestampDesc' AND object_id = OBJECT_ID('dbo.ChatMessages'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_ChatMessages_ReceiverProductSender_TimestampDesc
    ON dbo.ChatMessages (ReceiverID, ProductID, SenderID, MessageTimestamp DESC)
    INCLUDE (MessageContent, IsRead, MimeType, FileUrl, FileSize, FileName);
    PRINT 'Created index IX_ChatMessages_ReceiverProductSender_TimestampDesc';
END
GO

-- Index to optimize fetching messages between two users for a specific product (supporting sp_GetChatMessagesByProductAndUsers)
-- Ordered by timestamp for pagination.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessages_ProductSenderReceiver_Timestamp' AND object_id = OBJECT_ID('dbo.ChatMessages'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_ChatMessages_ProductSenderReceiver_Timestamp
    ON dbo.ChatMessages (ProductID, SenderID, ReceiverID, MessageTimestamp DESC)
    INCLUDE (MessageContent, IsRead, MimeType, FileUrl, FileSize, FileName, VisibleToSender, VisibleToReceiver);
    PRINT 'Created index IX_ChatMessages_ProductSenderReceiver_Timestamp';
END
GO

-- Optional: A variation for the above if the query for sp_GetChatMessagesByProductAndUsers
-- sometimes has ReceiverID before SenderID in its predicates, though one well-structured query with OR
-- should effectively use the IX_ChatMessages_ProductSenderReceiver_Timestamp index.
-- However, if direct lookups with Receiver, Sender are common and performance is critical:
-- IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessages_ProductReceiverSender_Timestamp' AND object_id = OBJECT_ID('dbo.ChatMessages'))
-- BEGIN
-- CREATE NONCLUSTERED INDEX IX_ChatMessages_ProductReceiverSender_Timestamp
-- ON dbo.ChatMessages (ProductID, ReceiverID, SenderID, MessageTimestamp DESC)
-- INCLUDE (MessageContent, IsRead, MimeType, FileUrl, FileSize, FileName, VisibleToSender, VisibleToReceiver);
-- PRINT 'Created index IX_ChatMessages_ProductReceiverSender_Timestamp';
-- END
-- GO

PRINT 'Finished creating indexes for ChatMessages table.';
GO 