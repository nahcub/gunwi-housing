"""법정리 경계·시설 배정. 원자료 기준 알려진 개수를 고정하고, 망가진 입력에 멈추는지 본다."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import prepare  # noqa: E402
import prepare_ri  # noqa: E402


@pytest.fixture(scope="module")
def ri():
    _, name_by_code = prepare.prepare_population()
    gj = prepare_ri.prepare_ri_boundary(prepare.RAW, prepare.read_meta, name_by_code)
    seniors = prepare.prepare_senior_centers(name_by_code)
    fac = prepare_ri.assign_facilities(prepare.RAW, prepare.read_meta, gj, seniors)
    return name_by_code, gj, fac


def test_ri_boundary_is_92_legal_ri_in_8_eupmyeon(ri):
    name_by_code, gj, _ = ri
    props = [f["properties"] for f in gj["features"]]
    assert len(props) == 92
    per_emd = {}
    for p in props:
        per_emd[p["region_name"]] = per_emd.get(p["region_name"], 0) + 1
    # 법정동코드(2026-09-29) 기준
    assert per_emd == {"군위읍": 17, "소보면": 14, "효령면": 15, "부계면": 8,
                       "우보면": 9, "의흥면": 11, "산성면": 7, "삼국유사면": 11}
    # 같은 이름의 리가 다른 읍면에 있다 - 코드로만 구분해야 한다
    names = [p["ri_name"] for p in props]
    assert names.count("수서리") == 2 and names.count("달산리") == 2


def test_ri_boundary_is_wgs84(ri):
    _, gj, _ = ri
    # 재투영이 빠지면 좌표가 미터(수십만)로 남는다. 군 동쪽 끝이 128.9004 라 0.01도 여유를 둔다
    lon_min, lat_min, lon_max, lat_max = prepare.GUNWI_BBOX
    lon_min, lat_min, lon_max, lat_max = lon_min - 0.01, lat_min - 0.01, lon_max + 0.01, lat_max + 0.01
    for f in gj["features"]:
        ring = f["geometry"]["coordinates"][0]
        ring = ring[0] if isinstance(ring[0][0], list) else ring
        for lon, lat in ring:
            assert lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def test_facility_known_totals(ri):
    _, _, fac = ri
    assert fac["totals"] == {
        "senior_center": 215, "health": 18, "clinic": 17, "pharmacy": 7, "school": 8,
        "childcare": 4, "kindergarten": 1, "closed_school": 11,
        "bus_stop": 725, "store": 1155,
    }


def test_every_point_has_a_current_ri_and_matching_region(ri):
    _, gj, fac = ri
    codes = {f["properties"]["ri_code"] for f in gj["features"]}
    for p in fac["points"]:
        assert p["ri_code"] in codes
        assert p["region_code"] == p["ri_code"][:8] + "00"


def test_cross_checks_with_source_fields(ri):
    _, _, fac = ri
    c = fac["checks"]
    assert c["경로당 주소 읍면"]["mismatch"] == 0
    assert c["HIRA 읍면동"]["mismatch"] == 0
    assert c["학교 지번주소 리"]["mismatch"] == 0
    # 상가는 큰 건물 공유 좌표 때문에 리 경계 근처에서 어긋난다(지번 코드를 따른다)
    assert c["상가 법정동코드 vs 좌표"]["mismatch"] == 9


def test_uncounted_types_are_not_counted(ri):
    """기준이 정해지지 않은 버스정류장·상가는 리별 집계에 없어야 한다."""
    _, _, fac = ri
    for v in fac["by_ri"].values():
        assert "bus_stop" not in v["counts"] and "store" not in v["counts"]
    assert sum(v["counts"]["senior_center"] for v in fac["by_ri"].values()) == 215


def test_closed_school_old_eupmyeon_name_maps_to_new(ri):
    """폐교 주소의 '고로면' 은 삼국유사면으로 맞춰야 한다(이름 매칭 실패로 멈추지 않게)."""
    _, gj, fac = ri
    name = {f["properties"]["ri_code"]: f["properties"]["region_name"] for f in gj["features"]}
    hwasu = [p for p in fac["points"] if p["type"] == "closed_school" and "화수" in p["name"]]
    assert hwasu and all(name[p["ri_code"]] == "삼국유사면" for p in hwasu)


def test_point_outside_all_ri_stops(ri):
    _, gj, _ = ri
    loc = prepare_ri.RiLocator(gj)
    assert loc.locate(126.9780, 37.5665) is None      # 서울시청


# ------------------------------------------------------------- 집별 접근성

@pytest.fixture(scope="module")
def access(ri):
    _, gj, fac = ri
    return prepare_ri.prepare_access(prepare.RAW, prepare.read_meta, gj, fac)


def test_access_counts_every_residential_building(access):
    # GIS건물통합정보 2026-09-09 군위: 단독주택 10,189 + 공동주택 75
    assert access["totals"]["houses"] == 10264
    assert sum(v["houses"] for v in access["by_ri"].values()) == 10264
    assert sum(v["houses"] for v in access["by_region"].values()) == 10264
    assert all(v["houses"] > 0 for v in access["by_ri"].values())     # 92개 리 모두 집이 있다
    assert access["checks"]["건물 법정동코드 vs 중심점 좌표"]["mismatch"] == 11


def test_access_summary_is_consistent(access):
    for v in [access["gun"], *access["by_region"].values(), *access["by_ri"].values()]:
        for g in prepare_ri.ACCESS_GROUPS:
            s = v[g]
            assert 0 <= s["median_m"] <= s["max_m"] and 0 <= s["mean_m"] <= s["max_m"]
            assert 0 <= s["far_share_pct"] <= 100
            # 1차 의료는 보건기관과 의원을 합친 묶음이라 둘 중 가까운 쪽보다 멀 수 없다
        assert v["primary_care"]["max_m"] <= max(v["health"]["max_m"], v["clinic"]["max_m"])
        # 중·고 묶음과 초등 묶음은 같은 학교 점(8곳)을 나눈 것 - 둘 다 비어 있으면 안 된다
        assert v["school_elementary"]["mean_m"] is not None and v["school_secondary"]["mean_m"] is not None


def test_access_group_facility_counts(access, ri):
    """묶음별 시설 수. 버스는 군위 안 725행 중 '미정차' 8행(IC·JC)을 빼고 중복 등록은 그대로 둔다."""
    _, _, fac = ri
    n = {g: v["facilities"] for g, v in access["groups"].items()}
    assert n == {"primary_care": 35, "health": 18, "clinic": 17, "pharmacy": 7,
                 "bus_stop": 717, "school_elementary": 4, "school_secondary": 4, "childcare": 4,
                 "grocery": 60}
    bus = [p for p in fac["points"] if p["type"] == "bus_stop"]
    assert sum(p["no_stop"] for p in bus) == 8
    assert all("미정차" in p["name"] for p in bus if p["no_stop"])
    # 학교 묶음 둘이 학교 점 전체를 빠짐없이, 겹치지 않게 나눈다
    assert n["school_elementary"] + n["school_secondary"] == fac["totals"]["school"]
    assert access["far_m"] == prepare_ri.ACCESS_FAR_M == 2000


def test_access_new_groups_gun_summary(access):
    """군 전체 평균이 읍면 평균의 집 수 가중평균과 맞는지(반올림 오차 1 m 이내)."""
    for g in ("bus_stop", "school_elementary", "school_secondary", "childcare", "grocery"):
        total = sum(v["houses"] for v in access["by_region"].values())
        weighted = sum(v[g]["mean_m"] * v["houses"] for v in access["by_region"].values()) / total
        assert abs(weighted - access["gun"][g]["mean_m"]) <= 1, g
        assert access["gun"][g]["max_m"] == max(v[g]["max_m"] for v in access["by_ri"].values())
    # 정류장이 학교·어린이집보다 훨씬 촘촘하다
    assert access["gun"]["bus_stop"]["mean_m"] < access["gun"]["school_elementary"]["mean_m"]


def test_daeyul_clinic_coordinate_fixed(ri):
    """HIRA 가 대율보건진료소를 부계면보건지소(창평리) 좌표로 넣은 오류를 바로잡았는지."""
    _, _, fac = ri
    assert fac["coord_fixes"] == ["군위군부계면대율보건진료소"]
    p = next(p for p in fac["points"] if p["name"] == "군위군부계면대율보건진료소")
    assert p["ri_code"] == "2772033024"          # 부계면 대율리
    assert "coord_fix" in p


# ------------------------------------------------------------- 노후주택

@pytest.fixture(scope="module")
def housing(ri):
    _, gj, _ = ri
    return prepare_ri.prepare_housing_age(prepare.RAW, prepare.read_meta, gj, prepare.ANALYSIS_PERIOD)


def test_housing_age_cutoff_follows_analysis_period(housing):
    # 2026-09 분석 시점, 30년 → 1996-09-30 이전 사용승인
    assert housing["cutoff_date"] == "1996-09-30"
    assert housing["old_house_years"] == 30


def test_housing_age_known_counts(housing):
    g = housing["gun"]
    assert (g["houses"], g["old_confirmed"], g["old_estimated"], g["blank"]) == (10264, 2818, 3477, 3522)
    assert g["old_estimated"] <= g["blank"]


def test_housing_age_parts_add_up(housing):
    for v in [*housing["by_region"].values(), *housing["by_ri"].values()]:
        assert v["old_confirmed"] + v["old_estimated"] <= v["houses"]
        assert v["old_confirmed_pct"] <= v["old_with_estimate_pct"]
    assert sum(v["old_estimated"] for v in housing["by_ri"].values()) == housing["gun"]["old_estimated"]


def test_grocery_excludes_listed_stores(ri):
    """식료품점 = 슈퍼마켓·편의점 75곳 - 사람이 확인한 제외 15곳. 제외 목록은 상가업소번호로 고정."""
    _, _, fac = ri
    stores = [p for p in fac["points"] if p["type"] == "store"]
    core = [p for p in stores if p["category"].split()[0] in prepare_ri.GROCERY_CODES]
    assert len(core) == 75 and len(prepare_ri.GROCERY_EXCLUDE) == 15
    by_id = {p["store_id"]: p for p in core}
    for sid, (name, _) in prepare_ri.GROCERY_EXCLUDE.items():
        assert by_id[sid]["name"].strip() == name
    keep = prepare_ri.ACCESS_GROUPS["grocery"][2]
    assert sum(1 for p in stores if keep(p)) == 60
