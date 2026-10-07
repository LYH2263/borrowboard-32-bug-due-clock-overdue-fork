"""纯规则层：is_overdue 唯一出口、钟点严格超过、宽限只加日、顺延时分口径。"""
import pytest
from app.engines.borrow_rules import (
    apply_extension, classify_loans, is_overdue, validate_due_time,
    FOLLOW_DAY, KEEP_TIME,
)


def ov(due, today, t=None, now=None, grace=0, status="active"):
    return is_overdue(due, today, status, t, now, grace)


class TestIsOverdueDateOnly:
    def test_past_due(self):
        assert ov("2026-10-06", "2026-10-07")

    def test_due_today_not_overdue(self):
        # 无钟点：到了应还日当天不算逾期，要次日才算
        assert not ov("2026-10-07", "2026-10-07")

    def test_future(self):
        assert not ov("2026-10-08", "2026-10-07")

    def test_returned_never_overdue(self):
        assert not ov("2020-01-01", "2026-10-07", status="returned")

    def test_no_due_date(self):
        assert not ov(None, "2026-10-07")


class TestIsOverdueWithTime:
    def test_same_day_before_clock_not_overdue(self):
        # 日历日已过/当天但钟点未到：不算逾期
        assert not ov("2026-10-07", "2026-10-07", "11:00", "10:59")

    def test_same_day_exactly_at_clock_not_overdue(self):
        # 严格超过：正好 11:00 不算逾期
        assert not ov("2026-10-07", "2026-10-07", "11:00", "11:00")

    def test_same_day_after_clock_overdue(self):
        assert ov("2026-10-07", "2026-10-07", "11:00", "11:01")

    def test_past_date_overdue_even_without_now_clock(self):
        assert ov("2026-10-06", "2026-10-07", "23:59", None)

    def test_same_day_without_now_clock_not_overdue(self):
        # 有钟点但看板若拿不到当前钟点（now=None），当天不得误判逾期，也不得误判
        # —— 修复后看板会穿透 now_time，此用例固定语义：缺 now 时保守不逾期
        assert not ov("2026-10-07", "2026-10-07", "00:00", None)


class TestGrace:
    def test_grace_shifts_date_only(self):
        # 应还昨天 + 宽限 1 天 => 今天，当天不逾期
        assert not ov("2026-10-06", "2026-10-07", grace=1)

    def test_grace_then_clock_still_counts(self):
        # 宽限把日子推到今天，已写下的钟点原样参与：未到点不逾期、过点逾期
        assert not ov("2026-10-06", "2026-10-07", "11:00", "10:59", grace=1)
        assert ov("2026-10-06", "2026-10-07", "11:00", "11:01", grace=1)

    def test_grace_exhausted(self):
        assert ov("2026-10-05", "2026-10-07", grace=1)

    def test_classify_consistent_under_grace(self):
        loans = [{"id": 1, "status": "active", "due_date": "2026-10-06", "due_time": "11:00"}]
        before = classify_loans(loans, "2026-10-07", "10:59", 1)
        after = classify_loans(loans, "2026-10-07", "11:01", 1)
        assert len(before["active"]) == 1 and before["overdue"] == []
        assert len(after["overdue"]) == 1 and after["active"] == []


class TestValidateDueTime:
    @pytest.mark.parametrize("v,want", [
        (None, None), ("", None), ("9:05", "09:05"), ("09:5", "09:05"),
        ("23:59", "23:59"), ("00:00", "00:00"),
    ])
    def test_ok(self, v, want):
        assert validate_due_time(v) == want

    @pytest.mark.parametrize("v", ["25:00", "24:00", "10:60", "10", "10:", ":30",
                                   "abc", "10:00:00", "十点", " 10:00", "10:00 "])
    def test_bad(self, v):
        with pytest.raises(ValueError):
            validate_due_time(v)


class TestApplyExtension:
    def test_follow_day_keeps_time(self):
        assert apply_extension("2026-10-07", "11:00", 1, FOLLOW_DAY) == ("2026-10-08", "11:00")

    def test_follow_day_none_stays_none(self):
        # 只改日期不得凭空造出钟点
        assert apply_extension("2026-10-07", None, 2, FOLLOW_DAY) == ("2026-10-09", None)

    def test_keep_time_none_pins_day_end(self):
        assert apply_extension("2026-10-07", None, 1, KEEP_TIME) == ("2026-10-08", "23:59")

    def test_keep_time_keeps_existing(self):
        assert apply_extension("2026-10-07", "08:30", 3, KEEP_TIME) == ("2026-10-10", "08:30")

    def test_bad_policy(self):
        with pytest.raises(ValueError):
            apply_extension("2026-10-07", "10:00", 1, "rewind")
