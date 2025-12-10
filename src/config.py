from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    optimizer_service_url: str = ""
    generator_service_url: str = ""
    airtable_api_key: str = ""
    airtable_base_id: str = "appW8hvRj3lUrqEH2"
    airtable_structures_table_id: str = "tblPPDf9vlTBv2kyl"
    like_threshold: int = 25
    exploration_rate: float = 0.2
    train_timeout: int = 600
    score_timeout: int = 120
    update_timeout: int = 30


def get_settings() -> Settings:
    return Settings()
