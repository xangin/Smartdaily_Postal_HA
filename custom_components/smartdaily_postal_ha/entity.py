"""Shared entity helpers for Smartdaily."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CAT_ANNOUNCEMENT,
    CAT_COLLECTION,
    CAT_PACKAGE,
    CAT_POINTS,
    CONF_COM_ID,
    CONF_DEVICE_ID,
    DOMAIN,
)
from .coordinator import SmartdailyCoordinator

# 各類別建立的實體 key；"" 代表沿用舊版「My Package Tracker」的 unique_id
ENTITY_KEYS: dict[str, list[str]] = {
    CAT_PACKAGE: ["", "camera", "package_unclaimed", "package_claimed", "package_event"],
    CAT_COLLECTION: [
        "collection_unclaimed",
        "collection_claimed",
        "collection_camera",
        "collection_event",
    ],
    CAT_ANNOUNCEMENT: ["announcement_unread", "announcement_latest", "announcement_event"],
    CAT_POINTS: ["points"],
}
COMMON_KEYS = ["api_problem"]


def unique_prefix(entry: ConfigEntry) -> str:
    return f"{entry.data[CONF_DEVICE_ID]}_{entry.data[CONF_COM_ID]}"


def make_unique_id(entry: ConfigEntry, key: str) -> str:
    prefix = unique_prefix(entry)
    return f"{prefix}_{key}" if key else prefix


def expected_unique_ids(entry: ConfigEntry, categories: set[str]) -> set[str]:
    keys = list(COMMON_KEYS)
    for category in categories:
        keys += ENTITY_KEYS.get(category, [])
    return {make_unique_id(entry, key) for key in keys}


def device_info(entry: ConfigEntry) -> DeviceInfo:
    community = entry.runtime_data.community
    return DeviceInfo(
        # 與舊版相同的 identifier，升級後沿用原本的裝置
        identifiers={(DOMAIN, unique_prefix(entry))},
        name=f"智生活 {community}" if community else "智生活包裹追蹤",
        manufacturer="今網智生活",
        entry_type=DeviceEntryType.SERVICE,
    )


class SmartdailyEntity(CoordinatorEntity[SmartdailyCoordinator]):
    """Base entity bound to one category of a coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartdailyCoordinator,
        entry: ConfigEntry,
        category: str,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_unique_id = make_unique_id(entry, key)
        self._attr_name = name
        self._attr_device_info = device_info(entry)

    @property
    def category_data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._category) or {}
