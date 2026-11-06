# 데이터 설명서: `data/raw` → `data/derived`

`data/raw/` 에 무엇이 있고, `tools/prepare.py` 를 거치면 `data/derived/` 에서
무엇이 되는지 정리한 문서다. 숫자는 2026-10-14 실행 결과 기준(빈집애는 2026-10-30 수집).

```
data/raw/<폴더>/          받은 그대로. 동결. _meta.json = 출처 카드(출처·기준일·sha256)
      │  python tools/prepare.py   (assert 검증. 하나라도 틀리면 멈춘다)
      ▼
data/derived/*.json       정제·검증 통과분. 손으로 고치지 않는다
      │  python tools/build.py     (공개 여부 결정)
      ▼
public/data/*.json        웹 화면용
```

## 한눈에 보기

| raw 폴더 | 원자료 | 기준일 | → derived | 상태 |
|---|---|---|---|---|
| `mois-age-2023-12` | 행안부 연령별 주민등록인구 | 2023-12-31 | `population.json` | 사용 (인구감소 비교 기준) |
| `mois-age-2026-09` | 〃 | 2026-09-30 | `population.json` | 사용 (분석 기준 시점) |
| `boundary-eupmyeon-2025-06-30` | 읍면 경계 GeoJSON (SGIS 2025 2Q) | 2025-06-30 | `eupmyeon.geojson` | 사용 (2026-10-15 출처 확인) |
| `datagokr-gunwi-senior-2025-12-19` | 경로당 표준데이터(군위 215곳) | 2025-12-19 | `senior_centers.json` | 사용 |
| `sgis-admstat-2025-2q` | SGIS 행정구역 통계(2024년) | 2024-12-31 | `sgis_stats.json` | 19개 CSV 중 10개 사용 |
| `binzibe-gunwi-vacant-houses-2025` | 빈집애 읍면별 빈집 수(지자체 행정조사, 8개 읍면 합 602) | 미확인(화면 표시 2025년) | — | 등록만(prepare.py 미연결) |
| `mois-age-2023-07` ~ `mois-age-2026-09` (위 2개 제외 37개) | 행안부 연령별 주민등록인구 월별 | 매월 말일 | — | 등록만(prepare.py 미연결). 2026-11-05 gunwi 저장소에서 이관 |
| `mois-household-2023-07` ~ `mois-household-2026-09` (39개) | 행안부 주민등록 인구 및 세대현황 월별 | 매월 말일 | — | 등록만. 코드 없음 → 같은 달 mois-age 에서 이름으로 붙인다 |
| `gunwi-yearbook-64-2023` | 군위통계연보 제64회 (장별 xlsx zip) | 2023-12-31 | — | 등록만. 10장 주택건설·3장 리별 세대·인구·12장 독거노인 |
| `hira-2026-09` | HIRA 병의원·약국 (보건소·지소·진료소 포함, 전국 zip) | 2026-09 | — | 등록만. 군위 = '대구군위군' 42행 |
| `bus-stops-2026-10-20` | 국토부 전국 버스정류장 (CP949) | 2026-10-20 | — | 등록만. 군위는 좌표로 판정 |
| `sbiz-stores-gunwi-2026-09` | 상가(상권)정보 대구 CSV 중 군위 1,155행 (전국 zip 은 저장소 밖) | 2026-09 | — | 등록만 |
| `mohw-local-health-orgs-2025-12-31` | 보건복지부 지역보건의료기관 (좌표 없음) | 2025-12-31 | — | 등록만. HIRA 대조용 |
| `mois-eupmyeon-offices-2025-12` | 행안부 읍면동 하부행정기관 (좌표 없음) | 2025-12 | — | 등록만 |
| `school-locations-2026-09-20` | 초중등학교위치 | 2026-09-20 | — | 등록만 |
| `childcare-basic-2026-09` | 어린이집 기본정보 (포털 HTML 응답) | 2026-09 | — | 등록만 |
| `kindergarten-general-2026-2` | 유치원알리미 일반현황 (대구) | 2026년 2차 | — | 등록만 |
| `closed-schools-2025-09-30` | 학교알리미 폐교 정보 (주소만) | 2025-09-30 | — | 등록만. 참고용 |
| `vworld-ri-boundary-2026-10-09` | 브이월드 법정리 경계 중 군위 92개 (SHP, EPSG:5186, 전국 zip 은 저장소 밖) | 2026-10-09 | — | 등록만. 리 단위 분석의 공간단위 |
| `bjd-code-2026-09-29` | 국토부 법정동코드 (전국 CSV) | 2026-09-29 | — | 등록만. 군위 법정리 92개 코드 |
| `vworld-gis-building-gunwi-2026-09-09` | GIS건물통합정보 중 군위 54,977건 (SHP 4개를 zip 으로, EPSG:5186, 대구 원본은 저장소 밖) | 2026-09-09 | — | 등록만. 주거 건물 위치·사용승인일 |

