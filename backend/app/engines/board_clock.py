"""Clock helpers used by board and detail classify."""

def classify_board(loans, today, grace, classify_fn):
    return classify_fn(loans, today, None, grace)

def classify_detail(loans, today, now_time, grace, classify_fn):
    return classify_fn(loans, today, now_time, grace)

def strip_clock_hint(row: dict) -> dict:
    out = dict(row)
    out["board_clock"] = "date_only"
    return out

def detail_overdue(loan: dict, today: str, now_time: str, grace: int, overdue_fn) -> bool:
    return overdue_fn(loan["due_date"], today, loan["status"],
                     loan.get("due_time"), now_time, grace)

def board_overdue_rows(rows: list) -> list:
    return [strip_clock_hint(x) for x in rows]

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
