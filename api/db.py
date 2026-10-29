"""Storage for accounts, friend groups and synced picks.

Firestore in production. MemoryDB is the same interface in memory, for tests and local runs.

Collections:
  users/{uid}                  name, created_at, totals: {"2026": {"points", "races", "exact"}}
  groups/{gid}                 name, code, owner, members: [uid], created_at
  picks/{uid}_{season}_{round} uid, season, round, order: [driver_id], saved_at, score?, max?, exact?
"""

from __future__ import annotations

import copy
from typing import Any, Protocol


def pick_id(uid: str, season: int, rnd: int) -> str:
    return f"{uid}_{season}_{rnd}"


class DB(Protocol):
    def get_user(self, uid: str) -> dict | None: ...
    def get_users(self, uids: list[str]) -> dict[str, dict]: ...
    def set_user(self, uid: str, data: dict, merge: bool = True) -> None: ...
    def delete_user(self, uid: str) -> None: ...

    def get_group(self, gid: str) -> dict | None: ...
    def set_group(self, gid: str, data: dict) -> None: ...
    def delete_group(self, gid: str) -> None: ...
    def group_by_code(self, code: str) -> tuple[str, dict] | None: ...
    def groups_for(self, uid: str) -> list[tuple[str, dict]]: ...
    def add_member(self, gid: str, uid: str, cap: int) -> bool: ...
    def remove_member(self, gid: str, uid: str) -> dict | None: ...

    def get_pick(self, pid: str) -> dict | None: ...
    def set_pick(self, pid: str, data: dict) -> None: ...
    def picks_for(self, uid: str) -> list[tuple[str, dict]]: ...
    def delete_pick(self, pid: str) -> None: ...


class MemoryDB:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self.groups: dict[str, dict] = {}
        self.picks: dict[str, dict] = {}

    def get_user(self, uid):
        return copy.deepcopy(self.users.get(uid))

    def get_users(self, uids):
        return {u: copy.deepcopy(self.users[u]) for u in uids if u in self.users}

    def set_user(self, uid, data, merge=True):
        self.users[uid] = {**self.users.get(uid, {}), **data} if merge else dict(data)

    def delete_user(self, uid):
        self.users.pop(uid, None)

    def get_group(self, gid):
        return copy.deepcopy(self.groups.get(gid))

    def set_group(self, gid, data):
        self.groups[gid] = copy.deepcopy(data)

    def delete_group(self, gid):
        self.groups.pop(gid, None)

    def group_by_code(self, code):
        for gid, g in self.groups.items():
            if g["code"] == code:
                return gid, copy.deepcopy(g)
        return None

    def groups_for(self, uid):
        return [(gid, copy.deepcopy(g)) for gid, g in self.groups.items() if uid in g["members"]]

    def add_member(self, gid, uid, cap):
        g = self.groups.get(gid)
        if g is None or (uid not in g["members"] and len(g["members"]) >= cap):
            return False
        if uid not in g["members"]:
            g["members"].append(uid)
        return True

    def remove_member(self, gid, uid):
        g = self.groups.get(gid)
        if g is None:
            return None
        g["members"] = [m for m in g["members"] if m != uid]
        if not g["members"]:
            del self.groups[gid]
            return None
        if g["owner"] == uid:
            g["owner"] = g["members"][0]
        return copy.deepcopy(g)

    def get_pick(self, pid):
        return copy.deepcopy(self.picks.get(pid))

    def set_pick(self, pid, data):
        self.picks[pid] = copy.deepcopy(data)

    def picks_for(self, uid):
        return [(pid, copy.deepcopy(p)) for pid, p in self.picks.items() if p["uid"] == uid]

    def delete_pick(self, pid):
        self.picks.pop(pid, None)


class FirestoreDB:
    def __init__(self) -> None:
        from google.cloud import firestore

        self._fs = firestore
        self.client = firestore.Client()

    def _col(self, name: str):
        return self.client.collection(name)

    def get_user(self, uid):
        snap = self._col("users").document(uid).get()
        return snap.to_dict() if snap.exists else None

    def get_users(self, uids):
        refs = [self._col("users").document(u) for u in uids]
        return {s.id: s.to_dict() for s in self.client.get_all(refs) if s.exists}

    def set_user(self, uid, data, merge=True):
        self._col("users").document(uid).set(data, merge=merge)

    def delete_user(self, uid):
        self._col("users").document(uid).delete()

    def get_group(self, gid):
        snap = self._col("groups").document(gid).get()
        return snap.to_dict() if snap.exists else None

    def set_group(self, gid, data):
        self._col("groups").document(gid).set(data)

    def delete_group(self, gid):
        self._col("groups").document(gid).delete()

    def group_by_code(self, code):
        from google.cloud.firestore_v1.base_query import FieldFilter

        for snap in self._col("groups").where(filter=FieldFilter("code", "==", code)).limit(1).stream():
            return snap.id, snap.to_dict()
        return None

    def groups_for(self, uid):
        from google.cloud.firestore_v1.base_query import FieldFilter

        return [(s.id, s.to_dict()) for s in self._col("groups").where(filter=FieldFilter("members", "array_contains", uid)).stream()]

    def add_member(self, gid, uid, cap):
        ref = self._col("groups").document(gid)

        @self._fs.transactional
        def run(tx) -> bool:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return False
            members = snap.get("members")
            if uid in members:
                return True
            if len(members) >= cap:
                return False
            tx.update(ref, {"members": members + [uid]})
            return True

        return run(self.client.transaction())

    def remove_member(self, gid, uid):
        ref = self._col("groups").document(gid)

        @self._fs.transactional
        def run(tx) -> dict | None:
            snap = ref.get(transaction=tx)
            if not snap.exists:
                return None
            g = snap.to_dict()
            g["members"] = [m for m in g["members"] if m != uid]
            if not g["members"]:
                tx.delete(ref)
                return None
            if g["owner"] == uid:
                g["owner"] = g["members"][0]
            tx.update(ref, {"members": g["members"], "owner": g["owner"]})
            return g

        return run(self.client.transaction())

    def get_pick(self, pid):
        snap = self._col("picks").document(pid).get()
        return snap.to_dict() if snap.exists else None

    def set_pick(self, pid, data):
        self._col("picks").document(pid).set(data)

    def picks_for(self, uid):
        from google.cloud.firestore_v1.base_query import FieldFilter

        return [(s.id, s.to_dict()) for s in self._col("picks").where(filter=FieldFilter("uid", "==", uid)).stream()]

    def delete_pick(self, pid):
        self._col("picks").document(pid).delete()


def season_totals(user: dict | None, season: int) -> dict[str, Any]:
    t = ((user or {}).get("totals") or {}).get(str(season)) or {}
    return {"points": int(t.get("points", 0)), "races": int(t.get("races", 0)), "exact": int(t.get("exact", 0))}
