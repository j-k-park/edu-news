#!/usr/bin/env python3
"""각 시도교육청 누리집에서 '보도자료' 게시판 주소를 찾아 준다.

※ 일부 교육청 누리집은 해외 IP를 차단하므로, 국내 PC에서 실행해야 잘 찾습니다.
   찾은 주소를 sources.json 의 해당 교육청 board 항목에 넣으면
   그 교육청은 언론 기사 대신 공식 보도자료 원문을 수집합니다.

     "board": {"type":"html",
               "url":"<찾은 목록 주소>",
               "base":"<사이트 주소>",
               "link":"<상세보기 링크에 공통으로 들어가는 문자열>"}
"""
import json, os, re, time, requests, urllib3
from urllib.parse import urljoin
urllib3.disable_warnings()

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
S = requests.Session(); S.headers.update(H); S.verify = False

def follow(url, hops=3):
    r = S.get(url, timeout=25)
    for _ in range(hops):
        if len(r.text) > 4000: break
        m = (re.search(r'http-equiv=["\']refresh["\'][^>]*url=([^"\'>\s]+)', r.text, re.I)
             or re.search(r'location\.(?:href|replace)\s*[=(]\s*["\']([^"\']+)', r.text))
        if not m: break
        r = S.get(urljoin(r.url, m.group(1).strip()), timeout=25)
    return r

def main():
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.json"),
                        encoding="utf-8"))
    for o in cfg["offices"]:
        print(f"\n### {o['name']} — {o['full']}")
        if o.get("board"):
            print("   (이미 설정됨)", o["board"]["url"]); continue
        try:
            r = follow(o["site"])
        except Exception as e:
            print("   접속 실패:", str(e)[:70]); continue
        found = []
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.{0,60}?)</a>', r.text, re.S):
            txt = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if "보도자료" in txt or "보도 자료" in txt:
                found.append(urljoin(r.url, m.group(1)))
        for f in dict.fromkeys(found):
            print("   후보:", f)
        if not found:
            print("   찾지 못했습니다 — 누리집에서 직접 보도자료 목록 주소를 복사해 넣어 주세요.")
        time.sleep(1)

if __name__ == "__main__":
    main()
