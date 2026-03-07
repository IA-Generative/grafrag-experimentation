import json
import os
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, Field


DEFAULT_MODELS = (
    {
        "id": "gpt-oss-120b",
        "name": "GPT-OSS 120B",
        "description": "Modele generaliste puissant pour raisonnement et taches complexes.",
    },
    {
        "id": "llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B Instruct",
        "description": "Generaliste multilingue robuste pour conversation et analyse.",
    },
    {
        "id": "mistral-small-3.2-24b-instruct-2506",
        "name": "Mistral Small 3.2 24B",
        "description": "Bon equilibre latence/qualite pour usage quotidien.",
    },
    {
        "id": "qwen3-235b-a22b-instruct-2507",
        "name": "Qwen3 235B A22B",
        "description": "Grand contexte et bonnes performances generalistes multilingues.",
    },
)


class Pipeline:
    class Valves(BaseModel):
        api_base: str = Field(
            default="https://api.scaleway.ai/a9158aac-8404-46ea-8bf5-1ca048cd6ab4/v1"
        )
        api_key: str = Field(default="")
        timeout_seconds: int = Field(default=75)
        default_temperature: float = Field(default=0.3)
        models_json: str = Field(default="")

    def __init__(self) -> None:
        self.type = "manifold"
        self.id = "scaleway-general"
        self.name = "Scaleway General "
        self.valves = self.Valves(
            api_base=os.getenv("SCW_LLM_BASE_URL", ""),
            api_key=os.getenv("SCW_SECRET_KEY_LLM", ""),
            models_json=os.getenv("SCW_GENERAL_MODELS_JSON", ""),
        )

    async def on_startup(self) -> None:
        return None

    async def on_shutdown(self) -> None:
        return None

    def pipelines(self) -> list[dict[str, str]]:
        return [
            {"id": model["id"], "name": model["name"]}
            for model in self._models()
        ]

    def pipe(
        self,
        user_message: str | None = None,
        model_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        body: dict[str, Any] | None = None,
        user: dict[str, Any] | None = None,
        **_: Any,
    ) -> str:
        del user
        if not self.valves.api_key.strip():
            return (
                "Le pipeline Scaleway General n'est pas configure : "
                "SCW_SECRET_KEY_LLM est absent."
            )

        target_model = self._resolve_model_id(model_id, body or {})
        payload_messages = self._extract_messages(messages, body or {}, user_message)
        if not payload_messages:
            return "Le pipeline n'a recu aucun message exploitable."

        payload = {
            "model": target_model,
            "messages": payload_messages,
            "stream": False,
            "temperature": self._temperature_from_body(body or {}),
        }

        request_url = self._chat_completions_url()
        http_request = urllib_request.Request(
            request_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.valves.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(
                http_request, timeout=self.valves.timeout_seconds
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="ignore")
            return (
                "La requete vers Scaleway a echoue "
                f"(HTTP {error.code}) : {error_body[:400]}"
            )
        except Exception as error:
            return f"La requete vers Scaleway a echoue : {error}"

        choices = data.get("choices") or []
        if not choices:
            return "Le provider n'a renvoye aucun choix exploitable."

        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip() or "Le provider a renvoye une reponse vide."
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            merged = "\n".join(part for part in text_parts if part).strip()
            return merged or "Le provider a renvoye une reponse vide."
        return "Le provider a renvoye un format de reponse non pris en charge."

    def _models(self) -> list[dict[str, str]]:
        raw = self.valves.models_json.strip()
        if not raw:
            return list(DEFAULT_MODELS)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
                return [
                    {
                        "id": str(item.get("id", "")).strip(),
                        "name": str(item.get("name") or item.get("id") or "").strip(),
                        "description": str(item.get("description") or "").strip(),
                    }
                    for item in parsed
                    if str(item.get("id", "")).strip()
                ] or list(DEFAULT_MODELS)
        except Exception:
            return list(DEFAULT_MODELS)
        return list(DEFAULT_MODELS)

    def _resolve_model_id(self, model_id: str | None, body: dict[str, Any]) -> str:
        requested = str(model_id or body.get("model") or "").strip().lower()
        for model in self._models():
            if requested.endswith(model["id"].lower()):
                return model["id"]
        return self._models()[0]["id"]

    def _extract_messages(
        self,
        messages: list[dict[str, Any]] | None,
        body: dict[str, Any],
        user_message: str | None,
    ) -> list[dict[str, str]]:
        candidate_messages = messages or body.get("messages") or []
        normalized: list[dict[str, str]] = []
        for message in candidate_messages:
            role = str(message.get("role") or "user").strip() or "user"
            content = message.get("content", "")
            text = self._content_to_text(content)
            if text:
                normalized.append({"role": role, "content": text})
        if normalized:
            return normalized
        fallback = (user_message or "").strip()
        if fallback:
            return [{"role": "user", "content": fallback}]
        return []

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "\n".join(part for part in text_parts if part).strip()
        return ""

    def _temperature_from_body(self, body: dict[str, Any]) -> float:
        value = body.get("temperature", self.valves.default_temperature)
        try:
            return max(0.0, min(2.0, float(value)))
        except Exception:
            return self.valves.default_temperature

    def _chat_completions_url(self) -> str:
        base = self.valves.api_base.rstrip("/") or self.Valves.model_fields["api_base"].default
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"
