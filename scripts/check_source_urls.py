#!/usr/bin/env python3
"""Check source URLs without treating bot protection as a broken resource.

The default exit code is always zero so this can be introduced as an
informational audit. Pass ``--fail-on-broken`` when confirmed broken links
should produce a non-zero exit code.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import ssl
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from utils import load_sources


REPORT_SCHEMA_VERSION = 1
USER_AGENT = (
    "peer-calendar-source-check/1.0 "
    "(+https://github.com/lobabobloblaw/peer-calendar)"
)
MAX_RESPONSE_BYTES = 128 * 1024
# These statuses often represent bot/WAF policy rather than a missing page.
ACCESS_WARNING_STATUSES = {401, 403, 406, 407, 418, 451}
JS_CHALLENGE_MARKERS = (
    b"enable javascript",
    b"javascript is required",
    b"checking your browser",
    b"enable javascript and cookies",
    b"cf-chl-",
    b"challenge-platform",
    b"__cf_chl",
    b"just a moment...",
)


@dataclass
class RawResponse:
    """Small, transport-independent representation of an HTTP response."""

    status_code: int
    final_url: str
    headers: dict[str, str]
    body: bytes


class UnsafeUrlError(ValueError):
    """Raised when a request could reach a local or reserved network."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Expose redirects without fetching their destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def pinned_http_connection(vetted_address: str):
    """Return an HTTPConnection class that dials one vetted address."""

    import http.client

    class Connection(http.client.HTTPConnection):
        def __init__(self, host, **kwargs):
            super().__init__(host, **kwargs)
            self._create_connection = self._dial_vetted

        def _dial_vetted(self, address, timeout, source_address=None):
            _, port = address
            return socket.create_connection(
                (vetted_address, port), timeout, source_address
            )

    return Connection


def pinned_https_connection(vetted_address: str):
    """Return an HTTPSConnection class that preserves SNI/certificate checks."""

    import http.client

    class Connection(http.client.HTTPSConnection):
        def __init__(self, host, **kwargs):
            super().__init__(host, **kwargs)
            self._create_connection = self._dial_vetted

        def _dial_vetted(self, address, timeout, source_address=None):
            _, port = address
            return socket.create_connection(
                (vetted_address, port), timeout, source_address
            )

    return Connection


class PinnedHTTPHandler(HTTPHandler):
    def __init__(self, vetted_address: str):
        super().__init__()
        self._vetted_address = vetted_address

    def http_open(self, req):
        return self.do_open(pinned_http_connection(self._vetted_address), req)


class PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, vetted_address: str):
        super().__init__(context=ssl.create_default_context(), check_hostname=True)
        self._vetted_address = vetted_address

    def https_open(self, req):
        return self.do_open(pinned_https_connection(self._vetted_address), req)


def build_pinned_opener(scheme: str, vetted_address: str):
    """Build a no-proxy/no-redirect opener pinned to one vetted address."""

    if scheme == "https":
        handler = PinnedHTTPSHandler(vetted_address)
    else:
        handler = PinnedHTTPHandler(vetted_address)
    return build_opener(ProxyHandler({}), handler, NoRedirectHandler())


@dataclass
class LinkResult:
    """Serializable result for one unique URL."""

    url: str
    source_ids: list[str]
    host: str
    classification: str
    reason: str
    message: str
    status_code: int | None = None
    final_url: str | None = None
    redirected: bool = False
    method: str | None = None
    attempts: int = 0
    request_count: int = 0
    duration_ms: int = 0


class HostLimiter:
    """Bound concurrent checks to each host as well as globally."""

    def __init__(self, per_host: int):
        if per_host < 1:
            raise ValueError("per_host must be at least 1")
        self.per_host = per_host
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}

    def slot(self, host: str) -> threading.BoundedSemaphore:
        with self._lock:
            return self._semaphores.setdefault(
                host, threading.BoundedSemaphore(self.per_host)
            )


def _host_for_url(url: str) -> str:
    try:
        return urlparse(url).hostname or "<invalid>"
    except ValueError:
        return "<invalid>"


