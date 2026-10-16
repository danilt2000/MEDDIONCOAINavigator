from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    openai_api_key: str = ""
    llm_model: str = "gpt-5.4-mini"
    embed_model: str = "text-embedding-3-small"
    embed_dims: int = 1536
    llm_enabled: bool = True

    iris_host: str = "localhost"
    iris_port: int = 1972
    iris_namespace: str = "FHIRSERVER"
    iris_user: str = "SuperUser"
    iris_password: str = "SYS"
    fhir_base: str = "http://localhost:52773/fhir/r4"
    fhir_enabled: bool = True

    data_dir: Path = REPO_ROOT / "data"
    cache_dir: Path = REPO_ROOT / "backend" / "cache"
    api_port: int = 8100
    meddi_mock_url: str = "http://localhost:8100/mock/meddi"
    timezone: str = "Europe/Prague"


settings = Settings()