분석 제외(raw 삭제) — 2026-10-30 주제 변경(빈집·노후주택 주거환경)으로 뺐다.
`data/sources.json` 에 `status: "분석제외"` 와 사유가 남아 있고, 원본은 git 커밋
`ea23c30` 에서 복구할 수 있다.

| 삭제한 raw 폴더 | 원자료 | 쓰던 derived |
|---|---|---|
| `datagokr-park-2026-03-05` | 도시공원 표준데이터(군위 3건) | `parks.json` |
| `minwon-pothole-2026-10-13` | 권익위 포트홀 민원 좌표(전국) | `potholes.json` |
| `datagokr-gunwi-small-facility-risk-2026-07-15` | 소규모공공시설 위험지정(39건) | `drainage_risk.json` |
| `datagokr-gunwi-water-supply-rate-2025-12-31` | 읍면별 상수도보급률 | `water_supply.json` |
| `daegu-salpiso-reports-2024-11-27` | 대구 살피소 제보 처리현황 | `salpiso.json` |

모든 폴더에 공통으로 있는 파일:

- `_meta.json` — 출처 카드. `prepare.py` 는 `provenance` 필드가 없으면 멈춘다.
- `capture.html` — 내려받은 페이지 화면 보존본(증빙용). 가공에 쓰지 않는다.

## 지역 코드: derived 의 공통 키

derived 의 모든 읍면 단위 값은 **`region_code`(주민등록 행정기관코드)** 로 묶인다.
원자료마다 지역 식별 방식이 달라서 `prepare.py` 가 한 번씩 맞춰 준다.

| 원자료 | 원래 지역 표기 | region_code 로 바꾸는 방법 |
|---|---|---|
| 주민등록 인구 | `2772025000` 등 | 그대로 (기준) |
| 경계 GeoJSON | `ADM_CD` `22520111` 등 | 읍면 **이름**으로 대응 (`prepare_boundary`) |
| SGIS 통계 | `22520111` 등 | 경계에 남긴 `source_adm_cd` 로 대응 |
| 경로당 | 주소 문자열 | 주소 속 읍면 토큰으로 대응 |

| region_code | 읍면 | SGIS/경계 코드 |
|---|---|---|
| `2772000000` | 군위군 **합계** (읍면과 함께 더하지 말 것) | `22520` |
| `2772025000` | 군위읍 | `22520111` |
| `2772031000` | 소보면 | `22520311` |
| `2772032000` | 효령면 | `22520312` |
| `2772033000` | 부계면 | `22520313` |
| `2772034000` | 우보면 | `22520314` |
| `2772035000` | 의흥면 | `22520315` |
| `2772036000` | 산성면 | `22520316` |
| `2772037000` | 삼국유사면 | `22520317` |

---

## 1. 주민등록 인구 → `population.json`

**raw**: `mois-age-2023-12/age.json`, `mois-age-2026-09/age.json` (`prepare.py` `MOIS_PERIODS`)
(행정안전부 jumin.mois.go.kr 조회 결과)

- 시점마다 9행(군 합계 1 + 읍면 8), 행마다 `[코드, 이름, 숫자 69칸]`.
- 69칸 = 성별 블록 3개(계·남·여) × 23칸(총계, 총계 중복, 5세 구간 21개: 0–4세 … 100세 이상).
- 숫자는 `"22,452"` 처럼 쉼표가 들어간 문자열.

