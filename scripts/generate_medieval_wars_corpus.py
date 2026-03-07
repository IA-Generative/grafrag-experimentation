#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

USER_AGENT = "grafrag-experimentation/0.1 (local Wikipedia corpus builder)"
DEFAULT_OUTPUT_DIR = Path("graphrag/input/wikipedia-medieval-anglo-french-wars")


@dataclass(frozen=True)
class Topic:
    title: str
    focus: str


TOPICS: tuple[Topic, ...] = (
    Topic(
        title="Guerre de Cent Ans",
        focus="Vue d'ensemble du conflit, des causes et des grandes phases militaires.",
    ),
    Topic(
        title="Philippe VI de Valois",
        focus="Point de départ dynastique du conflit et tensions avec la couronne anglaise.",
    ),
    Topic(
        title="Édouard III",
        focus="Revendiations anglaises sur le trone de France et strategie militaire initiale.",
    ),
    Topic(
        title="Bataille de Crécy",
        focus="Victoire anglaise cle, tactiques de guerre et role des archers.",
    ),
    Topic(
        title="Bataille de Poitiers (1356)",
        focus="Capture de Jean II et approfondissement de la crise francaise.",
    ),
    Topic(
        title="Traité de Brétigny",
        focus="Concessions territoriales et pause diplomatique apres les succes anglais.",
    ),
    Topic(
        title="Charles V (roi de France)",
        focus="Redressement francais, reconquete et evolution de la strategie.",
    ),
    Topic(
        title="Bataille d'Azincourt",
        focus="Retour des victoires anglaises au XVe siecle et choc militaire majeur.",
    ),
    Topic(
        title="Henri V (roi d'Angleterre)",
        focus="Consolidation politique anglaise apres Azincourt et pression sur la couronne francaise.",
    ),
    Topic(
        title="Traité de Troyes",
        focus="Accord politique majeur liant la succession francaise aux victoires anglaises.",
    ),
    Topic(
        title="Siège d'Orléans",
        focus="Moment de bascule de la guerre et remobilisation du camp francais.",
    ),
    Topic(
        title="Jeanne d'Arc",
        focus="Leadership symbolique, legitimation politique et retournement de la dynamique du conflit.",
    ),
)

TEST_QUESTIONS: tuple[str, ...] = (
    "Quelles sont les causes dynastiques et territoriales de la guerre de Cent Ans ?",
    "Pourquoi la bataille de Crecy est-elle souvent presentee comme un tournant tactique ?",
    "Quel traite suit la bataille de Poitiers de 1356 et que change-t-il pour les territoires francais ?",
    "Comment Charles V contribue-t-il au redressement francais apres les grandes defaites initiales ?",
    "Compare les objectifs et les consequences du traite de Bretigny et du traite de Troyes.",
    "Quel role joue Jeanne d'Arc dans le siege d'Orleans et dans la legitimation du camp francais ?",
    "Comment Henri V exploite-t-il la victoire d'Azincourt sur le plan militaire et politique ?",
    "Quels documents du corpus montrent que la guerre de Cent Ans n'est pas un conflit continu ?",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a French-language Wikipedia corpus about medieval wars between England "
            "and France and write it under graphrag/input."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Target directory for generated Markdown files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--lang",
        default="fr",
        help="Wikipedia language edition to query. Default: fr",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the target directory before regenerating the corpus.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.35,
        help="Delay between Wikipedia requests. Default: 0.35",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug_chars: list[str] = []
    previous_dash = False
    for char in ascii_value.lower():
        if char.isalnum():
            slug_chars.append(char)
            previous_dash = False
            continue
        if not previous_dash:
            slug_chars.append("-")
            previous_dash = True
    return "".join(slug_chars).strip("-")


def page_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def normalize_text(value: str) -> str:
    lines = [line.rstrip() for line in value.splitlines()]
    normalized_lines: list[str] = []
    previous_blank = False
    for line in lines:
        if not line.strip():
            if previous_blank:
                continue
            normalized_lines.append("")
            previous_blank = True
            continue
        normalized_lines.append(line)
        previous_blank = False
    return "\n".join(normalized_lines).strip()


def fetch_page(lang: str, title: str) -> tuple[str, str, str]:
    params = {
        "action": "query",
        "prop": "extracts|info",
        "redirects": 1,
        "inprop": "url",
        "explaintext": 1,
        "exsectionformat": "plain",
        "format": "json",
        "formatversion": 2,
        "titles": title,
    }
    request_url = f"https://{lang}.wikipedia.org/w/api.php?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Wikipedia returned HTTP {error.code} for {title}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Wikipedia for {title}: {error}") from error

    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError(f"Wikipedia did not return a page payload for {title}")

    page = pages[0]
    if page.get("missing") is True:
        raise RuntimeError(f"Wikipedia page not found: {title}")

    resolved_title = page.get("title", title)
    full_url = page.get("fullurl") or page_url(lang, resolved_title)
    extract = normalize_text(page.get("extract", ""))
    if not extract:
        raise RuntimeError(f"Wikipedia returned an empty extract for {resolved_title}")
    return resolved_title, full_url, extract


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_page(topic: Topic, resolved_title: str, source_url: str, extract: str, retrieved_at: str) -> str:
    return f"""# {resolved_title}

Source Wikipedia: {source_url}
Theme focus: {topic.focus}
Retrieved at: {retrieved_at}

## Corpus note

Ce document est inclus pour repondre a des questions de retrieval sur les guerres medievales entre l'Angleterre et la France, avec un accent sur la guerre de Cent Ans, ses causes, ses batailles, ses traites et ses figures politiques.

## Wikipedia extract

{extract}
"""


