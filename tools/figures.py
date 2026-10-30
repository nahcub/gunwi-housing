"""data/derived -> outputs/figures/ 보고서 삽화

값은 tools/build.py 의 build_regions() 를 그대로 쓴다 - 웹과 같은 숫자다.
raw 는 읽지 않는다. 기준 시점은 export_excel.py 의 ANALYSIS_PERIOD 와 같다.

  python tools/figures.py

출력 (PNG, 그림2 는 근거표 CSV 포함)
  그림1_읍면별_지표지도.png          읍면 비교 지표 4개 읍면 지도
  그림2_지표간_순위상관.png  (+ csv)  지표끼리의 Spearman 순위상관
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402
from export_excel import ANALYSIS_PERIOD  # noqa: E402

DERIVED = ROOT / "data" / "derived"
OUT = ROOT / "outputs" / "figures"

# 그림1 에 그릴 지표 - 읍면 비교가 의미 있는 비율·지수
MAP_INDICATORS = ["elderly_ratio", "aging_index", "senior_center_old_ratio",
                  "senior_center_per_1k_elderly"]
CRITICAL_RHO_N8 = 0.738   # n=8, 양측 5% Spearman 임계값. 이보다 작으면 우연과 구분되지 않는다


def _font() -> None:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Malgun Gothic", "AppleGothic", "NanumGothic",
                 "Noto Sans CJK KR", "Noto Sans CJK JP"):
        if cand in names:
            plt.rcParams["font.family"] = cand
            break
    else:
        print("  ! 한글 글꼴을 찾지 못했다 - 그림의 한글이 깨질 수 있다")
    plt.rcParams["axes.unicode_minus"] = False


def _save(fig, name: str) -> None:
    path = OUT / name
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  {path.relative_to(ROOT)}")


def _rows() -> list[dict]:
    rows = build.build_regions()["regions"][ANALYSIS_PERIOD]
    assert len(rows) == 8
    return rows


def _ind(iid: str) -> dict:
    return next(i for i in build.INDICATORS if i["id"] == iid)


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1     # 동순위는 평균 순위
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _rank(a), _rank(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den


# ---------------------------------------------------------------- 그림1

def fig_maps(rows: list[dict]) -> None:
    gj = json.loads((DERIVED / "eupmyeon.geojson").read_text(encoding="utf-8"))
    by_code = {r["region_code"]: r for r in rows}
    lat0 = 36.18
    fig, axes = plt.subplots(2, 2, figsize=(11, 11.5))
    for ax, iid in zip(axes.flat, MAP_INDICATORS):
        ind = _ind(iid)
        vals = [r[iid] for r in rows]
        lo, hi = min(vals), max(vals)
        cmap = plt.get_cmap("OrRd" if ind["higher_is_worse"] else "OrRd_r")
        patches, colors = [], []
        for f in gj["features"]:
            code = f["properties"]["region_code"]
            v = by_code[code][iid]
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                patches.append(Polygon(poly[0], closed=True))
                colors.append(cmap((v - lo) / (hi - lo) if hi > lo else 0.5))
            # 라벨은 가장 큰 고리의 평균점 근처에
            ring = max((p[0] for p in polys), key=len)
            cx = statistics.mean(x for x, _ in ring)
            cy = statistics.mean(y for _, y in ring)
            ax.text(cx, cy, f"{by_code[code]['name']}\n{v:g}", ha="center", va="center",
                    fontsize=6.8, bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7))
        ax.add_collection(PatchCollection(patches, facecolor=colors, edgecolor="#555", linewidth=0.6))
        ax.autoscale_view()
        ax.set_aspect(1 / math.cos(math.radians(lat0)))
        ax.set_axis_off()
        ref = f" · {ind['reference']}" if ind.get("reference") else ""
        ax.set_title(f"{ind['label']} ({ind['unit'] or '지수'})", fontsize=11)
        ax.text(0.5, -0.02, f"{'높을수록 취약' if ind['higher_is_worse'] else '낮을수록 취약'}{ref}",
                transform=ax.transAxes, ha="center", va="top", fontsize=7, color="#666")
    fig.suptitle(f"군위군 읍면별 지표 (인구 기준 {ANALYSIS_PERIOD}, 진할수록 취약 방향)", fontsize=14)
    note = ("읍면 경계: SGIS 2025년 2분기" if gj.get("_provenance") == "verified"
            else f"읍면 경계 출처 {gj.get('_provenance')}")
    fig.text(0.5, 0.01, f"색 구간은 8개 읍면 안에서의 상대 척도다. {note}.",
             ha="center", fontsize=8, color="#666")
    _save(fig, "그림1_읍면별_지표지도.png")


# ---------------------------------------------------------------- 그림2

def fig_correlation(rows: list[dict]) -> None:
    ids = [i["id"] for i in build.INDICATORS if i["status"] == "available"]
    labels = [_ind(i)["label"] for i in ids]
    cols = {i: [r[i] for r in rows] for i in ids}
    n = len(ids)
    m = [[spearman(cols[a], cols[b]) for b in ids] for a in ids]

    with open(OUT / "그림2_지표간_순위상관.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["지표"] + labels)
        for lab, row in zip(labels, m):
            w.writerow([lab] + [round(x, 2) for x in row])

    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(m, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n), labels, rotation=45, ha="right", fontsize=8.5)
    ax.set_yticks(range(n), labels, fontsize=8.5)
    for i in range(n):
        for j in range(n):
            strong = abs(m[i][j]) >= CRITICAL_RHO_N8 and i != j
            ax.text(j, i, f"{m[i][j]:.2f}", ha="center", va="center", fontsize=7.5,
                    fontweight="bold" if strong else "normal",
                    color="white" if abs(m[i][j]) > 0.6 else "#222")
    fig.colorbar(im, ax=ax, shrink=0.75, label="Spearman ρ")
    ax.set_title("지표끼리의 순위상관 (읍면 8개, 인구 기준 " + ANALYSIS_PERIOD + ")", fontsize=12)
    fig.text(0.5, -0.07, f"굵은 글씨 = |ρ| ≥ {CRITICAL_RHO_N8} (n=8 양측 5% 임계값). "
             "지표끼리 같이 움직이는지 본 것이다 - 같이 움직이는 지표는 같은 현상을 다른 분모로 본 것일 수 있다.",
             ha="center", fontsize=8, color="#666", wrap=True)
    _save(fig, "그림2_지표간_순위상관.png")


def main() -> None:
    _font()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _rows()
    print("outputs/figures 생성:")
    fig_maps(rows)
    fig_correlation(rows)


if __name__ == "__main__":
    main()
