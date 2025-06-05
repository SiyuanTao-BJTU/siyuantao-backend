/*
 * 交易管理模块 - 订单触发器
 */

-- tr_Order_AfterCancel_RestoreQuantity: 订单取消或拒绝后恢复商品库存
-- ON [Order] AFTER UPDATE
DROP TRIGGER IF EXISTS [tr_Order_AfterCancel_RestoreQuantity];
GO
CREATE TRIGGER [tr_Order_AfterCancel_RestoreQuantity]
ON [Order]
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查订单状态是否从 'ConfirmedBySeller' 变为 'Cancelled' 或 'Rejected'
    IF UPDATE(Status)
    BEGIN
        BEGIN TRY
            UPDATE P
            SET P.Quantity = P.Quantity + i.Quantity
            FROM [Product] P
            JOIN inserted i ON P.ProductID = i.ProductID
            JOIN deleted d ON i.OrderID = d.OrderID
            WHERE i.Status IN ('Cancelled', 'Rejected') -- 新状态是取消或拒绝
            AND d.Status = 'ConfirmedBySeller'; -- 旧状态必须是"卖家已确认"
        END TRY
        BEGIN CATCH
            THROW; -- 传播错误，导致触发语句的事务回滚
        END CATCH
    END
END;
GO

-- tr_Order_AfterComplete_UpdateSellerCredit: 订单完成后更新卖家信用分
-- ON [Order] AFTER UPDATE
DROP TRIGGER IF EXISTS [tr_Order_AfterComplete_UpdateSellerCredit];
GO
CREATE TRIGGER [tr_Order_AfterComplete_UpdateSellerCredit]
ON [Order]
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 检查订单状态是否从非 'Completed' 变为 'Completed'
    IF UPDATE(Status)
    BEGIN
        BEGIN TRY -- 添加 TRY 块
            -- 根据设计文档，订单完成后，卖家信用分 +5 (如果评价系统也加分，需要协调)
            -- 这里假设订单完成本身就应该给卖家加分，具体分值参考设计文档或业务需求
            -- 假设订单完成固定增加 5 点信用分，上限100
            UPDATE U
            SET U.Credit = CASE 
                             WHEN U.Credit + 5 > 100 THEN 100 
                             ELSE U.Credit + 5 
                           END
            FROM [User] U
            JOIN inserted i ON U.UserID = i.SellerID
            JOIN deleted d ON i.OrderID = d.OrderID
            WHERE i.Status = 'Completed' -- 新状态是完成
            AND d.Status != 'Completed'; -- 旧状态不是完成 (避免重复增加)
        END TRY
        BEGIN CATCH -- 添加 CATCH 块
            THROW; -- 传播错误，导致触发语句的事务回滚
        END CATCH
    END
END;
GO