"""Pure data helpers for Smartdaily API records.

本模組不 import Home Assistant，可單獨測試。
"""

from __future__ import annotations

from datetime import datetime
import html
import re
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d",
)

PACKAGE_UNCLAIMED = 1
PACKAGE_CLAIMED = 2


def parse_local(value: Any) -> datetime | None:
    """Parse an API time string. API 回傳的時間已是台灣時間，不需再轉時區。"""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if "T" in text:  # 已轉成 ISO 格式的欄位（arrived_at 等）
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def to_iso(value: Any) -> str | None:
    dt = parse_local(value)
    return dt.isoformat() if dt else None


def _sort_key(dt: datetime | None) -> datetime:
    return dt or datetime.min.replace(tzinfo=TZ)


# ---------- 包裹 ----------


def package_key(record: dict) -> str:
    return str(record.get("pd_id") or "")


def package_arrived(record: dict) -> datetime | None:
    return parse_local(record.get("OriginCreateDate")) or parse_local(
        record.get("create_date")
    )


def enrich_package(record: dict) -> dict:
    """原始欄位加上幾個方便使用的欄位。"""
    out = dict(record)
    arrived = package_arrived(record)
    out["arrived_at"] = arrived.isoformat() if arrived else None
    out["picked_up_at"] = to_iso(record.get("receive_date"))
    # p_status 1 = 未領取，其餘（2 已取件等）都視為已處理
    out["claimed"] = record.get("p_status") != PACKAGE_UNCLAIMED
    out["refrigerated"] = bool(record.get("is_refrigerated"))
    return out


def split_packages(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """回傳 (未領取, 已取件)，皆為最新在前。"""
    items = [enrich_package(r) for r in records]
    unclaimed = [i for i in items if not i["claimed"]]
    claimed = [i for i in items if i["claimed"]]
    unclaimed.sort(key=lambda i: _sort_key(parse_local(i["arrived_at"])), reverse=True)
    claimed.sort(
        key=lambda i: _sort_key(
            parse_local(i["picked_up_at"]) or parse_local(i["arrived_at"])
        ),
        reverse=True,
    )
    return unclaimed, claimed


def latest_package(records: list[dict]) -> dict | None:
    if not records:
        return None
    return enrich_package(max(records, key=lambda r: _sort_key(package_arrived(r))))


# ---------- 寄放物 ----------


def collection_key(record: dict) -> str:
    # serial_num 會循環使用（如 B63），加上寄放時間才唯一
    return f"{record.get('serial_num', '')}|{record.get('sdate', '')}"


def enrich_collection(record: dict, my_tablet: str | None) -> dict:
    out = dict(record)
    out["deposited_at"] = to_iso(record.get("sdate"))
    out["claimed"] = record.get("is_end") == "yes"
    out["collected_at"] = to_iso(record.get("ddate")) if out["claimed"] else None
    out["is_mine"] = (
        record.get("to_tablet") == my_tablet if my_tablet else None
    )
    return out


def filter_collections(records: list[dict], community: str | None) -> list[dict]:
    """寄放物 API 不帶 com_id，會回傳所有社區的紀錄，以社區名稱過濾。"""
    if not community:
        return list(records)
    return [r for r in records if r.get("community") in (None, "", community)]


def split_collections(
    records: list[dict], my_tablet: str | None
) -> tuple[list[dict], list[dict]]:
    """回傳 (未領取, 已領取)，皆為最新在前。"""
    items = [enrich_collection(r, my_tablet) for r in records]
    unclaimed = [i for i in items if not i["claimed"]]
    claimed = [i for i in items if i["claimed"]]
    unclaimed.sort(key=lambda i: _sort_key(parse_local(i["deposited_at"])), reverse=True)
    claimed.sort(
        key=lambda i: _sort_key(
            parse_local(i["collected_at"]) or parse_local(i["deposited_at"])
        ),
        reverse=True,
    )
    return unclaimed, claimed


# ---------- 公告 ----------


def announcement_key(record: dict) -> str:
    return str(record.get("Id") or "")


def enrich_announcement(record: dict) -> dict:
    out = dict(record)
    out["created_at"] = to_iso(record.get("CreateDate"))
    out["pinned"] = bool(record.get("IsTop"))
    out["unread"] = not record.get("AlreadyRead", False)
    return out


def sort_announcements(records: list[dict]) -> list[dict]:
    """依建立時間排序（最新在前）。API 會把置頂的舊公告排在最前面，不能直接取第一筆。"""
    # 分頁取得時清單若剛好異動可能重複，依 Id 去重
    unique = {announcement_key(r): r for r in records}
    items = [enrich_announcement(r) for r in unique.values()]
    items.sort(key=lambda i: _sort_key(parse_local(i["created_at"])), reverse=True)
    return items


def html_to_text(value: str | None) -> str:
    """公告內文 HTML 轉純文字。"""
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def file_extension(url: str) -> str:
    """附件網址的副檔名（小寫，不含點）；簽名網址的 query 不影響判斷。"""
    path = urlparse(url).path
    return path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""


def latest_announcement(records: list[dict]) -> dict | None:
    items = sort_announcements(records)
    if not items:
        return None
    normal = [i for i in items if not i["pinned"]]
    return (normal or items)[0]


# ---------- 個人資料 ----------


def community_profile(profile: dict, com_id: str) -> dict:
    """從 GetProfileInfo 取出指定社區的資料（戶號、社區名、點數）。"""
    for item in profile.get("plist") or []:
        if str(item.get("com_id")) == str(com_id):
            return item
    return {}


# ---------- 變化偵測 ----------


def snapshot(records: list[dict], key_fn, done_fn) -> dict[str, bool]:
    return {key_fn(r): bool(done_fn(r)) for r in records if key_fn(r)}


def diff_snapshots(
    prev: dict[str, bool] | None, cur: dict[str, bool]
) -> list[tuple[str, str]]:
    """比對兩次快照，回傳 [(key, change)]。

    change: "new_open" 新出現且未完成、"new_done" 新出現且已完成、"done" 由未完成變完成。
    prev 為 None（第一次執行）時不產生任何變化，只建立基準。
    """
    if prev is None:
        return []
    changes: list[tuple[str, str]] = []
    for key, done in cur.items():
        if key not in prev:
            changes.append((key, "new_done" if done else "new_open"))
        elif done and not prev[key]:
            changes.append((key, "done"))
    return changes


def next_snapshot(
    prev: dict[str, bool] | None, cur: dict[str, bool]
) -> dict[str, bool] | None:
    """API 偶爾回傳空清單時保留舊快照，避免下次全部被當成新項目。"""
    if not cur and prev:
        return prev
    return cur
