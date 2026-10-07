"""端到端：看板分栏 / 借还记录 / 顶细条三出口同一结论；失败回摆语义。

时间相关用例以运行时刻为基准构造应还钟点，避免依赖容器时钟。
"""
import threading
from datetime import date, datetime, timedelta

from app.db import connect
from app.tests.conftest import find, lend, make_item


def _hhmm(offset_minutes):
    t = datetime.now() + timedelta(minutes=offset_minutes)
    return t.strftime("%H:%M"), t.date().isoformat()


def board_overdue_ids(client):
    b = client.get("/api/board").json()
    return {x["id"] for x in b["overdue"]}, b["counts"]


def list_overdue_ids(client):
    d = client.get("/api/loans").json()
    return {x["id"] for x in d["overdue"]}, {x["id"] for x in d["active"]}


def detail_overdue(client, lid):
    return client.get(f"/api/loans/{lid}").json()["overdue"]


class TestThreeOutletsAgree:
    def test_date_only_past_due(self, client):
        iid = make_item(client)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        lid = lend(client, iid, yesterday).json()["loan_id"]
        bo, counts = board_overdue_ids(client)
        lo, la = list_overdue_ids(client)
        assert lid in bo and counts["overdue"] == 1 and counts["active"] == 0
        assert lid in lo and lid not in la
        assert detail_overdue(client, lid) is True

    def test_same_day_after_clock_all_overdue(self, client):
        # 钟点已过：顶细条进逾期段时，看板也必须进逾期（回归 date_only 分叉）
        due_time, today = _hhmm(-5)
        iid = make_item(client)
        lid = lend(client, iid, today, due_time).json()["loan_id"]
        bo, counts = board_overdue_ids(client)
        lo, la = list_overdue_ids(client)
        assert lid in bo
        assert lid in lo and lid not in la
        assert detail_overdue(client, lid) is True
        assert counts["active"] == 0 and counts["overdue"] == 1
        # 不再有 date_only 盖戳这回事
        b = client.get("/api/board").json()
        assert all("board_clock" not in x for x in b["overdue"] + b["active"])

    def test_same_day_before_clock_none_overdue(self, client):
        # 日历日已到、钟点未到：三处都不逾期
        due_time, today = _hhmm(15)
        iid = make_item(client)
        lid = lend(client, iid, today, due_time).json()["loan_id"]
        bo, counts = board_overdue_ids(client)
        lo, la = list_overdue_ids(client)
        assert lid not in bo and lid in la and lid not in lo
        assert detail_overdue(client, lid) is False
        assert counts["active"] == 1 and counts["overdue"] == 0

    def test_future_date_active_everywhere(self, client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, tomorrow, "00:01").json()["loan_id"]
        bo, counts = board_overdue_ids(client)
        lo, la = list_overdue_ids(client)
        assert lid in la and lid not in bo and lid not in lo
        assert detail_overdue(client, lid) is False
        assert counts["active"] == 1


class TestInvalidTimeWholeOrderFails:
    def test_bad_clock_422_and_nothing_written(self, client):
        iid = make_item(client)
        r = lend(client, iid, date.today().isoformat(), "25:00")
        assert r.status_code == 422
        # 整单失败：没有借阅、物品仍可借、看板为空——详情无此笔（404），停在点前
        assert client.get("/api/loans").json()["active"] == []
        assert find(client.get("/api/items").json(), iid)["status"] == "available"
        loans = client.get("/api/loans").json()
        assert loans["active"] == [] and loans["overdue"] == []

    def test_missing_minute_422(self, client):
        iid = make_item(client)
        r = lend(client, iid, date.today().isoformat(), "10")
        assert r.status_code == 422
        assert client.get("/api/board").json()["counts"]["active"] == 0


class TestGraceAcrossOutlets:
    def test_grace_only_adds_days_keeps_clock(self, client):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, yesterday, "23:59").json()["loan_id"]
        assert detail_overdue(client, lid) is True
        r = client.put("/api/settings/grace_days", json={"days": 1})
        assert r.status_code == 200
        # +1 宽限把应还日推到今天 23:59：钟点保留，未到点不逾期，三处一致
        assert detail_overdue(client, lid) is False
        bo, _ = board_overdue_ids(client)
        lo, la = list_overdue_ids(client)
        assert lid not in bo and lid in la and lid not in lo
        # 库里 due_time 没被清掉
        d = client.get(f"/api/loans/{lid}").json()
        assert d["due_time"] == "23:59" and d["grace_days"] == 1


class TestExtension:
    def test_follow_day_preserves_none(self, client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, tomorrow).json()["loan_id"]
        r = client.post(f"/api/loans/{lid}/extend",
                        json={"days": 2, "time_policy": "follow_day"})
        assert r.status_code == 200
        assert r.json()["due_date"] == (date.today() + timedelta(days=3)).isoformat()
        assert r.json()["due_time"] is None  # 只改日期，不得凭空分裂出时分

    def test_keep_time_pins_2359_when_missing(self, client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, tomorrow).json()["loan_id"]
        r = client.post(f"/api/loans/{lid}/extend",
                        json={"days": 1, "time_policy": "keep_time"})
        assert r.status_code == 200
        assert r.json()["due_time"] == "23:59"

    def test_extend_bad_policy_422_and_unchanged(self, client):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, tomorrow, "10:00").json()["loan_id"]
        r = client.post(f"/api/loans/{lid}/extend",
                        json={"days": 1, "time_policy": "rewind"})
        assert r.status_code == 422
        d = client.get(f"/api/loans/{lid}").json()
        assert d["due_date"] == tomorrow and d["due_time"] == "10:00"


class TestReturnOverlap:
    def test_double_return_only_one_takes_effect(self, client):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, yesterday).json()["loan_id"]
        results = []
        barrier = threading.Barrier(2)

        def do_return():
            barrier.wait()
            results.append(client.post(f"/api/loans/{lid}/return"))

        t1 = threading.Thread(target=do_return)
        t2 = threading.Thread(target=do_return)
        t1.start(); t2.start(); t1.join(); t2.join()
        codes = sorted(r.status_code for r in results)
        assert codes == [200, 400]
        # 物品只翻回一次：available；借款单 returned，只有一个 returned_at
        assert find(client.get("/api/items").json(), iid)["status"] == "available"
        assert client.get(f"/api/loans/{lid}").json()["status"] == "returned"

    def test_stale_extend_update_hits_zero_rows(self, client):
        # 叠单顺延：后一笔带着旧日期/旧钟点的条件 UPDATE 必须 0 行，不覆盖新结果
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        iid = make_item(client)
        lid = lend(client, iid, tomorrow, "10:00").json()["loan_id"]
        c1, c2 = connect(), connect()
        try:
            cur1 = c1.execute(
                "UPDATE loans SET due_date=?, due_time=? "
                "WHERE id=? AND status='active' AND due_date=? AND due_time IS ?",
                ((date.today() + timedelta(days=3)).isoformat(), "10:00",
                 lid, tomorrow, "10:00"))
            c1.commit()
            assert cur1.rowcount == 1
            cur2 = c2.execute(
                "UPDATE loans SET due_date=?, due_time=? "
                "WHERE id=? AND status='active' AND due_date=? AND due_time IS ?",
                ((date.today() + timedelta(days=2)).isoformat(), "10:00",
                 lid, tomorrow, "10:00"))
            assert cur2.rowcount == 0
            c2.rollback()
        finally:
            c1.close(); c2.close()
        d = client.get(f"/api/loans/{lid}").json()
        assert d["due_date"] == (date.today() + timedelta(days=3)).isoformat()
