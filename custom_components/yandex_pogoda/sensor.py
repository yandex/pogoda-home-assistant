"""Sensor component."""

from __future__ import annotations

from dateutil import parser

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_API_CONDITION,
    ATTR_API_FEELS_LIKE_TEMPERATURE,
    ATTR_API_TEMPERATURE,
    ATTR_API_SERVER_TIME,
    ATTR_API_WIND_BEARING,
    ATTR_API_WIND_SPEED,
    ATTR_API_WIND_GUST,
    ATTR_API_YA_CONDITION,
    ATTR_MIN_FORECAST_TEMPERATURE,
    ATTRIBUTION,
    DOMAIN,
    ENTRY_NAME,
    TEMPERATURE_CONVERTER,
    UPDATER,
    WIND_SPEED_CONVERTER,
    convert_unit_value,
)
from .updater import WeatherUpdater

UNIT_CONVERTOR_TYPE_MAP: dict[str, str] = {
    ATTR_API_TEMPERATURE: TEMPERATURE_CONVERTER,
    ATTR_API_FEELS_LIKE_TEMPERATURE: TEMPERATURE_CONVERTER,
    ATTR_API_WIND_SPEED: WIND_SPEED_CONVERTER,
    ATTR_API_WIND_GUST: WIND_SPEED_CONVERTER,
    ATTR_MIN_FORECAST_TEMPERATURE: TEMPERATURE_CONVERTER,
}

WEATHER_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_API_TEMPERATURE,
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SensorEntityDescription(
        key=ATTR_API_FEELS_LIKE_TEMPERATURE,
        name="Feels like temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_SPEED,
        name="Wind speed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_GUST,
        name="Wind gust",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key=ATTR_API_WIND_BEARING,
        name="Wind bearing",
        entity_registry_enabled_default=True,
        icon="mdi:compass-rose",
        translation_key=ATTR_API_WIND_BEARING,
    ),
    SensorEntityDescription(
        key=ATTR_API_CONDITION,
        name="Condition HomeAssistant",
        entity_registry_enabled_default=False,
        translation_key=ATTR_API_CONDITION,
    ),
    SensorEntityDescription(
        key=ATTR_API_SERVER_TIME,
        name="Data update time",
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_API_YA_CONDITION,
        name="Condition Yandex",
        entity_registry_enabled_default=True,
        translation_key=ATTR_API_YA_CONDITION,
    ),
    SensorEntityDescription(
        key=ATTR_MIN_FORECAST_TEMPERATURE,
        name="Minimal forecast temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=True,
        icon="mdi:thermometer-chevron-down",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up weather "Yandex.Weather" sensor entry."""
    domain_data = hass.data[DOMAIN][config_entry.entry_id]
    name = domain_data[ENTRY_NAME]
    updater = domain_data[UPDATER]

    entities: list[YandexWeatherSensor] = [
        YandexWeatherSensor(
            name,
            f"{config_entry.unique_id}-{description.key}",
            description,
            updater,
        )
        for description in WEATHER_SENSORS
    ]
    async_add_entities(entities)


class YandexWeatherSensor(SensorEntity, CoordinatorEntity, RestoreEntity):
    """Yandex.Weather sensor entry."""

    _attr_attribution = ATTRIBUTION
    coordinator: WeatherUpdater

    def __init__(
        self,
        name: str,
        unique_id: str,
        description: SensorEntityDescription,
        updater: WeatherUpdater,
    ) -> None:
        """Initialize sensor."""
        CoordinatorEntity.__init__(self, coordinator=updater)
        RestoreEntity.__init__(self)
        self.entity_description = description

        self._attr_name = f"{name} {description.name}"
        self._attr_unique_id = unique_id
        self._attr_device_info = self.coordinator.device_info

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await RestoreEntity.async_added_to_hass(self)
        await CoordinatorEntity.async_added_to_hass(self)

        state = await self.async_get_last_state()
        if not state:
            return

        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._attr_available = False
        else:
            self._attr_available = True
            if self.entity_description.key == ATTR_API_SERVER_TIME:
                self._attr_native_value = parser.parse(state.state)
            elif self.entity_description.key in UNIT_CONVERTOR_TYPE_MAP:
                self._attr_native_value = str(
                    convert_unit_value(
                        UNIT_CONVERTOR_TYPE_MAP[self.entity_description.key],
                        float(state.state),
                        state.attributes['unit_of_measurement'],
                        self.native_unit_of_measurement,
                    )
                )
            else:
                self._attr_native_value = state.state

        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._attr_available = True
        self._attr_native_value = self.coordinator.data.get(
            self.entity_description.key, None
        )
        if self.entity_description.key == ATTR_API_YA_CONDITION:
            self._attr_icon = self.coordinator.data.get(f"{ATTR_API_YA_CONDITION}_icon")

        self.async_write_ha_state()
