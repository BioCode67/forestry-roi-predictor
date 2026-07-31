"""
Phase 1 — 임가경제조사 총괄 마이크로데이터 전처리 파이프라인

출처: 통계청 MDIS / 산림청 국가승인통계 「임가경제조사」 총괄(제공) 원데이터 2019~2023
산출: data/processed_forestry_data.parquet
"""
from __future__ import annotations

import glob
import json
import os
import re
import zipfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
OUT_PARQUET = os.path.join(DATA_DIR, "processed_forestry_data.parquet")
OUT_CSV = os.path.join(DATA_DIR, "processed_forestry_data.csv")
META_JSON = os.path.join(DATA_DIR, "processed_meta.json")

# MDIS 마이크로데이터는 CP949 고정폭/구분자 혼용 배포 → 인코딩·구분자 후보를 순차 시도
ENCODINGS = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
DELIMITERS = [",", "|", "^", "\t", ";"]

# MDIS 수치형 결측 코드 (무응답/해당없음)
MISSING_CODES = {-9, -8, -7, -1, 999999999, -999999999}

# ---------------------------------------------------------------------------
# 1. 파일설계서(코드북) 파싱 → 코드 → 한글 라벨 매핑 자동 생성
# ---------------------------------------------------------------------------

# 파일설계서에 없는 연도(2019~2022)까지 공통 적용되는 코드 체계.
# 코드북 파싱에 실패할 경우를 대비한 폴백 사전이기도 하다.
FALLBACK_CODEBOOK = {
    "연령별": {1: "39세 이하", 2: "40대", 3: "50대", 4: "60대", 5: "70세 이상"},
    "지역별": {
        31: "경기", 32: "강원", 33: "충북", 34: "충남", 35: "전북",
        36: "전남", 37: "경북", 38: "경남", 40: "광역시",
    },
    "전/겸업별": {1: "전업임가", 2: "임업주업", 3: "임업부업"},
    "업종별": {
        1: "육림/목재생산업", 2: "채취업", 3: "밤재배업", 4: "떫은감재배업",
        5: "수실류재배업", 6: "버섯재배업", 7: "조경재업", 8: "기타재배업",
    },
    "가구원수별": {1: "2명 이하", 2: "3명", 3: "4명", 4: "5명", 5: "6명 이상"},
    "임지규모별": {
        1: "1ha 미만", 2: "1-5ha 미만", 3: "5-10ha 미만",
        4: "10-20ha 미만", 5: "20ha 이상",
    },
}


def parse_codebook(path: str | None = None) -> dict[str, dict[int, str]]:
    """파일설계서 xlsx의 '코드정보' 시트를 파싱해 {항목명: {코드: 의미}} 반환."""
    if path is None:
        cands = glob.glob(os.path.join(DATA_DIR, "**", "*파일설계서*.xlsx"), recursive=True)
        if not cands:
            return dict(FALLBACK_CODEBOOK)
        path = cands[0]

    try:
        raw = pd.read_excel(path, sheet_name="코드정보", header=None)
    except Exception:
        return dict(FALLBACK_CODEBOOK)

    codebook: dict[str, dict[int, str]] = {}
    current: str | None = None
    for _, row in raw.iterrows():
        vals = [v for v in row.tolist()]
        # 레이아웃: [코드번호, 항목명, 코드, 코드의미, 특이사항]
        item = vals[1] if len(vals) > 1 else None
        code = vals[2] if len(vals) > 2 else None
        meaning = vals[3] if len(vals) > 3 else None

        if isinstance(item, str) and item.strip() and item.strip() != "항목명":
            current = item.strip()
            codebook.setdefault(current, {})
        # 항목명이 비어 있는 행은 직전 항목의 연속 코드 행 (병합 셀)
        if current and pd.notna(code) and pd.notna(meaning):
            try:
                codebook[current][int(code)] = str(meaning).strip()
            except (TypeError, ValueError):
                continue
        elif current and pd.notna(item) and pd.notna(code) and not isinstance(meaning, str):
            # 병합 해제 시 [코드, 의미]가 한 칸씩 당겨진 경우
            try:
                codebook[current][int(item)] = str(code).strip()
            except (TypeError, ValueError):
                continue

    # 파싱 결과가 부실하면 폴백으로 보강
    for k, v in FALLBACK_CODEBOOK.items():
        if len(codebook.get(k, {})) < len(v):
            codebook[k] = v
    return codebook


# ---------------------------------------------------------------------------
# 2. 연도별 컬럼명 표준화
# ---------------------------------------------------------------------------

# 2021년 파일은 'FMI_임업소득'처럼 영문 변수코드 접두사가 붙어 배포됨
PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*_(?=[가-힣])")

COLUMN_ALIASES = {
    "임가_번호": "임가번호",
    "임외소득": "임업외소득",        # 2019~2020 표기
    "재산적수입": "재산적_수입",
    "재산적지출": "재산적_지출",
    "경지면적_총합": "경지면적_총합",
    "자본": "기초_자본(순재산)",       # 2020 표기
    "연초보유현금": "연초보유",
    "연말보유현금": "연말보유",
}


