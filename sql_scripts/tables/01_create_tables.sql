-- SQL Server 数据库表结构定义

-- Explicitly drop table if it exists to ensure a clean start
IF OBJECT_ID('dbo.[User]', 'U') IS NOT NULL
    DROP TABLE dbo.[User];
GO

-- 1. 用户表 (User)
-- 这是系统的核心用户表，包含用户的基本信息、核心状态以及校园认证状态。
CREATE TABLE [User] (
    [UserID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),  -- 用户唯一标识符，主键，默认生成新的UUID
    [UserName] NVARCHAR(128) NOT NULL UNIQUE,              -- 登录用户名，不允许为空，且唯一
    [Password] NVARCHAR(128) NOT NULL,                     -- 密码的哈希值，不允许为空（通常为随机生成的，用于重置密码，或者只通过魔术链接登录则可为空/不使用）
    [Status] NVARCHAR(20) NOT NULL DEFAULT 'Active'        -- 用户账户状态，默认为'Active'
        CHECK ([Status] IN ('Active', 'Disabled')),         -- 约束状态值只能是'Active'（活跃）或'Disabled'（禁用）
    [Credit] INT NOT NULL DEFAULT 100                       -- 用户信用分，默认为100
        CHECK ([Credit] BETWEEN 0 AND 100),                 -- 信用分必须在0到100之间
    [IsStaff] BIT NOT NULL DEFAULT 0,                       -- 是否为平台管理员：0=普通用户，1=管理员，默认为0
    [IsSuperAdmin] BIT NOT NULL DEFAULT 0,                -- 是否超级管理员 (0=否, 1=是)
    [IsVerified] BIT NOT NULL DEFAULT 0,                    -- 校园身份是否已通过邮箱认证：0=未认证，1=已认证，默认为0 (通过邮箱OPT认证)
    [Major] NVARCHAR(100) NULL,                             -- 用户专业信息，可为空
    [Email] NVARCHAR(254) NULL,                  -- 用户认证邮箱，可以为空但认证后必须唯一（不能使用标准的唯一约束，标准唯一约束不允许重复的NULL值,修改为使用一个筛选的唯一索引。作为魔术链接认证的依据）
    [AvatarUrl] NVARCHAR(255) NULL,                         -- 用户头像图片URL，可为空
    [Bio] NVARCHAR(500) NULL,                               -- 用户个人简介，可为空
    [PhoneNumber] NVARCHAR(20) NULL UNIQUE,                 -- 用户手机号码，允许为空但如果填写则必须唯一
    [JoinTime] DATETIME NOT NULL DEFAULT GETDATE(),         -- 用户注册时间，不允许为空，默认当前系统时间
    [LastLoginTime] DATETIME2 NULL                          -- 用户最后登录时间
);
GO

CREATE UNIQUE INDEX UQ_User_Email ON [User](Email) WHERE Email IS NOT NULL;
GO

-- 2. 商品表 (Product)
-- 记录平台上的所有商品信息。
CREATE TABLE [Product] (
    [ProductID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),   -- 商品唯一标识符，主键
    [OwnerID] UNIQUEIDENTIFIER NOT NULL,                        -- 商品所有者（发布者）的用户ID，不允许为空
    [CategoryName] NVARCHAR(100) NULL,                          -- 商品类别名称，可为空（前端直接写死，后端返回）
    [ProductName] NVARCHAR(200) NOT NULL,                       -- 商品标题，不允许为空
    [Description] NVARCHAR(MAX) NULL,                           -- 商品详细描述，可为空，支持大文本
    [Quantity] INT NOT NULL CHECK ([Quantity] >= 0),            -- 商品库存数量，不允许为空，必须大于等于0
    [Price] DECIMAL(10, 2) NOT NULL CHECK ([Price] >= 0),       -- 商品价格，不允许为空，必须大于等于0
    [Condition] NVARCHAR(50) NULL,                              -- 商品成色 (例如: 全新, 九成新, 八成新等), 可为空
    [PostTime] DATETIME NOT NULL DEFAULT GETDATE(),             -- 商品发布时间，不允许为空，默认当前系统时间
    [Status] NVARCHAR(20) NOT NULL DEFAULT 'PendingReview'      -- 商品当前状态，默认为'PendingReview'
        CHECK ([Status] IN ('PendingReview', 'Rejected', 'Active', 'Sold', 'Withdrawn')), -- PendingReview (待审核) Rejected (管理员已拒绝) Active (在售) Sold (已售罄) Withdrawn (下架) 
    [AuditReason] NVARCHAR(MAX) NULL, -- 新增，审核拒绝原因
    CONSTRAINT FK_Product_Owner FOREIGN KEY ([OwnerID]) REFERENCES [User]([UserID]) ON DELETE CASCADE -- 外键关联User表，当用户删除时，其所有商品也删除
);
GO

