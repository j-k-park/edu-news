# 전국 시도교육청 소식 수집기

전국 **16개 시도교육청**의 보도자료와 교육 관련 뉴스를 매일 자동으로 모아
① 교육청별 웹 대시보드로 보여 주고 ② 노션 데이터베이스에 쌓습니다.

> 2026년 7월 1일 광주광역시교육청과 전라남도교육청이 **전남광주통합특별시교육청**으로
> 통합되어, 현재 시도교육청은 16개입니다.

---

## 1. 어떻게 모으나

| 경로 | 설명 | 준비물 |
|---|---|---|
| **구글 뉴스 RSS** | 16개 교육청 이름으로 검색. 기본 수집 경로 | 없음 |
| **공식 보도자료 게시판** | `sources.json` 에 주소를 넣은 교육청만 원문 수집 | 없음 |
| 네이버 뉴스 API | 있으면 보강 수집 | 네이버 개발자센터 키 |

교육청 누리집은 저마다 구조가 달라서 16곳을 한꺼번에 긁는 표준 방법이 없습니다.
그래서 **어디서나 동작하는 구글 뉴스 RSS를 기본**으로 깔고,
공식 보도자료 게시판은 찾는 대로 하나씩 붙이는 구조로 만들었습니다.
현재 서울은 공식 보도자료가 연결돼 있습니다.

### 다른 교육청 보도자료도 붙이려면

일부 교육청 누리집은 해외 IP를 막아 두어 GitHub 서버에서는 접속이 안 될 수 있습니다.
**국내 PC에서** 아래를 돌려 보도자료 목록 주소를 찾은 뒤 `sources.json` 에 넣으세요.

```bash
python discover.py
```

```jsonc
"board": {
  "type": "html",
  "url":  "https://enews.sen.go.kr/news/list.do?step1=3&step2=1",  // 목록 주소
  "base": "https://enews.sen.go.kr",                                // 사이트 주소
  "link": "view\\.do"                                               // 상세 링크 공통 문자열
}
```

---

## 2. 설치와 실행

```bash
pip install -r requirements.txt
python collect.py          # docs/data.json 생성
```

`docs/index.html` 을 브라우저로 열면 대시보드가 바로 보입니다.

---

## 3. 노션 연결

1. <https://www.notion.so/my-integrations> → **새 API 통합** 만들기 → 시크릿(`ntn_...`) 복사
2. 노션에서 **전국 시도교육청 소식 아카이브** 데이터베이스 열기
   → 우측 상단 `···` → **연결** → 방금 만든 통합 추가
3. 데이터베이스 주소에서 ID 복사
   `notion.so/<워크스페이스>/`**`5c96344f57fe407585db7c3bad628f57`**`?v=...`
4. 실행

```bash
export NOTION_TOKEN=ntn_xxxxxxxx
export NOTION_DATABASE_ID=5c96344f57fe407585db7c3bad628f57
python to_notion.py
```

`고유키` 속성으로 중복을 막기 때문에 여러 번 돌려도 같은 기사가 두 번 들어가지 않습니다.
기본으로 최근 7일치만 올립니다 (`NOTION_SYNC_DAYS` 로 조정).

---

## 4. 매일 자동 실행 (GitHub Actions)

1. 이 폴더를 깃허브 저장소로 올립니다.

```bash
git init && git add . && git commit -m "교육청 소식 수집기"
git branch -M main
git remote add origin https://github.com/<아이디>/<저장소>.git
git push -u origin main
```

2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|---|---|
| `NOTION_TOKEN` | 노션 통합 시크릿 |
| `NOTION_DATABASE_ID` | 노션 데이터베이스 ID |

3. 저장소 **Settings → Pages** → Source: `Deploy from a branch`,
   Branch: `main` / `/docs` → 저장
   → `https://<아이디>.github.io/<저장소>/` 에서 대시보드가 열립니다.

4. 매일 **한국시간 오전 7시**에 자동 실행됩니다.
   시간을 바꾸려면 `.github/workflows/daily.yml` 의 cron 을 고치세요 (UTC 기준, 한국시간 −9시간).
   `Actions` 탭에서 **Run workflow** 로 즉시 실행해 볼 수도 있습니다.

---

## 5. 분류 기준 손보기

`sources.json` 의 `tags` 가 제목·요약에 들어간 낱말로 분류를 붙입니다.
관심 주제에 맞게 낱말을 더하거나 새 분류를 만들면 대시보드 칩과 노션 `분류` 속성에 바로 반영됩니다.

```jsonc
"AI·디지털": ["AI","인공지능","디지털","에듀테크","디지털교과서","AIDT", ...]
```

---

## 6. 파일 구성

```
collect.py                     수집기 (여기가 본체)
to_notion.py                   노션 업로드
discover.py                    보도자료 게시판 주소 찾기 도우미
sources.json                   16개 교육청 설정 + 분류 낱말
docs/index.html                웹 대시보드 (전북특별자치도교육청 누리집 디자인)
docs/assets/img/               교육청 로고·파비콘 이미지
docs/favicon.ico               파비콘
docs/data.json                 수집 결과 (자동 생성)
docs/archive/YYYY-MM-DD.json   그날 새로 잡힌 것만 (자동 생성)
.github/workflows/daily.yml    매일 자동 실행
```

## 알아 둘 점

- 구글 뉴스 링크는 원문으로 넘어가는 중계 주소입니다. 눌러 보면 해당 언론사 기사로 이동합니다.
- 언론 보도는 교육청 발표를 옮긴 것이라 사실관계는 보도자료 원문으로 한 번 더 확인하는 편이 안전합니다.
- `RETENTION_DAYS`(기본 45) 보다 오래된 항목은 `data.json` 에서 빠지지만,
  노션과 `docs/archive/` 에는 그대로 남습니다.
