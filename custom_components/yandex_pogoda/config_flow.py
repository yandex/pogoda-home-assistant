"""Configuration flows."""

from __future__ import annotations

import uuid

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
                                 CONF_NAME)
from homeassistant.core import HomeAssistant, callback

from .const import CONF_LANGUAGE_KEY, DEFAULT_NAME, DOMAIN
from .updater import WeatherUpdater, read_translation_file


def get_supported_languages() -> list[str]:
    """Get supported translations."""
    return ["EN", "RU"]


def get_value(config_entry: config_entries | None, param: str, default=None):
    """Get current value for configuration parameter.

    :param config_entry: config_entries|None: config entry from Flow
    :param param: str: parameter name for getting value
    :param default: default value for parameter, defaults to None
    :returns: parameter value, or default value or None
    """
    if config_entry is not None:
        return config_entry.options.get(param, config_entry.data.get(param, default))

    return default


class YandexWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """First time set up flow."""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return YandexWeatherOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input is not None:
            latitude = user_input[CONF_LATITUDE]
            longitude = user_input[CONF_LONGITUDE]

            await self.async_set_unique_id(f"{uuid.uuid4()}")
            self._abort_if_unique_id_configured()

            if await _is_online(
                user_input[CONF_API_KEY], latitude, longitude, self.hass
            ):
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

            errors["base"] = "could_not_get_data"

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): cv.longitude,
                vol.Required(
                    CONF_LANGUAGE_KEY, default=get_supported_languages()[0]
                ): vol.In(get_supported_languages()),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class YandexWeatherOptionsFlow(config_entries.OptionsFlow):
    """Changing options flow."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            if await _is_online(
                user_input[CONF_API_KEY],
                user_input[CONF_LATITUDE],
                user_input[CONF_LONGITUDE],
                self.hass,
            ):
                return self.async_create_entry(title="", data=user_input)

            errors["base"] = "could_not_get_data"

        return self.async_show_form(
            step_id="init", data_schema=self._get_options_schema(), errors=errors
        )

    def _get_options_schema(self):
        return vol.Schema(
            {
                vol.Required(
                    CONF_API_KEY, default=get_value(self.config_entry, CONF_API_KEY)
                ): str,
                vol.Required(
                    CONF_LATITUDE, default=get_value(self.config_entry, CONF_LATITUDE)
                ): cv.latitude,
                vol.Required(
                    CONF_LONGITUDE, default=get_value(self.config_entry, CONF_LONGITUDE)
                ): cv.longitude,
                vol.Required(
                    CONF_LANGUAGE_KEY,
                    default=get_value(self.config_entry, CONF_LANGUAGE_KEY),
                ): vol.In(get_supported_languages()),
            }
        )


async def _is_online(api_key, lat, lon, hass: HomeAssistant) -> bool:
    language = get_supported_languages()[0]
    translation = await hass.async_add_executor_job(read_translation_file, language)
    weather = WeatherUpdater(lat, lon, api_key, hass, f"{uuid.uuid4()}", translation)
    await weather.async_request_refresh()
    return weather.last_update_success
