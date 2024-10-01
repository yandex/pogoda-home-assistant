"""Tests for updater."""

import pytest
from homeassistant.components.weather import ATTR_FORECAST_NATIVE_TEMP

from custom_components.yandex_pogoda.const import ATTR_MIN_FORECAST_TEMPERATURE
from custom_components.yandex_pogoda.updater import WeatherUpdater


scenarios = {
    "test_data.json": [
        ("condition", "sunny"),
        ("yandex_condition", "CLEAR"),
        ("feelsLike", 36),
        ("icon", "png.png"),
        ("temperature", 31),
        ("windAngle", 244),
        ("windGust", 9.1),
        ("windSpeed", 5.8),
        ("yandex_condition_icon", "mdi:weather-sunny"),
        (ATTR_MIN_FORECAST_TEMPERATURE, 25),
    ],
}


forecasts_data = [
    ([{ATTR_FORECAST_NATIVE_TEMP: 10}], 10),
    (
        [
            {ATTR_FORECAST_NATIVE_TEMP: 10},
            {ATTR_FORECAST_NATIVE_TEMP: 5},
        ],
        5,
    ),
    (
        [
            {ATTR_FORECAST_NATIVE_TEMP: 5},
            {ATTR_FORECAST_NATIVE_TEMP: 10},
        ],
        5,
    ),
    ([], None),
]


def pytest_generate_tests(metafunc):
    """Generate test data for different API responses."""
    tests = []
    for data, _tests in scenarios.items():
        tests += ((data, *t) for t in _tests)
    if "_bypass_get_data" in metafunc.fixturenames:
        metafunc.parametrize(
            "_bypass_get_data, key, value", tests, indirect=["_bypass_get_data"]
        )


@pytest.mark.asyncio
async def test_update(hass, key, value, _bypass_get_data):
    """Test update action."""
    w = WeatherUpdater(0, 0, "", hass, "test_device")
    result = await w.update()
    assert result[key] == value


@pytest.mark.parametrize("forecasts, expected", forecasts_data)
def test_min_forecast_temperature(hass, forecasts, expected):
    """Test min forecast temperature getter."""
    assert WeatherUpdater.get_min_forecast_temperature(forecasts) == expected
