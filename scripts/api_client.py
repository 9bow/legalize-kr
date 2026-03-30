"""Thin wrapper around law.go.kr OpenAPI."""

import logging
import time
from xml.etree import ElementTree

import requests

from config import (
    BACKOFF_BASE_SECONDS,
    LAW_API_BASE,
    LAW_API_KEY,
    MAX_RETRIES,
    REQUEST_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)

_last_request_time = 0.0


def _throttle():
    """Rate limit requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
    _last_request_time = time.time()


def _request(url: str, params: dict) -> requests.Response:
    """Make a throttled request with retry and exponential backoff."""
    params["OC"] = LAW_API_KEY

    for attempt in range(MAX_RETRIES + 1):
        _throttle()
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                wait = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(f"Rate limited (429). Waiting {wait}s before retry.")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            wait = BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning(f"Request failed: {e}. Retry {attempt + 1}/{MAX_RETRIES} in {wait}s")
            time.sleep(wait)

    raise RuntimeError("Unreachable")


def search_laws(
    query: str = "",
    page: int = 1,
    display: int = 20,
    sort: str = "lasc",
    law_type: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """Search laws via the search API.

    Returns dict with keys: totalCnt, page, laws (list of law metadata dicts).
    """
    params = {
        "target": "law",
        "type": "XML",
        "query": query,
        "page": str(page),
        "display": str(display),
        "sort": sort,
    }
    if law_type:
        params["knd"] = law_type
    if date_from and date_to:
        params["ancYd"] = f"{date_from}~{date_to}"

    resp = _request(f"{LAW_API_BASE}/lawSearch.do", params)
    root = ElementTree.fromstring(resp.content)

    total = root.findtext("totalCnt", "0")
    page_num = root.findtext("page", "1")

    laws = []
    for item in root.findall(".//law"):
        laws.append({
            "법령일련번호": item.findtext("법령일련번호", ""),
            "현행연혁코드": item.findtext("현행연혁코드", ""),
            "법령명한글": item.findtext("법령명한글", ""),
            "법령약칭명": item.findtext("법령약칭명", ""),
            "법령ID": item.findtext("법령ID", ""),
            "공포일자": item.findtext("공포일자", ""),
            "공포번호": item.findtext("공포번호", ""),
            "제개정구분명": item.findtext("제개정구분명", ""),
            "소관부처명": item.findtext("소관부처명", ""),
            "시행일자": item.findtext("시행일자", ""),
            "법령상세링크": item.findtext("법령상세링크", ""),
        })

    return {"totalCnt": int(total), "page": int(page_num), "laws": laws}


def get_law_detail(mst_id: str | int) -> dict:
    """Fetch full law text and metadata by MST ID.

    Returns dict with metadata fields and 조문 (articles) list.
    """
    params = {
        "target": "law",
        "MST": str(mst_id),
        "type": "XML",
    }

    resp = _request(f"{LAW_API_BASE}/lawService.do", params)
    root = ElementTree.fromstring(resp.content)

    # Check for error response
    error = root.findtext("result")
    if error and "실패" in error:
        raise RuntimeError(f"API error for MST {mst_id}: {error} - {root.findtext('msg', '')}")

    # Parse metadata
    metadata = {
        "법령명한글": root.findtext(".//법령명_한글", ""),
        "법령MST": str(mst_id),
        "법령ID": root.findtext(".//법령ID", ""),
        "법령구분": root.findtext(".//법종구분", ""),
        "법령구분코드": root.findtext(".//법종구분코드", ""),
        "소관부처명": root.findtext(".//소관부처명", ""),
        "소관부처코드": root.findtext(".//소관부처코드", ""),
        "공포일자": root.findtext(".//공포일자", ""),
        "공포번호": root.findtext(".//공포번호", ""),
        "시행일자": root.findtext(".//시행일자", ""),
        "제개정구분": root.findtext(".//제개정구분명", ""),
        "법령분야": root.findtext(".//법령분류명", ""),
    }

    # Parse articles (조문)
    articles = []
    for jo in root.findall(".//조문단위"):
        article = {
            "조문번호": jo.findtext("조문번호", ""),
            "조문제목": jo.findtext("조문제목", ""),
            "조문내용": jo.findtext("조문내용", ""),
        }
        # Parse 항 (paragraphs)
        paragraphs = []
        for hang in jo.findall(".//항"):
            para = {
                "항번호": hang.findtext("항번호", ""),
                "항내용": hang.findtext("항내용", ""),
            }
            # Parse 호 (subparagraphs)
            subparas = []
            for ho in hang.findall(".//호"):
                subparas.append({
                    "호번호": ho.findtext("호번호", ""),
                    "호내용": ho.findtext("호내용", ""),
                })
            para["호"] = subparas
            paragraphs.append(para)
        article["항"] = paragraphs
        articles.append(article)

    # Parse 부칙 (supplementary provisions)
    addenda = []
    for buchik in root.findall(".//부칙단위"):
        addenda.append({
            "부칙공포일자": buchik.findtext("부칙공포일자", ""),
            "부칙공포번호": buchik.findtext("부칙공포번호", ""),
            "부칙내용": buchik.findtext("부칙내용", ""),
        })

    return {
        "metadata": metadata,
        "articles": articles,
        "addenda": addenda,
        "raw_xml": resp.content,
    }


def get_law_history(mst_id: str | int) -> list[dict]:
    """Fetch amendment history for a law.

    Returns list of dicts sorted oldest-first, each with:
    법령MST, 법령명한글, 공포일자, 제개정구분명, 시행일자
    """
    params = {
        "target": "law",
        "MST": str(mst_id),
        "type": "XML",
        "search": "2",
    }

    # Try fetching history via the search endpoint with history mode
    resp = _request(f"{LAW_API_BASE}/lawSearch.do", params)
    root = ElementTree.fromstring(resp.content)

    history = []
    for item in root.findall(".//law"):
        history.append({
            "법령일련번호": item.findtext("법령일련번호", ""),
            "법령명한글": item.findtext("법령명한글", ""),
            "공포일자": item.findtext("공포일자", ""),
            "제개정구분명": item.findtext("제개정구분명", ""),
            "시행일자": item.findtext("시행일자", ""),
            "법령상세링크": item.findtext("법령상세링크", ""),
        })

    # Sort oldest first
    history.sort(key=lambda x: x.get("공포일자", ""))
    return history
