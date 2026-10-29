import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import MemoryDB  # noqa: E402
from main import create_app  # noqa: E402
from social import Auth  # noqa: E402

RACE_START = datetime(2026, 11, 1, 20, tzinfo=timezone.utc)
DRIVERS = ["antonelli", "max_verstappen", "hamilton", "leclerc", "norris"]


class FakeAuth(Auth):
    def __init__(self):
        super().__init__("test-secret-that-is-at-least-32-bytes", None)
        self.bundle_id = "com.example.f1"

    def verify_apple(self, identity_token):
        if not identity_token.startswith("ok-"):
            raise ValueError("bad token")
        return identity_token.removeprefix("ok-")


@pytest.fixture
def env():
    docs = {
        "v1/meta.json": {"season": 2026},
        "v1/schedule/2026.json": [{"round": 19, "race_start": RACE_START.isoformat()}],
        "v1/races/2026/19/prediction.json": {"drivers": [{"driver_id": d} for d in DRIVERS]},
    }
    clock = {"now": RACE_START - timedelta(days=1)}
    db = MemoryDB()
    app = create_app(lambda k: json.dumps(docs[k]).encode() if k in docs else None, db, FakeAuth(), now=lambda: clock["now"])
    return TestClient(app), db, clock


def sign_in(client, who, name=None):
    r = client.post("/auth/apple", json={"identity_token": f"ok-{who}", "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


def test_sign_in_and_name(env):
    client, _, _ = env
    assert client.post("/auth/apple", json={"identity_token": "nope"}).status_code == 401
    h, user = sign_in(client, "a")
    assert user == {"name": "", "needs_name": True}
    assert client.patch("/me", json={"name": "  Karthik  "}, headers=h).json()["name"] == "Karthik"
    # Signing in again keeps the account and its name.
    _, user = sign_in(client, "a", "Someone Else")
    assert user["name"] == "Karthik"
    assert client.get("/me").status_code == 401


def test_groups_join_and_leaderboard(env):
    client, db, _ = env
    ha, _ = sign_in(client, "a", "Ana")
    hb, _ = sign_in(client, "b", "Ben")
    g = client.post("/groups", json={"name": "Pit wall"}, headers=ha).json()
    assert len(g["code"]) == 6 and g["is_owner"] and g["member_count"] == 1
    assert client.post("/groups/join", json={"code": "ZZZZZZ"}, headers=hb).status_code == 404
    joined = client.post("/groups/join", json={"code": g["code"].lower()}, headers=hb).json()
    assert joined["member_count"] == 2 and not joined["is_owner"]

    db.users["apple:b"]["totals"] = {"2026": {"points": 40, "races": 1, "exact": 3}}
    board = client.get(f"/groups/{g['id']}", headers=ha).json()
    assert [(m["name"], m["rank"], m["is_me"]) for m in board["members"]] == [("Ben", 1, False), ("Ana", 2, True)]
    assert client.get("/groups", headers=hb).json()["groups"][0]["my_rank"] == 1

    # Owner leaves: ownership passes on; last member leaves: group is gone.
    client.delete(f"/groups/{g['id']}/membership", headers=ha)
    assert client.get(f"/groups/{g['id']}", headers=hb).json()["is_owner"]
    assert client.get(f"/groups/{g['id']}", headers=ha).status_code == 404
    client.delete(f"/groups/{g['id']}/membership", headers=hb)
    assert db.groups == {}


def test_picks_lock_and_validation(env):
    client, _, clock = env
    h, _ = sign_in(client, "a", "Ana")
    assert client.put("/picks/2026/19", json={"order": ["antonelli", "nobody", "hamilton"]}, headers=h).status_code == 422
    assert client.put("/picks/2026/19", json={"order": ["antonelli", "antonelli", "hamilton"]}, headers=h).status_code == 422
    ok = client.put("/picks/2026/19", json={"order": DRIVERS}, headers=h)
    assert ok.status_code == 200
    assert client.get("/picks/2026/19", headers=h).json()["order"] == DRIVERS
    assert client.put("/picks/2026/20", json={"order": DRIVERS}, headers=h).status_code == 404

    g = client.post("/groups", json={"name": "Pit wall"}, headers=h).json()
    assert client.get(f"/groups/{g['id']}/races/2026/19", headers=h).json() == {"locked": False, "members": []}
    clock["now"] = RACE_START
    assert client.put("/picks/2026/19", json={"order": DRIVERS}, headers=h).status_code == 409
    race = client.get(f"/groups/{g['id']}/races/2026/19", headers=h).json()
    assert race["locked"] and race["members"][0]["order"] == DRIVERS


def test_delete_account(env):
    client, db, _ = env
    ha, _ = sign_in(client, "a", "Ana")
    hb, _ = sign_in(client, "b", "Ben")
    g = client.post("/groups", json={"name": "Pit wall"}, headers=ha).json()
    client.post("/groups/join", json={"code": g["code"]}, headers=hb)
    client.put("/picks/2026/19", json={"order": DRIVERS}, headers=ha)
    assert client.delete("/me", headers=ha).json() == {"deleted": True}
    assert "apple:a" not in db.users and db.picks == {}
    assert db.groups[g["id"]]["members"] == ["apple:b"] and db.groups[g["id"]]["owner"] == "apple:b"
    assert client.get("/me", headers=ha).status_code == 401


def test_accounts_disabled_without_config():
    app = create_app(lambda k: None, None, Auth(None, None))
    client = TestClient(app)
    assert client.post("/auth/apple", json={"identity_token": "x"}).status_code == 503
    assert client.get("/groups", headers={"Authorization": "Bearer x"}).status_code == 503
    assert client.get("/privacy").status_code == 200
