import os, re, json, time, hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, urlsplit

import requests
import feedparser
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup
import trafilatura

# ---------------------------
# Paths
# ---------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_PATH = os.path.join(DATA_DIR, "raw.jsonl")
CSV_PATH = os.path.join(DATA_DIR, "processed.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------
# Settings
# ---------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LFD-FinalProject/1.0)"}
SLEEP_SEC = 0.35
MIN_TEXT_LEN = 220           # kısa ama işe yarar
TARGET_PER_LABEL = 450       # 5 label => ~2250 (elenenlere pay)

# Google News RSS Search template
# q içine anahtar kelimeler koyacağız; when:7d gibi filtreler işe yarar
def google_news_rss_url(q: str, hl="en-US", gl="US", ceid="US:en"):
    # q URL-encode basit: boşlukları + yap
    q = q.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

LABEL_QUERIES = {
    "business": [
        "economy OR inflation OR stock market OR central bank when:30d",
        "interest rates OR bond yields OR GDP when:30d",
        "company earnings OR revenue OR profit when:30d",
        "trade deficit OR exports OR imports when:30d",
        "banking regulation OR fintech when:30d",
    ],
    "tech": [
        "artificial intelligence OR generative AI OR LLM when:30d",
        "cybersecurity OR data breach OR ransomware when:30d",
        "software update OR cloud computing OR SaaS when:30d",
        "startup funding OR venture capital tech when:30d",
        "semiconductor OR chip manufacturing when:30d",
    ],
    "science": [
        "climate change OR environment research when:30d",
        "space mission OR NASA OR telescope when:30d",
        "scientists discover OR study finds when:30d",
        "renewable energy research OR fusion when:30d",
        "biodiversity OR ocean study when:30d",
    ],
    "health": [
        "public health OR WHO OR outbreak when:30d",
        "vaccine trial OR clinical trial when:30d",
        "hospital OR healthcare policy when:30d",
        "disease symptoms OR treatment study when:30d",
        "mental health study OR depression anxiety when:30d",
    ],
    "world": [
        "election OR parliament OR government policy when:30d",
        "war OR conflict OR ceasefire when:30d",
        "diplomacy OR summit OR sanctions when:30d",
        "protest OR referendum OR coup when:30d",
        "migration OR refugees OR border policy when:30d",
    ],
}

# ---------------------------
# Helpers
# ---------------------------
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def stable_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()

def load_seen_ids():
    seen = set()
    if os.path.exists(RAW_PATH):
        with open(RAW_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["id"])
                except Exception:
                    pass
    return seen

def append_raw(row: dict):
    with open(RAW_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def rebuild_csv():
    if not os.path.exists(RAW_PATH):
        return
    df = pd.read_json(RAW_PATH, lines=True)
    if df.empty:
        return
    cols = ["id","label","source","url","published_at","title","summary","text","scraped_at"]
    df = df[cols].drop_duplicates("id")
    df.to_csv(CSV_PATH, index=False, encoding="utf-8")

def resolve_google_news_to_original(url: str) -> str:
    """
    Google News RSS linkleri bazen news.google.com/articles/... olur.
    Sayfayı açıp canonical link veya dış linki yakalamaya çalışırız.
    Bulamazsak aynı URL kalır (fallback).
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # canonical
        canon = soup.find("link", rel="canonical")
        if canon and canon.get("href"):
            return canon["href"]

        # bazı sayfalarda dış link a etiketi:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "news.google.com" not in href:
                return href
    except Exception:
        pass
    return url

def extract_full_text(url: str) -> str:
    """
    trafilatura ile full text çıkarma.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return clean_text(text or "")
    except Exception:
        return ""

def scrape_label(label: str, queries: list[str], seen: set) -> int:
    added = 0
    for q in queries:
        feed_url = google_news_rss_url(q)
        feed = feedparser.parse(feed_url)
        entries = getattr(feed, "entries", []) or []

        for e in tqdm(entries, desc=f"{label} | {q[:22]}..."):
            if added >= TARGET_PER_LABEL:
                return added

            link = getattr(e, "link", "") or ""
            if not link:
                continue

            # önce google linki id olarak kullanma; orijinali çözmeye çalış
            original = resolve_google_news_to_original(link)

            _id = stable_id(original)
            if _id in seen:
                continue

            title = clean_text(getattr(e, "title", "") or "")
            summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", "") or "")
            published = ""
            if getattr(e, "published", None):
                published = clean_text(e.published)

            # full text dene, olmazsa fallback: title+summary
            text = extract_full_text(original)
            if len(text) < MIN_TEXT_LEN:
                text = clean_text(f"{title}. {summary}")

            if len(text) < MIN_TEXT_LEN:
                continue

            row = {
                "id": _id,
                "label": label,
                "source": urlparse(original).netloc,
                "url": original,
                "published_at": published,
                "title": title,
                "summary": summary,
                "text": text,
                "scraped_at": datetime.now(timezone.utc).isoformat()
            }
            append_raw(row)
            seen.add(_id)
            added += 1
            time.sleep(SLEEP_SEC)

            if added >= TARGET_PER_LABEL:
                return added

    return added

def run():
    seen = load_seen_ids()
    total_added = 0

    for label, queries in LABEL_QUERIES.items():
        print(f"\n=== Collecting {label} ===")
        added = scrape_label(label, queries, seen)
        total_added += added
        print(f"Label {label}: added {added}")

    rebuild_csv()

    df = pd.read_csv(CSV_PATH) if os.path.exists(CSV_PATH) else pd.DataFrame()
    print("\n=== SUMMARY ===")
    if not df.empty:
        print("rows:", len(df))
        print(df["label"].value_counts())
    print(f"\nAdded total this run: {total_added}")
    print(f"RAW: {RAW_PATH}")
    print(f"CSV: {CSV_PATH}")

if __name__ == "__main__":
    run()
