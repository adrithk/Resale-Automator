"""Load backend-only configuration without replacing explicit shell settings."""

from pathlib import Path

from dotenv import load_dotenv


def load_backend_environment() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False, interpolate=False)
