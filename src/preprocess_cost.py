"""
Phase 1-B — 임산물생산비조사 마이크로데이터 전처리 파이프라인

출처: 통계청 MDIS / 산림청 국가승인통계 「임산물생산비조사」
      대추(2020~2024) · 떫은감(2020~2024) · 밤(2020~2024) · 표고(노지)(2018~2022)

임가경제조사(총괄)가 '임가 단위 종합 수익성'을 다룬다면, 본 조사는
'품목 단위 단위면적당 투입-산출 구조'를 담고 있어 훨씬 정밀한 경영 진단이 가능하다.
  · 비목별 생산비 (비료·농약·노동·감가상각·위탁영농 등)
  · 작업 공정별 노동시간 (전정·시비·병해충방제·수확·선별포장 등 20여 공정)
  · 수령, 재배면적, 재배본수 등 임분(林分) 특성

산출: data/processed_cost_data.parquet
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SRC_DIR = os.path.join(DATA_DIR, "임산물생산비조사")
OUT_PARQUET = os.path.join(DATA_DIR, "processed_cost_data.parquet")
META_JSON = os.path.join(DATA_DIR, "processed_cost_meta.json")

ENCODINGS = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
MISSING_CODES = {-9, -8, -7, 999999999, -999999999}

# 파일설계서 '코드정보' 기준 (2024년 밤 배포본). 4개 품목 공통 체계.
CODEBOOK: dict[str, dict[int, str]] = {
    "연령별": {1: "50세 미만", 2: "50대", 3: "60대", 4: "70대 이상"},
    "지역별": {
        31: "경기", 32: "강원", 33: "충북", 34: "충남", 35: "전북", 36: "전남",
        37: "경북", 38: "경남", 39: "제주", 49: "특·광역시", 99: "기타",
    },
    "규모별": {1: "1~2ha 미만", 2: "2~3ha 미만", 3: "3~5ha 미만", 4: "5ha 이상"},
    "경영수준별": {1: "선도임가", 2: "이외임가"},
    "전/겸업별": {1: "전업", 2: "겸업"},
}

CATEGORICALS = ["품목", "연령별", "지역별", "규모별", "경영수준별", "전/겸업별"]

# 「경영수준별」 코드 체계가 연도별로 다르게 배포되어 있다.
#   2020~2022년 : 5 = 선도임가, 6 = 이외임가
#   2023~2024년 : 1 = 선도임가, 2 = 이외임가
# 두 체계의 구성비가 약 20:80으로 동일하며 파일설계서(2024년분)는 1/2만 문서화한다.
# 조화하지 않으면 동일 개념이 4개 범주로 쪼개져 연도 코호트로 오분할된다.
LEVEL_HARMONIZE = {5: 1, 6: 2}

# 목표변수 정의식에 포함되거나 사후(ex-post) 실적인 항목 → 설명변수에서 전면 제외.
#   ROI = 소득 / 경영비,  소득 = 총수입(총평가액) - 경영비
LEAKY_PATTERNS = [
    r"^소득$", r"^순수익$", r"평가액", r"수확량", r"생산량",
    r"^생산비합계", r"^직접생산비$", r"^간접생산비$", r"^내급비$",
    r"^타용도소비량$", r"^판매량", r"^총수입",
]
# 시비량(무기질/유기질 수량)은 투입량이므로 산출 '수량'과 구분해 유지한다
KEEP_DESPITE_PATTERN = re.compile(r"^(무기질|유기질)_.*_수량_단위당$")

TARGET = "ROI"


# ---------------------------------------------------------------------------
def normalize(col: str) -> str:
    """연도·품목별 표기 흔들림을 흡수하는 컬럼명 정규화."""
    c = str(col).strip().replace("▣", "").strip()
    # '무기질비료_질소질_지출액1' / '..._지출액2' → '..._지출액'
    c = re.sub(r"(지출액|수량|시간|면적)[0-9]$", r"\1", c)
    # 품목마다 단위 분모가 다르다: 밤·대추·떫은감은 ha당, 표고(노지)는 만본당
    c = re.sub(r"_(ha당|만본당)$", "_단위당", c)
    c = c.replace(" ", "")
    c = re.sub(r"^규모별\(통계표기준\)$", "규모별", c)
    return c


def is_leaky(col: str) -> bool:
    if KEEP_DESPITE_PATTERN.match(col):
        return False
    return any(re.search(p, col) for p in LEAKY_PATTERNS)


def read_csv_any(path: str) -> pd.DataFrame:
    last: Exception | None = None
    for enc in ENCODINGS:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = [normalize(c) for c in df.columns]
            return df.loc[:, ~df.columns.duplicated()]
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{path} 읽기 실패: {last}")


ITEM_RE = re.compile(r"^(\d{4})_(.+?)_\d{8}_\d+\.csv$")


def load_all() -> tuple[pd.DataFrame, dict]:
    paths = sorted(glob.glob(os.path.join(SRC_DIR, "**", "*.csv"), recursive=True))
    if not paths:
        raise FileNotFoundError(f"{SRC_DIR} 에 임산물생산비조사 CSV가 없습니다.")

    frames, manifest = [], []
    for p in paths:
        m = ITEM_RE.match(os.path.basename(p))
        if not m:
            continue
        year, item = int(m.group(1)), m.group(2).replace("_", " ")
        df = read_csv_any(p)
        df["품목"] = item
        df["조사연도"] = year
        frames.append(df)
        manifest.append({"품목": item, "연도": year, "행": len(df), "열": df.shape[1]})
        print(f"[load] {item:8s} {year}  rows={len(df):4d}  cols={df.shape[1]}")

    df = pd.concat(frames, ignore_index=True, sort=False)
    return df, {"files": manifest}


# ---------------------------------------------------------------------------
def iqr_mask(s: pd.Series, k: float = 1.5) -> pd.Series:
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    return (s >= q1 - k * (q3 - q1)) & (s <= q3 + k * (q3 - q1))


def build(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report: dict = {"raw_rows": int(len(df)), "raw_cols": int(df.shape[1])}

    # 수치화 및 결측코드 처리
    for c in df.columns:
        if c in ("품목",):
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c].isin(MISSING_CODES), c] = np.nan

    # --- 목표변수 ---------------------------------------------------------
    df = df.dropna(subset=["소득", "경영비"])
    report["after_dropna_core"] = int(len(df))
    valid = df["경영비"] > 0
    report["dropped_zero_cost"] = int((~valid).sum())
    df = df[valid].copy()

    df[TARGET] = df["소득"] / df["경영비"] * 100.0

    # --- IQR 이상치 제거 (품목별로 적용: 단위 분모가 달라 스케일이 다름) ----
    before = len(df)
    keep = pd.Series(False, index=df.index)
    for item, g in df.groupby("품목", observed=True):
        keep.loc[g.index] = iqr_mask(g[TARGET], 1.5) & iqr_mask(g["경영비"].fillna(g["경영비"].median()), 3.0)
    df = df[keep].copy()
    report["outliers_removed"] = int(before - len(df))
    report["rows_final"] = int(len(df))

    # --- 컬럼 선별 --------------------------------------------------------
    exclude = {TARGET, "가중치", "조사연도"} | set(CATEGORICALS)
    numeric_all = [
        c for c in df.columns
        if c not in exclude and not is_leaky(c) and pd.api.types.is_numeric_dtype(df[c])
    ]
    # 전량 결측이거나 상수인 열 제거
    numeric = [c for c in numeric_all if df[c].notna().sum() >= 200 and df[c].nunique(dropna=True) > 1]
    report["leaky_dropped"] = sorted(set(df.columns) - set(numeric) - exclude)
    report["sparse_dropped"] = sorted(set(numeric_all) - set(numeric))

    # --- 범주형 라벨 ------------------------------------------------------
    for c in CATEGORICALS:
        if c == "품목":
            continue
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        if c == "경영수준별":
            before = df[c].isin(LEVEL_HARMONIZE).sum()
            df[c] = df[c].replace(LEVEL_HARMONIZE)
            report["level_code_harmonized"] = int(before)
        lab = CODEBOOK.get(c, {})
        df[c + "_라벨"] = df[c].map(lambda v, l=lab: l.get(int(v)) if pd.notna(v) else None)

    # --- 파생 피처 --------------------------------------------------------
    df = add_derived_cost_features(df)
    derived = [c for c in DERIVED if c in df.columns]

    keep_cols = (
        ["품목", TARGET, "소득", "경영비", "조사연도", "가중치"]
        + [c for c in CATEGORICALS if c != "품목"]
        + [c + "_라벨" for c in CATEGORICALS if c != "품목"]
        + numeric + derived
    )
    keep_cols = [c for c in dict.fromkeys(keep_cols) if c in df.columns]
    out = df[keep_cols].reset_index(drop=True)

    report["n_numeric_features"] = len(numeric)
    report["n_derived_features"] = len(derived)
    report["items"] = out["품목"].value_counts().to_dict()
    report["roi_by_item"] = out.groupby("품목", observed=True)[TARGET].median().round(2).to_dict()
    return out, report


DERIVED = [
    "자가노동비율", "고용노동시간비율", "노동비_비중", "비료비_비중", "농약비_비중",
    "감가상각비_비중", "위탁영농비_비중", "수확선별_노동비중", "재배관리_노동비중",
    "log_경영비", "노동시간당_경영비", "차용지_비율",
]


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def add_derived_cost_features(df: pd.DataFrame) -> pd.DataFrame:
    """비목 구성비·노동 배분 등 '경영 구조'를 나타내는 파생 피처.

    학습(preprocess_cost)과 추론(app.py)이 동일 변환을 쓰도록 이 함수만 사용한다.
    """
    df = df.copy()
    g = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)  # noqa: E731

    cost = g("경영비")
    labor_cost = g("노동비_단위당")
    own_labor = g("자가노동비_단위당")
    hire_labor = g("고용노동비_단위당")
    hours_total = g("총노동시간_합계_단위당")
    hours_hire = (g("총노동시간_보통고용_남_단위당").fillna(0)
                  + g("총노동시간_보통고용_여_단위당").fillna(0)
                  + g("총노동시간_특수고용_단위당").fillna(0))

    df["자가노동비율"] = _safe_div(own_labor, own_labor.fillna(0) + hire_labor.fillna(0))
    df["고용노동시간비율"] = _safe_div(hours_hire, hours_total)
    df["노동비_비중"] = _safe_div(labor_cost, cost)
    df["비료비_비중"] = _safe_div(g("비료비_단위당"), cost)
    df["농약비_비중"] = _safe_div(g("농약비_단위당"), cost)
    df["감가상각비_비중"] = _safe_div(g("감가상각비_단위당"), cost)
    df["위탁영농비_비중"] = _safe_div(g("위탁영농비_단위당"), cost)

    harvest = g("수확_시간_단위당").fillna(0) + g("선별및포장_시간_단위당").fillna(0) + g("출하_시간_단위당").fillna(0)
    manage = (g("전정_시간_단위당").fillna(0) + g("시비_시간_단위당").fillna(0)
              + g("병해충방제_시간_단위당").fillna(0) + g("제초_시간_단위당").fillna(0))
    df["수확선별_노동비중"] = _safe_div(harvest, hours_total)
    df["재배관리_노동비중"] = _safe_div(manage, hours_total)

    df["log_경영비"] = np.log1p(cost.clip(lower=0))
    df["노동시간당_경영비"] = _safe_div(cost, hours_total)
    df["차용지_비율"] = _safe_div(g("재배면적_차용지_계"), g("재배면적_합계_계"))
    return df


def feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    cats = [c for c in CATEGORICALS if c in df.columns]
    drop = set(cats) | {TARGET, "소득", "가중치"} | {c + "_라벨" for c in CATEGORICALS}
    nums = [c for c in df.columns if c not in drop and pd.api.types.is_numeric_dtype(df[c])]
    return cats, nums


def main() -> None:
    raw, load_meta = load_all()
    df, report = build(raw)
    report.update(load_meta)

    df.to_parquet(OUT_PARQUET, index=False)
    cats, nums = feature_columns(df)
    report["features"] = {"categorical": cats, "n_numeric": len(nums)}
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n최종 {report['rows_final']:,}행 × 피처 {len(cats) + len(nums)}개")
    print("품목별:", report["items"])
    print("품목별 ROI 중앙값:", report["roi_by_item"])
    print(f"[saved] {OUT_PARQUET}")


if __name__ == "__main__":
    main()
