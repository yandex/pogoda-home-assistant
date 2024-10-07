"""Pogoda data updater."""

from __future__ import annotations

import aiohttp
import json
import logging
import math
import os

from dataclasses import dataclass
from datetime import timedelta
from dateutil import parser

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_APPARENT_TEMP,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_GUST_SPEED,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_WIND_BEARING,
    Forecast,
)
from homeassistant.core import HomeAssistant, HomeAssistantError, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_API_CONDITION,
    ATTR_API_DAYTIME,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_IMAGE,
    ATTR_API_SERVER_TIME,
    ATTR_API_SUNRISE_BEGIN_TIME,
    ATTR_API_SUNRISE_END_TIME,
    ATTR_API_TEMPERATURE,
    ATTR_API_TEMPERATURE_MAX,
    ATTR_API_TEMPERATURE_MIN,
    ATTR_API_TIME,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_GUST,
    ATTR_API_WIND_SPEED,
    ATTR_API_YA_CONDITION,
    ATTR_FORECAST_DATA,
    ATTR_FORECAST_HOURLY,
    ATTR_FORECAST_HOURLY_ICONS,
    ATTR_FORECAST_TWICE_DAILY,
    ATTR_FORECAST_TWICE_DAILY_ICONS,
    ATTR_MIN_FORECAST_TEMPERATURE,
    ATTR_WIND_INTERCARDINAL_DIRECTION,
    DEFAULT_UPDATES_PER_DAY,
    CONDITION_ICONS,
    DOMAIN,
    MANUFACTURER,
    WEATHER_STATES_CONVERSION,
    YA_CONDITION_STATE_MAP,
    get_wind_intercardinal_direction,
    map_state,
)

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.weather.yandex.ru/graphql/query"
API_HEADER_NAME = "X-Yandex-Weather-Key"

API_QUERY_TEMPLATE = f"""{{
    {ATTR_API_SERVER_TIME}
    weatherByPoint(request: {{ lat: %s, lon: %s }}) {{
        now {{
            {ATTR_API_CONDITION}
            {ATTR_API_DAYTIME}
            {ATTR_API_FEELS_LIKE_TEMPERATURE}
            {ATTR_API_IMAGE}(format: PNG_64)
            {ATTR_API_TEMPERATURE}
            {ATTR_API_WIND_BEARING}
            {ATTR_API_WIND_GUST}
            {ATTR_API_WIND_SPEED}
        }}
        forecast {{
            days(limit: 4){{
                {ATTR_API_TIME}
                {ATTR_API_SUNRISE_BEGIN_TIME}
                {ATTR_API_SUNRISE_END_TIME}
                hours{{
                    {ATTR_API_TIME}
                    {ATTR_API_CONDITION}
                    {ATTR_API_FEELS_LIKE_TEMPERATURE}
                    {ATTR_API_IMAGE}(format: PNG_64)
                    {ATTR_API_TEMPERATURE}
                    {ATTR_API_WIND_BEARING}
                    {ATTR_API_WIND_GUST}
                    {ATTR_API_WIND_SPEED}
                }}
                summary{{
                    night{{
                        ...forecastFields
                    }}
                    day{{
                        ...forecastFields
                    }}
                }}
            }}
        }}
    }}
}}
fragment forecastFields on Daypart {{
    {ATTR_API_CONDITION}
    {ATTR_API_FEELS_LIKE_TEMPERATURE}
    {ATTR_API_IMAGE}(format: PNG_64)
    {ATTR_API_WIND_BEARING}
    {ATTR_API_WIND_GUST}
    {ATTR_API_WIND_SPEED}
    {ATTR_API_TEMPERATURE_MAX}
    {ATTR_API_TEMPERATURE_MIN}
}}"""


@dataclass
class AttributeMapper:
    """Attribute mapper."""

    src: str
    _dst: str | None = None
    mapping: dict | None = None
    default: str | float | None = None

    @property
    def dst(self) -> str:
        """Destination for mapping."""
        return self.src if self._dst is None else self._dst


