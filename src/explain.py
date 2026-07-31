"""
Phase 2-K — 개인화 설명 · 반사실 처방 · 유사 임가 탐색

예측값 하나만 주면 임가는 그 숫자를 믿을 근거가 없습니다. 이 모듈은 같은 모델에서
세 가지를 더 끌어냅니다.

  ① 왜 이 숫자인가   — SHAP 기여도로 예측을 항목별로 분해
  ② 무엇을 바꿔야 하나 — 목표 수준에 닿는 최소 변경을 탐색(반사실 처방)
  ③ 누구를 보면 되나  — 조건이 비슷한데 더 잘 버는 임가를 찾아 차이를 보여줌

①은 XGBoost의 `pred_contribs`를 씁니다. TreeSHAP을 트리 구조에서 바로 계산하므로
별도 배경 표본이 필요 없고 밀리초 단위로 끝납니다. 기여도의 합에 기준값을 더하면
예측값과 정확히 일치하므로(가법 분해), 화면에서 "이만큼은 경영비 때문, 이만큼은
업종 때문"이라고 나눠 말할 수 있습니다.

②는 임가가 실제로 바꿀 수 있는 변수만 후보로 둡니다. 지역이나 연령을 바꾸라는
처방은 조언이 아니기 때문입니다.
"""
from __future__ import annotations

import os
from itertools import product

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 임가가 실제로 통제할 수 있는 변수만 처방 후보로 삼습니다.
# 지역·연령·가구원수는 바꿀 수 없거나 바꾸라고 말할 성질이 아닙니다.
ACTIONABLE = {
    # 경영비는 올해 당장 조절할 수 있습니다. 폭을 촘촘히 둡니다.
    "임업경영비": {"label": "한 해 쓰는 돈", "type": "num", "기간": "올해",
                "grid": [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6, 1.8, 2.1]},
    # 전업 전환은 결심의 문제라 후보에 둡니다.
    "전/겸업별": {"label": "전업 / 겸업", "type": "cat", "기간": "중기"},
    # 작목 전환은 수확까지 여러 해가 걸립니다. 처방이 아니라 검토 방향으로 표시합니다.
    "업종별": {"label": "작목", "type": "cat", "기간": "장기"},
}
# 임지 규모는 뺐습니다. "산을 1ha 미만으로 줄이면"은 땅을 팔라는 말이라
# 조언이 될 수 없습니다. 규모 효과는 유사 임가 비교에서 대신 다룹니다.

# 화면에 그대로 쓸 수 있는 쉬운 이름
FEATURE_LABEL = {
    "임업경영비": "한 해 쓰는 돈", "log_임업경영비": "한 해 쓰는 돈(규모 효과)",
    "ha당_경영비": "면적당 쓰는 돈", "log_ha당_경영비": "면적당 쓰는 돈(규모 효과)",
    "경영비_자본비율": "재산 대비 투입 비율", "임업외소득": "임업 말고 버는 돈",
    "임업외소득_비중": "임업 밖 소득 비중", "기초_자본(순재산)": "가진 재산",
    "ha당_자본": "면적당 재산", "연초보유": "연초 보유 현금",
    "업종별": "작목", "지역별": "지역", "임지규모별": "임지 규모",
    "임지규모_ha": "임지 면적", "전/겸업별": "전업 / 겸업",
    "연령별": "경영주 연세", "경영주_연령": "경영주 연세",
    "가구원수별": "가족 수", "가구원수_명": "가족 수",
    "ha당_가용노동력": "면적당 일손", "지역x업종": "지역과 작목 조합",
    "조사연도": "기준 연도",
}