def normalize_columns(cols) -> list[str]:
    out = []
    for c in cols:
        c = str(c).strip().replace(" ", "")
        c = PREFIX_RE.sub("", c)
        c = COLUMN_ALIASES.get(c, c)
        out.append(c)
    return out


def read_microdata_csv(path: str) -> pd.DataFrame:
    """인코딩/구분자를 자동 탐지해 MDIS CSV를 읽는다."""
    last_err: Exception | None = None
    for enc in ENCODINGS:
        for sep in DELIMITERS:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, engine="python")
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
            if df.shape[1] >= 5:  # 구분자가 맞으면 컬럼이 제대로 쪼개짐
                df.columns = normalize_columns(df.columns)
                return df
    raise RuntimeError(f"{path} 읽기 실패: {last_err}")


def extract_zips() -> None:
    """data/ 하위 ZIP을 같은 위치에 해제 (MDIS 배포본 대응)."""
    for zp in glob.glob(os.path.join(DATA_DIR, "**", "*.zip"), recursive=True):
        target = os.path.join(os.path.dirname(zp), os.path.splitext(os.path.basename(zp))[0])
        if os.path.isdir(target):
            continue
        os.makedirs(target, exist_ok=True)
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                # CP949 파일명 깨짐 복구
                try:
                    fixed = name.encode("cp437").decode("cp949")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    fixed = name
                dest = os.path.join(target, fixed)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if not name.endswith("/"):
                    with z.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
        print(f"[unzip] {zp} -> {target}")


# ---------------------------------------------------------------------------
# 3. 적재 · 결합
# ---------------------------------------------------------------------------

YEAR_RE = re.compile(r"(19|20)\d{2}")


def load_all() -> pd.DataFrame:
    extract_zips()
    # 임가경제조사 '총괄' 배포본만 사용한다.
    # (data/ 아래에는 임산물생산비조사 등 다른 조사 배포본도 함께 놓이므로 반드시 한정한다)
    paths = [
        p for p in glob.glob(os.path.join(DATA_DIR, "**", "*.csv"), recursive=True)
        if "총괄" in p and "processed" not in os.path.basename(p)
    ]
    if not paths:
        raise FileNotFoundError(f"{DATA_DIR} 에서 마이크로데이터 CSV를 찾지 못했습니다.")

    frames = []
    for p in sorted(paths):
        m = YEAR_RE.search(os.path.basename(p))
        if not m:
            continue
        df = read_microdata_csv(p)
        df["조사연도"] = int(m.group(0))
        frames.append(df)
        print(f"[load] {os.path.basename(p)}  rows={len(df):,}  cols={df.shape[1]}")

    df = pd.concat(frames, ignore_index=True, sort=False)
    return df


# ---------------------------------------------------------------------------
# 4. 정제 · 파생변수 · 이상치 제거
# ---------------------------------------------------------------------------

CATEGORICALS = ["연령별", "지역별", "전/겸업별", "업종별", "가구원수별", "임지규모별"]

# 목표변수 정의식에 직접 포함되어 정보누출(leakage)을 일으키는 컬럼.
#   임업소득 = 임업총수입 - 임업경영비,  ROI = 임업소득 / 임업경영비
#   임가소득·경상소득·임가순소득·임가처분가능소득·임가경제잉여는 모두 임업소득을 포함한 합계항목.
LEAKY = [
    "임업총수입", "임업소득", "임가소득", "경상소득",
    "임가순소득", "임가처분가능소득", "임가경제잉여",
]

# 임가가 영농계획 시점에 스스로 제시할 수 있는 사전(ex-ante) 변수만 설명변수로 사용
NUMERIC_FEATURES = [
    "임업경영비",        # 계획 경영비 (ROI 분모이나 분자(총수입)는 미지 → 누출 아님)
    "임업외소득",
    "기초_자본(순재산)",  # 기초 시점 자산 → 사후 정보 아님
    "연초보유",
    "조사연도",
]

DERIVED_FEATURES = [
    "임지규모_ha", "가구원수_명", "경영주_연령",
    "log_임업경영비", "경영비_자본비율",
    "ha당_경영비", "log_ha당_경영비", "ha당_가용노동력", "ha당_자본",
    "임업외소득_비중", "지역x업종",
]

# 대시보드 입력 폼에서 노출할 최소 입력 세트
FORM_FIELDS = CATEGORICALS + ["임업경영비", "임업외소득", "기초_자본(순재산)", "연초보유"]


def clean_numeric(df: pd.DataFrame) -> pd.DataFrame:
    num_cols = [c for c in df.columns if c not in CATEGORICALS + ["임가번호"]]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c].isin(MISSING_CODES), c] = np.nan
    return df


def iqr_filter(s: pd.Series, k: float = 1.5) -> pd.Series:
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return (s >= q1 - k * iqr) & (s <= q3 + k * iqr)


