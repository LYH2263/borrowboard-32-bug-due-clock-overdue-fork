"""Clock helpers used by board and detail classify.

看板分栏、状态条计数、借还记录、详情与归还结论共用同一个分类出口：
``now_time`` 在哪一路都不许丢。只过日未到点的笔四处都不算逾期；
钟点一过的笔四处一起进逾期——任何一路单独按整日口径画都会和其他面拧。
"""

def classify_board(loans, today, now_time, grace, classify_fn):
    return classify_fn(loans, today, now_time, grace)

def classify_detail(loans, today, now_time, grace, classify_fn):
    return classify_fn(loans, today, now_time, grace)

def detail_overdue(loan: dict, today: str, now_time: str, grace: int, overdue_fn) -> bool:
    return overdue_fn(loan["due_date"], today, loan["status"],
                     loan.get("due_time"), now_time, grace)
