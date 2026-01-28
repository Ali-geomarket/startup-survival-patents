import argparse
import os
import pandas as pd

from src.matching.name_matching import match_companies


def main():
    parser = argparse.ArgumentParser(description="Matching startups FrenchCleantech avec entreprises INPI (fichier local)")
    parser.add_argument("--startups", required=True, help="CSV startups (companies)")
    parser.add_argument("--inpi", required=True, help="CSV INPI (entreprises déposantes / candidates)")
    parser.add_argument("--startup-col", default="startup_name", help="Colonne nom startup")
    parser.add_argument("--inpi-col", default="company_name", help="Colonne nom entreprise INPI")
    parser.add_argument("--score-cutoff", type=int, default=90, help="Seuil minimal de matching (0-100)")
    parser.add_argument("--out", required=True, help="CSV sortie matching")
    args = parser.parse_args()

    df_startups = pd.read_csv(args.startups)
    df_inpi = pd.read_csv(args.inpi)

    # matching
    df_matched = match_companies(
        df_left=df_startups,
        left_col=args.startup_col,
        df_right=df_inpi,
        right_col=args.inpi_col,
        score_cutoff=args.score_cutoff
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df_matched.to_csv(args.out, index=False, encoding="utf-8-sig")

    # petit résumé
    n_total = len(df_matched)
    n_matched = df_matched["match_name"].notna().sum()
    print(f"Terminé Matchés: {n_matched}/{n_total} ({n_matched/n_total:.1%})")
    print(f"Sortie: {args.out}")


if __name__ == "__main__":
    main()
