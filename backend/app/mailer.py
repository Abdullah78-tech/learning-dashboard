import smtplib
import ssl
from email.message import EmailMessage


class DeliveryError(Exception):
    pass


def send_otp(settings, recipient, code):
    if not settings.mail_enabled:
        raise DeliveryError('Email delivery is not configured.')
    message = EmailMessage()
    message['Subject'] = f'{settings.app_name}: verify your email'
    message['From'] = settings.smtp_from
    message['To'] = recipient
    message.set_content(
        f'Your {settings.app_name} verification code is: {code}\n\n'
        'This code expires in 10 minutes and can be used once.\n'
        'If you did not request this, you can ignore this email.\n'
        'Never share this code with anyone.'
    )
    try:
        context = ssl.create_default_context()
        if settings.smtp_security == 'ssl':
            connection = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context)
        else:
            connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        with connection as smtp:
            if settings.smtp_security == 'starttls':
                smtp.starttls(context=context)
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # Do not return provider errors, credentials, or OTPs to the browser/logs.
        raise DeliveryError('Could not send the verification email. Please try again later.') from exc
