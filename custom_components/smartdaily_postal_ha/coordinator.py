"""Data update coordinators for Smartdaily."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
import secrets
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
    Event,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import parsers
from .api import SmartdailyApi, SmartdailyError
from .const import (
    CAT_ANNOUNCEMENT,
    CAT_COLLECTION,
    CAT_PACKAGE,
    CAT_POINTS,
    DOMAIN,
    STORAGE_VERSION,
)
from .links import LinkSigner

_LOGGER = logging.getLogger(__name__)

ANNOUNCEMENT_FETCH_COUNT = 20

# (category, event_type, record)
EventListener = Callable[[str, str, dict], None]


class SnapshotStore:
    """保存上次看到的項目狀態，重啟後才不會重複通知。"""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.data: dict[str, dict[str, bool]] = {}

    async def async_load(self) -> None:
        self.data = await self._store.async_load() or {}

    def get(self, category: str) -> dict[str, bool] | None:
        return self.data.get(category)

    def set(self, category: str, snap: dict[str, bool] | None) -> None:
        if snap is None:
            self.data.pop(category, None)
        else:
            self.data[category] = snap

    def secret(self) -> str:
        """連結簽名用密鑰，第一次使用時產生並保存。"""
        if "_secret" not in self.data:
            self.data["_secret"] = secrets.token_hex(32)
            self.save()
        return self.data["_secret"]

    def categories(self) -> list[str]:
        return [k for k in self.data if not k.startswith("_")]

    def save(self) -> None:
        self._store.async_delay_save(lambda: self.data, 5)

    async def async_remove(self) -> None:
        await self._store.async_remove()


@dataclass
class SmartdailyRuntime:
    """config entry 的執行期資料（entry.runtime_data）。"""

    api: SmartdailyApi
    com_id: str
    categories: set[str]
    store: SnapshotStore
    links: LinkSigner
    community: str | None = None
    my_tablet: str | None = None
    coordinators: dict[str, "SmartdailyCoordinator"] = field(default_factory=dict)
    # 轉好的 JPEG 快取（照片連結被重複開啟時不必重抓）
    image_cache: OrderedDict[str, bytes] = field(default_factory=OrderedDict)

    def coordinator_for(self, category: str) -> "SmartdailyCoordinator":
        for coordinator in self.coordinators.values():
            if category in coordinator.categories:
                return coordinator
        raise KeyError(category)

    def update_profile(self, profile: dict) -> dict:
        info = parsers.community_profile(profile, self.com_id)
        self.community = info.get("community") or self.community
        self.my_tablet = info.get("tablet_note") or self.my_tablet
        return info


class SmartdailyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """一個 coordinator 負責一組類別（快：包裹/寄放物；慢：公告/點數）。"""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        runtime: SmartdailyRuntime,
        name: str,
        categories: set[str],
        minutes: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Smartdaily {name}",
            update_interval=timedelta(minutes=minutes),
        )
        self.runtime = runtime
        self.categories = categories
        self.last_error: str | None = None
        self._event_listeners: list[EventListener] = []
        self._pending_events: list[tuple[str, str, dict]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        events: list[tuple[str, str, dict]] = []
        data: dict[str, Any] = {}
        api = self.runtime.api
        com_id = self.runtime.com_id
        try:
            if CAT_POINTS in self.categories:
                data[CAT_POINTS] = self._process_points(await api.get_profile())
            if CAT_PACKAGE in self.categories:
                data[CAT_PACKAGE] = self._process_packages(
                    await api.get_packages(com_id), events
                )
            if CAT_COLLECTION in self.categories:
                data[CAT_COLLECTION] = self._process_collections(
                    await api.get_collections(), events
                )
            if CAT_ANNOUNCEMENT in self.categories:
                data[CAT_ANNOUNCEMENT] = self._process_announcements(
                    await api.get_announcements(com_id, ANNOUNCEMENT_FETCH_COUNT),
                    events,
                )
        except SmartdailyError as err:
            self.last_error = str(err)
            raise UpdateFailed(str(err)) from err

        self.last_error = None
        self.runtime.store.save()
        # 等 coordinator.data 寫入後（async_update_listeners）才發送事件，
        # 自動化觸發時讀到的實體狀態才會是最新的
        self._pending_events = events
        return data

    @callback
    def async_update_listeners(self) -> None:
        events, self._pending_events = self._pending_events, []
        if events:
            self._dispatch(events)
        super().async_update_listeners()

    @callback
    def async_add_event_listener(self, listener: EventListener) -> CALLBACK_TYPE:
        """event 實體註冊，收到每一筆異動。"""
        self._event_listeners.append(listener)

        @callback
        def remove() -> None:
            self._event_listeners.remove(listener)

        return remove

    def _dispatch(self, events: list[tuple[str, str, dict]]) -> None:
        # HA 啟動中（例如重啟期間有包裹到）先暫存，等自動化載入後再發送
        if self.hass.state is CoreState.running:
            self._fire(events)
            return

        @callback
        def fire_later(_event: Event) -> None:
            self._fire(events)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, fire_later)

    @callback
    def _fire(self, events: list[tuple[str, str, dict]]) -> None:
        entry_id = self.config_entry.entry_id
        for category, event_type, record in events:
            self.hass.bus.async_fire(
                f"{DOMAIN}_{category}",
                {"type": event_type, "entry_id": entry_id, **record},
            )
            for listener in list(self._event_listeners):
                listener(category, event_type, record)

    def _diff(
        self,
        category: str,
        records: list[dict],
        key_fn,
        done_fn,
    ) -> list[tuple[str, str]]:
        store = self.runtime.store
        prev = store.get(category)
        cur = parsers.snapshot(records, key_fn, done_fn)
        changes = parsers.diff_snapshots(prev, cur)
        store.set(category, parsers.next_snapshot(prev, cur))
        return changes

    def _process_packages(self, records: list[dict], events: list) -> dict:
        unclaimed, claimed = parsers.split_packages(records)
        self._add_image_links(CAT_PACKAGE, unclaimed + claimed, parsers.package_key)
        by_key = {parsers.package_key(i): i for i in unclaimed + claimed}
        for key, change in self._diff(
            CAT_PACKAGE,
            records,
            parsers.package_key,
            lambda r: r.get("p_status") != parsers.PACKAGE_UNCLAIMED,
        ):
            event_type = "arrived" if change == "new_open" else "picked_up"
            events.append((CAT_PACKAGE, event_type, by_key[key]))
        return {
            "unclaimed": unclaimed,
            "claimed": claimed,
            "latest": parsers.latest_package(records),
        }

    def _process_collections(self, records: list[dict], events: list) -> dict:
        records = parsers.filter_collections(records, self.runtime.community)
        unclaimed, claimed = parsers.split_collections(records, self.runtime.my_tablet)
        self._add_image_links(CAT_COLLECTION, unclaimed + claimed, parsers.collection_key)
        by_key = {parsers.collection_key(i): i for i in unclaimed + claimed}
        for key, change in self._diff(
            CAT_COLLECTION,
            records,
            parsers.collection_key,
            lambda r: r.get("is_end") == "yes",
        ):
            event_type = "deposited" if change == "new_open" else "collected"
            events.append((CAT_COLLECTION, event_type, by_key[key]))
        latest = unclaimed[0] if unclaimed else (claimed[0] if claimed else None)
        return {"unclaimed": unclaimed, "claimed": claimed, "latest": latest}

    def _process_announcements(self, records: list[dict], events: list) -> dict:
        items = parsers.sort_announcements(records)
        for item in items:
            # 點開才呼叫 Detail API（會標成已讀），背景更新不會
            link = self.runtime.links.announcement(parsers.announcement_key(item))
            item["link"] = link["url"]
            item["link_path"] = link["path"]
        by_key = {parsers.announcement_key(i): i for i in items}
        for key, _change in self._diff(
            CAT_ANNOUNCEMENT, records, parsers.announcement_key, lambda r: True
        ):
            events.append((CAT_ANNOUNCEMENT, "new", by_key[key]))
        return {
            "items": items,
            "unread": [i for i in items if i["unread"]],
            "latest": parsers.latest_announcement(records),
        }

    def _add_image_links(self, category: str, items: list[dict], key_fn) -> None:
        """加上長期有效的 JPEG 照片連結（image_url 給通知、image_path 給儀表板）。"""
        for item in items:
            key = key_fn(item)
            link = self.runtime.links.image(category, key)
            item["image_url"] = link["url"]
            item["image_path"] = link["path"]
            item["image_key"] = key  # 給 save_image 動作使用

    def _process_points(self, profile: dict) -> dict:
        info = self.runtime.update_profile(profile)
        return {
            "point": info.get("point"),
            "carrier_count": info.get("carrier_count"),
            "community": info.get("community"),
        }