# 구간형 범주 → 대표값 (구간 중앙값 / 상한 없는 구간은 관행적 대표치)
HA_MIDPOINT = {1: 0.5, 2: 3.0, 3: 7.5, 4: 15.0, 5: 30.0}
MEMBERS_MIDPOINT = {1: 2.0, 2: 3.0, 3: 4.0, 4: 5.0, 5: 6.0}
AGE_MIDPOINT = {1: 35.0, 2: 45.0, 3: 55.0, 4: 65.0, 5: 75.0}


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """원시 항목으로부터 파생 피처를 생성한다.

    학습(preprocess)과 추론(app.py)이 동일한 변환을 쓰도록 이 함수 하나만 사용한다.
    """
    df = df.copy()
    df["임지규모_ha"] = df["임지규모별"].map(HA_MIDPOINT).astype("float64")
    df["가구원수_명"] = df["가구원수별"].map(MEMBERS_MIDPOINT).astype("float64")
    df["경영주_연령"] = df["연령별"].map(AGE_MIDPOINT).astype("float64")

    cost = df["임업경영비"].astype("float64")
    capital = df["기초_자본(순재산)"].astype("float64").replace(0, np.nan)
    offfarm = df["임업외소득"].astype("float64")

    df["log_임업경영비"] = np.log1p(cost.clip(lower=0))
    df["경영비_자본비율"] = cost / capital
    df["ha당_경영비"] = cost / df["임지규모_ha"]
    df["log_ha당_경영비"] = np.log1p(df["ha당_경영비"].clip(lower=0))
    df["ha당_가용노동력"] = df["가구원수_명"] / df["임지규모_ha"]
    df["ha당_자본"] = df["기초_자본(순재산)"].astype("float64") / df["임지규모_ha"]
    df["임업외소득_비중"] = offfarm / (offfarm.abs() + cost.abs()).replace(0, np.nan)
    df["지역x업종"] = (
        df["지역별"].astype("Float64") * 10 + df["업종별"].astype("Float64")
    ).astype("Float64")
    return df


def build(df: pd.DataFrame, codebook: dict) -> tuple[pd.DataFrame, dict]:
    report: dict = {"raw_rows": int(len(df))}
    df = clean_numeric(df)

    # --- 목표변수: 임가 ROI(%) = 임업소득 / 임업경영비 * 100 ---------------
    need = ["임업소득", "임업경영비", "임업총수입"]
    df = df.dropna(subset=need)
    report["after_dropna_core"] = int(len(df))

    # 임업 미영위(경영비 0 또는 총수입 0) 임가는 ROI 정의 불가 → 제외
    valid = (df["임업경영비"] > 0) & (df["임업총수입"] > 0)
    report["dropped_no_forestry_activity"] = int((~valid).sum())
    df = df[valid].copy()

    df["ROI"] = df["임업소득"] / df["임업경영비"] * 100.0
    # 참고 지표: 임업소득률(%) — 산림청 공표 지표와 직접 비교 가능
    df["임업소득률"] = df["임업소득"] / df["임업총수입"] * 100.0

    # --- IQR 이상치 제거 ---------------------------------------------------
    before = len(df)
    mask = iqr_filter(df["ROI"], k=1.5)
    for c in ["임업경영비", "임업외소득"]:
        if c in df.columns:
            mask &= iqr_filter(df[c].fillna(df[c].median()), k=3.0)
    df = df[mask].copy()
    report["outliers_removed"] = int(before - len(df))
    report["rows_final"] = int(len(df))
    report["roi_bounds"] = [float(df["ROI"].min()), float(df["ROI"].max())]

    # --- 범주형 라벨 -------------------------------------------------------
    for c in CATEGORICALS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        lab = codebook.get(c, {})
        df[c + "_라벨"] = df[c].map(lambda v, l=lab: l.get(int(v)) if pd.notna(v) else None)

    # --- 파생 피처 ---------------------------------------------------------
    df = add_derived_features(df)

    keep = (
        ["임가번호", "ROI", "임업소득률", "임업소득", "임업총수입", "가중치"]
        + CATEGORICALS
        + [c + "_라벨" for c in CATEGORICALS]
        + NUMERIC_FEATURES
        + DERIVED_FEATURES
    )
    keep = [c for c in dict.fromkeys(keep) if c in df.columns]
    return df[keep].reset_index(drop=True), report


def feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    cats = [c for c in CATEGORICALS if c in df.columns]
    nums = [c for c in NUMERIC_FEATURES + DERIVED_FEATURES if c in df.columns]
    return cats, nums


def main() -> None:
    codebook = parse_codebook()
    raw = load_all()
    df, report = build(raw, codebook)

    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    report["codebook_items"] = {k: len(v) for k, v in codebook.items()}
    report["leaky_excluded"] = LEAKY
    cats, nums = feature_columns(df)
    report["features"] = {"categorical": cats, "numeric": nums}
    with open(META_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[saved] {OUT_PARQUET}")


if __name__ == "__main__":
    main()
