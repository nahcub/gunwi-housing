# 군위군 빈집·노후주택 기반 주거환경 취약지역 분석

군위군 8개 읍·면의 빈집·노후주택 자료와 인구·생활시설 자료를 모으는 저장소다.
지금 단계는 **데이터 수집**이다. 새 지표·시각화는 만들지 않는다.
`nahcub/gunwi`(생활불편 민원 기반 시설관리 분석)를 복제해 주제를 바꿨다.
이전 주제의 원자료·문서는 git 커밋 `ea23c30` 에서 복구할 수 있다.

> **인수인계 안내** — 작업 전 `CLAUDE.md`(규칙)와 `docs/how-to.md`(작업별 절차)를
> 먼저 읽는다. AI 도구를 쓴다면 이 두 파일을 먼저 읽게 한다.

화면의 모든 숫자는 실제 공식 자료에서 나온 값이다. 샘플값이나 임의 생성값은 없다.

## 실행

```bash
npm ci                    # wrangler 하나
pip install -r requirements.txt

npm run prepare-data      # data/raw -> data/derived  (검증)
npm run dev               # 빌드 후 http://127.0.0.1:8787
```

| 명령 | 하는 일 |
|---|---|
| `npm run prepare-data` | 원자료 검증·정제 → `data/derived/` |
| `npm run build` | `data/derived/` → `public/data/` |
| `npm run export` | `data/derived/` → `outputs/` 제출용 엑셀·CSV |
| `npm run figures` | `data/derived/` → `outputs/figures/` 보고서 삽화 2장 |
| `npm test` | 검증 로직이 살아 있는지 확인 |
| `npm run deploy` | 빌드 후 Cloudflare 배포 (main push 시 GitHub Actions 가 자동 실행) |

`deploy` 와 `dev` 에 빌드가 붙어 있어 **빌드를 깜빡할 수 없다.** 원자료가 바뀌면
`prepare-data` 를 다시 돌린다. `public/data/` 는 git 에 없으므로 clone·pull 직후
웹을 열려면 `npm run build`(또는 `python tools/build.py`)를 한 번 돌려야 한다.

## 데이터 흐름

```
[다운로드]  tools/add_source.py
     ↓
data/raw/          받은 그대로. 동결. _meta.json 에 출처·수집일·sha256
     ↓             tools/prepare.py   <- assert 검증 관문
data/derived/      정제·검증 통과분                커밋 O   공개 X
     ↓             tools/build.py     <- 공개 결정 지점
public/data/       화면용                          커밋 X   공개 O
     ↓
public/index.html  브라우저가 런타임에 fetch 해서 region_code 로 조인
```

HTML 에는 데이터가 박히지 않는다. 빈 껍데기를 받고 브라우저가 JSON 을 가져와
Leaflet 으로 그린다.

## 폴더

```
data/sources.json    출처 레지스트리 — 유일한 진실. public/data/sources.json 이 여기서 생성된다
data/raw/            원자료 + _meta.json(출처 카드) + capture.html(원본 페이지 증빙)
data/derived/        prepare.py 출력
tools/               add_source.py / fetch_binzibe.py / prepare.py / build.py / export_excel.py / tests
outputs/             export_excel.py 출력 (제출용 엑셀·CSV)
outputs/figures/     figures.py 출력 (보고서 삽화 PNG + 근거 CSV)
public/              배포되는 폴더. "여기 넣은 건 공개"
docs/methodology.md  산식 근거. 공식 기준과 프로젝트 파생지표의 구분
docs/data-guide.md   raw 원자료별 내용과 derived 에서 무엇이 되는지
docs/how-to.md       작업별 절차 ("X 하려면 어디를 고치나")
docs/data-survey.md  있는 자료와 없는 자료 조사 결과
docs/requests/       군청 정보공개청구 초안 (미발송)
```

## 지금 지도에서 보이는 것

**표시됨** — 읍면 8개 코로플레스: 총인구 · 고령화율 · 노령화지수 · 인구밀도 ·
경로당 수 · 고령인구 1천명당 경로당 · 노후 경로당 비율 /
2개 시점 전환(2025-12, 2026-08. 시설·SGIS 지표는 시점과 무관) /
경로당 215곳 마커 / 읍면 순위·상세 / 데이터 출처 패널

**비활성** — 종합 점수(계산하지 않는다. `docs/methodology.md` §3)

빈집애 읍면별 빈집 수(합 602)는 raw 에 등록만 했고 아직 화면·엑셀에 없다.

## 있는 자료와 없는 자료

자세한 표는 `docs/data-survey.md`, 상태는 `data/sources.json`.

- **있음** — 빈집애 읍면별 빈집 수, SGIS 읍면별 주택 수·건축년도별 주택(2024),
  주민등록 인구, 경로당, 읍면 경계
- **없음** — 빈집 등급·위치(군청 실태조사, 정보공개청구 필요·미발송),
  건축물대장(리·지번 단위 사용승인일, API 키 승인·미수집),
  통계청 미거주주택(시군구 단위)
- **빈집률은 만들지 않는다** — 빈집애 빈집 수와 같은 정의의 분모(주택 수)가 없다

## 알려진 과제

1. ~~경계 GeoJSON 출처 미확인~~ — **2026-10-15 해결.** SGIS 2025 2Q 원본과 8개 읍면
   도형 일치 확인(`tools/verify_boundary.py`). → `CLAUDE.md`
2. **군청 빈집 실태조사 청구 미발송** → `docs/requests/README.md`
3. **건축물대장 수집기 없음** → `docs/how-to.md` §9
4. **SGIS 건축년도별주택 미연결** — 항목코드–연도 구간 대응 확인 필요 → `docs/data-guide.md` §4

## 이 저장소를 새로 판 이유

기존 두 저장소(`gunwi-knu/gunwi-civic-map`, `dohun3540-crypto/deltalab`)는
배포 폴더가 소스이자 산출물이어서 데이터 생성 단계가 들어갈 자리가 없었다.
그 결과 원자료를 정성껏 정리해도 웹에 반영되지 않았고, 출처 레지스트리와
웹 사본이 15개 항목 전부 어긋났다. 이 저장소는 `raw → derived → public` 을
분리해 그 단절을 없앤 것이다.

옛 저장소에서 계승한 것: 검증 assert 로직, 원본 페이지 캡처, 함정 목록,
출처 스키마. 버린 것: 샘플 지표값, 손으로 옮겨 적던 웹 사본, 워크플로 5개,
문서 7개, 실행 불가 빌드 스크립트.