-- 3. 商品图片表 (ProductImage)
-- 存储商品的图片信息。
CREATE TABLE [ProductImage] (
    [ImageID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 图片唯一标识符，主键
    [ProductID] UNIQUEIDENTIFIER NOT NULL,                  -- 图片所属的商品ID，不允许为空
    [ImageURL] NVARCHAR(255) NOT NULL,                      -- 图片存储的URL路径，不允许为空
    [UploadTime] DATETIME NOT NULL DEFAULT GETDATE(),       -- 图片上传时间，不允许为空，默认当前系统时间
    [SortOrder] INT NOT NULL DEFAULT 0,                     -- 图片显示顺序，默认为0 (SortOrder = 0 表示主图)
    CONSTRAINT FK_Image_Product FOREIGN KEY ([ProductID]) REFERENCES [Product]([ProductID]) ON DELETE CASCADE -- 外键关联Product表，当商品删除时，其所有图片也删除
);
GO

-- 4. 订单表 (Order)
-- 记录用户之间的交易订单信息。
CREATE TABLE [Order] (
    [OrderID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 订单唯一标识符，主键
    [SellerID] UNIQUEIDENTIFIER NOT NULL,                   -- 卖家用户ID，不允许为空
    [BuyerID] UNIQUEIDENTIFIER NOT NULL,                    -- 买家用户ID，不允许为空
    [ProductID] UNIQUEIDENTIFIER NOT NULL,                  -- 购买的商品ID，不允许为空
    [Quantity] INT NOT NULL CHECK ([Quantity] >= 1),        -- 购买数量，不允许为空，必须大于等于1
    [CreateTime] DATETIME NOT NULL DEFAULT GETDATE(),       -- 订单创建时间，不允许为空，默认当前系统时间
    [Status] NVARCHAR(50) NOT NULL                          -- 订单状态，不允许为空
        CHECK ([Status] IN (
            'PendingSellerConfirmation', -- 待卖家确认（买家已下单，等待卖家响应）
            'ConfirmedBySeller',         -- 卖家已确认（卖家已同意，商品库存已扣减）
            'Completed',                 -- 订单完成（买家已收货或交易已结束）
            'Cancelled'                  -- 订单取消（包括线下验货时买家取消）
        )),
    [CompleteTime] DATETIME NULL,                           -- 订单完成时间，可为空
    [CancelTime] DATETIME NULL,                             -- 订单取消时间，可为空
    [CancelReason] NVARCHAR(500) NULL,                      -- 订单取消原因，可为空
    CONSTRAINT FK_Order_Seller FOREIGN KEY ([SellerID]) REFERENCES [User]([UserID]), -- 外键关联卖家用户
    CONSTRAINT FK_Order_Buyer FOREIGN KEY ([BuyerID]) REFERENCES [User]([UserID]),   -- 外键关联买家用户
    CONSTRAINT FK_Order_Product FOREIGN KEY ([ProductID]) REFERENCES [Product]([ProductID]) ON DELETE NO ACTION -- 外键关联商品，当商品删除时，如果存在关联订单则操作失败
);
GO

-- 5. 评价表 (Evaluation)
-- 专门用于构建卖家交易名片和信任度的评价。
-- 买家对同一订单只能评价一次。评价对象是卖家,OrderID 是评价的上下文
-- 没有 OrderID，你将很难区分不同交易的评价，也无法限制"一次交易只能评价一次"。
CREATE TABLE [Evaluation] (
    [EvaluationID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 评价唯一标识符，主键
    [OrderID] UNIQUEIDENTIFIER NOT NULL,                        -- 评价关联的订单ID，不允许为空
    [SellerID] UNIQUEIDENTIFIER NOT NULL,                       -- 被评价的卖家用户ID
    [BuyerID] UNIQUEIDENTIFIER NOT NULL,                        -- 提交评价的买家用户ID
    [Rating] INT NOT NULL CHECK ([Rating] BETWEEN 1 AND 5),     -- 星级评分，1到5星，不允许为空
    [Content] NVARCHAR(500) NULL,                               -- 评价内容，可为空
    [CreateTime] DATETIME NOT NULL DEFAULT GETDATE(),           -- 评价创建时间，不允许为空，默认当前系统时间
    CONSTRAINT FK_Evaluation_Order FOREIGN KEY ([OrderID]) REFERENCES [Order]([OrderID]), -- 外键关联订单
    CONSTRAINT FK_Evaluation_Seller FOREIGN KEY ([SellerID]) REFERENCES [User]([UserID]), -- 外键关联被评价的卖家
    CONSTRAINT FK_Evaluation_Buyer FOREIGN KEY ([BuyerID]) REFERENCES [User]([UserID]), -- 外键关联提交评价的买家
    -- 核心改变：添加唯一约束，确保同一个订单只能被评价一次。
    -- 这意味着一旦一个订单被评价，任何人都不能再次评价它。
    CONSTRAINT UQ_Evaluation_OrderID UNIQUE ([OrderID])
);
GO

-- 6. 消息表 (ChatMessage)
-- 记录用户之间的聊天消息，严格以产品为中心。
CREATE TABLE [ChatMessage] (
    [MessageID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 消息唯一标识符，主键
    [SenderID] UNIQUEIDENTIFIER NOT NULL,                   -- 消息发送者用户ID，不允许为空
    [ReceiverID] UNIQUEIDENTIFIER NOT NULL,                 -- 消息接收者用户ID，不允许为空
    [ProductID] UNIQUEIDENTIFIER NOT NULL,                  -- 消息相关的商品ID，不允许为空（所有聊天都以产品为中心）
    [SenderVisible] BIT NOT NULL DEFAULT 1,                 -- 消息在发送者端是否可见：1=可见，0=逻辑删除，默认为1
    [ReceiverVisible] BIT NOT NULL DEFAULT 1,               -- 消息在接收者端是否可见：1=可见，0=逻辑删除，默认为1
    [Content] NVARCHAR(MAX) NOT NULL,                       -- 消息内容，不允许为空，支持大文本
    [SendTime] DATETIME NOT NULL DEFAULT GETDATE(),         -- 消息发送时间，不允许为空，默认当前系统时间
    [IsRead] BIT NOT NULL DEFAULT 0,                        -- 消息是否已读：0=未读，1=已读，默认为0
    CONSTRAINT FK_ChatMessage_Sender FOREIGN KEY ([SenderID]) REFERENCES [User]([UserID]), -- 外键关联发送者用户
    CONSTRAINT FK_ChatMessage_Receiver FOREIGN KEY ([ReceiverID]) REFERENCES [User]([UserID]), -- 外键关联接收者用户
    CONSTRAINT FK_ChatMessage_Product FOREIGN KEY ([ProductID]) REFERENCES [Product]([ProductID]) -- 外键关联商品
    -- 注意：如果商品被删除，关联到该商品的聊天记录如何处理？目前 ON DELETE NO ACTION，需要应用层处理。
);
GO

-- 7. 退货请求表 (ReturnRequest)
-- 记录用户发起的退货请求。
CREATE TABLE [ReturnRequest] (
    [ReturnRequestID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 退货请求唯一标识符，主键
    [OrderID] UNIQUEIDENTIFIER NOT NULL UNIQUE,                     -- 关联的订单ID，不允许为空，且一个订单只能有一个退货请求
    [ReturnReason] NVARCHAR(500) NOT NULL,                          -- 退货原因描述，不允许为空
    [ApplyTime] DATETIME NOT NULL DEFAULT GETDATE(),                -- 退货申请时间，不允许为空，默认当前系统时间
    [SellerAgree] BIT NULL,                                         -- 卖家是否同意退货：NULL=未处理，0=不同意，1=同意
    [BuyerApplyIntervene] BIT NULL,                                 -- 买家是否申请管理员介入：NULL=未申请，0=未申请，1=已申请
    [AuditTime] DATETIME NULL,                                      -- 退货请求处理时间（卖家或管理员），可为空
    [AuditStatus] NVARCHAR(20) NOT NULL DEFAULT 'ReturnRequested'  -- 退货请求的当前状态，默认为'ReturnRequested'
        CHECK ([AuditStatus] IN (
            'ReturnRequested',     -- 买家已提交退货请求，等待卖家处理
            'ReturnAccepted',      -- 卖家或管理员已同意退货
            'ReturnRejected',      -- 卖家或管理员已拒绝退货
            'InterventionRequested', -- 买家已申请管理员介入
            'InterventionResolved'   -- 管理员介入已解决
        )),
    [AuditIdea] NVARCHAR(500) NULL,                                 -- 卖家或管理员的处理意见/理由，可为空
    [ProcessorAdminID] UNIQUEIDENTIFIER NULL, -- 处理该退货请求的管理员ID，可为空
    CONSTRAINT FK_ReturnRequest_Order FOREIGN KEY ([OrderID]) REFERENCES [Order]([OrderID]) ON DELETE NO ACTION,  -- 外键关联订单，如果删除订单存在关联退货请求则操作失败
    CONSTRAINT FK_ReturnRequest_ProcessorAdmin FOREIGN KEY ([ProcessorAdminID]) REFERENCES [User]([UserID]) --只有具有管理员权限（IsStaff=1）的用户ID才应被写入该字段，应用层需保证。
);
GO

-- 8. 用户收藏表 (UserFavorite)
-- 记录用户收藏的商品。
CREATE TABLE [UserFavorite] (
    [FavoriteID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 收藏记录唯一标识符，主键
    [UserID] UNIQUEIDENTIFIER NOT NULL,                       -- 收藏商品的用户ID，不允许为空
    [ProductID] UNIQUEIDENTIFIER NOT NULL,                    -- 被收藏的商品ID，不允许为空
    [FavoriteTime] DATETIME NOT NULL DEFAULT GETDATE(),       -- 收藏时间，不允许为空，默认当前系统时间
    CONSTRAINT FK_UserFavorite_User FOREIGN KEY ([UserID]) REFERENCES [User]([UserID]) ON DELETE NO ACTION, -- 外键关联用户，用户删除时收藏记录删除
    CONSTRAINT FK_UserFavorite_Product FOREIGN KEY ([ProductID]) REFERENCES [Product]([ProductID]) ON DELETE CASCADE, -- 外键关联商品，商品删除时如果存在关联收藏记录则操作失败
    CONSTRAINT UQ_UserFavorite_UserProduct UNIQUE ([UserID], [ProductID]) -- 复合唯一约束，确保一个用户不能重复收藏同一个商品
);
GO

-- 9. 系统通知表 (SystemNotification)
-- 存储系统发送给用户的通知。通知类型由管理员在标题中或模板中定义。
CREATE TABLE [SystemNotification] (
    [NotificationID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(), -- 通知唯一标识符，主键
    [UserID] UNIQUEIDENTIFIER NOT NULL,                           -- 通知接收者用户ID，不允许为空
    [Title] NVARCHAR(200) NOT NULL,                               -- 通知标题，不允许为空（包含通知类型信息，如"商品降价通知"）
    [Content] NVARCHAR(MAX) NOT NULL,                             -- 通知内容，不允许为空，支持大文本
    [CreateTime] DATETIME NOT NULL DEFAULT GETDATE(),             -- 通知创建时间，不允许为空，默认当前系统时间
    [IsRead] BIT NOT NULL DEFAULT 0,                              -- 通知是否已读：0=未读，1=已读，默认为0
    CONSTRAINT FK_SystemNotification_User FOREIGN KEY ([UserID]) REFERENCES [User]([UserID]) ON DELETE CASCADE -- 外键关联用户，用户删除时通知记录删除
);
GO

-- 10. 举报表 (Report)
-- 记录用户或管理员提交的举报信息。
CREATE TABLE [Report] (
    [ReportID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),    -- 举报记录唯一标识符，主键
    [ReporterUserID] UNIQUEIDENTIFIER NOT NULL,                 -- 发起举报的用户ID，不允许为空
    [ReportedUserID] UNIQUEIDENTIFIER NULL,                     -- 被举报的用户ID，可为空（如果举报对象是商品/订单）
    [ReportedProductID] UNIQUEIDENTIFIER NULL,                  -- 被举报的商品ID，可为空
    [ReportedOrderID] UNIQUEIDENTIFIER NULL,                    -- 被举报的订单ID，可为空
    [ReportContent] NVARCHAR(500) NOT NULL,                     -- 举报内容描述，不允许为空
    [ReportTime] DATETIME NOT NULL DEFAULT GETDATE(),           -- 举报提交时间，不允许为空，默认当前系统时间
    [ProcessingStatus] NVARCHAR(20) NOT NULL DEFAULT 'Pending'  -- 举报处理状态，默认为'Pending'
        CHECK ([ProcessingStatus] IN ('Pending', 'Resolved', 'Rejected')), -- 约束状态值：'Pending' (待处理), 'Resolved' (已解决), 'Rejected' (已驳回)
    [ProcessorAdminID] UNIQUEIDENTIFIER NULL,                   -- 处理该举报的管理员ID，可为空
    [ProcessingTime] DATETIME NULL,                             -- 举报处理完成时间，可为空
    [ProcessingResult] NVARCHAR(500) NULL,                      -- 举报处理结果描述，可为空
    CONSTRAINT FK_Report_ReporterUser FOREIGN KEY ([ReporterUserID]) REFERENCES [User]([UserID]), -- 外键关联举报者用户
    CONSTRAINT FK_Report_ReportedUser FOREIGN KEY ([ReportedUserID]) REFERENCES [User]([UserID]), -- 外键关联被举报用户
    CONSTRAINT FK_Report_ProcessorAdmin FOREIGN KEY ([ProcessorAdminID]) REFERENCES [User]([UserID]), -- 外键关联处理管理员
    CONSTRAINT FK_Report_Product FOREIGN KEY ([ReportedProductID]) REFERENCES [Product]([ProductID]), -- 外键关联被举报商品
    CONSTRAINT FK_Report_Order FOREIGN KEY ([ReportedOrderID]) REFERENCES [Order]([OrderID]) -- 外键关联被举报订单
);
GO

-- 11. OTP 表 (Otp)
-- 存储用于各种验证（如密码重置、登录、邮箱验证）的一次性密码 (OTP)。
CREATE TABLE [Otp] (
    [OtpID] UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),       -- OTP 唯一标识符，主键
    [UserID] UNIQUEIDENTIFIER NOT NULL,                         -- 关联的用户ID
    [OtpCode] NVARCHAR(10) NOT NULL,                            -- OTP 代码（通常是6位数字或字母数字组合）
    [CreationTime] DATETIME NOT NULL DEFAULT GETDATE(),         -- OTP 创建时间
    [ExpiresAt] DATETIME NOT NULL,                              -- OTP 过期时间
    [IsUsed] BIT NOT NULL DEFAULT 0,                            -- OTP 是否已被使用：0=未使用，1=已使用
    [OtpType] NVARCHAR(50) NOT NULL,                            -- OTP 类型 (例如: 'PasswordReset', 'Login', 'EmailVerification')
    CONSTRAINT FK_Otp_User FOREIGN KEY ([UserID]) REFERENCES [User]([UserID]) ON DELETE CASCADE -- 外键关联用户表，用户删除时相关OTP也删除
);
GO

-- 针对 Otp 表添加筛选唯一索引
CREATE UNIQUE INDEX IX_Otp_UserID_OtpType_NotUsed 
ON [Otp] ([UserID], [OtpType]) 
WHERE [IsUsed] = 0; -- 同一用户针对同类型OTP只能有一个未使用的记录
GO