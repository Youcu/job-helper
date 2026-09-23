"""테스트 공용 도구. 네트워크와 시계를 대신한다."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = json.loads((ROOT / "fixtures" / "job_details.json").read_text(encoding="utf-8"))


# --- 목록 API 대역 --------------------------------------------------------


class FakeClient:
    """정해진 페이지를 돌려주는 가짜 목록 API. `pages(offset)` 이 응답을 만든다."""

    def __init__(self, pages):
        self.pages = pages
        self.calls: list[int] = []

    def get_json(self, path, *, params, referer):
        offset = int(dict(params)["offset"])
        self.calls.append(offset)
        result = self.pages(offset)
        if isinstance(result, Exception):
            raise result
        return result


def page(ids, has_next):
    return {"data": [{"id": i} for i in ids], "links": {"next": "…" if has_next else None}}


# --- HTTP 세션 대역 -------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload=None, url="https://www.wanted.co.kr/x"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {self.url}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """`requests.Session` 자리에 끼워 넣는다. 정해진 응답을 순서대로 돌려준다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.headers: dict[str, str] = {}
        self.requests: list[dict] = []

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.requests.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        item = self.responses.pop(0) if self.responses else FakeResponse(200)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(responses, **kwargs):
    """잠들지 않는 클라이언트. 재시도 백오프까지 기다리면 테스트가 몇 초씩 멈춘다.

    헤더는 실제 세션에 설정된 것을 그대로 옮긴다 — 헤더 구성이 검사 대상이라
    가짜로 덮으면 검사할 것이 없어진다.
    """
    from lib.client import WantedClient

    client = WantedClient(min_delay=0, max_delay=0, **kwargs)
    fake = FakeSession(responses)
    fake.headers = dict(client.session.headers)
    client.session = fake
    return client


# --- 파일 · 단언 ----------------------------------------------------------


def write_env(directory: Path, body: str) -> Path:
    path = directory / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def temp_dir():
    return tempfile.TemporaryDirectory()


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as other:
        raise AssertionError(f"{exc_type.__name__} 를 기대했는데 {type(other).__name__}: {other}")
    raise AssertionError(f"{exc_type.__name__} 가 나야 하는데 조용히 통과했다")
