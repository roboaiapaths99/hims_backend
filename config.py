from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Database
    MONGODB_URI: str = "mongodb://localhost:27017/hmis_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    JWT_SECRET: str = "hmis_platform_jwt_secret_key_change_in_production_2026"
    JWT_REFRESH_SECRET: str = "hmis_platform_jwt_refresh_secret_key_change_in_production_2026"
    JWT_EXPIRY_HOURS: int = 24
    JWT_REFRESH_EXPIRY_DAYS: int = 7
    
    # Inventory App Integration
    INVENTORY_API_BASE_URL: str = "https://inventory.agpkacademy.in"
    INVENTORY_BRIDGE_API_KEY: str = "test_bridge_api_key_123456"
    
    # DMS Integration
    DMS_API_BASE_URL: str = "http://localhost:8000"
    DMS_BRIDGE_API_KEY: str = "change-me-long-random-secret"
    DMS_WEBHOOK_SECRET: str = "change-me-webhook-secret"
    DMS_INTEGRATION_ENABLED: bool = True
    DMS_REQUEST_TIMEOUT_SECONDS: int = 15
    
    # Application settings
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8002
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:3000,http://localhost:8083,http://127.0.0.1:8083"

    
    # PayU Configuration
    PAYU_MERCHANT_KEY: Optional[str] = None
    PAYU_MERCHANT_SALT: Optional[str] = None
    PAYU_ENV: str = "test"
    PAYU_SUCCESS_URL: str = "http://localhost:3000/payment/success"
    PAYU_FAILURE_URL: str = "http://localhost:3000/payment/failure"
    
    # Jitsi Configuration
    JITSI_DOMAIN: str = "meet.jit.si"
    
    # ABDM Sandbox Configuration
    ABDM_CLIENT_ID: Optional[str] = None
    ABDM_CLIENT_SECRET: Optional[str] = None
    ABDM_GATEWAY_URL: str = "https://dev.abdm.gov.in"
    
    # Sandbox Co GSTIN Verification Configuration
    SANDBOX_CO_API_KEY: Optional[str] = None
    
    # Gemini Configuration
    GEMINI_API_KEY: Optional[str] = None
    
    # S3 Storage Configuration
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION_NAME: Optional[str] = None

    # WhatsApp Configuration
    WHATSAPP_API_URL: Optional[str] = None
    WHATSAPP_API_TOKEN: Optional[str] = None

    # Expo Push Notifications
    EXPO_ACCESS_TOKEN: Optional[str] = None
    
    # MetaReach SMS Gateway Configuration
    METAREACH_API_BASE_URL: str = "https://sms.metareach.in/vb/apikey.php"
    METAREACH_API_KEY: Optional[str] = None
    METAREACH_SENDER_ID: str = "HIMSOP"
    METAREACH_TEMPLATE_ID: Optional[str] = None
    METAREACH_OTP_ROUTE: str = "otp"
    METAREACH_ENABLED: bool = False
    
    # Local Development Helpers (must be explicitly enabled via .env)
    DEV_OTP_BYPASS: bool = False
    DEV_FAKE_SMS: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True, 
        extra="ignore",
        env_file_encoding='utf-8',
        env_ignore_empty=True
    )

settings = Settings()
