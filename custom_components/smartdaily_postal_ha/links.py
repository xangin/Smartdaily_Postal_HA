"""Signed, long-lived links served by this integration.

智生活的照片／附件網址 15 分鐘就失效，通知裡的連結需要長期有效，
所以改由 HA 提供穩定網址，點開時才向 API 取得最新的檔案。

HA 內建的 async_sign_path 密鑰不會保存，重啟後連結全部失效，
因此使用每個 config entry 自己保存的密鑰做 HMAC 簽名。
"""

from __future__ import annotations

import hashlib
import hmac
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN

URL_BASE = f"/api/{DOMAIN}"
LINK_DAYS = 30
_DAY = 86400


def item_id(key: str) -> str:
    """URL-safe id for a record key（寄放物 key 含 / 與 |）。"""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class LinkSigner:
    """產生與驗證連結簽名。"""

    def __init__(self, hass: HomeAssistant, entry_id: str, secret: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._secret = secret.encode()

    def _signature(self, path: str, exp: int) -> str:
        return hmac.new(
            self._secret, f"{path}|{exp}".encode(), hashlib.sha256
        ).hexdigest()[:32]

    def verify(self, path: str, exp: str | None, token: str | None) -> bool:
        if not exp or not token or not exp.isdigit():
            return False
        if int(exp) < time.time():
            return False
        return hmac.compare_digest(self._signature(path, int(exp)), token)

    def _link(self, path: str) -> dict[str, str]:
        # 到期日以天為單位，同一天內連結不變，屬性才不會每次更新都改變
        exp = (int(time.time()) // _DAY + LINK_DAYS + 1) * _DAY
        path_q = f"{path}?exp={exp}&t={self._signature(path, exp)}"
        try:
            # 通知服務（如 LINE）會從外部抓圖，優先使用外部網址
            base = get_url(self._hass, prefer_external=True)
        except NoURLAvailableError:
            base = ""
        return {"url": base + path_q, "path": path_q}

    def image(self, category: str, key: str) -> dict[str, str]:
        return self._link(f"{URL_BASE}/image/{self._entry_id}/{category}/{item_id(key)}.jpg")

    def announcement(self, announcement_id: str) -> dict[str, str]:
        return self._link(f"{URL_BASE}/announcement/{self._entry_id}/{announcement_id}")
