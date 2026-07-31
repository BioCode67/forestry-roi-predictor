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
  { to: '/', label: '얼마나 남을까' },
  { to: '/shipping', label: '언제 팔까' },
  { to: '/market', label: '값은 얼마' },
  { to: '/insight', label: '더 버는 법' },
  { to: '/detail', label: '자세한 진단' },
  { to: '/item', label: '작물별 자세히' },
  { to: '/model', label: '얼마나 맞나' },
  { to: '/about', label: '쓰인 자료' },
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
          <span class="brand__title">우리 산 수익 계산기</span>
          <span class="brand__sub">전국 임가 조사 자료로 계산합니다</span>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="n in NAV" :key="n.to" :to="n.to">{{ n.label }}</RouterLink>
      </nav>

      <div class="topbar__right">
        <span v-if="health" class="badge badge--green nowrap">계산 준비됨</span>
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
