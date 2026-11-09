PASSWORD = "a-long-test-password"
HEADERS = {"X-Modus-Request": "1"}


def invite(client, ids, **overrides):
    return client.post(
        "/admin/invitations",
        json={
            "name": "Сотрудник",
            "email": "worker@example.com",
            "company_id": ids["company_id"],
            "department_id": ids["department_id"],
            "roles": ["employee"],
            **overrides,
        },
    )


def token_from(response):
    assert response.status_code == 201, response.text
    return response.json()["activation_path"].split("token=")[1]
