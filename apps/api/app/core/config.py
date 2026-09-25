"""Application settings, loaded from environment variables (and a repo-root `.env` in local dev)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

from pydantic import BeforeValidator, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# apps/api/app/core/config.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]

_DURATION_RE = re.compile(r"^(\d+)\s*([smhd]?)$")
_DURATION_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}

_RATE_RE = re.compile(r"^(\d+)\s*/\s*(second|minute|hour|day)$")
_RATE_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_duration(value: object) -> int:
    """`15m`, `7d`, `3600` (seconds) -> seconds."""
    if isinstance(value, int):
        return value
    match = _DURATION_RE.match(str(value).strip().lower())
    if not match:
        raise ValueError("duration must look like 30s, 15m, 12h, 7d or a number of seconds")
    return int(match.group(1)) * _DURATION_UNITS[match.group(2)]


class RateLimit(NamedTuple):
    limit: int
    window_seconds: int


def parse_rate_limit(value: object) -> RateLimit:
    """`5/minute` -> RateLimit(5, 60)."""
    if isinstance(value, RateLimit):
        return value
    match = _RATE_RE.match(str(value).strip().lower())
    if not match:
        raise ValueError("rate limit must look like 5/minute (units: second, minute, hour, day)")
    return RateLimit(int(match.group(1)), _RATE_UNITS[match.group(2)])


Duration = Annotated[int, BeforeValidator(parse_duration)]
# NoDecode: a NamedTuple looks "complex" to pydantic-settings, which would try to JSON-decode
# `5/minute` before our parser ever sees it.
Rate = Annotated[RateLimit, NoDecode, BeforeValidator(parse_rate_limit)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `METRICS_TOKEN=` in .env means "unset", not an empty secret
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime -------------------------------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    docs_enabled: bool = True

    # --- Infrastructure ------------------------------------------------------------------
    database_url: str
    redis_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_echo: bool = False
    # Serverless hosts (Vercel) freeze the process between requests: no connection pool, one connection per use.
    db_serverless: bool = False

    # --- Auth ----------------------------------------------------------------------------
    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_expire: Duration = 15 * 60
    jwt_refresh_expire: Duration = 7 * 24 * 3600
    # A refresh token rotated less than this long ago is treated as a benign race
    # (two tabs refreshing at once) rather than as token theft.
    refresh_reuse_grace_seconds: int = 10
    email_verify_expire: Duration = 24 * 3600
    password_reset_expire: Duration = 3600
    # Argon2id cost parameters (defaults follow the OWASP baseline; tests lower them).
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    argon2_parallelism: int = 4

    # --- HTTP ----------------------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    frontend_url: str = "http://localhost:3000"
    max_request_bytes: int = 1_048_576
    # Admin endpoints carry whole problems including large hidden test files (only for requests bearing a token).
    admin_max_request_bytes: int = 8_388_608
    # Number of trusted reverse proxies in front of the API (0 = use the socket peer address).
    # Only that many right-most X-Forwarded-For entries are trusted, so clients cannot spoof their IP.
    trusted_proxy_count: int = 0
    cookie_secure: bool | None = None  # None -> True in production, False otherwise
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    metrics_token: SecretStr | None = None

    # --- Rate limiting -------------------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_login: Rate = RateLimit(5, 60)  # per IP
    rate_limit_login_account: Rate = RateLimit(10, 3600)  # per target account
    rate_limit_register: Rate = RateLimit(5, 60)  # per IP
    rate_limit_password_reset: Rate = RateLimit(5, 3600)  # per IP and per email
    rate_limit_general: Rate = RateLimit(300, 60)  # per IP, all /api routes
    rate_limit_submit: Rate = RateLimit(10, 60)  # per user
    rate_limit_run: Rate = RateLimit(20, 60)  # per user
    rate_limit_ai: Rate = RateLimit(20, 3600)  # per user, across every AI feature — local inference is expensive
    rate_limit_community_post: Rate = RateLimit(10, 60)  # per user — discussions + comments share this budget
    rate_limit_community_report: Rate = RateLimit(10, 3600)  # per user — reports are rarer and easier to abuse
    rate_limit_community_vote: Rate = RateLimit(60, 60)  # per user — votes are cheap but still worth capping

    # --- SahuJudge -----------------------------------------------------------------------
    submission_max_source_bytes: int = 65_536
    run_max_input_bytes: int = 65_536
    # Submissions a user may have queued or running at once; stops one account flooding the judge queue.
    max_inflight_submissions: int = 3
    # Jobs that stay QUEUED/RUNNING longer than this are failed by the reaper (the worker died or the queue lost them).
    judge_stale_after: Duration = 15 * 60
    # False where no judge worker runs (e.g. the free serverless deployment): submitting then fails cleanly with 503
    # JUDGE_UNAVAILABLE instead of leaving submissions queued forever.
    judge_enabled: bool = True
    # `celery`: API enqueues, a worker with a Docker sandbox judges (docker compose). `vercel`: no worker - the API
    # judges inside the request, running the code in a Vercel Sandbox microVM (needs a snapshot, see docs/judge.md).
    judge_backend: Literal["celery", "vercel"] = "celery"
    vercel_sandbox_snapshot: str = ""
    run_result_ttl: Duration = 10 * 60
    ws_ticket_ttl: Duration = 30
    # Sandbox (used by the judge worker only; the API never executes code).
    sandbox_docker_host: str | None = None  # DOCKER_HOST of the DEDICATED sandbox daemon, never the host's socket
    sandbox_docker_bin: str = "docker"
    sandbox_image: str = "sahucodex/runner:1"
    sandbox_runtime: str | None = None  # e.g. "runsc" to run sandboxes under gVisor
    sandbox_pids_limit: int = 64
    sandbox_cpus: float = 1.0
    sandbox_tmpfs_mb: int = 64
    sandbox_auto_build: bool = True  # build the runner image into the sandbox daemon on worker start if it is missing
    sandbox_build_context: str = "infrastructure/docker/runner"
    judge_max_output_bytes: int = 1_048_576  # per test; more is a runtime error
    judge_max_stderr_bytes: int = 8_192
    judge_max_compile_output_bytes: int = 8_192
    judge_max_tests: int = 200

    # --- SahuCodeX AI --------------------------------------------------------------------
    # Local/open-source first: Ollama needs no key and no paid API. `openrouter` is a hosted fallback for deployments
    # with no machine to run Ollama on (e.g. this platform's own free Vercel deployment) — same AiProvider protocol,
    # opt-in, and its key is read only from OPENROUTER_API_KEY (never hardcoded, never logged). AI_PROVIDER exists so
    # a deployment can name a provider it hasn't configured yet (e.g. during setup) without that being a code change.
    ai_provider: Literal["ollama", "openrouter", "none"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""  # empty = "no model chosen yet"; every AI endpoint then answers 503 AI_UNAVAILABLE
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = ""  # empty = "no model chosen yet", same contract as ollama_model
    ai_request_timeout: Duration = 60  # local inference is slow, especially on CPU; still a hard ceiling
    ai_max_prompt_chars: int = 8_000  # per message / code snippet sent to the model
    ai_max_response_tokens: int = 800  # Ollama's num_predict / OpenRouter's max_tokens — bounds latency and cost
    ai_max_conversations: int = 50  # per user
    ai_max_messages_per_conversation: int = 100

    # --- RAG (phase 8) ---------------------------------------------------------------------
    # Optional, like AI itself: an unset QDRANT_URL means "no vector search configured" and every RAG-dependent
    # feature (semantic problem search, "similar problems", retrieval-augmented chat context) is simply skipped —
    # never a fake or empty-looking result standing in for a real one. Embeddings are Ollama's own /api/embeddings
    # (no extra service beyond what AI already needs); OLLAMA_EMBED_MODEL is deliberately separate from
    # OLLAMA_MODEL since a good chat model and a good embedding model are rarely the same one.
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "sahucodex_problems"
    ollama_embed_model: str = "nomic-embed-text"
    rag_top_k: int = 5  # candidates returned by a similarity search

    # --- Email ---------------------------------------------------------------------------
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "SahuCodeX <no-reply@sahucodex.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True

    # --- Validators ----------------------------------------------------------------------
    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                value = "postgresql+asyncpg://" + value[len(prefix) :]
                break
        if not value.startswith("postgresql+asyncpg://"):
            return value
        # Hosted Postgres (Neon, ...) hands out libpq-style URLs. asyncpg rejects `sslmode`/`channel_binding`
        # and wants `ssl` instead.
        url, _, query = value.partition("?")
        params = [pair for pair in query.split("&") if pair]
        kept: list[str] = []
        for pair in params:
            key, _, val = pair.partition("=")
            if key == "sslmode":
                if val not in ("disable", "allow"):
                    kept.append("ssl=require")
            elif key != "channel_binding":
                kept.append(pair)
        return url + ("?" + "&".join(kept) if kept else "")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _check_safety(self) -> Settings:
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters (try: openssl rand -hex 32)")
        if self.app_env == "production":
            if "change-me" in self.jwt_secret.get_secret_value().lower():
                raise ValueError("JWT_SECRET still contains the placeholder value; set a real secret")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be disabled in production")
            if self.email_backend == "console":
                # The console mailer prints one-time links, which are credentials.
                raise ValueError("EMAIL_BACKEND=console is not allowed in production; configure SMTP")
        return self

    # --- Derived -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def use_secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def allowed_origins(self) -> set[str]:
        return {*self.cors_origins, self.frontend_url.rstrip("/")}

    @property
    def ai_configured(self) -> bool:
        if self.ai_provider == "ollama":
            return bool(self.ollama_model)
        if self.ai_provider == "openrouter":
            return bool(self.openrouter_model) and self.openrouter_api_key is not None
        return False

    @property
    def rag_configured(self) -> bool:
        return bool(self.qdrant_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