# 같은 뿌리에서 파생된 변수들은 하나로 묶어야 임가가 읽을 수 있습니다.
# '경영비'와 'log 경영비'가 따로 나오면 같은 이야기를 두 번 하는 셈입니다.
FEATURE_GROUP = {
    "임업경영비": "경영비", "log_임업경영비": "경영비", "ha당_경영비": "경영비",
    "log_ha당_경영비": "경영비", "경영비_자본비율": "경영비",
    "업종별": "작목", "지역x업종": "작목",
    "지역별": "지역",
    "임지규모별": "임지 규모", "임지규모_ha": "임지 규모", "ha당_자본": "임지 규모",
    "ha당_가용노동력": "일손", "가구원수별": "일손", "가구원수_명": "일손",
    "연령별": "경영주 연세", "경영주_연령": "경영주 연세",
    "임업외소득": "임업 밖 소득", "임업외소득_비중": "임업 밖 소득",
    "기초_자본(순재산)": "재산", "연초보유": "재산",
    "전/겸업별": "전업 여부", "조사연도": "기준 연도",
}

GROUP_HINT = {
    "경영비": "한 해에 쓰는 돈의 규모와 재산 대비 비율입니다. 임가가 가장 직접 조절할 수 있는 항목입니다.",
    "작목": "무엇을 기르는지입니다. 바꾸려면 여러 해가 걸립니다.",
    "지역": "산이 있는 지역입니다. 기후와 유통 여건이 함께 반영됩니다.",
    "임지 규모": "산의 크기와 면적당 자본입니다.",
    "일손": "가족 수와 면적당 투입할 수 있는 일손입니다.",
    "경영주 연세": "경영주 연령대입니다.",
    "임업 밖 소득": "임업 외 소득과 그 비중입니다.",
    "재산": "보유 자산과 연초 현금입니다.",
    "전업 여부": "임업에 전념하는지 겸업인지입니다.",
    "기준 연도": "어느 해 기준으로 계산했는지입니다.",
}


# ---------------------------------------------------------------------------
# ① 개인화 설명 — 왜 이 숫자인가
# ---------------------------------------------------------------------------
def explain(booster: xgb.Booster, X: pd.DataFrame, features: list[str],
            transform: str = "none") -> dict:
    """TreeSHAP으로 예측 하나를 항목별로 분해합니다.

    기여도 합 + 기준값 = 예측값이 정확히 성립하므로(가법 분해),
    "이만큼은 무엇 때문"이라고 나눠 말할 수 있습니다.
    """
    d = xgb.DMatrix(X, enable_categorical=True)
    contrib = booster.predict(d, pred_contribs=True)[0]
    base = float(contrib[-1])
    parts = contrib[:-1]

    # 파생 변수를 뿌리별로 합칩니다
    grouped: dict[str, float] = {}
    for f, v in zip(features, parts):
        g = FEATURE_GROUP.get(f, FEATURE_LABEL.get(f, f))
        grouped[g] = grouped.get(g, 0.0) + float(v)

    rows = [{"항목": k, "기여": round(v, 2), "설명": GROUP_HINT.get(k, "")}
            for k, v in sorted(grouped.items(), key=lambda kv: -abs(kv[1]))]
    total = base + float(parts.sum())

    return {
        "기준값": round(base, 2),
        "예측값": round(total, 2),
        "항목별": rows,
        "올린_항목": [r for r in rows if r["기여"] > 0][:4],
        "내린_항목": [r for r in rows if r["기여"] < 0][:4],
        "설명": "기준값은 전국 임가의 평균 수준이고, 각 항목이 그 위아래로 얼마나 "
                "끌어올리거나 끌어내렸는지를 나타냅니다. 모두 더하면 예측값이 됩니다.",
    }


