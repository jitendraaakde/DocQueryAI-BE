"""Application configuration settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "DocQuery AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SQL_ECHO: bool = False  # Set to True to see SQL queries in logs
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "docquery"
    POSTGRES_SSLMODE: Optional[str] = None  # Set to 'require' for NeonDB
    
    @property
    def DATABASE_URL(self) -> str:
        base_url = f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        if self.POSTGRES_SSLMODE:
            return f"{base_url}?sslmode={self.POSTGRES_SSLMODE}"
        return base_url
    
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        base_url = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        if self.POSTGRES_SSLMODE:
            return f"{base_url}?ssl={self.POSTGRES_SSLMODE}"
        return base_url
    
    # Weaviate
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_API_KEY: Optional[str] = None
    
    @property
    def WEAVIATE_URL(self) -> str:
        return f"http://{self.WEAVIATE_HOST}:{self.WEAVIATE_PORT}"
    
    # JWT
    JWT_SECRET_KEY: str = "your-jwt-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: list = ["pdf", "txt", "doc", "docx", "md"]
    
    # AI/LLM
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "groq"  # groq, gemini, or openai
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # Best for RAG
    
    # Jina Embeddings (free tier: 1M tokens/month)
    JINA_API_KEY: Optional[str] = None
    
    # CORS - comma-separated list of origins
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    @property
    def CORS_ORIGINS_LIST(self) -> list:
        """Parse CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
    
    # Supabase S3-Compatible Storage
    SUPABASE_S3_ACCESS_KEY: Optional[str] = None
    SUPABASE_S3_SECRET_KEY: Optional[str] = None
    SUPABASE_S3_ENDPOINT: Optional[str] = None
    SUPABASE_S3_REGION: str = "ap-south-1"
    SUPABASE_BUCKET: str = "documents"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "your-email-user"
    SMTP_PASSWORD: str = "your-email-password"
    FROM_EMAIL: str = "your-email-user"
    
    class Config:
        env_file = "../.env"  # .env is in project root, not backend folder
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars like NEXT_PUBLIC_*, CONNECTION_STRING, etc.


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
