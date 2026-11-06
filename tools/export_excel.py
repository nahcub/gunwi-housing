"""data/derived -> outputs/ 제출용 엑셀·CSV

읍면 8개를 한 행씩 놓은 결과표를 만든다. derived 만 읽고 raw 는 읽지 않는다.
종합 점수는 계산하지 않는다. '종합점수' 열은 그 사실을 남기려고 비워 둔다.

  python tools/export_excel.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
REGISTRY = ROOT / "data" / "sources.json"
OUT = ROOT / "outputs"
BASENAME = "군위군_주거환경취약지역_기초지표_2026-09"
RI_BASENAME = "군위군_주거환경취약지역_리별지표_2026-09"

from prepare import ANALYSIS_PERIOD, BASELINE_PERIOD  # noqa: E402  기준 시점은 prepare.py 한 곳에서 정한다
import build  # noqa: E402  인구 변화율 산식은 build.build_regions() 하나만 쓴다(웹과 같은 숫자)
SIGUNGU = "군위군"

# (컬럼명, 자료형, 단위, 설명) - 결과표 열 순서와 컬럼설명 시트를 한 곳에서 정한다
COLUMNS = [
    ("종합점수", "실수", "점", "계산하지 않는다. 근거 있는 가중치가 없어 비워 둔다 (docs/methodology.md §3)"),
    ("행정구역코드", "문자열", "", "행정안전부 행정기관코드 10자리. 조인키. 정수로 바꾸면 조인이 깨진다"),
    ("시군구명", "문자열", "", "군 이름"),
    ("읍면명", "문자열", "", "읍·면 이름"),
    ("총인구", "정수", "명", f"{ANALYSIS_PERIOD} 말 주민등록 인구 (행정안전부)"),
    ("고령인구", "정수", "명", "65세 이상 주민등록 인구"),
    ("고령화율", "실수", "%", "고령인구 / 총인구 × 100"),
    ("기준시점인구", "정수", "명", f"{BASELINE_PERIOD} 말 주민등록 인구. 인구 변화율의 분모"),
    ("인구변화율", "실수", "%", f"(총인구 - 기준시점인구) / 기준시점인구 × 100. {BASELINE_PERIOD} → {ANALYSIS_PERIOD}"),
    ("연평균인구변화율", "실수", "%/년", "((총인구 / 기준시점인구)^(12 / 개월수) - 1) × 100. 기간이 1년 단위가 아니라 연율로 환산"),
    ("고령화율변화", "실수", "%p", f"{ANALYSIS_PERIOD} 고령화율 - {BASELINE_PERIOD} 고령화율"),
    ("노령화지수", "실수", "", "유소년(0~14세) 100명당 고령인구. SGIS 2024년 (등록센서스)"),
    ("노년부양비", "실수", "", "생산연령(15~64세) 100명당 고령인구. SGIS 2024년"),
    ("평균나이", "실수", "세", "SGIS 2024년"),
    ("인구밀도", "실수", "명/㎢", "SGIS 2024년. SGIS 인구 기준이라 위 총인구와 분모가 다르다"),
    ("가구수", "정수", "가구", "SGIS 2024년 일반가구"),
    ("경로당수", "정수", "개소", "주소 기준 해당 읍면 소재 경로당 (2025-12-19 기준)"),
    ("노후경로당수", "정수", "개소", "건립연도 2000년 이전. 공식 기준이 아닌 프로젝트 임시 기준"),
    ("노후경로당비율", "실수", "%", "노후경로당수 / 경로당수 × 100"),
    ("고령인구1천명당_경로당수", "실수", "개소", "경로당수 / 고령인구 × 1,000"),
    ("중심위도", "실수", "도", "읍면 경계의 면적가중 중심점. EPSG:4326"),
    ("중심경도", "실수", "도", "읍면 경계의 면적가중 중심점. EPSG:4326"),
]

# 주거용 건물 기반 열 - 읍면 결과표와 리별 시트가 같은 정의를 쓴다 (컬럼명, 자료형, 단위, 설명, build 필드)
HOUSING_COLUMNS = [
    ("주거용건물수", "정수", "동", "GIS건물통합정보(2026-09-09) 용도 단독·공동주택 건물 수. 빈집 포함", "houses"),
    ("노후주택비율", "실수", "%", "사용승인 30년 이상(1996-09-30 이전) + 사용승인일 빈칸 중 재래식 구조(목·조적·블록·벽돌·석) 추정. 분모는 주거용 건물 전체. 30년은 프로젝트 기준", "old_house_ratio"),
    ("노후주택비율_확인분", "실수", "%", "사용승인일로 30년 이상이 확인된 집만 (하한)", "old_house_confirmed_ratio"),
    ("사용승인일빈칸비율", "실수", "%", "사용승인일이 없는 주거용 건물 비율. 노후 추정에 기댄 정도", "approval_blank_ratio"),
    ("1차의료_평균거리", "정수", "m", "집에서 가장 가까운 보건기관(보건소·지소·진료소) 또는 의원까지 직선거리 평균. 도로망 미사용", "primary_care_mean_m"),
    ("1차의료_2km밖_비율", "실수", "%", "가장 가까운 1차 의료가 2,000 m 넘게 떨어진 집 비율. 2 km 는 프로젝트 임시 기준", "primary_care_far_pct"),
    ("보건기관_평균거리", "정수", "m", "가장 가까운 보건소·보건지소·보건진료소까지 직선거리 평균", "health_mean_m"),
    ("의원_평균거리", "정수", "m", "가장 가까운 의원·치과·한의원까지 직선거리 평균", "clinic_mean_m"),
    ("약국_평균거리", "정수", "m", "가장 가까운 약국까지 직선거리 평균. 의약분업 예외지역 여부는 확인하지 않음", "pharmacy_mean_m"),
]
_pos = next(i for i, c in enumerate(COLUMNS) if c[0] == "중심위도")
COLUMNS[_pos:_pos] = [c[:4] for c in HOUSING_COLUMNS]

RI_COLUMNS = [
    ("법정리코드", "문자열", "", "법정동코드 10자리(시군구 27720 + 읍면 3 + 리 2). 조인키"),
    ("읍면명", "문자열", "", "읍·면 이름"),
    ("리명", "문자열", "", "법정리 이름. 이름이 같은 리가 있으니(수서리·달산리) 코드로 구분"),
    *[c[:4] for c in HOUSING_COLUMNS],
    ("경로당수", "정수", "개소", "리 경계 안 경로당 (2025-12-19 기준)"),
]


def load(name: str):
    return json.loads((DERIVED / name).read_text(encoding="utf-8"))


def _ring_centroid(ring: list) -> tuple[float, float, float]:
    """평면 근사 면적과 중심점. 읍면 크기에서는 경위도 평면 근사로 충분하다."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a /= 2
    return a, cx / (6 * a), cy / (6 * a)


