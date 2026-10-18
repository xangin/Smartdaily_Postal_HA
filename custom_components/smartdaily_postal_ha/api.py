"""Async client for the Smartdaily API."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.smartdaily.com.tw/api"
TOKEN_TTL = 30 * 60  # 秒；token 有效期不明，保守定期更新
TIMEOUT = aiohttp.ClientTimeout(total=20)
ANNOUNCEMENT_PAGE_SIZE = 10  # API 上限

_BASE_HEADERS = {
    "Connection": "keep-alive",
    "Accept": "application/json, text/plain, */*",
}
# 公告 API 需要 app 版本 header
_APP_HEADERS = {"x-app-version": "4.5.2", "User-Agent": "Mozilla/5.0"}


class SmartdailyError(Exception):
    """API 呼叫失敗。"""


class SmartdailyAuthError(SmartdailyError):
    """DeviceID 無效或無法取得 token。"""


class SmartdailyApi:
    """Smartdaily API client，多個 coordinator 共用同一個 token。"""

    def __init__(self, session: aiohttp.ClientSession, device_id: str) -> None:
        self._session = session
        self._device_id = device_id
        self._token: str | None = None
        self._token_time = 0.0
        self._lock = asyncio.Lock()

    async def _request(self, path: str, params=None, headers=None) -> dict:
        try:
            async with self._session.get(
                BASE_URL + path, params=params, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise SmartdailyAuthError(f"HTTP {resp.status} on {path}")
                if resp.status != 200:
                    body = (await resp.text())[:300]
                    raise SmartdailyError(f"HTTP {resp.status} on {path}: {body}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SmartdailyError(f"{path}: {err}") from err

    async def _ensure_token(self, force: bool = False) -> str:
        async with self._lock:
            if (
                not force
                and self._token
                and time.monotonic() - self._token_time < TOKEN_TTL
            ):
                return self._token
            data = await self._request(
                "/Valid/getHashCodeV2",
                params={"code": self._device_id},
                headers=_BASE_HEADERS,
            )
            token = (data.get("Data") or {}).get("token")
            if not token:
                raise SmartdailyAuthError("無法取得 token，請確認 DeviceID")
            self._token = f"CommunityUser {token}"
            self._token_time = time.monotonic()
            return self._token

    async def _get(self, path: str, params=None, app: bool = False) -> Any:
        """呼叫需要驗證的 API，失敗時更新 token 重試一次，回傳 Data。"""
        for attempt in (1, 2):
            token = await self._ensure_token(force=attempt == 2)
            headers = {**_BASE_HEADERS, "KingnetAuth": token}
            if app:
                headers.update(_APP_HEADERS)
            try:
                data = await self._request(path, params, headers)
            except SmartdailyAuthError:
                if attempt == 2:
                    raise
                continue
            if data.get("Status") == 1:
                return data.get("Data")
            if attempt == 2:
                raise SmartdailyError(
                    f"{path} 回傳 Status={data.get('Status')} {data.get('Message', '')}"
                )
        return None

    async def validate(self) -> None:
        await self._ensure_token(force=True)

    async def get_communities(self) -> list[dict]:
        return await self._get("/Community/GetUserCommunityList") or []

    async def get_packages(self, com_id: str) -> list[dict]:
        return await self._get("/Postal/getUserPostalList", {"com_id": com_id}) or []

    async def get_collections(self) -> list[dict]:
        return await self._get("/Collection/getCollectionPayment") or []

    async def get_profile(self) -> dict:
        return await self._get("/Profile/GetProfileInfo") or {}

    async def get_announcements(self, com_id: str, count: int = 10) -> list[dict]:
        # 注意：只用清單 API。呼叫 Announcement/Detail 會把公告標成已讀。
        # MaxCount 上限為 10，超過回 HTTP 400，需分頁取得
        results: list[dict] = []
        while len(results) < count:
            size = min(ANNOUNCEMENT_PAGE_SIZE, count - len(results))
            data = await self._get(
                "/v3.24/Announcement/Community/List",
                {"ComId": com_id, "Offset": len(results), "MaxCount": size},
                app=True,
            )
            page = (data or {}).get("Announcements") or []
            results += page
            if len(page) < size:
                break
        return results

    async def get_announcement_detail(self, com_id: str, announcement_id: str) -> dict:
        """公告內文與附件。注意：呼叫後該公告會被標成已讀，只在使用者點開連結時使用。"""
        return await self._get(
            "/v3.2/Announcement/Detail",
            {"com_id": com_id, "id": announcement_id},
            app=True,
        ) or {}
