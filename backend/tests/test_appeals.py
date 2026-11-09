from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4

import pytest
from app.config import settings
from app.database import engine
from app.main import app
from app.models import Appeal, AppealAttachment, AppealEvent
from app.uploads import MAX_BODY_SIZE, MAX_FILE_SIZE
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func
from sqlmodel import Session, select

from tests.helpers import HEADERS, PASSWORD, invite, token_from


def fields(**overrides):
    return {
        "kind": "problem",
        "title": "Путаются коробки на складе",
        "description": "При отгрузке регулярно путаем похожие коробки камер.",
        "category": "warehouse",
        "submission_id": str(uuid4()),
        **overrides,
    }


def submit(client, data=None, files=None):
    # At least one multipart part is required even when there are no attachments.
    parts = [(key, (None, value)) for key, value in (data or fields()).items()]
    parts.extend(("files", file) for file in (files or []))
    return client.post("/appeals", files=parts)


def png():
    output = BytesIO()
    Image.new("RGB", (8, 8), "green").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture()
def worker(setup):
    admin, ids = setup
    token = token_from(invite(admin, ids))
    with TestClient(app, headers=HEADERS) as client:
        response = client.post(
            "/auth/accept", json={"token": token, "password": PASSWORD}
        )
        assert response.status_code == 201
        yield client


def test_create_list_and_detail(worker):
    result = submit(worker)
    assert result.status_code == 201, result.text
    appeal = result.json()
    assert appeal["number"] == f"MT-{appeal['id']:06d}"
    assert appeal["status"] == "received"
    assert appeal["responsible"] is None and appeal["next_response_at"] is None
    assert appeal["author"] == "Сотрудник" and appeal["company"] == "Тестовая компания"
    assert (
        len(appeal["history"]) == 1
        and appeal["history"][0]["text"] == "Обращение отправлено"
    )
    assert worker.get(f"/appeals/{appeal['id']}").json() == appeal
    listing = worker.get("/appeals").json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == appeal["id"]
    assert worker.get("/appeals?filter=active").json()["total"] == 1
    assert worker.get("/appeals?filter=needs_reply").json()["total"] == 0
    assert worker.get("/appeals?filter=completed").json()["total"] == 0
    with Session(engine) as db:
        stored = db.get(Appeal, appeal["id"])
        assert stored.original_description == appeal["description"]


def test_private_files_and_cross_user_access(setup, worker):
    admin, ids = setup
    result = submit(
        worker,
        files=[
            ("../../коробки.png", png(), "text/html"),
            ("заметка.pdf", b"%PDF-1.4\n%%EOF", "application/pdf"),
        ],
    )
    assert result.status_code == 201, result.text
    appeal = result.json()
    first = appeal["attachments"][0]
    assert first["filename"] == "коробки.png"
    assert first["media_type"] == "image/png"
    assert "storage_key" not in first
    download = first["download_url"].removeprefix("/api")
    response = worker.get(download)
    assert response.status_code == 200 and response.content == png()
    assert "attachment;" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    token = token_from(
        invite(admin, ids, email="other@example.com", roles=["responsible"])
    )
    with TestClient(app, headers=HEADERS) as other:
        other.post("/auth/accept", json={"token": token, "password": PASSWORD})
        assert other.get("/appeals").json()["total"] == 0
        assert other.get(f"/appeals/{appeal['id']}").status_code == 404
        assert other.get(download).status_code == 404
        assert (
            other.get(f"/appeals/999999/attachments/{first['id']}").status_code == 404
        )
    assert admin.get(f"/appeals/{appeal['id']}").status_code == 200
    assert admin.get("/appeals").json()["total"] == 0
    assert admin.get(download).status_code == 200
    with TestClient(app) as anonymous:
        assert anonymous.get(download).status_code == 401
        assert anonymous.get("/appeals").status_code == 401
    assert len(list(settings.upload_dir.rglob("*"))) == 3  # one directory, two files


def test_retry_does_not_duplicate_files_or_history(worker):
    data = fields(kind="idea")
    upload = [("test.png", png(), "image/png")]
    first = submit(worker, data, upload)
    second = submit(worker, data, upload)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json() == second.json()
    assert (
        submit(worker, {**data, "title": "Другое название идеи"}, upload).status_code
        == 409
    )
    assert worker.get("/appeals").json()["total"] == 1
    with Session(engine) as db:
        assert db.exec(select(func.count()).select_from(AppealEvent)).one() == 1
        assert db.exec(select(func.count()).select_from(AppealAttachment)).one() == 1
    assert len(list(settings.upload_dir.rglob("*"))) == 2


