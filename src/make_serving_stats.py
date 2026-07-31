"""
서빙용 집계값 만들기 — models/serving_stats.json

서비스는 개별 임가의 행을 필요로 하지 않습니다. 필요한 것은 그 행들에서 나온
통계값입니다. 기준값은 집단 평균이고, 또래 분포는 히스토그램이며, 순위는 분위수고,
유사 임가 비교는 비슷한 조건 집단의 중앙값입니다.

그런데 지금까지는 전처리된 행자료(processed_*.parquet)를 그대로 배포본에 실어
왔습니다. 임가경제조사·임산물생산비조사에서 나온 임가 단위 자료라, 공개 저장소에
두면 사실상 마이크로데이터를 다시 배포하는 셈입니다. MDIS 이용 약관이 막는 일입니다.

그래서 필요한 통계값만 미리 뽑아 둡니다. 집단 하나에 5곳이 못 되면 아예 뺍니다.
통계 공표에서 쓰는 것과 같은 방식이고, 오히려 떳떳합니다.

산출: models/serving_stats.json
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_A = os.path.join(ROOT, "data", "processed_forestry_data.parquet")
DATA_B = os.path.join(ROOT, "data", "processed_cost_data.parquet")
OUT = os.path.join(ROOT, "models", "serving_stats.json")

MIN_CELL = 5          # 이보다 적은 집단은 내보내지 않습니다
QGRID = list(range(0, 101, 2))   # 분위수 격자 (2%p 간격)

# 유사 임가 비교에서 무엇이 갈리는지 볼 항목
CMP = ["임업경영비", "ha당_경영비", "경영비_자본비율", "임업외소득", "ha당_가용노동력"]
CELL_KEYS = ["지역별", "업종별", "임지규모별", "전/겸업별", "경영비구간"]
# 경영비 구간을 셀 열쇠에 넣습니다. 범주 넷만 맞추면 같은 지역·작목·규모라도
# 경영비가 세 배 차이 나는 임가가 한 집단에 들어갑니다. 그러면 "잘 버는 쪽이
# 무엇이 다른가"라는 물음의 답이 어긋납니다. 실제로 재 보니 기존 방식과
# 1순위 항목이 32%밖에 안 맞았습니다.
COST_BINS = 3
# 구간 수를 0·3·4·6·8로 바꿔 가며 기존 방식과 얼마나 맞는지 재 봤습니다.
# 3개일 때가 가장 나았습니다(1순위 항목 38%, 중앙값 차 29.5%p).
# 더 잘게 쪼개면 집단이 작아져 중앙값이 흔들려 오히려 나빠집니다.


def q(series: pd.Series) -> list[float]:
    """분위수 격자. 원래 값을 그대로 늘어놓지 않으면서 분포를 담습니다."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return []
    return [round(float(v), 3) for v in np.percentile(s, QGRID)]


def hist(series: pd.Series, bins: int = 36) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {}
    counts, edges = np.histogram(s, bins=bins)
    return {"bins": [round(float((edges[i] + edges[i + 1]) / 2), 2) for i in range(len(counts))],
            "counts": [int(c) for c in counts]}


def med(g: pd.DataFrame, c: str):
    if c not in g.columns:
        return None
    v = pd.to_numeric(g[c], errors="coerce").median()
    return None if pd.isna(v) else round(float(v), 4)


