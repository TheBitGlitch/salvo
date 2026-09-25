import json
from typing import Any
from pathlib import Path

from .validator import ApiValidator
from .models import ApiCall, ApiSlot
from .exceptions import (
    LoadApiEndpointsError,
    ApiEndpointsNotFoundError,
    NoValidApiEndpointFoundError,
)


class ApiFactory:
    """
    Creates API slots from endpoint configurations.

    The factory loads endpoint configurations from the specified JSON file,
    validates them, injects the provided context (e.g. phone), and creates an
    `ApiSlot` for each valid endpoint.
    """

    def __init__(self, endpoints_path: Path, context: dict) -> None:
        self._endpoints_path = endpoints_path
        self._context = context

        self._dropped_count = 0
        self._api_slots: list[ApiSlot] = []

    @property
    def endpoints_path(self) -> Path:
        return self._endpoints_path

    @property
    def dropped_count(self) -> int:
        """Returns the number of invalid endpoints dropped during the last build."""
        return self._dropped_count

    @property
    def api_slots(self) -> tuple[ApiSlot, ...]:
        """Returns the API slots created by the factory."""
        return tuple(self._api_slots)

    @property
    def slot_count(self) -> int:
        """Returns the number of API slots created by the factory."""
        return len(self._api_slots)

    def _load_endpoints(self) -> list[dict]:
        """
        Loads endpoint configurations from the configured endpoints JSON file.

        Returns:
            A list of raw endpoint configuration dictionaries.

        Raises:
            ApiEndpointsNotFoundError: If the file does not exist.
            LoadApiEndpointsError: If the file contains invalid JSON.
        """
        try:
            with open(self._endpoints_path, "r", encoding="utf-8") as f:
                return json.load(f)

        except FileNotFoundError as exc:
            raise ApiEndpointsNotFoundError(self._endpoints_path) from exc

        except json.JSONDecodeError as exc:
            raise LoadApiEndpointsError(self._endpoints_path) from exc

    def _validate_endpoints(self, endpoints: list[dict]) -> list[dict]:
        """
        Validates endpoint configurations and drops invalid endpoints.

        Returns:
            A list containing only valid endpoint configurations.

        Raises:
            NoValidApiEndpointFoundError: If no valid endpoints remain.
        """
        valid_endpoints = []

        for endpoint in endpoints:
            if ApiValidator.validate(endpoint):
                valid_endpoints.append(endpoint)

            else:
                self._dropped_count += 1

        if not valid_endpoints:
            raise NoValidApiEndpointFoundError(self._endpoints_path)

        return valid_endpoints

    def _create_slot(self, index: int, endpoint: dict) -> ApiSlot:
        """
        Creates an API slot from an endpoint configuration.

        Args:
            index: Position assigned to the API slot.
            endpoint: Valid endpoint configuration.

        Returns:
            An `ApiSlot` representing the configured API endpoint.
        """
        return ApiSlot(
            index=index,
            call=ApiCall(
                source=endpoint["source"],
                url=endpoint["url"],
                method=endpoint["method"],
                json=endpoint.get("json"),
                data=endpoint.get("data"),
            ),
            capacity=endpoint["capacity"],
            ticket=endpoint["ticket"],
        )

    def _inject_context(self, obj, context) -> Any:
        """
        Recursively injects context values into an endpoint configuration.

        Strings are formatted using the provided context. Dictionaries
        and lists are traversed recursively. Strings containing unknown
        placeholders are left unchanged.
        """
        if isinstance(obj, dict):
            return {k: self._inject_context(v, context) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._inject_context(v, context) for v in obj]

        if isinstance(obj, str):
            try:
                return obj.format(**context)

            except KeyError:
                return obj

        return obj

    def build(self) -> None:
        """
        Builds the API slots from the endpoint configurations.

        Existing API slots and dropped endpoint count are reset before rebuilding.
        Endpoint configurations are then loaded, validated, formatted with
        the configured context, and converted into API slots.
        """
        self._api_slots.clear()
        self._dropped_count = 0

        loaded_endpoints = self._load_endpoints()
        validated_endpoints = self._validate_endpoints(loaded_endpoints)

        for index, endpoint in enumerate(validated_endpoints, start=1):
            self._api_slots.append(
                self._create_slot(
                    index=index,
                    endpoint=self._inject_context(endpoint, self._context),
                )
            )
