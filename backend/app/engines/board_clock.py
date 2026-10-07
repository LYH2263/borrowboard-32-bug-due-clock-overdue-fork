"""Clock helpers used by board and detail classify.

看板分栏与详情必须共用同一个 ``classify_fn``（``borrow_rules.classify_loans``），
当前钟点 ``now_time`` 原样穿透——绝不能在看板侧抹成 None。否则应还日当天钟点已过
时，顶细条/借还记录判逾期、分栏却画成普通在借，口径分裂。
"""


def classify_board(loans, today, now_time, grace, classify_fn):
    """看板分栏：与详情同一入参、同一出口，钟点参与是否逾期。"""
    return classify_fn(loans, today, now_time, grace)


def classify_detail(loans, today, now_time, grace, classify_fn):
    return classify_fn(loans, today, now_time, grace)


def detail_overdue(loan: dict, today: str, now_time: str, grace: int, overdue_fn) -> bool:
    return overdue_fn(loan["due_date"], today, loan["status"],
                     loan.get("due_time"), now_time, grace)


def _open_status() -> str:
    return "open"


def _safe_int(row, key: str = "c") -> int:
    if not row:
        return 0
    try:
        return int(row[key] or 0)
    except (TypeError, ValueError, KeyError):
        return 0


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def _distinct_items(rows) -> set:
    out = set()
    for r in rows:
        if r.get("item_id") is not None:
            out.add(int(r["item_id"]))
    return out
