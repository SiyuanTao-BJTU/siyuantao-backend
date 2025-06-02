/*
 * 交易管理模块 - 评价存储过程
 */

-- sp_CreateEvaluation: 创建评价
-- 功能: 买家对已完成的订单进行评价
DROP PROCEDURE IF EXISTS [sp_CreateEvaluation];
GO
CREATE PROCEDURE [sp_CreateEvaluation]
    @OrderID UNIQUEIDENTIFIER,
    @BuyerID UNIQUEIDENTIFIER,
    @Rating INT,
    @Content NVARCHAR(500) NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @SellerID UNIQUEIDENTIFIER;
    DECLARE @OrderStatus NVARCHAR(50);
    DECLARE @ErrorMessage NVARCHAR(4000);
    DECLARE @NewEvaluationID UNIQUEIDENTIFIER = NEWID(); -- 预先生成新的评价ID

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 检查订单是否存在，是否属于该买家，以及是否已完成
        SELECT @OrderStatus = O.Status, @SellerID = O.SellerID
        FROM [Order] O
        WHERE O.OrderID = @OrderID AND O.BuyerID = @BuyerID;

        IF @OrderStatus IS NULL
        BEGIN
            SET @ErrorMessage = '创建评价失败：订单不存在或您不是该订单的买家。';
            THROW 50012, @ErrorMessage, 1;
        END

        IF @OrderStatus != 'Completed'
        BEGIN
            SET @ErrorMessage = '创建评价失败：只有已完成的订单才能评价。当前订单状态：' + @OrderStatus;
            THROW 50013, @ErrorMessage, 1;
        END

        -- 检查是否已评价过该订单
        IF EXISTS (SELECT 1 FROM [Evaluation] WHERE OrderID = @OrderID)
        BEGIN
            SET @ErrorMessage = '创建评价失败：您已评价过此订单。';
            THROW 50014, @ErrorMessage, 1;
        END

        -- 检查评分是否在有效范围内 (1-5)
        IF @Rating NOT BETWEEN 1 AND 5
        BEGIN
            SET @ErrorMessage = '创建评价失败：评分必须在1到5之间。';
            THROW 50015, @ErrorMessage, 1;
        END

        -- 插入评价
        INSERT INTO [Evaluation] (EvaluationID, OrderID, BuyerID, SellerID, Rating, Content, CreateTime)
        VALUES (@NewEvaluationID, @OrderID, @BuyerID, @SellerID, @Rating, @Content, GETDATE());

        -- 卖家信用分更新逻辑已移至触发器 tr_Evaluation_AfterInsert_UpdateSellerCredit
        
        SELECT @NewEvaluationID AS 评价ID, '评价创建成功' AS 消息;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO