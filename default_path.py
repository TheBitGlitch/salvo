from pathlib import Path

from platformdirs import user_data_path, user_cache_path


class DefaultPath:
    """Central source of the default paths used by the application."""

    BASE_DIR = Path(__file__).parent

    DATA_DIR = user_data_path("salvo")
    ENDPOINTS_JSON = DATA_DIR / "endpoints.json"
    HISTORY = DATA_DIR / ".history"

    CACHE_DIR = user_cache_path("salvo")
    ENDPOINTS_ETAG = CACHE_DIR / "endpoints.etag"
