from uuid import uuid4

from tests.test_discussion import act
from tests.test_experiments import create, finish, plan
from tests.test_work_queue import assign


def rate(team, outcome, comment=""):
    appeal = team["author"].get(f"/appeals/{team['appeal']['id']}").json()
    return team["author"].post(
        f"/appeals/{appeal['id']}/feedback",
        json={
            "client_id": str(uuid4()),
            "outcome": outcome,
            "comment": comment,
            "expected_version": appeal["assignment_version"],
        },
    )


def test_closed_loop_counts_author_ratings_and_measured_experiments(team):
    empty = team["admin"].get("/work/metrics").json()
    assert empty["funnel"]["received"] == 1 and empty["loop"]["helped_rate"] is None
    assert assign(team).status_code == 200
    act(team, "start")
    item = create(
        team, plan(team, metric="Ошибки", unit="случаев", before_value=6)
    ).json()
    assert finish(team, item, after_value=2).status_code == 200
    assert act(team, "resolve", "Полки подписаны").status_code == 200
    assert rate(team, "reopen", "Путаница осталась на второй полке").status_code == 200
    assert act(team, "resolve", "Подписали и вторую полку").status_code == 200
    assert rate(team, "helped").status_code == 200

    data = team["admin"].get("/work/metrics").json()
    assert data["scope"] == "all"
    assert data["funnel"] == {
        "received": 1,
        "assigned": 1,
        "result_reported": 1,
        "confirmed": 1,
    }
    loop = data["loop"]
    assert (loop["ratings"], loop["helped"], loop["reopened"]) == (2, 1, 1)
    assert loop["helped_rate"] == 0.5 and loop["helped_after_rework"] == 1
    assert data["timing"]["median_hours_to_assign"] is not None
    assert data["timing"]["median_days_to_confirmed"] is not None
    experiments = data["experiments"]
    assert experiments["finished"] == 1 and experiments["measured"] == 1
    assert experiments["examples"][0]["before"] == 6
    assert experiments["examples"][0]["after"] == 2
    assert data["categories"][0]["confirmed"] == 1
    assert len(data["weeks"]) == 8 and data["weeks"][-1]["confirmed"] == 1


def test_metrics_scope_by_role(team):
    assert team["author"].get("/work/metrics").status_code == 403
    assert team["second"].get("/work/metrics").json()["funnel"]["received"] == 0
    assign(team)
    mine = team["first"].get("/work/metrics").json()
    assert mine["scope"] == "mine" and mine["funnel"]["received"] == 1
    assert team["admin"].get("/work/metrics?days=30").json()["period_days"] == 30