def test_concurrent_submission(worker):
    data = fields()
    cookie = dict(worker.cookies)

    def send(_):
        with TestClient(app, headers=HEADERS, cookies=cookie) as client:
            response = submit(client, data)
            return response.status_code, response.json()["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert sorted(status for status, _ in results) == [200, 201]
    assert results[0][1] == results[1][1]


@pytest.mark.parametrize(
    "change",
    [
        {"title": "    "},
        {"description": "short"},
        {"kind": "complaint"},
        {"category": "unknown"},
        {"submission_id": "oops"},
        {"author_id": str(uuid4())},
        {"title": "x" * 161},
    ],
)
def test_invalid_fields_do_not_create_appeal(worker, change):
    assert submit(worker, fields(**change)).status_code == 422
    assert worker.get("/appeals").json()["total"] == 0


@pytest.mark.parametrize(
    "filename,content",
    [
        ("empty.png", b""),
        ("fake.png", b"not an image"),
        ("fake.pdf", b"not pdf"),
        ("script.svg", b"<svg/>"),
        ("fake.jpg", None),
    ],
)
def test_invalid_files_leave_no_data(worker, filename, content):
    if content is None:
        content = png()
    assert submit(worker, files=[(filename, content, "image/png")]).status_code == 422
    assert worker.get("/appeals").json()["total"] == 0
    assert list(settings.upload_dir.iterdir()) == []


def test_attachment_limits(worker):
    assert (
        submit(
            worker,
            files=[("a.pdf", b"%PDF-" + b"x" * MAX_FILE_SIZE, "application/pdf")],
        ).status_code
        == 413
    )
    assert submit(worker, files=[("a.png", png(), "image/png")] * 6).status_code == 400
    assert worker.get("/appeals").json()["total"] == 0
    assert list(settings.upload_dir.iterdir()) == []
    # A valid first file must also be removed if a later file is invalid.
    assert (
        submit(
            worker,
            files=[
                ("ok.png", png(), "image/png"),
                ("bad.pdf", b"bad", "application/pdf"),
            ],
        ).status_code
        == 422
    )
    assert list(settings.upload_dir.iterdir()) == []


def test_body_limits_for_length_and_chunked_requests(worker):
    assert (
        worker.post(
            "/appeals", content=b"x", headers={"Content-Length": str(MAX_BODY_SIZE + 1)}
        ).status_code
        == 413
    )
    # Use the actual configured limit: nested limiters intentionally allow inner
    # routes to override the cap, so an extra wrapper would not test this app.
    with TestClient(app, headers=HEADERS) as client:
        response = client.post(
            "/auth/login",
            content=iter([b" " * 1024 * 1024] * (MAX_BODY_SIZE // (1024 * 1024) + 1)),
            headers={"Content-Type": "application/json"},
        )
        assert "content-length" not in response.request.headers
        assert response.status_code == 413


def test_failed_publish_rolls_back(worker, monkeypatch):
    def fail(_):
        raise OSError("Simulated disk failure")

    monkeypatch.setattr("app.uploads.StagedUploads.publish", fail)
    with TestClient(
        app,
        headers=HEADERS,
        cookies=dict(worker.cookies),
        raise_server_exceptions=False,
    ) as client:
        assert submit(client, files=[("ok.png", png(), "image/png")]).status_code == 500
    assert worker.get("/appeals").json()["total"] == 0
    assert list(settings.upload_dir.iterdir()) == []


def test_status_filters_and_pagination(worker):
    result = submit(worker).json()
    with Session(engine) as db:
        first = db.get(Appeal, result["id"])
        for index in range(24):
            db.add(
                Appeal(
                    submission_id=uuid4(),
                    payload_hash="test",
                    kind="idea",
                    title=f"Идея номер {index}",
                    description="Описание тестовой идеи",
                    original_description="Описание тестовой идеи",
                    category="other",
                    author_id=first.author_id,
                    company_id=first.company_id,
                    department_id=first.department_id,
                    status="closed" if index == 0 else "needs_info",
                )
            )
        db.commit()
    all_items = worker.get("/appeals").json()
    second_page = worker.get("/appeals?page=2").json()
    assert (
        all_items["total"] == 25
        and len(all_items["items"]) == 20
        and len(second_page["items"]) == 5
    )
    assert not (
        {item["id"] for item in all_items["items"]}
        & {item["id"] for item in second_page["items"]}
    )
    assert worker.get("/appeals?filter=completed").json()["total"] == 1
    assert worker.get("/appeals?filter=needs_reply").json()["total"] == 23
    assert worker.get("/appeals?filter=active").json()["total"] == 24
    assert worker.get("/appeals?page=0").status_code == 422
    assert worker.get("/appeals?filter=unknown").status_code == 422
