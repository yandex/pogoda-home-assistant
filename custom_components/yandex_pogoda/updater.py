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
    API_DAY_PARTS,
    ATTR_API_CONDITION,
    ATTR_API_DAYTIME,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_FORECAST_ICONS,
    ATTR_API_TIME,
    ATTR_API_IMAGE,
    ATTR_API_TEMPERATURE,
    ATTR_API_SERVER_TIME,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_GUST,
    ATTR_API_WIND_SPEED,
    ATTR_API_YA_CONDITION,
    ATTR_FORECAST_DATA,
    ATTR_MIN_FORECAST_TEMPERATURE,
    ATTR_WIND_BEARING_DIRECTION,
    DEFAULT_UPDATES_PER_DAY,
    CONDITION_ICONS,
    DOMAIN,
    MANUFACTURER,
    WEATHER_STATES_CONVERSION,
    get_wind_direction,
    map_state,
)

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.weather.yandex.ru/graphql/query"
API_HEADER_NAME = "X-Yandex-Weather-Key"
API_QUERY_FORECAST_DAYS_LIMIT = 2
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
            days(limit: %s){{
                {ATTR_API_TIME}
                parts{{
                    {API_DAY_PARTS[0][0]}{{
                        ...forecastFields
                    }}
                    {API_DAY_PARTS[1][0]}{{
                        ...forecastFields
                    }}
                    {API_DAY_PARTS[2][0]}{{
                        ...forecastFields
                    }}
                    {API_DAY_PARTS[3][0]}{{
                        ...forecastFields
                    }}
                }}
            }}
        }}
    }}
}}
fragment forecastFields on Daypart {{
    {ATTR_API_CONDITION}
    {ATTR_API_DAYTIME}
    {ATTR_API_FEELS_LIKE_TEMPERATURE}
    {ATTR_API_IMAGE}(format: PNG_64)
    {ATTR_API_TEMPERATURE}
    {ATTR_API_WIND_BEARING}
    {ATTR_API_WIND_GUST}
    {ATTR_API_WIND_SPEED}
}}"""


@dataclass
class AttributeMapper:
    """Attribute mapper."""

    src: str
    _dst: str | None = None
    mapping: dict | None = None
    default: str | float | None = None
    should_translate: bool = False

    @property
    def dst(self) -> str:
        """Destination for mapping."""
        return self.src if self._dst is None else self._dst


CURRENT_WEATHER_ATTRIBUTE_TRANSLATION: list[AttributeMapper] = [
    AttributeMapper(ATTR_API_WIND_BEARING),
    AttributeMapper(
        ATTR_API_WIND_BEARING,
        ATTR_WIND_BEARING_DIRECTION,
        mapping=get_wind_direction,
        should_translate=True,
    ),
    AttributeMapper(ATTR_API_CONDITION, ATTR_API_YA_CONDITION, should_translate=True),
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


FORECAST_ATTRIBUTE_TRANSLATION: list[AttributeMapper] = [
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


BASE_DIR = os.path.dirname(os.path.realpath(__file__))


def read_translation_file(language: str) -> dict:
    """Read parse and return translation file for language."""
    try:
        with open(f"{BASE_DIR}/translations/{language.lower()}.json") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        _LOGGER.debug(f"We have no translation for {language=} in {BASE_DIR}")

    return {}


def translate_condition(value: str, translation: dict) -> str:
    """Translate Yandex condition."""
    try:
        return translation["entity"]["sensor"][ATTR_API_YA_CONDITION]["state"][value]
    except KeyError:
        _LOGGER.debug(f"Have no translation for {value}")

    return value


class WeatherUpdater(DataUpdateCoordinator):
    """Weather data updater for interaction with Yandex.Weather API."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        api_key: str,
        hass: HomeAssistant,
        device_id: str,
        translation: dict,
        name="Yandex Weather",
        updates_per_day: int = DEFAULT_UPDATES_PER_DAY,
    ):
        """Initialize updater.

        :param latitude: latitude of location for weather data
        :param longitude: longitude of location for weather data
        :param api_key: Yandex weather API. MUST be weather for site tariff plan
        :param hass: Home Assistant object
        :param language: Language for yandex_condition
        :param updates_per_day: int: how many updates per day we should do?
        :param device_id: ID of integration Device in Home Assistant
        """

        self.__api_key = api_key.strip()
        self._lat = latitude
        self._lon = longitude
        self._device_id = device_id
        self._name = name
        self.translation = translation

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

            if attribute.should_translate and value is not None:
                value = translate_condition(value, self.translation)

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

    async def update(self):
        """Update weather information.

        :returns: dict with weather data.
        """
        result = {}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            rs = await self.request(session, self.__api_key, self._lat, self._lon)

        data = rs["data"]
        weather_by_point = data["weatherByPoint"]
        now = weather_by_point["now"]
        now_dt = parser.parse(data[ATTR_API_SERVER_TIME])
        result = {
            ATTR_API_SERVER_TIME: now_dt,
            ATTR_API_FORECAST_ICONS: [],
            ATTR_FORECAST_DATA: [],
        }
        self.process_data(
            result,
            now,
            CURRENT_WEATHER_ATTRIBUTE_TRANSLATION,
            now[ATTR_API_DAYTIME] == "DAY",
        )

        for day in weather_by_point["forecast"]["days"]:
            day_parts = day["parts"]
            day_dt = parser.parse(day[ATTR_API_TIME])

            for part, hour in API_DAY_PARTS:
                f_dt = day_dt.replace(hour=hour)

                if now_dt > f_dt:
                    continue

                if f := day_parts.get(part):
                    forecast = Forecast(datetime=f_dt)
                    self.process_data(
                        forecast,
                        f,
                        FORECAST_ATTRIBUTE_TRANSLATION,
                        f[ATTR_API_DAYTIME] == "DAY",
                    )
                    result[ATTR_FORECAST_DATA].append(forecast)
                    result[ATTR_API_FORECAST_ICONS].append(
                        f.get(ATTR_API_IMAGE, "no_image")
                    )

        result[ATTR_MIN_FORECAST_TEMPERATURE] = self.get_min_forecast_temperature(
            result[ATTR_FORECAST_DATA]
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
        _LOGGER.info("Sending API request")
        async with session.post(
            API_URL,
            headers={API_HEADER_NAME: api_key},
            json={
                "query": API_QUERY_TEMPLATE % (lat, lon, API_QUERY_FORECAST_DAYS_LIMIT)
            },
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
