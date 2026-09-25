import shutil

from default_path import DefaultPath


def clear_cache() -> None:
    """Removes the application's cache."""
    try:
        shutil.rmtree(DefaultPath.CACHE_DIR)

    except FileNotFoundError:
        pass

    except OSError as exc:
        print(f"Failed to clear cache: {exc}")

    else:
        print("Cache cleared successfully.")


# CLI entry point for this tool; used by the manage subcommand for automatic discovery.
COMMAND = clear_cache