def build_a(df: pd.DataFrame) -> dict:
    out: dict = {}
    df = df.copy()
    # 경영비를 전체 기준 사분위로 나눕니다. 로그를 씌우는 이유는 금액이
    # 자릿수로 벌어져 그대로 자르면 큰 값 쪽이 한 칸에 몰리기 때문입니다.
    lc = np.log1p(pd.to_numeric(df["임업경영비"], errors="coerce").clip(lower=0))
    edges = [float(v) for v in np.nanpercentile(lc, np.linspace(0, 100, COST_BINS + 1))]
    df["경영비구간"] = np.clip(np.searchsorted(edges[1:-1], lc, side="right"),
                           0, COST_BINS - 1)
    out["경영비구간_경계"] = [round(float(np.expm1(e)), 0) for e in edges]

    # ── 기준값 — 산림청 현행 방식(지역x업종 평균) ──
    g2 = df.groupby(["지역별", "업종별"], observed=True)["ROI"].agg(["mean", "size"])
    out["baseline_지역x업종"] = {f"{int(a)}x{int(b)}": round(float(r["mean"]), 3)
                             for (a, b), r in g2.iterrows() if r["size"] >= MIN_CELL}
    g1 = df.groupby("업종별", observed=True)["ROI"].agg(["mean", "size"])
    out["baseline_업종"] = {str(int(k)): round(float(r["mean"]), 3)
                          for k, r in g1.iterrows() if r["size"] >= MIN_CELL}
    out["baseline_전체"] = round(float(df["ROI"].mean()), 3)

    # ── 또래 분포·순위 ──
    peer = {}
    for code, g in df.groupby("업종별", observed=True):
        if len(g) < MIN_CELL:
            continue
        peer[str(int(code))] = {"n": int(len(g)), "quantiles": q(g["ROI"]), **hist(g["ROI"])}
    out["peer_업종"] = peer

    # ── 유사 임가 비교용 집단표 ──
    # 조건이 같은 집단 안에서 수익이 높은 쪽과 낮은 쪽이 무엇에서 갈리는지 미리 계산합니다.
    cells = []
    for key, g in df.groupby(CELL_KEYS, observed=True):
        if len(g) < MIN_CELL:
            continue
        m = float(g["ROI"].median())
        hi, lo = g[g["ROI"] > m], g[g["ROI"] <= m]
        cells.append({
            "key": [int(v) for v in key],
            "n": int(len(g)),
            "ROI중앙값": round(m, 2),
            "ROI상위중앙값": round(float(hi["ROI"].median()), 2) if len(hi) else None,
            "ROI분위수": q(g["ROI"]),
            "잘버는쪽": {c: med(hi, c) for c in CMP},
            "그외": {c: med(lo, c) for c in CMP},
            "대표": {c: med(g, c) for c in ("임업경영비", "기초_자본(순재산)", "임업외소득")},
        })
    out["cells"] = cells
    out["cell_keys"] = CELL_KEYS
    out["표본수"] = int(len(df))
    return out


def build_b(df: pd.DataFrame) -> dict:
    ratios = ["노동비_비중", "비료비_비중", "농약비_비중", "감가상각비_비중", "위탁영농비_비중"]
    items = {}
    for it, g in df.groupby("품목", observed=True):
        if len(g) < MIN_CELL:
            continue
        lead = g[g["경영수준별"] == 1] if "경영수준별" in g.columns else g.iloc[:0]
        items[str(it)] = {
            "n": int(len(g)),
            "ROI중앙값": round(float(g["ROI"].median()), 2),
            "ROI분위수": q(g["ROI"]),
            **hist(g["ROI"]),
            "선도_n": int(len(lead)),
            "선도_ROI중앙값": round(float(lead["ROI"].median()), 2) if len(lead) else None,
            "선도_비목중앙값": {c: med(lead, c) for c in ratios} if len(lead) else {},
        }
    return {"품목": items, "표본수": int(len(df))}


def main() -> None:
    if not (os.path.exists(DATA_A) and os.path.exists(DATA_B)):
        raise SystemExit("전처리 산출물이 없습니다. preprocess.py / preprocess_cost.py 먼저.")

    a = build_a(pd.read_parquet(DATA_A))
    b = build_b(pd.read_parquet(DATA_B))
    doc = {
        "설명": ("서비스가 쓰는 통계값입니다. 개별 임가의 행은 들어 있지 않습니다. "
               f"집단 하나에 {MIN_CELL}곳이 못 되면 내보내지 않았습니다."),
        "출처": "산림청 「임가경제조사」·「임산물생산비조사」 마이크로데이터 (통계청 MDIS)",
        "최소집단": MIN_CELL,
        "model_a": a,
        "model_b": b,
    }
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"[saved] {OUT}  ({os.path.getsize(OUT)/1e6:.2f} MB)")
    print(f"  기준값  지역x업종 {len(a['baseline_지역x업종'])}개 · 업종 {len(a['baseline_업종'])}개")
    print(f"  또래분포 업종 {len(a['peer_업종'])}개")
    cov = sum(c["n"] for c in a["cells"])
    print(f"  비교집단 {len(a['cells'])}개 · 임가 {cov:,}곳 포함 "
          f"({cov / a['표본수'] * 100:.0f}%)  (전체 {a['표본수']:,}곳)")
    print(f"  경영비 구간 경계 {[f'{v/1e4:,.0f}만' for v in a['경영비구간_경계']]}")
    print(f"  품목    {len(b['품목'])}개  (원래 관측 {b['표본수']:,}건)")


if __name__ == "__main__":
    main()
