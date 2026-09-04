"""公开落地页、全局映射配置与根路径 OAuth2 重定向测试。"""

from __future__ import annotations

import json
from dataclasses import replace

from fastapi.testclient import TestClient

from xpeech_deck.app import create_app


def test_public_instances_only_expose_name_and_web_port(client, make_instance):
    make_instance("demo01")

    response = client.get("/api/public/instances")

    assert response.status_code == 200
    assert response.json() == {
        "display_name": "Xpeech Deck",
        "instances": [{"name": "demo01", "web_client_port": 7939}],
    }


def test_global_config_api_requires_token(client):
    assert client.get("/api/global-config").status_code == 401
    assert client.put("/api/global-config", json={"mappings": []}).status_code == 401


def test_global_config_api_saves_json(client, auth_headers, settings):
    response = client.put(
        "/api/global-config",
        headers=auth_headers,
        json={
            "mappings": [
                {"redirect_to": "desktop", "instance_name": "demo01"},
                {"redirect_to": "mobile", "instance_name": "demo02"},
            ]
        },
    )

    assert response.status_code == 200
    assert json.loads(settings.global_config_path.read_text(encoding="utf-8")) == {
        "redirect_to": {"desktop": "demo01", "mobile": "demo02"}
    }
    assert client.get("/api/global-config", headers=auth_headers).json() == {
        "mappings": [
            {"redirect_to": "desktop", "instance_name": "demo01"},
            {"redirect_to": "mobile", "instance_name": "demo02"},
        ]
    }


def test_global_config_rejects_duplicate_redirect_to(client, auth_headers):
    response = client.put(
        "/api/global-config",
        headers=auth_headers,
        json={
            "mappings": [
                {"redirect_to": "same", "instance_name": "demo01"},
                {"redirect_to": "same", "instance_name": "demo02"},
            ]
        },
    )

    assert response.status_code == 400


def test_root_redirects_using_realtime_mapping_and_passes_oauth_params(
    settings, make_instance
):
    make_instance("demo01")
    configured = replace(settings, global_host="https://deck.example.com")
    configured.global_config_path.write_text(
        json.dumps({"redirect_to": {"desktop": "demo01"}}), encoding="utf-8"
    )
    test_client = TestClient(create_app(configured))

    response = test_client.get(
        "/?redirect_to=desktop&state=a%2Fb%3D&oauth2provider=feishu",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://deck.example.com:7939/api/auth/oauth2/callback"
        "?state=a%2Fb%3D&oauth2provider=feishu"
    )

    configured.global_config_path.write_text(
        json.dumps({"redirect_to": {"changed": "demo01"}}), encoding="utf-8"
    )
    assert (
        test_client.get("/?redirect_to=desktop", follow_redirects=False).status_code
        == 404
    )
    assert (
        test_client.get("/?redirect_to=changed", follow_redirects=False).status_code
        == 307
    )


def test_root_redirect_does_not_fall_back_when_global_host_is_missing(
    client, settings
):
    settings.global_config_path.write_text(
        json.dumps({"redirect_to": {"desktop": "demo01"}}), encoding="utf-8"
    )

    response = client.get("/?redirect_to=desktop", follow_redirects=False)

    assert response.status_code == 400


def test_root_redirect_does_not_fall_back_for_missing_mapping(client):
    configured = replace(
        client.app.state.settings, global_host="https://deck.example.com"
    )
    test_client = TestClient(create_app(configured))

    response = test_client.get("/?redirect_to=unknown", follow_redirects=False)

    assert response.status_code == 404


def test_root_redirect_does_not_fall_back_for_missing_instance(settings):
    configured = replace(settings, global_host="https://deck.example.com")
    configured.global_config_path.write_text(
        json.dumps({"redirect_to": {"desktop": "missing"}}), encoding="utf-8"
    )
    test_client = TestClient(create_app(configured))

    response = test_client.get("/?redirect_to=desktop", follow_redirects=False)

    assert response.status_code == 404


def test_token_presence_or_missing_redirect_to_opens_frontend(client):
    assert client.get("/?token=").status_code == 200
    assert client.get("/?token=value&redirect_to=unknown").status_code == 200
    assert client.get("/").status_code == 200
