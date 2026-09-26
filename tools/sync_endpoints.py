import os
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from cyclopts.parameter import Parameter

from default_path import DefaultPath

DEFAULT_REMOTE_SOURCE = (
    "https://raw.githubusercontent.com/TheBitGlitch/"
    "salvo-endpoints/refs/heads/main/endpoints.json"
)


class SyncResult(StrEnum):
    """Represents the result of an endpoint synchronization operation."""

    SUCCEEDED = "succeeded"
    UNCHANGED = "unchanged"
    FAILED = "failed"


class Synchronizer:
    """Synchronizes the endpoint configuration with a remote source."""

    def __init__(self, source_url: str, dest_path: Path, force: bool) -> None:
        """
        Initializes the endpoint synchronizer.

        Args:
            source_url: URL of the remote endpoint configuration.
            dest_path: Path where the endpoint configuration is stored.
            force: Whether to download the configuration regardless of the stored ETag.
        """
        self._source_url = source_url
        self._dest_path = dest_path
        self._force = force

        self._etag_file = DefaultPath.ENDPOINTS_ETAG
        self._init_directories()

    def _init_directories(self) -> None:
        self._dest_path.parent.mkdir(parents=True, exist_ok=True)

        DefaultPath.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _read_etag(self) -> str | None:
        if not self._etag_file.is_file():
            return None

        try:
            etag = self._etag_file.read_text(encoding="utf-8").strip()

        except OSError:
            return None

        return etag or None

    def _write_etag(self, etag: str) -> None:
        temp_path = self._etag_file.with_suffix(self._etag_file.suffix + ".tmp")

        try:
            temp_path.write_text(etag, encoding="utf-8")

            temp_path.replace(self._etag_file)

        finally:
            temp_path.unlink(missing_ok=True)

    def _build_request(self) -> Request:
        request = Request(url=self._source_url, method="GET")
        request.add_header("User-Agent", "Mozilla/5.0/Salvo")

        if not self._force:
            etag = self._read_etag()

            if etag:
                request.add_header("If-None-Match", etag)

        return request

    def _validate_json(self, content: bytes) -> None:
        """
        Validates the endpoint configuration.

        Args:
            content: Raw endpoint configuration content.

        Raises:
            ValueError: If the content is not valid UTF-8 or does not
                contain valid JSON.
        """
        try:
            json.loads(content.decode("utf-8"))

        except UnicodeDecodeError as exc:
            raise ValueError("Endpoint configuration is not valid UTF-8.") from exc

        except json.JSONDecodeError as exc:
            raise ValueError("Endpoint configuration contains invalid JSON.") from exc

    def _write_content_safely(self, content: bytes) -> None:
        temp_path = self._dest_path.with_suffix(self._dest_path.suffix + ".tmp")

        try:
            with open(temp_path, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            temp_path.replace(self._dest_path)

        finally:
            temp_path.unlink(missing_ok=True)

    def _download(self) -> tuple[bytes, str | None] | None:
        request = self._build_request()

        try:
            with urlopen(request, timeout=15) as response:
                content = response.read()
                etag = response.headers.get("ETag")

                return content, etag

        except HTTPError as exc:

            if exc.code == 304:
                return None

            raise

    def sync(self) -> SyncResult:
        """
        Synchronizes the endpoint configuration with the remote source.

        Returns:
            The result of the synchronization operation.
        """
        try:
            download_result = self._download()

            if download_result is None:
                return SyncResult.UNCHANGED

            content, etag = download_result

            self._validate_json(content)
            self._write_content_safely(content)

            if etag:
                self._write_etag(etag)

            return SyncResult.SUCCEEDED

        except HTTPError as exc:
            print(f"HTTP error while synchronizing endpoints: {exc}\n")

        except URLError as exc:
            print(f"URL error while synchronizing endpoints: {exc}\n")

        except ValueError as exc:
            print(f"Invalid endpoint configuration: {exc}\n")

        except OSError as exc:
            print(f"File error while synchronizing endpoints: {exc}\n")

        except Exception as exc:
            print(f"Unexpected error while synchronizing endpoints: {exc}\n")

        return SyncResult.FAILED


def sync_endpoints(
    source: Annotated[
        str,
        Parameter(
            name=["-s", "--source"],
            help="URL of the remote endpoint configuration.",
        ),
    ] = DEFAULT_REMOTE_SOURCE,
    force: Annotated[
        bool,
        Parameter(
            name=["-f", "--force"],
            help="Download the endpoint configuration without using the stored ETag.",
        ),
    ] = False,
) -> None:
    """Synchronizes the local endpoint configuration with the remote source."""

    synchronizer = Synchronizer(
        source_url=source, dest_path=DefaultPath.ENDPOINTS_JSON, force=force
    )

    result = synchronizer.sync()

    if result is SyncResult.SUCCEEDED:
        print("Endpoint configuration synchronized successfully.\n")

    elif result is SyncResult.UNCHANGED:
        print("Endpoint configuration is already up to date.\n")

    else:
        print("Endpoint configuration synchronization failed.\n")


# CLI entry point for this tool; used by the manage subcommand for automatic discovery.
COMMAND = sync_endpoints
