# src/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """系统全局配置中心"""

    # --- DeepSeek 模型配置 ---
    DEEPSEEK_API_KEY: str = Field(description="DeepSeek API 密钥")
    DEEPSEEK_API_BASE: str = Field(default="https://api.deepseek.com")
    MODEL_FAST: str = Field(default="deepseek-chat", description="快速轻量级模型")
    MODEL_REASONER: str = Field(default="deepseek-v4-pro", description="深度推理与质检模型")

    # --- Gemini 模型配置 --- 
    GEMINI_API_KEY: str = Field(description="Google Gemini API 密钥")
    # 我们使用最新预览版，它在多模态理解（尤其是文档理解）上最强
    MODEL_VISION: str = Field(default="gemini-2.5-flash-lite", description="原生多模态视觉模型")
    # --- MinerU 配置 ---
    MINERU_API_TOKEN: str = Field(default="", description="MinerU 文档解析引擎 Token")
    # --- 外部工具配置 ---
    TAVILY_API_KEY: str | None = Field(default=None, description="Tavily Web Search API Key")

    # --- 本地 RAG 模型路径配置 ---
    EMBEDDING_MODEL_PATH: str = Field(default="./models/bge-m3")
    RERANKER_MODEL_PATH: str = Field(default="./models/bge-reranker-v2-m3")
    CHROMA_DB_DIR: str = Field(default="local_chroma_db")

    # --- 数据流水线目录 ---
    UPLOAD_DIR: str = Field(default="uploads")
    KB_DIR: str = Field(default="knowledge_base")
    ARCHIVE_DIR: str = Field(default="archived_pdfs")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()