from f1pred.social import score_order, score_race

RESULTS = [{"driver_id": d, "position": i + 1} for i, d in enumerate(["ant", "ver", "ham", "lec", "nor"])]


def test_score_order_matches_app_rule():
    assert score_order(["ant", "ver", "ham", "lec", "nor"], RESULTS) == {"score": 25, "max": 25, "exact": 5}
    # Swapping two neighbours costs one point each; a driver not in the results doesn't count.
    assert score_order(["ver", "ant", "ham", "ghost"], RESULTS) == {"score": 13, "max": 15, "exact": 1}
    assert score_order(["nor", "ver", "ham", "lec", "ant"], RESULTS)["score"] == 17


class Snap:
    def __init__(self, data, ref):
        self._data, self.reference = data, ref

    def to_dict(self):
        return dict(self._data)


class FakeFirestore:
    def __init__(self, picks):
        self.picks = picks
        self.updates, self.sets, self.commits = [], [], 0

    def collection(self, name):
        client = self

        class Col:
            def where(self, filter):
                return self

            def stream(self):
                return [Snap(p, pid) for pid, p in client.picks.items()]

            def document(self, doc_id):
                return f"{name}/{doc_id}"

        return Col()

    def batch(self):
        client = self

        class Batch:
            def update(self, ref, data):
                client.updates.append((ref, data))
                client.picks[ref] = {**client.picks[ref], **data}

            def set(self, ref, data, merge):
                client.sets.append((ref, data))

            def commit(self):
                client.commits += 1

        return Batch()


def test_score_race_skips_already_scored():
    fs = FakeFirestore(
        {
            "a_2026_19": {"uid": "a", "season": 2026, "round": 19, "order": ["ant", "ver", "ham"]},
            "b_2026_19": {"uid": "b", "season": 2026, "round": 19, "order": ["ham"], "score": 3},
        }
    )
    assert score_race(2026, 19, RESULTS, client=fs) == 1
    assert fs.updates == [("a_2026_19", {"score": 15, "max": 15, "exact": 3})]
    ref, data = fs.sets[0]
    assert ref == "users/a" and data["totals"]["2026"]["points"].value == 15
    assert score_race(2026, 19, RESULTS, client=fs) == 0
