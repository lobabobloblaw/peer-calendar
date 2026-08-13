#!/usr/bin/env python3
"""Deterministic tests for check_source_urls.py (no live network)."""

from __future__ import annotations

import io
import json
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

import check_source_urls as links


def public_resolver(host, port, type=0):
    """Return a documentation-only public address without doing live DNS."""

    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class FakeResponse:
    def __init__(
        self,
        status: int,
        url: str = "https://example.org/source",
        *,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ):
        self.status = status
        self._url = url
        self.headers = headers or {}
        self._body = io.BytesIO(body)
        self.closed = False

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def read(self, size=-1):
        return self._body.read(size)

    def close(self):
        self.closed = True


class SequenceOpener:
    def __init__(self, actions):
        self.actions = list(actions)
        self.requests: list[tuple[str, float]] = []

    def open(self, request, timeout):
        self.requests.append((request.get_method(), timeout))
        if not self.actions:
            raise AssertionError("Unexpected request")
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


class CheckUrlTests(unittest.TestCase):
    def check_url(self, *args, **kwargs):
        kwargs.setdefault("resolver", public_resolver)
        return links.check_url(*args, **kwargs)

    def test_reachable_head_response(self):
        opener = SequenceOpener([FakeResponse(200)])

        result = self.check_url(
            "https://example.org/source", ["entry-a"], opener=opener, retries=0
        )

        self.assertEqual(result.classification, "ok")
        self.assertEqual(result.reason, "reachable")
        self.assertEqual(result.method, "HEAD")
        self.assertEqual(result.source_ids, ["entry-a"])
        self.assertEqual(opener.requests, [("HEAD", 12.0)])

    def test_followed_redirect_is_healthy_and_records_destination(self):
        opener = SequenceOpener(
            [FakeResponse(200, "https://www.example.org/current")]
        )

        result = self.check_url(
            "https://example.org/old", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "ok")
        self.assertEqual(result.reason, "redirected")
        self.assertTrue(result.redirected)
        self.assertEqual(result.final_url, "https://www.example.org/current")

    def test_head_404_is_confirmed_with_get_before_marking_broken(self):
        opener = SequenceOpener([FakeResponse(404), FakeResponse(404)])

        result = self.check_url(
            "https://example.org/missing", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "broken")
        self.assertEqual(result.reason, "not_found")
        self.assertEqual(opener.requests, [("HEAD", 12.0), ("GET", 12.0)])

    def test_403_is_warning_not_broken(self):
        opener = SequenceOpener([FakeResponse(403), FakeResponse(403)])

        result = self.check_url(
            "https://example.org/protected", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "warning")
        self.assertEqual(result.reason, "access_limited")

    def test_other_access_policy_statuses_are_warnings(self):
        for status in (401, 406, 407, 418, 451):
            with self.subTest(status=status):
                opener = SequenceOpener([FakeResponse(status), FakeResponse(status)])
                result = self.check_url(
                    "https://example.org/policy", opener=opener, retries=0
                )
                self.assertEqual(result.classification, "warning")
                self.assertEqual(result.reason, "access_limited")

    def test_429_retries_head_then_remains_warning(self):
        sleeps = []
        opener = SequenceOpener(
            [
                FakeResponse(429, headers={"Retry-After": "2"}),
                FakeResponse(429),
            ]
        )

        result = self.check_url(
            "https://example.org/busy",
            opener=opener,
            retries=1,
            sleep=sleeps.append,
        )

        self.assertEqual(result.classification, "warning")
        self.assertEqual(result.reason, "rate_limited")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.request_count, 2)
        self.assertEqual(sleeps, [2.0])

    def test_head_transport_failure_falls_back_to_get(self):
        opener = SequenceOpener(
            [URLError("HEAD blocked"), FakeResponse(200)]
        )

        result = self.check_url(
            "https://example.org/source", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "ok")
        self.assertEqual(result.method, "GET")
        self.assertEqual(opener.requests, [("HEAD", 12.0), ("GET", 12.0)])

    def test_javascript_challenge_is_warning(self):
        opener = SequenceOpener(
            [
                FakeResponse(405),
                FakeResponse(
                    200,
                    headers={"Content-Type": "text/html; charset=utf-8"},
                    body=b"<h1>JavaScript is required</h1>",
                ),
            ]
        )

        result = self.check_url(
            "https://example.org/app", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "warning")
        self.assertEqual(result.reason, "javascript_challenge")

    def test_404_takes_precedence_over_javascript_template_text(self):
        missing = FakeResponse(
            404,
            headers={"Content-Type": "text/html"},
            body=b"Page missing. Enable JavaScript for navigation.",
        )
        opener = SequenceOpener([missing, missing])

        result = self.check_url(
            "https://example.org/missing", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "broken")
        self.assertEqual(result.reason, "not_found")

    def test_ambiguous_client_errors_are_warnings(self):
        for status in (400, 408, 409, 425, 426, 428, 431):
            with self.subTest(status=status):
                opener = SequenceOpener([FakeResponse(status), FakeResponse(status)])
                result = self.check_url(
                    "https://example.org/request-policy", opener=opener, retries=0
                )
                self.assertEqual(result.classification, "warning")
                self.assertEqual(result.reason, "client_error")

    def test_server_error_retries_after_get_confirmation(self):
        sleeps = []
        opener = SequenceOpener(
            [FakeResponse(503), FakeResponse(503), FakeResponse(204)]
        )

        result = self.check_url(
            "https://example.org/source",
            opener=opener,
            retries=1,
            sleep=sleeps.append,
        )

        self.assertEqual(result.classification, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.request_count, 3)
        self.assertEqual(sleeps, [0.5])

    def test_tls_failure_is_broken_after_head_and_get(self):
        cert_error = ssl.SSLCertVerificationError(1, "bad certificate")
        opener = SequenceOpener([URLError(cert_error), URLError(cert_error)])

        result = self.check_url(
            "https://example.org/source", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "broken")
        self.assertEqual(result.reason, "tls_error")

    def test_private_and_malformed_urls_are_rejected_without_requests(self):
        for url in (
            "ftp://example.org/file",
            "http://127.0.0.1/admin",
            "http://[bad]/",
            "http://example.org:99999/",
            "not-a-url",
        ):
            with self.subTest(url=url):
                opener = SequenceOpener([])
                result = self.check_url(url, opener=opener, retries=0)
                self.assertEqual(result.classification, "broken")
                self.assertEqual(result.reason, "invalid_url")
                self.assertEqual(opener.requests, [])

    def test_dns_resolution_to_private_address_is_rejected(self):
        opener = SequenceOpener([])

        result = self.check_url(
            "https://calendar.example.org/source",
            opener=opener,
            retries=0,
            resolver=lambda host, port, type=0: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
            ],
        )

        self.assertEqual(result.classification, "broken")
        self.assertEqual(result.reason, "invalid_url")
        self.assertEqual(opener.requests, [])

    def test_noncanonical_loopback_address_is_rejected_after_resolution(self):
        opener = SequenceOpener([])

        result = self.check_url(
            "http://2130706433/source",
            opener=opener,
            retries=0,
            resolver=lambda host, port, type=0: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
            ],
        )

        self.assertEqual(result.reason, "invalid_url")
        self.assertEqual(opener.requests, [])

    def test_redirect_to_private_address_is_not_followed(self):
        opener = SequenceOpener(
            [FakeResponse(302, headers={"Location": "http://169.254.169.254/latest"})]
        )

        def resolver(host, port, type=0):
            address = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

        result = self.check_url(
            "https://example.org/source",
            opener=opener,
            resolver=resolver,
            retries=0,
        )

        self.assertEqual(result.classification, "warning")
        self.assertEqual(result.reason, "unresolved_redirect")
        self.assertEqual(opener.requests, [("HEAD", 12.0)])

    def test_redirect_is_reported_without_following_destination(self):
        opener = SequenceOpener(
            [FakeResponse(301, headers={"Location": "/current"})]
        )

        result = self.check_url(
            "https://example.org/old", opener=opener, retries=0
        )

        self.assertEqual(result.classification, "warning")
        self.assertEqual(result.reason, "unresolved_redirect")
        self.assertEqual(len(opener.requests), 1)


