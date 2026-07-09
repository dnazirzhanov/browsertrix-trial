import csv
from pathlib import Path
from urllib.parse import urlparse

# Maps domain -> priority tier, per the trial plan.
# One source of truth for priority — change it here, not in 31 places.
DOMAIN_PRIORITY = {
    "ripost.hu": 1,
    "metropol.hu": 1,
    "pestisracok.hu": 1,
    "origo.hu": 2,
    "mandiner.hu": 2,
    "magyarnemzet.hu": 2,
}

# Raw input: (url, url_type, notes). Domain + priority get computed, not typed.
RAW_SEEDS = [
    # --- Recent articles ---
    ("https://ripost.hu/nino/2026/06/fodraszuzlet-elott-verfurdovel-vegzodott-egy-vita",
     "recent_article", "Recent tabloid crime story"),
    ("https://ripost.hu/nino/2026/06/fulladt-11-eves-fiu",
     "recent_article", "Recent tabloid tragedy story"),
    ("https://metropol.hu/aktualis/2026/06/magyarorszag-legjei-hazai-rekordok",
     "recent_article", "Recent human-interest/records piece"),
    ("https://pestisracok.hu/polbeat/2026/06/ez-az-aszaly-nem-termeszeti-csapas-hanem-a-mi-alkotasunk-polbeat-piknik",
     "recent_article", "Recent opinion/commentary piece"),
    ("http://origo.hu/belpol/2026/07/kormanyszovivoi-tajekoztato-elo-kozvetites-2026-07-09",
     "recent_article", "Recent political briefing, possibly a live-blog page"),
    ("https://mandiner.hu/belfold/2026/07/magyar-peter-felszolitotta-es-csornai-charles-bronsonnak-nevezte-a-volt-koztarsasagi-elnokot",
     "recent_article", "Recent political news"),
    ("https://mandiner.hu/belfold/2026/07/haladektalan-intezkedesre-szolitotta-fel-a-greenpeace-a-tisza-kormanyt",
     "recent_article", "Recent political/environmental news"),
    ("https://magyarnemzet.hu/belfold/2026/07/sulyok-tamas-az-alaptorveny-modositasi-javaslat-szamos-elemeben-serti-a-jogallamisag-a-demokracia-es-a-hatalommegosztas-elvet",
     "recent_article", "Recent political/legal news, long headline (good edge case for a crawler)"),
    ("https://pestisracok.hu/magyar-ugar/2026/06/orban-a-matolcsy-fidesz-alatt-elindultak-az-eljarasok",
     "recent_article", "Recent political commentary"),
    ("https://pestisracok.hu/magyar-ugar/2026/06/adomanygyujtesbol-fizetnek-ki-budahazyek-a-perkoltsegeiket",
     "recent_article", "Recent political commentary"),
    ("https://pestisracok.hu/vilagugar/2026/06/iran-donald-trump-hadsereg-hormuzi-szoros",
     "recent_article", "Recent foreign affairs piece"),

    # --- Older articles ---
    ("https://ripost.hu/kulfold/2025/07/nagy-bajban-van-ursula-von-der-leyen",
     "older_article", "~1 year old, foreign politics"),
    ("https://ripost.hu/kulfold/2025/07/repulogep-motorja-olt-meg-egy-ferfit",
     "older_article", "~1 year old, foreign news"),
    ("https://ripost.hu/kulfold/2025/07/szuz-lanyokat-kinalo-iszlamista-tarskereso-indult-europaban",
     "older_article", "~1 year old, foreign news"),
    ("https://www.origo.hu/nagyvilag/2025/07/oroszorszag-azerbajdzsan-konfliktus-kaukazus-repulo",
     "older_article", "~1 year old, foreign affairs"),
    ("https://www.origo.hu/utazas/2025/07/kamalduli-remeteseg",
     "older_article", "~1 year old, travel/feature piece"),

    # --- Homepage / category pages ---
    ("https://www.origo.hu/cimke/orban-viktor",
     "homepage_category", "Tag/category listing page"),
    ("https://www.origo.hu/cimke/magyar-peter",
     "homepage_category", "Tag/category listing page"),
    ("https://metropol.hu/rovat/sport",
     "homepage_category", "Section front page"),
    ("https://metropol.hu/rovat/budapest",
     "homepage_category", "Section front page"),
    ("https://pestisracok.hu/rovat/vilagugar",
     "homepage_category", "Section front page"),

    # --- Image-heavy pages ---
    ("https://mandiner.hu/kultura/2026/05/ket-lencse-par-szegecs-es-nehany-regi-lemez-mi-sem-egyszerubb-mint-ezekbol-osszerakni-egy-jo-szemuveget",
     "image_heavy", "Feature article, likely many inline images"),
    ("https://magyarnemzet.hu/galeriak",
     "image_heavy", "Gallery index page"),
    ("https://mandiner.hu/cimke/galeria",
     "image_heavy", "Gallery tag/index page"),
    ("https://www.origo.hu/galeriak?page=1273",
     "image_heavy", "Gallery index page, has a query string (good edge case)"),
    ("https://pestisracok.hu/",
     "image_heavy", "Homepage, image-dense layout"),

    # --- Video / social embeds ---
    ("https://ripost.hu/insider/2026/06/orban-viktor-most-meg-nincsenek-migransok-remeljuk-ez-igy-is-marad",
     "video_social", "Likely embedded video/social content"),
    ("https://ripost.hu/insider/2026/06/migracios-paktum-eletbe-lep-penteken",
     "video_social", "Likely embedded video/social content"),
    ("https://mandiner.hu/belfold/2026/07/kommandosok-csaptak-le-a-drogszallitokra-pecs-hataraban-videon-a-hajmereszto-akcio",
     "video_social", "Headline confirms embedded video"),
    ("https://mandiner.hu/belfold/2026/07/az-atv-veletlenul-elcsipte-magyar-petert-egy-rovid-interjura-torokorszagban-ahol-a-miniszterelnok-azt-is-elmagyarazta-mi-tortent-kozte-es-trump-kozott-video",
     "video_social", "Headline confirms video, also a long-URL edge case"),
    ("https://magyarnemzet.hu/kulfold/2026/07/amerika-levette-sziriat-terrorlistarol",
     "video_social", "Foreign affairs, likely social/video embed"),
]


def normalize_domain(url: str) -> str:
    """Extract bare domain from a URL, stripping a leading 'www.'."""
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.")


def build_seed_records(raw_seeds):
    records = []
    for url, url_type, notes in raw_seeds:
        domain = normalize_domain(url)
        priority = DOMAIN_PRIORITY.get(domain)
        if priority is None:
            print(f"WARNING: no priority mapping for domain '{domain}' ({url})")
        records.append({
            "url": url,
            "domain": domain,
            "url_type": url_type,
            "priority": priority,
            "notes": notes,
        })
    return records


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "seed_urls"
TXT_PATH = DATA_DIR / "test_urls.txt"
CSV_PATH = DATA_DIR / "test_urls.csv"


def write_txt(seeds, path):
    with open(path, "w", encoding="utf-8") as f:
        for seed in seeds:
            f.write(seed["url"] + "\n")


def write_csv(seeds, path):
    fieldnames = ["url", "domain", "url_type", "priority", "notes"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(seeds)


if __name__ == "__main__":
    seeds = build_seed_records(RAW_SEEDS)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_txt(seeds, TXT_PATH)
    write_csv(seeds, CSV_PATH)
    print(f"Wrote {len(seeds)} URLs to {TXT_PATH.name} and {CSV_PATH.name}")