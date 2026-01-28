import argparse
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}

BASE_URL = "https://www.frenchcleantech.com/"

LEGAL_FORMS = {
    "SAS", "SASU", "SARL", "SA", "SNC", "EURL", "GIE",
    "LTD", "LIMITED", "INC", "CORP", "CORPORATION",
    "BV", "GMBH", "SPA", "SRL"
}


def clean_text(x: Optional[str]) -> str:
    if not x:
        return ""
    return re.sub(r"\s+", " ", str(x)).strip()


def normalize_company_name(name: str) -> str:
    """Normalisation simple : majuscules, suppression accents, suppression formes juridiques."""
    if not isinstance(name, str):
        return ""
    x = name.upper()
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = re.sub(r"[^A-Z0-9]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    tokens = [t for t in x.split() if t not in LEGAL_FORMS]
    return " ".join(tokens)


def normalize_company_name_v2(name: str) -> str:
    """Normalisation améliorée : fusionne tokens d'1 lettre (ex: 'S TILE' -> 'STILE')."""
    if not isinstance(name, str):
        return ""
    x = name.upper()
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    x = re.sub(r"[^A-Z0-9]", " ", x)
    x = re.sub(r"\s+", " ", x).strip()

    tokens = [t for t in x.split() if t not in LEGAL_FORMS]

    merged: List[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and len(tokens[i]) == 1 and len(tokens[i + 1]) <= 4:
            merged.append(tokens[i] + tokens[i + 1])
            i += 2
        else:
            merged.append(tokens[i])
            i += 1

    return " ".join(merged)


@dataclass
class CompanyRow:
    startup_name: str
    tagline: str
    detail_url: str
    category: str
    list_page: int


class FrenchCleantechScraper:
    def __init__(
        self,
        base_url: str = BASE_URL,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        sleep_s: float = 0.6
    ):
        self.base_url = base_url
        self.headers = headers or DEFAULT_HEADERS
        self.timeout = timeout
        self.sleep_s = sleep_s
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_soup(self, url: str) -> BeautifulSoup:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    @staticmethod
    def extract_cards(soup: BeautifulSoup):
        """
        Repère les liens 'Read more' puis remonte au bloc contenant un titre (h1/h2/h3).
        Retourne une liste de tuples: (block_html, readmore_link)
        """
        read_more = soup.find_all("a", string=re.compile(r"read more", re.I))
        cards = []
        for a in read_more:
            block = a
            for _ in range(10):
                block = getattr(block, "parent", None)
                if block is None:
                    break
                title = block.find(["h1", "h2", "h3"])
                if title and clean_text(title.get_text()):
                    cards.append((block, a))
                    break
        return cards

    @staticmethod
    def extract_tagline_from_block(block, name_tag) -> str:
        """
        Essaie de récupérer la tagline (texte sous le nom).
        On se limite à quelques siblings pour éviter de prendre 'Read more'.
        """
        if not name_tag:
            return ""
        sib = name_tag.find_next_sibling()
        for _ in range(4):
            if sib is None:
                break
            t = clean_text(sib.get_text(" ", strip=True))
            if t and "read more" not in t.lower():
                return t
            sib = sib.find_next_sibling()
        return ""

    def scrape_category(self, category_slug: str, category_name: str, max_page: int) -> pd.DataFrame:
        rows: List[CompanyRow] = []

        for page in range(1, max_page + 1):
            url = (
                f"{self.base_url}companies/categories/{category_slug}.html"
                if page == 1
                else f"{self.base_url}companies/categories/{category_slug}.html?page={page}"
            )
            print(f"[FrenchCleantech] Page {page:02d}/{max_page} -> {url}")

            soup = self.get_soup(url)
            cards = self.extract_cards(soup)
            print(f"  - Cartes trouvées: {len(cards)}")

            for block, readmore_a in cards:
                name_tag = block.find(["h1", "h2", "h3"])
                startup_name = clean_text(name_tag.get_text()) if name_tag else ""
                tagline = self.extract_tagline_from_block(block, name_tag)

                detail_url = urljoin(self.base_url, readmore_a.get("href", ""))

                rows.append(CompanyRow(
                    startup_name=startup_name,
                    tagline=tagline,
                    detail_url=detail_url,
                    category=category_name,
                    list_page=page
                ))

            time.sleep(self.sleep_s)

        df = pd.DataFrame([r.__dict__ for r in rows])
        df = df.drop_duplicates(subset=["startup_name", "detail_url"]).reset_index(drop=True)

        # Nettoyage noms
        df["name_clean"] = df["startup_name"].apply(normalize_company_name)
        df["name_clean_v2"] = df["startup_name"].apply(normalize_company_name_v2)

        return df

    @staticmethod
    def deduplicate_companies(df: pd.DataFrame) -> pd.DataFrame:
        """
        1 ligne = 1 entreprise, on garde l'occurrence la plus tôt vue (page la plus petite).
        """
        df_companies = (
            df.sort_values("list_page", ascending=True)
              .drop_duplicates(subset=["name_clean_v2"])
              .reset_index(drop=True)
        ).copy()
        return df_companies


def main():
    parser = argparse.ArgumentParser(description="Scraping FrenchCleantech (par catégorie)")
    parser.add_argument("--category-slug", required=True, help="Slug catégorie (ex: energy-generation)")
    parser.add_argument("--category-name", required=True, help="Nom catégorie (ex: Energy generation)")
    parser.add_argument("--max-page", type=int, required=True, help="Nombre de pages à scraper (ex: 19)")
    parser.add_argument("--out-raw", required=True, help="Chemin de sortie CSV raw")
    parser.add_argument("--out-companies", required=True, help="Chemin de sortie CSV entreprises uniques")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out_raw), exist_ok=True)
    os.makedirs(os.path.dirname(args.out_companies), exist_ok=True)

    scraper = FrenchCleantechScraper()
    df = scraper.scrape_category(
        category_slug=args.category_slug,
        category_name=args.category_name,
        max_page=args.max_page
    )
    df_companies = scraper.deduplicate_companies(df)

    df.to_csv(args.out_raw, index=False, encoding="utf-8-sig")
    df_companies.to_csv(args.out_companies, index=False, encoding="utf-8-sig")

    print("\nTerminé")
    print(f"- Lignes (raw): {len(df)} -> {args.out_raw}")
    print(f"- Entreprises uniques: {len(df_companies)} -> {args.out_companies}")
    print(f"- Doublons restants (name_clean_v2): {df_companies['name_clean_v2'].duplicated().sum()}")


if __name__ == "__main__":
    main()
