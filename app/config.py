from dataclasses import dataclass
from pathlib import Path
import os


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists() or not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        env_key = key.strip()
        env_value = value.strip().strip('"').strip("'")
        if env_key:
            os.environ.setdefault(env_key, env_value)


def _bootstrap_env() -> None:
    project_root = Path(__file__).resolve().parents[1]
    # Prefer .env for local secrets, but support .env.example as a fallback.
    _load_env_file(project_root / ".env")
    _load_env_file(project_root / ".env.example")


_bootstrap_env()


@dataclass(frozen=True)
class Settings:
    app_name: str
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_seconds: int
    upload_max_bytes: int
    output_root: Path


def get_settings() -> Settings:
    return Settings(
        app_name="CODESYS Documentation Agent",
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
        gemini_timeout_seconds=int(os.getenv("GEMINI_TIMEOUT_SECONDS", "45")),
        upload_max_bytes=int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024))),
        output_root=Path(os.getenv("OUTPUT_ROOT", "output")).resolve(),
    )
