"""Validate all law Markdown files for consistency.

Usage:
    python validate.py

Checks:
- Valid YAML frontmatter with required fields
- 소관부처 is a YAML list
- Unicode dot normalization consistency
- metadata.json matches file system
"""

import json
import logging
import sys
from pathlib import Path

import yaml

from config import CHILD_SUFFIXES, KR_DIR, PROJECT_ROOT
from converter import normalize_law_name

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["제목", "법령MST", "법령구분", "법령구분코드", "소관부처", "공포일자", "상태"]

METADATA_FILE = PROJECT_ROOT / "metadata.json"


def validate_frontmatter(file_path: Path) -> list[str]:
    """Validate a single law file. Returns list of error messages."""
    errors = []
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"Cannot read: {e}"]

    if not text.startswith("---"):
        return ["No YAML frontmatter"]

    try:
        end = text.index("---", 3)
    except ValueError:
        return ["Unterminated YAML frontmatter"]

    yaml_str = text[3:end]
    try:
        fm = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        return [f"Invalid YAML: {e}"]

    if not isinstance(fm, dict):
        return ["Frontmatter is not a dict"]

    for field in REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"Missing required field: {field}")

    dept = fm.get("소관부처")
    if dept is not None and not isinstance(dept, list):
        errors.append(f"소관부처 must be a YAML list, got {type(dept).__name__}")

    title = fm.get("제목", "")
    if title != normalize_law_name(title):
        errors.append(f"제목 contains un-normalized Unicode dots: {title}")

    # Cross-validate suffix-based grouping against 법령구분
    law_type = fm.get("법령구분", "")
    normalized_title = normalize_law_name(title)
    for suffix, _ in CHILD_SUFFIXES:
        if normalized_title.endswith(suffix):
            if suffix == " 시행령" and law_type not in ("대통령령", ""):
                errors.append(
                    f"이름이 '{suffix}'로 끝나지만 법령구분이 '{law_type}' "
                    f"(예상: 대통령령)"
                )
            if suffix == " 시행규칙" and law_type != "" and not law_type.endswith("총리령") and not law_type.endswith("부령") and not law_type.endswith("규칙"):
                errors.append(
                    f"이름이 '{suffix}'로 끝나지만 법령구분이 '{law_type}' "
                    f"(예상: 총리령 또는 부령)"
                )
            break

    return errors


def validate_metadata_json() -> list[str]:
    """Validate metadata.json against file system."""
    errors = []

    if not METADATA_FILE.exists():
        return ["metadata.json not found"]

    try:
        metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return [f"Cannot parse metadata.json: {e}"]

    # Check each entry has a corresponding file
    for mst, info in metadata.items():
        file_path = PROJECT_ROOT / info.get("path", "")
        if not file_path.exists():
            errors.append(f"metadata.json references missing file: {info.get('path')}")

    # Check for files not in metadata (by MST in frontmatter)
    known_paths = {info.get("path") for info in metadata.values()}
    for md_file in KR_DIR.rglob("*.md"):
        rel = str(md_file.relative_to(PROJECT_ROOT))
        if rel not in known_paths:
            errors.append(f"File not in metadata.json: {rel}")

    return errors


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    total_errors = 0
    files_checked = 0

    for md_file in sorted(KR_DIR.rglob("*.md")):
        errors = validate_frontmatter(md_file)
        files_checked += 1
        if errors:
            rel_path = md_file.relative_to(PROJECT_ROOT)
            for err in errors:
                logger.error(f"{rel_path}: {err}")
            total_errors += len(errors)

    meta_errors = validate_metadata_json()
    for err in meta_errors:
        logger.error(f"metadata.json: {err}")
    total_errors += len(meta_errors)

    logger.info(f"Checked {files_checked} files, found {total_errors} errors")

    if total_errors > 0:
        sys.exit(1)
    else:
        logger.info("All validations passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
