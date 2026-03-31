"""Import laws from law.go.kr OpenAPI.

Usage:
    python import_laws.py                          # Import all laws
    python import_laws.py --law-type 법률           # Import 법률 only
    python import_laws.py --law-type 대통령령       # Import 대통령령 only
    python import_laws.py --limit 10 --dry-run     # Preview first 10
    python import_laws.py --csv doc/references/법령검색목록.csv  # CSV fallback
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

import yaml

from api_client import get_law_detail, get_law_history, search_laws
from checkpoint import get_processed_msts, mark_processed
from config import KR_DIR, LAW_API_KEY
from converter import (
    format_date,
    get_law_path,
    law_to_markdown,
    normalize_law_name,
    parse_departments,
    reset_path_registry,
)
from git_engine import commit_law

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Commit message builder
# ---------------------------------------------------------------------------

def build_commit_msg(law_name: str, law_type: str, mst: str, meta: dict) -> str:
    """Build a rich commit message with law.go.kr URLs and metadata."""
    normalized = normalize_law_name(law_name)
    name_compact = normalized.replace(" ", "")

    departments = meta.get("소관부처명", "")
    if isinstance(departments, list):
        departments = ", ".join(departments)
    departments = departments or "미상"

    prom_date = format_date(meta.get("공포일자", ""))
    prom_num = meta.get("공포번호", "")
    prom_raw = meta.get("공포일자", "").replace("-", "")
    field = meta.get("법령분야", "") or meta.get("법령분야명", "") or "미분류"
    amendment = meta.get("제개정구분", "") or meta.get("제개정구분명", "")
    reason = meta.get("제개정이유", "")

    # Title
    title = f"{law_type}: {normalized}"
    if amendment:
        title += f" ({amendment})"

    # URLs
    url_law = f"https://www.law.go.kr/법령/{name_compact}"
    url_revision = (
        f"https://www.law.go.kr/법령/제개정문/{name_compact}/({prom_num},{prom_raw})"
        if prom_num else ""
    )
    url_diff = f"https://www.law.go.kr/법령/신구법비교/{name_compact}"

    lines = [title, ""]
    lines.append(f"법령 전문: {url_law}")
    if url_revision:
        lines.append(f"제개정문: {url_revision}")
    lines.append(f"신구법비교: {url_diff}")

    lines.append("")
    lines.append(f"공포일자: {prom_date} | 공포번호: {prom_num}")
    lines.append(f"소관부처: {departments}")
    lines.append(f"법령분야: {field}")
    lines.append(f"법령MST: {mst}")

    if reason:
        lines.extend(["", "## 제개정이유", "", reason])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API-based import
# ---------------------------------------------------------------------------

def fetch_all_laws() -> list[dict]:
    """Fetch all law entries via search API (metadata only)."""
    all_laws = []
    page = 1

    while True:
        result = search_laws(query="", page=page, display=100)
        all_laws.extend(result["laws"])
        total = result["totalCnt"]
        logger.info(f"Search page {page}: {len(all_laws)}/{total}")

        if page * 100 >= total:
            break
        page += 1

    return all_laws


def import_law_with_history(
    law_name: str,
    law_type_filter: str | None = None,
    dry_run: bool = False,
) -> int:
    """Import all historical versions of a single law.

    Fetches amendment history, then for each version (oldest first),
    fetches full detail, writes markdown, and commits with historical date.

    Returns count of committed versions.
    """
    logger.info(f"Fetching history for: {law_name}")
    history = get_law_history(law_name)
    if not history:
        logger.warning(f"No history found for: {law_name}")
        return 0

    logger.info(f"Found {len(history)} historical versions for {law_name}")

    processed = get_processed_msts()
    committed = 0
    errors = 0

    for i, entry in enumerate(history, 1):
        mst = entry["법령일련번호"]
        if mst in processed:
            logger.info(f"  [{i}/{len(history)}] MST {mst} already processed, skipping")
            continue

        try:
            detail = get_law_detail(mst)
            meta = detail["metadata"]
            law_type_name = meta.get("법령구분", "")

            if law_type_filter and law_type_filter != law_type_name:
                continue

            fetched_name = meta.get("법령명한글", law_name)
            file_path = get_law_path(fetched_name, law_type_name)
            abs_path = KR_DIR.parent / file_path

            # Merge history metadata into detail metadata
            meta["제개정구분"] = entry.get("제개정구분명", meta.get("제개정구분", ""))
            if not meta.get("공포번호"):
                meta["공포번호"] = entry.get("공포번호", "")

            prom_date = format_date(meta.get("공포일자", ""))
            amendment = entry.get("제개정구분명", "")

            if dry_run:
                logger.info(f"  [{i}/{len(history)}] [DRY-RUN] MST={mst} {prom_date} {amendment} -> {file_path}")
                continue

            # Write markdown (overwrites previous version — git tracks history)
            content = law_to_markdown(detail)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")

            # Commit with historical date
            commit_msg = build_commit_msg(fetched_name, law_type_name, mst, meta)
            if not prom_date or len(prom_date) != 10:
                prom_date = "2000-01-01"

            result = commit_law(file_path, commit_msg, prom_date, mst)
            if result:
                mark_processed(mst)
                committed += 1
                logger.info(f"  [{i}/{len(history)}] Committed MST={mst} {prom_date} {amendment}")

        except Exception as e:
            logger.error(f"  [{i}/{len(history)}] Failed MST {mst}: {e}")
            errors += 1

    logger.info(f"History import for {law_name}: committed={committed}, errors={errors}")
    return committed


def import_from_api(
    law_type_filter: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    """Import laws from API with full amendment history. Returns count of committed versions."""
    reset_path_registry()
    logger.info("Fetching law list from API...")
    all_laws = fetch_all_laws()
    logger.info(f"Found {len(all_laws)} laws total")

    # Deduplicate by law name (search returns current versions only)
    seen_names: set[str] = set()
    unique_laws: list[dict] = []
    for law in all_laws:
        name = law.get("법령명한글", "")
        if name and name not in seen_names:
            seen_names.add(name)
            unique_laws.append(law)

    # Sort by promulgation date (oldest first)
    unique_laws.sort(key=lambda x: x.get("공포일자", ""))

    if limit:
        unique_laws = unique_laws[:limit]

    logger.info(f"Importing history for {len(unique_laws)} unique laws")

    committed = 0
    errors = 0

    for i, search_entry in enumerate(unique_laws, 1):
        name = search_entry.get("법령명한글", "")

        try:
            count = import_law_with_history(name, law_type_filter, dry_run)
            committed += count
        except Exception as e:
            logger.error(f"Failed history import for {name}: {e}")
            errors += 1

        if i % 50 == 0:
            logger.info(f"Progress: {i}/{len(unique_laws)} laws (committed={committed}, errors={errors})")

    logger.info(f"API import done: committed={committed}, errors={errors}")
    return committed


# ---------------------------------------------------------------------------
# CSV-based import (fallback)
# ---------------------------------------------------------------------------

CSV_COLUMNS = {
    "MST": 1, "DEPT_CODE": 2, "DEPT_NAME": 3, "LAW_ID": 4, "LAW_NAME": 5,
    "PROM_DATE": 6, "PROM_NUM": 7, "ENF_DATE": 8, "TYPE_CODE": 9,
    "TYPE_NAME": 10, "FIELD_CODE": 11, "FIELD_NAME": 12,
}


def parse_csv(csv_path: Path) -> list[dict]:
    """Parse reference CSV into law metadata dicts."""
    laws = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # 총N건
        next(reader)  # column headers
        for row in reader:
            if len(row) < 13:
                continue
            c = CSV_COLUMNS
            laws.append({
                "법령MST": row[c["MST"]].strip(),
                "소관부처명": row[c["DEPT_NAME"]].strip(),
                "법령ID": row[c["LAW_ID"]].strip(),
                "법령명": row[c["LAW_NAME"]].strip(),
                "공포일자": row[c["PROM_DATE"]].strip(),
                "공포번호": row[c["PROM_NUM"]].strip(),
                "시행일자": row[c["ENF_DATE"]].strip(),
                "법령구분코드": row[c["TYPE_CODE"]].strip(),
                "법령구분명": row[c["TYPE_NAME"]].strip(),
                "법령분야명": row[c["FIELD_NAME"]].strip(),
            })
    return laws


def build_csv_markdown(law: dict) -> str:
    """Build markdown from CSV metadata (no full text)."""
    raw_name = law["법령명"]
    normalized = normalize_law_name(raw_name)
    departments = parse_departments(law["소관부처명"])

    fm = {
        "제목": normalized,
        "법령MST": int(law["법령MST"]) if law["법령MST"].isdigit() else law["법령MST"],
        "법령ID": law.get("법령ID", ""),
        "법령구분": law["법령구분명"],
        "법령구분코드": law.get("법령구분코드", ""),
        "소관부처": departments,
        "공포일자": format_date(law["공포일자"]),
        "공포번호": law.get("공포번호", ""),
        "시행일자": format_date(law.get("시행일자", "")),
        "법령분야": law.get("법령분야명", ""),
        "상태": "시행",
        "출처": f"https://www.law.go.kr/법령/{normalized.replace(' ', '')}",
    }
    if normalized != raw_name:
        fm["원본제목"] = raw_name

    yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return (
        f"---\n{yaml_str}---\n\n# {normalized}\n\n"
        f"> 본문은 추후 추가 예정입니다.\n>\n"
        f"> 법령 원문: [{normalized}]({fm['출처']})\n"
    )


def import_from_csv(
    csv_path: Path,
    law_type_filter: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> int:
    """Import from CSV fallback. Returns committed count."""
    reset_path_registry()
    laws = parse_csv(csv_path)
    logger.info(f"Loaded {len(laws)} laws from CSV")

    if law_type_filter:
        laws = [l for l in laws if l["법령구분명"] == law_type_filter]
        logger.info(f"Filtered to {len(laws)} ({law_type_filter})")

    processed = get_processed_msts()
    laws = [l for l in laws if l["법령MST"] not in processed]
    laws.sort(key=lambda x: x.get("공포일자", ""))

    if limit:
        laws = laws[:limit]

    committed = 0
    for i, law in enumerate(laws, 1):
        mst = law["법령MST"]
        name = law["법령명"]
        law_type = law["법령구분명"]

        try:
            file_path = get_law_path(name, law_type)
            abs_path = KR_DIR.parent / file_path

            if dry_run:
                logger.info(f"[DRY-RUN] {file_path}")
                continue

            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(build_csv_markdown(law), encoding="utf-8")

            commit_msg = build_commit_msg(name, law_type, mst, law)
            date = format_date(law["공포일자"])
            if not date or len(date) != 10:
                date = "2000-01-01"

            if commit_law(file_path, commit_msg, date, mst):
                mark_processed(mst)
                committed += 1
        except Exception as e:
            logger.error(f"Failed MST {mst}: {e}")

        if i % 100 == 0:
            logger.info(f"Progress: {i}/{len(laws)} (committed={committed})")

    logger.info(f"CSV import done: committed={committed}")
    return committed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import Korean laws")
    parser.add_argument("--law-type", help="Filter by 법령구분 (e.g., 법률, 대통령령)")
    parser.add_argument("--law-name", help="Import history for a single law by name (e.g., 민법)")
    parser.add_argument("--limit", type=int, help="Limit number of laws")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--csv", type=Path, help="CSV file path (fallback mode)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.csv:
        committed = import_from_csv(args.csv, args.law_type, args.limit, args.dry_run)
    elif args.law_name:
        reset_path_registry()
        committed = import_law_with_history(args.law_name, args.law_type, args.dry_run)
    elif LAW_API_KEY:
        committed = import_from_api(args.law_type, args.limit, args.dry_run)
    else:
        logger.error("No API key (LAW_OC) set and no --csv provided. Cannot import.")
        sys.exit(1)

    if not args.dry_run and committed > 0:
        logger.info("Generating metadata.json...")
        from generate_metadata import save as save_metadata
        save_metadata()

    logger.info(f"Total committed: {committed}")


if __name__ == "__main__":
    main()
