import shutil

from default_path import DefaultPath


def clear_data() -> None:
    """Clears the application's data."""
    confirm = input(
        "This will permanently delete all salvo data.\nProceed (y/n)? "
    ).lower()

    if confirm not in ("y", "yes"):
        return

    try:
        shutil.rmtree(DefaultPath.DATA_DIR)

        if DefaultPath.CACHE_DIR.exists():
            shutil.rmtree(DefaultPath.CACHE_DIR)

    except FileNotFoundError:
        print("No data found.\n")

    except OSError as exc:
        print(f"Failed to clear data: {exc}\n")

    else:
        print("Data cleared successfully.\n")


# CLI entry point for this tool; used by the manage subcommand for automatic discovery.
COMMAND = clear_data
