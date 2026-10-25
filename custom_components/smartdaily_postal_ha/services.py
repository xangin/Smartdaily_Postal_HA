"""Actions (services) for Smartdaily."""

from __future__ import annotations

import os
import time

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CAT_COLLECTION, CAT_PACKAGE, DOMAIN
from .links import item_id
from .photos import async_get_photo, get_runtime

SERVICE_SAVE_IMAGE = "save_image"
DEFAULT_SUBDIR = "smartdaily_postal_ha"
DEFAULT_WAIT = 30  # 秒；剛登記時照片可能還沒上傳
KEEP_DAYS = 7

SAVE_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("category"): vol.In([CAT_PACKAGE, CAT_COLLECTION]),
        vol.Required("key"): cv.string,
        vol.Optional("directory", default=""): cv.string,
        vol.Optional("wait", default=DEFAULT_WAIT): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=120)
        ),
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    async def save_image(call: ServiceCall) -> ServiceResponse:
        """把指定包裹／寄放物的照片存成本機 JPEG，回傳檔案路徑。"""
        runtime = get_runtime(hass, call.data["entry_id"])
        if runtime is None:
            raise ServiceValidationError("找不到已載入的智生活整合（entry_id 錯誤或整合未載入）")
        category = call.data["category"]
        if category not in runtime.categories:
            raise ServiceValidationError(f"此整合未啟用 {category} 類別")

        directory = call.data["directory"] or _default_directory(hass)
        if not hass.config.is_allowed_path(directory):
            raise ServiceValidationError(
                f"{directory} 不在允許寫入的資料夾（allowlist_external_dirs）內"
            )

        item = item_id(call.data["key"])
        jpeg = await async_get_photo(hass, runtime, category, item, wait=call.data["wait"])
        if jpeg is None:
            raise HomeAssistantError("目前無法取得這筆資料的照片")

        path = os.path.join(directory, f"{category}_{item}.jpg")
        await hass.async_add_executor_job(_write, directory, path, jpeg)
        return {"path": path}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_IMAGE,
        save_image,
        schema=SAVE_IMAGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _default_directory(hass: HomeAssistant) -> str:
    # 預設存到媒體資料夾（不需登入就能存取的 www 不適合放有姓名地址的貨運單照片）
    media = hass.config.media_dirs.get("local") or next(
        iter(hass.config.media_dirs.values()), hass.config.path("media")
    )
    return os.path.join(media, DEFAULT_SUBDIR)


def _write(directory: str, path: str, data: bytes) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as file:
        file.write(data)
    # 清掉本動作產生、超過保存天數的舊照片
    cutoff = time.time() - KEEP_DAYS * 86400
    for name in os.listdir(directory):
        if not name.endswith(".jpg") or not name.startswith((f"{CAT_PACKAGE}_", f"{CAT_COLLECTION}_")):
            continue
        full = os.path.join(directory, name)
        try:
            if os.path.getmtime(full) < cutoff:
                os.remove(full)
        except OSError:
            pass
