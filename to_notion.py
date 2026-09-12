#!/usr/bin/env python3
"""docs/data.json 의 항목을 노션 데이터베이스에 업서트(중복 없이 추가)한다.

환경변수
  NOTION_TOKEN        노션 내부 통합(integration) 시크릿  (ntn_... )
  NOTION_DATABASE_ID  대상 데이터베이스 ID
  NOTION_SYNC_DAYS    최근 며칠치만 올릴지 (기본 7)
"""
import os, json, time, datetime as dt, requests

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("NOTION_TOKEN")
DBID = os.environ.get("NOTION_DATABASE_ID", "").replace("-", "")
DAYS = int(os.environ.get("NOTION_SYNC_DAYS", "7"))
API = "https://api.notion.com/v1"
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
     "Content-Type": "application/json"}
KST = dt.timezone(dt.timedelta(hours=9))

def log(*a): print("[notion]", *a, flush=True)

def existing_keys():
    """이미 들어있는 고유키 전부 읽어오기."""
    keys, cursor = set(), None
    while True:
        body = {"page_size": 100, "filter_properties": []}
        if cursor: body["start_cursor"] = cursor
        r = requests.post(f"{API}/databases/{DBID}/query", headers=H,
                          json={k: v for k, v in body.items() if k != "filter_properties"},
                          timeout=30)
        if r.status_code != 200:
            log("조회 실패", r.status_code, r.text[:300]); raise SystemExit(1)
        d = r.json()
        for pg in d["results"]:
            rt = pg["properties"].get("고유키", {}).get("rich_text", [])
            if rt: keys.add(rt[0]["plain_text"])
        if not d.get("has_more"): break
        cursor = d["next_cursor"]; time.sleep(0.34)
    return keys

def page_payload(it):
    return {"parent": {"database_id": DBID}, "properties": {
        "제목":   {"title": [{"text": {"content": it["title"][:1900]}}]},
        "교육청": {"select": {"name": it["office"]}},
        "구분":   {"select": {"name": it["kind"]}},
        "분류":   {"multi_select": [{"name": t} for t in it["tags"]]},
        "게시일": {"date": {"start": it["date"]}},
        "출처":   {"rich_text": [{"text": {"content": it["source"][:200]}}]},
        "원문링크": {"url": it["url"][:1900]},
        "요약":   {"rich_text": [{"text": {"content": (it.get("summary") or "")[:1900]}}]},
        "수집일": {"date": {"start": it["collected_at"]}},
        "고유키": {"rich_text": [{"text": {"content": it["id"]}}]},
    }}

def main():
    if not (TOKEN and DBID):
        log("NOTION_TOKEN / NOTION_DATABASE_ID 가 없어 건너뜁니다."); return
    data = json.load(open(os.path.join(ROOT, "docs", "data.json"), encoding="utf-8"))
    cutoff = (dt.datetime.now(KST) - dt.timedelta(days=DAYS)).strftime("%Y-%m-%d")
    todo = [i for i in data["items"] if i["date"] >= cutoff]
    log(f"대상 {len(todo)}건 (최근 {DAYS}일)")
    have = existing_keys()
    log(f"노션에 이미 {len(have)}건 있음")
    added = 0
    for it in todo:
        if it["id"] in have: continue
        r = requests.post(f"{API}/pages", headers=H, json=page_payload(it), timeout=30)
        if r.status_code == 200:
            added += 1
        elif r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 3)))
            r = requests.post(f"{API}/pages", headers=H, json=page_payload(it), timeout=30)
            if r.status_code == 200: added += 1
        else:
            log("  ! 실패", r.status_code, it["title"][:30], r.text[:160])
        time.sleep(0.34)
    log(f"신규 {added}건 추가 완료")

if __name__ == "__main__":
    main()
