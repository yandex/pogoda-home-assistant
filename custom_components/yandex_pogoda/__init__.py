"""Yandex.Pogoda custom integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant

from .config_flow import get_value
from .const import (
    CONF_LANGUAGE_KEY,
    DOMAIN,
    ENTRY_NAME,
    PLATFORMS,
    UPDATE_LISTENER,
    UPDATER,
)
from .updater import WeatherUpdater, read_translation_file


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry configured via user interface."""
    name = get_value(entry, CONF_NAME)
    api_key = get_value(entry, CONF_API_KEY)
    latitude = get_value(entry, CONF_LATITUDE, hass.config.latitude)
    longitude = get_value(entry, CONF_LONGITUDE, hass.config.longitude)
    language = get_value(entry, CONF_LANGUAGE_KEY, "EN")
    translation = await hass.async_add_executor_job(read_translation_file, language)

    weather_updater = WeatherUpdater(
        latitude=latitude,
        longitude=longitude,
        api_key=api_key,
        hass=hass,
        device_id=entry.unique_id,
        name=name,
        translation=translation,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        ENTRY_NAME: name,
        UPDATER: weather_updater,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    update_listener = entry.add_update_listener(async_update_options)
    hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER] = update_listener

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options for entry that was configured via user interface."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entry configured via user interface."""
    unload_ok = True
    for platform in PLATFORMS:
        unload_ok = unload_ok & await hass.config_entries.async_forward_entry_unload(
            entry=entry, domain=platform
        )
    if unload_ok:
        update_listener = hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER]
        update_listener()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
