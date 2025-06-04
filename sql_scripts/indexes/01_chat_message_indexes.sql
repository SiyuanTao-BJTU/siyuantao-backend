-- Indexes for ChatMessage Table to optimize chat functionalities

-- Index for sp_GetChatMessagesByProductAndUsers and sp_HideConversation
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessage_Product_Sender_Receiver_Time' AND object_id = OBJECT_ID('ChatMessage'))
BEGIN
    CREATE INDEX IX_ChatMessage_Product_Sender_Receiver_Time 
    ON ChatMessage (ProductId, SenderId, ReceiverId, CreatedAt);
    PRINT 'Index IX_ChatMessage_Product_Sender_Receiver_Time created.';
END
ELSE
BEGIN
    PRINT 'Index IX_ChatMessage_Product_Sender_Receiver_Time already exists.';
END
GO

-- Index for sp_GetUserConversations (when user is Sender)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessage_Sender_Product_TimeDesc_Includes' AND object_id = OBJECT_ID('ChatMessage'))
BEGIN
    CREATE INDEX IX_ChatMessage_Sender_Product_TimeDesc_Includes
    ON ChatMessage (SenderId, ProductId, CreatedAt DESC)
    INCLUDE (ReceiverId, SenderVisible, IsRead);
    PRINT 'Index IX_ChatMessage_Sender_Product_TimeDesc_Includes created.';
END
ELSE
BEGIN
    PRINT 'Index IX_ChatMessage_Sender_Product_TimeDesc_Includes already exists.';
END
GO

-- Index for sp_GetUserConversations (when user is Receiver)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ChatMessage_Receiver_Product_TimeDesc_Includes' AND object_id = OBJECT_ID('ChatMessage'))
BEGIN
    CREATE INDEX IX_ChatMessage_Receiver_Product_TimeDesc_Includes
    ON ChatMessage (ReceiverId, ProductId, CreatedAt DESC)
    INCLUDE (SenderId, ReceiverVisible, IsRead);
    PRINT 'Index IX_ChatMessage_Receiver_Product_TimeDesc_Includes created.';
END
ELSE
BEGIN
    PRINT 'Index IX_ChatMessage_Receiver_Product_TimeDesc_Includes already exists.';
END
GO

PRINT 'Finished applying chat message indexes.';
GO 