# ---------------------------------------------------------------------------
# ② 반사실 처방 — 무엇을 얼마나 바꿔야 하나
# ---------------------------------------------------------------------------
def prescribe(predict_fn, vals: dict, target: float, codebook: dict,
              max_changes: int = 2, top_k: int = 5) -> dict:
    """목표 수익률에 닿는 조합을 후보 격자에서 찾습니다.

    바꿀 수 있는 변수만 후보로 두고, 변경 개수가 적고 변화 폭이 작은 순으로
    고릅니다. 한 번에 세 가지를 바꾸라는 처방은 실행되지 않기 때문입니다.
    """
    base_cost = float(vals.get("임업경영비") or 0)
    current = predict_fn(vals)

    # 후보 값 목록
    options: dict[str, list] = {}
    for key, spec in ACTIONABLE.items():
        if spec["type"] == "num":
            options[key] = [round(base_cost * m, -4) for m in spec["grid"] if base_cost * m > 0]
        else:
            codes = sorted(int(c) for c in codebook.get(key, {}))
            options[key] = codes

    keys = list(options)
    found, fallback = [], []
    # 변경 개수를 1개부터 늘려가며 탐색합니다
    for n in range(1, max_changes + 1):
        for combo in _combinations(keys, n):
            for picks in product(*[options[k] for k in combo]):
                if all(picks[i] == vals[combo[i]] for i in range(n)):
                    continue
                cand = dict(vals)
                for k, v in zip(combo, picks):
                    cand[k] = v
                roi = predict_fn(cand)
                rec = {
                    "변경": [_describe(k, vals[k], v, codebook, base_cost)
                             for k, v in zip(combo, picks)],
                    "변경수": n,
                    "예측": round(roi, 1),
                    "개선": round(roi - current, 1),
                    "노력": _effort(combo, picks, vals, base_cost),
                    "기간": max((ACTIONABLE[k].get("기간", "올해") for k in combo),
                              key=lambda x: {"올해": 0, "중기": 1, "장기": 2}[x]),
                }
                (found if roi >= target else fallback).append(rec)
        if found:
            break   # 더 적은 변경으로 되면 굳이 여러 개를 바꿀 이유가 없습니다

    ok = bool(found)
    if ok:
        # 당장 할 수 있는 것부터 보여줍니다
        order = {"올해": 0, "중기": 1, "장기": 2}
        found.sort(key=lambda r: (order[r["기간"]], r["변경수"], r["노력"], -r["개선"]))
    else:
        # 목표에 못 미쳐도 손 놓고 있을 수는 없습니다. 개선폭이 큰 순으로 보여줍니다.
        order = {"올해": 0, "중기": 1, "장기": 2}
        fallback.sort(key=lambda r: (order[r["기간"]], -r["개선"], r["변경수"]))
        found = [r for r in fallback if r["개선"] > 0]

    return {
        "현재": round(current, 1),
        "목표": round(target, 1),
        "달성가능": ok,
        "처방": found[:top_k],
        "안내": ("목표에 닿는 조합을 찾았습니다." if ok else
                "지금 조건에서는 목표에 닿는 조합이 없어, 개선폭이 가장 큰 방향을 대신 보여드립니다."),
        "주의": "모델이 학습한 범위 안에서 조건을 바꿔 본 결과입니다. 작목 전환은 "
                "수확까지 여러 해가 걸리고 기술도 달라, 바로 실행할 수 있는 처방이 "
                "아니라 검토할 방향으로 봐 주세요.",
    }


def _combinations(items, n):
    if n == 1:
        return [(i,) for i in items]
    out = []
    for i in range(len(items)):
        for rest in _combinations(items[i + 1:], n - 1):
            out.append((items[i],) + rest)
    return out


def _josa(word: str, with_batchim: str, without: str) -> str:
    """한글 받침 유무에 따라 조사를 고릅니다. '임지 규모을'처럼 어긋나지 않게."""
    w = str(word).rstrip()
    if not w:
        return without
    ch = w[-1]
    if not ("가" <= ch <= "힣"):
        return without
    return with_batchim if (ord(ch) - 0xAC00) % 28 else without


