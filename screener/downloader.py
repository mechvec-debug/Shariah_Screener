import os
import json
import zipfile
import requests
from datetime import datetime, timedelta
from typing import Optional

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"

BASE_URLS = [
    "https://www.bseindia.com/xml-data/corpfiling/AttachLive/",
    "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Origin": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _safe_parse_json(response: requests.Response) -> dict:
    """Handles BSE's single- and double-encoded JSON payloads."""
    try:
        data = response.json()
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _extract_if_zip(file_path: str, output_dir: str) -> str:
    """Extracts XML from ZIP if BSE packaged the XBRL inside an archive."""
    if file_path.lower().endswith(".zip") and zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, "r") as z:
            z.extractall(output_dir)
            for name in z.namelist():
                if name.lower().endswith((".xml", ".xbrl")):
                    return os.path.join(output_dir, name)
    return file_path


def fetch_latest_xbrl(scrip_code: str, output_dir: str = "./downloads", max_pages: int = 4) -> Optional[str]:
    """
    Queries BSE corporate filings for the scrip code over the past 365 days
    to locate and download the latest XBRL filing.
    """
    os.makedirs(output_dir, exist_ok=True)
    session = requests.Session()

    today = datetime.now()
    one_year_ago = today - timedelta(days=365)
    to_date_str = today.strftime("%Y%m%d")
    from_date_str = one_year_ago.strftime("%Y%m%d")

    for page in range(1, max_pages + 1):
        params = {
            "pageno": page,
            "strCat": "-1",
            "strPrevDate": from_date_str,
            "strScrip": str(scrip_code).strip(),
            "strSearch": "P",           # Period search
            "strToDate": to_date_str,
            "strType": "C",
            "subcategory": ""
        }

        try:
            res = session.get(BSE_API_URL, params=params, headers=HEADERS, timeout=15)
            res.raise_for_status()
        except requests.RequestException as e:
            print(f"[-] HTTP connection to BSE failed on page {page}: {e}")
            continue

        data = _safe_parse_json(res)
        records = data.get("Table") or data.get("Table1") or []

        if not records:
            continue

        for row in records:
            attachment = (row.get("ATTACHMENTNAME") or "").strip()
            subject = (row.get("NEWSSUB") or "").upper()
            headline = (row.get("HEADLINE") or "").upper()

            if not attachment:
                continue

            is_xml_file = attachment.lower().endswith((".xml", ".xbrl"))
            is_xbrl_text = "XBRL" in subject or "XBRL" in headline

            # Match explicit XML or an XBRL zip package
            if is_xml_file or (is_xbrl_text and attachment.lower().endswith(".zip")):
                target_path = os.path.join(output_dir, f"{scrip_code}_{attachment}")

                for base in BASE_URLS:
                    file_url = f"{base}{attachment}"
                    try:
                        dl = session.get(file_url, headers=HEADERS, timeout=25, stream=True)
                        if dl.status_code == 200:
                            with open(target_path, "wb") as f:
                                for chunk in dl.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            return _extract_if_zip(target_path, output_dir)
                    except requests.RequestException:
                        continue

    return None