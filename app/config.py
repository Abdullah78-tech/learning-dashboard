from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_name: str = 'Learning Dashboard'
    secret_key: str
    base_url: str = 'http://localhost:8000'
    secure_cookies: bool = False
    database_url: str = 'sqlite:///./learning.db'
    google_client_id: str = ''
    google_client_secret: str = ''
    smtp_host: str = 'smtp.gmail.com'
    smtp_port: int = 587
    smtp_username: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_security: Literal['starttls', 'ssl'] = 'starttls'

    @model_validator(mode='after')
    def validate_configuration(self):
        if len(self.secret_key) < 32 or self.secret_key.startswith('replace-'):
            raise ValueError('Set SECRET_KEY to a random value of at least 32 characters in .env.')
        self.base_url = self.base_url.rstrip('/')
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('BASE_URL must be an origin, e.g. http://localhost:8000.')
        if parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            if parsed.scheme != 'https' or not self.secure_cookies:
                raise ValueError('Non-local use requires HTTPS and SECURE_COOKIES=true.')
        return self

    @property
    def google_enabled(self):
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def mail_enabled(self):
        return bool(self.smtp_username and self.smtp_password and self.smtp_from)


@lru_cache
def get_settings():
    return Settings()