class TransportTests(unittest.TestCase):
    def test_http_error_is_returned_as_response_and_body_is_bounded(self):
        error = HTTPError(
            "https://example.org/missing",
            404,
            "Not Found",
            {"Content-Type": "text/html"},
            io.BytesIO(b"missing"),
        )
        opener = SequenceOpener([error])

        response = links.perform_request(
            opener,
            "https://example.org/missing",
            "GET",
            3.0,
            resolver=public_resolver,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body, b"missing")
        self.assertEqual(response.headers["content-type"], "text/html")

    def test_host_limiter_reuses_bounded_semaphore(self):
        limiter = links.HostLimiter(1)
        first = limiter.slot("example.org")
        second = limiter.slot("example.org")
        self.assertIs(first, second)
        self.assertTrue(first.acquire(blocking=False))
        self.assertFalse(second.acquire(blocking=False))
        first.release()

    def test_pinned_http_connection_dials_vetted_address(self):
        connection_class = links.pinned_http_connection("93.184.216.34")
        connection = connection_class("calendar.example.org", timeout=3)
        sentinel = object()

        with mock.patch(
            "check_source_urls.socket.create_connection", return_value=sentinel
        ) as dial:
            sock = connection._dial_vetted(("calendar.example.org", 80), 3)

        self.assertIs(sock, sentinel)
        dial.assert_called_once_with(("93.184.216.34", 80), 3, None)

    def test_pinned_https_connection_retains_original_hostname(self):
        connection_class = links.pinned_https_connection("93.184.216.34")
        connection = connection_class("calendar.example.org", timeout=3)

        self.assertEqual(connection.host, "calendar.example.org")
        with mock.patch(
            "check_source_urls.socket.create_connection", return_value=object()
        ) as dial:
            connection._dial_vetted(("calendar.example.org", 443), 3)
        dial.assert_called_once_with(("93.184.216.34", 443), 3, None)

    def test_production_transport_builds_pinned_opener(self):
        response = links.RawResponse(
            status_code=200,
            final_url="https://example.org/source",
            headers={},
            body=b"",
        )
        fake_opener = SequenceOpener([FakeResponse(200)])

        with mock.patch(
            "check_source_urls.build_pinned_opener", return_value=fake_opener
        ) as build:
            result = links.perform_request(
                None,
                "https://example.org/source",
                "HEAD",
                3.0,
                resolver=public_resolver,
            )

        build.assert_called_once_with("https", "93.184.216.34")
        self.assertEqual(result.status_code, response.status_code)


