#!/usr/bin/env python3
"""전국 17개 시도교육청 소식 수집기.

수집 경로
  1) Google News RSS   : API 키 없이 17개 교육청 모두 동일하게 수집 (기본)
  2) 네이버 뉴스 API    : NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 있으면 추가 수집
  3) 공식 보도자료 게시판: sources.json 의 board 설정이 있는 교육청만 원문 수집

결과: docs/data.json (웹앱용, 최근 RETENTION_DAYS 일)
      docs/archive/YYYY-MM-DD.json (그날 새로 잡힌 것만)
"""
import os, re, json, time, hashlib, datetime as dt
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
ARCH = os.path.join(DOCS, "archive")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "45"))
PER_QUERY = int(os.environ.get("PER_QUERY", "25"))
KST = dt.timezone(dt.timedelta(hours=9))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

def log(*a): print("[collect]", *a, flush=True)

def load_cfg():
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        return json.load(f)

TITLE_NOISE = re.compile(r"\s*[>·|\-–]\s*(뉴스|기사|보도자료|속보|종합)\s*$")

def clean_title(t):
    t = strip_tags(t)
    for _ in range(3):
        n = TITLE_NOISE.sub("", t).strip()
        if n == t: break
        t = n
    return t.strip(" -–·|")

def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'"),("&nbsp;"," ")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()

def norm_title(t):
    return re.sub(r"[^가-힣a-z0-9]", "", strip_tags(t).lower())

def item_id(office, title, url):
    return hashlib.sha1(f"{office}|{norm_title(title)}".encode()).hexdigest()[:16]

def aliases(office):
    """queries 에서 따옴표를 벗겨 관련성 검사용 별칭 목록을 만든다."""
    al = [q.strip().strip('"') for q in office["queries"]]
    al.append(office["full"])
    return [a for a in {x for x in al if x}]

HANGUL = re.compile(r"[가-힣]")

def is_relevant(office, title, summary):
    """구글 뉴스가 느슨하게 매칭한 다른 지역 기사를 걸러낸다.
    별칭이 들어 있어도 '전남광주시교육청'처럼 다른 낱말에 묻힌 경우는 제외."""
    blob = (title or "") + " " + (summary or "")
    for a in aliases(office):
        for m in re.finditer(re.escape(a), blob):
            before = blob[m.start() - 1] if m.start() else " "
            if not HANGUL.match(before):
                return True
    return False

def tag_of(text, tagmap):
    hits = []
    for tag, words in tagmap.items():
        n = sum(1 for w in words if w in text)
        if n: hits.append((n, tag))
    hits.sort(reverse=True)
    return [t for _, t in hits[:2]] or ["기타"]

def to_kst_date(struct_or_str):
    """RFC822 / ISO 문자열 -> YYYY-MM-DD (KST)"""
    s = (struct_or_str or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = dt.datetime.strptime(s, fmt)
            if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
            return d.astimezone(KST).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(20\d\d)[-.\/](\d{1,2})[-.\/](\d{1,2})", s)
    if m: return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return dt.datetime.now(KST).strftime("%Y-%m-%d")

def fetch(url, **kw):
    last = None
    for i in range(3):
        try:
            r = S.get(url, timeout=kw.pop("timeout", 25), **kw)
            if r.status_code < 400: return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:80]
        time.sleep(1.5 * (i + 1))
    log("  ! 실패:", url[:80], last)
    return None

# ---------------------------------------------------------------- providers
def from_google_news(office):
    out = []
    for q in office["queries"]:
        url = ("https://news.google.com/rss/search?q=" + quote(q + " when:14d") +
               "&hl=ko&gl=KR&ceid=KR:ko")
        r = fetch(url)
        if not r: continue
        try: root = ET.fromstring(r.content)
        except ET.ParseError: continue
        for it in root.iter("item"):
            title = strip_tags(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            if not title or not link: continue
            press = ""
            if " - " in title:
                title, press = title.rsplit(" - ", 1)
            desc = strip_tags(it.findtext("description"))[:300]
            out.append({"title": clean_title(title), "url": link,
                        "date": to_kst_date(it.findtext("pubDate")),
                        "source": press.strip() or "언론보도", "kind": "뉴스",
                        "summary": desc})
            if len(out) >= PER_QUERY * len(office["queries"]): break
        time.sleep(0.6)
    return out

def from_naver(office):
    cid, csec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and csec): return []
    out = []
    for q in office["queries"]:
        r = fetch("https://openapi.naver.com/v1/search/news.json?display=30&sort=date&query=" + quote(q),
                  headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec})
        if not r: continue
        for it in r.json().get("items", []):
            out.append({"title": clean_title(it["title"]), "url": it.get("originallink") or it["link"],
                        "date": to_kst_date(it.get("pubDate", "")),
                        "source": "언론보도", "kind": "뉴스",
                        "summary": strip_tags(it.get("description", ""))[:300]})
        time.sleep(0.4)
    return out

