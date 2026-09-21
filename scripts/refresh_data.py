#!/usr/bin/env python3
"""Rebuild data.json from the data-center jobs Google Sheet (last N days only)."""
import os, json, re, sys, hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
DAYS = int(os.environ.get("DAYS", "30"))
TAB = os.environ.get("SHEET_TAB", "Datacenter Technician")
MAX_DESC = 12000

DATE_FORMATS = ("%m/%d/%Y", "%a, %b %d, %Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y")
DC_RE = re.compile(r"data\s?-?\s?cent(?:er|re)s?|datacenter|colocation|critical\s+facilit", re.I)
COE_RE = re.compile(r"data\s?-?\s?cent(?:er|re)s?\s+of\s+excellence", re.I)


def is_dc(title, desc):
    """Data-center role: named in the title, or the description keeps coming back to it."""
    if DC_RE.search(COE_RE.sub("", title)):
        return True
    return len(DC_RE.findall(COE_RE.sub("", desc[:6000]))) >= 3


def clean(s):
    return (s or "").strip()


def parse_date(s):
    s = clean(s)
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})T", s)
    if m:
        s = m.group(1)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def parse_posted(s, scraped):
    """Exact dates pass through; 'N days ago' / 'Just posted' are anchored to the scrape date."""
    d = parse_date(s)
    if d:
        return d
    t = clean(s).lower()
    if not t:
        return None
    if re.search(r"just posted|today|hour|minute|moment", t):
        return scraped
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return scraped - timedelta(days=int(m.group(1)))
    return None


def norm_source(s):
    t = clean(s).lower()
    if "linkedin" in t:
        return "LinkedIn"
    if "indeed" in t:
        return "Indeed"
    return clean(s) or "Other"


def norm_loc(s):
    s = clean(s)
    s = re.sub(r"\b[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d\b", "", s)   # postal codes
    s = re.sub(r",?\s*Canada\s*$", "", s, flags=re.I)
    s = re.sub(r"\bOntario\b", "ON", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    return s


def salary_value(s):
    """Rough annualised max of a salary string, used only for sorting."""
    t = clean(s).lower()
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", t) if re.search(r"\d", x)]
    if not nums:
        return 0
    v = max(nums)
    if re.search(r"hour|/hr|\bhr\b", t):
        v *= 2080
    elif "month" in t:
        v *= 12
    elif "week" in t:
        v *= 52
    elif re.search(r"\bday\b", t):
        v *= 260
    elif v < 500:
        v *= 2080
    return int(v)


def job_key(url):
    m = re.search(r"jk=([0-9a-f]+)", url)
    if m:
        return m.group(1)
    m = re.findall(r"(\d{7,})", url)
    if m:
        return m[-1]
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def process_rows(rows, today=None, days=DAYS):
    today = today or datetime.now(TZ).date()
    cutoff = today - timedelta(days=days)
    out = {}
    for order, raw in enumerate(rows[1:]):
        r = [clean(x) for x in (list(raw) + [""] * 12)[:12]]
        src, title, posted, applied, salary, jtype, company, loc, desc, url = r[:10]
        if not title or not url:
            continue
        scraped = parse_date(applied) or parse_date(posted)   # "Date Applied" is really the scrape date
        if not scraped or scraped < cutoff:
            continue
        pdate = parse_posted(posted, scraped)
        rec = {
            "id": job_key(url),
            "source": norm_source(src),
            "title": title,
            "company": company,
            "loc": norm_loc(loc),
            "type": jtype,
            "salary": salary,
            "salv": salary_value(salary),
            "posted": pdate.isoformat() if pdate else "",
            "scraped": scraped.isoformat(),
            "url": url,
            "desc": desc[:MAX_DESC],
            "dc": is_dc(title, desc),
            "_o": order,
        }
        prev = out.get(rec["id"])
        if not prev or (rec["scraped"], rec["_o"]) >= (prev["scraped"], prev["_o"]):
            out[rec["id"]] = rec
    jobs = sorted(out.values(), key=lambda j: (j["scraped"], j["_o"]), reverse=True)
    for j in jobs:
        del j["_o"]
    return jobs


def fetch_rows():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
    res = svc.spreadsheets().values().get(
        spreadsheetId=os.environ["SHEET_ID"], range=f"'{TAB}'!A1:L"
    ).execute()
    return res.get("values", [])


def write_data(jobs, path="data.json"):
    now = datetime.now(TZ)
    synced = now.strftime("%b %-d, %Y \u00b7 %-I:%M %p %Z")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"synced": synced, "days": DAYS, "jobs": jobs}, f, ensure_ascii=False, separators=(",", ":"))
    return synced


def main():
    if not os.environ.get("GCP_SERVICE_ACCOUNT_JSON") or not os.environ.get("SHEET_ID"):
        print("Secrets not set - leaving the existing data.json untouched.")
        return
    rows = fetch_rows()
    jobs = process_rows(rows)
    if not jobs:
        sys.exit("No jobs parsed from the sheet - refusing to overwrite data.json.")
    synced = write_data(jobs)
    print(f"Wrote {len(jobs)} jobs from the last {DAYS} days, synced={synced}")


if __name__ == "__main__":
    main()
