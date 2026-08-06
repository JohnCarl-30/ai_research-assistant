from functools import lru_cache

from pydantic_settings import BaseSettings

TECH_KEYWORDS: list[str] = [
    # Languages
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "rust",
    "c",
    "c++",
    "c#",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "r",
    # Frontend
    "react",
    "vue",
    "angular",
    "svelte",
    "next.js",
    "nuxt",
    "html",
    "css",
    # Backend
    "node.js",
    "express",
    "django",
    "flask",
    "fastapi",
    "spring",
    "rails",
    "laravel",
    # Cloud/DevOps
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "terraform",
    "ansible",
    "jenkins",
    "github actions",
    "ci/cd",
    # Data
    "sql",
    "postgresql",
    "mongodb",
    "redis",
    "elasticsearch",
    "graphql",
    "rest api",
    # AI/ML
    "machine learning",
    "deep learning",
    "tensorflow",
    "pytorch",
    "llm",
]

# Phrases first to avoid partial matches
TECH_PHRASES: list[str] = [
    "machine learning",
    "deep learning",
    "github actions",
    "rest api",
    "next.js",
    "ci/cd",
]

TECH_SINGLE_WORDS: list[str] = [kw for kw in TECH_KEYWORDS if kw not in TECH_PHRASES]


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str

    # LangSmith
    langsmith_api_key: str | None = None
    langsmith_project: str = "scout"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/scout"

    # Gmail SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_recipient: str = ""

    # Scraping
    headless_browser: bool = True

    # CORS
    cors_origins: list[str] = ["*"]

    # Tag extraction
    tech_keywords: list[str] = TECH_KEYWORDS

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
