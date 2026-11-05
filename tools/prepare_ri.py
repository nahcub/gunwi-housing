"""법정리(리) 단위: 리 경계 정리 + 시설을 리에 배정한다. prepare.py 가 부른다.

리 단위 분석의 공간단위는 법정리 92개다(행정리 경계는 공개 자료가 없다).
배정 방법은 자료마다 다르고, 여기 한 곳에서만 정한다.

  좌표가 있는 자료  -> 리 경계에 점을 넣어 판정(point-in-polygon)
  상가정보          -> 원자료의 법정동코드(=법정리 코드)를 그대로 쓰고, 좌표 판정과 대조
                       (상가 좌표는 큰 건물 하나에 여러 업소가 같은 점으로 찍혀 리 경계 근처에서
                        어긋난다 - 2026-11-05 첫 실행에서 1,155건 중 9건. 지번 기준 코드를 따른다)
  주소만 있는 폐교  -> 주소의 '읍면 + 리' 이름을 법정동코드 목록에 맞춘다

배정만 한다. 기준이 아직 정해지지 않은 것(버스정류장 중복, 식료품점 상호 검토,
학교 '운영' 정의)은 여기서 걸러내거나 세지 않는다 - 점마다 원자료 구분값을 남겨
둔다. 기준은 docs/methodology.md 에 먼저 적고 나서 센다.
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
    pts += _hira(raw, read_meta) + _schools(raw, read_meta) + _childcare(raw, read_meta)
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
                  "리별로 세지 않는다 - 기준은 docs/methodology.md 에서 정한다."),
        "ri_boundary_reference_date": ri_gj["_reference_date"],
        "type_labels": TYPE_LABELS,
        "counted_types": COUNTED_TYPES,
        "totals": totals,
        "checks": checks,
        "by_ri": by_ri,
        "points": out,
    }
