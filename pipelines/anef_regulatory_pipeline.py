import json
import os
import re
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, Field

ARTICLE_CITATION_RE = re.compile(r"Article\s+([LRD])\.\s?(\d+(?:-\d+)*)", re.IGNORECASE)


class Pipeline:
    class Valves(BaseModel):
        anef_api_base: str = Field(
            default=os.getenv("ANEF_API_BASE", "http://host.docker.internal:8000")
        )
        anef_public_base: str = Field(
            default=os.getenv("ANEF_PUBLIC_BASE", "http://localhost:8000")
        )
        timeout_seconds: int = Field(default=60)
        title_search_limit: int = Field(default=5)
        legal_result_limit: int = Field(default=3)

    def __init__(self) -> None:
        self.type = "manifold"
        self.id = "anef-regulatory"
        self.name = "ANEF Regulatory "
        self.valves = self.Valves()

    async def on_startup(self) -> None:
        return None

    async def on_shutdown(self) -> None:
        return None

    def pipelines(self) -> list[dict[str, str]]:
        return [
            {"id": "assistant", "name": "Assistant"},
            {"id": "legal", "name": "Legal"},
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
        question = (user_message or self._extract_question(body or {}, messages)).strip()
        if not question:
            return "Le pipeline ANEF n'a recu aucune question utilisateur."

        if self._looks_like_follow_up_prompt(question):
            return self._follow_up_response(question)

        model_name = str(model_id or (body or {}).get("model") or "assistant").lower()
        if model_name.endswith(".legal") or model_name.endswith("legal"):
            return self._run_legal(question)
        return self._run_assistant(question)

    def _run_assistant(self, question: str) -> str:
        if self._looks_legal_only(question):
            return self._run_legal(question)

        title_query = self._derive_title_query(question)
        title_search = self._api_post(
            "/search-title",
            {"query": title_query, "limit": self.valves.title_search_limit},
        )
        title_candidates = title_search.get("items", [])
        title = title_candidates[0] if title_candidates else None
        if not title or float(title.get("score", 0.0)) < 0.55:
            legal_fallback = self._safe_legal_search(question)
            suggestions = self._format_title_suggestions(title_candidates)
            if legal_fallback:
                return f"{suggestions}\n\n{legal_fallback}"
            return suggestions

        title_label = title.get("full_label") or title.get("label")
        stage = self._infer_stage(question)
        channel = self._infer_channel(question)
        territory = self._infer_territory(question)

        if self._looks_like_faq(question):
            faq = self._api_post(
                "/generate-faq",
                {"title_label": title_label, "stage": stage, "limit": 5},
            )
            return self._format_faq(title_candidates, faq)

        if self._looks_like_reflex(question):
            reflex = self._api_post(
                "/generate-reflex-sheet",
                {"title_label": title_label},
            )
            return self._format_reflex(title_candidates, reflex)

        if self._looks_like_conditions(question):
            explanation = self._api_post(
                "/explain-conditions",
                {
                    "title_label": title_label,
                    "stage": stage,
                    "channel": channel,
                    "territory": territory,
                    "facts": self._infer_facts(question),
                },
            )
            return self._format_conditions(title_candidates, explanation)

        eligibility = self._api_post(
            "/eligibility-check",
            {
                "title_label": title_label,
                "stage": stage,
                "channel": channel,
                "territory": territory,
                "facts": self._infer_facts(question),
            },
        )
        legal = self._api_post(
            "/legal-search",
            {"query": question, "limit": self.valves.legal_result_limit},
        )
        return self._format_eligibility(title_candidates, eligibility, legal)

    def _run_legal(self, question: str) -> str:
        legal = self._api_post("/legal-search", self._legal_payload(question))
        if not legal.get("items"):
            legal = self._api_post(
                "/legal-search",
                {"query": question, "limit": self.valves.legal_result_limit},
            )
        return self._format_legal(legal)

    def _api_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_url = f"{self.valves.anef_api_base.rstrip('/')}{path}"
        http_request = urllib_request.Request(
            request_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(
                http_request, timeout=self.valves.timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as error:
            body = error.read().decode("utf-8", errors="ignore")
            return {
                "error": (
                    f"ANEF API error on {path}: HTTP {error.code}: {body[:400]}"
                )
            }
        except Exception as error:
            return {"error": f"ANEF API error on {path}: {error}"}

    def _safe_legal_search(self, question: str) -> str:
        legal = self._api_post("/legal-search", self._legal_payload(question))
        if legal.get("error") or not legal.get("items"):
            return ""
        return self._format_legal(legal)

    def _format_title_suggestions(self, title_candidates: list[dict[str, Any]]) -> str:
        if not title_candidates:
            return (
                "Je n'ai pas trouve de titre suffisamment fiable dans la base ANEF. "
                "Precisez le titre ou le motif de sejour."
            )
        lines = [
            "Je n'ai pas trouve de titre suffisamment fiable. Candidats proches :"
        ]
        for item in title_candidates[:5]:
            lines.append(
                f"- {item.get('full_label')} (score {float(item.get('score', 0.0)):.2f})"
            )
        return "\n".join(lines)

    def _public_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return f"{self.valves.anef_public_base.rstrip('/')}{path}"

    def _markdown_link(self, label: str, path: str | None) -> str:
        href = self._public_url(path)
        if not href:
            return label
        return f"[{label}]({href})"

    def _viewer_path_from_citation(self, citation: str | None) -> str | None:
        if not citation:
            return None
        match = ARTICLE_CITATION_RE.search(citation)
        if not match:
            return None
        article_id = f"{match.group(1).upper()}{match.group(2)}"
        return f"/legal/articles/{article_id}/view"

    def _display_article_id(self, article_id: str) -> str:
        cleaned = str(article_id or "").strip().replace(" ", "").replace(".", "").upper()
        if len(cleaned) < 2:
            return str(article_id)
        return f"{cleaned[0]}. {cleaned[1:]}"

    def _format_citation_link(self, citation: str | None) -> str:
        if not citation:
            return ""
        return self._markdown_link(citation, self._viewer_path_from_citation(citation))

    def _format_citation_links(self, citations: list[str]) -> str:
        rendered = [self._format_citation_link(citation) for citation in citations if citation]
        return ", ".join(item for item in rendered if item)

    def _format_reference_links(self, item: dict[str, Any]) -> str:
        reference_links = item.get("reference_links") or []
        if reference_links:
            rendered = [
                self._markdown_link(str(link.get("citation")), link.get("viewer_path"))
                for link in reference_links
                if link.get("citation")
            ]
            return ", ".join(rendered)
        rendered = [
            self._markdown_link(
                f"Article {self._display_article_id(str(reference))}",
                f"/legal/articles/{reference}/view",
            )
            for reference in (item.get("references") or [])
        ]
        return ", ".join(rendered)

    def _format_eligibility(
        self,
        title_candidates: list[dict[str, Any]],
        eligibility: dict[str, Any],
        legal: dict[str, Any],
    ) -> str:
        if eligibility.get("error"):
            return eligibility["error"]

        decisions = eligibility.get("decisions", [])
        grouped = {
            "pieces_communes": [],
            "pieces_specifiques": [],
            "pieces_conditionnelles": [],
        }
        for item in decisions:
            if item.get("rule_kind") == "exemption":
                continue
            grouped.setdefault(item.get("category", "pieces_specifiques"), []).append(item)

        sections = [
            f"Titre retenu : {eligibility.get('title_label', 'inconnu')}",
            f"Confiance : {eligibility.get('confidence', 'n/a')}",
        ]
        for key, label in (
            ("pieces_communes", "Pieces communes"),
            ("pieces_specifiques", "Pieces specifiques"),
            ("pieces_conditionnelles", "Pieces conditionnelles"),
        ):
            items = grouped.get(key) or []
            if not items:
                continue
            lines = [label + " :"]
            for item in items:
                citations = self._format_citation_links(item.get("legal_citations") or [])
                suffix = f" [{citations}]" if citations else ""
                lines.append(f"- {item.get('document_label')}: {item.get('requirement_text')}{suffix}")
            sections.append("\n".join(lines))

        if eligibility.get("vigilance"):
            sections.append(
                "Points de vigilance :\n"
                + "\n".join(f"- {item}" for item in eligibility["vigilance"])
            )
        if eligibility.get("uncovered_cases"):
            sections.append(
                "Cas non couverts :\n"
                + "\n".join(f"- {item}" for item in eligibility["uncovered_cases"])
            )
        if eligibility.get("manual_review_required"):
            sections.append("Revue humaine : requise")
        if eligibility.get("legal_basis"):
            sections.append(
                "Base legale :\n"
                + "\n".join(
                    f"- {self._format_citation_link(item)}" if self._format_citation_link(item) else f"- {item}"
                    for item in eligibility["legal_basis"]
                )
            )
        if legal.get("items"):
            sections.append(self._format_legal(legal, heading="Extraits juridiques"))

        alternatives = [
            item.get("full_label")
            for item in title_candidates[1:4]
            if item.get("full_label")
        ]
        if alternatives:
            sections.append("Autres titres proches :\n" + "\n".join(f"- {item}" for item in alternatives))

        return "\n\n".join(section for section in sections if section)

    def _format_legal(self, legal: dict[str, Any], heading: str = "Recherche juridique") -> str:
        if legal.get("error"):
            return legal["error"]
        items = legal.get("items") or []
        if not items:
            return "Aucun extrait juridique pertinent n'a ete trouve."
        lines = [heading + " :"]
        for item in items:
            text = " ".join(str(item.get("text") or "").split())[:500]
            citation = self._markdown_link(
                str(item.get("citation") or "Article"),
                item.get("viewer_path") or item.get("article_viewer_path") or self._viewer_path_from_citation(item.get("citation")),
            )
            refs = self._format_reference_links(item)
            ref_suffix = f" | references: {refs}" if refs else ""
            lines.append(f"- {citation}: {text}{ref_suffix}")
        return "\n".join(lines)

    def _format_faq(
        self,
        title_candidates: list[dict[str, Any]],
        faq: dict[str, Any],
    ) -> str:
        if faq.get("error"):
            return faq["error"]
        sections = [f"FAQ pour : {faq.get('title_label', 'inconnu')}"]
        for item in faq.get("items", []):
            citations = self._format_citation_links(item.get("citations") or [])
            suffix = f"\nSources : {citations}" if citations else ""
            sections.append(f"Q: {item.get('question')}\nR: {item.get('answer')}{suffix}")
        if title_candidates[1:3]:
            sections.append(
                "Titres alternatifs proches :\n"
                + "\n".join(f"- {item.get('full_label')}" for item in title_candidates[1:3])
            )
        return "\n\n".join(sections)

    def _format_reflex(
        self,
        title_candidates: list[dict[str, Any]],
        reflex: dict[str, Any],
    ) -> str:
        if reflex.get("error"):
            return reflex["error"]
        sections = [f"Fiche reflexe : {reflex.get('title_label', 'inconnu')}"]
        for section in reflex.get("sections", []):
            items = section.get("items") or []
            if items:
                sections.append(
                    f"{section.get('heading')} :\n" + "\n".join(f"- {item}" for item in items)
                )
        if reflex.get("citations"):
            sections.append(
                "Sources :\n"
                + "\n".join(
                    f"- {self._format_citation_link(item)}" if self._format_citation_link(item) else f"- {item}"
                    for item in reflex["citations"]
                )
            )
        if reflex.get("manual_review_required"):
            sections.append("Revue humaine : requise")
        if title_candidates[1:3]:
            sections.append(
                "Titres alternatifs proches :\n"
                + "\n".join(f"- {item.get('full_label')}" for item in title_candidates[1:3])
            )
        return "\n\n".join(sections)

    def _format_conditions(
        self,
        title_candidates: list[dict[str, Any]],
        explanation: dict[str, Any],
    ) -> str:
        if explanation.get("error"):
            return explanation["error"]
        sections = [f"Conditions pour : {explanation.get('title_label', 'inconnu')}"]
        items = explanation.get("items") or []
        if not items:
            sections.append("Aucune condition explicite n'a ete trouvee.")
        else:
            lines = []
            for item in items[:20]:
                state = "satisfaite" if item.get("satisfied") else "non satisfaite"
                lines.append(
                    f"- {item.get('condition')} -> {state} (ligne source {item.get('source_row')})"
                )
            sections.append("\n".join(lines))
        if explanation.get("assumptions"):
            sections.append(
                "Hypotheses :\n"
                + "\n".join(f"- {item}" for item in explanation["assumptions"])
            )
        if title_candidates[1:3]:
            sections.append(
                "Titres alternatifs proches :\n"
                + "\n".join(f"- {item.get('full_label')}" for item in title_candidates[1:3])
            )
        return "\n\n".join(sections)

    def _looks_like_faq(self, question: str) -> bool:
        lowered = question.lower()
        return "faq" in lowered or "difference entre" in lowered or "différence entre" in lowered

    def _looks_like_reflex(self, question: str) -> bool:
        lowered = question.lower()
        return "fiche reflexe" in lowered or "fiche réflexe" in lowered or "reflexe agent" in lowered

    def _looks_like_conditions(self, question: str) -> bool:
        lowered = question.lower()
        return "condition" in lowered or "explique" in lowered or "pourquoi" in lowered

    def _looks_legal_only(self, question: str) -> bool:
        lowered = question.lower()
        legal_markers = ["article", "base legale", "base légale", "ceseda", "teleservice", "téléservice"]
        title_markers = ["titre", "renouvellement", "premiere demande", "première demande", "salari", "travailleur", "talent", "etudiant", "étudiant"]
        return any(marker in lowered for marker in legal_markers) and not any(
            marker in lowered for marker in title_markers
        )

    def _infer_stage(self, question: str) -> str:
        lowered = question.lower()
        if "changement de statut" in lowered:
            return "renewal_change_status"
        if "renouvellement" in lowered:
            return "renewal"
        if "premiere demande" in lowered or "première demande" in lowered or "1ere demande" in lowered:
            return "first_application"
        return "all"

    def _infer_channel(self, question: str) -> str | None:
        lowered = question.lower()
        if "teleservice" in lowered or "téléservice" in lowered or "depot en ligne" in lowered:
            return "teleservice"
        if "guichet" in lowered or "prefecture" in lowered or "préfecture" in lowered:
            return "guichet"
        return None

    def _infer_territory(self, question: str) -> str | None:
        lowered = question.lower()
        if "mayotte" in lowered:
            return "mayotte"
        if "metropole" in lowered or "métropole" in lowered or "hexagone" in lowered:
            return "metropole"
        return None

    def _infer_facts(self, question: str) -> dict[str, str]:
        facts: dict[str, str] = {}
        if "mayotte" in question.lower():
            facts["special_case"] = "mayotte"
        return facts

    def _legal_payload(self, question: str) -> dict[str, Any]:
        lowered = question.lower()
        if (
            "teleservice" in lowered
            or "téléservice" in lowered
            or "depot en ligne" in lowered
            or "dépôt en ligne" in lowered
        ):
            return {
                "query": question,
                "limit": self.valves.legal_result_limit,
                "article_id": "R431-2",
            }
        return {"query": question, "limit": self.valves.legal_result_limit}

    def _derive_title_query(self, question: str) -> str:
        lowered = question.lower()
        mapping = [
            ("travailleur temporaire", "travailleur temporaire"),
            ("vie privee et familiale", "vie privee et familiale"),
            ("vie privée et familiale", "vie privée et familiale"),
            ("salarie detache", "salarié détaché"),
            ("salarié détaché", "salarié détaché"),
            ("salarie", "salarié"),
            ("salarié", "salarié"),
            ("etudiant", "étudiant"),
            ("étudiant", "étudiant"),
            ("entrepreneur", "entrepreneur"),
            ("profession liberale", "profession libérale"),
            ("profession libérale", "profession libérale"),
            ("passeport talent", "talent"),
            ("talent", "talent"),
            ("chercheur", "chercheur"),
            ("carte bleue", "carte bleue européenne"),
            ("medicale", "profession médicale"),
            ("pharmacie", "profession médicale"),
        ]
        for marker, query in mapping:
            if marker in lowered:
                return query

        match = re.search(
            r"titre(?:\s+de\s+sejour)?\s+([a-zA-Zàâçéèêëîïôùûüÿæœ' -]{3,80})",
            question,
            flags=re.IGNORECASE,
        )
        if match:
            candidate = match.group(1)
            candidate = re.sub(
                r"\b(premiere demande|première demande|renouvellement|changement de statut|tele-?service|teleservice|téléservice|pieces?|conditions?|depot|dépôt|en ligne|guichet|mayotte|metropole|métropole)\b",
                " ",
                candidate,
                flags=re.IGNORECASE,
            )
            candidate = " ".join(candidate.split())
            if candidate:
                return candidate

        return question

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

    def _looks_like_follow_up_prompt(self, question: str) -> bool:
        lowered = question.lower()
        return (
            "### task:" in lowered
            and "follow-up" in lowered
            and "<chat_history>" in lowered
            and "json" in lowered
        )

    def _follow_up_response(self, question: str) -> str:
        del question
        return json.dumps(
            [
                "Quelles pieces sont requises pour une premiere demande ?",
                "Quelle est la base legale exacte de cette reponse ?",
                "Quels cas imposent une revue humaine ?",
            ],
            ensure_ascii=False,
        )
