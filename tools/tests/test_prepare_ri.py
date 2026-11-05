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


def test_daeyul_clinic_coordinate_fixed(ri):
    """HIRA 가 대율보건진료소를 부계면보건지소(창평리) 좌표로 넣은 오류를 바로잡았는지."""
    _, _, fac = ri
    assert fac["coord_fixes"] == ["군위군부계면대율보건진료소"]
    p = next(p for p in fac["points"] if p["name"] == "군위군부계면대율보건진료소")
    assert p["ri_code"] == "2772033024"          # 부계면 대율리
    assert "coord_fix" in p
