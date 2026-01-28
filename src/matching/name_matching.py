import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz, process


LEGAL_FORMS = {
    "SAS", "SASU", "SARL", "SA", "SNC", "EURL", "GIE",
    "LTD", "LIMITED", "INC", "CORP", "CORPORATION",
    "BV", "GMBH", "SPA", "SRL"
}


def normalize_name(name: str) -> str:
    """Normalisation robuste pour matching."""
    if not isinstance(name, str):
        return ""
    x = name.upper()
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = re.sub(r"[^A-Z0-9]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    tokens = [t for t in x.split() if t not in LEGAL_FORMS]
    return " ".join(tokens)


def is_plausible_match(query: str, candidate: str) -> bool:
    """
    Garde-fou simple contre faux positifs :
    - au moins 2 caractères
    - au moins 1 token en commun si > 1 token
    """
    if len(query) < 2 or len(candidate) < 2:
        return False

    q_tokens = set(query.split())
    c_tokens = set(candidate.split())

    if len(q_tokens) >= 2 and len(c_tokens) >= 2:
        return len(q_tokens.intersection(c_tokens)) >= 1

    return True


@dataclass
class MatchResult:
    query_name: str
    best_match: Optional[str]
    score: Optional[float]


def match_companies(
    df_left: pd.DataFrame,
    left_col: str,
    df_right: pd.DataFrame,
    right_col: str,
    score_cutoff: int = 90
) -> pd.DataFrame:
    """
    Match de noms entre df_left[left_col] et df_right[right_col] via RapidFuzz.
    Retourne df_left + colonnes match.
    """
    left = df_left.copy()
    right = df_right.copy()

    left["_norm"] = left[left_col].apply(normalize_name)
    right["_norm"] = right[right_col].apply(normalize_name)

    # Liste des choix (côté droite)
    choices = right["_norm"].dropna().unique().tolist()

    results: List[Tuple[Optional[str], Optional[float]]] = []

    for q in left["_norm"].tolist():
        if not q:
            results.append((None, None))
            continue

        best = process.extractOne(
            q,
            choices,
            scorer=fuzz.token_set_ratio,
            score_cutoff=score_cutoff
        )

        if best is None:
            results.append((None, None))
            continue

        candidate_norm, score, _ = best

        if not is_plausible_match(q, candidate_norm):
            results.append((None, None))
            continue

        results.append((candidate_norm, float(score)))

    left["match_norm"] = [r[0] for r in results]
    left["match_score"] = [r[1] for r in results]

    # récupérer la valeur originale côté droite (pas normalisée)
    # on prend la première occurrence
    norm_to_original = (
        right.dropna(subset=["_norm"])
             .drop_duplicates("_norm")
             .set_index("_norm")[right_col]
             .to_dict()
    )
    left["match_name"] = left["match_norm"].map(norm_to_original)

    # nettoyage colonnes temporaires
    left.drop(columns=["_norm"], inplace=True, errors="ignore")

    return left
