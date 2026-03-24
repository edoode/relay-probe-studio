#!/usr/bin/env python3
"""Probe an OpenAI-compatible relay for model identity and stability.

This script answers three practical questions:
1. What model does the relay claim to expose?
2. Does the response behavior match that claim consistently?
3. How stable is the relay under repeated requests?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import textwrap
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


EXACT_PROMPT = (
    "Reply with exactly this text and nothing else:\n"
    "RELAY_OK_20260324"
)

COMPARE_PROMPT = textwrap.dedent(
    """
    Compare TCP and QUIC in exactly 6 lines.
    Each line must be 8 to 12 words.
    Do not use bullets or numbering.
    """
).strip()

JSON_PROMPT = (
    "Return only valid JSON matching this shape exactly: "
    '{"relay_ok": true, "tag": "probe", "n": 1}'
)


@dataclass
class ProbeRun:
    ok: bool
    status: int | None
    latency_s: float
    text: str
    response_model: str | None
    system_fingerprint: str | None
    error: str | None
    usage: dict[str, Any] | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe an OpenAI-compatible relay for identity and stability."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL"),
        help="OpenAI-compatible base URL, usually ending with /v1",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY",
    )
    parser.add_argument(
        "--model",
        action="append",
        required=False,
        help="Model ID to probe. Repeat to compare multiple models.",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=12,
        help="Number of stability requests per model",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Concurrent requests for the stability test",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for probes",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=96,
        help="max tokens to request",
    )
    parser.add_argument(
        "--skip-models-endpoint",
        action="store_true",
        help="Skip GET /models if your relay does not support it",
    )
    args = parser.parse_args()

    if not args.base_url:
        parser.error("--base-url is required or set OPENAI_BASE_URL")
    if not args.api_key:
        parser.error("--api-key is required or set OPENAI_API_KEY")
    if not args.model:
        env_model = os.environ.get("OPENAI_MODEL")
        if env_model:
            args.model = [env_model]
        else:
            parser.error("Provide at least one --model or set OPENAI_MODEL")
    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    return args


def http_json(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, str], dict[str, Any] | list[Any] | str]:
    data = None
    request_headers = headers.copy()
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url=url,
        method=method,
        headers=request_headers,
        data=data,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = parse_json_or_text(raw)
            return response.status, dict(response.headers.items()), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = parse_json_or_text(raw)
        return exc.code, dict(exc.headers.items()), parsed


def parse_json_or_text(raw: str) -> dict[str, Any] | list[Any] | str:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def completion_body(
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        body["response_format"] = response_format
    return body


def extract_text(payload: dict[str, Any] | list[Any] | str) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "\n".join(parts).strip()
    return json.dumps(payload, ensure_ascii=False)


def run_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    response_format: dict[str, Any] | None = None,
) -> ProbeRun:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "relay-probe/1.0",
    }
    started = time.perf_counter()
    try:
        status, response_headers, payload = http_json(
            method="POST",
            url=url,
            headers=headers,
            body=completion_body(
                model=model,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            ),
            timeout=timeout,
        )
        latency_s = time.perf_counter() - started
        if not isinstance(payload, dict):
            return ProbeRun(
                ok=False,
                status=status,
                latency_s=latency_s,
                text=extract_text(payload),
                response_model=None,
                system_fingerprint=None,
                error=f"Non-JSON response with status {status}",
                usage=None,
            )
        error = None
        if status >= 400:
            error = compact_error(payload)
        return ProbeRun(
            ok=status < 400,
            status=status,
            latency_s=latency_s,
            text=extract_text(payload),
            response_model=payload.get("model"),
            system_fingerprint=payload.get("system_fingerprint")
            or response_headers.get("x-system-fingerprint"),
            error=error,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        )
    except urllib.error.URLError as exc:
        return ProbeRun(
            ok=False,
            status=None,
            latency_s=time.perf_counter() - started,
            text="",
            response_model=None,
            system_fingerprint=None,
            error=f"URL error: {exc.reason}",
            usage=None,
        )
    except TimeoutError:
        return ProbeRun(
            ok=False,
            status=None,
            latency_s=time.perf_counter() - started,
            text="",
            response_model=None,
            system_fingerprint=None,
            error="Timeout",
            usage=None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return ProbeRun(
            ok=False,
            status=None,
            latency_s=time.perf_counter() - started,
            text="",
            response_model=None,
            system_fingerprint=None,
            error=f"{type(exc).__name__}: {exc}",
            usage=None,
        )


def compact_error(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("type") or str(error)
        return str(message)
    return json.dumps(payload, ensure_ascii=False)[:240]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def summarize_run_group(
    runs: list[ProbeRun],
    *,
    expected_exact: str | None = None,
) -> dict[str, Any]:
    ok_runs = [run for run in runs if run.ok]
    failed_runs = [run for run in runs if not run.ok]
    latencies = [run.latency_s for run in ok_runs]
    hashes = [text_hash(run.text) for run in ok_runs]

    summary: dict[str, Any] = {
        "total": len(runs),
        "ok": len(ok_runs),
        "failed": len(failed_runs),
        "success_rate": len(ok_runs) / len(runs) if runs else 0.0,
        "response_models": sorted({run.response_model for run in ok_runs if run.response_model}),
        "fingerprints": sorted(
            {run.system_fingerprint for run in ok_runs if run.system_fingerprint}
        ),
        "unique_output_hashes": sorted(set(hashes)),
        "latency_avg_s": statistics.mean(latencies) if latencies else None,
        "latency_p50_s": percentile(latencies, 0.50) if latencies else None,
        "latency_p95_s": percentile(latencies, 0.95) if latencies else None,
        "errors": [run.error for run in failed_runs if run.error],
    }
    if expected_exact is not None:
        exact_ok = sum(1 for run in ok_runs if run.text.strip() == expected_exact.strip())
        summary["exact_match_rate"] = exact_ok / len(ok_runs) if ok_runs else 0.0
    return summary


def stability_probe(
    *,
    base_url: str,
    api_key: str,
    model: str,
    total_requests: int,
    concurrency: int,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> list[ProbeRun]:
    runs: list[ProbeRun] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                run_completion,
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=EXACT_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            for _ in range(total_requests)
        ]
        for future in as_completed(futures):
            runs.append(future.result())
    runs.sort(key=lambda run: run.latency_s)
    return runs


def json_probe(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> ProbeRun:
    return run_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        prompt=JSON_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        response_format={"type": "json_object"},
    )


def compare_probe(
    *,
    base_url: str,
    api_key: str,
    models: list[str],
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> dict[str, ProbeRun]:
    results: dict[str, ProbeRun] = {}
    for model in models:
        results[model] = run_completion(
            base_url=base_url,
            api_key=api_key,
            model=model,
            prompt=COMPARE_PROMPT,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    return results


def format_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}s"


def print_models_section(base_url: str, api_key: str, timeout: float, requested: list[str]) -> None:
    print("== /models ==")
    try:
        url = base_url.rstrip("/") + "/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "relay-probe/1.0",
        }
        status, _, payload = http_json("GET", url, headers, None, timeout)
        print(f"status: {status}")
        if status >= 400:
            print(f"error: {compact_error(payload) if isinstance(payload, dict) else payload}")
            print()
            return
        ids: list[str] = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            for item in payload["data"]:
                if isinstance(item, dict) and item.get("id"):
                    ids.append(str(item["id"]))
        print(f"models_returned: {len(ids)}")
        if ids:
            preview = ", ".join(ids[:12])
            print(f"sample: {preview}")
        for model in requested:
            print(f"contains {model}: {'yes' if model in ids else 'no'}")
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}")
    print()


def print_single_probe(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> None:
    print(f"== Single Probe: {model} ==")
    run = run_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        prompt=EXACT_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    print(f"ok: {run.ok}")
    print(f"http_status: {run.status}")
    print(f"latency: {run.latency_s:.2f}s")
    print(f"requested_model: {model}")
    print(f"response_model: {run.response_model or '-'}")
    print(f"system_fingerprint: {run.system_fingerprint or '-'}")
    print(f"text: {json.dumps(run.text, ensure_ascii=False)}")
    if run.error:
        print(f"error: {run.error}")
    print()


def print_json_probe(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> None:
    print(f"== JSON Capability: {model} ==")
    run = json_probe(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    print(f"ok: {run.ok}")
    print(f"http_status: {run.status}")
    print(f"response_model: {run.response_model or '-'}")
    if run.ok:
        try:
            parsed = json.loads(run.text)
            print("valid_json: yes")
            print(f"json_keys: {sorted(parsed.keys()) if isinstance(parsed, dict) else '-'}")
        except json.JSONDecodeError:
            print("valid_json: no")
            print(f"text: {json.dumps(run.text, ensure_ascii=False)}")
    else:
        print(f"error: {run.error}")
    print()


def print_stability_probe(
    *,
    base_url: str,
    api_key: str,
    model: str,
    total_requests: int,
    concurrency: int,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> None:
    print(f"== Stability: {model} ==")
    print(f"requests: {total_requests}")
    print(f"concurrency: {concurrency}")
    runs = stability_probe(
        base_url=base_url,
        api_key=api_key,
        model=model,
        total_requests=total_requests,
        concurrency=concurrency,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    summary = summarize_run_group(runs, expected_exact="RELAY_OK_20260324")
    print(f"success_rate: {summary['success_rate']:.1%}")
    print(f"exact_match_rate: {summary.get('exact_match_rate', 0.0):.1%}")
    print(f"latency_avg: {format_seconds(summary['latency_avg_s'])}")
    print(f"latency_p50: {format_seconds(summary['latency_p50_s'])}")
    print(f"latency_p95: {format_seconds(summary['latency_p95_s'])}")
    print(f"response_models: {summary['response_models'] or '-'}")
    print(f"fingerprints: {summary['fingerprints'] or '-'}")
    print(f"unique_output_hashes: {summary['unique_output_hashes'] or '-'}")
    if summary["errors"]:
        print("errors:")
        for error in summary["errors"][:5]:
            print(f"  - {error}")
    print()


def print_compare_section(
    *,
    base_url: str,
    api_key: str,
    models: list[str],
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> None:
    if len(models) < 2:
        return
    print("== Cross-Model Compare ==")
    results = compare_probe(
        base_url=base_url,
        api_key=api_key,
        models=models,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    for model, run in results.items():
        print(f"[{model}] ok={run.ok} status={run.status} response_model={run.response_model or '-'}")
        if run.ok:
            print(f"  hash={text_hash(run.text)}")
            print(f"  text={json.dumps(run.text, ensure_ascii=False)}")
        else:
            print(f"  error={run.error}")
    ok_hashes = {
        model: text_hash(run.text)
        for model, run in results.items()
        if run.ok
    }
    if len(ok_hashes) >= 2 and len(set(ok_hashes.values())) == 1:
        print("note: all compared model IDs returned the same text hash.")
        print("      this can indicate aliasing to one backend, but is not proof.")
    print()


def print_interpretation_guide() -> None:
    print("== How To Read This ==")
    print("- If response_model differs from requested_model, the relay is rewriting routes.")
    print("- If /models does not contain the model you can still call, the listing is unreliable.")
    print("- If exact_match_rate is below 100% at temperature 0, the relay or backend is unstable.")
    print("- If fingerprints or response models change within one short burst, routing is inconsistent.")
    print("- If multiple model IDs produce the same nontrivial output hash, aliasing is possible.")
    print("- You can know the claimed model with confidence.")
    print("- You cannot prove the true upstream model with 100% certainty if the relay lies.")
    print("  You can only collect mismatch evidence from metadata, capabilities, and behavior.")


def main() -> int:
    args = parse_args()

    if not args.skip_models_endpoint:
        print_models_section(args.base_url, args.api_key, args.timeout, args.model)

    for model in args.model:
        print_single_probe(
            base_url=args.base_url,
            api_key=args.api_key,
            model=model,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        print_json_probe(
            base_url=args.base_url,
            api_key=args.api_key,
            model=model,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        print_stability_probe(
            base_url=args.base_url,
            api_key=args.api_key,
            model=model,
            total_requests=args.requests,
            concurrency=args.concurrency,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

    print_compare_section(
        base_url=args.base_url,
        api_key=args.api_key,
        models=args.model,
        timeout=args.timeout,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    print_interpretation_guide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
