"""
KAMIS(농수산물유통정보) OpenAPI 클라이언트

KAMIS 서버는 구형 TLS 설정을 사용해 OpenSSL 3 기본 정책에서
`SSLV3_ALERT_HANDSHAKE_FAILURE` 로 핸드셰이크가 거부된다.
보안 수준을 낮춘 SSLContext를 쓰는 전용 어댑터로 우회한다.

인증 정보는 코드에 두지 않는다. 환경변수로만 전달한다.
    export KAMIS_CERT_KEY=...   # 발급받은 인증키
    export KAMIS_CERT_ID=...    # 가입 이메일
"""
from __future__ import annotations

import os
import ssl
import time

import requests
import urllib3
from requests.adapters import HTTPAdapter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www.kamis.or.kr/service/price/xml.do"

# KAMIS 부류코드
CATEGORIES = {
    "100": "식량작물", "200": "채소류", "300": "특용작물",
    "400": "과일류", "500": "축산물", "600": "수산물",
}


class _LegacyTLSAdapter(HTTPAdapter):
    """구형 TLS 서버와 핸드셰이크하기 위한 어댑터."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        except ssl.SSLError:
            pass
        try:
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        except AttributeError:
            pass
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


class KamisClient:
    def __init__(self, cert_key: str | None = None, cert_id: str | None = None,
                 pause: float = 0.25):
        self.key = cert_key or os.environ.get("KAMIS_CERT_KEY")
        self.cid = cert_id or os.environ.get("KAMIS_CERT_ID")
        if not self.key or not self.cid:
            raise RuntimeError(
                "KAMIS 인증정보가 없습니다. 환경변수 KAMIS_CERT_KEY / KAMIS_CERT_ID 를 설정하거나 "
                "생성자 인자로 전달하세요."
            )
        self.pause = pause
        self.s = requests.Session()
        self.s.mount("https://", _LegacyTLSAdapter())

    def _get(self, params: dict, timeout: int = 40) -> dict:
        p = dict(params)
        p.setdefault("p_returntype", "json")
        # 액션마다 인증 파라미터 이름이 다르다 (p_cert_key / p_key 계열 혼용)
        p.update({"p_cert_key": self.key, "p_cert_id": self.cid,
                  "p_key": self.key, "p_id": self.cid})
        r = self.s.get(BASE, params=p, timeout=timeout)
        r.raise_for_status()
        time.sleep(self.pause)
        try:
            return r.json()
        except ValueError:
            return {"_raw": r.text}

    # -- 품목 코드 탐색 ----------------------------------------------------
    def daily_by_category(self, category: str, regday: str,
                          product_cls: str = "02", county: str = "1101") -> list[dict]:
        """부류별 일일 가격. 품목·품종·등급 코드를 수집하는 용도로도 쓴다.

        product_cls: 01 소매, 02 도매(중도매인 판매가격)
        county: 1101 서울 (전국 평균 조회는 지원 액션이 다름)
        """
        j = self._get({
            "action": "dailyPriceByCategoryList",
            "p_product_cls_code": product_cls,
            "p_country_code": county,
            "p_regday": regday,
            "p_convert_kg_yn": "Y",
            "p_item_category_code": category,
        })
        data = j.get("data")
        if isinstance(data, dict):
            items = data.get("item", [])
            return items if isinstance(items, list) else [items]
        return []

    def discover_items(self, regdays: list[str], categories: list[str] | None = None,
                       product_cls: str = "02") -> list[dict]:
        """여러 기준일을 훑어 품목/품종/등급 코드 표를 만든다.

        조사일에 따라 시세가 없는 품목은 응답에서 빠지므로 여러 날짜를 합집합으로 모은다.
        """
        seen: dict[tuple, dict] = {}
        for cat in (categories or CATEGORIES):
            for day in regdays:
                try:
                    rows = self.daily_by_category(cat, day, product_cls)
                except Exception:  # noqa: BLE001
                    continue
                for r in rows:
                    if not isinstance(r, dict) or not r.get("item_code"):
                        continue
                    k = (cat, r.get("item_code"), r.get("kind_code"), r.get("rank_code"))
                    seen.setdefault(k, {
                        "부류코드": cat, "부류명": CATEGORIES.get(cat, cat),
                        "품목코드": r.get("item_code"), "품목명": r.get("item_name"),
                        "품종코드": r.get("kind_code"), "품종명": r.get("kind_name"),
                        "등급코드": r.get("rank_code"), "등급명": r.get("rank"),
                        "단위": r.get("unit"),
                    })
        return list(seen.values())

    # -- 시계열 ------------------------------------------------------------
    def period_series(self, category: str, item_code: str, kind_code: str,
                      rank_code: str = "04", start: str = "2019-01-01",
                      end: str = "2024-12-31", county: str = "",
                      product_cls: str = "02") -> list[dict]:
        """기간별 가격 시계열. 반환 원소: {yyyy, regday, price, countyname}"""
        j = self._get({
            "action": "periodProductList",
            "p_startday": start,
            "p_endday": end,
            "p_itemcategorycode": category,
            "p_itemcode": item_code,
            "p_kindcode": kind_code,
            "p_productrankcode": rank_code,
            "p_countycode": county,
            "p_convert_kg_yn": "Y",
            "p_productclscode": product_cls,
        })
        data = j.get("data")
        if isinstance(data, dict):
            items = data.get("item", [])
            return items if isinstance(items, list) else [items]
        return []
