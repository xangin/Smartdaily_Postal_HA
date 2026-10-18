"""Sensor platform for Smartdaily."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CAT_ANNOUNCEMENT,
    CAT_COLLECTION,
    CAT_PACKAGE,
    CAT_POINTS,
    DEFAULT_IMAGE_URL,
    MAX_CLAIMED_ITEMS,
)
from .coordinator import SmartdailyCoordinator
from .entity import SmartdailyEntity

RECENT_ANNOUNCEMENTS = 5


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    categories = runtime.categories
    entities: list[SensorEntity] = []

    if CAT_PACKAGE in categories:
        c = runtime.coordinator_for(CAT_PACKAGE)
        entities += [
            LatestPackageSensor(c, entry),
            ItemsSensor(c, entry, CAT_PACKAGE, "unclaimed", "package_unclaimed",
                        "未領取包裹", "件", "mdi:package-variant-closed"),
            ItemsSensor(c, entry, CAT_PACKAGE, "claimed", "package_claimed",
                        "近期已取件包裹", "件", "mdi:package-variant-closed-check",
                        MAX_CLAIMED_ITEMS),
        ]
    if CAT_COLLECTION in categories:
        c = runtime.coordinator_for(CAT_COLLECTION)
        entities += [
            ItemsSensor(c, entry, CAT_COLLECTION, "unclaimed", "collection_unclaimed",
                        "未領取寄放物", "件", "mdi:archive-clock-outline"),
            ItemsSensor(c, entry, CAT_COLLECTION, "claimed", "collection_claimed",
                        "近期已領取寄放物", "件", "mdi:archive-check-outline",
                        MAX_CLAIMED_ITEMS),
        ]
    if CAT_ANNOUNCEMENT in categories:
        c = runtime.coordinator_for(CAT_ANNOUNCEMENT)
        entities += [
            ItemsSensor(c, entry, CAT_ANNOUNCEMENT, "unread", "announcement_unread",
                        "未讀公告", "則", "mdi:bullhorn-outline"),
            LatestAnnouncementSensor(c, entry),
        ]
    if CAT_POINTS in categories:
        entities.append(PointsSensor(runtime.coordinator_for(CAT_POINTS), entry))

    async_add_entities(entities)


class ItemsSensor(SmartdailyEntity, SensorEntity):
    """狀態為件數，items 屬性為完整清單（給 Markdown 卡片用迴圈顯示）。"""

    _attr_state_class = SensorStateClass.MEASUREMENT
    # 清單內含每次更新都會變的簽名網址，不寫入歷史資料庫
    _unrecorded_attributes = frozenset({"items"})

    def __init__(
        self,
        coordinator: SmartdailyCoordinator,
        entry: ConfigEntry,
        category: str,
        list_key: str,
        key: str,
        name: str,
        unit: str,
        icon: str,
        limit: int | None = None,
    ) -> None:
        super().__init__(coordinator, entry, category, key, name)
        self._list_key = list_key
        self._limit = limit
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon

    @property
    def _items(self) -> list[dict]:
        return self.category_data.get(self._list_key) or []

    @property
    def native_value(self) -> int:
        return len(self._items)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._items
        if self._limit is not None:
            items = items[: self._limit]
        return {"items": items}


class LatestPackageSensor(SmartdailyEntity, SensorEntity):
    """最新一件包裹（沿用舊版 My Package Tracker 的 unique_id 與屬性名稱）。"""

    def __init__(self, coordinator: SmartdailyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CAT_PACKAGE, "", "最新包裹")

    @property
    def _package(self) -> dict | None:
        return self.category_data.get("latest")

    @property
    def native_value(self) -> str | None:
        package = self._package
        if package is None:
            return None
        return "已取件" if package["claimed"] else "未領取"

    @property
    def icon(self) -> str:
        state = self.native_value
        if state is None:
            return "mdi:package-variant-remove"
        if state == "未領取":
            return "mdi:package-variant-closed"
        return "mdi:package-variant-closed-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        package = self._package
        if package is None:
            return {}
        return {
            "pd_id": package.get("pd_id"),
            "create_date": package.get("create_date"),
            "arrived_at": package.get("arrived_at"),
            "picked_up_at": package.get("picked_up_at"),
            "p_name": package.get("p_name"),
            "postal_typeText": package.get("postal_typeText"),
            "transport_code": package.get("transport_code"),
            "privacy": package.get("privacy") == "privacy",
            "p_note": package.get("p_note"),
            "postal_logisticsText": package.get("postal_logisticsText"),
            "refrigerated": package.get("refrigerated"),
            "postal_img": package.get("postal_img") or DEFAULT_IMAGE_URL,
            "image_url": package.get("image_url"),
            "unclaimed_packages_count": len(self.category_data.get("unclaimed") or []),
        }


class LatestAnnouncementSensor(SmartdailyEntity, SensorEntity):
    """最新一則非置頂公告。"""

    _attr_icon = "mdi:bullhorn"
    _unrecorded_attributes = frozenset({"recent"})

    def __init__(self, coordinator: SmartdailyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CAT_ANNOUNCEMENT, "announcement_latest", "最新公告")

    @property
    def _latest(self) -> dict | None:
        return self.category_data.get("latest")

    @property
    def native_value(self) -> str | None:
        latest = self._latest
        return (latest.get("Title") or "")[:255] if latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = self._latest
        if latest is None:
            return {}
        recent = [
            {
                "Id": i.get("Id"),
                "Title": i.get("Title"),
                "TypeName": i.get("TypeName"),
                "created_at": i.get("created_at"),
                "unread": i.get("unread"),
                "link": i.get("link"),
            }
            for i in self.category_data.get("items") or []
            if not i.get("pinned")
        ][:RECENT_ANNOUNCEMENTS]
        return {
            "Id": latest.get("Id"),
            "TypeName": latest.get("TypeName"),
            "created_at": latest.get("created_at"),
            "unread": latest.get("unread"),
            "pinned": latest.get("pinned"),
            "link": latest.get("link"),
            "recent": recent,
        }


class PointsSensor(SmartdailyEntity, SensorEntity):
    """社區點數。"""

    _attr_icon = "mdi:star-circle-outline"
    _attr_native_unit_of_measurement = "點"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SmartdailyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, CAT_POINTS, "points", "社區點數")

    @property
    def native_value(self) -> int | None:
        return self.category_data.get("point")
