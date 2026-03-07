#!/usr/bin/env bash
set -euo pipefail

KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
NAMESPACE="${NAMESPACE:-grafrag}"
OPENWEBUI_DEPLOYMENT="${OPENWEBUI_DEPLOYMENT:-openwebui}"
SEARCH_QUERY="${SEARCH_QUERY:-${1:-Open WebUI}}"
MIN_RESULTS="${MIN_RESULTS:-1}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120s}"
REQUIRE_API_TEST="${REQUIRE_API_TEST:-false}"
RUN_API_TEST="${RUN_API_TEST:-false}"
CHECK_SEARXNG_LOGS="${CHECK_SEARXNG_LOGS:-true}"
FAIL_ON_ENGINE_REFUSAL="${FAIL_ON_ENGINE_REFUSAL:-false}"
RETRY_ATTEMPTS="${RETRY_ATTEMPTS:-3}"
RETRY_DELAY_SECONDS="${RETRY_DELAY_SECONDS:-10}"

if ! command -v "${KUBECTL_BIN}" >/dev/null 2>&1; then
  echo "kubectl not found in PATH." >&2
  exit 1
fi

TEST_START_TIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

extract_result_json() {
  python3 -c 'import sys; lines=[line.split("=", 1)[1] for line in sys.stdin.read().splitlines() if line.startswith("RESULT_JSON=")]; print(lines[-1] if lines else ""); raise SystemExit(0 if lines else 1)'
}

json_outcome() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["outcome"])'
}

json_reason() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason", ""))'
}

json_has_admin_user() {
  python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("has_admin_user", False)).lower())'
}

json_refusal_count() {
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("total_refusals", 0))'
}

print_summary() {
  local label="$1"
  python3 -c 'import json, sys; data=json.load(sys.stdin); label=sys.argv[1]; summary={"label": label, "outcome": data.get("outcome"), "has_admin_user": data.get("has_admin_user"), "query": data.get("query"), "engine": data.get("engine"), "result_count": data.get("result_count"), "item_count": data.get("item_count"), "status_code": data.get("status_code"), "reason": data.get("reason"), "first_result": data.get("first_result"), "first_item": data.get("first_item"), "collection_names": data.get("collection_names"), "user_email": data.get("user_email"), "user_role": data.get("user_role"), "since_time": data.get("since_time"), "pod_count": data.get("pod_count"), "total_refusals": data.get("total_refusals"), "engines": data.get("engines"), "categories": data.get("categories"), "sample_events": data.get("sample_events")}; print(json.dumps(summary, ensure_ascii=False))' "${label}"
}

run_python_in_openwebui() {
  local description="$1"
  local script="$2"
  shift 2

  local stdout_file stderr_file rc
  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"

  if ! printf '%s\n' "${script}" | \
    "${KUBECTL_BIN}" -n "${NAMESPACE}" exec -i "deploy/${OPENWEBUI_DEPLOYMENT}" -- \
      env "$@" python - >"${stdout_file}" 2>"${stderr_file}"; then
    rc=$?
    echo "${description} failed." >&2
    if [[ -s "${stderr_file}" ]]; then
      cat "${stderr_file}" >&2
    fi
    if [[ -s "${stdout_file}" ]]; then
      cat "${stdout_file}" >&2
    fi
    rm -f "${stdout_file}" "${stderr_file}"
    return "${rc}"
  fi

  cat "${stdout_file}"
  rm -f "${stdout_file}" "${stderr_file}"
}

LAST_RESULT_JSON=""
LAST_OUTCOME=""

