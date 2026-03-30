"""Central configuration for legalize-kr pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
KR_DIR = PROJECT_ROOT / "kr"
REFERENCES_DIR = PROJECT_ROOT / "doc" / "references"

# API
LAW_API_BASE = "http://www.law.go.kr/DRF"
LAW_API_KEY = os.environ.get("LAW_OC", os.environ.get("LAW_API_KEY", ""))

# Rate limiting
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0

# Suffixes that indicate a child law (order matters: longest first)
CHILD_SUFFIXES = [
    (" 시행규칙", "시행규칙"),
    (" 시행령", "시행령"),
]

# Fallback filename by 법령구분
TYPE_TO_FILENAME = {
    "헌법": "헌법",
    "법률": "법률",
    "대통령령": "대통령령",
    "총리령": "총리령",
    "부령": "부령",
    "대법원규칙": "대법원규칙",
    "국회규칙": "국회규칙",
    "헌법재판소규칙": "헌법재판소규칙",
    "감사원규칙": "감사원규칙",
    "선거관리위원회규칙": "선거관리위원회규칙",
}
