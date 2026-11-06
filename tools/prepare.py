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

# 주민등록 인구 기준시점. raw 에는 2023-07~2026-09 매월 시점이 있지만 population.json 은 두 시점만 쓴다.
# 2026-11-05 결정: 분석 기준 시점은 2026-09 하나로 맞춘다(생활시설 자료가 2026-09 최신본).
# 2023-12 는 인구감소 비교의 출발 시점(대구 편입 후 첫 연말)이다.
ANALYSIS_PERIOD = "2026-09"
BASELINE_PERIOD = "2023-12"
MOIS_PERIODS = [BASELINE_PERIOD, ANALYSIS_PERIOD]

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

def _read_households(period: str) -> dict:
    """행안부 주민등록 인구 및 세대현황(같은 달). 화면에 코드가 없어 이름으로 붙인다(이름·순서·총인구는
    수집 때 연령별 인구와 일치 확인). 행 = [이름, 총인구수, 세대수, 세대당인구, 남, 여, 남녀비율]."""
    folder = f"mois-household-{period}"
    read_meta(folder)
    rows = json.loads((RAW / folder / "household.json").read_text(encoding="utf-8"))
    assert len(rows) == 9, f"{folder}: 9행이어야 하는데 {len(rows)}행"
    out = {r[0]: {"population": _num(r[1]), "households": _num(r[2])} for r in rows}
    assert len(out) == 9, f"{folder}: 이름 중복"
    gun = [k for k in out if k.endswith("군")]
    assert len(gun) == 1 and sum(v["households"] for k, v in out.items() if k not in gun) == out[gun[0]]["households"], (
        f"{folder}: 읍면 세대 합 != 군 세대")
    return out


def prepare_population():
    """행정안전부 연령별 인구. 2개 시점 x (군 합계 1 + 읍면 8) = 18행."""
    records = []
    name_by_code = {}

    for period in MOIS_PERIODS:
        folder = f"mois-age-{period}"
        meta = read_meta(folder)
        rows = json.loads((RAW / folder / "age.json").read_text(encoding="utf-8"))

        assert len(rows) == 9, f"{folder}: 9행이어야 하는데 {len(rows)}행"
        households = _read_households(period)

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

            hh = households[name]
            assert hh["population"] == block["total"], (
                f"{folder}/{name}: 세대현황 총인구 {hh['population']} != 연령별 {block['total']}")
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
                "households": hh["households"],
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


# ---------------------------------------------------------------- 빈집애

BINZIBE_FOLDER = "binzibe-gunwi-vacant-houses-2025"


def prepare_vacant_houses(name_by_code: dict) -> dict:
    """빈집애 읍면별 빈집 수(지자체 빈집행정조사). 빈집률은 만들지 않는다 - 같은 조사의 주택 수가 없다."""
    meta = read_meta(BINZIBE_FOLDER)
    d = json.loads((RAW / BINZIBE_FOLDER / "rank.json").read_text(encoding="utf-8"))
    code_by_name = {v: k for k, v in name_by_code.items()}
    by_region = {}
    for r in d["dataList"]:
        parts = r["sojaeji"].split("_")
        assert parts[:2] == ["대구광역시", "군위군"], f"군위군이 아닌 행 {r['sojaeji']}"
        name = parts[-1]
        assert name in code_by_name, f"빈집애 읍면 {name!r} 가 인구 자료에 없다"
        by_region[code_by_name[name]] = {"vacant_houses": int(r["binCnt"]),
                                         "share_of_gun_pct": r["binzipRateReg"]}
    assert set(by_region) == set(name_by_code), "빈집애 읍면이 8개가 아님"
    total = sum(v["vacant_houses"] for v in by_region.values())
    assert total == d["regionStatus"]["totalBinCnt"] == 602, f"빈집 합 {total}"
    return {
        "reference_date": meta["reference_date"],
        "provenance": meta["provenance"],
        "_note": ("한국부동산원 빈집애 지도의 읍면별 빈집 수(지자체 빈집행정조사, 국가승인통계 아님). "
                  "share_of_gun_pct 는 빈집률이 아니라 군 전체 빈집 대비 그 읍면 비중. 같은 조사의 주택 수가 "
                  "없어 빈집률은 만들지 않는다. 사이트가 조사연도 하나만 제공한다(화면 '2025년')."),
        "total": total,
        "by_region": by_region,
    }


# ---------------------------------------------------------------- main

def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    population, name_by_code = prepare_population()
    boundary = prepare_boundary(name_by_code)
    seniors = prepare_senior_centers(name_by_code)
    vacant = prepare_vacant_houses(name_by_code)
    # 리 단위(법정리 92개). shapely·pyproj·pyshp 가 필요하다(requirements.txt)
    import prepare_ri
    ri_boundary = prepare_ri.prepare_ri_boundary(RAW, read_meta, name_by_code)
    ri_facilities = prepare_ri.assign_facilities(RAW, read_meta, ri_boundary, seniors)
    ri_access = prepare_ri.prepare_access(RAW, read_meta, ri_boundary, ri_facilities)
    ri_housing = prepare_ri.prepare_housing_age(RAW, read_meta, ri_boundary, ANALYSIS_PERIOD)
    ri_population = prepare_ri.prepare_ri_population(RAW, read_meta, ri_boundary, population,
                                                     BASELINE_PERIOD, ANALYSIS_PERIOD)

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
    write("vacant_houses.json", vacant)
    write("ri_boundary.geojson", ri_boundary)
    write("ri_facilities.json", ri_facilities)
    write("ri_access.json", ri_access)
    write("ri_housing_age.json", ri_housing)
    write("ri_population.json", ri_population)

    print(f"\n  인구 {len(population)}행")
    old = sum(v["old_count"] for v in seniors["by_region"].values())
    print(f"  경로당 {len(seniors['centers'])}곳 "
          f"(노후 {old}곳, {SENIOR_OLD_BEFORE_YEAR}년 이전 - 임시 기준)")
    print(f"  빈집애 읍면별 빈집 수 합 {vacant['total']} (빈집률 아님)")
    print(f"  법정리 {len(ri_boundary['features'])}개 경계, 시설 배정 "
          + ", ".join(f"{ri_facilities['type_labels'][t]} {n}"
                      for t, n in ri_facilities["totals"].items()))
    for k, v in ri_facilities["checks"].items():
        print(f"    대조 {k}: {v['n']}건 중 불일치 {v['mismatch']}")
    g = ri_access["gun"]
    print(f"  주거 건물 {g['houses']}채 → 1차 의료 평균 {g['primary_care']['mean_m']} m, "
          f"{ri_access['far_m']} m 초과 {g['primary_care']['far_share_pct']}% (프로젝트 기준)")
    print("    평균 거리 " + ", ".join(
        f"{v['label']} {g[k]['mean_m']} m({v['facilities']}곳)" for k, v in ri_access["groups"].items()))
    h = ri_housing["gun"]
    print(f"  노후주택({ri_housing['old_house_years']}년+) 확인 {h['old_confirmed_pct']}%, "
          f"구조 추정 포함 {h['old_with_estimate_pct']}%, 사용승인일 빈칸 {h['blank_pct']}%")

if __name__ == "__main__":
    main()
