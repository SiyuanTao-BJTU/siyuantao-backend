/*
 * 删除所有数据库对象的脚本
 * 
 * 注意：此脚本将删除所有相关表、存储过程和触发器。
 */

PRINT N'Starting complete database object drop sequence...';
GO

-- Step 1: Drop all known triggers
PRINT N'Dropping all known triggers...';
IF EXISTS (SELECT * FROM sys.triggers WHERE name = 'tr_Product_AfterUpdate_QuantityStatus') DROP TRIGGER [tr_Product_AfterUpdate_QuantityStatus];
IF EXISTS (SELECT * FROM sys.triggers WHERE name = 'tr_Order_AfterCancel_RestoreQuantity') DROP TRIGGER [tr_Order_AfterCancel_RestoreQuantity];
IF EXISTS (SELECT * FROM sys.triggers WHERE name = 'tr_Order_AfterComplete_UpdateSellerCredit') DROP TRIGGER [tr_Order_AfterComplete_UpdateSellerCredit];
IF EXISTS (SELECT * FROM sys.triggers WHERE name = 'tr_Evaluation_AfterInsert_UpdateSellerCredit') DROP TRIGGER [tr_Evaluation_AfterInsert_UpdateSellerCredit];
GO

-- Step 2: Drop all known procedures
PRINT N'Dropping all known procedures...';
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetUserProfileById') DROP PROCEDURE [sp_GetUserProfileById];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetUserByUsernameWithPassword') DROP PROCEDURE [sp_GetUserByUsernameWithPassword];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateUser') DROP PROCEDURE [sp_CreateUser];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateUserProfile') DROP PROCEDURE [sp_UpdateUserProfile];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetUserPasswordHashById') DROP PROCEDURE [sp_GetUserPasswordHashById];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateUserPassword') DROP PROCEDURE [sp_UpdateUserPassword];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_RequestMagicLink') DROP PROCEDURE [sp_RequestMagicLink];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_VerifyMagicLink') DROP PROCEDURE [sp_VerifyMagicLink];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_ChangeUserStatus') DROP PROCEDURE [sp_ChangeUserStatus];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_AdjustUserCredit') DROP PROCEDURE [sp_AdjustUserCredit];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateSystemNotification') DROP PROCEDURE [sp_CreateSystemNotification];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetSystemNotificationsByUserId') DROP PROCEDURE [sp_GetSystemNotificationsByUserId];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_MarkNotificationAsRead') DROP PROCEDURE [sp_MarkNotificationAsRead];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetProductList') DROP PROCEDURE [sp_GetProductList];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetProductDetail') DROP PROCEDURE [sp_GetProductDetail];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateProduct') DROP PROCEDURE [sp_CreateProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateProduct') DROP PROCEDURE [sp_UpdateProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_DeleteProduct') DROP PROCEDURE [sp_DeleteProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_ReviewProduct') DROP PROCEDURE [sp_ReviewProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_WithdrawProduct') DROP PROCEDURE [sp_WithdrawProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_AddFavoriteProduct') DROP PROCEDURE [sp_AddFavoriteProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_RemoveFavoriteProduct') DROP PROCEDURE [sp_RemoveFavoriteProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetUserFavoriteProducts') DROP PROCEDURE [sp_GetUserFavoriteProducts];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetTransactionsByUser') DROP PROCEDURE [sp_GetTransactionsByUser];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetTransactionById') DROP PROCEDURE [sp_GetTransactionById];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetTransactionComments') DROP PROCEDURE [sp_GetTransactionComments];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateTransaction') DROP PROCEDURE [sp_CreateTransaction];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateTransactionStatus') DROP PROCEDURE [sp_UpdateTransactionStatus];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateTransactionComment') DROP PROCEDURE [sp_CreateTransactionComment];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetChatMessagesByProduct') DROP PROCEDURE [sp_GetChatMessagesByProduct];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateOrder') DROP PROCEDURE [sp_CreateOrder];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_ConfirmOrder') DROP PROCEDURE [sp_ConfirmOrder];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_RejectOrder') DROP PROCEDURE [sp_RejectOrder];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetChatMessagesByTransaction') DROP PROCEDURE [sp_GetChatMessagesByTransaction];
-- Image Procedures
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetImageById') DROP PROCEDURE [sp_GetImageById];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_GetImagesByObject') DROP PROCEDURE [sp_GetImagesByObject];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateImage') DROP PROCEDURE [sp_CreateImage];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateImage') DROP PROCEDURE [sp_UpdateImage];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_DeleteImage') DROP PROCEDURE [sp_DeleteImage];
-- Old/Renamed procedures just in case
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateUser') DROP PROCEDURE [sp_UpdateUser];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_CreateOrUpdateStudentAuthProfile') DROP PROCEDURE [sp_CreateOrUpdateStudentAuthProfile];
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_UpdateStudentAuthStatus') DROP PROCEDURE [sp_UpdateStudentAuthStatus];
GO

-- Step 3: Drop tables. Start with tables that have foreign keys pointing to other tables.
PRINT N'Dropping all tables (custom first, then Django-managed)...';

-- Drop custom application specific tables (order matters due to FKs)
PRINT N'Dropping custom application tables...';
-- Order reversed based on FK dependencies to ensure tables are dropped before those they reference.
DROP TABLE IF EXISTS [Report]; -- FK to User, Product, Order
DROP TABLE IF EXISTS [ReturnRequest]; -- FK to Order
DROP TABLE IF EXISTS [Evaluation]; -- FK to Order, User
DROP TABLE IF EXISTS [ChatMessage]; -- FK to User, Product - Note: ChatMessage FK to Transaction is in the original, updated FK is to Product.
DROP TABLE IF EXISTS [UserFavorite]; -- FK to User, Product
DROP TABLE IF EXISTS [ProductImage]; -- FK to Product
DROP TABLE IF EXISTS [Order]; -- FK to User, Product
DROP TABLE IF EXISTS [Product]; -- FK to User
DROP TABLE IF EXISTS [SystemNotification]; -- FK to User
DROP TABLE IF EXISTS [User]; -- Base custom user table

-- Drop Django auto-generated tables (if any remain or are generated separately)
-- Reversing order based on typical Django app FKs (contenttypes, auth)
PRINT N'Dropping Django auto-generated tables (if any)...';
DROP TABLE IF EXISTS [itemTrade_transactioncomment]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_chatmessage]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_systemnotification]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_userfavorite]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_productcomment]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_uploadedimage]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_transaction]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_product]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_category]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_authenticationprofile]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_administrator]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_customuser_groups]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_customuser_user_permissions]; -- If it exists
DROP TABLE IF EXISTS [itemTrade_customuser]; -- If it exists

-- Drop Django core tables (order matters due to FKs)
PRINT N'Dropping Django core tables...';
DROP TABLE IF EXISTS [django_admin_log]; -- FK to django_content_type, auth_user
DROP TABLE IF EXISTS [auth_user_user_permissions]; -- FK to auth_user, auth_permission
DROP TABLE IF EXISTS [auth_user_groups]; -- FK to auth_user, auth_group
DROP TABLE IF EXISTS [auth_group_permissions]; -- FK to auth_group, auth_permission
DROP TABLE IF EXISTS [auth_permission]; -- FK to django_content_type
DROP TABLE IF EXISTS [auth_group];
DROP TABLE IF EXISTS [auth_user]; -- Django's built-in user table if used alongside CustomUser
DROP TABLE IF EXISTS [django_content_type];
DROP TABLE IF EXISTS [django_migrations];
DROP TABLE IF EXISTS [django_session];
GO

PRINT N'All specified database objects dropped (if they existed).';
GO 