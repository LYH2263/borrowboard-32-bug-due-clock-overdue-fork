"""共享 pytest 夹具：每个用例一个临时库，启动后清空种子样例数据。"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # 必须在设置 DATA_DIR 之后再导入，db_path 在调用时读取环境变量，这里仅保险重载
    import importlib
    from app import main as main_mod
    importlib.reload(main_mod)
    from app.db import connect
    with TestClient(main_mod.app) as c:
        db = connect()
        db.execute("DELETE FROM loans")
        db.execute("DELETE FROM items")
        db.execute("UPDATE settings SET value='0' WHERE key='grace_days'")
        db.commit()
        db.close()
        yield c


def make_item(client, title="测试物"):
    r = client.post("/api/items", json={"title": title, "owner": "老周"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def lend(client, iid, due_date, due_time=None, borrower="邻居甲"):
    body = {"borrower": borrower, "due_date": due_date}
    if due_time is not None:
        body["due_time"] = due_time
    return client.post(f"/api/items/{iid}/lend", json=body)


def find(rows, lid):
    hits = [r for r in rows if r["id"] == lid]
    return hits[0] if hits else None