**가공** (`prepare_population`)

1. 쉼표 제거 후 정수로 변환.
2. 검증: 블록마다 5세 구간 21개 합 = 총계 / 남 + 여 = 계 / 읍면 8개 합 = 군 합계.
3. 고령인구 `elderly` = 65세 이상 구간(인덱스 13~20) 합.

**derived**: 2시점 × 9행 = 18개 레코드

```json
{"period": "2026-09", "reference_date": "2026-09-30",
 "region_code": "2772025000", "region_name": "군위읍", "level": "eupmyeon",
 "population": 7844, "male": 4087, "female": 3757, "elderly": 2925}
```

- `level`: `gun`(군 합계) / `eupmyeon`.
- 고령화율은 저장하지 않는다. 화면에서 `elderly / population` 으로 계산한다.
- 2026-09 군 전체: 인구 22,432명, 65세 이상 11,334명(50.5%). 2023-12: 22,988명, 10,311명.

## 2. 읍면 경계 → `eupmyeon.geojson`

**raw**: `boundary-eupmyeon-2025-06-30/eupmyeon.geojson` (피처 8개)

- `provenance: verified` (2026-10-15). 원래 다운로드 이력이 없어 UNVERIFIED 였으나,
  SGIS 행정구역 경계 2025 2Q 원본 `bnd_dong_00_2025_2Q.shp` 에서 군위군 8개를 뽑아
  대조한 결과 도형·속성(ADM_CD, ADM_NM, BASE_DATE)이 모두 같았다(IoU 1.000000).
  재현은 `tools/verify_boundary.py`. 파일 자체는 바꾸지 않았다.
- `boundary-alt.geojson` 은 속성 구조가 다른 대체본(출처 미확인). **쓰지 않는다.**

**가공** (`prepare_boundary`)

1. 피처 `ADM_NM` 의 마지막 단어(읍면명)로 인구 데이터의 region_code 를 찾는다.
2. 검증: 피처 8개, 중복 없음, 인구의 읍면 8개와 집합이 같음.
3. 피처 속성을 아래 4개로 **교체**한다(원래 속성은 버린다). 도형은 그대로.

**derived**: 피처 8개 + 최상위 `_provenance: "verified"`

```json
{"region_code": "2772025000", "region_name": "군위읍",
 "source_adm_cd": "22520111", "base_date": "20250630"}
```

- `source_adm_cd` 는 SGIS 통계를 붙일 때 다리로 쓰인다(§4).
- `_provenance` 가 `verified` 가 아니면 웹 화면 상단에 경고 배너가 뜬다(현재는 verified 라 뜨지 않는다).

## 3. 경로당 → `senior_centers.json`

**raw**: `datagokr-gunwi-senior-2025-12-19/15114136_gunwi.csv` (215행, UTF-8 BOM)

- 전국 마을회관·경로당 표준데이터에서 팀원이 군위군만 추출한 파일
  (`provenance: verified_import`, 정부 원본 바이트 아님).
- 컬럼: 시설명, 시설유형, 소재지도로명주소, 소재지지번주소, 위도, 경도, 영업상태명,
  전화번호, 건립일자, 건물면적, 관리기관명, 데이터기준일자.
- 건립일자가 전 행 `YYYY-01-01` 이라 **연도 정밀도**로만 쓸 수 있다.

**가공** (`prepare_senior_centers`)

1. 검증: 시설유형이 모두 `경로당`, 건립일자 형식 유지, 좌표가 군위 범위 안, 이름+주소 중복 없음.
2. 도로명·지번 주소에서 읍면명을 찾아 region_code 부여(두 주소가 다른 읍면이면 멈춤).
3. 건립일자 → `built_year`(연도만).
4. 읍면별 개수와 **노후 경로당 수**(2000년 이전 건립) 집계.

**derived**

```json
{"reference_date": "2025-12-19", "provenance": "verified_import", "old_before_year": 2000,
 "by_region": {"2772025000": {"count": 38, "old_count": 8}, ...},
 "centers": [{"name": "동부1리 경로당", "region_code": "2772025000",
              "address": "대구광역시 군위군 군위읍 동서길 27", "lon": 128.565, "lat": 36.236,
              "built_year": 2009, "floor_area_sqm": 157.56, "status": "영업",
              "reference_date": "2025-12-19", "source_row": 1}, ...]}
```