def _headers_to_dict(headers) -> dict[str, str]:
    if not headers:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _read_limited(response, method: str) -> bytes:
    if method != "GET":
        return b""
    return response.read(MAX_RESPONSE_BYTES + 1)[:MAX_RESPONSE_BYTES]


def _resolved_addresses(
    url: str, resolver: Callable = socket.getaddrinfo
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a URL and reject any target outside the public internet."""

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("The URL does not contain a hostname.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    records = resolver(host, port, type=socket.SOCK_STREAM)
    addresses = {
        ipaddress.ip_address(record[4][0].split("%", 1)[0]) for record in records
    }
    if not addresses:
        raise OSError("DNS resolution returned no addresses")
    unsafe = [str(address) for address in addresses if not address.is_global]
    if unsafe:
        raise UnsafeUrlError(
            "The hostname resolves to a private, loopback, link-local, or "
            "reserved network address."
        )
    return sorted(addresses, key=str)


def _open_once(opener, url: str, method: str, timeout: float) -> RawResponse:
    """Perform one request and return HTTP errors as ordinary responses."""

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5",
    }
    request = Request(url, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as error:
        try:
            return RawResponse(
                status_code=error.code,
                final_url=error.geturl() or url,
                headers=_headers_to_dict(error.headers),
                body=_read_limited(error, method),
            )
        finally:
            error.close()

    try:
        status = getattr(response, "status", None) or response.getcode()
        return RawResponse(
            status_code=int(status),
            final_url=response.geturl() or url,
            headers=_headers_to_dict(response.headers),
            body=_read_limited(response, method),
        )
    finally:
        response.close()


def perform_request(
    opener,
    url: str,
    method: str,
    timeout: float,
    *,
    resolver: Callable = socket.getaddrinfo,
) -> RawResponse:
    """Perform a request, validating DNS and every redirect destination."""

    validation_error = _validate_url(url)
    if validation_error:
        raise UnsafeUrlError(validation_error)
    parsed = urlparse(url)
    host = parsed.hostname
    assert host is not None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolved_addresses(url, resolver)
    # Tests may inject a fake opener. Production always builds a transport that
    # connects directly to one address from this vetted DNS result.
    if opener is None:
        opener = build_pinned_opener(parsed.scheme, str(addresses[0]))
    return _open_once(opener, url, method, timeout)


def _is_javascript_challenge(response: RawResponse) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if response.body and content_type and not any(
        value in content_type for value in ("html", "text", "javascript")
    ):
        return False
    body = response.body.lower()
    return any(marker in body for marker in JS_CHALLENGE_MARKERS)


def _classify_response(url: str, response: RawResponse, method: str) -> LinkResult:
    status = response.status_code
    final_url = response.final_url
    redirected = final_url.rstrip("/") != url.rstrip("/")
    common = {
        "url": url,
        "source_ids": [],
        "host": _host_for_url(url),
        "status_code": status,
        "final_url": final_url,
        "redirected": redirected,
        "method": method,
    }

    if status == 404:
        return LinkResult(
            **common,
            classification="broken",
            reason="not_found",
            message="The server confirmed that the page was not found.",
        )
    if status == 410:
        return LinkResult(
            **common,
            classification="broken",
            reason="gone",
            message="The server confirmed that the page is gone.",
        )
    if _is_javascript_challenge(response):
        return LinkResult(
            **common,
            classification="warning",
            reason="javascript_challenge",
            message="The response requires JavaScript or an anti-bot challenge.",
        )
    if 200 <= status < 300:
        return LinkResult(
            **common,
            classification="ok",
            reason="redirected" if redirected else "reachable",
            message="The URL redirected to a reachable page."
            if redirected
            else "The URL is reachable.",
        )
    if 300 <= status < 400:
        return LinkResult(
            **common,
            classification="warning",
            reason="unresolved_redirect",
            message="The URL redirects; verify its destination in a browser.",
        )
    if status in ACCESS_WARNING_STATUSES:
        return LinkResult(
            **common,
            classification="warning",
            reason="access_limited",
            message="The site restricts automated access; verify it in a browser.",
        )
    if status == 429:
        return LinkResult(
            **common,
            classification="warning",
            reason="rate_limited",
            message="The site rate-limited the checker; this is not a broken link.",
        )
    if 400 <= status < 500:
        return LinkResult(
            **common,
            classification="warning",
            reason="client_error",
            message=(
                f"The server returned HTTP {status}, which may reflect request "
                "policy rather than a missing page; verify it in a browser."
            ),
        )
    if status >= 500:
        return LinkResult(
            **common,
            classification="warning",
            reason="server_error",
            message=f"The server returned HTTP {status}; retry manually later.",
        )
    return LinkResult(
        **common,
        classification="warning",
        reason="unexpected_status",
        message=f"The server returned unexpected HTTP status {status}.",
    )


def _invalid_url_result(url: str, source_ids: Iterable[str], message: str) -> LinkResult:
    return LinkResult(
        url=url,
        source_ids=sorted(set(source_ids)),
        host=_host_for_url(url),
        classification="broken",
        reason="invalid_url",
        message=message,
    )


def _validate_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return "The URL contains an invalid hostname, IPv6 address, or port."
    if parsed.scheme not in {"http", "https"}:
        return "Only http:// and https:// source URLs can be checked."
    if not host:
        return "The URL does not contain a hostname."
    if parsed.username or parsed.password:
        return "Source URLs must not contain embedded credentials."
    if port is not None and not 1 <= port <= 65535:
        return "The URL port must be between 1 and 65535."
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return "Local-network URLs are not allowed."
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    if not address.is_global:
        return "Private, loopback, and reserved network addresses are not allowed."
    return None


def _fallback_to_get(status: int) -> bool:
    # Some sites reject HEAD while serving GET normally. Do not add load after a
    # 429; retry the lightweight HEAD instead.
    return status >= 400 and status != 429


def _retry_delay(result: LinkResult, attempt: int, response: RawResponse | None) -> float:
    delay = min(4.0, 0.5 * (2 ** (attempt - 1)))
    if response and result.reason == "rate_limited":
        value = response.headers.get("retry-after", "").strip()
        try:
            delay = min(10.0, max(delay, float(value)))
        except ValueError:
            pass
    return delay


def _exception_result(url: str, method: str, exc: Exception) -> LinkResult:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return LinkResult(
            url=url,
            source_ids=[],
            host=_host_for_url(url),
            classification="warning",
            reason="timeout",
            message="The request timed out; retry manually later.",
            method=method,
        )
    reason_obj = getattr(exc, "reason", exc)
    is_tls = isinstance(reason_obj, (ssl.SSLError, ssl.CertificateError))
    return LinkResult(
        url=url,
        source_ids=[],
        host=_host_for_url(url),
        classification="broken" if is_tls else "warning",
        reason="tls_error" if is_tls else "network_error",
        message="TLS certificate validation failed."
        if is_tls
        else "The network request failed; retry manually later.",
        method=method,
    )


def check_url(
    url: str,
    source_ids: Iterable[str] = (),
    *,
    timeout: float = 12.0,
    retries: int = 1,
    opener=None,
    resolver: Callable = socket.getaddrinfo,
    sleep: Callable[[float], None] = time.sleep,
) -> LinkResult:
    """Check one URL with HEAD, GET fallback, and bounded retries."""

    url = url.strip()
    source_ids = sorted(set(source_ids))
    validation_error = _validate_url(url)
    if validation_error:
        return _invalid_url_result(url, source_ids, validation_error)
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if retries < 0:
        raise ValueError("retries cannot be negative")

    started = time.monotonic()
    request_count = 0
    result: LinkResult | None = None

    for attempt in range(1, retries + 2):
        response = None
        method = "HEAD"
        try:
            request_count += 1
            response = perform_request(
                opener, url, method, timeout, resolver=resolver
            )
        except UnsafeUrlError as exc:
            result = _invalid_url_result(url, source_ids, str(exc))
            result.method = method
            result.attempts = attempt
            result.request_count = request_count
            break
        except (TimeoutError, socket.timeout, URLError, ConnectionError, OSError):
            # A proxy or origin can reject HEAD at the transport layer rather
            # than with HTTP 405. Confirm with one bounded GET before warning.
            method = "GET"
            try:
                request_count += 1
                response = perform_request(
                    opener, url, method, timeout, resolver=resolver
                )
                result = _classify_response(url, response, method)
            except UnsafeUrlError as exc:
                result = _invalid_url_result(url, source_ids, str(exc))
                result.method = method
            except (TimeoutError, socket.timeout, URLError, ConnectionError, OSError) as get_exc:
                result = _exception_result(url, method, get_exc)
        else:
            if _fallback_to_get(response.status_code):
                method = "GET"
                try:
                    request_count += 1
                    response = perform_request(
                        opener, url, method, timeout, resolver=resolver
                    )
                    result = _classify_response(url, response, method)
                except UnsafeUrlError as exc:
                    result = _invalid_url_result(url, source_ids, str(exc))
                    result.method = method
                except (
                    TimeoutError,
                    socket.timeout,
                    URLError,
                    ConnectionError,
                    OSError,
                ) as get_exc:
                    result = _exception_result(url, method, get_exc)
            else:
                result = _classify_response(url, response, method)

        result.attempts = attempt
        result.request_count = request_count
        should_retry = (
            attempt <= retries
            and result.reason
            in {"rate_limited", "server_error", "timeout", "network_error"}
        )
        if not should_retry:
            break
        sleep(_retry_delay(result, attempt, response))

    assert result is not None
    result.source_ids = source_ids
    result.duration_ms = round((time.monotonic() - started) * 1000)
    return result


def collect_source_urls(entries: Iterable[dict]) -> dict[str, list[str]]:
    """Return unique source URLs mapped to the entries that cite them."""

    url_sources: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        entry_id = str(entry.get("id", "<unknown>"))
        urls = entry.get("source_urls") or []
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            continue
        for value in urls:
            if isinstance(value, str) and value.strip():
                url_sources[value.strip()].add(entry_id)
    return {url: sorted(ids) for url, ids in sorted(url_sources.items())}


def check_urls(
    url_sources: Mapping[str, Iterable[str]],
    *,
    max_workers: int = 8,
    per_host: int = 2,
    timeout: float = 12.0,
    retries: int = 1,
    opener_factory: Callable[[], object] = lambda: None,
    resolver: Callable = socket.getaddrinfo,
    sleep: Callable[[float], None] = time.sleep,
) -> list[LinkResult]:
    """Check URLs concurrently while limiting requests to each host."""

    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    limiter = HostLimiter(per_host)

    def run_one(url: str, source_ids: Iterable[str]) -> LinkResult:
        host = _host_for_url(url)
        with limiter.slot(host):
            return check_url(
                url,
                source_ids,
                timeout=timeout,
                retries=retries,
                opener=opener_factory(),
                resolver=resolver,
                sleep=sleep,
            )

    results: list[LinkResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_one, url, source_ids): url
            for url, source_ids in url_sources.items()
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                results.append(future.result())
            except Exception:
                results.append(
                    LinkResult(
                        url=url,
                        source_ids=sorted(set(url_sources[url])),
                        host=_host_for_url(url),
                        classification="warning",
                        reason="checker_error",
                        message="The checker encountered an internal error for this URL.",
                    )
                )
    return sorted(results, key=lambda result: result.url)


def build_report(
    results: Iterable[LinkResult],
    *,
    source_file: str,
    entry_count: int,
    configuration: Mapping[str, int | float],
    generated_at: str | None = None,
) -> dict:
    results = list(results)
    classes = Counter(result.classification for result in results)
    by_reason = Counter(result.reason for result in results)
    by_status = Counter(
        str(result.status_code) if result.status_code is not None else "none"
        for result in results
    )
    hosts: dict[str, Counter] = defaultdict(Counter)
    for result in results:
        hosts[result.host]["total"] += 1
        hosts[result.host][result.classification] += 1

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file": source_file,
        "entry_count": entry_count,
        "configuration": dict(configuration),
        "summary": {
            "total": len(results),
            "ok": classes["ok"],
            "warning": classes["warning"],
            "broken": classes["broken"],
        },
        "by_reason": dict(sorted(by_reason.items())),
        "by_status": dict(sorted(by_status.items())),
        "by_host": [
            {
                "host": host,
                "total": counts["total"],
                "ok": counts["ok"],
                "warning": counts["warning"],
                "broken": counts["broken"],
            }
            for host, counts in sorted(hosts.items())
        ],
        "results": [asdict(result) for result in results],
    }


def _escape_markdown(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: Mapping, detail_limit: int = 30) -> str:
    summary = report["summary"]
    lines = [
        "## Source URL health",
        "",
        "This check is informational: access blocks and transient failures "
        "are warnings, not broken links.",
        "",
        "| URLs | Reachable | Warnings | Broken |",
        "| ---: | ---: | ---: | ---: |",
        f"| {summary['total']} | {summary['ok']} | {summary['warning']} | {summary['broken']} |",
    ]

    broken = [row for row in report["results"] if row["classification"] == "broken"]
    if broken:
        lines.extend(
            [
                "",
                "### Broken links",
                "",
                "| Status | Reason | Source entries | URL |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in broken[:detail_limit]:
            status = row["status_code"] if row["status_code"] is not None else "-"
            ids = ", ".join(row["source_ids"])
            lines.append(
                f"| {status} | {_escape_markdown(row['reason'])} | "
                f"{_escape_markdown(ids)} | <{row['url']}> |"
            )
        if len(broken) > detail_limit:
            lines.append(f"\n_And {len(broken) - detail_limit} more in the JSON artifact._")

    warning_reasons = Counter(
        row["reason"]
        for row in report["results"]
        if row["classification"] == "warning"
    )
    if warning_reasons:
        detail = ", ".join(
            f"`{_escape_markdown(reason)}`: {count}"
            for reason, count in sorted(warning_reasons.items())
        )
        lines.extend(["", f"Warnings by reason: {detail}."])
    return "\n".join(lines) + "\n"


def print_console_summary(report: Mapping, report_path: Path | None = None) -> None:
    summary = report["summary"]
    print(
        f"Checked {summary['total']} unique source URLs across "
        f"{report['entry_count']} entries: {summary['ok']} reachable, "
        f"{summary['warning']} warnings, {summary['broken']} broken."
    )
    broken = [row for row in report["results"] if row["classification"] == "broken"]
    for row in broken[:10]:
        status = row["status_code"] if row["status_code"] is not None else row["reason"]
        ids = ", ".join(row["source_ids"])
        print(f"  BROKEN [{status}] {row['url']} ({ids})")
    if len(broken) > 10:
        print(f"  ... {len(broken) - 10} more broken links in the JSON report")
    if report_path:
        print(f"JSON report: {report_path}")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("cannot be negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _resolve_input_path(value: str, script_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path.resolve()
    return (script_dir / path).resolve()


def _resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path.resolve()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check source_urls in sources.yaml and classify link health."
    )
    parser.add_argument("--sources", default="../data/sources.yaml")
    parser.add_argument("--output", help="Write the machine-readable JSON report here")
    parser.add_argument("--markdown-output", help="Write a concise Markdown summary here")
    parser.add_argument("--max-workers", type=_positive_int, default=8)
    parser.add_argument("--per-host", type=_positive_int, default=2)
    parser.add_argument("--timeout", type=_positive_float, default=12.0)
    parser.add_argument("--retries", type=_nonnegative_int, default=1)
    parser.add_argument(
        "--fail-on-broken",
        action="store_true",
        help="Exit 1 if confirmed broken links are found (default: informational only)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    sources_path = _resolve_input_path(args.sources, script_dir)
    if not sources_path.exists():
        print(f"Error: sources file not found: {sources_path}", file=sys.stderr)
        return 2

    entries = load_sources(sources_path)
    url_sources = collect_source_urls(entries)
    results = check_urls(
        url_sources,
        max_workers=args.max_workers,
        per_host=args.per_host,
        timeout=args.timeout,
        retries=args.retries,
    )
    configuration = {
        "max_workers": args.max_workers,
        "per_host": args.per_host,
        "timeout_seconds": args.timeout,
        "retries": args.retries,
    }
    report = build_report(
        results,
        source_file=str(sources_path),
        entry_count=len(entries),
        configuration=configuration,
    )

    output_path = _resolve_output_path(args.output) if args.output else None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        markdown_path = _resolve_output_path(args.markdown_output)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")

    print_console_summary(report, output_path)
    if args.fail_on_broken and report["summary"]["broken"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
