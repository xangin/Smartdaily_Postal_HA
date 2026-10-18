"""Binary sensor：API 連線異常。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SmartdailyEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ApiProblemSensor(entry)])


class ApiProblemSensor(SmartdailyEntity, BinarySensorEntity):
    """任一 coordinator 更新失敗時為 on；本身永遠可用，方便自動化監看。"""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry) -> None:
        coordinators = list(entry.runtime_data.coordinators.values())
        super().__init__(coordinators[0], entry, "", "api_problem", "API 連線異常")
        self._coordinators = coordinators

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        for coordinator in self._coordinators[1:]:
            self.async_on_remove(
                coordinator.async_add_listener(self._handle_coordinator_update)
            )

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return any(not c.last_update_success for c in self._coordinators)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            c.name: c.last_error or "OK" for c in self._coordinators
        }