| 읍면 | 군위읍 | 소보면 | 효령면 | 부계면 | 우보면 | 의흥면 | 산성면 | 삼국유사면 | 계 |
|---|---|---|---|---|---|---|---|---|---|
| 경로당 | 38 | 33 | 36 | 17 | 28 | 28 | 15 | 20 | 215 |
| 2000년 이전 건립 | 8 | 4 | 4 | 5 | 4 | 8 | 4 | 4 | 41 |

- **2000년 기준은 공식 기준이 아니라 프로젝트 임시값**이다(`SENIOR_OLD_BEFORE_YEAR`).
- `source_row` 로 원본 CSV 몇 번째 행인지 추적할 수 있다.

## 4. SGIS 행정구역 통계 → `sgis_stats.json`

**raw**: `sgis-admstat-2025-2q/` CSV 19개 (**cp949**). 전국 파일(269MB zip, 저장소 밖 보관)에서
군위군(SGIS 코드 `22520`) 행만 걸러낸 것. 형식은 모두 같다:

```
기준연도,행정구역코드,통계항목,통계값
2024,22520,to_in_001,21493
```

⚠️ SGIS 제공용 코드는 `22520` 계열이다. 행정구역코드 `27720` 으로 찾으면 0행이 나온다.

**사용하는 10개 파일** (항목코드 1개씩, 군 1 + 읍면 8 = 9행)

| 파일 접미 | 항목코드 | derived 키 | 단위 | 읍면합=군합 검사 |
|---|---|---|---|---|
| 인구총괄(총인구) | `to_in_001` | `population` | 명 | O |
| 인구총괄(평균나이) | `to_in_002` | `avg_age` | 세 | |
| 인구총괄(인구밀도) | `to_in_003` | `density_per_km2` | 명/㎢ | |
| 인구총괄(노령화지수) | `to_in_004` | `aging_index` | 유소년 100명당 고령인구 | |
| 인구총괄(노년부양비) | `to_in_005` | `old_dependency` | 생산연령 100명당 고령인구 | |
| 인구총괄(유년부양비) | `to_in_006` | `young_dependency` | 생산연령 100명당 유소년 | |
| 가구총괄 | `to_ga_001` | `households` | 가구 | O |
| 주택총괄_총주택(거처)수 | `to_ho_001` | `houses` | 호 | O |
| 산업분류별(11차_대분류)_총괄사업체수 | `to_fa_010` | `businesses` | 개 | O |
| 산업분류별(11차_대분류)_총괄종사자수 | `to_em_020` | `employees` | 명 | O |

**아직 읽지 않는 9개 파일**: 건축년도별주택, 주택유형별주택, 연건평별주택, 세대구성별가구,
성연령별인구, 산업분류별 대분류 사업체수·종사자수, 중분류 사업체수·종사자수.
이 중 건축년도별주택(`ho_yr_001`~`ho_yr_020`, 읍면 단위, `N/A` 칸 있음)·주택유형별주택·
연건평별주택은 노후주택 주제의 원천 후보다. 파일은 raw 에 있으나 `prepare.py` 에 연결하지
않았다. 항목코드가 어느 건축연도 구간인지는 SGIS 제공용 코드집으로 확인한 뒤 연결한다.

**가공** (`prepare_sgis_stats`)

1. 경계 derived 의 `source_adm_cd` → `region_code` 대응표로 SGIS 코드를 바꾼다.
2. 검증: 기준연도 2024, 지역코드가 군 1 + 읍면 8.
3. 더할 수 있는 항목(O)은 읍면 8개 합 = 군 합계인지 검산.
4. `N/A`(비공개 소수 셀)는 0 이 아니라 `null` 로 두고 `na_cells` 에 기록 (현재 0칸).
5. 코드 매핑 검산: SGIS 인구가 분석 기준 시점(2026-09) 주민등록 인구와 15% 넘게 다르면 멈춘다.

**derived**

