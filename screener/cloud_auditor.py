import os
import json
from pypdf import PdfReader
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

DEFAULT_AUDIT = {
    "haram_business_revenue": 0.0,
    "impermissible_interest_income": 0.0,
    "non_compliant_investments": 0.0
}

def audit_footnotes_online(notes_text: str) -> dict:
    """
    Audits footnote text using Gemini online for C1, C2, and C6 metrics.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return DEFAULT_AUDIT

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are an Islamic finance auditor reviewing an Indian Ind-AS Annual Report footnote.
    Extract the following values in INR Crores. If absent or zero, assign 0.0.

    Footnote Content:
    {notes_text}

    Return strictly a JSON object with this exact schema:
    {{
      "haram_business_revenue": float,
      "impermissible_interest_income": float,
      "non_compliant_investments": float
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[!] Online audit notice: {e}. Proceeding with primary financial primitives.")
        return DEFAULT_AUDIT


def extract_notes_from_pdf(pdf_path: str) -> str:
    """
    Scans a 200+ page Annual Report PDF and extracts only the pages
    containing critical Shariah audit keywords (Other Income, Borrowings, Segments).
    """
    if not os.path.exists(pdf_path):
        return ""

    reader = PdfReader(pdf_path)
    keywords = ["other income", "borrowings", "segment reporting", "current investments", "interest income"]
    extracted = []

    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text_lower = text.lower()
        if any(k in text_lower for k in keywords):
            extracted.append(f"--- NOTE EXCERPT PAGE {idx + 1} ---\n{text}")
            if len(extracted) >= 8:  # Cap at 8 high-relevance pages to respect token limits
                break

    return "\n".join(extracted)