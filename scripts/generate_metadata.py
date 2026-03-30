"""Generate metadata.json index at repository root."""

import json
import logging
from pathlib import Path

import yaml

from config import KR_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

METADATA_FILE = PROJECT_ROOT / "metadata.json"
STATS_FILE = PROJECT_ROOT / "docs" / "stats.json"


def parse_frontmatter(file_path: Path) -> dict | None:
    """Extract YAML frontmatter from a Markdown file."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"Cannot read {file_path}: {e}")
        return None

    if not text.startswith("---"):
        return None

    try:
        end = text.index("---", 3)
    except ValueError:
        return None

    yaml_str = text[3:end]
    try:
        return yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML in {file_path}: {e}")
        return None


def generate() -> dict:
    """Scan all law files and generate metadata index.

    Returns dict keyed by 법령MST with metadata for each law.
    """
    metadata = {}

    for md_file in sorted(KR_DIR.rglob("*.md")):
        fm = parse_frontmatter(md_file)
        if fm is None:
            continue

        mst = str(fm.get("법령MST", ""))
        if not mst:
            logger.warning(f"No 법령MST in {md_file}")
            continue

        rel_path = str(md_file.relative_to(PROJECT_ROOT))

        metadata[mst] = {
            "path": rel_path,
            "제목": fm.get("제목", ""),
            "법령구분": fm.get("법령구분", ""),
            "법령구분코드": fm.get("법령구분코드", ""),
            "소관부처": fm.get("소관부처", []),
            "공포일자": fm.get("공포일자", ""),
            "시행일자": fm.get("시행일자", ""),
            "상태": fm.get("상태", ""),
        }

    return metadata


def build_stats(metadata: dict) -> dict:
    """Build summary statistics from metadata."""
    from collections import Counter

    type_counts = Counter(m.get("법령구분", "") for m in metadata.values())
    return {
        "total": len(metadata),
        "types": dict(type_counts),
    }


def save(metadata: dict | None = None) -> int:
    """Generate and save metadata.json and docs/stats.json. Returns count of entries."""
    if metadata is None:
        metadata = generate()

    METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    stats = build_stats(metadata)
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(f"Generated metadata.json with {len(metadata)} entries")
    logger.info(f"Generated docs/stats.json: {stats}")
    return len(metadata)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = save()
    print(f"Generated metadata.json with {count} entries")
