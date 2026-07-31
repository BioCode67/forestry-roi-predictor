"""
Phase 2-H — 기상 자료를 임가 데이터에 결합

출처: 기상청 API 허브 「지상관측(ASOS) 일자료」 2019~2024, 전국 97개 지점

왜 붙이는가
-----------
Model A의 설명력이 낮은 이유를 "기상 등 관측되지 않은 요인" 이라고만 말해 왔다.
그 말이 맞는지 확인하려면 기상을 실제로 넣어 봐야 한다. 올라가면 성능 개선이고,
안 올라가면 "기상을 통제해도 설명되지 않는 부분이 크다"는 결론이라 어느 쪽이든
보고서에 쓸 근거가 된다.

결합 방식
---------
임가 데이터의 지역 단위는 시도이고 기상 관측은 지점 단위다. 지점을 시도로 묶어
연·시도 평균을 만든 뒤 (지역별, 조사연도) 키로 붙인다. 지점마다 고도가 크게
다르므로(대관령 772m) 산간 고지대 지점이 시도 평균을 끌어내리지 않도록
고도 600m 이상 지점은 제외한다.

산출: data/weather/weather_sido.csv
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W_DIR = os.path.join(ROOT, "data", "weather")
ANNUAL = os.path.join(W_DIR, "weather_annual.csv")
STATIONS = os.path.join(W_DIR, "stations.csv")
OUT_SIDO = os.path.join(W_DIR, "weather_sido.csv")

# 임가경제조사 '지역별' 코드
REGION_CODE = {
    "경기": 31, "강원": 32, "충북": 33, "충남": 34, "전북": 35,
    "전남": 36, "경북": 37, "경남": 38, "광역시": 40,
}

# 관측지점명 → 시도. 기상청 지점명은 시·군 단위라 소속 시도로 접는다.
STN_TO_SIDO = {
    # 경기·인천
    "동두천": "경기", "파주": "경기", "서울": "광역시", "인천": "광역시",
    "수원": "경기", "이천": "경기", "양평": "경기", "백령도": "광역시",
    "강화": "광역시", "김포": "경기",
    # 강원
    "속초": "강원", "북춘천": "강원", "철원": "강원", "대관령": "강원",
    "춘천": "강원", "북강릉": "강원", "강릉": "강원", "동해": "강원",
    "원주": "강원", "영월": "강원", "인제": "강원", "홍천": "강원",
    "태백": "강원", "정선군": "강원", "삼척": "강원", "양구": "강원",
    "고성": "강원", "양양": "강원", "화천": "강원", "평창": "강원",
    # 충북
    "충주": "충북", "청주": "충북", "서청주": "충북", "추풍령": "충북", "제천": "충북",
    "보은": "충북", "괴산": "충북", "진천": "충북", "음성": "충북", "증평": "충북",
    # 충남·대전·세종
    "서산": "충남", "천안": "충남", "홍성": "충남", "보령": "충남",
    "부여": "충남", "금산": "충남", "대전": "광역시", "세종": "충남",
    "아산": "충남", "태안": "충남", "청양": "충남", "예산": "충남",
    "당진": "충남", "논산": "충남", "계룡": "충남", "서천": "충남",
    # 전북
    "군산": "전북", "전주": "전북", "부안": "전북", "임실": "전북",
    "정읍": "전북", "남원": "전북", "장수": "전북", "고창": "전북",
    "고창군": "전북", "순창군": "전북", "김제": "전북", "익산": "전북",
    "완주": "전북", "진안": "전북", "무주": "전북", "부안군": "전북",
    # 전남·광주
    "광주": "광역시", "목포": "전남", "여수": "전남", "흑산도": "전남",
    "완도": "전남", "장흥": "전남", "해남": "전남", "고흥": "전남",
    "순천": "전남", "진도군": "전남", "영광군": "전남", "강진군": "전남",
    "장성": "전남", "나주": "전남", "담양": "전남", "화순": "전남",
    "구례군": "전남", "곡성": "전남", "함평": "전남", "무안": "전남",
    "보성군": "전남", "영암": "전남", "광양시": "전남", "진도": "전남",
    "목포항": "전남", "여수항": "전남", "홍도": "전남", "거문도": "전남",
    # 경북·대구·울산
    "울릉도": "경북", "안동": "경북", "포항": "경북", "대구": "광역시",
    "울진": "경북", "영덕": "경북", "의성": "경북", "구미": "경북",
    "영천": "경북", "경주시": "경북", "문경": "경북", "영주": "경북",
    "봉화": "경북", "상주": "경북", "청송군": "경북", "울산": "광역시",
    "독도": "경북", "김천": "경북", "칠곡": "경북", "고령": "경북",
    "성주": "경북", "예천": "경북", "군위": "경북", "청도": "경북",
    "경산": "경북",
    # 경남·부산
    "부산": "광역시", "북부산": "광역시", "통영": "경남", "진주": "경남", "거창": "경남",
    "합천": "경남", "밀양": "경남", "산청": "경남", "거제": "경남",
    "남해": "경남", "함양군": "경남", "북창원": "경남", "창원": "경남",
    "양산시": "경남", "김해시": "경남", "의령군": "경남", "함안": "경남",
    "광양": "전남", "사천": "경남", "고성군": "경남", "하동": "경남",
    "창녕": "경남", "울주": "광역시",
    # 제주 (임가경제조사 지역 코드에 없어 결합에서 빠진다)
    "제주": "제주", "고산": "제주", "성산": "제주", "서귀포": "제주",
    "성산포": "제주", "이어도": "제주", "추자도": "제주", "가파도": "제주",
    "지리산": "경남", "마라도": "제주", "한라산": "제주",
}

# 고산 관측소는 그 지역 임가의 재배 환경을 대표하지 못한다
MAX_ELEVATION_M = 600

# 결합에 사용할 기상 지표
WEATHER_COLS = [
    "평균기온", "최저기온평균", "최고기온평균", "연강수량", "연일조시간",
    "평균습도", "연일사량", "연증발량", "생육기평균기온", "생육기강수량",
    "서리일수", "초상서리일수", "개화기저온일수", "폭염일수", "호우일수",
]


def build_sido() -> pd.DataFrame:
    if not (os.path.exists(ANNUAL) and os.path.exists(STATIONS)):
        raise FileNotFoundError(
            "기상 자료가 없습니다. scripts/fetch_weather.py 를 먼저 실행하세요.")

    ann = pd.read_csv(ANNUAL)
    stn = pd.read_csv(STATIONS)[["STN", "STN_KO", "HT"]]
    df = ann.merge(stn, on="STN", how="left")

    df["시도"] = df["STN_KO"].map(STN_TO_SIDO)
    unmapped = sorted(df.loc[df["시도"].isna(), "STN_KO"].dropna().unique())
    if unmapped:
        print(f"[warn] 시도 미매핑 지점 {len(unmapped)}개: {unmapped[:12]}")

    lowland = df[(df["HT"] <= MAX_ELEVATION_M) & df["시도"].notna()].copy()
    dropped = int((df["HT"] > MAX_ELEVATION_M).sum())
    print(f"[info] 고도 {MAX_ELEVATION_M}m 초과 관측소 {dropped}개 지점-연 제외")

    # 관측일수가 부족한 지점-연은 연 집계가 왜곡되므로 뺀다
    before = len(lowland)
    lowland = lowland[lowland["관측일수"] >= 300]
    print(f"[info] 관측일수 300일 미만 {before - len(lowland)}건 제외")

    cols = [c for c in WEATHER_COLS if c in lowland.columns]
    sido = (lowland.groupby(["시도", "연도"], observed=True)[cols]
            .mean().round(2).reset_index())
    sido["지점수"] = (lowland.groupby(["시도", "연도"], observed=True)["STN"]
                    .nunique().values)
    sido["지역별"] = sido["시도"].map(REGION_CODE)
    return sido.dropna(subset=["지역별"]).astype({"지역별": int})


def attach(df: pd.DataFrame, sido: pd.DataFrame | None = None,
           year_col: str = "조사연도", region_col: str = "지역별") -> pd.DataFrame:
    """임가 데이터에 (지역, 연도) 키로 기상 지표를 붙인다.

    기상 자료가 없는 조합(제주 등)은 결측으로 남긴다. XGBoost는 결측을 그대로
    처리하므로 행을 버리지 않는다.
    """
    if sido is None:
        sido = pd.read_csv(OUT_SIDO) if os.path.exists(OUT_SIDO) else build_sido()

    cols = [c for c in WEATHER_COLS if c in sido.columns]
    right = sido[["지역별", "연도"] + cols].rename(
        columns={"연도": year_col, **{c: f"기상_{c}" for c in cols}})
    out = df.merge(right, left_on=[region_col, year_col],
                   right_on=["지역별", year_col], how="left",
                   suffixes=("", "_w"))
    matched = out[f"기상_{cols[0]}"].notna().mean() * 100
    print(f"[info] 기상 결합률 {matched:.1f}%")
    return out


def weather_feature_names(sido: pd.DataFrame | None = None) -> list[str]:
    cols = WEATHER_COLS if sido is None else [c for c in WEATHER_COLS if c in sido.columns]
    return [f"기상_{c}" for c in cols]


def main() -> None:
    sido = build_sido()
    sido.to_csv(OUT_SIDO, index=False, encoding="utf-8-sig")
    print(f"\n[saved] {OUT_SIDO}  {len(sido)}행 (시도×연도)")
    print(f"시도 {sido['시도'].nunique()}개 · 연도 {sido['연도'].min()}~{sido['연도'].max()}")
    print("\n연도별 전국 평균:")
    print(sido.groupby("연도")[["평균기온", "연강수량", "서리일수", "폭염일수",
                              "개화기저온일수"]].mean().round(1).to_string())
    print("\n시도별 평균 (2023):")
    print(sido[sido["연도"] == 2023][
        ["시도", "평균기온", "연강수량", "생육기강수량", "서리일수", "폭염일수", "지점수"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()
