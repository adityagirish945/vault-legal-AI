"""
Query Router for Vault KB.

Classifies user queries into one of 3 intents and returns the
appropriate ChromaDB collection(s) to search.
"""

from dataclasses import dataclass

# Collection names (must match ingest.py)
COLLECTION_L1 = "vault_l1_legal"
COLLECTION_L2 = "vault_l2_services"
COLLECTION_L3 = "vault_l3_discrepancies"


@dataclass
class RouteResult:
    """Result of query routing."""
    intent: str  # "general", "vault_service", or "issue"
    collections: list[str]
    confidence: float
    reason: str


# Intent keywords — ordered by priority (issue > vault_service > general)
ISSUE_KEYWORDS = [
    "problem", "issue", "rejected", "stuck", "delayed", "delay",
    "error", "wrong", "mismatch", "complaint", "not working",
    "discrepancy", "failed", "failure", "denied", "denied",
    "corruption", "bribe", "incorrect", "missing", "lost",
    "frustrated", "confused", "help me", "what went wrong",
    "why was", "why is", "pending", "not received", "not updated",
    "dispute", "pain", "confusion", "opaque", "unclear",
]

VAULT_SERVICE_KEYWORDS = [
    "vault", "vault proptech", "vaultproptech",
    "service", "price", "pricing", "cost", "charge", "fee",
    "book", "apply", "hire", "engage", "how much",
    "vault charge", "your service", "your team",
    "i need", "i want", "can you help", "do you offer",
    "how to get", "how to apply",
    "blog", "article", "website",
]

GENERAL_KEYWORDS = [
    "what is", "what are", "how to", "how does", "explain",
    "legal", "law", "act", "section", "provision",
    "process", "procedure", "step", "steps",
    "document", "documents", "required", "checklist",
    "fee structure", "timeline", "time",
    "definition", "meaning", "difference between",
    "registration", "transfer", "khata", "e-khata",
    "bescom", "property tax", "deed", "conveyancing",
    "modt", "encumbrance", "ec", "gruha jyoti",
    "rental", "lease", "agreement", "due diligence",
    "stamp duty", "sub-registrar", "bbmp", "bda",
    "inheritance", "gift deed", "sale deed", "will",
]


def _keyword_score(query_lower: str, keywords: list[str]) -> float:
    """Calculate keyword match score for a query."""
    matches = 0
    total_weight = 0
    for kw in keywords:
        if kw in query_lower:
            # Longer keywords get more weight
            weight = len(kw.split())
            matches += weight
            total_weight += weight

    # Normalize to 0-1 range
    if matches == 0:
        return 0.0
    return min(1.0, matches / 5.0)  # cap at 5 weighted matches


def route_query(query: str) -> RouteResult:
    """
    Classify a user query and return the appropriate collections to search.

    Routing logic:
    - Issue/discrepancy queries → L2 + L3
    - Vault service queries → L2
    - General/legal queries → L1
    - Ambiguous → L1 (default, broadest knowledge)

    Args:
        query: User's natural language query.

    Returns:
        RouteResult with intent, collections, confidence, and reason.
    """
    query_lower = query.lower().strip()

    # Score each intent
    issue_score = _keyword_score(query_lower, ISSUE_KEYWORDS)
    vault_score = _keyword_score(query_lower, VAULT_SERVICE_KEYWORDS)
    general_score = _keyword_score(query_lower, GENERAL_KEYWORDS)

    # Boost issue score if question words suggest a problem
    problem_patterns = [
        "why was", "why is", "what happened", "what went wrong",
        "not getting", "not received", "was rejected",
    ]
    for pattern in problem_patterns:
        if pattern in query_lower:
            issue_score += 0.3

    # Boost vault score if explicitly mentioning Vault
    if "vault" in query_lower:
        vault_score += 0.4

    # Determine intent (priority: issue > vault > general)
    scores = {
        "issue": issue_score,
        "vault_service": vault_score,
        "general": general_score,
    }

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    # If all scores are very low, default to general
    if best_score < 0.1:
        best_intent = "general"
        best_score = 0.3  # low confidence default

    # Map intent to collections
    intent_to_collections = {
        "issue": [COLLECTION_L2, COLLECTION_L3],
        "vault_service": [COLLECTION_L2],
        "general": [COLLECTION_L1],
    }

    # Generate reason
    reasons = {
        "issue": "Query indicates a problem, discrepancy, or complaint",
        "vault_service": "Query is about Vault's services, pricing, or offerings",
        "general": "Query is a general/legal question about property services",
    }

    return RouteResult(
        intent=best_intent,
        collections=intent_to_collections[best_intent],
        confidence=min(1.0, best_score),
        reason=reasons[best_intent],
    )


if __name__ == "__main__":
    """Quick test of the router."""
    test_queries = [
        "What is Khata Transfer?",
        "How much does Vault charge for E-Khata?",
        "My E-Khata application was rejected, what should I do?",
        "What documents are needed for property registration?",
        "I need help with BESCOM name change",
        "Why is my Khata transfer stuck in pending?",
        "What is the legal process for MODT cancellation?",
        "Can Vault help with due diligence?",
        "The property tax portal shows wrong owner name",
    ]

    for q in test_queries:
        result = route_query(q)
        print(f"\nQ: {q}")
        print(f"  Intent: {result.intent} (confidence: {result.confidence:.2f})")
        print(f"  Collections: {result.collections}")
        print(f"  Reason: {result.reason}")
