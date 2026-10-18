"""Tests for parsers.py (不需安裝 Home Assistant)。

執行：python3 tests/test_parsers.py   或   pytest tests/
"""

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "smartdaily_postal_ha" / "parsers.py"
)
_spec = importlib.util.spec_from_file_location("parsers", _PATH)
parsers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parsers)


def pkg(pd_id, status, created, received=""):
    return {
        "pd_id": pd_id,
        "p_status": status,
        "create_date": created.replace("-", "/")[:16],
        "OriginCreateDate": created,
        "receive_date": received,
        "is_refrigerated": 0,
    }


def col(serial, is_end, sdate, ddate="", to_tablet="A-1", community="測試社區"):
    return {
        "serial_num": serial,
        "is_end": is_end,
        "sdate": sdate,
        "ddate": ddate,
        "to_tablet": to_tablet,
        "community": community,
    }


def ann(aid, created, top=0, read=False):
    return {"Id": aid, "Title": f"公告{aid}", "IsTop": top, "CreateDate": created,
            "AlreadyRead": read}


def test_parse_local_is_taipei_time_without_shift():
    # API 時間已是台灣時間，不可再加 8 小時（舊版 parse_time 的錯誤）
    dt = parsers.parse_local("2026/10/15 15:18")
    assert dt.isoformat() == "2026-10-15T15:18:00+08:00"
    assert parsers.to_iso("2026-10-15 15:18:00") == "2026-10-15T15:18:00+08:00"
    assert parsers.parse_local("剛剛") is None
    assert parsers.parse_local(None) is None


def test_split_packages_sorted_newest_first():
    records = [
        pkg("a", 1, "2026-10-01 10:00:00"),
        pkg("b", 1, "2026-10-03 10:00:00"),
        pkg("c", 2, "2026-10-02 10:00:00", "2026/10/04 09:00"),
        pkg("d", 2, "2026-10-05 10:00:00", "2026/10/05 12:00"),
    ]
    unclaimed, claimed = parsers.split_packages(records)
    assert [p["pd_id"] for p in unclaimed] == ["b", "a"]
    assert [p["pd_id"] for p in claimed] == ["d", "c"]
    assert claimed[0]["picked_up_at"] == "2026-10-05T12:00:00+08:00"
    assert parsers.latest_package(records)["pd_id"] == "d"
    assert parsers.latest_package([]) is None


def test_collections_filter_and_is_mine():
    records = [
        col("B1", "no", "2026/10/16 07:00", to_tablet="A-1"),
        col("B2", "yes", "2026/10/15 07:00", "2026/10/15 09:00", to_tablet="B-2"),
        col("B3", "no", "2026/10/16 08:00", community="別的社區"),
    ]
    filtered = parsers.filter_collections(records, "測試社區")
    assert [r["serial_num"] for r in filtered] == ["B1", "B2"]
    unclaimed, claimed = parsers.split_collections(filtered, "A-1")
    assert unclaimed[0]["is_mine"] is True
    assert claimed[0]["is_mine"] is False
    assert claimed[0]["collected_at"] == "2026-10-15T09:00:00+08:00"
    # 不知道自己戶號時 is_mine 為 None，不要誤判
    assert parsers.split_collections(filtered, None)[0][0]["is_mine"] is None


def test_collection_key_unique_with_reused_serial():
    a = col("B63", "yes", "2026/10/01 07:00")
    b = col("B63", "no", "2026/10/16 07:00")
    assert parsers.collection_key(a) != parsers.collection_key(b)


def test_latest_announcement_skips_pinned():
    records = [
        ann("old-top", "2024-10-28 13:55:25", top=2, read=True),
        ann("new1", "2026-10-15 15:19:33"),
        ann("new2", "2026-10-15 15:31:27"),
    ]
    latest = parsers.latest_announcement(records)
    assert latest["Id"] == "new2"
    assert latest["unread"] is True
    assert parsers.latest_announcement([ann("t", "2024-01-01 00:00:00", top=2)])["Id"] == "t"


def test_diff_first_run_is_baseline_only():
    assert parsers.diff_snapshots(None, {"a": False}) == []


def test_diff_detects_new_and_done():
    prev = {"a": False, "b": False, "c": True}
    cur = {"a": True, "b": False, "c": True, "d": False, "e": True}
    changes = dict(parsers.diff_snapshots(prev, cur))
    assert changes == {"a": "done", "d": "new_open", "e": "new_done"}


def test_diff_multiple_arrivals_in_one_poll():
    # 舊版用數量比較，同時到兩件只會通知一次
    changes = parsers.diff_snapshots({"a": False}, {"a": False, "b": False, "c": False})
    assert sorted(changes) == [("b", "new_open"), ("c", "new_open")]


def test_arrival_and_pickup_in_same_poll_both_reported():
    # 數量不變（一件到、一件被領）舊版不會通知
    changes = dict(parsers.diff_snapshots({"a": False}, {"a": True, "b": False}))
    assert changes == {"a": "done", "b": "new_open"}


def test_empty_response_keeps_previous_snapshot():
    prev = {"a": False}
    assert parsers.next_snapshot(prev, {}) == prev
    assert parsers.next_snapshot(None, {}) == {}
    assert parsers.next_snapshot(prev, {"b": True}) == {"b": True}


def test_html_to_text():
    assert parsers.html_to_text("<p>請參閱附件</p>\n") == "請參閱附件"
    assert parsers.html_to_text("第一行<br>第二行<br/>&amp;結束") == "第一行\n第二行\n&結束"
    assert parsers.html_to_text(None) == ""


def test_file_extension_ignores_signed_query():
    url = "https://storage.googleapis.com/b/a/file.PDF?X-Goog-Expires=899&x=1.jpg"
    assert parsers.file_extension(url) == "pdf"
    assert parsers.file_extension("https://x/y/noext") == ""


def test_community_profile():
    profile = {"plist": [{"com_id": "1", "point": 5}, {"com_id": "2", "point": 9}]}
    assert parsers.community_profile(profile, "2")["point"] == 9
    assert parsers.community_profile(profile, "3") == {}
    assert parsers.community_profile({}, "1") == {}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} passed")
