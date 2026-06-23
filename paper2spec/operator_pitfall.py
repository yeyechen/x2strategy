"""Operator-pitfall semantic retrieval for spec repair/audit.

This mirrors QSA's paper2spec-repair helper: the LLM does not decide which
pitfalls apply from prompt text alone. We split a draft spec into component
queries, build a vector index over `paper2spec/resources/operator_pitfall_index.md`, and
return only entries above a relevance threshold.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from paper2spec.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = float(os.getenv("X2STRATEGY_OPERATOR_PITFALL_THRESHOLD", "0.65"))
DEFAULT_TOP_K = int(os.getenv("X2STRATEGY_OPERATOR_PITFALL_TOP_K", "3"))


def operator_pitfall_file() -> Path:
    """Return the bundled operator-pitfall corpus path."""
    return PROJECT_ROOT / "paper2spec" / "resources" / "operator_pitfall_index.md"


def load_operator_pitfall_entries(path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Load `## operator:` chunks from the operator-pitfall corpus."""
    path = path or operator_pitfall_file()
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    chunks = re.split(r"(?m)^##\s+operator:\s*", text)
    entries: List[Dict[str, str]] = []
    for chunk in chunks[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        first_line, _, rest = chunk.partition("\n")
        operator_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", first_line.strip()).strip("_") or f"operator_{len(entries)+1}"
        entries.append({
            "operator_id": operator_id,
            "text": f"## operator: {first_line.strip()}\n{rest.strip()}",
        })
    if not entries and text.strip():
        entries.append({"operator_id": path.stem, "text": text.strip()})
    return entries


def operator_pitfall_queries_from_spec(spec_dict: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Split a draft StrategySpec-like dict into independent retrieval queries."""
    queries: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def add_query(path: str, *parts: Any) -> None:
        query = _compact_query_text(*parts)
        if len(query) < 12 or query in seen:
            return
        seen.add(query)
        queries.append((path, query))

    for idx, ind in enumerate(spec_dict.get("indicators") or []):
        if not isinstance(ind, dict):
            continue
        add_query(
            f"indicators[{idx}]:{ind.get('indicator_id') or ind.get('name') or idx}",
            ind.get("indicator_id"),
            ind.get("description"),
            ind.get("name"),
            ind.get("formula"),
            ind.get("executable_explanation"),
        )

    for idx, step in enumerate(spec_dict.get("logic_pipeline") or []):
        if not isinstance(step, dict):
            continue
        add_query(
            f"logic_pipeline[{idx}]:{step.get('step_id') or step.get('output') or idx}",
            step.get("description"),
            step.get("expression"),
            step.get("executable_explanation"),
            step.get("output"),
        )

    for metric_idx, metric in enumerate((spec_dict.get("expected_performance") or {}).get("metric_definitions") or []):
        if not isinstance(metric, dict):
            continue
        for step_idx, step in enumerate(metric.get("steps") or []):
            if not isinstance(step, dict):
                continue
            add_query(
                f"expected_performance.metric_definitions[{metric_idx}].steps[{step_idx}]",
                step.get("description"),
                step.get("expression"),
                step.get("executable_explanation"),
                step.get("output"),
            )

    for plan_idx, plan in enumerate(spec_dict.get("execution_plan") or []):
        if not isinstance(plan, dict):
            continue
        sizing = plan.get("position_sizing") or {}
        if not isinstance(sizing, dict):
            continue
        for step_idx, step in enumerate(sizing.get("steps") or []):
            if not isinstance(step, dict):
                continue
            add_query(
                f"execution_plan[{plan_idx}].position_sizing.steps[{step_idx}]",
                step.get("description"),
                step.get("expression"),
                step.get("executable_explanation"),
                step.get("output"),
            )

    return queries


def retrieve_operator_pitfalls(
    spec_dict: Dict[str, Any],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
    corpus_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve matched operator-pitfall entries via semantic similarity.

    Requires the optional `agent` dependencies (`langchain-community`,
    `sentence-transformers`, `faiss-cpu`). The LLM should consume this output;
    it should not self-select operator pitfalls without retrieval.
    """
    queries = operator_pitfall_queries_from_spec(spec_dict)
    entries = load_operator_pitfall_entries(corpus_path)
    if not queries or not entries:
        return []

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from langchain_community.vectorstores import FAISS

        embeddings = HuggingFaceEmbeddings(
            model_name=os.getenv("X2STRATEGY_OPERATOR_PITFALL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            encode_kwargs={"normalize_embeddings": True},
        )
        vectorstore = FAISS.from_texts(
            [entry["text"] for entry in entries],
            embeddings,
            metadatas=[{"operator_id": entry["operator_id"], "entry_index": idx} for idx, entry in enumerate(entries)],
        )
    except Exception as exc:
        # Don't crash the run — the script-level caller writes a
        # placeholder to disk when render_operator_pitfall_matches([])
        # is invoked. We re-raise so the script's CLI shows the
        # install hint, but a wrapper (e.g. the agent's loop) can
        # catch and continue.
        raise RuntimeError(
            "Operator-pitfall semantic retrieval requires optional agent dependencies. "
            "Install with `uv sync --extra agent` or `pip install -e .[agent]`."
        ) from exc

    matched: Dict[str, Dict[str, Any]] = {}
    for query_path, query_text in queries:
        docs = vectorstore.similarity_search_with_relevance_scores(
            query_text,
            k=min(top_k, len(entries)),
        )
        for doc, score in docs:
            if score < threshold:
                continue
            operator_id = str(doc.metadata.get("operator_id") or "operator")
            previous = matched.get(operator_id)
            if previous is None or score > previous["score"]:
                matched[operator_id] = {
                    "operator_id": operator_id,
                    "score": float(score),
                    "matched_from": query_path,
                    "threshold": float(threshold),
                    "text": doc.page_content,
                }

    return sorted(matched.values(), key=lambda item: item["score"], reverse=True)


def render_operator_pitfall_matches(matches: List[Dict[str, Any]]) -> str:
    """Render retrieval matches in the same style as QSA repair prompt context.

    Returns a Markdown string. **Always non-empty** — even when zero matches
    were found above threshold, we render a header explaining what we looked
    for and what we didn't find. This way the output file is never 0 bytes
    and downstream readers (agents, humans) can tell the retrieval ran.
    """
    if not matches:
        return (
            "<!-- operator_pitfall_context: no entries above threshold -->\n"
            "<!--\n"
            "  The semantic retrieval completed without error, but no\n"
            "  operator-pitfall corpus entries scored above the configured\n"
            "  threshold. To lower the bar, set\n"
            "  X2STRATEGY_OPERATOR_PITFALL_THRESHOLD (default 0.65).\n"
            "-->\n"
        )
    chunks = []
    for item in matches:
        chunks.append(
            f"### Matched operator entry: {item['operator_id']}\n"
            f"- match_score: {item['score']:.3f}\n"
            f"- matched_from: {item['matched_from']}\n"
            f"- threshold: {item['threshold']:.3f}\n\n"
            f"{item['text']}"
        )
    return "\n\n---\n\n".join(chunks)


def _compact_query_text(*parts: Any) -> str:
    values: List[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (dict, list)):
            text = json.dumps(part, ensure_ascii=False)
        else:
            text = str(part)
        text = re.sub(r"\s+", " ", text).strip()
        if text and text.lower() not in {"none", "null"}:
            values.append(text)
    return " | ".join(values)[:4000]