def _describe(key, old, new, codebook, base_cost):
    label = ACTIONABLE[key]["label"]
    eul = _josa(label, "을", "를")
    if ACTIONABLE[key]["type"] == "num":
        return {
            "항목": label, "전": float(old), "후": float(new), "형식": "money",
            "문장": f"{label}{eul} {_won(old)}에서 {_won(new)}으로 "
                    f"{'늘리면' if new > old else '줄이면'}",
        }
    cb = codebook.get(key, {})
    a, b = cb.get(int(old), str(old)), cb.get(int(new), str(new))
    return {
        "항목": label, "전": a, "후": b, "형식": "category",
        "문장": f"{label}{eul} {a}에서 {b}{_josa(b, '으로', '로')} 바꾸면",
    }


def _won(v):
    v = float(v)
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.2f}억원"
    if abs(v) >= 1e4:
        return f"{v / 1e4:,.0f}만원"
    return f"{v:,.0f}원"


def _effort(combo, picks, vals, base_cost):
    """변화 폭을 0~1로 환산합니다. 작을수록 실행하기 쉬운 처방입니다."""
    e = 0.0
    for k, v in zip(combo, picks):
        if ACTIONABLE[k]["type"] == "num":
            e += abs(float(v) - float(vals[k])) / max(base_cost, 1)
        else:
            # 작목 전환은 규모 조정보다 훨씬 큰 결심이 필요합니다
            e += 1.6 if k == "업종별" else 0.5
    return round(e, 3)


# ---------------------------------------------------------------------------
# ③ 유사 임가 탐색 — 누구를 보면 되나
# ---------------------------------------------------------------------------
NEIGHBOR_KEYS = ["지역별", "업종별", "임지규모별", "전/겸업별", "연령별", "가구원수별"]
NEIGHBOR_NUM = ["임업경영비", "기초_자본(순재산)", "임업외소득"]


def neighbors(df: pd.DataFrame, vals: dict, k: int = 40, top: int = 8) -> dict:
    """조건이 비슷한 임가를 찾아, 그중 잘 버는 쪽이 무엇이 다른지 보여줍니다.

    범주형은 일치 여부로, 수치형은 로그 스케일 상대거리로 잽니다. 금액은
    자릿수가 커서 그대로 빼면 큰 값 하나가 거리를 지배합니다.
    """
    if df is None or df.empty:
        return {}
    d = df.copy()

    dist = np.zeros(len(d))
    for c in NEIGHBOR_KEYS:
        if c in d.columns:
            w = 2.0 if c in ("업종별", "지역별") else 1.0
            dist += w * (d[c].astype(float) != float(vals[c])).to_numpy()
    for c in NEIGHBOR_NUM:
        if c in d.columns:
            a = np.log1p(pd.to_numeric(d[c], errors="coerce").clip(lower=0).to_numpy())
            b = np.log1p(max(float(vals.get(c) or 0), 0))
            s = np.nanstd(a) or 1.0
            dist += np.abs(a - b) / s

    d["_거리"] = dist
    near = d.nsmallest(k, "_거리")
    if near.empty:
        return {}

    better = near[near["ROI"] > near["ROI"].median()]
    worse = near[near["ROI"] <= near["ROI"].median()]

    def med(g, c):
        return float(pd.to_numeric(g[c], errors="coerce").median()) if c in g.columns else None

    diffs = []
    for c, label in [("임업경영비", "한 해 쓰는 돈"), ("ha당_경영비", "면적당 쓰는 돈"),
                     ("경영비_자본비율", "재산 대비 투입 비율"),
                     ("임업외소득", "임업 말고 버는 돈"), ("ha당_가용노동력", "면적당 일손")]:
        hi, lo = med(better, c), med(worse, c)
        if hi is None or lo is None or not np.isfinite(hi) or not np.isfinite(lo) or lo == 0:
            continue
        diffs.append({
            "항목": label, "잘버는쪽": round(hi, 3), "그외": round(lo, 3),
            "차이_pct": round((hi / lo - 1) * 100, 1),
        })
    diffs.sort(key=lambda r: -abs(r["차이_pct"]))

    return {
        "표본": int(len(near)),
        "이웃_ROI중앙값": round(float(near["ROI"].median()), 1),
        "잘버는쪽_ROI중앙값": round(float(better["ROI"].median()), 1) if len(better) else None,
        "상위_ROI": [round(float(v), 1) for v in near.nlargest(top, "ROI")["ROI"]],
        "차이": diffs[:4],
        "설명": "지역·작목·규모·전겸업이 비슷한 임가를 찾아, 그중 수익이 높은 쪽과 "
                "낮은 쪽이 무엇에서 갈리는지 비교한 결과입니다. 인과가 아니라 경향입니다.",
    }


