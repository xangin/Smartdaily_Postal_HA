"""Camera platform: 最新包裹／寄放物照片。"""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import parsers
from .const import CAT_COLLECTION, CAT_PACKAGE, DEFAULT_IMAGE_URL
from .coordinator import SmartdailyCoordinator
from .entity import SmartdailyEntity
from .images import to_jpeg

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=10)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    entities: list[Camera] = []
    if CAT_PACKAGE in runtime.categories:
        entities.append(
            SmartdailyCamera(
                runtime.coordinator_for(CAT_PACKAGE), entry, CAT_PACKAGE,
                "camera", "包裹照片", "postal_img", parsers.package_key,
            )
        )
    if CAT_COLLECTION in runtime.categories:
        entities.append(
            SmartdailyCamera(
                runtime.coordinator_for(CAT_COLLECTION), entry, CAT_COLLECTION,
                "collection_camera", "寄放物照片", "CollectionImage",
                parsers.collection_key,
            )
        )
    async_add_entities(entities)


class SmartdailyCamera(SmartdailyEntity, Camera):
    """顯示最新一筆未領取（沒有則為最新一筆）的照片。

    照片網址是 15 分鐘有效的簽名網址，所以每次都從 coordinator 取當下的網址，
    並依項目快取圖片，避免儀表板縮圖每 10 秒重抓一次。
    """

    def __init__(
        self,
        coordinator: SmartdailyCoordinator,
        entry: ConfigEntry,
        category: str,
        key: str,
        name: str,
        image_field: str,
        key_fn,
    ) -> None:
        SmartdailyEntity.__init__(self, coordinator, entry, category, key, name)
        Camera.__init__(self)
        self._image_field = image_field
        self._key_fn = key_fn
        self._cache_key: str | None = None
        self._cache: bytes | None = None

    def _record(self) -> dict | None:
        data = self.category_data
        unclaimed = data.get("unclaimed") or []
        return unclaimed[0] if unclaimed else data.get("latest")

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        record = self._record()
        url = (record or {}).get(self._image_field) or DEFAULT_IMAGE_URL
        cache_key = self._key_fn(record) if record else "default"
        if record and not record.get(self._image_field):
            cache_key = "default"
        if cache_key == self._cache_key and self._cache is not None:
            return self._cache

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    _LOGGER.warning("取得照片失敗，HTTP %s", resp.status)
                    return self._cache
                raw = await resp.read()
                raw_type = resp.headers.get("Content-Type", "image/jpeg")
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("取得照片失敗：%s", err)
            return self._cache

        # 智生活照片是 WebP；camera.snapshot 會原樣寫檔，通知服務多半只收 JPEG
        try:
            self._cache = await self.hass.async_add_executor_job(to_jpeg, raw)
            self.content_type = "image/jpeg"
        except Exception as err:  # noqa: BLE001 - 轉檔失敗仍回傳原圖
            _LOGGER.warning("照片轉 JPEG 失敗，使用原始格式 %s：%s", raw_type, err)
            self._cache = raw
            self.content_type = raw_type
        self._cache_key = cache_key
        return self._cache

