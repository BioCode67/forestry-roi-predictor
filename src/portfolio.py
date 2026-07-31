"""
Phase 2-L — 작목 조합의 위험 분산 효과

임업 조언은 대개 "무엇이 가장 돈이 되는가" 하나만 답합니다. 그런데 임가가 실제로
겪는 문제는 그해 시세와 작황이 흔들린다는 것입니다. 한 작목에만 걸면 좋은 해와
나쁜 해의 폭이 그대로 소득 폭이 됩니다. 여러 작목을 섞으면 그 폭이 줄어듭니다.
작목들이 같은 해에 같은 방향으로만 움직이지는 않기 때문입니다.

── 위험을 어떻게 쟀는가 (여기가 핵심입니다)

임산물생산비조사의 ROI는 두 가지 이유로 흩어집니다.

  (가) 연도 효과 — 그해 시세·작황. 모든 임가가 함께 겪습니다.
  (나) 임가 효과 — 같은 해 같은 작목 안에서도 임가마다 다릅니다. 산의 상태,
       기술, 판로의 차이입니다.

작목을 섞어서 줄일 수 있는 것은 (가)뿐입니다. (나)는 그 임가의 특성이라 어느
작목을 하든 따라옵니다. 밤과 대추를 반씩 해도 서툰 사람은 양쪽 다 서툽니다.

그래서 이 계산은 (가)만 분산 대상으로 놓습니다. 임가 간 산포를 그대로 위험에
넣으면 √n 효과로 변동폭이 터무니없이 작게 나옵니다. (나)는 줄어들지 않는 몫으로
따로 표시합니다.

── 상관계수를 믿을 수 있는가

없습니다. 표고는 2018~2022, 과실류(밤·대추·떫은감)는 2020~2024 자료라 겹치는
해가 3년뿐입니다. 점 3개로 잰 상관은 우연히 ±1에 가깝게 나오기 쉽습니다.
그래서 겹친 해 수에 따라 0쪽으로 강하게 수축시키고, 그러고도 행렬이 성립하지
않으면(음의 분산) 가장 가까운 정상 행렬로 보정합니다. 더불어 "작목들이 실은
어느 정도 같이 움직인다"고 보는 보수적 가정(ρ=0.3)에서도 같은 계산을 돌려
결론이 뒤집히지 않는지 확인합니다.

── 이 결과로 하면 안 되는 말

"내년부터 이 비율로 나누십시오"는 아닙니다. 작목을 바꾸려면 나무를 새로 심어
수확까지 여러 해가 걸리고, 면적을 쪼개면 규모의 경제가 줄며, 기술과 판로도
작목마다 다릅니다. 표고는 만본당, 나머지는 ha당 기준이라 면적을 그대로 나눈다는
뜻도 아닙니다. 읽어야 할 것은 "한 작목에 몰면 해마다 얼마나 흔들리고, 섞으면
얼마나 줄어드는가"입니다.

산출: models/portfolio.json
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed_cost_data.parquet")
OUT = os.path.join(ROOT, "models", "portfolio.json")

MIN_ROWS = 150       # 품목별 최소 관측
MIN_YEARS = 3        # 연도 변동을 재려면 최소 3개 연도
N_PORTFOLIO = 6000   # 무작위 비중 조합 수
SHRINK_K = 8.0       # 상관 수축 강도 — 겹친 해가 적을수록 0에 가깝게
FLAT_RHO = 0.3       # 보수적 대안 가정
SEED = 42


# ── 자료 ──────────────────────────────────────────────────────────────────
def load() -> pd.DataFrame:
    df = pd.read_parquet(DATA)
    n = df.groupby("품목", observed=True)["ROI"].size()
    y = df.groupby("품목", observed=True)["조사연도"].nunique()
    keep = n[(n >= MIN_ROWS) & (y >= MIN_YEARS)].index
    return df[df["품목"].isin(keep)].copy()


def decompose(df: pd.DataFrame):
    """연도 효과와 임가 효과를 갈라냅니다.

    연도 효과는 연도별 중앙값 계열로 봅니다. 평균이 아니라 중앙값을 쓰는 이유는
    ROI가 오른쪽으로 길게 늘어진 분포라 소수의 대박 임가가 계열 전체를 끌고
    다니기 때문입니다.
    """
    per = df.groupby(["품목", "조사연도"], observed=True)["ROI"].median().unstack(0)
    items = [c for c in per.columns if per[c].notna().sum() >= MIN_YEARS]
    per = per[items]

    mu = per.mean()          # 기대수익 = 연도별 중앙값의 평균
    sys_sd = per.std()       # 분산 가능한 위험 = 해마다 흔들리는 폭

    # 임가 효과 = 같은 해·같은 작목 안에서의 산포. 연도 중앙값을 뺀 잔차로 봅니다.
    resid = df.merge(
        per.stack().rename("연도중앙값").reset_index(),
        on=["품목", "조사연도"], how="inner")
    resid["잔차"] = resid["ROI"] - resid["연도중앙값"]
    # 표준편차 대신 사분위 범위를 σ로 환산합니다. 극단값에 덜 휘둘립니다.
    idio = resid.groupby("품목", observed=True)["잔차"].quantile(0.75) \
        - resid.groupby("품목", observed=True)["잔차"].quantile(0.25)
    idio = (idio / 1.349).reindex(items)

    return per, mu, sys_sd, idio


def correlation(per: pd.DataFrame):
    """겹친 해 수에 따라 0쪽으로 수축시킨 상관 행렬."""
    items = list(per.columns)
    raw = per.corr(min_periods=MIN_YEARS).reindex(index=items, columns=items)
    overlap = per.notna().astype(int).T @ per.notna().astype(int)  # 짝별 공통 연도 수

    C = np.eye(len(items))
    detail = []
    for i, a in enumerate(items):
        for j, b in enumerate(items):
            if i >= j:
                continue
            n = int(overlap.iloc[i, j])
            r = raw.iloc[i, j]
            r = 0.0 if pd.isna(r) else float(r)
            lam = max(n - 1, 0) / (max(n - 1, 0) + SHRINK_K)  # n이 작으면 λ→0
            s = lam * r
            C[i, j] = C[j, i] = s
            detail.append({"a": a, "b": b, "공통연도": n,
                           "원상관": round(r, 2), "수축후": round(s, 2)})
    return nearest_psd(C), detail


def nearest_psd(C: np.ndarray) -> np.ndarray:
    """음의 고윳값을 잘라내 실제로 성립하는 상관 행렬로 되돌립니다.

    수축을 거쳐도 짝별로 따로 다듬은 행렬은 전체가 모순일 수 있습니다
    (A와 B가 같이 가고 B와 C가 같이 가는데 A와 C가 반대로 가는 식). 그대로 두면
    분산이 음수가 되어 √에서 NaN이 납니다.
    """
    w, V = np.linalg.eigh((C + C.T) / 2)
    C2 = V @ np.diag(np.clip(w, 1e-8, None)) @ V.T
    d = np.sqrt(np.diag(C2))
    return C2 / np.outer(d, d)


# ── 조합 탐색 ─────────────────────────────────────────────────────────────
def explore(items, mu, sd, C, rng):
    """무작위 비중 + 단일 작목 꼭짓점을 함께 놓고 위험-수익을 잽니다."""
    n = len(items)
    cov = np.outer(sd, sd) * C
    W = np.vstack([rng.dirichlet(np.ones(n), size=N_PORTFOLIO), np.eye(n)])
    ret = W @ mu
    var = np.einsum("ij,jk,ik->i", W, cov, W)
    vol = np.sqrt(np.clip(var, 0, None))
    return W, ret, vol


def frontier(ret, vol, bins=26):
    """수익 구간마다 변동폭이 가장 작은 조합 — 효율적 투자선."""
    edges = np.linspace(ret.min(), ret.max(), bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (ret >= lo) & (ret <= hi)
        if m.sum():
            k = np.flatnonzero(m)[np.argmin(vol[m])]
            out.append(int(k))
    return out


def pack(items, W, ret, vol, idio, i, floor=0.02):
    w = W[i]
    # 줄지 않는 몫: 임가 효과는 같은 사람이 여러 작목을 하므로 비중 가중 합으로 봅니다
    return {
        "구성": [{"품목": items[j], "비중_pct": round(float(w[j]) * 100, 1)}
                for j in np.argsort(-w) if w[j] >= floor],
        "기대수익_pct": round(float(ret[i]), 1),
        "연도변동_pct": round(float(vol[i]), 1),
        "임가격차_pct": round(float(w @ idio), 1),
        "효율": round(float(ret[i] / vol[i]), 2) if vol[i] > 0 else None,
    }


def main() -> None:
    rng = np.random.default_rng(SEED)
    df = load()
    per, mu, sys_sd, idio = decompose(df)
    items = list(mu.index)
    C, corr_detail = correlation(per)

    muv, sdv, idv = mu.to_numpy(), sys_sd.to_numpy(), idio.to_numpy()
    W, ret, vol = explore(items, muv, sdv, C, rng)

    eff = np.divide(ret, vol, out=np.full_like(ret, -np.inf), where=vol > 1e-9)
    best = int(np.argmax(eff))
    minvol = int(np.argmin(vol))

    # 보수적 대안: 작목들이 실은 ρ=0.3 만큼 같이 움직인다고 보면?
    Cf = np.full((len(items), len(items)), FLAT_RHO)
    np.fill_diagonal(Cf, 1.0)
    W2, ret2, vol2 = explore(items, muv, sdv, Cf, rng)
    eff2 = np.divide(ret2, vol2, out=np.full_like(ret2, -np.inf), where=vol2 > 1e-9)
    best2 = int(np.argmax(eff2))

    single = [{"품목": it,
               "기대수익_pct": round(float(mu[it]), 1),
               "연도변동_pct": round(float(sys_sd[it]), 1),
               "임가격차_pct": round(float(idio[it]), 1),
               "효율": round(float(mu[it] / sys_sd[it]), 2) if sys_sd[it] else None,
               "표본수": int((df["품목"] == it).sum()),
               "조사연도": [int(y) for y in sorted(per.index[per[it].notna()])]}
              for it in items]
    single_best = max(single, key=lambda r: r["효율"] or 0)

    fr = frontier(ret, vol)
    best_pack = pack(items, W, ret, vol, idv, best)

    res = {
        "출처": "산림청 「임산물생산비조사」 마이크로데이터 — 품목별 단위면적당 ROI",
        "품목": single,
        "상관": corr_detail,
        "최고효율": best_pack,
        "최저변동": pack(items, W, ret, vol, idv, minvol),
        "단일_최고효율": single_best,
        "분산효과_pct": round(
            (best_pack["효율"] / single_best["효율"] - 1) * 100, 1)
        if single_best["효율"] and best_pack["효율"] else None,
        "보수가정": {
            "가정": f"작목 간 상관을 일률적으로 {FLAT_RHO}로 놓았을 때",
            **pack(items, W2, ret2, vol2, idv, best2),
        },
        "효율선": [{"vol": round(float(vol[i]), 1), "ret": round(float(ret[i]), 1),
                  "구성": [{"품목": items[j], "비중_pct": round(float(W[i][j]) * 100, 1)}
                          for j in np.argsort(-W[i]) if W[i][j] >= 0.05]}
                 for i in fr],
        "표본": [{"vol": round(float(vol[i]), 2), "ret": round(float(ret[i]), 2)}
                for i in rng.choice(N_PORTFOLIO, size=min(800, N_PORTFOLIO), replace=False)],
        "방법": (
            "ROI의 흩어짐을 연도 효과와 임가 효과로 나눈 뒤, 작목을 섞어 줄일 수 있는 "
            "연도 효과만 위험으로 놓았습니다. 임가 효과는 그 임가의 특성이라 작목을 "
            "바꿔도 따라오므로 '줄지 않는 몫'으로 따로 표시합니다. 기대수익은 연도별 "
            "중앙값의 평균, 연도변동은 그 계열의 표준편차입니다. 작목 간 상관은 겹친 "
            f"조사연도 수에 따라 0쪽으로 수축(λ=n−1/(n−1+{SHRINK_K:.0f}))시키고 "
            f"가장 가까운 정상 행렬로 보정했습니다. 비중 조합 {N_PORTFOLIO:,}개를 "
            "무작위로 만들어 단일 작목과 함께 비교했습니다."),
        "한계": (
            "표고는 2018~2022년, 과실류는 2020~2024년 자료라 겹치는 해가 3년뿐입니다. "
            "작목 간 상관은 사실상 추정이 어렵다고 보는 편이 맞고, 그래서 수축과 "
            f"보수 가정(ρ={FLAT_RHO})을 함께 실었습니다. 또한 작목 전환은 수확까지 "
            "여러 해가 걸리고, 면적을 쪼개면 규모의 경제가 줄며, 기술과 판로도 작목마다 "
            "다릅니다. 표고는 만본당·나머지는 ha당 기준이라 면적을 그대로 나눈다는 뜻이 "
            "아닙니다. 배분 지침이 아니라 한 작목에 몰 때의 위험을 가늠하는 참고입니다."),
    }
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ── 출력 ──
    print(f"[saved] {OUT}\n")
    print(f"{'품목':10s} {'기대수익':>8s} {'연도변동':>8s} {'임가격차':>8s} {'효율':>6s} {'표본':>7s}  조사연도")
    for r in sorted(single, key=lambda x: -(x["효율"] or 0)):
        yrs = f"{r['조사연도'][0]}~{r['조사연도'][-1]}"
        print(f"{r['품목']:10s} {r['기대수익_pct']:>7.1f}% {r['연도변동_pct']:>7.1f}% "
              f"{r['임가격차_pct']:>7.1f}% {r['효율']:>6.2f} {r['표본수']:>7,}  {yrs}")

    print("\n작목 간 상관 (공통연도 수에 따라 수축)")
    for d in sorted(corr_detail, key=lambda x: -abs(x["수축후"])):
        print(f"  {d['a']:6s}–{d['b']:6s}  공통 {d['공통연도']}년  "
              f"원 {d['원상관']:+.2f} → 수축 {d['수축후']:+.2f}")

    print(f"\n단일 최고효율 : {single_best['품목']}  효율 {single_best['효율']} "
          f"(수익 {single_best['기대수익_pct']}% / 변동 {single_best['연도변동_pct']}%)")
    b = res["최고효율"]
    print(f"조합 최고효율 : 효율 {b['효율']} — "
          + " · ".join(f"{c['품목']} {c['비중_pct']}%" for c in b["구성"]))
    print(f"                수익 {b['기대수익_pct']}% / 연도변동 {b['연도변동_pct']}% "
          f"/ 줄지 않는 임가격차 ±{b['임가격차_pct']}%")
    print(f"분산으로 얻는 효율 개선: {res['분산효과_pct']:+.1f}%")
    c = res["보수가정"]
    print(f"보수 가정(ρ={FLAT_RHO}) : 효율 {c['효율']} — "
          + " · ".join(f"{x['품목']} {x['비중_pct']}%" for x in c["구성"]))
    m = res["최저변동"]
    print(f"최저변동 조합 : 변동 {m['연도변동_pct']}% / 수익 {m['기대수익_pct']}% — "
          + " · ".join(f"{x['품목']} {x['비중_pct']}%" for x in m["구성"]))


if __name__ == "__main__":
    main()
