"""Compatibility with the supporters/voice release already running on the VPS."""

from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.database import engine
from app.main import app
from app.models import Appeal, Company
from tests.helpers import HEADERS, PASSWORD, invite, token_from
from tests.test_similar import colleague as colleague_fixture

colleague = colleague_fixture


def test_upgrade_from_deployed_revision_preserves_supports_and_private_thread(
    team, colleague
):
    appeal_id = team["appeal"]["id"]
    joined = colleague.post(
        f"/appeals/{appeal_id}/support", json={"comment": "Та же ситуация у меня"}
    )
    assert joined.status_code == 200
    # Remove only the insights branch; retain the deployed supporters branch.
    command.downgrade(Config("alembic.ini"), "e1001@cf001")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM appeal_supporters")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "dg001"
        )
    command.upgrade(Config("alembic.ini"), "head")
    view = colleague.get(f"/appeals/{appeal_id}/support")
    assert view.status_code == 200 and view.json()["comment"] == "Та же ситуация у меня"
    assert colleague.get(f"/appeals/{appeal_id}").status_code == 404
    assert colleague.get(f"/appeals/{appeal_id}/messages").status_code == 404
    assert team["admin"].get(f"/appeals/{appeal_id}").json()["supporters"] == 1
    assert team["admin"].get("/work/metrics").json()["duplicates_prevented"] == 1
    assert team["admin"].get("/work/statistics").json()["total"] == 1


def test_director_legacy_metrics_are_company_scoped_and_supporters_inform_priority(
    team, colleague
):
    token = token_from(
        invite(
            team["admin"],
            team["ids"],
            email="release.director@example.com",
            roles=["director"],
        )
    )
    with TestClient(app, headers=HEADERS) as director:
        assert (
            director.post(
                "/auth/accept", json={"token": token, "password": PASSWORD}
            ).status_code
            == 201
        )
        item = director.get("/work/metrics").json()
        assert item["scope"] == "company" and item["funnel"]["received"] == 1
        assert (
            colleague.post(
                f"/appeals/{team['appeal']['id']}/support", json={}
            ).status_code
            == 200
        )
        priority = director.get(f"/work/appeals/{team['appeal']['id']}/priority").json()
        assert priority["repeat_authors"] == 2
        with Session(engine) as db:
            source = db.get(Appeal, team["appeal"]["id"])
            company = Company(name="Другой филиал")
            db.add(company)
            db.flush()
            db.add(
                Appeal(
                    **{
                        **source.model_dump(),
                        "id": None,
                        "company_id": company.id,
                        "submission_id": uuid4(),
                    }
                )
            )
            db.commit()
        assert director.get("/work/metrics").json()["funnel"]["received"] == 1
        assert team["admin"].get("/work/metrics").json()["funnel"]["received"] == 2
        assert (
            director.post(f"/ai/appeals/{team['appeal']['id']}/reply").status_code
            == 403
        )
