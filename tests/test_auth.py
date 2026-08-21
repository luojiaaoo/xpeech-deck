"""认证测试：正确/错误/缺失 Token 与公开接口。"""

from __future__ import annotations


def test_health_is_public(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_auth_check_with_correct_token(client, auth_headers):
    r = client.get("/api/auth/check", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"authenticated": True}


def test_missing_token_returns_401(client):
    assert client.get("/api/instances").status_code == 401
    assert client.get("/api/auth/check").status_code == 401
    assert client.post("/api/instances", json={"name": "demo01"}).status_code == 401


def test_wrong_token_returns_401(client):
    r = client.get("/api/instances", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Token 错误"


def test_non_bearer_header_returns_401(client):
    r = client.get("/api/instances", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401
