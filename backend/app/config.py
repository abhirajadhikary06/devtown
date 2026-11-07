from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./devtown.db"
    secret_key: str = "dev-only-change-me"
    token_encryption_key: str = ""          # Fernet key; derived from secret_key when empty (set it in production)
    github_client_id: str = ""
    github_client_secret: str = ""
    github_seed_token: str = ""          # optional PAT used to seed showcase cities from public profiles; falls back to a stored login token
    github_readme_token: str = ""        # optional token for the configured personal README repository
    github_readme_repository: str = ""   # owner/repository allowed to receive DevTown banner updates
    public_base_url: str = "http://localhost:5173"   # used in the README Markdown snippet
    frontend_url: str = "http://localhost:5173"
    cookie_secure: bool = False


settings = Settings()
