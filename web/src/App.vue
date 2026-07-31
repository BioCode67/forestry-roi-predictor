<script setup>
import { onMounted, provide, reactive, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { api } from './lib/api'

const meta = ref(null)
const health = ref(null)
const err = ref('')

/** 사이드바 입력 — 전 화면이 공유하는 단일 상태 */
const farm = reactive({
  연령별: 4, 지역별: 32, '전/겸업별': 1, 업종별: 3,
  가구원수별: 2, 임지규모별: 3,
  임업경영비: 15000000, 임업외소득: 8000000,
  '기초_자본(순재산)': 400000000, 연초보유: 3000000, 조사연도: 2023,
})

provide('meta', meta)
provide('farm', farm)
provide('health', health)

onMounted(async () => {
  try {
    const [m, h] = await Promise.all([api.meta(), api.health()])
    meta.value = m
    health.value = h
  } catch (e) {
    err.value = e.message
  }
})

const NAV = [
  { to: '/', label: '임가 진단' },
  { to: '/item', label: '품목 정밀' },
  { to: '/shipping', label: '출하 전략' },
  { to: '/market', label: '시장·단가' },
  { to: '/insight', label: '수익 개선' },
  { to: '/model', label: '모델 성능' },
  { to: '/about', label: '데이터·방법론' },
]
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <div class="brand__mark" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2 6.2 11h3L4.6 18h6.15v4h2.5v-4h6.15L15.8 11h3L12 2Z" />
          </svg>
        </div>
        <div class="brand__text">
          <span class="brand__title">임가 수익성 분석 플랫폼</span>
          <span class="brand__sub">산림청 국가승인통계 마이크로데이터 기반</span>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="n in NAV" :key="n.to" :to="n.to">{{ n.label }}</RouterLink>
      </nav>

      <div class="topbar__right">
        <span v-if="health" class="badge badge--green nowrap">
          모델 {{ [health.models.model_a, health.models.model_b].filter(Boolean).length }}종 가동
        </span>
        <span v-else class="spinner" />
      </div>
    </header>

    <div v-if="err" style="padding:24px">
      <div class="note note--danger">
        <strong>API에 연결하지 못했습니다.</strong> {{ err }}<br />
        <span class="fs-sm">백엔드를 먼저 실행하세요 — <code class="mono">uvicorn api.main:app --port 8000</code></span>
      </div>
    </div>

    <RouterView v-else />

    <footer style="padding:22px 28px;border-top:1px solid var(--border);background:var(--surface)">
      <div class="container fs-xs subtle" style="display:flex;gap:18px;flex-wrap:wrap">
        <span>2026년 임업통계 활용 경진대회 · 데이터 분석 부문</span>
        <span>임가경제조사 · 임산물생산비조사 · 임산물생산조사 · 임업경영실태조사 (통계청 MDIS)</span>
        <span>융복합: KAMIS 도매가격 · 산림청 보조금 세부사업</span>
      </div>
    </footer>
  </div>
</template>
