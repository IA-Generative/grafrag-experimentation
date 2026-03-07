"""Compatibility wrapper for tooling expecting graphrag_pipeline.py at repo root."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

PIPELINE_FILE = Path(__file__).resolve().parent / "pipelines" / "graphrag_pipeline.py"
SPEC = spec_from_file_location("repo_pipelines_graphrag_pipeline", PIPELINE_FILE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load pipeline module from {PIPELINE_FILE}")

MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Pipeline = MODULE.Pipeline
