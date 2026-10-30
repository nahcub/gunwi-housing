# 작업별 절차: "X 하려면 어디를 고치나"

규칙의 이유는 `CLAUDE.md`, 데이터 내용은 `docs/data-guide.md` 에 있다.
여기는 순서만 적는다.

## 0. 처음 받았을 때

```bash
git pull
pip install -r requirements.txt     # pytest, openpyxl
python tools/build.py               # public/data 는 git 에 없다. 이걸 안 하면 웹이 안 뜬다
python -m http.server 8787 --directory public    # 또는 npm run dev
```

http://127.0.0.1:8787 접속. "데이터를 불러오지 못했습니다" 가 뜨면 build.py 를 안 돌린 것이다.
`prepare.py` 는 원자료나 prepare.py 를 바꿨을 때만 돌리면 된다(derived 는 git 에 있다).

## 1. 화면(디자인·문구·동작)만 바꾸기

- 고칠 파일: `public/index.html`, `public/app.js`, `public/styles.css`
- 데이터는 `public/data/*.json` 을 fetch 해서 쓴다. 이 JSON 은 손으로 고치지 않는다
- 브라우저 새로고침으로 확인. 빌드 불필요

화면이 읽는 파일 (`app.js` 의 `main()`):

| 파일 | 내용 |
|---|---|
| `regions.json` | 읍면 8개 × 2시점 지표값 + 지표 정의(`indicators`) |
| `eupmyeon.geojson` | 읍면 경계(`region_code`) |
| `facilities.json` | 경로당 지점 |
| `sources.json` | 출처 패널 |

## 2. 이미 derived 에 있는 값을 화면에 새 지표로 올리기

예: SGIS `households`(가구수)를 코로플레스로 띄우고 싶다.

1. `tools/build.py` 의 `build_regions()` 에서 행 dict 에 값 추가
   (`"households": sgis[code]["households"]`)
2. 같은 파일 `INDICATORS` 에 정의 추가
   (`id` 는 위 키와 같게, `status: "available"`, `unit`, `higher_is_worse`, `reference`)
3. `python tools/build.py` → 새로고침. 지표 목록에 자동으로 생긴다
4. `python -m pytest tools/tests -q`
   (`test_every_available_indicator_has_values` 가 값 누락을 잡는다)

공개하면 안 되는 값(개인정보, 비공개 자료 파생물)은 build.py 에 적지 않는다.

## 3. 새 원자료 추가하기

1. 받은 파일을 그대로 등록 (raw 폴더를 손으로 만들지 말 것)
   ```bash
   python tools/add_source.py --id 새_ID --dir 출처-이름-기준일 --name "..." --provider "..." --url "..." --reference-date YYYY-MM-DD --license "..." --file 받은파일.csv
   ```
   - cp949 파일이면 `--encoding cp949`, 기준일 근거·행수·품질 문제는 `--notes "..."`
   - 원본 페이지를 `capture.html` 로 저장해 같이 `--file` 로 넣는다(URL 이 죽어도 증빙이 남는다)
2. 생성된 `data/raw/<폴더>/_meta.json` 을 열어 빠진 내용을 채운다
3. `data/sources.json` 에 항목 추가 (`id`, `name`, `provider`, `license`, `status` 필수)
4. `tools/prepare.py` 에 `prepare_xxx()` 추가 → `main()` 에서 `write("xxx.json", ...)`
   - 지역은 반드시 `region_code` 로 붙인다 (`_region_code_from_address()` 등 기존 함수 재사용)
   - 행수·합계·범위를 `assert` 로 검증한다
5. `python tools/prepare.py` → `data/derived/xxx.json` 확인
6. `tools/tests/test_prepare.py` 에 알려진 개수 테스트 추가
7. 화면에 올릴 거면 §2, 엑셀에 넣을 거면 §5
8. `docs/data-guide.md` 표에 한 줄 추가

## 4. 원자료를 새 시점으로 갱신하기

예: 2026-12 주민등록 인구.

1. 기존 폴더는 그대로 두고 **새 폴더**로 등록 (§3-1)
2. `prepare.py` 의 `MOIS_PERIODS` 에 `"2026-12"` 추가
3. `python tools/prepare.py`
4. 테스트 기대값(예: 18행 = 2시점×9)이 깨지면 새 값으로 고친다
5. 쓰지 않을 옛 시점은 `MOIS_PERIODS` 에서 빼고 raw 폴더를 지운다(git 기록에 남는다)

## 5. 제출용 엑셀 다시 만들기

```bash
python tools/export_excel.py
```

