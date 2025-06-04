/*
 * 商品相关触发器
 */

-- 商品状态变更触发器：当商品数量为0时自动设为Sold状态，数量大于0时恢复Active状态
DROP TRIGGER IF EXISTS [tr_Product_AfterUpdate_QuantityStatus];
GO
CREATE TRIGGER [tr_Product_AfterUpdate_QuantityStatus]
ON [Product]
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY -- 添加 TRY 块

    -- 处理数量从大于0变为0的情况 (商品售罄)
    IF UPDATE(Quantity)
    BEGIN
        UPDATE p
        SET P.Status = 'Sold' -- 设为Sold
        FROM [Product] P
        JOIN inserted i ON P.ProductID = i.ProductID
        JOIN deleted d ON P.ProductID = d.ProductID
        WHERE i.Quantity = 0
        AND d.Quantity > 0 -- 确保 Quantity 是从大于0变为0
        AND i.Status != 'Sold'; -- 确保不是已经Sold的状态，避免重复触发或死循环
    END

     -- 处理数量从0变为大于0的情况 (订单取消时恢复库存)
    IF UPDATE(Quantity)
    BEGIN
         UPDATE p
        SET P.Status = 'Active' -- 恢复为Active
        FROM [Product] P
        JOIN inserted i ON P.ProductID = i.ProductID
        JOIN deleted d ON P.ProductID = d.ProductID
        WHERE i.Quantity > 0
        AND d.Quantity = 0 -- 确保 Quantity 是从0变为大于0
        AND i.Status = 'Sold'; -- 确保原状态是Sold (这是订单取消触发器逻辑，在此处合并处理 Quantity 变化)
    END

    END TRY
    BEGIN CATCH -- 添加 CATCH 块
        -- 在触发器中，错误处理应该记录错误并可能回滚事务
        -- 但这里是 AFTER 触发器，默认运行在触发语句的事务中
        -- THROW 会传播错误，导致触发语句的事务回滚
        THROW;
    END CATCH
END;
GO 