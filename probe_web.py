#!/usr/bin/env python3
"""Local web UI for the relay probe."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import relay_probe as probe


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def parse_payload(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


def clean_models(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        parts = value
    else:
        parts = []
    models = [str(item).strip() for item in parts if str(item).strip()]
    if not models:
        raise ValueError("Please provide at least one model ID.")
    return models


def as_int(value: Any, default: int, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, minimum)


def as_float(value: Any, default: float, *, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, minimum)


def collect_models_listing(
    *,
    base_url: str,
    api_key: str,
    timeout: float,
    requested_models: list[str],
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "status": None, "error": None}

    url = base_url.rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "relay-probe-web/1.0",
    }
    try:
        status, _, payload = probe.http_json("GET", url, headers, None, timeout)
        if status >= 400:
            return {
                "enabled": True,
                "status": status,
                "models_returned": 0,
                "sample_ids": [],
                "contains": {model: False for model in requested_models},
                "error": probe.compact_error(payload) if isinstance(payload, dict) else str(payload),
            }

        ids: list[str] = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            for item in payload["data"]:
                if isinstance(item, dict) and item.get("id"):
                    ids.append(str(item["id"]))

        return {
            "enabled": True,
            "status": status,
            "models_returned": len(ids),
            "sample_ids": ids[:18],
            "contains": {model: model in ids for model in requested_models},
            "error": None,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "status": None,
            "models_returned": 0,
            "sample_ids": [],
            "contains": {model: False for model in requested_models},
            "error": f"{type(exc).__name__}: {exc}",
        }


def serialize_run(run: probe.ProbeRun) -> dict[str, Any]:
    return {
        "ok": run.ok,
        "status": run.status,
        "latency_s": run.latency_s,
        "text": run.text,
        "response_model": run.response_model,
        "system_fingerprint": run.system_fingerprint,
        "error": run.error,
        "usage": run.usage,
    }


def collect_json_capability(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    run = probe.json_probe(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    valid_json = False
    json_keys: list[str] = []
    if run.ok:
        try:
            parsed = json.loads(run.text)
            valid_json = True
            if isinstance(parsed, dict):
                json_keys = sorted(parsed.keys())
        except json.JSONDecodeError:
            valid_json = False

    result = serialize_run(run)
    result["valid_json"] = valid_json
    result["json_keys"] = json_keys
    return result


def collect_stability(
    *,
    base_url: str,
    api_key: str,
    model: str,
    requests: int,
    concurrency: int,
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    runs = probe.stability_probe(
        base_url=base_url,
        api_key=api_key,
        model=model,
        total_requests=requests,
        concurrency=concurrency,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    summary = probe.summarize_run_group(runs, expected_exact="RELAY_OK_20260324")
    return {
        "requests": requests,
        "concurrency": concurrency,
        "summary": summary,
        "samples": [serialize_run(run) for run in runs[:6]],
    }


def collect_compare(
    *,
    base_url: str,
    api_key: str,
    models: list[str],
    timeout: float,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    if len(models) < 2:
        return {"enabled": False, "same_hash": False, "rows": []}

    results = probe.compare_probe(
        base_url=base_url,
        api_key=api_key,
        models=models,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    rows = []
    ok_hashes: list[str] = []
    for model, run in results.items():
        row = serialize_run(run)
        row["requested_model"] = model
        row["hash"] = probe.text_hash(run.text) if run.ok else None
        rows.append(row)
        if row["hash"]:
            ok_hashes.append(row["hash"])

    same_hash = len(ok_hashes) >= 2 and len(set(ok_hashes)) == 1
    return {
        "enabled": True,
        "same_hash": same_hash,
        "rows": rows,
        "note": (
            "多个模型 ID 返回了同一段输出哈希，可能共用同一后端。"
            if same_hash
            else None
        ),
    }


def build_model_assessment(model_report: dict[str, Any]) -> dict[str, Any]:
    single = model_report["single"]
    json_capability = model_report["json_capability"]
    stability = model_report["stability"]["summary"]

    route_rewritten = (
        bool(single.get("response_model"))
        and single.get("response_model") != model_report["id"]
    )
    unstable = stability.get("success_rate", 0.0) < 1.0 or stability.get("exact_match_rate", 0.0) < 1.0
    drifting = len(stability.get("response_models", [])) > 1 or len(stability.get("fingerprints", [])) > 1
    weak_json = not json_capability.get("valid_json")

    risk_score = 0
    if route_rewritten:
        risk_score += 35
    if unstable:
        risk_score += 35
    if drifting:
        risk_score += 20
    if weak_json:
        risk_score += 10

    if risk_score >= 60:
        tone = "高风险"
    elif risk_score >= 30:
        tone = "需谨慎"
    else:
        tone = "相对稳定"

    verdicts: list[str] = []
    if route_rewritten:
        verdicts.append("接口返回的 response_model 与你传入的模型 ID 不一致。")
    if unstable:
        verdicts.append("温度 0 的重复请求未能保持完全一致，稳定性不足。")
    if drifting:
        verdicts.append("短时间内出现了多组 response_model 或 fingerprint，路由存在漂移。")
    if weak_json:
        verdicts.append("JSON 约束能力偏弱，说明能力边界可能与声称模型不完全一致。")
    if not verdicts:
        verdicts.append("这组模型的元数据和行为目前看起来比较一致。")

    return {
        "label": tone,
        "risk_score": risk_score,
        "route_rewritten": route_rewritten,
        "unstable": unstable,
        "drifting": drifting,
        "weak_json": weak_json,
        "verdicts": verdicts,
    }


def build_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    models_listing = report["models_endpoint"]

    if models_listing.get("enabled") and models_listing.get("error"):
        findings.append(
            {
                "severity": "medium",
                "title": "模型列表接口不可用",
                "detail": "中转没有稳定暴露 /models，元数据层面的可观测性较弱。",
            }
        )

    for model_report in report["models"]:
        assessment = model_report["assessment"]
        if assessment["route_rewritten"]:
            findings.append(
                {
                    "severity": "high",
                    "title": f"{model_report['id']} 存在路由改写",
                    "detail": "返回体中的 response_model 和请求模型 ID 不一致，这通常意味着中转做了映射。",
                }
            )
        if assessment["unstable"]:
            findings.append(
                {
                    "severity": "high",
                    "title": f"{model_report['id']} 稳定性不足",
                    "detail": "固定温度下的重复请求没有保持 100% 成功率或 100% 精确一致率。",
                }
            )
        if assessment["drifting"]:
            findings.append(
                {
                    "severity": "medium",
                    "title": f"{model_report['id']} 存在后端漂移",
                    "detail": "同一轮短压测中出现多组 response_model 或 fingerprint，说明路由不稳定。",
                }
            )

    compare = report["compare"]
    if compare.get("enabled") and compare.get("same_hash"):
        findings.append(
            {
                "severity": "medium",
                "title": "多个模型 ID 的行为高度相似",
                "detail": "不同模型 ID 在约束性提示词下返回完全相同的输出哈希，存在共用后端的嫌疑。",
            }
        )

    if not findings:
        findings.append(
            {
                "severity": "low",
                "title": "暂未发现明显异常",
                "detail": "目前看到的是元数据与行为基本一致，但仍不能 100% 证明真实上游。",
            }
        )
    return findings


def build_overview(report: dict[str, Any]) -> dict[str, Any]:
    assessments = [model["assessment"] for model in report["models"]]
    stabilities = [model["stability"]["summary"] for model in report["models"]]

    avg_success = sum(item.get("success_rate", 0.0) for item in stabilities) / len(stabilities)
    avg_exact = sum(item.get("exact_match_rate", 0.0) for item in stabilities) / len(stabilities)
    p95_values = [item.get("latency_p95_s") for item in stabilities if item.get("latency_p95_s") is not None]
    avg_p95 = sum(p95_values) / len(p95_values) if p95_values else None

    score = 100
    score -= round((1.0 - avg_success) * 45)
    score -= round((1.0 - avg_exact) * 35)
    score -= sum(15 for item in assessments if item["route_rewritten"])
    score -= sum(8 for item in assessments if item["drifting"])
    score -= 5 if report["compare"].get("same_hash") else 0
    score = max(score, 0)

    if score >= 90:
        grade = "A"
        headline = "现在看起来比较稳"
    elif score >= 75:
        grade = "B"
        headline = "整体可用，但还要盯住细节"
    elif score >= 60:
        grade = "C"
        headline = "能用，但中转层有明显不确定性"
    else:
        grade = "D"
        headline = "这条中转需要谨慎对待"

    return {
        "grade": grade,
        "score": score,
        "headline": headline,
        "avg_success_rate": avg_success,
        "avg_exact_match_rate": avg_exact,
        "avg_latency_p95_s": avg_p95,
        "aliasing_suspected": report["compare"].get("same_hash", False),
        "findings_count": len(report["findings"]),
    }


def run_probe_report(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = str(payload.get("base_url", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    if not base_url:
        raise ValueError("Please provide a base URL.")
    if not api_key:
        raise ValueError("Please provide an API key.")

    models = clean_models(payload.get("models"))
    requests = as_int(payload.get("requests"), 12, minimum=1)
    concurrency = as_int(payload.get("concurrency"), 3, minimum=1)
    timeout = as_float(payload.get("timeout"), 60.0, minimum=1.0)
    temperature = as_float(payload.get("temperature"), 0.0, minimum=0.0)
    max_tokens = as_int(payload.get("max_tokens"), 96, minimum=1)
    skip_models_endpoint = bool(payload.get("skip_models_endpoint"))

    report: dict[str, Any] = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "base_url": base_url,
            "models": models,
            "requests": requests,
            "concurrency": concurrency,
            "timeout": timeout,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "skip_models_endpoint": skip_models_endpoint,
        },
        "models_endpoint": collect_models_listing(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            requested_models=models,
            enabled=not skip_models_endpoint,
        ),
        "models": [],
        "compare": {},
        "findings": [],
        "overview": {},
    }

    for model in models:
        model_report = {
            "id": model,
            "single": serialize_run(
                probe.run_completion(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    prompt=probe.EXACT_PROMPT,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            ),
            "json_capability": collect_json_capability(
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            "stability": collect_stability(
                base_url=base_url,
                api_key=api_key,
                model=model,
                requests=requests,
                concurrency=concurrency,
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        }
        model_report["assessment"] = build_model_assessment(model_report)
        report["models"].append(model_report)

    report["compare"] = collect_compare(
        base_url=base_url,
        api_key=api_key,
        models=models,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    report["findings"] = build_findings(report)
    report["overview"] = build_overview(report)
    return report


class ProbeRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/probe":
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = parse_payload(raw_body)
            report = run_probe_report(payload)
            json_response(self, HTTPStatus.OK, report)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except json.JSONDecodeError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body."})
        except Exception as exc:
            json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"{type(exc).__name__}: {exc}"},
            )

    def log_message(self, format: str, *args: Any) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the relay probe web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ProbeRequestHandler)
    print(f"Relay Probe UI running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
