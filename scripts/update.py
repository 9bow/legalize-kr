"""Incremental updater for new/amended laws.

Usage:
    python update.py                    # Update recent laws (default 7 days)
    python update.py --days 30          # Look back 30 days
    python update.py --law-type 법률    # Only 법률
    python update.py --dry-run          # Preview only
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

from api_client import get_law_detail, search_laws
from checkpoint import get_last_update, get_processed_msts, mark_processed, set_last_update
from config import KR_DIR, LAW_API_KEY
from converter import format_date, get_law_path, law_to_markdown, normalize_law_name, reset_path_registry
from git_engine import commit_law
from import_laws import build_commit_msg

logger = logging.getLogger(__name__)


def update(days: int = 7, law_type_filter: str | None = None, dry_run: bool = False) -> int:
    """Query API for recently amended laws and import them."""
    if not LAW_API_KEY:
        logger.error("No API key (LAW_OC) configured. Cannot update.")
        return 0

    reset_path_registry()

    last = get_last_update()
    since = last.replace("-", "") if last else (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    today = datetime.now().strftime("%Y%m%d")

    logger.info(f"Searching amendments from {since} to {today}")

    all_laws = []
    page = 1
    while True:
        result = search_laws(query="", page=page, display=100, date_from=since, date_to=today)
        all_laws.extend(result["laws"])
        if page * 100 >= result["totalCnt"]:
            break
        page += 1

    logger.info(f"Found {len(all_laws)} amended laws")

    processed = get_processed_msts()
    committed = 0

    for search_entry in all_laws:
        mst = search_entry["법령일련번호"]
        if mst in processed:
            continue

        try:
            detail = get_law_detail(mst)
            meta = detail["metadata"]
            law_type = meta.get("법령구분", "")

            if law_type_filter and law_type_filter != law_type:
                continue

            law_name = meta.get("법령명한글", "")
            file_path = get_law_path(law_name, law_type)
            abs_path = KR_DIR.parent / file_path

            if dry_run:
                logger.info(f"[DRY-RUN] {file_path}")
                continue

            content = law_to_markdown(detail)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")

            commit_msg = build_commit_msg(law_name, law_type, mst, meta)
            date = format_date(meta.get("공포일자", ""))
            if not date or len(date) != 10:
                date = "2000-01-01"

            if commit_law(file_path, commit_msg, date, mst):
                mark_processed(mst)
                committed += 1

        except Exception as e:
            logger.error(f"Failed MST {mst}: {e}")

    if not dry_run:
        set_last_update(format_date(today))

    return committed


def main():
    parser = argparse.ArgumentParser(description="Incremental law updater")
    parser.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    parser.add_argument("--law-type", help="Filter by 법령구분 (e.g., 법률)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    committed = update(days=args.days, law_type_filter=args.law_type, dry_run=args.dry_run)

    if not args.dry_run and committed > 0:
        from generate_metadata import save as save_metadata
        save_metadata()

    logger.info(f"Update complete: {committed} laws committed")


if __name__ == "__main__":
    main()
