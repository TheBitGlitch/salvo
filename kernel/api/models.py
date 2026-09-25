from typing import Literal
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ApiCall:
    """
    Immutable representation of a single API request configuration.

    Attributes:
        source: Identifier of the API source.
        url: Target endpoint URL.
        method: HTTP method used for the request.
        data: Form-data payload, if provided.
        json: JSON payload, if provided.

    Notes:
        Either `data` or `json` may be provided, but not both.
    """

    source: str
    url: str
    method: Literal["POST", "GET"]
    data: dict | None = None
    json: dict | None = None


@dataclass(slots=True)
class ApiSlot:
    """
    Runtime state associated with an API call.

    Attributes:
        index: Position of the slot in the API pool.
        call: API request configuration associated with the slot.
        capacity: Execution capacity per phone number per cycle.
        ticket: Weight used by the API pool to prioritize API selection.
        strikes: Number of failed attempts or recorded violations.
        was_jailed: Whether the slot has been jailed.
        jailed_until: Timestamp until which the slot remains jailed.
    """

    index: int
    call: ApiCall
    capacity: int = 0
    ticket: int = 0
    strikes: int = 0
    was_jailed: bool = False
    jailed_until: float | None = None