run_check_with_retry() {
  local description="$1"
  local label="$2"
  local script="$3"
  shift 3

  local raw json attempt reason
  for ((attempt = 1; attempt <= RETRY_ATTEMPTS; attempt++)); do
    raw="$(run_python_in_openwebui "${description}" "${script}" "$@")"
    json="$(printf '%s\n' "${raw}" | extract_result_json)"
    LAST_RESULT_JSON="${json}"
    LAST_OUTCOME="$(printf '%s\n' "${json}" | json_outcome)"
    reason="$(printf '%s\n' "${json}" | json_reason)"

    if [[ "${LAST_OUTCOME}" != "fail" ]]; then
      printf '%s\n' "${json}" | print_summary "${label}"
      return 0
    fi

    if (( attempt < RETRY_ATTEMPTS )) && [[ "${reason}" == *"429"* || "${reason}" == *"Too Many Requests"* ]]; then
      sleep "${RETRY_DELAY_SECONDS}"
      continue
    fi

    printf '%s\n' "${json}" | print_summary "${label}"
    return 1
  done
}

check_searxng_logs() {
  local log_dir fetch_failed=0 pod
  log_dir="$(mktemp -d)"
  searxng_pods=()

  while IFS= read -r pod; do
    if [[ -n "${pod}" ]]; then
      searxng_pods+=("${pod}")
    fi
  done < <(
    "${KUBECTL_BIN}" -n "${NAMESPACE}" get pods -l app=searxng \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'
  )

  if (( ${#searxng_pods[@]} == 0 )); then
    python3 - <<'PY'
import json
print(json.dumps({
    "outcome": "fail",
    "reason": "No searxng pods found",
    "since_time": None,
    "pod_count": 0,
    "total_refusals": 0,
    "engines": {},
    "categories": {},
    "sample_events": [],
}, ensure_ascii=False))
PY
    return 0
  fi

  for pod in "${searxng_pods[@]}"; do
    if ! "${KUBECTL_BIN}" -n "${NAMESPACE}" logs "pod/${pod}" --since-time="${TEST_START_TIME}" >"${log_dir}/${pod}.log" 2>"${log_dir}/${pod}.err"; then
      fetch_failed=1
    fi
  done

  TEST_START_TIME="${TEST_START_TIME}" LOG_FETCH_FAILED="${fetch_failed}" python3 - "${log_dir}" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

log_dir = Path(sys.argv[1])
since_time = os.environ.get("TEST_START_TIME")
fetch_failed = os.environ.get("LOG_FETCH_FAILED") == "1"

engine_pattern = re.compile(r"searx\.engines\.([A-Za-z0-9_]+)")
refusal_patterns = [
    ("captcha", re.compile(r"\bCAPTCHA\b", re.IGNORECASE)),
    ("too_many_requests", re.compile(r"\b429\b|Too Many Requests", re.IGNORECASE)),
    ("access_denied", re.compile(r"\b403\b|Forbidden|Access Denied|access denied", re.IGNORECASE)),
    ("blocked", re.compile(r"\bblocked\b|\bblocking\b", re.IGNORECASE)),
    ("refused", re.compile(r"\brefused\b|\brefusal\b", re.IGNORECASE)),
]

events = []
errors = []
pod_logs = sorted(log_dir.glob("*.log"))

for log_file in pod_logs:
    pod = log_file.stem
    err_file = log_dir / f"{pod}.err"
    if err_file.exists():
        err_text = err_file.read_text(encoding="utf-8", errors="ignore").strip()
        if err_text:
            errors.append({"pod": pod, "message": err_text})

    for raw_line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "searx.engines." not in raw_line:
            continue

        matched_category = None
        for category, pattern in refusal_patterns:
            if pattern.search(raw_line):
                matched_category = category
                break

        if matched_category is None:
            continue

        engine_match = engine_pattern.search(raw_line)
        events.append(
            {
                "pod": pod,
                "engine": engine_match.group(1) if engine_match else "unknown",
                "category": matched_category,
                "line": raw_line,
            }
        )

engines = {}
categories = {}
for event in events:
    engines[event["engine"]] = engines.get(event["engine"], 0) + 1
    categories[event["category"]] = categories.get(event["category"], 0) + 1

outcome = "pass"
reason = ""
if fetch_failed or errors:
    outcome = "fail"
    reason = "Unable to fetch all searxng pod logs"
elif events:
    outcome = "warn"
    reason = "Search engine refusals detected in searxng logs"

payload = {
    "outcome": outcome,
    "reason": reason,
    "since_time": since_time,
    "pod_count": len(pod_logs),
    "total_refusals": len(events),
    "engines": dict(sorted(engines.items())),
    "categories": dict(sorted(categories.items())),
    "sample_events": events[:5],
    "log_fetch_errors": errors,
}

print(json.dumps(payload, ensure_ascii=False))
PY

  rm -rf "${log_dir}"
}

PREFLIGHT_SCRIPT=$(cat <<'PY'
import json

from open_webui.models.users import Users

user = Users.get_super_admin_user()
payload = {
    "outcome": "pass",
    "has_admin_user": bool(user),
    "reason": "" if user else "No admin user found in the Open WebUI database",
    "user_email": user.email if user else None,
    "user_role": user.role if user else None,
}

print("RESULT_JSON=" + json.dumps(payload, ensure_ascii=False))
PY
)

HELPER_SCRIPT=$(cat <<'PY'
import json
import os
import random
from types import SimpleNamespace
from unittest.mock import patch

import requests
from open_webui.main import app
from open_webui.routers.retrieval import search_web

query = os.environ["SEARCH_QUERY"]
min_results = int(os.environ["MIN_RESULTS"])
request = SimpleNamespace(app=app)
fake_ip = f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
payload = {
    "outcome": "pass",
    "query": query,
    "engine": app.state.config.WEB_SEARCH_ENGINE,
    "reason": "",
    "result_count": 0,
    "first_result": None,
}

original_get = requests.get

def patched_get(*args, **kwargs):
    headers = dict(kwargs.get("headers") or {})
    headers.setdefault("X-Forwarded-For", fake_ip)
    headers.setdefault("X-Real-IP", fake_ip)
    kwargs["headers"] = headers
    return original_get(*args, **kwargs)

if not app.state.config.ENABLE_WEB_SEARCH:
    payload["outcome"] = "fail"
    payload["reason"] = "ENABLE_WEB_SEARCH is false"
else:
    try:
        with patch("requests.get", patched_get), patch(
            "open_webui.retrieval.web.searxng.requests.get", patched_get
        ):
            results = search_web(request, app.state.config.WEB_SEARCH_ENGINE, query)
        payload["result_count"] = len(results)
        if results:
            payload["first_result"] = {
                "link": results[0].link,
                "title": results[0].title,
                "snippet": results[0].snippet,
            }
        if len(results) < min_results:
            payload["outcome"] = "fail"
            payload["reason"] = (
                f"Expected at least {min_results} results but got {len(results)}"
            )
    except Exception as exc:
        payload["outcome"] = "fail"
        payload["reason"] = str(exc)

print("RESULT_JSON=" + json.dumps(payload, ensure_ascii=False))
PY
)

API_SCRIPT=$(cat <<'PY'
import json
import os

import requests

from open_webui.models.users import Users
from open_webui.utils.auth import create_token

query = os.environ["SEARCH_QUERY"]
min_results = int(os.environ["MIN_RESULTS"])
payload = {
    "outcome": "skip",
    "query": query,
    "reason": "",
    "status_code": None,
    "item_count": 0,
    "first_item": None,
    "collection_names": [],
    "user_email": None,
    "user_role": None,
}

user = Users.get_super_admin_user()
if user is None:
    first_user = Users.get_first_user()
    if first_user is None:
        payload["reason"] = (
            "No Open WebUI user exists yet. Log in once, then rerun to exercise the API."
        )
        print("RESULT_JSON=" + json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0)
    if first_user.role != "admin":
        payload["reason"] = (
            f"First Open WebUI user {first_user.email} is not admin. "
            "Log in with an admin user, then rerun."
        )
        print("RESULT_JSON=" + json.dumps(payload, ensure_ascii=False))
        raise SystemExit(0)
    user = first_user

payload["user_email"] = user.email
payload["user_role"] = user.role

try:
    response = requests.post(
        "http://127.0.0.1:8080/api/v1/retrieval/process/web/search",
        headers={"Authorization": f"Bearer {create_token({'id': user.id})}"},
        json={"queries": [query]},
        timeout=180,
    )
    payload["status_code"] = response.status_code

    data = response.json() if "json" in response.headers.get("content-type", "") else {}
    items = data.get("items") or []
    payload["item_count"] = len(items)
    payload["collection_names"] = data.get("collection_names") or []
    if items:
        payload["first_item"] = items[0]

    if response.status_code != 200:
        payload["outcome"] = "fail"
        payload["reason"] = (
            f"Expected HTTP 200 but got {response.status_code}: "
            f"{response.text[:240]}"
        )
    elif len(items) < min_results:
        payload["outcome"] = "fail"
        payload["reason"] = (
            f"Expected at least {min_results} items but got {len(items)}"
        )
    else:
        payload["outcome"] = "pass"
except Exception as exc:
    payload["outcome"] = "fail"
    payload["reason"] = str(exc)

print("RESULT_JSON=" + json.dumps(payload, ensure_ascii=False))
PY
)

echo "Waiting for deployment/${OPENWEBUI_DEPLOYMENT} in namespace ${NAMESPACE}"
"${KUBECTL_BIN}" -n "${NAMESPACE}" rollout status "deployment/${OPENWEBUI_DEPLOYMENT}" --timeout="${REQUEST_TIMEOUT}" >/dev/null

if [[ "${RUN_API_TEST}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
  preflight_raw="$(run_python_in_openwebui "Open WebUI admin preflight" "${PREFLIGHT_SCRIPT}")"
  preflight_json="$(printf '%s\n' "${preflight_raw}" | extract_result_json)"
  printf '%s\n' "${preflight_json}" | print_summary "preflight"

  if [[ "$(printf '%s\n' "${preflight_json}" | json_has_admin_user)" == "true" ]]; then
    echo "Checking authenticated Open WebUI retrieval API for query: ${SEARCH_QUERY}"
    if ! run_check_with_retry \
      "Open WebUI retrieval API check" \
      "api" \
      "${API_SCRIPT}" \
      SEARCH_QUERY="${SEARCH_QUERY}" \
      MIN_RESULTS="${MIN_RESULTS}"; then
      exit 1
    fi
  else
    echo "No admin user detected in Open WebUI. Falling back to helper check for query: ${SEARCH_QUERY}"
    if ! run_check_with_retry \
      "Open WebUI web search helper check" \
      "helper" \
      "${HELPER_SCRIPT}" \
      SEARCH_QUERY="${SEARCH_QUERY}" \
      MIN_RESULTS="${MIN_RESULTS}"; then
      exit 1
    fi

    if [[ "${REQUIRE_API_TEST}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
      echo "REQUIRE_API_TEST=true but no admin Open WebUI user is available yet." >&2
      exit 1
    fi
  fi
else
  echo "Checking Open WebUI web search helper for query: ${SEARCH_QUERY}"
  if ! run_check_with_retry \
    "Open WebUI web search helper check" \
    "helper" \
    "${HELPER_SCRIPT}" \
    SEARCH_QUERY="${SEARCH_QUERY}" \
    MIN_RESULTS="${MIN_RESULTS}"; then
    exit 1
  fi
fi

if [[ "${CHECK_SEARXNG_LOGS}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
  echo "Checking SearXNG logs for search engine refusals since ${TEST_START_TIME}"
  searxng_logs_json="$(check_searxng_logs)"
  printf '%s\n' "${searxng_logs_json}" | print_summary "searxng-logs"

  searxng_logs_outcome="$(printf '%s\n' "${searxng_logs_json}" | json_outcome)"
  if [[ "${searxng_logs_outcome}" == "fail" ]]; then
    exit 1
  fi

  if [[ "${searxng_logs_outcome}" == "warn" && "${FAIL_ON_ENGINE_REFUSAL}" =~ ^([Tt][Rr][Uu][Ee]|1|[Yy][Ee]?[Ss])$ ]]; then
    exit 1
  fi
fi

echo "Kubernetes web search smoke test passed."
