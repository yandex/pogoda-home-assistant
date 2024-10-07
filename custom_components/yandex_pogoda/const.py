"""General constants."""

from __future__ import annotations

import logging

from collections.abc import Callable

from homeassistant.components.weather import (
    ATTR_WEATHER_TEMPERATURE_UNIT,
    ATTR_WEATHER_WIND_SPEED_UNIT,
    UNIT_CONVERSIONS,
)
from homeassistant.const import Platform


_LOGGER = logging.getLogger(__name__)

DOMAIN = "yandex_pogoda"
DEFAULT_NAME = "Yandex Pogoda"
DEFAULT_UPDATES_PER_DAY = 12
ATTRIBUTION = "Data provided by Yandex Pogoda"
MANUFACTURER = "Yandex"
ENTRY_NAME = "name"
UPDATER = "updater"

ATTR_API_TEMPERATURE = "temperature"
ATTR_API_TEMPERATURE_MAX = "maxTemperature"
ATTR_API_TEMPERATURE_MIN = "minTemperature"
ATTR_API_FEELS_LIKE_TEMPERATURE = "feelsLike"
ATTR_API_WIND_SPEED = "windSpeed"
ATTR_API_WIND_BEARING = "windAngle"
ATTR_API_DAYTIME = "daytime"
ATTR_API_CONDITION = "condition"
ATTR_API_IMAGE = "icon"
ATTR_API_SERVER_TIME = "serverTime"
ATTR_API_TIME = "time"
ATTR_API_SUNRISE_BEGIN_TIME = "sunriseBeginTime"
ATTR_API_SUNRISE_END_TIME = "sunsetEndTime"
ATTR_API_YA_CONDITION = "yandex_condition"
ATTR_API_WIND_GUST = "windGust"

ATTR_FORECAST_DATA = "forecast"
ATTR_FORECAST_HOURLY = "hourly"
ATTR_FORECAST_HOURLY_ICONS = "forecast_hourly_icons"
ATTR_FORECAST_TWICE_DAILY = "twice_daily"
ATTR_FORECAST_TWICE_DAILY_ICONS = "forecast_twice_daily_icons"

ATTR_MIN_FORECAST_TEMPERATURE = "min_forecast_temperature"
ATTR_WIND_INTERCARDINAL_DIRECTION = "wind_intercardinal"

UPDATE_LISTENER = "update_listener"
PLATFORMS = [Platform.SENSOR, Platform.WEATHER]

YA_CONDITIONS = [
    "CLEAR",
    "PARTLY_CLOUDY",
    "CLOUDY",
    "OVERCAST",
    "LIGHT_RAIN",
    "RAIN",
    "HEAVY_RAIN",
    "SHOWERS",
    "SLEET",
    "LIGHT_SNOW",
    "SNOW",
    "SNOWFALL",
    "HAIL",
    "THUNDERSTORM",
    "THUNDERSTORM_WITH_RAIN",
    "THUNDERSTORM_WITH_HAIL",
]
YA_CONDITION_STATE_MAP = {i: i.lower() for i in YA_CONDITIONS}
"""Mapping for yandex states"""

YA_CONDITION_STATES = list(YA_CONDITION_STATE_MAP.values())

WEATHER_STATES_CONVERSION = {
    "CLEAR": {
        "day": "sunny",
        "night": "clear-night",
    },
    "PARTLY_CLOUDY": "partlycloudy",
    "CLOUDY": "cloudy",
    "OVERCAST": "cloudy",
    "LIGHT_RAIN": "rainy",
    "RAIN": "rainy",
    "HEAVY_RAIN": "pouring",
    "SHOWERS": "pouring",
    "SLEET": "snowy-rainy",
    "LIGHT_SNOW": "snowy",
    "SNOW": "snowy",
    "SNOWFALL": "snowy",
    "HAIL": "hail",
    "THUNDERSTORM": "lightning",
    "THUNDERSTORM_WITH_RAIN": "lightning-rainy",
    "THUNDERSTORM_WITH_HAIL": "lightning-rainy",
}
"""Map rich Yandex weather condition to ordinary HA"""

HA_WEATHER_STATES = [
    i for i in WEATHER_STATES_CONVERSION.values() if isinstance(i, str)
] + list(WEATHER_STATES_CONVERSION["CLEAR"].values())

CONDITION_ICONS = {
    "CLEAR": {
        "day": "mdi:weather-sunny",
        "night": "mdi:weather-night",
    },
    "PARTLY_CLOUDY": {
        "day": "mdi:weather-partly-cloudy",
        "night": "mdi:weather-night-partly-cloudy",
    },
    "CLOUDY": "mdi:weather-cloudy",
    "OVERCAST": "mdi:weather-cloudy",
    "LIGHT_RAIN": "mdi:weather-rainy",
    "RAIN": "mdi:weather-rainy",
    "HEAVY_RAIN": "mdi:weather-pouring",
    "SHOWERS": "mdi:weather-pouring",
    "SLEET": "mdi:weather-snowy-rainy",
    "LIGHT_SNOW": "mdi:weather-snowy",
    "SNOW": "mdi:weather-snowy",
    "SNOWFALL": "mdi:weather-snowy-heavy",
    "HAIL": "mdi:weather-hail",
    "THUNDERSTORM": "mdi:weather-lightning",
    "THUNDERSTORM_WITH_RAIN": "mdi:weather-lightning-rainy",
    "THUNDERSTORM_WITH_HAIL": "mdi:weather-lightning-rainy",
}
"""Mapping for state icon"""


TEMPERATURE_CONVERTER = UNIT_CONVERSIONS[ATTR_WEATHER_TEMPERATURE_UNIT]
WIND_SPEED_CONVERTER = UNIT_CONVERSIONS[ATTR_WEATHER_WIND_SPEED_UNIT]


def convert_unit_value(
    converter: Callable[[float, str, str], float],
    val: float | None,
    unit_from: str | None,
    unit_to: str | None,
) -> float | None:
    """Weather factor unit converter."""
    if val is not None and unit_from and unit_to:
        return converter(val, unit_from, unit_to)
    return None


def map_state(src: str, is_day: bool, mapping: dict | None = None) -> str:
    """Map weather condition based on WEATHER_STATES_CONVERSION.

    :param src: str: Yandex weather state
    :param is_day: bool: Is it day? Used for icons
    :param mapping: use this dict for mapping
    :return: str: Home Assistant weather state
    """
    if mapping is None:
        mapping = {}

    try:
        result: str | dict[str, str] = mapping[src]
    except KeyError:
        result = src

    if type(result) is dict:
        return result["day" if is_day else "night"]

    return result


def get_wind_intercardinal_direction(wind_direction_degree: int) -> str:
    """Convert wind direction degree to named direction."""

    if wind_direction_degree < 0 or wind_direction_degree > 360:
        _LOGGER.error("Angle should be in [0, 360] range")

    if wind_direction_degree <= 22.5:
        return "n"

    if wind_direction_degree <= 67.5:
        return "ne"

    if wind_direction_degree <= 112.5:
        return "e"

    if wind_direction_degree <= 157.5:
        return "se"

    if wind_direction_degree <= 202.5:
        return "s"

    if wind_direction_degree <= 247.5:
        return "sw"

    if wind_direction_degree <= 292.5:
        return "w"

    if wind_direction_degree <= 337.5:
        return "nw"

    return "n"
