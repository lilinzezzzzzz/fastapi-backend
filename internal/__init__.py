import os
from pathlib import Path

BASE_DIR: Path = Path(__file__).parent.parent.absolute()
APP_ENV: str = str.lower(os.getenv("APP_ENV", "unknown"))
