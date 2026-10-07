"""逾期一致性回归：同一笔在 看板分栏 / 状态条计数 / 借还记录 / 详情 / 归还结论
五个面必须同进同出；非法钟点整单失败且失败后各面停在点前。

运行：cd backend && python -m pytest app/tests -q
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main

TODAY = "2026-10-07"
NOON = "12:00"
YESTERDAY = "2026-10-06"
TOMORROW = "2026-10-08"


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """每用例一个全新库；板内“现在”钉在 TODAY NOON，结论可复现。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_now", lambda: (TODAY, NOON))
    with TestClient(main.app) as c:
        yield c


def _lend(c, due_date, due_time="keep"):
    iid = c.post("/api/items", json={"title": "锯子", "owner": "老周"}).json()["id"]
    body = {"borrower": "邻居", "due_date": due_date}
    if due_time != "keep":
        body["due_time"] = due_time
    r = c.post(f"/api/items/{iid}/lend", json=body)
    return iid, r


def _verdicts(c, lid):
    """同一笔在四个读取面的逾期结论；归还结论另见 _return_verdict。"""
    board = c.get("/api/board").json()
    assert board["counts"]["overdue"] == len(board["overdue"])  # 顶细条计数与分栏同源
    assert board["counts"]["active"] == len(board["active"])
    board_od = any(l["id"] == lid for l in board["overdue"])
    board_act = any(l["id"] == lid for l in board["active"])
    records = c.get("/api/loans").json()
    rec_od = any(l["id"] == lid for l in records["overdue"])
    rec_act = any(l["id"] == lid for l in records["active"])
    detail = c.get(f"/api/loans/{lid}").json()
    assert board_od != board_act and rec_od != rec_act  # 一笔只能落一个栏
    return {"board": board_od, "records": rec_od, "detail": detail["overdue"]}


def _assert_all(c, lid, expected):
    v = _verdicts(c, lid)
    assert v == {"board": expected, "records": expected, "detail": expected}


def test_clock_passed_all_surfaces_overdue_together(api):
    _, r = _lend(api, TODAY, "11:59")  # 钟点已过
    assert r.status_code == 200
    _assert_all(api, r.json()["loan_id"], True)


def test_clock_not_yet_all_surfaces_not_overdue(api):
    _, r = _lend(api, TODAY, "12:30")  # 到日未到点
    _assert_all(api, r.json()["loan_id"], False)


def test_day_passed_with_grace_clock_not_yet_not_overdue(api):
    _, r = _lend(api, YESTERDAY, "12:30")  # 日历日已过，宽限 1 天顶回今天，钟点未到
    lid = r.json()["loan_id"]
    assert api.put("/api/settings/grace_days", json={"days": 1}).status_code == 200
    _assert_all(api, lid, False)
    # 宽限改回 0：各面一起进逾期，不许有的面还吃着旧宽限
    assert api.put("/api/settings/grace_days", json={"days": 0}).status_code == 200
    _assert_all(api, lid, True)


def test_day_fully_passed_overdue_regardless_of_clock(api):
    _, r = _lend(api, YESTERDAY, "23:59")
    _assert_all(api, r.json()["loan_id"], True)


def test_no_clock_keeps_whole_day_semantics(api):
    _, r1 = _lend(api, TODAY, None)       # 无钟点：应还日当天不算逾期
    _assert_all(api, r1.json()["loan_id"], False)
    _, r2 = _lend(api, YESTERDAY, None)   # 无钟点：日一过完即逾期
    _assert_all(api, r2.json()["loan_id"], True)


def test_return_verdict_matches_surfaces(api):
    _, r1 = _lend(api, TODAY, "11:00")    # 已过点
    lid1 = r1.json()["loan_id"]
    _assert_all(api, lid1, True)
    assert api.post(f"/api/loans/{lid1}/return").json()["overdue"] is True
    _, r2 = _lend(api, TODAY, "12:30")    # 未到点
    lid2 = r2.json()["loan_id"]
    assert api.post(f"/api/loans/{lid2}/return").json()["overdue"] is False
    # 归还后五个面都不再把它当在借/逾期
    board = api.get("/api/board").json()
    assert all(l["id"] not in (lid1, lid2) for l in board["active"] + board["overdue"])
    records = api.get("/api/loans").json()
    assert {lid1, lid2} <= {l["id"] for l in records["returned"]}


@pytest.mark.parametrize("bad", ["25:00", "9", "12:", ":30", "ab:cd", "12:60", "1:2:3"])
def test_illegal_due_time_fails_whole_order(api, bad):
    before = api.get("/api/board").json()
    iid, r = _lend(api, TODAY, bad)
    assert r.status_code == 422
    # 整单失败：一笔都不写，物品仍可借，各面停在点前
    assert api.get("/api/loans").json()["active"] == []
    after = api.get("/api/board").json()
    assert after["counts"] == before["counts"]
    item = [i for i in api.get("/api/items").json() if i["id"] == iid][0]
    assert item["status"] == "available"


def test_extend_moves_date_and_time_as_one_pair(api):
    _, r = _lend(api, TODAY, "11:00")     # 已过点 → 逾期
    lid = r.json()["loan_id"]
    _assert_all(api, lid, True)
    ext = api.post(f"/api/loans/{lid}/extend",
                   json={"days": 2, "time_policy": "follow_day"})
    assert ext.status_code == 200
    assert ext.json()["due_date"] == "2026-10-09" and ext.json()["due_time"] == "11:00"
    _assert_all(api, lid, False)          # 顺延到未来后各面一起退出逾期
    d = api.get(f"/api/loans/{lid}").json()
    assert d["due_date"] == "2026-10-09" and d["due_time"] == "11:00"  # 时分口径不分裂


def test_extend_time_policies_without_clock(api):
    _, r1 = _lend(api, TOMORROW, None)
    lid1 = r1.json()["loan_id"]
    ext = api.post(f"/api/loans/{lid1}/extend", json={"days": 1, "time_policy": "keep_time"})
    assert ext.json()["due_time"] == "23:59"   # 钉在原时刻：无钟点钉当日 23:59
    _, r2 = _lend(api, TOMORROW, None)
    lid2 = r2.json()["loan_id"]
    ext = api.post(f"/api/loans/{lid2}/extend", json={"days": 1, "time_policy": "follow_day"})
    assert ext.json()["due_time"] is None      # 跟着新日走：仍整日


def test_failed_extend_leaves_everything_as_before(api):
    _, r = _lend(api, TODAY, "11:00")
    lid = r.json()["loan_id"]
    before_detail = api.get(f"/api/loans/{lid}").json()
    before_board = api.get("/api/board").json()
    assert api.post(f"/api/loans/{lid}/extend",
                    json={"days": 1, "time_policy": "bogus"}).status_code == 422
    assert api.get(f"/api/loans/{lid}").json() == before_detail   # 详情停在点前
    assert api.get("/api/board").json() == before_board           # 分栏与顶细条也是


def test_grace_never_rewrites_stored_clock(api):
    _, r = _lend(api, YESTERDAY, "12:30")
    lid = r.json()["loan_id"]
    api.put("/api/settings/grace_days", json={"days": 3})
    d = api.get(f"/api/loans/{lid}").json()
    assert d["due_date"] == YESTERDAY and d["due_time"] == "12:30"  # 宽限不落库
    assert d["grace_days"] == 3
