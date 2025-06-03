/*
 * 交易管理模块 - 评价触发器
 * 功能: 评价插入后更新卖家的信用分
 */

-- tr_Evaluation_AfterInsert_UpdateSellerCredit: 评价插入后更新卖家的信用分
-- ON [Evaluation] AFTER INSERT
DROP TRIGGER IF EXISTS [tr_Evaluation_AfterInsert_UpdateSellerCredit];
GO
CREATE TRIGGER [tr_Evaluation_AfterInsert_UpdateSellerCredit]
ON [Evaluation]
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY -- 添加 TRY 块

    -- Cursor 或 JOIN 处理可能的多行插入
    -- 这里使用JOIN来处理批量插入更高效
    UPDATE U
    SET U.Credit = CASE
                     -- 调整信用分逻辑：3星不加不减，高于3加，低于3减。每颗星+/- 2分。例如 5星: +4, 4星: +2, 3星: 0, 2星: -2, 1星: -4
                     WHEN U.Credit + ((i.Rating - 3) * 2) > 100 THEN 100 -- 信用分上限100
                     WHEN U.Credit + ((i.Rating - 3) * 2) < 0 THEN 0     -- 信用分下限0
                     ELSE U.Credit + ((i.Rating - 3) * 2) -- 计算新的信用分
                   END
    FROM [User] U
    JOIN [Order] O ON U.UserID = O.SellerID -- 从 Order 表获取 SellerID (对应中文列名)
    JOIN inserted i ON O.OrderID = i.OrderID; -- 关联 inserted 表的 OrderID

    END TRY
    BEGIN CATCH -- 添加 CATCH 块
         -- 在触发器中，错误处理应该记录错误并可能回滚事务
        -- THROW 会传播错误，导致触发语句的事务回滚
        THROW;
    END CATCH
END;
GO 