"""Pogoda component."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_API_CONDITION,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_FORECAST_ICONS,
    ATTR_API_IMAGE,
    ATTR_API_TEMPERATURE,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_GUST,
    ATTR_API_WIND_SPEED,
    ATTR_API_YA_CONDITION,
    ATTR_FORECAST_DATA,
    ATTRIBUTION,
    DOMAIN,
    ENTRY_NAME,
    TEMPERATURE_CONVERTER,
    UPDATER,
    WIND_SPEED_CONVERTER,
    convert_unit_value,
)
from .device_trigger import TRIGGERS
from .updater import WeatherUpdater

_LOGGER = logging.getLogger(__name__)


def _get_converter(
    converter: Callable[[float, str, str], float], unit_from: str, unit_to: str
) -> Callable[[float], float | None]:
    def wrap(value: float) -> float | None:
        return convert_unit_value(converter, value, unit_from, unit_to)

    return wrap


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up weather "Yandex.Pogoda" weather entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    updater = domain_data[UPDATER]

    async_add_entities([YandexWeather(name, config_entry, updater, hass)], False)


class YandexWeather(WeatherEntity, CoordinatorEntity, RestoreEntity):
    """Yandex.Pogoda entry."""

    _attr_attribution = ATTRIBUTION
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _hourly_forecast: list[Forecast] | None

    coordinator: WeatherUpdater

    def __init__(
        self,
        name,
        config_entry: ConfigEntry,
        updater: WeatherUpdater,
        hass: HomeAssistant,
    ) -> None:
        """Initialize entry."""
        WeatherEntity.__init__(self)
        CoordinatorEntity.__init__(self, coordinator=updater)
        RestoreEntity.__init__(self)

        self.hass = hass
        self._attr_name = name
        self._attr_condition = None
        self._attr_unique_id = config_entry.unique_id
        self._attr_device_info = self.coordinator.device_info
        self._attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await RestoreEntity.async_added_to_hass(self)
        await CoordinatorEntity.async_added_to_hass(self)

        state = await self.async_get_last_state()
        if not state:
            _LOGGER.debug("Have no state for restore!")
            await self.coordinator.async_config_entry_first_refresh()
            return

        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._attr_available = False
            await self.coordinator.async_config_entry_first_refresh()
        else:
            _LOGGER.debug(f"state for restore: {state}")
            self._attr_available = True
            self._attr_condition = state.state
            temp_converter = _get_converter(
                TEMPERATURE_CONVERTER,
                state.attributes.get("temperature_unit")
                or self._weather_option_temperature_unit,
                self._attr_native_temperature_unit,
            )
            ws_converter = _get_converter(
                WIND_SPEED_CONVERTER,
                state.attributes.get("wind_speed_unit")
                or self._weather_option_wind_speed_unit,
                self._attr_native_wind_speed_unit,
            )

            self._attr_native_temperature = temp_converter(
                state.attributes.get("temperature")
            )
            self._attr_native_wind_speed = ws_converter(
                state.attributes.get("wind_speed")
            )
            self._attr_native_wind_gust_speed = ws_converter(
                state.attributes.get("windGust")
            )
            self._attr_native_apparent_temperature = temp_converter(
                state.attributes.get("feelsLike")
            )
            self._attr_wind_bearing = state.attributes.get("wind_bearing")
            self._attr_entity_picture = state.attributes.get("entity_picture")
            self._hourly_forecast = state.attributes.get(ATTR_FORECAST_DATA, [])

            self._attr_extra_state_attributes = {
                ATTR_FORECAST_DATA: self._hourly_forecast,
            }
            for attribute in [
                ATTR_API_FEELS_LIKE_TEMPERATURE,
                ATTR_API_WIND_GUST,
                "yandex_condition",
                "forecast_icons",
            ]:
                value = state.attributes.get(attribute)
                if value is not None:
                    self._attr_extra_state_attributes[attribute] = value

            # last_updated is last call of self.async_write_ha_state(), not a real last update
            since_last_update = datetime.now(timezone.utc) - state.last_updated.replace(
                tzinfo=timezone.utc
            )
            _LOGGER.debug(
                f"Time since last update: {since_last_update} ({state.last_updated}), "
                f"update interval is {self.coordinator.update_interval}"
            )
            if since_last_update > self.coordinator.update_interval:
                await self.coordinator.async_config_entry_first_refresh()
            else:
                self.coordinator.schedule_refresh(
                    offset=self.coordinator.update_interval - since_last_update
                )
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._attr_available = True
        self.update_condition_and_fire_event(
            new_condition=self.coordinator.data.get(ATTR_API_CONDITION)
        )
        self._attr_entity_picture = self.coordinator.data.get(ATTR_API_IMAGE)
        self._hourly_forecast = self.coordinator.data.get(ATTR_FORECAST_DATA, [])
        self._attr_native_temperature = self.coordinator.data.get(ATTR_API_TEMPERATURE)
        self._attr_native_wind_speed = self.coordinator.data.get(ATTR_API_WIND_SPEED)
        self._attr_wind_bearing = self.coordinator.data.get(ATTR_API_WIND_BEARING)
        _LOGGER.debug(f"_handle_coordinator_update: {self._hourly_forecast=}")
        self._attr_extra_state_attributes = {
            ATTR_API_FEELS_LIKE_TEMPERATURE: self.coordinator.data.get(
                ATTR_API_FEELS_LIKE_TEMPERATURE
            ),
            ATTR_API_WIND_GUST: self.coordinator.data.get(ATTR_API_WIND_GUST),
            ATTR_API_YA_CONDITION: self.coordinator.data.get(ATTR_API_YA_CONDITION),
            ATTR_API_FORECAST_ICONS: self.coordinator.data.get(ATTR_API_FORECAST_ICONS),
            ATTR_FORECAST_DATA: self.__forecast_hourly(),
        }
        # self.coordinator.async_refresh()
        self.async_write_ha_state()

    def update_condition_and_fire_event(self, new_condition: str):
        """Set new condition and fire event on change."""
        if (
            new_condition != self._attr_condition
            and self.hass is not None
            and new_condition in TRIGGERS
        ):
            self.hass.bus.async_fire(
                DOMAIN + "_event",
                {
                    "device_id": self.coordinator.device_id,
                    "type": new_condition,
                },
            )

        self._attr_condition = new_condition

    def __forecast_hourly(self) -> list[Forecast] | None:
        """Return the daily forecast in native units."""
        return [] if self._hourly_forecast is None else self._hourly_forecast

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast in native units.

        Only implement this method if `WeatherEntityFeature.FORECAST_HOURLY` is set
        """
        _LOGGER.debug(f"async_forecast_hourly: {self._hourly_forecast=}")
        return self.__forecast_hourly()
