import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

CACHE_FILE = "latest_results.json"

def sync_to_firestore():
    if not os.path.exists(CACHE_FILE):
        print("[-] Cache file not found. Nothing to sync.")
        return

    # Authenticate via environment secret or local key file
    cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
    elif os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json")
    else:
        print("[!] No Firebase credentials detected. Skipping Firestore sync.")
        return

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    last_updated = payload.get("last_updated", "")
    stocks = payload.get("data", [])

    print(f"[*] Syncing {len(stocks)} stocks to Firestore...")
    batch = db.batch()

    # Write metadata document
    meta_ref = db.collection("shariah_metadata").document("summary")
    batch.set(meta_ref, {
        "last_updated": last_updated,
        "total_screened": len(stocks),
        "compliant_count": sum(1 for s in stocks if s.get("is_compliant")),
    })

    # Write each stock document (Collection: shariah_stocks)
    for stock in stocks:
        doc_ref = db.collection("shariah_stocks").document(stock["ticker"])
        batch.set(doc_ref, {
            "ticker": stock["ticker"],
            "bse_code": stock.get("bse_code", "N/A"),
            "sector": stock.get("sector", "Diversified"),
            "market_cap_cr": stock.get("market_cap_cr", 0.0),
            "financial_date": stock.get("financial_date", "Latest"),
            "is_compliant": stock.get("is_compliant", False),
            "failure_reason": stock.get("failure_reason", ""),
            "metrics": stock.get("metrics", {}),
            "last_synced": firestore.SERVER_TIMESTAMP
        })

    batch.commit()
    print("[+] Successfully synced all stock results to Firebase Firestore.")

if __name__ == "__main__":
    sync_to_firestore()