# ── 집계값으로 하는 유사 임가 비교 ────────────────────────────────────────
NEIGHBOR_LABEL = {
    "임업경영비": "한 해 쓰는 돈",
    "ha당_경영비": "면적당 쓰는 돈",
    "경영비_자본비율": "재산 대비 투입 비율",
    "임업외소득": "임업 말고 버는 돈",
    "ha당_가용노동력": "면적당 일손",
}
CELL_WEIGHT = {"업종별": 3.0, "지역별": 2.0, "임지규모별": 1.0, "전/겸업별": 1.0}


def neighbors_from_cells(stats: dict, vals: dict, top: int = 8) -> dict:
    """비슷한 조건 집단을 찾아 그 안에서 무엇이 갈리는지 보여줍니다.

    예전에는 개별 임가 4,438행에서 가까운 40곳을 골랐습니다. 그러려면 행자료를
    배포본에 실어야 하는데, 임가 단위 자료를 공개 저장소에 두는 셈이라
    미리 집단별로 묶어 둔 값을 쓰도록 바꿨습니다.

    집단은 지역·작목·규모·전겸업이 같은 임가들이고, 5곳이 못 되는 집단은
    애초에 만들어지지 않습니다. 딱 맞는 집단이 없으면 조건이 덜 어긋나는 쪽부터
    찾아 갑니다. 작목이 다른 것은 지역이 다른 것보다 크게 칩니다.
    """
    keys = stats.get("cell_keys") or ["지역별", "업종별", "임지규모별", "전/겸업별"]
    cells = stats.get("cells") or []
    if not cells:
        return {}

    def gap(cell):
        d = 0.0
        for i, k in enumerate(keys):
            want, got = vals.get(k), cell["key"][i]
            if want is None or int(want) != int(got):
                d += CELL_WEIGHT.get(k, 1.0)
        return d

    best = min(cells, key=lambda c: (gap(c), -c["n"]))
    d = gap(best)

    diffs = []
    for c, label in NEIGHBOR_LABEL.items():
        hi, lo = best["잘버는쪽"].get(c), best["그외"].get(c)
        if hi is None or lo is None or not lo:
            continue
        diffs.append({"항목": label, "잘버는쪽": hi, "그외": lo,
                      "차이_pct": round((hi / lo - 1) * 100, 1)})
    diffs.sort(key=lambda r: -abs(r["차이_pct"]))

    qs = best.get("ROI분위수") or []
    상위 = [round(v, 1) for v in qs[-top:][::-1]] if qs else []

    맞춤 = "지역·작목·규모·전겸업이 모두 같은" if d == 0 else "조건이 가장 가까운"
    return {
        "표본": best["n"],
        "이웃_ROI중앙값": best["ROI중앙값"],
        "잘버는쪽_ROI중앙값": best.get("ROI상위중앙값"),
        "상위_ROI": 상위,
        "차이": diffs[:4],
        "설명": (f"{맞춤} 임가 {best['n']}곳을 묶어, 그중 수익이 높은 쪽과 낮은 쪽이 "
                "무엇에서 갈리는지 비교한 결과입니다. 인과가 아니라 경향입니다."),
        "정확도": "같은 조건" if d == 0 else "가까운 조건",
    }
