"""법정리(리) 단위: 리 경계 정리 + 시설을 리에 배정한다. prepare.py 가 부른다.

리 단위 분석의 공간단위는 법정리 92개다(행정리 경계는 공개 자료가 없다).
배정 방법은 자료마다 다르고, 여기 한 곳에서만 정한다.

  좌표가 있는 자료  -> 리 경계에 점을 넣어 판정(point-in-polygon)
  상가정보          -> 원자료의 법정동코드(=법정리 코드)를 그대로 쓰고, 좌표 판정과 대조
                       (상가 좌표는 큰 건물 하나에 여러 업소가 같은 점으로 찍혀 리 경계 근처에서
                        어긋난다 - 2026-11-05 첫 실행에서 1,155건 중 9건. 지번 기준 코드를 따른다)
  주소만 있는 폐교  -> 주소의 '읍면 + 리' 이름을 법정동코드 목록에 맞춘다

배정만 한다. 기준이 아직 정해지지 않은 것(버스정류장 중복의 리별 개수, 식료품점 상호 검토,
학교 '운영' 정의)은 여기서 걸러내거나 세지 않는다 - 점마다 원자료 구분값을 남겨
둔다. 기준은 docs/methodology.md 에 먼저 적고 나서 센다. 집별 거리(prepare_access)는
ACCESS_GROUPS 의 조건(미정차 제외 등)으로 점을 고른다.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import shapefile
from pyproj import Transformer
import shapely
from shapely import STRtree
from shapely.geometry import Point, shape

BUILDING_FOLDER = "vworld-gis-building-gunwi-2026-09-09"
RESIDENTIAL_USES = ("단독주택", "공동주택")   # 건축물용도명. 용도 빈칸(대장 미연계) 건물은 집인지 알 수 없어 뺀다
# 집에서 가장 가까운 시설까지 직선거리를 잴 묶음: 묶음 -> (점 유형, 걸러내는 조건 설명, 조건).
# 조건은 점마다 원자료 구분값을 보고 판단한다. 식료품점(상가)은 기준이 정해지지 않아 아직 없다.
# 읍면사무소는 좌표 자료가 없어 넣지 않는다(2026-11-06 사용자 결정)
ACCESS_GROUPS = {
    "primary_care": (("health", "clinic"), None, None),   # 1차 의료: 보건소·보건지소·보건진료소 + 의원·치과·한의원
    "health": (("health",), None, None),
    "clinic": (("clinic",), None, None),
    "pharmacy": (("pharmacy",), None, None),
    # 정류장명에 '미정차' 가 든 행(고속도로 IC·JC, 버스가 서지 않음)은 뺀다. 여러 BIS 에 중복 등록된
    # 정류장은 가장 가까운 거리에 영향이 없어 그대로 둔다(2026-11-06 사용자 결정)
    "bus_stop": (("bus_stop",), "정류장명에 '미정차' 가 든 행 제외", lambda p: not p["no_stop"]),
    # 학교 위치 자료(2026-09-20)의 학교급구분. category = '학교급 / 본교분교 / 운영상태'
    "school_elementary": (("school",), "학교급 초등학교",
                          lambda p: p["category"].split(" / ")[0] == "초등학교"),
    "school_secondary": (("school",), "학교급 중학교·고등학교",
                         lambda p: p["category"].split(" / ")[0] in ("중학교", "고등학교")),
    "childcare": (("childcare",), None, None),
    # 식료품점(2026-11-06 사용자 결정): 상권업종 소분류 슈퍼마켓·편의점만, 휴게소·캠핑장 등 GROCERY_EXCLUDE 제외.
    # 정육점·채소과일 등 확장 업종은 치킨집·농장 직판이 섞여 있어 쓰지 않는다
    "grocery": (("store",), "슈퍼마켓(G20404)·편의점(G20405) 중 GROCERY_EXCLUDE 15곳 제외",
                lambda p: p["category"].split()[0] in GROCERY_CODES and p["store_id"] not in GROCERY_EXCLUDE),
}
GROCERY_CODES = ("G20404", "G20405")
# 사람이 상호를 보고 뺀 곳 (상가업소번호: (상호, 사유)). 2026-11-06 '휴게소' 키워드 1차 + 사용자 확인 12곳
GROCERY_EXCLUDE = {
    "MA010120220806434737": ("씨유군위휴게소점", "휴게소"),
    "MA010120220808164975": ("송이휴게소", "휴게소"),
    "MA010120220812397719": ("의흥휴게소", "휴게소"),
    "MA010120220809253410": ("거매정자나무휴게실", "휴게 시설"),
    "MA010120220809703149": ("팔공쉼터매점", "휴게 시설"),
    "MA010120220805731350": ("청화산캠프관광농원", "캠핑장·관광지"),
    "MA0101202406A0456697": ("이지파크캠핑", "캠핑장·관광지"),
    "MA0101202303A0061741": ("동산더숲", "캠핑장·관광지"),
    "MA0101202306A0098552": ("씨유삼국유사테마파크공원점", "캠핑장·관광지"),
    "MA010120220808729566": ("일연파크편의점", "캠핑장·관광지"),
    "MA010120220809256570": ("동산매점", "매점·주유소"),
    "MA0101202406A0205746": ("해룡매점", "매점·주유소"),
    "MA010120220809252345": ("일송정매점", "매점·주유소"),
    "MA010120220809296038": ("화수정유소매점", "매점·주유소"),
    "MA010120220814171518": ("아날로그데이", "분류 오류(원자료 업종 숙박업)"),
}
ACCESS_LABELS = {"primary_care": "1차 의료(보건기관+의원)", "health": "보건소·보건지소·보건진료소",
                 "clinic": "의원·치과·한의원", "pharmacy": "약국",
                 "bus_stop": "버스정류장(미정차 제외)", "school_elementary": "초등학교",
                 "school_secondary": "중·고등학교", "childcare": "어린이집",
                 "grocery": "식료품점(슈퍼마켓·편의점)"}
# '먼 집' 기준 거리. 공식 기준이 아니라 프로젝트 임시값이다 - 확정되면 여기만 바꾼다.
# 지금은 모든 묶음에 같은 값을 쓴다. 시설별 기준(예: 버스는 걸어서 1 km)은 아직 정하지 않았다
ACCESS_FAR_M = 2000

# HIRA 좌표 보정. 원자료가 틀린 것으로 확인된 시설만, 근거와 함께 적는다.
#  - 대율보건진료소: HIRA 2026-09 가 부계면보건지소(창평리)와 똑같은 주소·좌표로 넣었다. 보건복지부
#    지역보건의료기관 목록의 주소는 '부계면 한티로 2146-1'(대율리)이다(2026-11-05 확인). GIS건물통합정보에
#    같은 이름 건물이 대율리에 2동(673-2, 756, 약 120 m 간격) 있어 연면적이 큰 쪽 중심점을 쓴다.
HIRA_COORD_FIXES = {
    "군위군부계면대율보건진료소": {"building_name": "대율보건진료소", "ri_code": "2772033024"},
}

# 노후주택(2026-11-05 사용자 결정). 사용승인 후 OLD_HOUSE_YEARS 년 이상. 공식 기준이 아닌 프로젝트 기준이다.
OLD_HOUSE_YEARS = 30
# 사용승인일이 빈 집 중 이 구조면 '노후 추정'으로 센다. 빈칸 집의 98% 가 이 구조이고(사용승인 제도
# 이전·대장 소급 등재 추정), 30년 미만 확인 집에는 드물다(5%+32%). 통나무구조는 근래 전원주택이라 뺀다.
TRADITIONAL_STRUCTURES = ("일반목구조", "목구조", "기타조적구조", "조적구조", "블록구조", "벽돌구조", "석구조")

RI_FOLDER = "vworld-ri-boundary-2026-10-09"
BJD_FOLDER = "bjd-code-2026-09-29"
SIGUNGU = "27720"
RI_COUNT = 92
COORD_DIGITS = 6        # 경계 좌표 반올림(약 0.1 m). 재투영 결과를 바이트 단위로 안정시킨다

# 읍면 옛 이름 -> 현재 이름 (2021-01 고로면 -> 삼국유사면, 경계 동일)
EMD_ALIASES = {"고로면": "삼국유사면"}


# ------------------------------------------------------------- 공통

def _meta_file(raw: Path, folder: str, meta: dict, suffix: str) -> Path:
    names = [n for n in meta["files"] if n.endswith(suffix)]
    assert len(names) == 1, f"{folder}: {suffix} 파일이 하나가 아님 {names}"
    return raw / folder / names[0]


def _round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(v, COORD_DIGITS) for v in obj]
        return [_round_coords(o) for o in obj]
    return obj


# ------------------------------------------------------------- 법정동코드

def read_bjd_ri(raw: Path, read_meta) -> dict[str, str]:
    """군위 현행 법정리 코드 -> 전체 이름('대구광역시 군위군 군위읍 동부리')."""
    meta = read_meta(BJD_FOLDER)
    path = _meta_file(raw, BJD_FOLDER, meta, ".csv")
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode(meta["encoding"]))))
    assert rows[0] == ["법정동코드", "법정동명", "폐지여부"], f"{BJD_FOLDER}: 헤더가 바뀜 {rows[0]}"
    ri = {c: n for c, n, s in rows[1:]
          if c.startswith(SIGUNGU) and not c.endswith("00") and s == "존재"}
    assert len(ri) == RI_COUNT, f"{BJD_FOLDER}: 군위 현행 법정리 {len(ri)}개 (기대 {RI_COUNT})"
    return ri


# ------------------------------------------------------------- 리 경계

def prepare_ri_boundary(raw: Path, read_meta, name_by_code: dict) -> dict:
    """법정리 92개 경계(EPSG:5186) -> WGS84 GeoJSON. region_code(읍면)를 심는다."""
    meta = read_meta(RI_FOLDER)
    assert meta["provenance"] == "verified"
    shp = _meta_file(raw, RI_FOLDER, meta, ".shp")
    prj = _meta_file(raw, RI_FOLDER, meta, ".prj").read_text(encoding="ascii")
    assert 'AUTHORITY["EPSG","5186"]' in prj, f"{RI_FOLDER}: 좌표계가 EPSG:5186 이 아님"
    bjd = read_bjd_ri(raw, read_meta)

    to_wgs = Transformer.from_crs(5186, 4326, always_xy=True).transform
    reader = shapefile.Reader(str(shp.with_suffix("")), encoding=meta["encoding"])
    feats = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        code, name = rec["A1"], rec["A2"]
        assert code in bjd, f"{RI_FOLDER}: 법정동코드에 없는 리 {code} {name}"
        assert bjd[code].endswith(" " + name), f"{RI_FOLDER}: 이름 불일치 {code} {name} / {bjd[code]}"
        region_code = code[:8] + "00"      # 법정리 코드 앞 8자리 + 00 = 읍면 코드
        assert region_code in name_by_code, f"{code}: 읍면 코드 {region_code} 가 인구 자료에 없음"
        geom = shapely.transform(shape(sr.shape.__geo_interface__), to_wgs, interleaved=False)
        assert geom.is_valid, f"{code} {name}: 도형이 유효하지 않음"
        gi = geom.__geo_interface__
        feats.append({
            "type": "Feature",
            "properties": {
                "ri_code": code,
                "ri_name": name,
                "region_code": region_code,
                "region_name": name_by_code[region_code],
                "base_date": str(rec["A3"]),
            },
            "geometry": {"type": gi["type"], "coordinates": _round_coords(gi["coordinates"])},
        })
    feats.sort(key=lambda f: f["properties"]["ri_code"])
    codes = [f["properties"]["ri_code"] for f in feats]
    assert len(codes) == len(set(codes)) == RI_COUNT, f"{RI_FOLDER}: 리 {len(codes)}개, 중복 확인"
    assert set(codes) == set(bjd), f"{RI_FOLDER}: 법정동코드와 리 집합이 다름"
    assert {f["properties"]["region_code"] for f in feats} == set(name_by_code)
    return {
        "type": "FeatureCollection",
        "_provenance": meta["provenance"],
        "_reference_date": meta["reference_date"],
        "_crs_note": "원본 EPSG:5186 -> EPSG:4326 재투영, 좌표 소수 6자리 반올림",
        "features": feats,
    }


class RiLocator:
    """점 -> 법정리 코드. 경계선 위의 점도 잡도록 covers 로 판정한다."""

    def __init__(self, ri_gj: dict):
        self.codes = [f["properties"]["ri_code"] for f in ri_gj["features"]]
        self.geoms = [shape(f["geometry"]) for f in ri_gj["features"]]
        self.tree = STRtree(self.geoms)

    def locate(self, lon: float, lat: float) -> str | None:
        p = Point(lon, lat)
        hits = [self.codes[i] for i in self.tree.query(p, predicate="covered_by")]
        assert len(hits) <= 1 or len(set(h[:8] for h in hits)) == 1, (
            f"({lon}, {lat}) 가 여러 읍면의 리에 걸침: {hits}")
        return min(hits) if hits else None   # 리 경계선 위 점은 코드가 작은 쪽(재현 가능하게)


# ------------------------------------------------------------- 시설 읽기

def _csv_rows(raw: Path, folder: str, meta: dict) -> list[dict]:
    path = _meta_file(raw, folder, meta, ".csv")
    return list(csv.DictReader(io.StringIO(path.read_bytes().decode(meta["encoding"]))))


def _hira(raw: Path, read_meta) -> list[dict]:
    folder = "hira-2026-09"
    meta = read_meta(folder)
    zpath = _meta_file(raw, folder, meta, ".zip")
    out = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:      # UTF-8 플래그가 없으면 cp949 이름
                name = name.encode("cp437").decode("cp949")
            kind = "pharmacy" if name.startswith("2.") else "clinic" if name.startswith("1.") else None
            if not kind:
                continue
            text = z.read(info).decode("cp949")
            for r in csv.DictReader(io.StringIO(text)):
                if r["시군구코드명"] != "대구군위군":
                    continue
                out.append({
                    "type": "health" if r["종별코드명"] in ("보건소", "보건지소", "보건진료소") else kind,
                    "category": r["종별코드명"],
                    "name": r["요양기관명"],
                    "lon": float(r["좌표(X)"]), "lat": float(r["좌표(Y)"]),
                    "source_id": "HIRA_HOSPITAL_PHARMACY",
                    "emd_hint": r["읍면동"],
                })
    assert len(out) == 42, f"{folder}: 군위 {len(out)}행 (조사 시 42)"
    return out


def _bus(raw: Path, read_meta) -> list[dict]:
    folder = "bus-stops-2026-10-20"
    meta = read_meta(folder)
    return [{
        "type": "bus_stop",
        "category": r["관리도시명"],
        "name": r["정류장명"],
        "lon": float(r["경도"]), "lat": float(r["위도"]),
        "source_id": "BUS_STOPS_NATIONAL",
        "stop_id": r["정류장번호"],
        "no_stop": "미정차" in r["정류장명"],
    } for r in _csv_rows(raw, folder, meta)]


def _stores(raw: Path, read_meta) -> list[dict]:
    folder = "sbiz-stores-gunwi-2026-09"
    meta = read_meta(folder)
    rows = _csv_rows(raw, folder, meta)
    assert {r["시군구코드"] for r in rows} == {SIGUNGU}
    return [{
        "type": "store",
        "category": f"{r['상권업종소분류코드']} {r['상권업종소분류명']}",
        "name": r["상호명"] + (f" {r['지점명']}" if r["지점명"] else ""),
        "lon": float(r["경도"]), "lat": float(r["위도"]),
        "source_id": "SBIZ_STORES",
        "store_id": r["상가업소번호"],
        "ri_code_source": r["법정동코드"],
    } for r in rows]


def _schools(raw: Path, read_meta) -> list[dict]:
    folder = "school-locations-2026-09-20"
    meta = read_meta(folder)
    return [{
        "type": "school",
        "category": f"{r['학교급구분']} / {r['본교분교구분']} / {r['운영상태']}",
        "name": r["학교명"],
        "lon": float(r["경도"]), "lat": float(r["위도"]),
        "source_id": "SCHOOL_LOCATIONS",
        # 지번주소의 리 이름 - 좌표 판정 대조용
        "ri_name_hint": re.search(r"(\S+리)\s+\d", r["소재지지번주소"]).group(1),
    } for r in _csv_rows(raw, folder, meta) if "군위군" in r["소재지지번주소"]]


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _childcare(raw: Path, read_meta) -> list[dict]:
    folder = "childcare-basic-2026-09"
    meta = read_meta(folder)
    html = _meta_file(raw, folder, meta, ".html").read_bytes().decode(meta["encoding"])
    p = _TableRows()
    p.feed(html)
    header = p.rows[0]
    assert header[:6] == ["번호", "시도", "시군구", "어린이집명", "어린이집유형구분", "운영현황"], header
    out = []
    for row in p.rows[1:]:
        r = dict(zip(header, row))
        assert r["시군구"] == "군위군", r
        out.append({
            "type": "childcare",
            "category": f"{r['어린이집유형구분']} / {r['운영현황']}",
            "name": r["어린이집명"],
            "lon": float(r["경도"]), "lat": float(r["위도"]),
            "source_id": "CHILDCARE_BASIC",
        })
    assert len(out) == 4, f"{folder}: {len(out)}곳 (조사 시 4)"
    return out


def _kindergartens(raw: Path, read_meta) -> list[dict]:
    folder = "kindergarten-general-2026-2"
    meta = read_meta(folder)
    return [{
        "type": "kindergarten",
        "category": r["설립유형"],
        "name": r["유치원명"],
        "lon": float(r["경도"]), "lat": float(r["위도"]),
        "source_id": "KINDERGARTEN_GENERAL",
    } for r in _csv_rows(raw, folder, meta) if "군위군" in r["주소"]]


def _closed_schools(raw: Path, read_meta, bjd: dict[str, str]) -> list[dict]:
    """좌표가 없어 주소의 '읍면 리' 이름으로 법정리 코드를 찾는다."""
    folder = "closed-schools-2025-09-30"
    meta = read_meta(folder)
    by_name = {}
    for code, full in bjd.items():
        emd, ri = full.split()[-2:]
        by_name[(emd, ri)] = code
    out = []
    for r in _csv_rows(raw, folder, meta):
        if r["교육청"] != "군위":
            continue
        m = re.search(r"(\S+[읍면])\s+(\S+리)\b", r["주소"])
        assert m, f"{folder}: 주소에서 읍면·리를 못 찾음 {r['주소']!r}"
        emd = EMD_ALIASES.get(m.group(1), m.group(1))
        key = (emd, m.group(2))
        assert key in by_name, f"{folder}: 법정동코드에 없는 리 {key} ({r['주소']})"
        out.append({
            "type": "closed_school",
            "category": f"{r['학교급명']} / 폐교 {r['폐교일자']}",
            "name": r["학교명"],
            "lon": None, "lat": None,
            "source_id": "CLOSED_SCHOOLS",
            "ri_code": by_name[key],
            "ri_method": "address",
        })
    assert len(out) == 11, f"{folder}: 군위 {len(out)}곳 (조사 시 11)"
    return out


# ------------------------------------------------------------- 배정

# 리별로 세는 유형. 버스정류장(중복 등록)·상가(식료품 기준 미정)는 기준을 정할 때까지 세지 않는다
COUNTED_TYPES = ["senior_center", "health", "clinic", "pharmacy", "school",
                 "childcare", "kindergarten", "closed_school"]
TYPE_LABELS = {
    "senior_center": "경로당", "health": "보건소·보건지소·보건진료소", "clinic": "의원·치과·한의원",
    "pharmacy": "약국", "school": "초·중·고", "childcare": "어린이집", "kindergarten": "유치원",
    "closed_school": "폐교", "bus_stop": "버스정류장(원자료 행, 중복 포함)",
    "store": "상가(전 업종)",
}


def assign_facilities(raw: Path, read_meta, ri_gj: dict, seniors: dict) -> dict:
    bjd = read_bjd_ri(raw, read_meta)
    loc = RiLocator(ri_gj)
    ri_props = {f["properties"]["ri_code"]: f["properties"] for f in ri_gj["features"]}
    emd_name = {p["region_code"]: p["region_name"] for p in ri_props.values()}

    pts = [{
        "type": "senior_center", "category": f"건립 {c['built_year']}", "name": c["name"],
        "lon": c["lon"], "lat": c["lat"], "source_id": "DATAGOKR_GUNWI_SENIOR",
        "region_hint": c["region_code"],
    } for c in seniors["centers"]]
    hira = _hira(raw, read_meta)
    fixes = _apply_hira_fixes(raw, read_meta, hira)
    pts += hira + _schools(raw, read_meta) + _childcare(raw, read_meta)
    pts += _kindergartens(raw, read_meta) + _stores(raw, read_meta)
    bus_all = _bus(raw, read_meta)
    closed = _closed_schools(raw, read_meta, bjd)

    checks = {}
    out = []
    for p in pts:
        code = loc.locate(p["lon"], p["lat"])
        assert code, f"{p['source_id']} {p['name']}: 어느 리에도 들지 않음 ({p['lon']}, {p['lat']})"
        if "ri_code_source" in p:
            # 상가: 지번 기준 법정동코드를 쓴다. 좌표 판정은 대조용으로만 남긴다
            assert p["ri_code_source"] in ri_props, f"상가 {p['name']}: 현행 법정리가 아닌 코드"
            p["ri_code"], p["ri_method"], p["ri_code_by_point"] = p["ri_code_source"], "source_code", code
        else:
            p["ri_code"], p["ri_method"] = code, "point_in_polygon"
        out.append(p)
    # 자료가 스스로 가진 읍면·리 정보와 좌표 판정이 맞는지 센다(틀린 수는 기록, 큰 차이는 멈춤)
    for kind, hint, get in [
        ("경로당 주소 읍면", "region_hint", lambda p: p["ri_code"][:8] + "00"),
        ("HIRA 읍면동", "emd_hint", lambda p: emd_name[p["ri_code"][:8] + "00"]),
        ("학교 지번주소 리", "ri_name_hint", lambda p: ri_props[p["ri_code"]]["ri_name"]),
        ("상가 법정동코드 vs 좌표", "ri_code_by_point", lambda p: p["ri_code"]),
    ]:
        sub = [p for p in out if hint in p]
        bad = [p for p in sub if p[hint] != get(p)]
        checks[kind] = {"n": len(sub), "mismatch": len(bad),
                        "examples": [f"{p['name']}: 자료 {p[hint]} / 좌표 {get(p)}" for p in bad[:5]]}
        assert len(bad) <= max(2, len(sub) * 0.02), f"{kind}: 좌표 판정과 {len(bad)}/{len(sub)} 불일치"

    # 버스: 전국 자료라 군위 리 안에 드는 것만 남긴다
    bus_in = []
    for p in bus_all:
        code = loc.locate(p["lon"], p["lat"])
        if code:
            p["ri_code"], p["ri_method"] = code, "point_in_polygon"
            bus_in.append(p)
    out += bus_in + closed

    for p in out:
        p["region_code"] = p["ri_code"][:8] + "00"
        for k in ("region_hint", "emd_hint", "ri_name_hint", "ri_code_source"):
            p.pop(k, None)
        if p["lon"] is not None:
            p["lon"], p["lat"] = round(p["lon"], 7), round(p["lat"], 7)
    out.sort(key=lambda p: (p["type"], p["ri_code"], p["name"], p.get("stop_id", "")))

    by_ri = {}
    for code, prop in sorted(ri_props.items()):
        counts = {t: sum(1 for p in out if p["type"] == t and p["ri_code"] == code)
                  for t in COUNTED_TYPES}
        by_ri[code] = {"ri_name": prop["ri_name"], "region_code": prop["region_code"],
                       "region_name": prop["region_name"], "counts": counts}
    totals = {t: sum(1 for p in out if p["type"] == t) for t in TYPE_LABELS}
    for t in COUNTED_TYPES:
        assert sum(v["counts"][t] for v in by_ri.values()) == totals[t]

    return {
        "_note": ("법정리 92개 기준 시설 배정. 좌표가 있으면 리 경계 포함 판정, 상가는 원자료 법정동코드, "
                  "폐교는 주소의 읍면·리 이름. 버스정류장(중복 등록·미정차 행 포함)과 상가(식료품 기준 미정)는 배정만 하고 "
                  "리별로 세지 않는다 - 기준은 docs/methodology.md 에서 정한다. 버스정류장은 미정차 행을 빼고 "
                  "집별 거리(ri_access.json)에만 쓴다."),
        "ri_boundary_reference_date": ri_gj["_reference_date"],
        "type_labels": TYPE_LABELS,
        "counted_types": COUNTED_TYPES,
        "totals": totals,
        "checks": checks,
        "coord_fixes": fixes,
        "by_ri": by_ri,
        "points": out,
    }


# ------------------------------------------------------------- 집별 접근성

_BUILDINGS_CACHE: dict = {}


def _buildings(raw: Path, read_meta) -> list[tuple[dict, object]]:
    """GIS건물통합정보 군위 54,977건 (속성, 도형 EPSG:5186). 한 번만 읽는다."""
    key = str(raw)
    if key in _BUILDINGS_CACHE:
        return _BUILDINGS_CACHE[key]
    meta = read_meta(BUILDING_FOLDER)
    zpath = _meta_file(raw, BUILDING_FOLDER, meta, ".zip")
    with zipfile.ZipFile(zpath) as z:
        parts = {n.rsplit(".", 1)[1]: io.BytesIO(z.read(n)) for n in z.namelist()}
    prj = parts["prj"].read().decode("ascii")
    assert 'AUTHORITY["EPSG","5186"]' in prj, f"{BUILDING_FOLDER}: 좌표계가 EPSG:5186 이 아님"
    reader = shapefile.Reader(shp=parts["shp"], shx=parts["shx"], dbf=parts["dbf"],
                              encoding=meta["encoding"])
    assert len(reader) == 54977, f"{BUILDING_FOLDER}: 건물 {len(reader)}건 (등록 시 54,977)"
    out = []
    for sr in reader.iterShapeRecords():
        g = shape(sr.shape.__geo_interface__)
        out.append((sr.record.as_dict(), g))
    _BUILDINGS_CACHE[key] = out
    return out


def read_residential(raw: Path, read_meta) -> list[dict]:
    """주거용 건물(단독·공동주택)의 중심점(EPSG:5186)과 법정리 코드."""
    houses = []
    for rec, g in _buildings(raw, read_meta):
        if rec["A9"] not in RESIDENTIAL_USES:
            continue
        assert g.is_valid and not g.is_empty, f"{rec['A1']}: 도형 오류"
        c = g.centroid
        houses.append({"ri_code": rec["A3"], "use": rec["A9"],
                       "x": round(c.x, 1), "y": round(c.y, 1),
                       "approved": str(rec["A13"]).strip() or None,
                       "structure": (rec["A11"] or "").strip()})
    return houses


def _apply_hira_fixes(raw: Path, read_meta, pts: list[dict]) -> list[str]:
    """HIRA_COORD_FIXES 의 시설 좌표를 GIS건물통합정보의 같은 이름 건물 중심점으로 바꾼다."""
    to_wgs = Transformer.from_crs(5186, 4326, always_xy=True).transform
    applied = []
    for name, fix in HIRA_COORD_FIXES.items():
        targets = [p for p in pts if p["source_id"] == "HIRA_HOSPITAL_PHARMACY" and p["name"] == name]
        assert len(targets) == 1, f"보정 대상 {name} 이 {len(targets)}건 - 원자료가 바뀌었으면 보정을 다시 확인"
        cands = [(rec, g) for rec, g in _buildings(raw, read_meta)
                 if str(rec["A24"]).strip() == fix["building_name"] and rec["A3"] == fix["ri_code"]]
        assert cands, f"{name}: 건물통합정보에 {fix['building_name']} 건물이 없다"
        rec, g = max(cands, key=lambda c: (float(c[0]["A14"] or 0), c[0]["A1"]))
        c = g.centroid
        lon, lat = to_wgs(c.x, c.y)
        p = targets[0]
        p["coord_fix"] = (f"HIRA 좌표 ({p['lon']}, {p['lat']}) 를 GIS건물통합정보 "
                          f"{rec['A4']} {rec['A5']} 건물 중심점으로 보정")
        p["lon"], p["lat"] = lon, lat
        applied.append(name)
    return applied


def _summary(dists: list[float]) -> dict:
    if not dists:
        return {"mean_m": None, "median_m": None, "max_m": None, "far_share_pct": None}
    s = sorted(dists)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"mean_m": round(sum(s) / n), "median_m": round(median), "max_m": round(s[-1]),
            "far_share_pct": round(sum(d > ACCESS_FAR_M for d in s) / n * 100, 1)}


def prepare_access(raw: Path, read_meta, ri_gj: dict, ri_fac: dict) -> dict:
    """주거용 건물마다 가장 가까운 시설까지 직선거리(m)를 재고 리·읍면별로 요약한다.

    리 배정은 건물의 법정동코드(지번 기준)를 쓴다. 좌표 판정과 다른 건수는 checks 에 남긴다.
    도로망은 쓰지 않는다 - 실제 이동거리보다 짧게 나온다.
    """
    houses = read_residential(raw, read_meta)
    ri_props = {f["properties"]["ri_code"]: f["properties"] for f in ri_gj["features"]}
    assert {h["ri_code"] for h in houses} <= set(ri_props), "현행 법정리가 아닌 건물 코드"

    # 좌표 판정 대조(건물 중심점 -> WGS84 -> 리 경계)
    to_wgs = Transformer.from_crs(5186, 4326, always_xy=True).transform
    loc = RiLocator(ri_gj)
    mismatch = 0
    for h in houses:
        lon, lat = to_wgs(h["x"], h["y"])
        if loc.locate(lon, lat) != h["ri_code"]:
            mismatch += 1
    assert mismatch <= len(houses) * 0.02, f"건물 법정동코드 vs 좌표 불일치 {mismatch}/{len(houses)}"

    # 식료품점 제외 목록이 원자료와 맞는지(번호가 있고 상호가 같은지) - 손으로 옮긴 목록이라 매번 검사한다
    stores = {p["store_id"]: p for p in ri_fac["points"] if p["type"] == "store"}
    for sid, (name, _) in GROCERY_EXCLUDE.items():
        assert sid in stores, f"식료품점 제외 목록의 상가업소번호 {sid}({name})가 원자료에 없다"
        assert stores[sid]["name"].strip() == name, f"{sid}: 상호 {stores[sid]['name']!r} != {name!r}"
        assert stores[sid]["category"].split()[0] in GROCERY_CODES, f"{sid}: 슈퍼마켓·편의점이 아님"

    to_tm = Transformer.from_crs(4326, 5186, always_xy=True).transform
    trees = {}
    for g, (types, _, keep) in ACCESS_GROUPS.items():
        pts = [Point(*to_tm(p["lon"], p["lat"])) for p in ri_fac["points"]
               if p["type"] in types and p["lon"] is not None and (keep is None or keep(p))]
        assert pts, f"{g}: 시설이 없다"
        trees[g] = (STRtree(pts), len(pts))
    house_pts = [Point(h["x"], h["y"]) for h in houses]
    for g, (tree, _) in trees.items():
        _, dist = tree.query_nearest(house_pts, return_distance=True, all_matches=False)
        assert len(dist) == len(houses)
        for h, d in zip(houses, dist):
            h[g] = float(d)

    def summarize(group: list[dict]) -> dict:
        return {"houses": len(group),
                **{g: _summary([h[g] for h in group]) for g in ACCESS_GROUPS}}

    by_ri = {}
    for code, prop in sorted(ri_props.items()):
        mine = [h for h in houses if h["ri_code"] == code]
        by_ri[code] = {"ri_name": prop["ri_name"], "region_code": prop["region_code"],
                       "region_name": prop["region_name"], **summarize(mine)}
    by_region = {}
    for rc in sorted({p["region_code"] for p in ri_props.values()}):
        mine = [h for h in houses if h["ri_code"][:8] + "00" == rc]
        by_region[rc] = summarize(mine)
    assert sum(v["houses"] for v in by_ri.values()) == len(houses)

    return {
        "_note": ("주거용 건물(GIS건물통합정보 용도 단독·공동주택) 중심점에서 가장 가까운 시설까지 직선거리(m). "
                  "도로망 미사용이라 실제 이동거리보다 짧다. 용도 빈칸 건물(대장 미연계)은 집인지 알 수 없어 "
                  "빠졌다. 사람 수가 아니라 집(건물) 수 기준이고 빈집도 포함된다. far_share_pct 의 기준 "
                  f"{ACCESS_FAR_M} m 는 프로젝트 임시값(모든 묶음 공통). 버스정류장은 운행 횟수가 없어 "
                  "거리가 가까워도 서비스 수준을 뜻하지 않는다. 읍면사무소는 좌표 자료가 없어 뺐다."),
        "reference_dates": {"buildings": "2026-09-09", "hira": "2026-09", "bus_stops": "2026-10-20",
                            "schools": "2026-09-20", "childcare": "2026-09"},
        "far_m": ACCESS_FAR_M,
        "far_m_note": "모든 묶음에 같은 기준. 시설별 기준(예: 버스 도보 1 km)은 미정",
        "groups": {g: {"label": ACCESS_LABELS[g], "types": list(t), "filter": rule,
                       "facilities": trees[g][1]}
                   for g, (t, rule, _) in ACCESS_GROUPS.items()},
        "residential_uses": list(RESIDENTIAL_USES),
        "totals": {"houses": len(houses),
                   "houses_without_approval_date": sum(1 for h in houses if not h["approved"])},
        "checks": {"건물 법정동코드 vs 중심점 좌표": {"n": len(houses), "mismatch": mismatch}},
        "gun": summarize(houses),
        "by_region": by_region,
        "by_ri": by_ri,
    }


# ------------------------------------------------------------- 노후주택

def prepare_housing_age(raw: Path, read_meta, ri_gj: dict, analysis_period: str) -> dict:
    """주거용 건물의 노후 비율. 분모는 주거용 건물 전체(사용승인일 빈칸 포함).

    old_confirmed : 사용승인일이 기준일(분석 시점 말일 - OLD_HOUSE_YEARS 년) 이전
    old_estimated : 사용승인일 빈칸 + 재래식 구조(TRADITIONAL_STRUCTURES) - 노후로 추정
    blank         : 사용승인일 빈칸 전체
    """
    import calendar
    y, m = map(int, analysis_period.split("-"))
    cutoff = f"{y - OLD_HOUSE_YEARS:04d}-{m:02d}-{calendar.monthrange(y - OLD_HOUSE_YEARS, m)[1]:02d}"
    houses = read_residential(raw, read_meta)
    for h in houses:
        a = h["approved"]
        if a:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", a), f"사용승인일 형식이 바뀜 {a!r}"
            assert a <= f"{y:04d}-{m:02d}-31", f"분석 시점 이후 사용승인 {a}"
        h["old_confirmed"] = bool(a) and a <= cutoff
        h["old_estimated"] = not a and h["structure"] in TRADITIONAL_STRUCTURES

    def summarize(group: list[dict]) -> dict:
        n = len(group)
        conf = sum(h["old_confirmed"] for h in group)
        est = sum(h["old_estimated"] for h in group)
        blank = sum(not h["approved"] for h in group)
        pct = (lambda k: round(k / n * 100, 1)) if n else (lambda k: None)
        return {"houses": n, "old_confirmed": conf, "old_estimated": est, "blank": blank,
                "old_confirmed_pct": pct(conf),           # 하한: 확인된 노후만
                "old_with_estimate_pct": pct(conf + est),  # 주 지표: 확인 + 구조 추정
                "blank_pct": pct(blank)}                   # 추정에 기댄 정도

    ri_props = {f["properties"]["ri_code"]: f["properties"] for f in ri_gj["features"]}
    by_ri = {code: {"ri_name": p["ri_name"], "region_code": p["region_code"],
                    "region_name": p["region_name"],
                    **summarize([h for h in houses if h["ri_code"] == code])}
             for code, p in sorted(ri_props.items())}
    by_region = {rc: summarize([h for h in houses if h["ri_code"][:8] + "00" == rc])
                 for rc in sorted({p["region_code"] for p in ri_props.values()})}
    gun = summarize(houses)
    assert sum(v["houses"] for v in by_ri.values()) == gun["houses"]
    return {
        "_note": (f"주거용 건물(단독·공동주택) 중 사용승인 후 {OLD_HOUSE_YEARS}년 이상(사용승인일 ≤ {cutoff}). "
                  "사용승인일 빈칸 + 재래식 구조(목·조적·블록·벽돌·석)는 노후로 추정한다. 분모는 주거용 건물 "
                  "전체. 주 지표는 old_with_estimate_pct, 하한은 old_confirmed_pct, blank_pct 는 추정 의존도. "
                  "노후 기준 연수는 공식 기준이 아닌 프로젝트 기준."),
        "reference_date": "2026-09-09",
        "analysis_period": analysis_period,
        "old_house_years": OLD_HOUSE_YEARS,
        "cutoff_date": cutoff,
        "traditional_structures": list(TRADITIONAL_STRUCTURES),
        "gun": gun,
        "by_region": by_region,
        "by_ri": by_ri,
    }