```json
{"reference_date": "2024-12-31", "provenance": "verified",
 "items": {"population": {"sgis_code": "to_in_001", "label": "인구총괄(총인구)", "unit": "명"}, ...},
 "na_cells": [],
 "gun_total": {"population": 21493, "avg_age": 59.2, "density_per_km2": 35.1,
               "aging_index": 1188.7, "old_dependency": 89.6, "young_dependency": 7.5,
               "households": 10883, "houses": 9735, "businesses": 3372, "employees": 9893},
 "by_region": {"2772025000": {"population": 7606, "avg_age": 52.7, ...}, ...}}
```

- SGIS 인구(등록센서스, 2024)와 주민등록 인구(§1)는 **정의가 달라 값이 다르다**
  (군 전체 21,493 vs 22,432). 한 표에서 섞어 쓰지 말 것.

## 5. 빈집애 읍면별 빈집 수 (derived 없음)

**raw**: `binzibe-gunwi-vacant-houses-2025/`

- `rank.json` — 빈집애 지도 내부 API 응답. 읍면 8행, `binCnt` 합 602.
  의흥 112 · 우보 108 · 군위읍 103 · 산성 65 · 소보 65 · 효령 65 · 삼국유사 42 · 부계 42.
- `filter-options.json` — 조사연도 선택지(year=2026 하나. 화면은 '2025년'으로 표시).
- `capture.html`, `capture-map-filter-loader.js` — 지도 페이지와 연도 표시 로직 보존본.
- 수집: `python tools/fetch_binzibe.py` (받기만 한다. 등록은 `add_source.py`).

주의:

- 지자체 빈집행정조사 결과이며 국가승인통계가 아니다(지도 안내문).
- `binzipRateReg` 는 빈집률이 아니라 군 전체 빈집 수 대비 그 읍면의 비중(%)이다.
- 등급·건별 위치는 없다. 조사시점은 사이트에 없어 미확인.
- 같은 정의의 분모(주택 수)가 없어 빈집률을 만들지 않는다. SGIS 주택 수(§4)나
  통계청 미거주주택과 정의가 달라 한 산식에서 섞지 않는다.
- `prepare.py` 에 연결하지 않았다. 연결하면 읍면명(`sojaeji` 끝 단어)으로 region_code 를 붙인다.

## 6. 법정리 경계 → `ri_boundary.geojson`, 시설 리 배정 → `ri_facilities.json`

**raw**: `vworld-ri-boundary-2026-10-09/`(SHP, EPSG:5186), `bjd-code-2026-09-29/`(법정동코드),
생활시설 raw 들(§한눈에 보기). 코드는 `tools/prepare_ri.py`.

**`ri_boundary.geojson`** — 법정리 92개, EPSG:4326 으로 재투영(좌표 소수 6자리).
속성 `ri_code`(10자리) · `ri_name` · `region_code`(읍면) · `region_name` · `base_date`.

검증: 법정동코드의 군위 현행 법정리 92개와 코드·이름 일치, 읍면별 리 수
(군위읍17 소보14 효령15 부계8 우보9 의흥11 산성7 삼국유사11), 모든 도형 유효.

**`ri_facilities.json`** — 시설 점마다 `ri_code`·`region_code`·`ri_method` 를 붙인 목록(`points`)과
리별 개수(`by_ri`).

| 유형 | 자료 | 개수 | 리 배정 | 리별로 세나 |
|---|---|---|---|---|
| 경로당 | 경로당 표준데이터 | 215 | 좌표 → 리 경계 | 예 |
| 보건소·보건지소·보건진료소 | HIRA | 18 | 좌표 | 예 |
| 의원·치과·한의원 / 약국 | HIRA | 17 / 7 | 좌표 | 예 |
| 초·중·고 | 초중등학교위치 | 8 | 좌표 | 예 (원자료 '운영' 8곳 그대로) |
| 어린이집 / 유치원 | 포털 / 유치원알리미 | 4 / 1 | 좌표 | 예 |
| 폐교 | 학교알리미 | 11 | 주소의 읍면·리 이름 (고로면 → 삼국유사면) | 예 |
| 버스정류장 | 국토부 | 725행 | 좌표, 군위 리 안에 드는 것만 | **아니오** — 중복 등록 묶는 기준 미정. 집별 거리에는 미정차 8행을 빼고 717행을 쓴다(`no_stop`) |
| 상가(전 업종) | 상가정보 | 1,155 | 원자료 법정동코드 | 아니오 — 식료품점(슈퍼마켓·편의점 60곳)은 집별 거리(`ri_access.json` `grocery`)로만 쓴다 |

