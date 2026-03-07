# GraphRAG Experimentation Baseline

This repository demonstrates a realistic retrieval architecture where Open WebUI calls a pipeline, the pipeline calls a FastAPI bridge, and the bridge triggers Microsoft GraphRAG workflows when available.

The bridge is designed to keep local development productive. If GraphRAG CLI artifacts do not exist yet, it can still rank local documents and return a deterministic answer while surfacing a warning.

For Kubernetes, the same bridge image is reused by the runtime deployment and the indexing job so operational behavior stays aligned.

