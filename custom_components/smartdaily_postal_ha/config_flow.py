"""Config flow for the Smartdaily Postal integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import SmartdailyApi, SmartdailyAuthError, SmartdailyError
from .const import (
    ALL_CATEGORIES,
    CONF_CATEGORIES,
    CONF_COM_ID,
    CONF_DEVICE_ID,
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_SLOW_INTERVAL,
    DOMAIN,
)

DEFAULT_OPTIONS = {
    CONF_CATEGORIES: ALL_CATEGORIES,
    CONF_FAST_INTERVAL: DEFAULT_FAST_INTERVAL,
    CONF_SLOW_INTERVAL: DEFAULT_SLOW_INTERVAL,
}

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CATEGORIES): SelectSelector(
            SelectSelectorConfig(
                options=ALL_CATEGORIES,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_CATEGORIES,
            )
        ),
        vol.Required(CONF_FAST_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=1, max=60, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        ),
        vol.Required(CONF_SLOW_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=10, max=1440, step=1, mode=NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        ),
    }
)


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_CATEGORIES: [c for c in ALL_CATEGORIES if c in user_input[CONF_CATEGORIES]],
        CONF_FAST_INTERVAL: int(user_input[CONF_FAST_INTERVAL]),
        CONF_SLOW_INTERVAL: int(user_input[CONF_SLOW_INTERVAL]),
    }


class SmartdailyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smartdaily."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_id: str = ""
        self._communities: dict[str, str] = {}
        self._com_id: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """輸入 DeviceID。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            api = SmartdailyApi(async_get_clientsession(self.hass), device_id)
            try:
                communities = await api.get_communities()
            except SmartdailyAuthError:
                errors["base"] = "invalid_auth"
            except SmartdailyError:
                errors["base"] = "cannot_connect"
            else:
                if not communities:
                    errors["base"] = "no_communities"
                else:
                    self._device_id = device_id
                    self._communities = {
                        str(c["id"]): c.get("community", str(c["id"]))
                        for c in communities
                    }
                    return await self.async_step_select_community()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): str}),
            errors=errors,
        )

    async def async_step_select_community(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """選擇社區。"""
        if user_input is not None:
            self._com_id = user_input[CONF_COM_ID]
            await self.async_set_unique_id(f"{self._device_id}_{self._com_id}")
            self._abort_if_unique_id_configured()
            return await self.async_step_features()

        return self.async_show_form(
            step_id="select_community",
            data_schema=vol.Schema(
                {vol.Required(CONF_COM_ID): vol.In(self._communities)}
            ),
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """選擇要啟用的類別與更新頻率。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CATEGORIES):
                errors["base"] = "no_categories"
            else:
                return self.async_create_entry(
                    title=f"智生活 {self._communities[self._com_id]}",
                    data={CONF_DEVICE_ID: self._device_id, CONF_COM_ID: self._com_id},
                    options=_normalize(user_input),
                )

        return self.async_show_form(
            step_id="features",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or DEFAULT_OPTIONS
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartdailyOptionsFlow:
        return SmartdailyOptionsFlow()


class SmartdailyOptionsFlow(OptionsFlow):
    """齒輪設定：調整類別與更新頻率，儲存後自動重新載入。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CATEGORIES):
                errors["base"] = "no_categories"
            else:
                return self.async_create_entry(data=_normalize(user_input))

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or current
            ),
            errors=errors,
        )
