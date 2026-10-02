import shutil

from default_path import DefaultPath
from cli.helpers import register_manage_command


@register_manage_command
def clear_data() -> None:
    """Clears the application's data."""
    proceed = input(
        "This will permanently delete all salvo data. Proceed (y/n)? "
    ).lower()

    if proceed not in ("y", "yes"):
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
