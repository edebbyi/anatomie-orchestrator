from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Service URLs
    optimizer_service_url: str = "https://optimizer-2ym2.onrender.com"
    generator_service_url: str = "https://anatomie-prompt-generator.onrender.com"
    strategist_service_url: str = "https://anatomie-prompt-strategist.onrender.com"

    # Airtable
    airtable_api_key: str = ""
    airtable_base_id: str = "appW8hvRj3lUrqEH2"
    airtable_structures_table_id: str = "tblPPDf9vlTBv2kyl"

    # Learning cycle
    like_threshold: int = 25
    exploration_rate: float = 0.2

    # Batch generation defaults
    default_batch_ideas: int = 3
    default_num_prompts: int = 30
    default_renderer: str = "ImageFX"

    # Timeouts (seconds)
    train_timeout: int = 600
    score_timeout: int = 120
    update_timeout: int = 30
    strategist_timeout: int = 120
    generator_timeout: int = 60


def get_settings() -> Settings:
    return Settings()