def from_board(office):
    """공식 보도자료 게시판(HTML) 수집. sources.json 의 board 설정이 있을 때만."""
    b = office.get("board")
    if not b: return []
    r = fetch(b["url"])
    if not r: return []
    html = r.text
    out, seen = [], set()
    pat = re.compile(r'<a[^>]+href=["\']([^"\']*' + b["link"] + r'[^"\']*)["\'][^>]*>(.*?)</a>', re.S)
    for m in pat.finditer(html):
        href = strip_tags(m.group(1))
        block = m.group(2)
        text = strip_tags(block)
        if not text or len(text) < 6: continue
        date = to_kst_date(text)
        title = re.sub(r"20\d\d[-.]\d{1,2}[-.]\d{1,2}.*$", "", text).strip(" .·|")
        title = re.sub(r"\s*\d+\s*$", "", title).strip()
        if len(title) < 6: continue
        url = urljoin(b.get("base") or b["url"], href)
        if url in seen: continue
        seen.add(url)
        out.append({"title": clean_title(title), "url": url, "date": date,
                    "source": "공식 보도자료", "kind": "보도자료", "summary": ""})
    return out[:40]

# ---------------------------------------------------------------- main
def main():
    cfg = load_cfg()
    tagmap = cfg["tags"]
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    cutoff = (dt.datetime.now(KST) - dt.timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")

    os.makedirs(ARCH, exist_ok=True)
    prev_path = os.path.join(DOCS, "data.json")
    prev = {"items": []}
    if os.path.exists(prev_path):
        try: prev = json.load(open(prev_path, encoding="utf-8"))
        except Exception: pass
    known = {i["id"] for i in prev.get("items", [])}

    items, stats = {i["id"]: i for i in prev.get("items", [])}, []
    fresh = []

    for off in cfg["offices"]:
        got = []
        for fn in (from_board, from_google_news, from_naver):
            try:
                got += fn(off)
            except Exception as e:
                log(f"  ! {off['name']} {fn.__name__}: {str(e)[:70]}")
        n_new = 0
        for g in got:
            if g["date"] < cutoff: continue
            if g["kind"] == "뉴스" and not is_relevant(off, g["title"], g["summary"]):
                continue
            if norm_title(g["summary"])[:40] and norm_title(g["summary"]).startswith(norm_title(g["title"])[:30]):
                g["summary"] = ""   # 제목만 되풀이하는 요약은 버린다
            iid = item_id(off["code"], g["title"], g["url"])
            if iid in items:            # 이미 있으면 보도자료 원문을 우선 유지
                if g["kind"] == "보도자료": items[iid].update({"kind": "보도자료", "url": g["url"], "source": g["source"]})
                continue
            rec = {"id": iid, "office": off["name"], "office_code": off["code"],
                   "office_full": off["full"], "title": g["title"], "url": g["url"],
                   "date": g["date"], "source": g["source"], "kind": g["kind"],
                   "summary": g["summary"],
                   "tags": tag_of(g["title"] + " " + g["summary"], tagmap),
                   "collected_at": today}
            items[iid] = rec
            if iid not in known: fresh.append(rec); n_new += 1
        stats.append({"office": off["name"], "fetched": len(got), "new": n_new})
        log(f"  {off['name']:<3} 수집 {len(got):>3}건 / 신규 {n_new:>3}건")

    allitems = [i for i in items.values() if i["date"] >= cutoff]
    allitems.sort(key=lambda x: (x["date"], x["office"]), reverse=True)

    out = {"generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
           "offices": [{"code": o["code"], "name": o["name"], "full": o["full"], "site": o["site"]}
                       for o in cfg["offices"]],
           "tags": list(tagmap.keys()) + ["기타"],
           "stats": stats, "items": allitems}
    json.dump(out, open(prev_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 같은 날 여러 번 돌려도 그날 아카이브가 덮이지 않도록 합쳐서 저장
    apath = os.path.join(ARCH, today + ".json")
    day = {}
    if os.path.exists(apath):
        try: day = {i["id"]: i for i in json.load(open(apath, encoding="utf-8"))["items"]}
        except Exception: day = {}
    for r in fresh: day[r["id"]] = r
    json.dump({"date": today, "items": list(day.values())},
              open(apath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"완료: 전체 {len(allitems)}건, 오늘 신규 {len(fresh)}건 -> docs/data.json")

if __name__ == "__main__":
    main()
