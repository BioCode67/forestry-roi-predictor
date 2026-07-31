<script setup>
import { computed, onMounted, provide, reactive, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { api } from './lib/api'

const route = useRoute()
/** 히어로가 있는 화면에서는 헤더가 이미지 위에 얹힌다 */
const floating = computed(() => route.path === '/')

const meta = ref(null)
const health = ref(null)
const err = ref('')

/** 사이드바 입력 — 전 화면이 공유하는 단일 상태 */
const farm = reactive({
  연령별: 4, 지역별: 32, '전/겸업별': 1, 업종별: 3,
  가구원수별: 2, 임지규모별: 3,
  임업경영비: 15000000, 임업외소득: 8000000,
  '기초_자본(순재산)': 400000000, 연초보유: 3000000, 조사연도: 2023,
  // 작년 자료 — 채우면 정확도가 크게 오르는 대신, 없어도 계산은 된다
  직전_ROI: null, 직전_경영비: null,
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
  { to: '/risk', label: '몰아도 될까' },
  { to: '/detail', label: '자세한 진단' },
  { to: '/item', label: '작물별 자세히' },
  { to: '/model', label: '얼마나 맞나' },
  { to: '/about', label: '쓰인 자료' },
]
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar__bar">
      <RouterLink to="/" class="brand">
        <span class="brand__mark" aria-hidden="true">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2 6.2 11h3L4.6 18h6.15v4h2.5v-4h6.15L15.8 11h3L12 2Z" />
          </svg>
        </span>
        <span class="brand__title">우리 산 수익 계산기</span>
      </RouterLink>

      <nav class="nav">
        <RouterLink v-for="n in NAV" :key="n.to" :to="n.to">{{ n.label }}</RouterLink>
      </nav>

      <RouterLink to="/" class="cta">계산해 보기</RouterLink>
      </div>
    </header>

    <div v-if="err" style="padding:24px">
      <div class="note note--danger">
        <strong>API에 연결하지 못했습니다.</strong> {{ err }}<br />
        <span class="fs-sm">백엔드를 먼저 실행하세요 — <code class="mono">uvicorn api.main:app --port 8000</code></span>
      </div>
    </div>

    <RouterView v-else />

    <footer class="foot">
      <div class="foot__inner">
        <div class="foot__brand">
          <span class="brand__mark" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2 6.2 11h3L4.6 18h6.15v4h2.5v-4h6.15L15.8 11h3L12 2Z" />
            </svg>
          </span>
          <div>
            <p class="foot__title">우리 산 수익 계산기</p>
            <p class="foot__sub">전국 임가를 조사한 국가승인통계로 계산합니다</p>
          </div>
        </div>

        <div class="foot__cols">
          <div class="foot__col">
            <p class="foot__head">쓰인 임업통계</p>
            <p>임가경제조사 2019~2023</p>
            <p>임산물생산비조사 2018~2024</p>
            <p>임산물생산조사 2022~2024</p>
            <p>임업경영실태조사 2018·2020</p>
          </div>
          <div class="foot__col">
            <p class="foot__head">함께 쓴 공공데이터</p>
            <p>KAMIS 농수산물 도매가격</p>
            <p>산림청 보조금 세부사업</p>
            <p>기상청 지상관측 일자료</p>
          </div>
          <div class="foot__col">
            <p class="foot__head">바로 가기</p>
            <RouterLink v-for="n in NAV.slice(0, 4)" :key="n.to" :to="n.to">{{ n.label }}</RouterLink>
          </div>
        </div>
      </div>

      <div class="foot__bar">
        <span>2026년 임업통계 활용 경진대회 · 데이터 분석 부문</span>
        <span>자료 출처 통계청 MDIS · 산림청</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.foot {
  margin-top: 60px;
  border-top: 1px solid var(--border);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--forest-50) 60%, transparent), transparent 60%),
    var(--surface);
}
.foot__inner {
  max-width: var(--maxw); margin: 0 auto;
  padding: 46px 30px 34px;
  display: flex; gap: 48px; flex-wrap: wrap; justify-content: space-between;
}
.foot__brand { display: flex; gap: 12px; align-items: flex-start; max-width: 34ch; }
.foot__title { font-weight: 740; font-size: 1rem; letter-spacing: -0.028em; }
.foot__sub { font-size: 0.83rem; color: var(--text-muted); margin-top: 4px; line-height: 1.6; }

.foot__cols { display: flex; gap: 52px; flex-wrap: wrap; }
.foot__col { display: flex; flex-direction: column; gap: 6px; font-size: 0.83rem; color: var(--text-muted); }
.foot__col a { color: var(--text-muted); text-decoration: none; }
.foot__col a:hover { color: var(--accent); }
.foot__head {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--text-subtle); margin-bottom: 4px;
}

.foot__bar {
  border-top: 1px solid var(--border);
  padding: 16px 30px;
  display: flex; gap: 18px; flex-wrap: wrap; justify-content: space-between;
  max-width: var(--maxw); margin: 0 auto;
  font-size: 0.76rem; color: var(--text-subtle);
}
@media (prefers-color-scheme: dark) {
  .foot { background: linear-gradient(180deg, #13201a, transparent 60%), var(--surface); }
}
@media (max-width: 820px) {
  .foot__inner { padding: 32px 18px 24px; gap: 30px; }
  .foot__cols { gap: 30px; }
  .foot__bar { padding: 14px 18px; }
}
</style>
