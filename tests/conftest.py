"""A fake Companies House on localhost, shared by the tests that cross the live connection."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

TEST_KEY = "test-key-not-a-secret"
# HTTP Basic auth for TEST_KEY as the username with a blank password, worked out by hand.
EXPECTED_AUTH = "Basic dGVzdC1rZXktbm90LWEtc2VjcmV0Og=="


@dataclass
class FakeCompaniesHouse:
    """Answers /company/{number} like the real API (the profile, or 404), and name searches.

    `respond` scripts a run of responses for one number (a 429, then a 503, and so on). The last
    scripted response repeats; a scripted 200 serves the company's profile.
    """

    url: str = ""
    companies: dict[str, dict[str, Any]] = field(default_factory=dict)
    script: dict[str, list[tuple[int, dict[str, str]]]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def add(self, profile: dict[str, Any]) -> None:
        self.companies[profile["company_number"]] = profile

    def respond(self, number: str, *responses: tuple[int, dict[str, str]]) -> None:
        self.script[number] = list(responses)

    def answer(self, path: str) -> tuple[int, dict[str, str], dict[str, Any] | None]:
        if path.startswith("/search/companies?"):
            return 200, {}, self.search(parse_qs(urlsplit(path).query)["q"][0])
        number = path.removeprefix("/company/")
        queue = self.script.get(number)
        if queue:
            status, headers = queue.pop(0) if len(queue) > 1 else queue[0]
        else:
            status, headers = (200, {}) if number in self.companies else (404, {})
        return status, headers, self.companies.get(number) if status == 200 else None

    def search(self, query: str) -> dict[str, Any]:
        """Like the real search, loose on purpose: any company sharing a word with the query."""
        words = set(query.upper().split())
        items = [
            {
                "company_number": number,
                "title": profile.get("company_name", ""),
                "company_status": profile.get("company_status", ""),
                "address": {
                    "postal_code": (profile.get("registered_office_address") or {}).get(
                        "postal_code", ""
                    )
                },
            }
            for number, profile in self.companies.items()
            if words & set(profile.get("company_name", "").upper().split())
        ]
        return {"total_results": len(items), "items": items}


@pytest.fixture
def companies_house() -> Iterator[FakeCompaniesHouse]:
    fake = FakeCompaniesHouse()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.requests.append(self.path)
            headers: dict[str, str]
            if self.headers.get("Authorization") != EXPECTED_AUTH:
                status, headers, body = 401, {}, None
            else:
                status, headers, body = fake.answer(self.path)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if body is not None:
                self.wfile.write(json.dumps(body).encode())

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    server.shutdown()
    server.server_close()