def centroid(geom: dict) -> tuple[float, float]:
    """(위도, 경도). 구멍은 음의 면적으로 빼서 면적가중 평균한다."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    total = sx = sy = 0.0
    for poly in polys:
        for k, ring in enumerate(poly):
            a, x, y = _ring_centroid(ring)
            a = abs(a) if k == 0 else -abs(a)
            total += a
            sx += a * x
            sy += a * y
    return sy / total, sx / total


def build_rows() -> list[dict]:
    pop = [r for r in load("population.json")["records"]
           if r["period"] == ANALYSIS_PERIOD and r["level"] == "eupmyeon"]
    assert len(pop) == 8, f"{ANALYSIS_PERIOD} 읍면 인구가 8행이 아님: {len(pop)}"
    sgis = load("sgis_stats.json")["by_region"]
    seniors = load("senior_centers.json")["by_region"]
    shapes = {f["properties"]["region_code"]: f["geometry"]
              for f in load("eupmyeon.geojson")["features"]}

    change = {r["region_code"]: r for r in build.build_regions()["regions"][ANALYSIS_PERIOD]}

    rows = []
    for p in sorted(pop, key=lambda r: r["region_code"]):
        code = p["region_code"]
        c = change[code]
        lat, lon = centroid(shapes[code])
        rows.append({
            "종합점수": None,
            "행정구역코드": code,
            "시군구명": SIGUNGU,
            "읍면명": p["region_name"],
            "총인구": p["population"],
            "고령인구": p["elderly"],
            "고령화율": round(p["elderly"] / p["population"] * 100, 2),
            "기준시점인구": c["population_baseline"],
            "인구변화율": c["pop_change_rate"],
            "연평균인구변화율": c["pop_change_rate_annual"],
            "고령화율변화": c["elderly_ratio_change"],
            "노령화지수": sgis[code]["aging_index"],
            "노년부양비": sgis[code]["old_dependency"],
            "평균나이": sgis[code]["avg_age"],
            "인구밀도": sgis[code]["density_per_km2"],
            "가구수": sgis[code]["households"],
            "경로당수": seniors[code]["count"],
            "노후경로당수": seniors[code]["old_count"],
            "노후경로당비율": round(seniors[code]["old_count"] / seniors[code]["count"] * 100, 2),
            "고령인구1천명당_경로당수": round(seniors[code]["count"] / p["elderly"] * 1000, 2),
            **{c[0]: change[code][c[4]] for c in HOUSING_COLUMNS},
            "중심위도": round(lat, 6),
            "중심경도": round(lon, 6),
        })
    assert [c[0] for c in COLUMNS] == list(rows[0]), "COLUMNS 와 결과표 열이 어긋남"
    return rows


def build_ri_rows() -> list[dict]:
    """법정리 92개 행 - build.build_ri_rows() 의 값을 그대로 쓴다(웹과 같은 숫자)."""
    rows = []
    for r in build.build_ri_rows():
        rows.append({
            "법정리코드": r["ri_code"], "읍면명": r["region_name"], "리명": r["name"],
            **{c[0]: r[c[4]] for c in HOUSING_COLUMNS},
            "경로당수": r["senior_center_count"],
        })
    assert [c[0] for c in RI_COLUMNS] == list(rows[0]), "RI_COLUMNS 와 리별 시트 열이 어긋남"
    return rows


def method_rows() -> list[tuple[str, str]]:
    reg = {s["id"]: s for s in json.loads(REGISTRY.read_text(encoding="utf-8"))["sources"]}
    used = ["MOIS_AGE", "SGIS_ADM_STAT_2025", "DATAGOKR_GUNWI_SENIOR", "BOUNDARY_EUPMYEON",
            "GIS_BUILDING_INTEGRATED", "HIRA_HOSPITAL_PHARMACY", "VWORLD_RI_BOUNDARY"]
    excluded = [s for s in reg.values() if s["status"] == "분석제외"]

    rows = [
        ("■ 개요", ""),
        ("데이터셋", "대구광역시 군위군 읍면별 주거환경 취약지역 기초지표"),
        ("공간 단위", "읍·면 8곳 (군위읍, 소보·효령·부계·우보·의흥·산성·삼국유사면) + "
                     "'리별지표' 시트는 법정리 92곳 (인구·고령화는 리별 자료가 없어 읍면에만 있다)"),
        ("기준 시점", f"분석 기준 {ANALYSIS_PERIOD} 말(주민등록 인구). 인구 변화는 {BASELINE_PERIOD} 말 대비. "
                     "조사 주기가 정해진 자료는 최근 조사분: SGIS 2024년 / 경로당 2025-12-19"),
        ("좌표계", "EPSG:4326 (WGS84)"),
        ("", ""),
        ("■ 산출식", ""),
        ("종합 점수", "계산하지 않는다. 지표 간 척도가 달라(건수·비율·지수) 표준화와 가중치 근거가 "
                     "없으므로 '종합점수' 열을 비워 두었다"),
        ("고령화율", "65세 이상 인구 ÷ 총인구 × 100"),
        ("고령인구1천명당_경로당수", "경로당수 ÷ 고령인구 × 1,000"),
        ("인구변화율", f"(분석 시점 인구 - 기준 시점 인구) ÷ 기준 시점 인구 × 100 ({BASELINE_PERIOD} → {ANALYSIS_PERIOD})"),
        ("연평균인구변화율", "((분석 시점 인구 ÷ 기준 시점 인구)^(12 ÷ 개월수) - 1) × 100"),
        ("노후경로당수", "건립연도 < 2000. 공식 기준이 아니라 프로젝트 임시 기준"),
        ("노후주택비율", "(사용승인 30년 이상 + 사용승인일 빈칸·재래식 구조) ÷ 주거용 건물. 빈칸 집의 98% 가 "
                       "목·조적·블록·벽돌·석조라 옛집으로 추정. 확인분만의 비율과 빈칸 비율을 함께 본다"),
        ("1차의료_평균거리", "주거용 건물 중심점마다 가장 가까운 보건기관·의원까지 직선거리를 재고 평균. "
                          "도로망을 쓰지 않아 실제 이동거리보다 짧다. HIRA 대율보건진료소 좌표 오류 1건 보정"),
        ("", ""),
        ("■ 자료 출처", ""),
    ]
    for sid in used:
        s = reg[sid]
        rows.append((s["name"], f"{s['provider']} | 기준일 {s['reference_date']} | "
                                f"{s['url'] or 'URL 미확인'}"))
    rows += [
        ("", ""),
        ("■ 알아둘 점", ""),
        ("표본 수", "읍면이 8곳뿐이라 상관분석은 탐색적 수준이다. 유의성 해석에 주의"),
        ("두 가지 인구", "총인구·고령인구는 주민등록(" + ANALYSIS_PERIOD + "), 노령화지수·인구밀도 등은 SGIS 등록센서스"
                      "(2024)다. 정의가 달라 값이 다르므로 한 지표 안에서 섞지 말 것"),
        ("경계 출처", "읍면 경계는 통계청 SGIS 행정구역 경계 2025년 2분기(기준일 2025-06-30). "
                    "2026-10-15 SGIS 원본과 8개 읍면 도형 일치 확인"),
        ("", ""),
        ("■ 분석에서 제외한 자료", ""),
    ]
    for s in excluded:
        reason = s["notes"].split("사유: ", 1)[-1].split(". 원본은", 1)[0]
        rows.append((s["name"], reason))
    rows += [
        ("", ""),
        ("■ 함께 제공하는 파일", ""),
        (f"{BASENAME}.csv", "결과표를 개방 포맷으로 (기계 판독용). 내용은 이 파일 1번 시트와 같다"),
        (f"{RI_BASENAME}.csv", "리별지표 시트를 개방 포맷으로"),
        ("data/sources.json", "출처·기준일·확보 상태를 구조화한 출처 레지스트리"),
        ("tools/prepare.py · tools/export_excel.py", "원자료 → 정제 → 이 파일까지의 재현 코드"),
    ]
    return rows


HEADER_FONT = Font(bold=True, size=10, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
SECTION_FONT = Font(bold=True)
THIN = Side(style="thin")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _sheet(ws, header: list[str], body: list[list], widths: list[float]) -> None:
    ws.append(header)
    for row in body:
        ws.append(row)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows():
        for cell in row:
            cell.border = BORDER
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"


def main() -> None:
    rows = build_rows()
    header = [c[0] for c in COLUMNS]
    OUT.mkdir(exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "기초지표"
    _sheet(ws, header, [[r[h] for h in header] for r in rows],
           [8, 13, 9, 11] + [13] * (len(header) - 4))
    for cell in ws["B"][1:]:
        cell.number_format = "@"          # 코드는 문자열로 둔다

    ri_rows = build_ri_rows()
    ri_header = [c[0] for c in RI_COLUMNS]
    ws_ri = wb.create_sheet("리별지표")
    _sheet(ws_ri, ri_header, [[r[h] for h in ri_header] for r in ri_rows],
           [13, 10, 10] + [13] * (len(ri_header) - 3))
    for cell in ws_ri["A"][1:]:
        cell.number_format = "@"

    _sheet(wb.create_sheet("컬럼설명"), ["시트", "컬럼명", "자료형", "단위", "설명"],
           [["기초지표", *c] for c in COLUMNS] + [["리별지표", *c] for c in RI_COLUMNS[:3]] +
           [["리별지표", *RI_COLUMNS[-1]]], [10, 24, 9, 8, 84])

    ws3 = wb.create_sheet("산출방법")
    _sheet(ws3, ["구분", "내용"], [list(r) for r in method_rows()], [26, 112])
    for row in ws3.iter_rows(min_row=2):
        if str(row[0].value or "").startswith("■"):
            row[0].font = SECTION_FONT
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    xlsx = OUT / f"{BASENAME}.xlsx"
    wb.save(xlsx)
    with open(OUT / f"{BASENAME}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)

    print(f"  {xlsx.relative_to(ROOT)}  (읍면 {len(rows)}행 x {len(header)}열)")
    print(f"  {(OUT / f'{BASENAME}.csv').relative_to(ROOT)}")
    with open(OUT / f"{RI_BASENAME}.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ri_header)
        w.writeheader()
        w.writerows(ri_rows)
    print(f"  리별지표 시트 (법정리 {len(ri_rows)}행) + {(OUT / f'{RI_BASENAME}.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
