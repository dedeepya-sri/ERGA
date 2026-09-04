"""
Shared tokenization/stemming, used by BOTH retrieval (embeddings.py) and
semantic assessment (nli.py) so they agree on what counts as "the same
word". Without this, TF-IDF cosine similarity and the lexical coverage
check could each have their own idea of whether "government" and
"governments" match — this module is the single source of truth for that.

Lives in its own module (rather than in nli.py, where it originated) to
avoid a circular import: embeddings.py needs it, and nli.py imports from
embeddings.py.
"""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']*")

# Standard English stop-word list (function words carry no criterion-specific
# meaning, so they're excluded from both retrieval and coverage matching).
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can",
    "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "will", "with", "would", "you", "your", "yours",
    "yourself", "yourselves", "also", "one", "two", "e.g", "i.e", "etc",
}


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def normalize_spelling(word: str) -> str:
    """British -> American normalisation for the common, low-risk cases only."""
    if word.endswith("ise") and len(word) > 4:
        return word[:-3] + "ize"
    if word.endswith("isation"):
        return word[:-7] + "ization"
    if word.endswith("our") and len(word) > 4:
        return word[:-3] + "or"
    return word


def stem(word: str) -> str:
    """Crude suffix stripping for match purposes — not a linguistic stemmer."""
    word = normalize_spelling(word)
    for suf in ("edly", "ing", "ies", "ied", "ed", "es", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            root = word[: -len(suf)]
            return root + "y" if suf in ("ies", "ied") else root
    return word


def content_words(text: str, min_len: int = 3) -> list[str]:
    """Tokenize, drop stopwords/short tokens, stem — the shared 'meaningful words' extractor."""
    return [stem(w) for w in tokenize(text) if w not in STOPWORDS and len(w) >= min_len]


def stemmed_tokenizer(text: str) -> list[str]:
    """scikit-learn-compatible tokenizer: stopwords are dropped and remaining tokens stemmed
    BEFORE sklearn generates n-grams from them, so retrieval and NLI coverage both key off
    the same normalized vocabulary."""
    return content_words(text)
