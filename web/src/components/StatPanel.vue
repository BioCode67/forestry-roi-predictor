<script setup>
/**
 * 스크롤에 반응하는 전면 통계 패널.
 * 참고 템플릿이 스크롤할 때마다 새 사진을 보여주듯, 여기서는 사진 위에
 * 통계 한 가지를 얹어 화면을 내릴 때마다 새 사실이 드러나게 한다.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  src: { type: String, required: true },
  kicker: String,
  value: String,
  unit: String,
  title: String,
  body: String,
  source: String,
  align: { type: String, default: 'left' },
})

const el = ref(null)
const shown = ref(false)
let io = null

onMounted(() => {
  io = new IntersectionObserver(
    ([e]) => { if (e.isIntersecting) { shown.value = true; io.disconnect() } },
    { threshold: 0.28 },
  )
  io.observe(el.value)
})
onBeforeUnmount(() => io?.disconnect())
</script>

<template>
  <section ref="el" class="sp" :class="[`sp--${align}`, { 'is-shown': shown }]">
    <img class="sp__img" :src="src" alt="" loading="lazy" />
    <div class="sp__veil" aria-hidden="true"></div>
    <div class="sp__inner">
      <div class="sp__box">
        <p v-if="kicker" class="sp__kicker">{{ kicker }}</p>
        <p class="sp__value">{{ value }}<small v-if="unit">{{ unit }}</small></p>
        <h2 class="sp__title">{{ title }}</h2>
        <p class="sp__body">{{ body }}</p>
        <p v-if="source" class="sp__source">{{ source }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sp {
  position: relative; isolation: isolate; overflow: hidden;
  min-height: min(78vh, 720px);
  display: flex; align-items: center;
}
.sp__img {
  position: absolute; inset: 0; z-index: -2;
  width: 100%; height: 100%; object-fit: cover;
  transform: scale(1.1); transition: transform 1.5s cubic-bezier(.2,.7,.2,1);
}
.sp.is-shown .sp__img { transform: scale(1); }

.sp__veil {
  position: absolute; inset: 0; z-index: -1;
  background: linear-gradient(100deg, rgba(10,16,10,.86) 0%, rgba(10,16,10,.6) 42%,
              rgba(10,16,10,.2) 74%, rgba(10,16,10,.34) 100%);
}
.sp--right .sp__veil {
  background: linear-gradient(260deg, rgba(10,16,10,.86) 0%, rgba(10,16,10,.6) 42%,
              rgba(10,16,10,.2) 74%, rgba(10,16,10,.34) 100%);
}

.sp__inner { width: 100%; padding: 0 32px; max-width: var(--maxw); margin: 0 auto; }
.sp--right .sp__inner { display: flex; justify-content: flex-end; }

.sp__box {
  max-width: 40ch;
  opacity: 0; transform: translateY(26px);
  transition: opacity .7s ease .12s, transform .7s cubic-bezier(.2,.7,.3,1) .12s;
}
.sp.is-shown .sp__box { opacity: 1; transform: none; }

.sp__kicker {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.2em;
  text-transform: uppercase; color: rgba(255,255,255,.66); margin-bottom: 14px;
}
.sp__value {
  font-size: clamp(3rem, 8vw, 6.4rem); line-height: .94;
  font-weight: 860; letter-spacing: -0.055em; color: #fff;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 4px 40px rgba(0,0,0,.4);
}
.sp__value small { font-size: 0.3em; font-weight: 700; margin-left: 6px; letter-spacing: -0.01em; }
.sp__title {
  margin-top: 16px; font-size: clamp(1.1rem, 2vw, 1.5rem);
  font-weight: 720; color: #fff; letter-spacing: -0.024em; line-height: 1.35;
}
.sp__body { margin-top: 12px; font-size: 0.94rem; line-height: 1.68; color: rgba(255,255,255,.84); }
.sp__source {
  margin-top: 16px; font-size: 0.74rem; color: rgba(255,255,255,.56);
  padding-top: 12px; border-top: 1px solid rgba(255,255,255,.18);
}

@media (max-width: 820px) {
  .sp { min-height: 66vh; }
  .sp__inner { padding: 0 18px; }
  .sp--right .sp__inner { justify-content: flex-start; }
  .sp__veil, .sp--right .sp__veil {
    background: linear-gradient(180deg, rgba(10,16,10,.5), rgba(10,16,10,.88));
  }
}
@media (prefers-reduced-motion: reduce) {
  .sp__img { transform: none !important; transition: none; }
  .sp__box { opacity: 1; transform: none; transition: none; }
}
</style>
