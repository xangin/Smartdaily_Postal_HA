"""Event platform：包裹／寄放物／公告的每一筆異動。

同樣的資料也會以 bus 事件 smartdaily_postal_ha_<category> 發送，
自動化可擇一使用。
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CAT_ANNOUNCEMENT, CAT_COLLECTION, CAT_PACKAGE
from .coordinator import SmartdailyCoordinator
from .entity import SmartdailyEntity

EVENTS = {
    CAT_PACKAGE: ("package_event", "包裹事件", ["arrived", "picked_up"], "mdi:package-variant"),
    CAT_COLLECTION: ("collection_event", "寄放物事件", ["deposited", "collected"], "mdi:archive-outline"),
    CAT_ANNOUNCEMENT: ("announcement_event", "公告事件", ["new"], "mdi:bullhorn-variant-outline"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        SmartdailyEventEntity(runtime.coordinator_for(category), entry, category, *spec)
        for category, spec in EVENTS.items()
        if category in runtime.categories
    )


class SmartdailyEventEntity(SmartdailyEntity, EventEntity):
    """收到 coordinator 偵測到的異動時觸發。"""

    def __init__(
        self,
        coordinator: SmartdailyCoordinator,
        entry: ConfigEntry,
        category: str,
        key: str,
        name: str,
        event_types: list[str],
        icon: str,
    ) -> None:
        super().__init__(coordinator, entry, category, key, name)
        self._attr_event_types = event_types
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_event_listener(self._handle_event)
        )

    @callback
    def _handle_event(self, category: str, event_type: str, record: dict) -> None:
        if category != self._category:
            return
        self._trigger_event(event_type, record)
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        # 斷線時不轉成 unavailable，恢復時才不會誤觸以狀態為觸發的自動化
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        # 狀態只在有事件時改變，一般更新不需重寫
        return
