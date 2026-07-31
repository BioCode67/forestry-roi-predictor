"""
기상청 API 허브 클라이언트 (apihub.kma.go.kr)

인증키는 코드에 두지 않는다. 환경변수로만 전달한다.
    export KMA_AUTH_KEY=...

API 접근 정책
-------------
허브는 관측망(종관/방재/기후통계/…) 카테고리 아래에 개별 API를 두고, **API마다**
별도의 활용신청을 받는다. 신청되지 않은 API는 403 "활용신청이 필요한 API"를 돌려준다.

  kma_sfctm2.php  지상관측 시간자료 — 단일 시각(tm) 조회. stn=0이면 전국 지점 일괄
  kma_sfcdd3.php  지상관측 일자료   — tm1~tm2 기간 조회 (승인 시 훨씬 저렴)

일자료가 열려 있으면 그쪽을 쓰고, 아니면 시간자료를 표본 추출해 일 단위로 집계한다.
시간자료의 RN_DAY는 '해당 시각까지의 일강수량 누적'이므로, 하루 마지막 관측만
있으면 그날 총 강수량을 얻을 수 있다.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE = "https://apihub.kma.go.kr/api/typ01/url/"

# kma_sfctm2 응답 컬럼 (help=1 헤더 기준)
SFCTM_COLS = (
    "TM STN WD WS GST_WD GST_WS GST_TM PA PS PT PR TA TD HM PV RN RN_DAY RN_JUN "
    "RN_INT SD_HR3 SD_DAY SD_TOT WC WP WW CA_TOT CA_MID CH_MIN CT CT_TOP CT_MID "
    "CT_LOW VS SS SI ST_GD TS TE_005 TE_01 TE_02 TE_03 ST_SEA WH BF IR IX"
).split()

MISSING = {-9.0, -99.0, -999.0, -9.9, -50.0}


class KmaClient:
    def __init__(self, auth_key: str | None = None, pause: float = 0.12):
        self.key = auth_key or os.environ.get("KMA_AUTH_KEY")
        if not self.key:
            raise RuntimeError(
                "기상청 인증키가 없습니다. 환경변수 KMA_AUTH_KEY 를 설정하세요.")
        self.pause = pause
        self.s = requests.Session()

    def _get(self, endpoint: str, params: dict, timeout: int = 40) -> str:
        p = dict(params)
        p.update({"help": "0", "authKey": self.key})
        r = self.s.get(BASE + endpoint, params=p, timeout=timeout)
        r.raise_for_status()
        time.sleep(self.pause)
        return r.text

    @staticmethod
    def _rows(text: str) -> list[list[str]]:
        return [ln.split() for ln in text.splitlines()
                if ln and not ln.startswith("#") and not ln.startswith("7777")]

    def available(self, endpoint: str, probe: dict) -> bool:
        """해당 API가 활용신청되어 열려 있는지 확인한다."""
        try:
            return "START7777" in self._get(endpoint, probe, timeout=20)
        except Exception:  # noqa: BLE001
            return False

    # -- 지점 정보 ---------------------------------------------------------
    def stations(self) -> pd.DataFrame:
        txt = self._get("stn_inf.php", {"inf": "SFC", "stn": "", "tm": "20230101"})
        rows = [r for r in self._rows(txt) if len(r) >= 12]
        cols = ["STN", "LON", "LAT", "STN_SP", "HT", "HT_PA", "HT_TA", "HT_WD",
                "HT_RN", "STN_AD", "STN_KO", "STN_EN"]
        df = pd.DataFrame([r[:len(cols)] for r in rows], columns=cols)
        for c in ["STN", "LON", "LAT", "HT"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["STN"])

    # -- 시간자료 ----------------------------------------------------------
    def hourly_all_stations(self, tm: str) -> pd.DataFrame:
        """단일 시각의 전국 지점 관측. tm = YYYYMMDDHHMM"""
        txt = self._get("kma_sfctm2.php", {"tm": tm, "stn": "0"})
        rows = [r for r in self._rows(txt) if len(r) >= len(SFCTM_COLS)]
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([r[:len(SFCTM_COLS)] for r in rows], columns=SFCTM_COLS)
        for c in ["STN", "TA", "RN_DAY", "SS", "SI", "TS", "HM", "WS", "TE_005", "TE_01"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            df.loc[df[c].isin(MISSING), c] = pd.NA
        df["일자"] = pd.to_datetime(df["TM"].str[:8], format="%Y%m%d", errors="coerce")
        return df

    # -- 일자료 (승인 시) ---------------------------------------------------
    def daily_range(self, start: str, end: str, stn: str = "0") -> pd.DataFrame:
        """kma_sfcdd3.php 기간 조회. start/end = YYYYMMDD"""
        txt = self._get("kma_sfcdd3.php", {"tm1": start, "tm2": end, "stn": stn}, timeout=90)
        rows = self._rows(txt)
        if not rows:
            return pd.DataFrame()
        width = max(len(r) for r in rows)
        df = pd.DataFrame([r + [None] * (width - len(r)) for r in rows])
        return df


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