def render_overview(topics: Iterable[Topic], lang: str, output_dir: Path, retrieved_at: str) -> str:
    topic_lines = []
    for topic in topics:
        topic_lines.append(f"- {topic.title}: {topic.focus}")
    joined_topics = "\n".join(topic_lines)
    return f"""# Medieval Anglo-French Wars Wikipedia Corpus

Generated at: {retrieved_at}
Wikipedia language edition: {lang}
Output directory: {output_dir}

## Scope

Ce corpus couvre surtout la guerre de Cent Ans et ses moments structurants:
causes dynastiques, grandes campagnes, traites, reconquetes et figures politiques.

## Included pages

{joined_topics}

## Recommended test style

- Questions factuelles sur une bataille ou un traite.
- Questions de synthese reliant plusieurs documents.
- Questions comparatives entre dirigeants, batailles ou accords diplomatiques.
- Questions de chronologie pour verifier que le systeme croise bien plusieurs pages.
"""


def render_questions(questions: Iterable[str], bridge_base_url: str) -> str:
    question_lines = [f"{index}. {question}" for index, question in enumerate(questions, start=1)]
    joined_questions = "\n".join(question_lines)
    return f"""# Test Questions For The Medieval Wars Corpus

## Suggested questions

{joined_questions}

## Query example

```bash
curl -fsS -X POST {bridge_base_url}/query \\
  -H 'Content-Type: application/json' \\
  -d '{{"question":"Compare le traite de Bretigny et le traite de Troyes.","method":"global","top_k":6}}'
```
"""


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    generated_files: list[Path] = []

    overview_path = output_dir / "00-overview.md"
    write_text(
        overview_path,
        render_overview(TOPICS, args.lang, output_dir, retrieved_at),
    )
    generated_files.append(overview_path)

    for index, topic in enumerate(TOPICS, start=1):
        resolved_title, source_url, extract = fetch_page(args.lang, topic.title)
        filename = f"{index:02d}-{slugify(resolved_title)}.md"
        destination = output_dir / filename
        write_text(
            destination,
            render_page(topic, resolved_title, source_url, extract, retrieved_at),
        )
        generated_files.append(destination)
        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    questions_path = output_dir / "99-test-questions.md"
    write_text(
        questions_path,
        render_questions(TEST_QUESTIONS, "http://localhost:8081"),
    )
    generated_files.append(questions_path)

    print(f"Generated {len(generated_files)} files under {output_dir}")
    for path in generated_files:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
