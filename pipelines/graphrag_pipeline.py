import json
import re
from typing import Any
from urllib import request as urllib_request

from pydantic import BaseModel, Field


class Pipeline:
    class Valves(BaseModel):
        bridge_url: str = Field(default="http://bridge:8081")
        default_method: str = Field(default="local")
        timeout_seconds: int = Field(default=75)

    def __init__(self) -> None:
        self.type = "manifold"
        self.id = "graphrag-bridge"
        self.name = "GraphRAG "
        self.valves = self.Valves()

    async def on_startup(self) -> None:
        return None

    async def on_shutdown(self) -> None:
        return None

    def pipelines(self) -> list[dict[str, str]]:
        return [
            {"id": "graphrag-local", "name": "Local"},
            {"id": "graphrag-global", "name": "Global"},
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
        question = (user_message or self._extract_question(body or {}, messages)).strip()
        if not question:
            return "Le pipeline n'a reçu aucune question utilisateur."

        if self._looks_like_follow_up_prompt(question):
            return self._follow_up_response(question)

        corpus_id, normalized_question = self._extract_corpus_selector(question)
        user_context = self._extract_user_context(user or {})

        model_name = str(model_id or (body or {}).get("model", "graphrag-local")).lower()
        method = "global" if "global" in model_name else self.valves.default_method
        payload = json.dumps(
            {
                "question": normalized_question,
                "method": method,
                "corpus_id": corpus_id,
                "user_email": user_context["email"],
                "user_groups": user_context["groups"],
                "user_roles": user_context["roles"],
            }
        ).encode("utf-8")
        http_request = urllib_request.Request(
            f"{self.valves.bridge_url}/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(
                http_request, timeout=self.valves.timeout_seconds
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            return f"La requête vers le bridge GraphRAG a échoué : {error}"

        answer = data.get("answer", "Aucune réponse n'a été renvoyée par le bridge.")
        citations = data.get("citations", [])
        graph_url = data.get("graph_url")
        notices = data.get("notices", [])
        warnings = data.get("warnings", [])
        prefix_sections = []
        if notices:
            notice_lines = []
            for item in notices:
                if not isinstance(item, dict):
                    continue
                title = item.get("title", "Notification")
                message = item.get("message", "")
                link_url = item.get("link_url")
                line = f"- {title}: {message}".strip()
                if link_url:
                    line = f"{line} ({link_url})"
                notice_lines.append(line)
            if notice_lines:
                prefix_sections.append("Etat des corpus:\n" + "\n".join(notice_lines))
        if warnings:
            prefix_sections.append("Notes:\n" + "\n".join(f"- {item}" for item in warnings))
        prefix = ("\n\n".join(prefix_sections) + "\n\n") if prefix_sections else ""
        if citations:
            sources = "\n".join(
                f"- {item.get('path', 'source inconnue')}" for item in citations
            )
            graph_section = (
                f"\n\nGraphe :\n[Ouvrir le graphe interactif]({graph_url})"
                if graph_url
                else ""
            )
            return f"{prefix}{answer}\n\nSources:\n{sources}{graph_section}"
        if graph_url:
            return f"{prefix}{answer}\n\nGraphe :\n[Ouvrir le graphe interactif]({graph_url})"
        return f"{prefix}{answer}"

    def _looks_like_follow_up_prompt(self, question: str) -> bool:
        lowered = question.lower()
        return (
            "### task:" in lowered
            and "follow-up" in lowered
            and "<chat_history>" in lowered
            and "json" in lowered
        )

    def _follow_up_response(self, question: str) -> str:
        history_match = re.search(
            r"USER:\s*(.+?)(?:\nASSISTANT:|\Z)",
            question,
            flags=re.IGNORECASE | re.DOTALL,
        )
        seed = ""
        if history_match:
            seed = history_match.group(1).strip().replace("\n", " ")

        if "bretigny" in seed.lower() or "troyes" in seed.lower():
            follow_ups = [
                "Peux-tu détailler les clauses du traite de Bretigny ?",
                "Quel role joue le traite de Troyes dans la succession au trone de France ?",
                "Quelles consequences territoriales distinguent ces deux traites ?",
            ]
        elif "jeanne d'arc" in seed.lower() or "orleans" in seed.lower():
            follow_ups = [
                "Peux-tu détailler le role de Jeanne d'Arc a Orleans ?",
                "Quels evenements suivent immediatement la levee du siege d'Orleans ?",
                "Comment cette sequence modifie-t-elle la legitimite du camp francais ?",
            ]
        else:
            follow_ups = [
                "Peux-tu me donner une chronologie plus detaillee ?",
                "Quels personnages relient le plus les evenements cites ?",
                "Quelles sources du corpus soutiennent le mieux cette reponse ?",
            ]

        return json.dumps(follow_ups, ensure_ascii=False)

    def _extract_question(
        self, body: dict[str, Any], messages: list[dict[str, Any]] | None = None
    ) -> str:
        candidate_messages = messages or body.get("messages") or []
        for message in reversed(candidate_messages):
            if message.get("role") != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                text_parts = [
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                merged = "\n".join(part for part in text_parts if part).strip()
                if merged:
                    return merged
        return ""

    def _extract_corpus_selector(self, question: str) -> tuple[str | None, str]:
        match = re.match(r"^\s*\[\[\s*corpus:([A-Za-z0-9._-]+)\s*\]\]\s*(.*)$", question)
        if not match:
            return None, question
        corpus_id = match.group(1).strip()
        normalized = match.group(2).strip() or question
        return corpus_id, normalized

    def _extract_user_context(self, user: dict[str, Any]) -> dict[str, Any]:
        email = str(user.get("email") or user.get("mail") or "").strip()
        groups = user.get("groups")
        roles = user.get("roles")
        if not isinstance(groups, list):
            groups = []
        if not isinstance(roles, list):
            role_value = user.get("role")
            roles = [str(role_value)] if role_value else []
        return {
            "email": email or None,
            "groups": [str(item) for item in groups],
            "roles": [str(item) for item in roles],
        }
