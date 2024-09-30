"""Test wind direction values"""

import pytest

from custom_components.yandex_pogoda.const import (
    get_wind_intercardinal_direction,
    get_wind_secondary_intercardinal_direction,
)


wind_angle = [
    -1500,
    1,
    22,
    44,
    55,
    65,
    80,
    95,
    105,
    115,
    125,
    145,
    165,
    185,
    205,
    225,
    265,
    285,
    305,
    335,
    1500,
]

intercardinal_expected = [
    "N",
    "N",
    "N",
    "NE",
    "NE",
    "NE",
    "E",
    "E",
    "E",
    "SE",
    "SE",
    "SE",
    "S",
    "S",
    "SW",
    "SW",
    "W",
    "W",
    "NW",
    "NW",
    "N",
]

secondary_intercardinal_expected = [
    "N",
    "N",
    "NNE",
    "NE",
    "NE",
    "ENE",
    "E",
    "E",
    "ESE",
    "ESE",
    "SE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "W",
    "WNW",
    "NW",
    "NNW",
    "N",
]


@pytest.mark.parametrize("direction,expected", zip(wind_angle, intercardinal_expected))
@pytest.mark.asyncio
async def test_get_wind_intercardinal_direction(direction, expected):
    """Test get_wind_intercardinal_direction"""
    assert expected == get_wind_intercardinal_direction(direction)


@pytest.mark.parametrize(
    "direction,expected", zip(wind_angle, secondary_intercardinal_expected)
)
@pytest.mark.asyncio
async def test_get_wind_intercardinal_direction(direction, expected):
    """Test get_wind_intercardinal_direction"""
    assert expected == get_wind_secondary_intercardinal_direction(direction)
