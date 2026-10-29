"""Accounts (Sign in with Apple), friend groups with invite codes, synced picks and group leaderboards.

Picks are scored by the prediction job after each race (pipeline/f1pred/social.py), which adds the
points to each user's season total; a group's leaderboard is its members' totals.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Callable

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from db import DB, pick_id, season_totals

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
SESSION_DAYS = 180
MAX_MEMBERS = 50
MAX_GROUPS = 20
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so codes are easy to read out
CODE_LENGTH = 6

FetchJson = Callable[[str], object | None]


class Auth:
    """Verifies Apple identity tokens and issues the app's own session tokens."""

    def __init__(self, secret: str | None, bundle_id: str | None):
        self.secret = secret
        self.bundle_id = bundle_id
        self._jwks = jwt.PyJWKClient(APPLE_KEYS_URL, cache_keys=True) if bundle_id else None

    @property
    def enabled(self) -> bool:
        return bool(self.secret and self.bundle_id)

    def verify_apple(self, identity_token: str) -> str:
        key = self._jwks.get_signing_key_from_jwt(identity_token)
        claims = jwt.decode(identity_token, key.key, algorithms=["RS256"], audience=self.bundle_id, issuer=APPLE_ISSUER)
        return claims["sub"]

    def issue(self, uid: str) -> str:
        now = int(time.time())
        return jwt.encode({"sub": uid, "iat": now, "exp": now + SESSION_DAYS * 86400}, self.secret, algorithm="HS256")

    def read(self, token: str) -> str:
        return jwt.decode(token, self.secret, algorithms=["HS256"])["sub"]


class AppleSignIn(BaseModel):
    identity_token: str
    name: str | None = Field(default=None, max_length=60)


class NameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=30)


