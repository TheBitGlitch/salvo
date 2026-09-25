import pytest

from kernel.api.validator import ApiValidator


class TestApiValidation:

    def test_valid_api_config(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
        }

        assert ApiValidator.validate(config) is True

    @pytest.mark.parametrize("source", ["", "   ", "#bad", "   #hidden"])
    def test_invalid_source(self, source) -> None:
        config = {
            "source": source,
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    @pytest.mark.parametrize("value", [0, -1, -10])
    def test_invalid_capacity_ticket(self, value):
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 20,
            "ticket": value,
        }
        assert ApiValidator.validate(config) is False

    def test_missing_required_field(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
        }
        assert ApiValidator.validate(config) is False

    def test_bool_not_allowed_as_int(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": True,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    def test_invalid_method(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "DELETE",
            "capacity": 10,
            "ticket": 5,
        }
        assert ApiValidator.validate(config) is False

    def test_both_json_and_data_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": {},
            "data": {},
        }
        assert ApiValidator.validate(config) is False

    def test_valid_payload_none(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": None,
            "data": None,
        }
        assert ApiValidator.validate(config) is True

    def test_valid_single_json_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": {},
            "data": None,
        }
        assert ApiValidator.validate(config) is True

    def test_valid_single_json_payload(self) -> None:
        config = {
            "source": "test.com",
            "url": "https://example.com",
            "method": "GET",
            "capacity": 10,
            "ticket": 5,
            "json": None,
            "data": {},
        }
        assert ApiValidator.validate(config) is True