대조(`checks`): 경로당 주소 읍면 215/215, HIRA 읍면동 42/42, 학교 지번주소 리 8/8 일치.
상가는 원자료 법정동코드와 좌표 판정이 9건 다르다 — 큰 건물 하나에 여러 업소가 같은 좌표로
찍혀 리 경계 근처에서 어긋나는 경우라 지번 기준 코드를 따른다.

**`ri_access.json`** — 주거용 건물 10,264동마다 가장 가까운 시설까지 직선거리를 재고 리(`by_ri`)·
읍면(`by_region`)·군(`gun`)별로 묶음마다 `mean_m`·`median_m`·`max_m`·`far_share_pct`(2 km 초과 비율,
임시 기준·모든 묶음 공통)를 낸다. 묶음은 1차 의료 `primary_care`(35) · 보건기관 `health`(18) · 의원 `clinic`(17) ·
약국 `pharmacy`(7) · 버스정류장 `bus_stop`(717, 미정차 제외) · 초등학교 `school_elementary`(4) ·
중·고등학교 `school_secondary`(4) · 어린이집 `childcare`(4)이고, `groups` 에 묶음별 이름·점 유형·
거르는 조건(`filter`)·시설 수(`facilities`)가 있다. 읍면사무소는 좌표가 없어 없다. 버스 거리는 운행 횟수를
반영하지 않는다(산식·한계는 methodology "집별 생활시설 거리"). 건물 단위 값은 derived 에도 남기지 않는다(지번 단위 자료라).

**`ri_housing_age.json`** — 주거용 건물의 노후(사용승인 30년 이상) 비율. 리·읍면·군별로 `old_confirmed_pct`
(확인, 하한), `old_with_estimate_pct`(빈칸+재래식 구조 추정 포함, 주 지표), `blank_pct`(추정 의존도).
산식은 methodology "노후주택".

공개: `build.py` 가 리별 **집계값만** `regions.json` 의 `ri` 와 `ri_boundary.geojson` 으로 내보낸다.
건물·지번 단위 값과 시설 점 목록(`ri_facilities.json` 의 `points`)은 공개하지 않는다.

---

## derived 다음 단계

| derived | `build.py` → `public/data/` | `export_excel.py` → `outputs/` |
|---|---|---|
| `population.json` | `regions.json` 에 합쳐짐(군 합계 행 제거) | 결과표 |
| `sgis_stats.json` | `regions.json` 에 합쳐짐 | 결과표 |
| `senior_centers.json` | `regions.json`(읍면 집계·노후 비율) + `facilities.json`(지점) | 결과표 |
| `eupmyeon.geojson` | 그대로 복사 | — |
| `ri_housing_age.json` · `ri_access.json` | `regions.json` 읍면 행 + `ri`(법정리 92행) | 결과표 열 + `리별지표` 시트·CSV |
| `ri_facilities.json` | `ri` 행의 경로당 수(리별 집계만) | 리별지표 경로당수 |
| `ri_boundary.geojson` | 그대로 복사 | — |

## 저장소에 없는 자료

빈집 등급·위치(군청 실태조사), 건축물대장(리·지번 단위 사용승인일), 통계청 미거주주택 등은
아직 raw 에 없다. 무엇이 어디에 있는지는 `docs/data-survey.md`, 상태는 `data/sources.json`
(`status: "미확보"`)에 있다.

## 원자료를 바꿀 때

1. 새 자료는 **새 폴더**로 받는다(`tools/add_source.py`). 기존 raw 파일은 고치지 않는다.
2. `python tools/prepare.py` — 구조가 바뀌었으면 assert 에서 멈추고 이유를 출력한다.
3. derived 가 이상하면 derived 를 고치지 말고 `prepare.py` 를 고친다.
