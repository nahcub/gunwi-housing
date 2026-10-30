#!/usr/bin/env python3
"""빈집애(한국부동산원 빈집정보시스템) 군위군 읍면별 빈집 수 수집기

빈집애 지도(https://www.binzibe.kr/main/html/map.html)가 화면을 그릴 때 부르는
내부 API 응답을 받은 그대로 저장한다. 공식 공개(Open API) 목록에 있는 API 가 아니다.
인증키는 필요 없다.

  python tools/fetch_binzibe.py                 # 프로젝트 루트/binzibe-download/ 에 저장
  python tools/add_source.py ... --file binzibe-download/rank.json ...   # 받은 4개 파일을 등록

저장 파일
  rank.json                   읍면별 빈집 수 (rank API 응답 바이트 그대로)
  filter-options.json         지도 필터의 조사연도 목록 (year 값 근거)
  capture.html                지도 페이지 원본 HTML (안내문: 지자체 행정조사, 국가승인통계 아님)
  capture-map-filter-loader.js 조사연도 표시 방식 근거 (화면에는 year - 1 로 표시)
"""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.binzibe.kr"
# sreg=27 대구광역시, sigungu=27720 군위군(통계청 최신 시군구 코드. 프로젝트 region_code 와 다른 체계)
RANK = "/apihome/map/vacant-houses/rank?year={year}&sreg=27&sigungu=27720&mapInfo=VACANT_COUNT"
FILES = {
    "filter-options.json": "/apihome/map/filter-options",
    "capture.html": "/main/html/map.html",
    "capture-map-filter-loader.js": "/main/js/map-filter-loader.js",
}


def get(path: str) -> bytes:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser(description="빈집애 군위군 읍면별 빈집 수 수집")
    ap.add_argument("--year", default="2026", help="API 의 year 값 (화면 표시는 year - 1 년)")
    ap.add_argument("--out", default=str(ROOT / "binzibe-download"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    targets = {"rank.json": RANK.format(year=args.year), **FILES}
    for name, path in targets.items():
        body = get(path)
        (out / name).write_bytes(body)
        print(f"{name:30s} {len(body):>8,} bytes  <- {BASE}{path}")


if __name__ == "__main__":
    main()
