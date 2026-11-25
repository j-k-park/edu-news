"""
오늘의 핵심 요약
  docs/data.json 에서 오늘 새로 모인 소식 제목을 읽어 AI에게 개조식 10개 이내로 정리하게 하고
  docs/briefing.json 으로 저장한다. 화면(docs/index.html)이 이 파일을 읽어 '오늘의 핵심'을 보여 준다.

필요한 환경 변수: BAZE_API_KEY, BAZE_API_BASE (GitHub 저장소 Secrets)
키가 없거나 AI 호출이 실패하면 기존 briefing.json 을 그대로 두고 조용히 끝낸다(수집은 막지 않음).
"""
import datetime as dt
import json
import os
import re
import sys

import requests

KST = dt.timezone(dt.timedelta(hours=9))
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
MODEL = os.environ.get("BRIEFING_MODEL", "claude-sonnet-5-5")
MAX_ITEMS = 400

SYSTEM = """당신은 전북특별자치도교육청 정책 담당자를 위해 전국 시도교육청 동향을 정리하는 브리핑 작성자입니다.
주어진 오늘의 보도자료·뉴스 제목만 근거로, 오늘의 핵심을 개조식으로 정리합니다.

규칙
- 핵심은 10개 이내(보통 7~10개). 중요도 순으로 배열.
- 여러 교육청에서 동시에 나온 흐름(공통 이슈)을 먼저 묶고, 전북 소식은 반드시 1개 이상 포함.
- 각 항목의 text는 개조식 한 줄(60자 안팎). '~함', '~추진', '~확대' 처럼 명사형·간결체로 끝냄. 마침표 없음.
- 제목에 없는 사실, 숫자, 평가는 만들지 않음. 교육감 개인에 대한 해석·논평 금지.
- head는 그 항목을 대표하는 4~12자 짧은 머리말(예: 내신 부정행위 대책).
- offices는 그 항목에 해당하는 교육청 이름 배열(주어진 이름 그대로: 서울, 부산, 전북, 전남광주 …).
- keyword는 관련 제목들에 실제로 들어 있는 검색어 1개(2~8자, 예: 금속탐지기).
- 마크다운 기호(**, #, -)를 쓰지 말 것.

출력은 JSON 하나만:
{"points":[{"head":"…","text":"…","offices":["…"],"keyword":"…"}]}"""


def log(*a):
    print(*a, file=sys.stderr)


def main():
    key, base = os.environ.get("BAZE_API_KEY"), os.environ.get("BAZE_API_BASE")
    if not key or not base:
        log("요약 건너뜀: BAZE_API_KEY / BAZE_API_BASE 가 없습니다.")
        return

    data = json.load(open(os.path.join(DOCS, "data.json"), encoding="utf-8"))
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    items = [i for i in data["items"] if i.get("collected_at") == today]
    if not items:
        log("요약 건너뜀: 오늘 새로 모인 소식이 없습니다.")
        return

    # 보도자료와 전북을 앞에 두고, 너무 많으면 자른다
    items.sort(key=lambda i: (i["kind"] != "보도자료", i["office"] != "전북"))
    items = items[:MAX_ITEMS]
    names = [o["name"] for o in data["offices"]]
    lines = "\n".join(f"[{i['office']}] ({i['kind']}) {i['title']}" for i in items)
    prompt = f"오늘({today}) 새로 모인 소식 {len(items)}건입니다.\n\n{lines}"

    try:
        r = requests.post(
            base.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": MODEL, "max_tokens": 2000, "temperature": 0.2,
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": prompt}]},
            timeout=180,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        raw = json.loads(m.group(0) if m else text)["points"]
    except Exception as e:
        log(f"요약 실패(기존 요약 유지): {str(e)[:120]}")
        return

    titles = " ".join(i["title"] for i in items).lower()
    clean = re.compile(r"[*#`]+")
    points = []
    for p in raw[:10]:
        t = clean.sub("", str(p.get("text", ""))).strip().lstrip("-•· ").rstrip(".")
        if not t:
            continue
        kw = clean.sub("", str(p.get("keyword", ""))).strip()
        points.append({
            "head": clean.sub("", str(p.get("head", ""))).strip(),
            "text": t,
            "offices": [o for o in p.get("offices", []) if o in names],
            "keyword": kw if kw and kw.lower() in titles else "",
        })
    if not points:
        log("요약 실패(기존 요약 유지): 항목이 비었습니다.")
        return

    out = {"date": today, "generated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
           "based_on": len(items), "model": MODEL, "points": points}
    json.dump(out, open(os.path.join(DOCS, "briefing.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log(f"오늘의 핵심 {len(points)}개 -> docs/briefing.json")


if __name__ == "__main__":
    main()
