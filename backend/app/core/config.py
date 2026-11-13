import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Get the backend root directory
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Application configuration
    app_name: str = "AgriGrade AI API"
    model_variant: str = "field"

    # Disease classification model
    model_path: str = "artifacts/resnet18_augmented_field.pt"
    class_mapping_path: str = "artifacts/class_mapping.json"

    # Severity estimation model
    severity_model_path: str = "artifacts/severity_head.pt"

    # Image upload configuration
    max_upload_mb: int = 10
    frontend_origin: str = "http://localhost:5173"

    # Weather API configuration
    openweathermap_api_key: str = ""

    # Market price API configuration
    market_api_base_url: str = (
        "https://api.data.gov.in/resource/"
        "9ef84268-d588-465a-a308-a864a43d0070"
    )
    market_api_key: str = ""
    data_gov_api_key: str = ""

    # Load environment variables from the backend .env file
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )

    @property
    def effective_market_api_key(self) -> str:
        return (
            self.market_api_key
            or self.data_gov_api_key
            or os.getenv("DATA_GOV_API_KEY", "")
            or os.getenv("MARKET_API_KEY", "")
        ).strip()

    # Return the full path to the disease model
    @property
    def resolved_model_path(self) -> Path:
        return BASE_DIR / self.model_path

    # Return the full path to the class mapping
    @property
    def resolved_mapping_path(self) -> Path:
        return BASE_DIR / self.class_mapping_path

    # Return the full path to the severity model
    @property
    def resolved_severity_model_path(self) -> Path:
        return BASE_DIR / self.severity_model_path


# Create the settings instance
settings = Settings()
