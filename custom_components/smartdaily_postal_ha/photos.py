"""Fetch a specific package/collection photo as JPEG.

照片連結（views）與 save_image 動作共用。智生活照片網址 15 分鐘失效，
且剛登記時照片可能還沒上傳，因此會重新向 API 取得網址並在等待時間內重試。
"""

from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import ClientError, ClientTimeout

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import parsers
from .api import SmartdailyError
from .const import CAT_COLLECTION, CAT_PACKAGE, DOMAIN
from .coordinator import SmartdailyRuntime
from .images import to_jpeg
from .links import item_id

_LOGGER = logging.getLogger(__name__)
TIMEOUT = ClientTimeout(total=15)
CACHE_SIZE = 30
RETRY_INTERVAL = 5  # 秒

# category -> (key 函式, 照片欄位)
IMAGE_SOURCES = {
    CAT_PACKAGE: (parsers.package_key, "postal_img"),
    CAT_COLLECTION: (parsers.collection_key, "CollectionImage"),
}


def get_runtime(hass: HomeAssistant, entry_id: str) -> SmartdailyRuntime | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    return entry.runtime_data


async def async_get_photo(
    hass: HomeAssistant,
    runtime: SmartdailyRuntime,
    category: str,
    item: str,
    wait: float = 0,
) -> bytes | None:
    """回傳 JPEG；拿不到時在 wait 秒內每 5 秒重新向 API 取得一次。"""
    cache_key = f"{category}/{item}"
    if (cached := runtime.image_cache.get(cache_key)) is not None:
        return cached

    deadline = time.monotonic() + wait
    fresh = False
    reason = ""
    while True:
        raw, reason = await _download(hass, runtime, category, item, fresh)
        if raw is None and not fresh:
            # coordinator 裡的網址可能已過期，立即改用最新資料再試
            fresh = True
            raw, reason = await _download(hass, runtime, category, item, fresh)
        if raw is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _LOGGER.warning("無法取得照片 %s：%s", cache_key, reason)
            return None
        await asyncio.sleep(min(RETRY_INTERVAL, remaining))

    jpeg = await hass.async_add_executor_job(to_jpeg, raw)
    runtime.image_cache[cache_key] = jpeg
    while len(runtime.image_cache) > CACHE_SIZE:
        runtime.image_cache.popitem(last=False)
    return jpeg


async def _download(
    hass: HomeAssistant,
    runtime: SmartdailyRuntime,
    category: str,
    item: str,
    fresh: bool,
) -> tuple[bytes | None, str]:
    key_fn, field = IMAGE_SOURCES[category]
    record = await _find(runtime, category, item, key_fn, fresh)
    if record is None:
        return None, "找不到這筆資料"
    url = record.get(field)
    if not url:
        return None, "這筆資料尚未提供照片"
    try:
        async with async_get_clientsession(hass).get(url, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                return await resp.read(), ""
            return None, f"照片伺服器回應 HTTP {resp.status}"
    except (ClientError, TimeoutError) as err:
        return None, f"下載失敗：{type(err).__name__}"


async def _find(
    runtime: SmartdailyRuntime, category: str, item: str, key_fn, fresh: bool
) -> dict | None:
    if fresh:
        try:
            if category == CAT_PACKAGE:
                records = await runtime.api.get_packages(runtime.com_id)
            else:
                records = await runtime.api.get_collections()
        except SmartdailyError as err:
            _LOGGER.debug("取得照片資料失敗：%s", err)
            return None
    else:
        data = (runtime.coordinator_for(category).data or {}).get(category) or {}
        records = (data.get("unclaimed") or []) + (data.get("claimed") or [])
    return next((r for r in records if item_id(key_fn(r)) == item), None)