class CollectionAndReportingTests(unittest.TestCase):
    def test_collect_source_urls_deduplicates_and_tracks_entries(self):
        entries = [
            {"id": "b", "source_urls": ["https://example.org/a"]},
            {
                "id": "a",
                "source_urls": [
                    " https://example.org/a ",
                    "https://example.org/b",
                ],
            },
            {"id": "ignored", "source_urls": None},
        ]

        self.assertEqual(
            links.collect_source_urls(entries),
            {
                "https://example.org/a": ["a", "b"],
                "https://example.org/b": ["a"],
            },
        )

    def test_report_groups_by_host_status_and_reason(self):
        results = [
            links.LinkResult(
                url="https://a.example/ok",
                source_ids=["a"],
                host="a.example",
                classification="ok",
                reason="reachable",
                message="ok",
                status_code=200,
            ),
            links.LinkResult(
                url="https://a.example/no",
                source_ids=["b"],
                host="a.example",
                classification="broken",
                reason="not_found",
                message="no",
                status_code=404,
            ),
            links.LinkResult(
                url="https://b.example/blocked",
                source_ids=["c"],
                host="b.example",
                classification="warning",
                reason="access_limited",
                message="blocked",
                status_code=403,
            ),
        ]

        report = links.build_report(
            results,
            source_file="data/sources.yaml",
            entry_count=3,
            configuration={"max_workers": 2},
            generated_at="2026-08-13T12:00:00+00:00",
        )

        self.assertEqual(
            report["summary"], {"total": 3, "ok": 1, "warning": 1, "broken": 1}
        )
        self.assertEqual(report["by_status"], {"200": 1, "403": 1, "404": 1})
        self.assertEqual(report["by_host"][0]["total"], 2)
        markdown = links.render_markdown(report)
        self.assertIn("## Source URL health", markdown)
        self.assertIn("https://a.example/no", markdown)
        self.assertIn("`access_limited`: 1", markdown)

    def test_check_urls_returns_stable_url_order(self):
        def opener_factory():
            return SequenceOpener([FakeResponse(200)])

        results = links.check_urls(
            {
                "https://z.example/source": ["z"],
                "https://a.example/source": ["a"],
            },
            max_workers=2,
            opener_factory=opener_factory,
            resolver=public_resolver,
            retries=0,
        )

        self.assertEqual(
            [result.url for result in results],
            ["https://a.example/source", "https://z.example/source"],
        )

    def test_batch_marks_malformed_authority_invalid(self):
        results = links.check_urls(
            {"http://[bad]/": ["bad-entry"]},
            max_workers=1,
            opener_factory=lambda: SequenceOpener([]),
            resolver=public_resolver,
            retries=0,
        )

        self.assertEqual(results[0].classification, "broken")
        self.assertEqual(results[0].reason, "invalid_url")

    def test_main_writes_json_and_fail_on_broken_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sources = root / "sources.yaml"
            output = root / "report.json"
            sources.write_text(
                "- id: example\n  source_urls:\n    - https://example.org/missing\n",
                encoding="utf-8",
            )
            result = links.LinkResult(
                url="https://example.org/missing",
                source_ids=["example"],
                host="example.org",
                classification="broken",
                reason="not_found",
                message="missing",
                status_code=404,
            )

            with mock.patch("check_source_urls.check_urls", return_value=[result]):
                informational = links.main(
                    ["--sources", str(sources), "--output", str(output)]
                )
                blocking = links.main(
                    [
                        "--sources",
                        str(sources),
                        "--output",
                        str(output),
                        "--fail-on-broken",
                    ]
                )

            self.assertEqual(informational, 0)
            self.assertEqual(blocking, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["summary"]["broken"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
