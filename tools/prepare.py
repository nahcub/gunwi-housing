"""data/raw -> data/derived

원자료를 검증하고 정제해 derived/에 쓴다. raw/는 절대 수정하지 않는다.
검증에 실패하면 assert로 멈춘다 - 조용히 넘어가지 않는다.

  python tools/prepare.py
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"

# 주민등록 인구 파일이 제공하는 기준시점별 폴더
# 2023-12·2024-12 는 분석에 쓰지 않아 raw 에서 삭제했다(커밋 38c9139 에서 복구 가능)
MOIS_PERIODS = ["2025-12", "2026-08"]

GUNWI_CODE = "2772000000"        # 군 합계 행. 읍면과 절대 함께 더하지 않는다
ELDERLY_FROM_BUCKET = 13         # 5세 구간 인덱스 13 == 65세
SEX_BLOCKS = {"total": 0, "male": 23, "female": 46}
GUNWI_BBOX = (128.3, 35.9, 128.9, 36.5)   # lon_min, lat_min, lon_max, lat_max


def _num(value) -> int:
    return int(str(value).replace(",", "").strip())


def read_meta(folder: str) -> dict:
    meta = json.loads((RAW / folder / "_meta.json").read_text(encoding="utf-8"))
    assert meta.get("provenance"), f"{folder}: provenance 필드 없음"
    return meta


# ---------------------------------------------------------------- 인구

def prepare_population():
    """행정안전부 연령별 인구. 2개 시점 x (군 합계 1 + 읍면 8) = 18행."""
    records = []
    name_by_code = {}

    for period in MOIS_PERIODS:
        folder = f"mois-age-{period}"
        meta = read_meta(folder)
        rows = json.loads((RAW / folder / "age.json").read_text(encoding="utf-8"))

        assert len(rows) == 9, f"{folder}: 9행이어야 하는데 {len(rows)}행"

        gunwi_total = None
        eupmyeon_total = 0
        for row in rows:
            code, name = row[0], row[1]
            nums = [_num(v) for v in row[2:]]
            assert len(nums) == 69, f"{folder}/{name}: 69칸이어야 하는데 {len(nums)}칸"

            # 성별 블록마다 5세 구간 21개의 합이 그 블록 총계와 같아야 한다
            block = {}
            for label, off in SEX_BLOCKS.items():
                buckets = nums[off + 2: off + 23]
                assert len(buckets) == 21
                assert nums[off] == sum(buckets), (
                    f"{folder}/{name}/{label}: 구간합 != 총계")
                block[label] = nums[off]

            assert block["total"] == block["male"] + block["female"], (
                f"{folder}/{name}: 남+여 != 계")

            elderly = sum(nums[2 + ELDERLY_FROM_BUCKET: 2 + 21])
            is_gunwi = code == GUNWI_CODE

            records.append({
                "period": period,
                "reference_date": meta["reference_date"],
                "region_code": code,
                "region_name": name,
                "level": "gun" if is_gunwi else "eupmyeon",
                "population": block["total"],
                "male": block["male"],
                "female": block["female"],
                "elderly": elderly,
            })

            if is_gunwi:
                gunwi_total = block["total"]
            else:
                eupmyeon_total += block["total"]
                name_by_code[code] = name

        assert gunwi_total is not None, f"{folder}: 군 합계 행이 없다"
        assert eupmyeon_total == gunwi_total, (
            f"{folder}: 읍면 합계 {eupmyeon_total} != 군 합계 {gunwi_total}")

    assert len(name_by_code) == 8, f"읍면이 8개가 아님: {len(name_by_code)}"
    assert len(records) == len(MOIS_PERIODS) * 9
    return records, name_by_code


# ---------------------------------------------------------------- 경계

def prepare_boundary(name_by_code: dict) -> dict:
    """읍면 경계에 region_code를 심는다.

    원본 피처는 ADM_CD(22520111 계열)를 갖는데 인구 데이터의 행정기관코드
    (2772025000 계열)와 다른 체계다. 지역명으로 여기서 한 번만 맞춰 코드를
    심고, 이후 웹에서는 코드만 쓴다 - 런타임 이름 매칭을 없앤다.
    """
    folder = "boundary-eupmyeon-2025-06-30"
    meta = read_meta(folder)
    gj = json.loads((RAW / folder / "eupmyeon.geojson").read_text(encoding="utf-8"))

    assert len(gj["features"]) == 8, (
        f"경계 피처가 8개가 아님: {len(gj['features'])}")

    code_by_name = {v: k for k, v in name_by_code.items()}
    assert len(code_by_name) == 8, "읍면 이름이 중복됨"

    seen = set()
    for feat in gj["features"]:
        props = feat["properties"]
        raw_name = str(props.get("ADM_NM") or props.get("adm_nm") or "")
        name = raw_name.split()[-1] if raw_name else ""
        assert name in code_by_name, f"인구 데이터에 없는 읍면: {raw_name!r}"
        code = code_by_name[name]
        assert code not in seen, f"경계 피처 중복: {name}"
        seen.add(code)
        feat["properties"] = {
            "region_code": code,
            "region_name": name,
            "source_adm_cd": props.get("ADM_CD"),
            "base_date": props.get("BASE_DATE"),
        }

    assert seen == set(name_by_code), "경계와 인구의 읍면 집합이 다름"

    gj["_provenance"] = meta["provenance"]
    if meta["provenance"] != "verified":
        print(f"  ! 경계 출처 미확인 ({meta['provenance']}) "
              "- 화면에 경고가 표시됩니다")
    return gj


# ------------------------------------------------------------ 시설 공통

def _read_csv(folder: str, meta: dict) -> list[dict]:
    """_meta.json 에 등록된 CSV 하나를 읽는다. 인코딩은 meta 를 따른다."""
    names = [n for n in meta["files"] if n.endswith(".csv")]
    assert len(names) == 1, f"{folder}: CSV가 하나가 아님 {names}"
    text = (RAW / folder / names[0]).read_bytes().decode(
        meta.get("encoding", "utf-8-sig"))
    return list(csv.DictReader(io.StringIO(text)))


def _region_code_from_address(code_by_name: dict, *addresses: str) -> str:
    """주소의 읍면 토큰으로 region_code 를 정한다 - 빌드 시점에 한 번만.

    도로명·지번 주소가 서로 다른 읍면을 가리키면 멈춘다.
    """
    found = {tok for addr in addresses for tok in (addr or "").split()
             if tok in code_by_name}
    assert len(found) == 1, f"주소에서 읍면을 하나로 정할 수 없음: {addresses} -> {found}"
    return code_by_name[found.pop()]


def _check_bbox(lon: float, lat: float, label: str) -> None:
    lon_min, lat_min, lon_max, lat_max = GUNWI_BBOX
    assert lon_min <= lon <= lon_max and lat_min <= lat <= lat_max, (
        f"{label}: 군위군 범위 밖 좌표 ({lon}, {lat})")


# ---------------------------------------------------------------- 경로당

# 노후 판정 기준 연도. 공식 기준이 아니라 프로젝트 임시값이다 - 확정되면 여기만 바꾼다
SENIOR_OLD_BEFORE_YEAR = 2000


def prepare_senior_centers(name_by_code: dict) -> dict:
    """경로당 215곳에 region_code 와 건립연도를 붙이고 읍면별로 센다."""
    folder = "datagokr-gunwi-senior-2025-12-19"
    meta = read_meta(folder)
    rows = _read_csv(folder, meta)
    code_by_name = {v: k for k, v in name_by_code.items()}

    centers = []
    for i, r in enumerate(rows, start=1):
        label = f"{folder}/{i}행 {r['시설명']}"
        assert r["시설유형"] == "경로당", f"{label}: 시설유형 {r['시설유형']!r}"
        built = r["건립일자"].strip()
        # 원본은 전 행 YYYY-01-01 - 월일은 의미가 없으므로 연도만 쓴다
        assert len(built) == 10 and built.endswith("-01-01"), (
            f"{label}: 건립일자 형식이 바뀜 {built!r}")
        lon, lat = float(r["경도"]), float(r["위도"])
        _check_bbox(lon, lat, label)
        centers.append({
            "name": r["시설명"],
            "region_code": _region_code_from_address(
                code_by_name, r["소재지도로명주소"], r["소재지지번주소"]),
            "address": r["소재지도로명주소"] or r["소재지지번주소"],
            "lon": lon,
            "lat": lat,
            "built_year": int(built[:4]),
            "floor_area_sqm": float(r["건물면적"]) if r["건물면적"] else None,
            "status": r["영업상태명"],
            "reference_date": r["데이터기준일자"],
            "source_row": i,
        })

    assert len({(c["name"], c["address"]) for c in centers}) == len(centers), (
        "경로당 이름+주소 중복")

    by_region = {}
    for code in name_by_code:
        mine = [c for c in centers if c["region_code"] == code]
        by_region[code] = {
            "count": len(mine),
            "old_count": sum(c["built_year"] < SENIOR_OLD_BEFORE_YEAR for c in mine),
        }
    assert sum(v["count"] for v in by_region.values()) == len(centers)

    return {
        "reference_date": meta["reference_date"],
        "provenance": meta["provenance"],
        "old_before_year": SENIOR_OLD_BEFORE_YEAR,
        "_note": "노후 기준 연도는 공식 기준이 아닌 프로젝트 임시값. 건립연도는 연도 정밀도.",
        "by_region": by_region,
        "centers": centers,
    }


# ---------------------------------------------------------------- SGIS 통계

SGIS_FOLDER = "sgis-admstat-2025-2q"
SGIS_GUN_CODE = "22520"           # SGIS 체계의 군 합계 코드
# 파일명이 의미를 정해 주는 총괄 항목만 쓴다. 건축년도·주택유형·연건평 등
# 주택 세부 항목은 사유 재산이라 공공시설 관리 분석 범위 밖이므로 쓰지 않는다.
SGIS_ITEMS = {
    # 항목코드: (파일명 접미, 출력 키, 단위, 읍면합 == 군합 검사 여부)
    "to_in_001": ("인구총괄(총인구)", "population", "명", True),
    "to_in_002": ("인구총괄(평균나이)", "avg_age", "세", False),
    "to_in_003": ("인구총괄(인구밀도)", "density_per_km2", "명/㎢", False),
    "to_in_004": ("인구총괄(노령화지수)", "aging_index", "유소년 100명당 고령인구", False),
    "to_in_005": ("인구총괄(노년부양비)", "old_dependency", "생산연령 100명당 고령인구", False),
    "to_in_006": ("인구총괄(유년부양비)", "young_dependency", "생산연령 100명당 유소년", False),
    "to_ga_001": ("가구총괄", "households", "가구", True),
    "to_ho_001": ("주택총괄_총주택(거처)수", "houses", "호", True),
    "to_fa_010": ("산업분류별(11차_대분류)_총괄사업체수", "businesses", "개", True),
    "to_em_020": ("산업분류별(11차_대분류)_총괄종사자수", "employees", "명", True),
}
# SGIS 인구(등록센서스)와 주민등록 인구는 정의가 달라 같지 않다. 매핑이
# 뒤바뀌면 수배 차이가 나므로 이 정도 허용 폭이면 뒤바뀜만 잡는다.
SGIS_POP_TOLERANCE = 0.15


def prepare_sgis_stats(boundary: dict, population: list) -> dict:
    """SGIS 행정구역 통계(2024년)를 읍면별로 정리한다.

    SGIS 코드(22520111 계열)는 경계 원본 ADM_CD 와 같은 체계다. prepare_boundary()
    가 심어 둔 source_adm_cd -> region_code 대응을 그대로 써서, 코드 변환을
    한 곳에만 둔다.
    """
    meta = read_meta(SGIS_FOLDER)
    region_by_sgis = {f["properties"]["source_adm_cd"]: f["properties"]["region_code"]
                      for f in boundary["features"]}
    assert len(region_by_sgis) == 8, "경계에서 SGIS 코드 8개를 얻지 못함"

    by_region = {code: {} for code in region_by_sgis.values()}
    gun = {}
    na_cells = []
    for item, (suffix, key, _unit, additive) in SGIS_ITEMS.items():
        name = f"2025년기준_2024년_{suffix}.csv"
        assert name in meta["files"], f"{SGIS_FOLDER}: _meta.json 에 없는 파일 {name}"
        text = (RAW / SGIS_FOLDER / name).read_bytes().decode(meta["encoding"])
        rows = [r for r in csv.DictReader(io.StringIO(text)) if r["통계항목"] == item]
        assert {r["기준연도"] for r in rows} == {"2024"}, f"{name}: 기준연도가 2024가 아님"
        codes = [r["행정구역코드"] for r in rows]
        assert sorted(codes) == sorted([SGIS_GUN_CODE, *region_by_sgis]), (
            f"{name}: 지역코드가 군 1 + 읍면 8 이 아님 {codes}")

        for r in rows:
            raw = r["통계값"].strip()
            # N/A 는 비공개(소수 셀) 표시다. 0 으로 바꾸지 않는다
            value = None if raw == "N/A" else (int(raw) if additive else float(raw))
            if value is None:
                na_cells.append(f"{r['행정구역코드']}/{item}")
            if r["행정구역코드"] == SGIS_GUN_CODE:
                gun[key] = value
            else:
                by_region[region_by_sgis[r["행정구역코드"]]][key] = value

        if additive:
            parts = [by_region[c][key] for c in by_region]
            if None not in parts and gun[key] is not None:
                assert sum(parts) == gun[key], (
                    f"{name}: 읍면 합 {sum(parts)} != 군 합계 {gun[key]}")

    # 매핑 검산: 분석 기준 시점(2025-12) 주민등록 인구와 크게 다르면 코드가 뒤바뀐 것
    mois = {r["region_code"]: r["population"] for r in population
            if r["period"] == "2025-12"}
    for code, v in by_region.items():
        gap = abs(v["population"] - mois[code]) / mois[code]
        assert gap <= SGIS_POP_TOLERANCE, (
            f"SGIS {code}: 인구 {v['population']:.0f} vs 주민등록 {mois[code]} "
            f"({gap:.0%} 차이) - 코드 매핑 확인")

    return {
        "reference_date": "2024-12-31",
        "provenance": meta["provenance"],
        "_note": ("SGIS 등록센서스 기반 2024년 통계. 인구는 주민등록 인구와 정의가 달라 "
                  "값이 다르다 - 섞어 쓰지 말 것. 주택 세부 항목(건축년도 등)은 "
                  "사유 재산이라 분석 범위 밖으로 제외."),
        "items": {key: {"sgis_code": item, "label": suffix, "unit": unit}
                  for item, (suffix, key, unit, _) in SGIS_ITEMS.items()},
        "na_cells": na_cells,
        "gun_total": gun,
        "by_region": by_region,
    }


# ---------------------------------------------------------------- main

def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    population, name_by_code = prepare_population()
    boundary = prepare_boundary(name_by_code)
    seniors = prepare_senior_centers(name_by_code)
    sgis = prepare_sgis_stats(boundary, population)

    def write(name: str, obj) -> None:
        path = DERIVED / name
        # 좌표 덩어리는 사람이 읽을 게 아니므로 압축해서 쓴다
        indent = None if name.endswith(".geojson") else 2
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n",
                        encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")

    print("PASS: 검증 통과. derived/ 생성:")
    # 실행 날짜를 넣지 않는다 - CI 가 derived 재생성 결과를 커밋과 바이트 비교하므로
    # 같은 raw 에서는 언제 돌려도 같은 파일이 나와야 한다
    write("population.json", {
        "periods": MOIS_PERIODS,
        "records": population,
    })
    write("eupmyeon.geojson", boundary)
    write("senior_centers.json", seniors)
    write("sgis_stats.json", sgis)

    print(f"\n  인구 {len(population)}행")
    old = sum(v["old_count"] for v in seniors["by_region"].values())
    print(f"  경로당 {len(seniors['centers'])}곳 "
          f"(노후 {old}곳, {SENIOR_OLD_BEFORE_YEAR}년 이전 - 임시 기준)")
    print(f"  SGIS 2024 항목 {len(sgis['items'])}개 x 읍면 {len(sgis['by_region'])}개 "
          f"(N/A {len(sgis['na_cells'])}칸)")

if __name__ == "__main__":
    main()
