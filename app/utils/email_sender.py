# app/utils/email_sender.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import logging
from app.config import settings
from app.exceptions import EmailSendingError # Assuming you have a custom exception for email sending failures

# Import Aliyun Direct Mail SDK (ensure you have installed it: pip install alibabacloud_dm20151123)
from alibabacloud_dm20151123.client import Client
from alibabacloud_dm20151123.models import SingleSendMailRequest
from alibabacloud_tea_openapi.models import Config as OpenApiConfig # Use alias to avoid conflict with app.config
from alibabacloud_tea_util.models import RuntimeOptions # 导入 RuntimeOptions

logger = logging.getLogger(__name__)

async def send_email_smtp(recipient_email: str, subject: str, body: str):
    """使用 SMTP 发送邮件。"""
    logger.info(f"Attempting to send email via SMTP to {recipient_email}")
    sender_email = settings.SENDER_EMAIL
    sender_password = settings.SMTP_PASSWORD
    smtp_server = settings.SMTP_SERVER
    smtp_port = settings.SMTP_PORT

    if not all([sender_email, sender_password, smtp_server, smtp_port]):
        logger.error("SMTP configuration is incomplete.")
        raise EmailSendingError("SMTP 配置不完整。")

    # Ensure port is integer
    try:
        smtp_port = int(smtp_port)
    except (ValueError, TypeError):
        logger.error(f"Invalid SMTP port: {settings.SMTP_PORT}")
        raise EmailSendingError("SMTP 端口配置无效。")

    try:
        message = MIMEText(body, 'html', 'utf-8')
        message['From'] = Header(f'您的应用 <{sender_email}>', 'utf-8') # Replace '您的应用' with your app name
        message['To'] = Header(recipient_email, 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        # Use SSL for port 465, otherwise start TLS for port 587 (or 25)
        if smtp_port == 465:
            smtp_obj = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            smtp_obj = smtplib.SMTP(smtp_server, smtp_port)
            smtp_obj.ehlo()
            smtp_obj.starttls()
            smtp_obj.ehlo()

        smtp_obj.login(sender_email, sender_password)
        smtp_obj.sendmail(sender_email, [recipient_email], message.as_bytes())
        smtp_obj.quit()
        logger.info(f"Email sent successfully via SMTP to {recipient_email}")
    except Exception as e:
        logger.error(f"Failed to send email via SMTP to {recipient_email}: {e}")
        raise EmailSendingError(f"通过 SMTP 发送邮件失败: {e}") from e

async def send_email_aliyun(recipient_email: str, subject: str, body: str):
    """使用阿里云邮件服务发送邮件。"""
    logger.info(f"Attempting to send email via Aliyun Direct Mail to {recipient_email}")

    # TODO: Implement Aliyun Direct Mail sending logic here
    # 1. Get Aliyun Access Key ID and Secret from settings
    access_key_id = settings.ALIYUN_EMAIL_ACCESS_KEY_ID
    access_key_secret = settings.ALIYUN_EMAIL_ACCESS_KEY_SECRET
    region = settings.ALIYUN_EMAIL_REGION
    sender_email = settings.SENDER_EMAIL

    if not all([access_key_id, access_key_secret, region, sender_email]):
         logger.error("Aliyun Direct Mail configuration is incomplete.")
         raise EmailSendingError("阿里云邮件服务配置不完整。")

    try:
        # Aliyun SDK Configuration
        config = OpenApiConfig(
            # 您的Access Key ID
            access_key_id=access_key_id,
            # 您的Access Key Secret
            access_key_secret=access_key_secret,
            # Endpoint 请参考阿里云官方文档，这里使用泛型域名，会自动解析到对应区域
            endpoint='dm.aliyuncs.com'
        )

        # 创建 Direct Mail 客户端
        client = Client(config)

        # 创建发送邮件请求
        request = SingleSendMailRequest(
            account_name=sender_email, # 控制台创建的发信地址
            from_alias='思源淘', # 发件人昵称
            address_type=1, # 0: 随机发信地址，1: 控制台创建的固定地址
            reply_to_address=False, # 是否需要回复地址
            to_address=recipient_email, # 收信人地址
            subject=subject, # 邮件标题
            # text_body=body, # 邮件正文
            html_body=body, # 如果是HTML邮件，使用html_body
            # tag_name='...' # 邮件标签
        )

        # 设置 RuntimeOptions，配置超时时间（单位：毫秒）
        runtime_options = RuntimeOptions(
            read_timeout=15000,  # 设置读取超时为 15 秒
            connect_timeout=15000 # 设置连接超时为 15 秒
        )

        # 发送邮件
        # SDK 默认是同步调用，如果需要异步，可能需要查找异步方法或使用其他库
        # 这里直接使用 SDK 的同步方法，因为 send_email_aliyun 是 async 函数，可以在事件循环中运行同步代码
        response = client.single_send_mail_with_options(request, runtime_options)

        # 检查响应是否成功
        # 阿里云 SDK 调用成功通常返回 None 或者一个表示成功的对象，异常会在调用失败时抛出
        # 这里简单记录成功信息，更详细的成功判断可能需要检查响应对象的特定属性
        logger.info(f"Email sent successfully via Aliyun Direct Mail to {recipient_email}.")
        # 你可以根据需要检查 response 对象的内容
        # logger.debug(f"Aliyun Direct Mail response details: {response}")

    except Exception as e:
        logger.error(f"Failed to send email via Aliyun Direct Mail to {recipient_email}: {e}")
        # Catch specific Aliyun SDK exceptions if needed and wrap them
        raise EmailSendingError(f"通过阿里云邮件服务发送邮件失败: {e}") from e

async def send_email(recipient_email: str, subject: str, body: str):
    """
    根据配置发送邮件。

    Args:
        recipient_email: 接收邮件的邮箱地址。
        subject: 邮件主题。
        body: 邮件正文 (可以是纯文本或HTML)。
    """
    if settings.EMAIL_PROVIDER == "smtp":
        await send_email_smtp(recipient_email, subject, body)
    elif settings.EMAIL_PROVIDER == "aliyun":
        await send_email_aliyun(recipient_email, subject, body)
    else:
        logger.error(f"Invalid email provider configured: {settings.EMAIL_PROVIDER}")
        raise EmailSendingError(f"配置的邮件服务提供商无效: {settings.EMAIL_PROVIDER}") 