- 출력: `outputs/군위군_주거환경취약지역_기초지표_2025.xlsx` (+ 같은 이름 `.csv`)
- 시트 3개: `기초지표`(읍면 8행) · `컬럼설명` · `산출방법`
- 열을 추가·변경하려면 `export_excel.py` 의 `COLUMNS`(열 정의)와 `build_rows()`(값)를 같이 고친다
- 엑셀을 열어 둔 채로 실행하면 저장이 실패한다. 닫고 실행

## 6. 배포

- main 에 push 하면 GitHub Actions 가 검증 → Cloudflare 배포까지 자동으로 한다
- 단 Cloudflare 키가 GitHub Secrets 에 없으면 배포 단계는 건너뛴다(현재 그 상태).
  실제로 공개하려면 레포 Settings → Secrets 에 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` 등록
- 실패 원인 1순위: raw/prepare.py 를 바꾸고 `data/derived/` 를 재생성·커밋하지 않음
  → `python tools/prepare.py` 후 derived 변경분까지 커밋
- 커밋 전 로컬 점검:
  ```bash
  python tools/prepare.py
  python -m pytest tools/tests -q
  python tools/build.py
  ```

## 7. 빈집애 자료 다시 받기

```bash
python tools/fetch_binzibe.py          # binzibe-download/ 에 4개 파일 저장. 키 불필요
                                       # 조사연도가 바뀌면 --year (화면 표시는 year - 1 년)
```

1. 받은 4개 파일을 `--file` 로 넘겨 §3-1 처럼 `add_source.py` 로 **새 raw 폴더**에 등록한다
   (기존 폴더는 고치지 않는다)
2. 쓴 `year` 값과 화면 표시 연도를 `--notes` 에 적는다
3. `data/sources.json` 의 `BINZIBE_GUNWI_VACANT_HOUSES` 의 `raw_dir`·`reference_date` 를 갱신한다
4. 공개 Open API 가 아니라 예고 없이 바뀌거나 막힐 수 있다. 실패하면 응답을 고쳐 쓰지 말고 기록만 남긴다

이전 주제의 포트홀 수집기(`tools/fetch_pothole.py`)는 2026-10-30 지웠다. 커밋 `ea23c30` 에서 복구할 수 있다.

## 8. 군청 빈집 실태조사 자료가 들어오면

청구서 초안: `docs/requests/README.md` (아직 발송 안 됨)

1. 소유자·상세 지번 등 개인정보가 섞여 있으면 **공개 저장소에 올리지 않는다** —
   비식별 집계(읍면·리별, 등급별 수)만 raw 에
2. §3 절차로 등록. `--notes` 에 조사연도·조사기준일·등급 기준 문서 여부를 적는다
3. `data/sources.json` 의 `GUNWI_VACANT_SURVEY_INTERNAL` 을 `확보` 로 바꾸고 `raw_dir` 를 채운다
4. 빈집애(`BINZIBE_GUNWI_VACANT_HOUSES`)·통계청 미거주주택과 정의가 다르다.
   값을 합치거나 서로의 분모로 쓰지 않는다(`docs/methodology.md` §2)

## 9. 건축물대장 API 로 수집하기

아직 수집기가 없다. 만들 때 지킬 것:

1. 키는 환경변수 `DATA_GO_KR_KEY` 에서만 읽는다. 코드·파일·로그·커밋에 적지 않는다
   (요청 URL 을 저장할 때도 키를 지운다)
2. 수집기(`tools/fetch_*.py`)는 받기만 한다. 응답은 손대지 않고 `tools/add_source.py` 로
   새 raw 폴더에 등록한다(§3)
3. 조회 범위(법정동·리 코드 목록), 조회일, 응답 건수를 `--notes` 에 남긴다
4. `data/sources.json` 의 `BUILDING_HUB_API` 상태를 갱신한다

## 10. 보고서 그림 다시 만들기

```bash
pip install -r requirements.txt      # matplotlib 포함
python tools/figures.py              # 또는 npm run figures
```

- 출력: `outputs/figures/그림1~2_*.png` (+ 그림2 근거 CSV)
- 값은 `build.py` `build_regions()` 를 그대로 쓴다 — 웹과 같은 숫자
- 기준 시점은 `export_excel.py` 의 `ANALYSIS_PERIOD`(2025-12)
- 한글 글꼴(맑은 고딕·AppleGothic·나눔고딕·Noto CJK) 중 하나가 있어야 한글이 안 깨진다
- CI 는 그림을 만들지 않는다. 그림을 바꿨으면 직접 돌려서 커밋한다
