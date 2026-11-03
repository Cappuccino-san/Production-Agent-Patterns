"""Deterministic offline mock LLM engine for query decomposition, grading, and synthesis."""

import re
from typing import Any, Optional


class DeterministicMockLLM:
    """Offline deterministic LLM engine providing genuine reasoning without API keys.
    
    Produces realistic query decompositions, document relevance grading,
    query reformulation, and answer synthesis with verifiable citations.
    """

    def __init__(self, forced_relevance: Optional[bool] = None):
        self.forced_relevance = forced_relevance

    def decompose_query(self, query: str) -> list[str]:
        """Decompose composite questions into atomic subqueries."""
        cleaned = query.strip()
        if not cleaned:
            return []

        # Split on conjunctions or punctuation indicating multiple questions
        conjunction_patterns = [
            r"\s+(?:and|as well as|along with)\s+",
            r"\s*;\s*",
            r"\?\s+",
        ]

        # Check if the query has compound clauses
        parts: list[str] = []
        for pat in conjunction_patterns:
            matches = re.split(pat, cleaned, flags=re.IGNORECASE)
            if len(matches) > 1:
                parts = [m.strip().rstrip("?") for m in matches if m.strip()]
                break

        if len(parts) > 1:
            subqueries = []
            for p in parts:
                p_clean = p.strip()
                if not p_clean.endswith("?"):
                    p_clean = f"{p_clean}?"
                subqueries.append(p_clean)
            return subqueries

        return [cleaned]

    def grade_relevance(
        self, query: str, documents: list[dict[str, Any]], threshold: float = 0.0
    ) -> bool:
        """Evaluate if retrieved documents contain content relevant to the query."""
        if self.forced_relevance is not None:
            return self.forced_relevance

        if not documents:
            return False

        # Extract meaningful tokens from query
        query_words = set(
            w.lower()
            for w in re.findall(r"\w+", query)
            if len(w) > 2 and w.lower() not in {"what", "how", "why", "when", "where", "the", "and", "for"}
        )

        if not query_words:
            return True

        # Check document contents and titles for exact token hits
        total_hits = 0
        for doc in documents:
            doc_text = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
            doc_words = set(re.findall(r"\w+", doc_text))
            hits = len(query_words.intersection(doc_words))
            total_hits += hits

        return total_hits > 0


    def reformulate_query(self, query: str, iteration: int) -> str:
        """Reformulate or simplify a search query to broaden retrieval scope."""
        # Strip common interrogative stop words to focus on content nouns/verbs
        stop_words = {
            "what", "is", "are", "how", "do", "does", "can", "you", "tell",
            "me", "about", "the", "a", "an", "in", "to", "of", "for", "with"
        }
        tokens = [
            w for w in re.findall(r"\w+", query)
            if w.lower() not in stop_words and len(w) > 2
        ]

        if tokens:
            # On second iteration, keep the most salient keywords
            return " ".join(tokens)
        return query.strip()

    def synthesize_answer(
        self, query: str, documents: list[dict[str, Any]]
    ) -> tuple[str, list[str]]:
        """Synthesize a factual answer grounded in retrieved documents with citations."""
        if not documents:
            return (
                f"I could not find relevant documentation in the knowledge base to answer '{query}'.",
                [],
            )

        citations: list[str] = []
        doc_summaries: list[str] = []

        for doc in documents:
            title = doc.get("title", "Untitled Document")
            citation_tag = f"[Doc: {title}]"
            if citation_tag not in citations:
                citations.append(citation_tag)

            snippet = doc.get("snippet") or doc.get("content", "")[:200]
            clean_snippet = re.sub(r"</?b>", "", snippet).strip()
            doc_summaries.append(f"- According to {citation_tag}: {clean_snippet}")

        context_body = "\n".join(doc_summaries)
        answer = (
            f"Based on the retrieved documentation regarding '{query}':\n\n"
            f"{context_body}\n\n"
            f"In summary, the knowledge base confirms the relevant concepts described above."
        )

        return answer, citations
