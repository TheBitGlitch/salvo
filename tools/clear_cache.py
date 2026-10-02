import shutil

from default_path import DefaultPath
from cli.helpers import register_manage_command


@register_manage_command
def clear_cache() -> None:
    """Removes the application's cache."""
    try:
        shutil.rmtree(DefaultPath.CACHE_DIR)

    except FileNotFoundError:
        print("No cache found.\n")

    except OSError as exc:
        print(f"Failed to clear cache: {exc}\n")

    else:
        print("Cache cleared successfully.\n")
