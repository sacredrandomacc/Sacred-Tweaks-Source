"""Conservative, versioned username screen; every hit requires human review."""
from dataclasses import dataclass
import re
import unicodedata

POLICY_VERSION = 1
# Compact lexical checks target explicit slur spellings. Results expose only a category.
_BLOCKED = frozenset({
    'nigger', 'nigga', 'faggot', 'fag', 'kike', 'chink', 'spic', 'wetback',
    'coon', 'tranny', 'retard', 'raghead', 'towelhead', 'dyke', 'gook',
})
_LEET = str.maketrans({'0':'o', '1':'i', '!':'i', '3':'e', '4':'a', '@':'a', '5':'s', '$':'s', '7':'t'})


@dataclass(frozen=True)
class ModerationResult:
    normalized: str
    policy_version: int
    status: str
    category: str | None = None


def moderate_username(value: str) -> ModerationResult:
    normalized = unicodedata.normalize('NFKC', value).casefold()
    folded = ''.join(c for c in normalized.translate(_LEET) if c.isalnum())
    flagged = any(term in folded for term in _BLOCKED)
    return ModerationResult(normalized, POLICY_VERSION, 'pending' if flagged else 'clear',
                            'prohibited_hate_speech' if flagged else None)