CURRENT_WEATHER_ATTRIBUTE_TRANSLATION: list[AttributeMapper] = [
    AttributeMapper(ATTR_API_WIND_BEARING),
    AttributeMapper(
        ATTR_API_WIND_BEARING,
        ATTR_WIND_INTERCARDINAL_DIRECTION,
        mapping=get_wind_intercardinal_direction,
    ),
    AttributeMapper(ATTR_API_CONDITION, ATTR_API_YA_CONDITION, YA_CONDITION_STATE_MAP),
    AttributeMapper(
        ATTR_API_CONDITION, f"{ATTR_API_YA_CONDITION}_icon", CONDITION_ICONS
    ),
    AttributeMapper(ATTR_API_CONDITION, mapping=WEATHER_STATES_CONVERSION),
    AttributeMapper(ATTR_API_FEELS_LIKE_TEMPERATURE),
    AttributeMapper(ATTR_API_IMAGE),
    AttributeMapper(ATTR_API_TEMPERATURE),
    AttributeMapper(ATTR_API_WIND_GUST),
    AttributeMapper(ATTR_API_WIND_SPEED, default=0),
]


FORECAST_HOUR_ATTRIBUTE_TRANSLATION: list[AttributeMapper] = [
    AttributeMapper(ATTR_API_WIND_BEARING, ATTR_FORECAST_WIND_BEARING),
    AttributeMapper(ATTR_API_WIND_SPEED, ATTR_FORECAST_NATIVE_WIND_SPEED, default=0),
    AttributeMapper(
        ATTR_API_FEELS_LIKE_TEMPERATURE, ATTR_FORECAST_NATIVE_APPARENT_TEMP
    ),
    AttributeMapper(ATTR_API_TEMPERATURE, ATTR_FORECAST_NATIVE_TEMP),
    AttributeMapper(
        ATTR_API_CONDITION, ATTR_FORECAST_CONDITION, mapping=WEATHER_STATES_CONVERSION
    ),
    AttributeMapper(ATTR_API_WIND_GUST, ATTR_FORECAST_NATIVE_WIND_GUST_SPEED),
]


FORECAST_DAY_ATTRIBUTE_TRANSLATION: list[AttributeMapper] = [
    AttributeMapper(ATTR_API_WIND_BEARING, ATTR_FORECAST_WIND_BEARING),
    AttributeMapper(ATTR_API_WIND_SPEED, ATTR_FORECAST_NATIVE_WIND_SPEED, default=0),
    AttributeMapper(
        ATTR_API_FEELS_LIKE_TEMPERATURE, ATTR_FORECAST_NATIVE_APPARENT_TEMP
    ),
    AttributeMapper(ATTR_API_TEMPERATURE_MAX, ATTR_FORECAST_NATIVE_TEMP),
    AttributeMapper(ATTR_API_TEMPERATURE_MIN, ATTR_FORECAST_NATIVE_TEMP_LOW),
    AttributeMapper(
        ATTR_API_CONDITION, ATTR_FORECAST_CONDITION, mapping=WEATHER_STATES_CONVERSION
    ),
    AttributeMapper(ATTR_API_WIND_GUST, ATTR_FORECAST_NATIVE_WIND_GUST_SPEED),
]