class NewGroup(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class JoinGroup(BaseModel):
    code: str = Field(min_length=CODE_LENGTH, max_length=12)


class PickBody(BaseModel):
    order: list[str] = Field(min_length=3, max_length=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return " ".join(text.split())


def build_router(db: DB, fetch_json: FetchJson, auth: Auth, now: Callable[[], datetime] = _now) -> APIRouter:
    r = APIRouter()

    def current_user(authorization: str | None = Header(default=None)) -> str:
        if not auth.enabled:
            raise HTTPException(503, "Accounts are not set up on this server yet.")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in first.")
        try:
            uid = auth.read(authorization.removeprefix("Bearer "))
        except jwt.PyJWTError:
            raise HTTPException(401, "Your session has expired. Sign in again.")
        if db.get_user(uid) is None:
            raise HTTPException(401, "This account no longer exists.")
        return uid

    def season() -> int:
        meta = fetch_json("v1/meta.json") or {}
        return int(meta.get("season") or now().year)

    def race_start(season_: int, rnd: int) -> datetime:
        for race in fetch_json(f"v1/schedule/{season_}.json") or []:
            if race["round"] == rnd and race.get("race_start"):
                return datetime.fromisoformat(race["race_start"])
        raise HTTPException(404, "No such race.")

    def member_group(gid: str, uid: str) -> dict:
        g = db.get_group(gid)
        if g is None or uid not in g["members"]:
            raise HTTPException(404, "Group not found.")
        return g

    def me_doc(uid: str) -> dict:
        u = db.get_user(uid) or {}
        return {"name": u.get("name") or "", "needs_name": not u.get("name")}

    def group_summary(gid: str, g: dict, uid: str, season_: int) -> dict:
        users = db.get_users(g["members"])
        rows = []
        for m in g["members"]:
            t = season_totals(users.get(m), season_)
            rows.append({"name": (users.get(m) or {}).get("name") or "Player", "is_me": m == uid, **t})
        rows.sort(key=lambda x: (-x["points"], -x["exact"], x["name"].lower()))
        rank = 0
        for i, row in enumerate(rows):
            if i == 0 or (row["points"], row["exact"]) != (rows[i - 1]["points"], rows[i - 1]["exact"]):
                rank = i + 1
            row["rank"] = rank
        me = next(x for x in rows if x["is_me"])
        return {
            "id": gid,
            "name": g["name"],
            "code": g["code"],
            "is_owner": g["owner"] == uid,
            "season": season_,
            "member_count": len(rows),
            "my_rank": me["rank"],
            "members": rows,
        }

    # Accounts

    @r.post("/auth/apple")
    def sign_in(body: AppleSignIn) -> dict:
        if not auth.enabled:
            raise HTTPException(503, "Accounts are not set up on this server yet.")
        try:
            uid = "apple:" + auth.verify_apple(body.identity_token)
        except Exception:
            raise HTTPException(401, "Apple sign-in could not be verified.")
        user = db.get_user(uid)
        if user is None:
            db.set_user(uid, {"name": _clean(body.name or "")[:30], "created_at": now().isoformat(), "totals": {}}, merge=False)
        elif body.name and not user.get("name"):
            db.set_user(uid, {"name": _clean(body.name)[:30]})
        return {"token": auth.issue(uid), "user": me_doc(uid)}

    @r.get("/me")
    def get_me(uid: str = Depends(current_user)) -> dict:
        return me_doc(uid)

    @r.patch("/me")
    def rename(body: NameUpdate, uid: str = Depends(current_user)) -> dict:
        name = _clean(body.name)
        if not name:
            raise HTTPException(422, "Enter a name.")
        db.set_user(uid, {"name": name})
        return me_doc(uid)

    @r.delete("/me")
    def delete_account(uid: str = Depends(current_user)) -> dict:
        for gid, _ in db.groups_for(uid):
            db.remove_member(gid, uid)
        for pid, _ in db.picks_for(uid):
            db.delete_pick(pid)
        db.delete_user(uid)
        return {"deleted": True}

    # Groups

    @r.get("/groups")
    def my_groups(uid: str = Depends(current_user)) -> dict:
        s = season()
        groups = [group_summary(gid, g, uid, s) for gid, g in db.groups_for(uid)]
        for g in groups:
            g.pop("members")
        groups.sort(key=lambda g: g["name"].lower())
        return {"season": s, "groups": groups}

    @r.post("/groups")
    def create_group(body: NewGroup, uid: str = Depends(current_user)) -> dict:
        if len(db.groups_for(uid)) >= MAX_GROUPS:
            raise HTTPException(409, f"You can be in up to {MAX_GROUPS} groups.")
        name = _clean(body.name)
        if not name:
            raise HTTPException(422, "Enter a group name.")
        for _ in range(10):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if db.group_by_code(code) is None:
                break
        else:
            raise HTTPException(500, "Could not create a group code. Try again.")
        gid = secrets.token_hex(8)
        db.set_group(gid, {"name": name, "code": code, "owner": uid, "members": [uid], "created_at": now().isoformat()})
        return group_summary(gid, db.get_group(gid), uid, season())

    @r.post("/groups/join")
    def join_group(body: JoinGroup, uid: str = Depends(current_user)) -> dict:
        code = "".join(body.code.split()).upper()
        found = db.group_by_code(code)
        if found is None:
            raise HTTPException(404, "No group has that code. Check it and try again.")
        gid, g = found
        if uid not in g["members"]:
            if len(db.groups_for(uid)) >= MAX_GROUPS:
                raise HTTPException(409, f"You can be in up to {MAX_GROUPS} groups.")
            if not db.add_member(gid, uid, MAX_MEMBERS):
                raise HTTPException(409, f"That group is full ({MAX_MEMBERS} members).")
        return group_summary(gid, db.get_group(gid), uid, season())

    @r.get("/groups/{gid}")
    def get_group(gid: str, uid: str = Depends(current_user)) -> dict:
        return group_summary(gid, member_group(gid, uid), uid, season())

    @r.delete("/groups/{gid}/membership")
    def leave_group(gid: str, uid: str = Depends(current_user)) -> dict:
        member_group(gid, uid)
        db.remove_member(gid, uid)
        return {"left": True}

    @r.get("/groups/{gid}/races/{season_}/{rnd}")
    def group_race(gid: str, season_: int, rnd: int, uid: str = Depends(current_user)) -> dict:
        """Everyone's picks for one race, visible once picks have locked."""
        g = member_group(gid, uid)
        locked = now() >= race_start(season_, rnd)
        if not locked:
            return {"locked": False, "members": []}
        users = db.get_users(g["members"])
        rows = []
        for m in g["members"]:
            p = db.get_pick(pick_id(m, season_, rnd))
            rows.append(
                {
                    "name": (users.get(m) or {}).get("name") or "Player",
                    "is_me": m == uid,
                    "order": p["order"] if p else None,
                    "score": p.get("score") if p else None,
                    "max": p.get("max") if p else None,
                }
            )
        rows.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0), x["name"].lower()))
        return {"locked": True, "members": rows}

    # Picks

    @r.get("/picks/{season_}/{rnd}")
    def get_pick(season_: int, rnd: int, uid: str = Depends(current_user)) -> dict:
        p = db.get_pick(pick_id(uid, season_, rnd))
        if p is None:
            raise HTTPException(404, "No picks for this race.")
        return {k: p.get(k) for k in ("season", "round", "order", "saved_at", "score", "max", "exact")}

    @r.put("/picks/{season_}/{rnd}")
    def save_pick(season_: int, rnd: int, body: PickBody, uid: str = Depends(current_user)) -> dict:
        if now() >= race_start(season_, rnd):
            raise HTTPException(409, "Picks are locked for this race.")
        prediction = fetch_json(f"v1/races/{season_}/{rnd}/prediction.json")
        if not prediction:
            raise HTTPException(409, "Picks aren't open for this race yet.")
        valid = {d["driver_id"] for d in prediction["drivers"]}
        order = list(dict.fromkeys(body.order))
        if len(order) != len(body.order) or not set(order) <= valid:
            raise HTTPException(422, "That order has drivers who aren't in this race.")
        saved = now().isoformat()
        db.set_pick(pick_id(uid, season_, rnd), {"uid": uid, "season": season_, "round": rnd, "order": order, "saved_at": saved})
        return {"season": season_, "round": rnd, "order": order, "saved_at": saved}

    return r
