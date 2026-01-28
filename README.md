# Startup survival and patents

Projet tuteuré de Master visant à analyser empiriquement le lien entre la détention de brevets et la survie des start-ups françaises.

Le projet combine :
- extraction de données (web scraping),
- appariement de noms d’entreprises avec des bases de brevets,
- construction de portefeuilles de brevets,
- analyse économétrique (logit / probit).

## Exécution (scraping)

```bash
pip install -r requirements.txt
python -m src.scraping.frenchcleantech_scraper --category-slug "energy-generation" --category-name "Energy generation" --max-page 19 --out-raw "data/raw/frenchcleantech_energy_generation.csv" --out-companies "data/raw/frenchcleantech_energy_generation_companies.csv"
