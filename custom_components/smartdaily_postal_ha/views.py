"""HTTP views for signed photo and announcement links."""

from __future__ import annotations

import html
import logging

from aiohttp import web

from homeassistant.helpers.http import KEY_HASS, HomeAssistantView

from . import parsers
from .api import SmartdailyError
from .const import DOMAIN
from .coordinator import SmartdailyRuntime
from .links import URL_BASE
from .photos import IMAGE_SOURCES, async_get_photo, get_runtime

_LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
LINK_WAIT = 10  # 秒；外部服務下載逾時多為 20 秒


def _authorized(runtime: SmartdailyRuntime, request: web.Request) -> bool:
    return runtime.links.verify(
        request.path, request.query.get("exp"), request.query.get("t")
    )


class SmartdailyImageView(HomeAssistantView):
    """回傳包裹／寄放物照片（轉成 JPEG）。以連結內的簽名驗證，不需登入。"""

    url = URL_BASE + "/image/{entry_id}/{category}/{item}.jpg"
    name = f"api:{DOMAIN}:image"
    requires_auth = False

    async def get(
        self, request: web.Request, entry_id: str, category: str, item: str
    ) -> web.Response:
        hass = request.app[KEY_HASS]
        runtime = get_runtime(hass, entry_id)
        if runtime is None or category not in IMAGE_SOURCES:
            return web.Response(status=404)
        if not _authorized(runtime, request):
            return web.Response(status=403)
        try:
            jpeg = await async_get_photo(hass, runtime, category, item, wait=LINK_WAIT)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("照片轉 JPEG 失敗")
            return web.Response(status=500)
        if jpeg is None:
            # 照片尚未提供（剛登記時可能還沒上傳）
            return web.Response(status=404, headers={"Cache-Control": "no-store"})
        return web.Response(
            body=jpeg,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )


class SmartdailyAnnouncementView(HomeAssistantView):
    """點開公告連結時才呼叫 Detail API（該公告會被標成已讀）。

    只有一個附件時直接轉址到附件；否則顯示內文與附件清單。
    """

    url = URL_BASE + "/announcement/{entry_id}/{announcement_id}"
    name = f"api:{DOMAIN}:announcement"
    requires_auth = False

    async def get(
        self, request: web.Request, entry_id: str, announcement_id: str
    ) -> web.Response:
        hass = request.app[KEY_HASS]
        runtime = get_runtime(hass, entry_id)
        if runtime is None:
            return web.Response(status=404)
        if not _authorized(runtime, request):
            return web.Response(status=403)

        try:
            detail = await runtime.api.get_announcement_detail(
                runtime.com_id, announcement_id
            )
        except SmartdailyError as err:
            _LOGGER.warning("取得公告失敗：%s", err)
            return web.Response(status=502, text="無法取得公告，請稍後再試。")

        files = [f["Url"] for f in detail.get("AttachedFile") or [] if f.get("Url")]
        text = parsers.html_to_text(detail.get("Content") or detail.get("Detail"))
        if len(files) == 1 and text in ("", "請參閱附件"):
            raise web.HTTPFound(files[0])
        return web.Response(
            text=_render(detail.get("Title") or "", detail.get("CreateDate") or "", text, files),
            content_type="text/html",
            headers={"Cache-Control": "no-store"},
        )


def _render(title: str, date: str, text: str, files: list[str]) -> str:
    parts = []
    for index, url in enumerate(files, 1):
        ext = parsers.file_extension(url)
        safe = html.escape(url, quote=True)
        if ext in IMAGE_EXTENSIONS:
            parts.append(f'<a href="{safe}"><img src="{safe}" alt="附件 {index}"></a>')
        else:
            label = f"附件 {index}" + (f"（{ext.upper()}）" if ext else "")
            parts.append(f'<p><a class="file" href="{safe}">{label}</a></p>')
    body = html.escape(text).replace("\n", "<br>")
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0 auto;max-width:720px;padding:16px;line-height:1.6;color:#222;background:#fff}}
@media (prefers-color-scheme:dark){{body{{color:#ddd;background:#111}}a{{color:#8ab4f8}}}}
h1{{font-size:1.3em;margin:0 0 4px}} .date{{color:#888;font-size:.9em;margin-bottom:16px}}
img{{max-width:100%;height:auto;margin:8px 0;border-radius:6px}}
a.file{{display:inline-block;padding:10px 14px;border:1px solid #888;border-radius:6px;text-decoration:none}}
.note{{color:#888;font-size:.8em;margin-top:24px}}
</style></head><body>
<h1>{html.escape(title)}</h1><div class="date">{html.escape(date)}</div>
<div>{body}</div>
{"".join(parts) or "<p>沒有附件。</p>"}
<p class="note">附件連結 15 分鐘內有效，過期請重新整理此頁。</p>
</body></html>"""