class WeatherUpdater(DataUpdateCoordinator):
    """Weather data updater for interaction with Yandex.Weather API."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        api_key: str,
        hass: HomeAssistant,
        device_id: str,
        name="Yandex Weather",
        updates_per_day: int = DEFAULT_UPDATES_PER_DAY,
        weather_data: dict | None = None,
    ):
        """Initialize updater.

        :param latitude: latitude of location for weather data
        :param longitude: longitude of location for weather data
        :param api_key: Yandex weather API. MUST be weather for site tariff plan
        :param hass: Home Assistant object
        :param language: Language for yandex_condition
        :param updates_per_day: int: how many updates per day we should do?
        :param device_id: ID of integration Device in Home Assistant
        :param weather_data: if not None then weather_data will be used for first update
        """

        self.__api_key = api_key.strip()
        self._lat = latitude
        self._lon = longitude
        self._device_id = device_id
        self._name = name
        self.weather_data = weather_data
        self.is_first_update_requred = bool(weather_data)

        self.update_interval = timedelta(
            seconds=math.ceil((24 * 60 * 60) / updates_per_day)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{self._name} updater",
            update_interval=self.update_interval,
            update_method=self.update,
        )
        self.data = {}

    def process_data(
        self, dst: dict, src: dict, attributes: list[AttributeMapper], is_day: bool
    ):
        """Convert Yandex API weather response to HA friendly.

        :param dst: weather data for HomeAssistant
        :param src: weather data form Yandex
        :param attributes: how to translate src to dst
        """

        for attribute in attributes:
            value = src.get(attribute.src, attribute.default)

            if value is not None and attribute.mapping is not None:
                if isinstance(attribute.mapping, dict):
                    value = map_state(
                        src=str(value), is_day=is_day, mapping=attribute.mapping
                    )
                else:
                    value = attribute.mapping(value)

            dst[attribute.dst] = value

    @staticmethod
    def get_min_forecast_temperature(forecasts: list[dict]) -> float | None:
        """Get minimum temperature from forecast data."""
        low_fc_temperatures: list[float] = []

        for f in forecasts:
            f_low_temperature: float = f.get(ATTR_FORECAST_NATIVE_TEMP, None)
            if f_low_temperature is not None:
                low_fc_temperatures.append(f_low_temperature)

        return min(low_fc_temperatures) if len(low_fc_temperatures) > 0 else None

    async def _get_weather_data(self):
        if self.is_first_update_requred:  # No need to make API request
            self.is_first_update_requred = False
            _LOGGER.error("Skip API request")
            return self.weather_data

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            rs = await self.request(session, self.__api_key, self._lat, self._lon)

        self.weather_data = rs["data"]
        return self.weather_data

    async def update(self):
        """Update weather information.

        :returns: dict with weather data.
        """
        data = await self._get_weather_data()
        weather_by_point = data["weatherByPoint"]
        now = weather_by_point["now"]
        now_dt = parser.parse(data[ATTR_API_SERVER_TIME])
        result = {
            ATTR_API_SERVER_TIME: now_dt,
            ATTR_FORECAST_DATA: {
                ATTR_FORECAST_HOURLY: [],
                ATTR_FORECAST_TWICE_DAILY: [],
            },
            ATTR_FORECAST_HOURLY_ICONS: [],
            ATTR_FORECAST_TWICE_DAILY_ICONS: [],
        }
        self.process_data(
            result,
            now,
            CURRENT_WEATHER_ATTRIBUTE_TRANSLATION,
            now[ATTR_API_DAYTIME] == "DAY",
        )

        for day in weather_by_point["forecast"]["days"]:
            sunrise_begin = parser.parse(day[ATTR_API_SUNRISE_BEGIN_TIME])
            sunset_end = parser.parse(day[ATTR_API_SUNRISE_END_TIME])
            for hour in day["hours"]:
                hour_dt = parser.parse(hour[ATTR_API_TIME])
                if now_dt > hour_dt:
                    continue

                hour_forecast = Forecast(datetime=hour_dt)
                self.process_data(
                    dst=hour_forecast,
                    src=hour,
                    attributes=FORECAST_HOUR_ATTRIBUTE_TRANSLATION,
                    is_day=sunrise_begin <= hour_dt < sunset_end,
                )
                result[ATTR_FORECAST_DATA][ATTR_FORECAST_HOURLY].append(hour_forecast)
                result[ATTR_FORECAST_HOURLY_ICONS].append(hour.get(ATTR_API_IMAGE))

            day_dt = parser.parse(day[ATTR_API_TIME]) + timedelta(hours=2)
            day_part = day["summary"]["day"]
            night_part = day["summary"]["night"]
            for part, is_day in ((night_part, False), (day_part, True)):
                part_forecast = Forecast(datetime=day_dt, is_daytime=is_day)
                self.process_data(
                    dst=part_forecast,
                    src=part,
                    attributes=FORECAST_DAY_ATTRIBUTE_TRANSLATION,
                    is_day=is_day,
                )
                result[ATTR_FORECAST_DATA][ATTR_FORECAST_TWICE_DAILY].append(
                    part_forecast
                )
                result[ATTR_FORECAST_TWICE_DAILY_ICONS].append(part.get(ATTR_API_IMAGE))
                day_dt = day_dt + timedelta(hours=12)

        result[ATTR_MIN_FORECAST_TEMPERATURE] = self.get_min_forecast_temperature(
            result[ATTR_FORECAST_DATA][ATTR_FORECAST_HOURLY]
        )

        return result

    @staticmethod
    async def request(
        session: aiohttp.ClientSession,
        api_key: str,
        lat: float,
        lon: float,
    ):
        """Make request to API endpoint.

        :param session: aiohttp.ClientSession: HTTP session for request
        :param api_key: str: API key
        :param lat: float: latitude of location where we are getting weather data
        :param lon: float: longitude of location where we ate getting weather data

        :returns: dict with response data
        :raises AssertionError: when response.status is not 200
        """
        _LOGGER.error("Sending API request")
        async with session.post(
            API_URL,
            headers={API_HEADER_NAME: api_key},
            json={"query": API_QUERY_TEMPLATE % (lat, lon)},
        ) as response:
            try:
                assert response.status == 200
            except AssertionError as e:
                _LOGGER.error("Could not get data from API: %s", response)
                raise aiohttp.ClientError(response.status, await response.text()) from e

            result = await response.json()

        if "errors" in result:
            msg = f"Errors in weather API response: {result}"
            _LOGGER.error(msg)
            raise HomeAssistantError(msg)

        _LOGGER.debug(result)
        return result

    def __str__(self):
        """Show as pretty look data json."""
        _d = dict(self.data)
        _d[ATTR_API_SERVER_TIME] = str(_d[ATTR_API_SERVER_TIME])
        return json.dumps(_d, indent=4, sort_keys=True)

    @property
    def url(self) -> str:
        """Weather URL."""
        return f"https://yandex.ru/weather/?lat={self._lat}&lon={self._lon}"

    @property
    def device_info(self):
        """Device info."""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self.device_id)},
            manufacturer=MANUFACTURER,
            name=self._name,
            configuration_url=self.url,
        )

    def schedule_refresh(self, offset: timedelta):
        """Schedule refresh."""
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        _LOGGER.debug(f"scheduling next refresh after {offset=}")
        next_refresh = (
            int(self.hass.loop.time()) + self._microsecond + offset.total_seconds()
        )
        self._unsub_refresh = self.hass.loop.call_at(
            next_refresh, self.__wrap_handle_refresh_interval
        ).cancel

    @callback
    def __wrap_handle_refresh_interval(self) -> None:
        """Handle a refresh interval occurrence."""
        # We need this private callback from parent class
        if self.config_entry:
            self.config_entry.async_create_background_task(
                self.hass,
                self._handle_refresh_interval(),
                name=f"{self.name} - {self.config_entry.title} - refresh",
                eager_start=True,
            )
        else:
            self.hass.async_create_background_task(
                self._handle_refresh_interval(),
                name=f"{self.name} - refresh",
                eager_start=True,
            )

    @property
    def device_id(self) -> str:
        """Device ID."""
        return self._device_id
