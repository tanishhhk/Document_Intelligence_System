from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import docs_urls


def test_api_docs_can_be_turned_off_for_public_deployments():
    client = TestClient(FastAPI(**docs_urls(False)))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_api_docs_are_served_when_enabled():
    client = TestClient(FastAPI(**docs_urls(True)))
    assert client.get("/openapi.json").status_code == 200
