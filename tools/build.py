"""data/derived + data/sources.json -> public/data

public/에 넣는 것은 인터넷에 공개된다. 이 파일에 적은 것만 공개되고,
적지 않은 것은 derived/에 남는다 - 이 스크립트가 공개 여부를 결정하는 자리다.

정적 파일(html/js/css)은 복사하지 않는다. public/에 이미 있다.

  python tools/build.py
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from prepare import ANALYSIS_PERIOD, BASELINE_PERIOD

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
REGISTRY = ROOT / "data" / "sources.json"
OUT = ROOT / "public" / "data"

# 웹 화면에 내보내는 출처 필드. 여기서 뺀 필드는 화면에 안 뜬다.
# license는 공공데이터 출처표시 의무가 있어 반드시 포함한다.
SOURCE_FIELDS = [
    "id", "name", "provider", "url", "reference_date",
    "license", "status", "request_status", "used_for", "notes",
]

# 지표 정의. status가 missing이면 화면에서 비활성으로 표시된다.
# 원자료가 없는 지표에 값을 채우지 않는다 - 비활성이 정직한 상태다.
INDICATORS = [
    {"id": "population", "label": "총인구", "unit": "명",
     "status": "available", "higher_is_worse": False},
    {"id": "elderly_ratio", "label": "고령화율", "unit": "%",
     "status": "available", "higher_is_worse": True},
    # 인구 변화: 시계열은 raw 에 두고, 분석 기준 시점(2026-09) 값으로는 기준 시점 대비 변화만 낸다
    {"id": "pop_change_rate", "label": "인구 변화율", "unit": "%",
     "status": "available", "higher_is_worse": False,
     "reference": f"{BASELINE_PERIOD} → {ANALYSIS_PERIOD}"},
    {"id": "pop_change_rate_annual", "label": "연평균 인구 변화율", "unit": "%/년",
     "status": "available", "higher_is_worse": False,
     "reference": f"{BASELINE_PERIOD} → {ANALYSIS_PERIOD}, 연율 환산"},
    {"id": "elderly_ratio_change", "label": "고령화율 변화", "unit": "%p",
     "status": "available", "higher_is_worse": True,
     "reference": f"{BASELINE_PERIOD} → {ANALYSIS_PERIOD}"},
    # 아래 시설·SGIS 지표는 조사 주기가 정해진 자료라 기준일이 다르다. reference 에 적는다
    {"id": "aging_index", "label": "노령화지수", "unit": "",
     "status": "available", "higher_is_worse": True, "reference": "SGIS 2024"},
    {"id": "density_per_km2", "label": "인구밀도", "unit": "명/㎢",
     "status": "available", "higher_is_worse": False, "reference": "SGIS 2024"},
    {"id": "senior_center_count", "label": "경로당 수", "unit": "개소",
     "status": "available", "higher_is_worse": False, "reference": "2025-12-19"},
    {"id": "senior_center_per_1k_elderly", "label": "고령인구 1천명당 경로당", "unit": "개소",
     "status": "available", "higher_is_worse": False,
     "reference": f"경로당 2025-12-19 / 고령인구 {ANALYSIS_PERIOD}"},
    {"id": "senior_center_old_ratio", "label": "노후 경로당 비율", "unit": "%",
     "status": "available", "higher_is_worse": True,
     "reference": "2025-12-19 · 2000년 이전 건립(프로젝트 임시 기준)"},
    {"id": "priority_score", "label": "종합 점수", "unit": "점",
     "status": "blocked",
     "reason": "검증된 가중치 모형이 없다. docs/methodology.md 참고"},
]


def load(name: str):
    return json.loads((DERIVED / name).read_text(encoding="utf-8"))


def months_between(start: str, end: str) -> int:
    """'YYYY-MM' 두 시점 사이 개월 수."""
    (ys, ms), (ye, me) = (map(int, p.split("-")) for p in (start, end))
    return (ye - ys) * 12 + (me - ms)


def build_regions() -> dict:
    """분석 기준 시점(ANALYSIS_PERIOD) 읍면 8개. 군 합계 행은 내보내지 않는다(중복 합산 방지).

    한 시점 진단이다(2026-11-05 결정). 기준 시점(BASELINE_PERIOD) 인구는 화면 행으로
    내보내지 않고 변화율 계산에만 쓴다. 산식은 docs/methodology.md §1.
    """
    pop = load("population.json")
    sgis = load("sgis_stats.json")["by_region"]
    seniors = load("senior_centers.json")["by_region"]
    eup = [r for r in pop["records"] if r["level"] == "eupmyeon"]
    base = {r["region_code"]: r for r in eup if r["period"] == BASELINE_PERIOD}
    cur = [r for r in eup if r["period"] == ANALYSIS_PERIOD]
    assert len(base) == 8 and len(cur) == 8, "기준·분석 시점 읍면이 각 8개가 아님"
    months = months_between(BASELINE_PERIOD, ANALYSIS_PERIOD)
    assert months > 0
    rows: list[dict] = []

    for rec in cur:
        code = rec["region_code"]
        b = base[code]
        ratio_now = rec["elderly"] / rec["population"] * 100
        ratio_base = b["elderly"] / b["population"] * 100
        rows.append({
            "region_code": code,
            "name": rec["region_name"],
            "population": rec["population"],
            "elderly": rec["elderly"],
            "elderly_ratio": round(ratio_now, 1),
            "population_baseline": b["population"],
            "elderly_baseline": b["elderly"],
            "pop_change_rate": round((rec["population"] - b["population"]) / b["population"] * 100, 1),
            "pop_change_rate_annual": round(
                ((rec["population"] / b["population"]) ** (12 / months) - 1) * 100, 2),
            "elderly_ratio_change": round(ratio_now - ratio_base, 1),
            "aging_index": sgis[code]["aging_index"],
            "density_per_km2": sgis[code]["density_per_km2"],
            "senior_center_count": seniors[code]["count"],
            "senior_center_old_count": seniors[code]["old_count"],
            "senior_center_old_ratio": round(
                seniors[code]["old_count"] / seniors[code]["count"] * 100, 1),
            "senior_center_per_1k_elderly": round(
                seniors[code]["count"] / rec["elderly"] * 1000, 1),
        })

    rows.sort(key=lambda r: r["region_code"])
    ref = {r["period"]: r["reference_date"] for r in pop["records"]}
    return {
        "meta": {
            "generated_at": date.today().isoformat(),
            "analysis_period": ANALYSIS_PERIOD,
            "baseline_period": BASELINE_PERIOD,
            "change_months": months,
            "default_period": ANALYSIS_PERIOD,
            "reference_dates": {ANALYSIS_PERIOD: ref[ANALYSIS_PERIOD],
                                BASELINE_PERIOD: ref[BASELINE_PERIOD]},
        },
        "indicators": INDICATORS,
        # 키를 시점으로 두는 것은 figures·테스트와의 호환 때문이다. 시점은 하나뿐이다
        "regions": {ANALYSIS_PERIOD: rows},
    }


def build_facilities() -> dict:
    """지도 마커용 시설 지점. 화면에 필요한 필드만 골라 내보낸다."""
    seniors = load("senior_centers.json")
    return {
        "senior_centers": {
            "reference_date": seniors["reference_date"],
            "old_before_year": seniors["old_before_year"],
            "points": [
                {k: c[k] for k in ("name", "region_code", "lat", "lon", "built_year")}
                for c in seniors["centers"]],
        },
    }


def build_sources() -> dict:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    out = []
    for s in reg["sources"]:
        missing = [f for f in ("id", "name", "provider", "license", "status")
                   if not s.get(f)]
        assert not missing, f"{s.get('id')}: 필수 필드 누락 {missing}"
        out.append({f: s.get(f) for f in SOURCE_FIELDS})
    return {
        "schema_version": reg["schema_version"],
        "verified_at": reg["verified_at"],
        "sources": out,
    }


def main() -> None:
    # stale 파일이 배포될 수 없게 매번 비우고 다시 쓴다
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    def write(name: str, obj) -> None:
        path = OUT / name
        indent = None if name.endswith(".geojson") else 2
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n",
                        encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")

    boundary = load("eupmyeon.geojson")

    print("public/data 생성:")
    write("regions.json", build_regions())
    write("eupmyeon.geojson", boundary)
    write("facilities.json", build_facilities())
    write("sources.json", build_sources())

    if boundary.get("_provenance") != "verified":
        print(f"  ! 경계 출처 {boundary['_provenance']} "
              "- 화면 상단에 경고 배너가 뜹니다")


if __name__ == "__main__":
    main()
