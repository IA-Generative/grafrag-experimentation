#!/usr/bin/env python3
"""Run reproducible local GraphRAG indexing benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
GRAPHRAG_DIR = ROOT_DIR / "graphrag"
BENCHMARKS_DIR = ROOT_DIR / "benchmarks"
ARTIFACTS_DIR = BENCHMARKS_DIR / "artifacts"
WORKSPACES_DIR = GRAPHRAG_DIR / "benchmarks" / "workspaces"
RESULTS_PATH = BENCHMARKS_DIR / "results.json"
SUMMARY_PATH = BENCHMARKS_DIR / "summary.md"
PLACEHOLDER_VALUES = {"", "CHANGE_ME", "EXAMPLE_ONLY", "REPLACE_ME"}
DEFAULT_DOCKER_CONTAINER = "grafrag-experimentation-bridge-1"
DEFAULT_OPTIMIZED_CHAT_MODEL = "mistral-small-3.2-24b-instruct-2506"
DEFAULT_OPTIMIZED_EMBEDDING_MODEL = "qwen3-embedding-8b"
EMBEDDING_VECTOR_SIZES = {
    "bge-multilingual-gemma2": 3584,
    "qwen3-embedding-8b": 4096,
}
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")
WORKFLOW_START_RE = re.compile(r"Workflow started: ([A-Za-z0-9_]+)")
WORKFLOW_DONE_RE = re.compile(r"Workflow completed: ([A-Za-z0-9_]+)")
PROGRESS_RE = re.compile(r" - ([A-Za-z0-9_ ]+progress):\s*(\d+)/(\d+)")


@dataclass(frozen=True)
class RunSpec:
    name: str
    settings_file: str
    method: str
    cache_state: str
    chat_model: str
    embedding_model: str
    quality_note: str
    clear_cache: bool
    reuse_workspace: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runner",
        choices=("auto", "docker", "local"),
        default="auto",
        help="Execution backend for graphrag.",
    )
    parser.add_argument(
        "--container",
        default=os.getenv("BENCHMARK_BRIDGE_CONTAINER", DEFAULT_DOCKER_CONTAINER),
        help="Docker container name when --runner=docker or auto selects Docker.",
    )
    parser.add_argument(
        "--baseline-method",
        choices=("standard", "fast", "standard-update", "fast-update"),
        default="standard",
        help="Indexing method for the baseline run.",
    )
    parser.add_argument(
        "--optimized-method",
        choices=("standard", "fast", "standard-update", "fast-update"),
        default="standard",
        help="Indexing method for the optimized runs.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip model compatibility checks against the active OpenAI-compatible endpoint.",
    )
    return parser.parse_args()


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def is_set(value: str | None) -> bool:
    return value is not None and value.strip() not in PLACEHOLDER_VALUES


def first_set(*values: str | None) -> str | None:
    for value in values:
        if is_set(value):
            return value
    return None


def infer_vector_size(model: str) -> int:
    return EMBEDDING_VECTOR_SIZES.get(model, EMBEDDING_VECTOR_SIZES["bge-multilingual-gemma2"])


def host_run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    stdout: Any = None,
    stderr: Any = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        check=False,
        stdout=stdout,
        stderr=stderr,
    )


def docker_available(container: str) -> bool:
    if shutil.which("docker") is None:
        return False
    result = host_run(["docker", "inspect", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def detect_runner(preferred: str, container: str) -> str:
    if preferred != "auto":
        return preferred
    if shutil.which("graphrag"):
        return "local"
    if docker_available(container):
        return "docker"
    raise RuntimeError("Neither local graphrag nor the benchmark Docker container is available.")


def read_container_env(container: str) -> dict[str, str]:
    result = host_run(["docker", "exec", container, "env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to read environment from Docker container {container}: {result.stderr.strip()}")
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def resolve_runtime_env(runner: str, container: str) -> dict[str, str]:
    merged = load_env_file(ROOT_DIR / ".env")
    merged.update(os.environ)
    container_env: dict[str, str] = {}
    if runner == "docker":
        container_env = read_container_env(container)
    api_key = first_set(
        merged.get("SCW_API_KEY"),
        merged.get("SCW_SECRET_KEY_LLM"),
        container_env.get("SCW_API_KEY"),
        container_env.get("SCW_SECRET_KEY_LLM"),
    )
    chat_base_url = first_set(
        merged.get("SCW_CHAT_BASE_URL"),
        merged.get("SCW_LLM_BASE_URL"),
        merged.get("OPENAI_API_BASE"),
        container_env.get("SCW_CHAT_BASE_URL"),
        container_env.get("SCW_LLM_BASE_URL"),
        container_env.get("OPENAI_API_BASE"),
    )
    embedding_base_url = first_set(
        merged.get("SCW_EMBEDDING_BASE_URL"),
        merged.get("SCW_CHAT_BASE_URL"),
        merged.get("SCW_LLM_BASE_URL"),
        merged.get("OPENAI_API_BASE"),
        container_env.get("SCW_EMBEDDING_BASE_URL"),
        container_env.get("SCW_CHAT_BASE_URL"),
        container_env.get("SCW_LLM_BASE_URL"),
        container_env.get("OPENAI_API_BASE"),
        chat_base_url,
    )
    chat_model = first_set(
        merged.get("SCW_CHAT_MODEL"),
        merged.get("SCW_LLM_MODEL"),
        merged.get("OPENAI_MODEL"),
        container_env.get("SCW_CHAT_MODEL"),
        container_env.get("SCW_LLM_MODEL"),
        container_env.get("OPENAI_MODEL"),
    )
    embedding_model = first_set(
        merged.get("SCW_EMBEDDING_MODEL"),
        merged.get("OPENAI_EMBEDDING_MODEL"),
        container_env.get("SCW_EMBEDDING_MODEL"),
        container_env.get("OPENAI_EMBEDDING_MODEL"),
    )
    if not all((api_key, chat_base_url, embedding_base_url, chat_model, embedding_model)):
        raise RuntimeError(
            "Missing benchmark environment values. Set SCW_API_KEY/SCW_SECRET_KEY_LLM, "
            "SCW_CHAT_BASE_URL, SCW_EMBEDDING_BASE_URL, SCW_CHAT_MODEL, and SCW_EMBEDDING_MODEL."
        )
    runtime_env = dict(merged)
    runtime_env.update(container_env)
    runtime_env["SCW_API_KEY"] = api_key
    runtime_env["SCW_SECRET_KEY_LLM"] = api_key
    runtime_env["SCW_CHAT_BASE_URL"] = chat_base_url
    runtime_env["SCW_EMBEDDING_BASE_URL"] = embedding_base_url
    runtime_env["SCW_CHAT_MODEL"] = chat_model
    runtime_env["SCW_EMBEDDING_MODEL"] = embedding_model
    runtime_env["SCW_BASELINE_CHAT_MODEL"] = first_set(
        merged.get("SCW_BASELINE_CHAT_MODEL"),
        container_env.get("SCW_BASELINE_CHAT_MODEL"),
        runtime_env["SCW_CHAT_MODEL"],
    ) or runtime_env["SCW_CHAT_MODEL"]
    runtime_env["SCW_BASELINE_EMBEDDING_MODEL"] = first_set(
        merged.get("SCW_BASELINE_EMBEDDING_MODEL"),
        container_env.get("SCW_BASELINE_EMBEDDING_MODEL"),
        runtime_env["SCW_EMBEDDING_MODEL"],
    ) or runtime_env["SCW_EMBEDDING_MODEL"]
    runtime_env["SCW_OPTIMIZED_CHAT_MODEL"] = first_set(
        merged.get("SCW_OPTIMIZED_CHAT_MODEL"),
        container_env.get("SCW_OPTIMIZED_CHAT_MODEL"),
        DEFAULT_OPTIMIZED_CHAT_MODEL,
    ) or DEFAULT_OPTIMIZED_CHAT_MODEL
    runtime_env["SCW_OPTIMIZED_EMBEDDING_MODEL"] = first_set(
        merged.get("SCW_OPTIMIZED_EMBEDDING_MODEL"),
        container_env.get("SCW_OPTIMIZED_EMBEDDING_MODEL"),
        DEFAULT_OPTIMIZED_EMBEDDING_MODEL,
    ) or DEFAULT_OPTIMIZED_EMBEDDING_MODEL
    return runtime_env


def ensure_directories() -> None:
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def repo_relative_container_path(path: Path) -> str:
    relative = path.resolve().relative_to(GRAPHRAG_DIR.resolve())
    return f"/app/graphrag/{relative.as_posix()}"


def build_execution_env(
    base_env: dict[str, str],
    *,
    chat_model: str,
    embedding_model: str,
) -> dict[str, str]:
    vector_size = infer_vector_size(embedding_model)
    env = dict(base_env)
    env["SCW_CHAT_MODEL"] = chat_model
    env["SCW_EMBEDDING_MODEL"] = embedding_model
    env["SCW_LLM_MODEL"] = chat_model
    env["OPENAI_MODEL"] = chat_model
    env["OPENAI_API_BASE"] = env["SCW_CHAT_BASE_URL"]
    env["OPENAI_API_KEY"] = env["SCW_API_KEY"]
    env["OPENAI_EMBEDDING_MODEL"] = embedding_model
    env["OPENAI_EMBEDDING_VECTOR_SIZE"] = str(vector_size)
    env["TMPDIR"] = "/tmp"
    env["TMP"] = "/tmp"
    env["TEMP"] = "/tmp"
    return env


def runner_python_script(
    runner: str,
    container: str,
    code: str,
    env: dict[str, str],
) -> str:
    command = [sys.executable, "-c", code]
    if runner == "docker":
        command = ["python", "-c", code]
        docker_command = ["docker", "exec"]
        for key, value in env.items():
            docker_command.extend(["-e", f"{key}={value}"])
        docker_command.extend([container, *command])
        result = host_run(docker_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        result = host_run(command, env={**os.environ, **env}, cwd=ROOT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Python helper command failed.")
    return result.stdout.strip()


def runner_command(
    runner: str,
    container: str,
    command: list[str],
    *,
    env: dict[str, str],
    cwd: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    stdout_handle = open(stdout_path, "w", encoding="utf-8") if stdout_path else subprocess.PIPE
    stderr_handle = open(stderr_path, "w", encoding="utf-8") if stderr_path else subprocess.PIPE
    try:
        if runner == "docker":
            docker_command = ["docker", "exec"]
            if cwd:
                docker_command.extend(["-w", repo_relative_container_path(cwd)])
            for key, value in env.items():
                docker_command.extend(["-e", f"{key}={value}"])
            docker_command.extend([container, *command])
            return host_run(docker_command, stdout=stdout_handle, stderr=stderr_handle)
        execution_env = {**os.environ, **env}
        return host_run(command, env=execution_env, cwd=cwd, stdout=stdout_handle, stderr=stderr_handle)
    finally:
        if stdout_path:
            stdout_handle.close()
        if stderr_path:
            stderr_handle.close()


def git_commit_sha() -> str | None:
    result = host_run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT_DIR, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout.strip() if result.returncode == 0 else None


def runner_versions(runner: str, container: str) -> dict[str, str]:
    code = textwrap.dedent(
        """
        import importlib.metadata as md
        import json
        import platform
        payload = {
            "python_version": platform.python_version(),
            "graphrag_version": md.version("graphrag"),
            "litellm_version": md.version("litellm"),
            "openai_version": md.version("openai"),
        }
        print(json.dumps(payload))
        """
    ).strip()
    payload = json.loads(runner_python_script(runner, container, code, {}))
    return {key: str(value) for key, value in payload.items()}


def collect_corpus_stats(root: Path) -> dict[str, Any]:
    documents = [path for path in sorted(root.rglob("*")) if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in documents)
    return {
        "document_count": len(documents),
        "total_bytes": total_bytes,
        "documents": [
            {"path": str(path.relative_to(root)), "size_bytes": path.stat().st_size}
            for path in documents
        ],
    }


def copy_corpus_input(destination: Path) -> None:
    shutil.copytree(GRAPHRAG_DIR / "input", destination / "input")


def prepare_workspace(run_label: str, settings_file: str) -> Path:
    workspace = WORKSPACES_DIR / run_label
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    copy_corpus_input(workspace)
    (workspace / "output").mkdir(parents=True, exist_ok=True)
    (workspace / "cache").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GRAPHRAG_DIR / settings_file, workspace / "settings.yaml")
    return workspace


def reset_workspace(workspace: Path, *, clear_cache: bool) -> None:
    output_dir = workspace / "output"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if clear_cache:
        cache_dir = workspace / "cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)


def validate_models(
    runner: str,
    container: str,
    env: dict[str, str],
    *,
    chat_model: str,
    embedding_model: str,
) -> dict[str, Any]:
    helper_env = build_execution_env(env, chat_model=chat_model, embedding_model=embedding_model)
    code = textwrap.dedent(
        """
        import json
        import os
        from openai import OpenAI

        chat_client = OpenAI(base_url=os.environ["SCW_CHAT_BASE_URL"], api_key=os.environ["SCW_API_KEY"])
        embedding_client = OpenAI(base_url=os.environ["SCW_EMBEDDING_BASE_URL"], api_key=os.environ["SCW_API_KEY"])
        chat = chat_client.chat.completions.create(
            model=os.environ["SCW_CHAT_MODEL"],
            messages=[
                {"role": "system", "content": "Return valid json only."},
                {"role": "user", "content": "Return an object with keys ok=true and label=benchmark."},
            ],
            response_format={"type": "json_object"},
        )
        embeddings = embedding_client.embeddings.create(
            model=os.environ["SCW_EMBEDDING_MODEL"],
            input=["bonjour benchmark"],
        )
        payload = {
            "chat_model": os.environ["SCW_CHAT_MODEL"],
            "embedding_model": os.environ["SCW_EMBEDDING_MODEL"],
            "chat_response": chat.choices[0].message.content,
            "embedding_vector_size": len(embeddings.data[0].embedding),
        }
        print(json.dumps(payload))
        """
    ).strip()
    payload = json.loads(runner_python_script(runner, container, code, helper_env))
    expected_vector_size = infer_vector_size(embedding_model)
    if int(payload["embedding_vector_size"]) != expected_vector_size:
        raise RuntimeError(
            f"Embedding dimension mismatch for {embedding_model}: "
            f"expected {expected_vector_size}, got {payload['embedding_vector_size']}."
        )
    return payload


def collect_output_counts(runner: str, container: str, workspace: Path) -> dict[str, int]:
    code = textwrap.dedent(
        f"""
        import json
        from pathlib import Path
        import pandas as pd

        root = Path({json.dumps(repo_relative_container_path(workspace / "output"))})
        payload = {{}}
        for name in [
            "documents.parquet",
            "text_units.parquet",
            "entities.parquet",
            "relationships.parquet",
            "communities.parquet",
            "community_reports.parquet",
        ]:
            payload[name] = int(len(pd.read_parquet(root / name)))
        print(json.dumps(payload))
        """
    ).strip()
    return json.loads(runner_python_script(runner, container, code, {}))


def parse_phase_timings(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {"phases_seconds": {}, "progress": {}, "started_at": None, "ended_at": None}
    start_times: dict[str, datetime] = {}
    phase_seconds: dict[str, float] = {}
    progress: dict[str, dict[str, int]] = {}
    started_at: datetime | None = None
    ended_at: datetime | None = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        ts_match = TIMESTAMP_RE.match(line)
        timestamp = (
            datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
            if ts_match
            else None
        )
        if timestamp and started_at is None:
            started_at = timestamp
        if timestamp:
            ended_at = timestamp
        start_match = WORKFLOW_START_RE.search(line)
        if start_match and timestamp:
            start_times[start_match.group(1)] = timestamp
        done_match = WORKFLOW_DONE_RE.search(line)
        if done_match and timestamp:
            workflow = done_match.group(1)
            if workflow in start_times:
                phase_seconds[workflow] = round((timestamp - start_times[workflow]).total_seconds(), 3)
        progress_match = PROGRESS_RE.search(line)
        if progress_match:
            label = progress_match.group(1).strip().replace(" ", "_")
            progress[label] = {
                "current": int(progress_match.group(2)),
                "total": int(progress_match.group(3)),
            }
    return {
        "phases_seconds": phase_seconds,
        "progress": progress,
        "started_at": started_at.isoformat() if started_at else None,
        "ended_at": ended_at.isoformat() if ended_at else None,
    }


def extract_metrics_tail(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        read_size = min(size, 32768)
        handle.seek(-read_size, os.SEEK_END)
        tail = handle.read(read_size).decode("utf-8", errors="ignore")
    marker = tail.rfind('"metrics":')
    if marker == -1:
        return {}
    brace_start = tail.find("{", marker)
    if brace_start == -1:
        return {}
    depth = 0
    for index in range(brace_start, len(tail)):
        char = tail[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                metrics_blob = tail[brace_start : index + 1]
                return json.loads(metrics_blob)
    return {}


def collect_cache_metrics(cache_dir: Path) -> dict[str, Any]:
    categories: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    non_zero_cost_found = False
    file_count = 0
    for path in sorted(cache_dir.rglob("*")):
        if not path.is_file():
            continue
        metrics = extract_metrics_tail(path)
        if not metrics:
            continue
        file_count += 1
        category = path.parent.name
        bucket = categories.setdefault(
            category,
            {
                "files": 0,
                "attempted_request_count": 0,
                "successful_response_count": 0,
                "failed_response_count": 0,
                "responses_with_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "compute_duration_seconds": 0.0,
                "cost": 0.0,
            },
        )
        bucket["files"] += 1
        for key in (
            "attempted_request_count",
            "successful_response_count",
            "failed_response_count",
            "responses_with_tokens",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            bucket[key] += int(metrics.get(key, 0) or 0)
        bucket["compute_duration_seconds"] += float(metrics.get("compute_duration_seconds", 0.0) or 0.0)
        cost = float(metrics.get("cost_per_response", 0.0) or 0.0)
        bucket["cost"] += cost
        total_cost += cost
        if cost:
            non_zero_cost_found = True
    for payload in categories.values():
        payload["compute_duration_seconds"] = round(payload["compute_duration_seconds"], 3)
        payload["cost"] = round(payload["cost"], 6)
    return {
        "file_count": file_count,
        "categories": categories,
        "llm_calls_observed": int(
            sum(payload["attempted_request_count"] for payload in categories.values())
        ),
        "total_tokens": int(sum(payload["total_tokens"] for payload in categories.values())),
        "estimated_cost": round(total_cost, 6) if non_zero_cost_found else None,
    }


def copy_run_artifacts(workspace: Path, artifact_dir: Path, stdout_path: Path, stderr_path: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for source in (
        workspace / "settings.yaml",
        workspace / "output" / "reports" / "indexing-engine.log",
        workspace / "output" / "stats.json",
        stdout_path,
        stderr_path,
    ):
        if source.exists():
            shutil.copyfile(source, artifact_dir / source.name)


def execute_run(
    runner: str,
    container: str,
    runtime_env: dict[str, str],
    run_spec: RunSpec,
    workspace: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    reset_workspace(workspace, clear_cache=run_spec.clear_cache)
    execution_env = build_execution_env(
        runtime_env,
        chat_model=run_spec.chat_model,
        embedding_model=run_spec.embedding_model,
    )
    stdout_path = artifact_root / f"{run_spec.name}.stdout.log"
    stderr_path = artifact_root / f"{run_spec.name}.stderr.log"
    command = [
        "graphrag",
        "index",
        "--root",
        repo_relative_container_path(workspace) if runner == "docker" else str(workspace),
        "--method",
        run_spec.method,
        "--cache",
    ]
    started_at = datetime.now().astimezone()
    started_perf = time.perf_counter()
    result = runner_command(
        runner,
        container,
        command,
        env=execution_env,
        cwd=workspace if runner == "local" else None,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    duration_seconds = round(time.perf_counter() - started_perf, 3)
    ended_at = datetime.now().astimezone()
    if result.returncode != 0:
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="ignore")
        raise RuntimeError(
            f"{run_spec.name} failed with exit code {result.returncode}.\n{stderr_text.strip()}"
        )
    output_counts = collect_output_counts(runner, container, workspace)
    phase_timings = parse_phase_timings(workspace / "output" / "reports" / "indexing-engine.log")
    cache_metrics = collect_cache_metrics(workspace / "cache")
    artifact_dir = artifact_root / run_spec.name
    copy_run_artifacts(workspace, artifact_dir, stdout_path, stderr_path)
    return {
        "name": run_spec.name,
        "settings_file": run_spec.settings_file,
        "settings_path": str((workspace / "settings.yaml").relative_to(ROOT_DIR)),
        "workspace_path": str(workspace.relative_to(ROOT_DIR)),
        "artifact_path": str(artifact_dir.relative_to(ROOT_DIR)),
        "method": run_spec.method,
        "cache_state": run_spec.cache_state,
        "chat_model": run_spec.chat_model,
        "embedding_model": run_spec.embedding_model,
        "embedding_vector_size": infer_vector_size(run_spec.embedding_model),
        "chunking": {
            "size": 1200,
            "overlap": 100,
        }
        if run_spec.settings_file == "settings.baseline.yaml"
        else {
            "size": 1800,
            "overlap": 80,
        },
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": duration_seconds,
        "quality_note": run_spec.quality_note,
        "documents": output_counts["documents.parquet"],
        "chunks": output_counts["text_units.parquet"],
        "entities": output_counts["entities.parquet"],
        "relationships": output_counts["relationships.parquet"],
        "communities": output_counts["communities.parquet"],
        "community_reports": output_counts["community_reports.parquet"],
        "phase_timings": phase_timings,
        "cache_metrics": cache_metrics,
    }


def comparison_payload(baseline: dict[str, Any], optimized: dict[str, Any]) -> dict[str, Any]:
    delta = round(baseline["duration_seconds"] - optimized["duration_seconds"], 3)
    relative = round((delta / baseline["duration_seconds"]) * 100, 2) if baseline["duration_seconds"] else 0.0
    return {
        "baseline_run": baseline["name"],
        "optimized_run": optimized["name"],
        "absolute_gain_seconds": delta,
        "relative_gain_percent": relative,
    }


def top_phase_lines(run: dict[str, Any]) -> list[str]:
    phases = run["phase_timings"]["phases_seconds"]
    pairs = sorted(phases.items(), key=lambda item: item[1], reverse=True)[:3]
    return [f"{name}: {seconds:.3f}s" for name, seconds in pairs]


def write_summary(
    metadata: dict[str, Any],
    corpus: dict[str, Any],
    preflight: dict[str, Any],
    runs: list[dict[str, Any]],
    comparisons: dict[str, Any],
) -> None:
    baseline = runs[0]
    optimized_cold = runs[1]
    optimized_warm = runs[2]
    lines = [
        "# GraphRAG Indexing Benchmark",
        "",
        f"- Generated at: {metadata['generated_at']}",
        f"- Commit: {metadata.get('git_commit', 'unknown')}",
        f"- Runner: {metadata['runner']}",
        f"- Docker container: {metadata.get('docker_container', 'n/a')}",
        f"- Host OS: {metadata['host_os']}",
        f"- Host Python: {metadata['host_python']}",
        f"- GraphRAG: {metadata['runner_versions']['graphrag_version']}",
        f"- LiteLLM: {metadata['runner_versions']['litellm_version']}",
        "",
        "## Corpus",
        "",
        f"- Documents: {corpus['document_count']}",
        f"- Total size: {corpus['total_bytes']} bytes",
        "",
        "## Model Preflight",
        "",
        f"- Baseline chat: {preflight['baseline']['chat_model']}",
        f"- Baseline embedding: {preflight['baseline']['embedding_model']} ({preflight['baseline']['embedding_vector_size']} dims)",
        f"- Optimized chat: {preflight['optimized']['chat_model']}",
        f"- Optimized embedding: {preflight['optimized']['embedding_model']} ({preflight['optimized']['embedding_vector_size']} dims)",
        "",
        "## Runs",
        "",
        "| Run | Method | Cache | Chat model | Embedding model | Chunking | Chunks | LLM calls | Total time |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for run in runs:
        lines.append(
            "| {name} | {method} | {cache_state} | {chat_model} | {embedding_model} | "
            "{chunk} | {chunks} | {calls} | {seconds:.3f}s |".format(
                name=run["name"],
                method=run["method"],
                cache_state=run["cache_state"],
                chat_model=run["chat_model"],
                embedding_model=run["embedding_model"],
                chunk=f"{run['chunking']['size']}/{run['chunking']['overlap']}",
                chunks=run["chunks"],
                calls=run["cache_metrics"]["llm_calls_observed"],
                seconds=run["duration_seconds"],
            )
        )
    lines.extend(
        [
            "",
            "## Before/After",
            "",
            f"- Baseline cold: {baseline['duration_seconds']:.3f}s",
            f"- Optimized cold: {optimized_cold['duration_seconds']:.3f}s",
            f"- Absolute gain: {comparisons['cold']['absolute_gain_seconds']:.3f}s",
            f"- Relative gain: {comparisons['cold']['relative_gain_percent']:.2f}%",
            f"- Optimized warm: {optimized_warm['duration_seconds']:.3f}s",
            f"- Warm vs optimized cold gain: {comparisons['warm']['absolute_gain_seconds']:.3f}s ({comparisons['warm']['relative_gain_percent']:.2f}%)",
            "",
            "## Hot Phases",
            "",
            f"- {baseline['name']}: {', '.join(top_phase_lines(baseline))}",
            f"- {optimized_cold['name']}: {', '.join(top_phase_lines(optimized_cold))}",
            f"- {optimized_warm['name']}: {', '.join(top_phase_lines(optimized_warm))}",
            "",
            "## Observations",
            "",
            "- Cold runs were executed with GraphRAG cache enabled but empty; warm means the optimized cache was preserved while output artifacts were rebuilt.",
            "- The optimized profile stays on `standard` by default, so the main tradeoff is model size plus larger chunks rather than the noisier `fast` graph extraction path.",
            f"- Baseline quality note: {baseline['quality_note']}",
            f"- Optimized quality note: {optimized_cold['quality_note']}",
            "- Scaleway cache metrics exposed token counts and call volumes, but cost stayed at `0.0` in provider metrics, so no monetary estimate could be derived reliably.",
            "",
            "## Recommendations",
            "",
            "- Default to the optimized profile for local and CI indexing when standard GraphRAG quality is still required.",
            "- Keep the warm-cache path for iterative corpus relaunches; it is a separate benchmark class and should not be compared directly to first-run latency.",
            "- If you can accept lower graph fidelity on this French corpus, test `python3 scripts/benchmark_indexing.py --optimized-method fast` as a follow-up experiment.",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    runner = detect_runner(args.runner, args.container)
    ensure_directories()
    runtime_env = resolve_runtime_env(runner, args.container)
    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "runner": runner,
        "docker_container": args.container if runner == "docker" else None,
        "git_commit": git_commit_sha(),
        "host_os": platform.platform(),
        "host_python": platform.python_version(),
        "runner_versions": runner_versions(runner, args.container),
    }
    corpus = collect_corpus_stats(GRAPHRAG_DIR / "input")
    baseline_spec = RunSpec(
        name="baseline_cold",
        settings_file="settings.baseline.yaml",
        method=args.baseline_method,
        cache_state="cold",
        chat_model=runtime_env["SCW_BASELINE_CHAT_MODEL"],
        embedding_model=runtime_env["SCW_BASELINE_EMBEDDING_MODEL"],
        quality_note="Reference run with standard indexing, baseline chunking, and the baseline chat/embedding models.",
        clear_cache=True,
    )
    optimized_quality_note = (
        "Standard indexing kept, but chat model, embedding model, and chunking were tuned for speed."
        if args.optimized_method == "standard"
        else "Fast indexing reduces LLM work further, but graph fidelity is expected to drop on this French corpus."
    )
    optimized_cold_spec = RunSpec(
        name="optimized_cold",
        settings_file="settings.optimized.yaml",
        method=args.optimized_method,
        cache_state="cold",
        chat_model=runtime_env["SCW_OPTIMIZED_CHAT_MODEL"],
        embedding_model=runtime_env["SCW_OPTIMIZED_EMBEDDING_MODEL"],
        quality_note=optimized_quality_note,
        clear_cache=True,
    )
    optimized_warm_spec = RunSpec(
        name="optimized_warm",
        settings_file="settings.optimized.yaml",
        method=args.optimized_method,
        cache_state="warm",
        chat_model=runtime_env["SCW_OPTIMIZED_CHAT_MODEL"],
        embedding_model=runtime_env["SCW_OPTIMIZED_EMBEDDING_MODEL"],
        quality_note="Same optimized profile rerun with a preserved GraphRAG cache.",
        clear_cache=False,
        reuse_workspace=True,
    )
    preflight: dict[str, Any] = {"baseline": {}, "optimized": {}}
    if not args.skip_preflight:
        preflight["baseline"] = validate_models(
            runner,
            args.container,
            runtime_env,
            chat_model=baseline_spec.chat_model,
            embedding_model=baseline_spec.embedding_model,
        )
        preflight["optimized"] = validate_models(
            runner,
            args.container,
            runtime_env,
            chat_model=optimized_cold_spec.chat_model,
            embedding_model=optimized_cold_spec.embedding_model,
        )
    else:
        preflight["baseline"] = {
            "chat_model": baseline_spec.chat_model,
            "embedding_model": baseline_spec.embedding_model,
            "embedding_vector_size": infer_vector_size(baseline_spec.embedding_model),
            "chat_response": "skipped",
        }
        preflight["optimized"] = {
            "chat_model": optimized_cold_spec.chat_model,
            "embedding_model": optimized_cold_spec.embedding_model,
            "embedding_vector_size": infer_vector_size(optimized_cold_spec.embedding_model),
            "chat_response": "skipped",
        }
    timestamp_label = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifact_root = ARTIFACTS_DIR / timestamp_label
    artifact_root.mkdir(parents=True, exist_ok=True)
    baseline_workspace = prepare_workspace(f"{timestamp_label}-{baseline_spec.name}", baseline_spec.settings_file)
    optimized_workspace = prepare_workspace(f"{timestamp_label}-{optimized_cold_spec.name}", optimized_cold_spec.settings_file)
    runs = [
        execute_run(runner, args.container, runtime_env, baseline_spec, baseline_workspace, artifact_root),
        execute_run(runner, args.container, runtime_env, optimized_cold_spec, optimized_workspace, artifact_root),
        execute_run(runner, args.container, runtime_env, optimized_warm_spec, optimized_workspace, artifact_root),
    ]
    comparisons = {
        "cold": comparison_payload(runs[0], runs[1]),
        "warm": comparison_payload(runs[1], runs[2]),
    }
    results = {
        "metadata": metadata,
        "corpus": corpus,
        "preflight": preflight,
        "runs": runs,
        "comparisons": comparisons,
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_summary(metadata, corpus, preflight, runs, comparisons)
    print(json.dumps(comparisons, indent=2))
    print(f"Wrote {RESULTS_PATH.relative_to(ROOT_DIR)} and {SUMMARY_PATH.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
