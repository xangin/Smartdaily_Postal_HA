"""The Smartdaily Postal integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import SmartdailyApi, SmartdailyError
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
    FAST_CATEGORIES,
    SLOW_CATEGORIES,
)
from .coordinator import SmartdailyCoordinator, SmartdailyRuntime, SnapshotStore
from .entity import expected_unique_ids
from .links import LinkSigner
from .services import async_register_services
from .views import SmartdailyAnnouncementView, SmartdailyImageView

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.CAMERA, Platform.EVENT, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type SmartdailyConfigEntry = ConfigEntry[SmartdailyRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> None | bool:
    """註冊照片與公告連結的 HTTP view，以及 save_image 動作。"""
    hass.http.register_view(SmartdailyImageView())
    hass.http.register_view(SmartdailyAnnouncementView())
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmartdailyConfigEntry) -> bool:
    """Set up Smartdaily from a config entry."""
    options = entry.options
    # 舊版設定沒有 options，預設全部啟用
    categories = set(options.get(CONF_CATEGORIES, ALL_CATEGORIES))

    api = SmartdailyApi(async_get_clientsession(hass), entry.data[CONF_DEVICE_ID])
    store = SnapshotStore(hass, entry.entry_id)
    await store.async_load()
    # 停用過的類別清掉舊快照，重新啟用時才不會一次補發大量通知
    for category in store.categories():
        if category not in categories:
            store.set(category, None)

    runtime = SmartdailyRuntime(
        api=api,
        com_id=str(entry.data[CONF_COM_ID]),
        categories=categories,
        store=store,
        links=LinkSigner(hass, entry.entry_id, store.secret()),
    )
    try:
        # 取得自己的戶號（判斷寄放物是否給自己）與社區名稱
        runtime.update_profile(await api.get_profile())
    except SmartdailyError as err:
        raise ConfigEntryNotReady(f"無法連線智生活 API：{err}") from err

    groups = (
        ("fast", categories & FAST_CATEGORIES, CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
        ("slow", categories & SLOW_CATEGORIES, CONF_SLOW_INTERVAL, DEFAULT_SLOW_INTERVAL),
    )
    for name, group, conf_key, default in groups:
        if group:
            runtime.coordinators[name] = SmartdailyCoordinator(
                hass, entry, runtime, name, group, int(options.get(conf_key, default))
            )

    entry.runtime_data = runtime
    for coordinator in runtime.coordinators.values():
        await coordinator.async_config_entry_first_refresh()

    _remove_stale_entities(hass, entry, categories)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartdailyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """刪除整合時一併移除快照檔。"""
    await SnapshotStore(hass, entry.entry_id).async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, categories: set[str]
) -> None:
    """移除停用類別的實體，以及舊版的「包裹 1~4」slot 實體。"""
    registry = er.async_get(hass)
    expected = expected_unique_ids(entry, categories)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id not in expected:
            _LOGGER.debug("Removing stale entity %s", entity.entity_id)
            registry.async_remove(entity.entity_id)
