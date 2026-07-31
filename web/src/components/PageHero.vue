<script setup>
/**
 * 내부 화면 사진 배너.
 * 홈의 풀스크린 히어로를 낮춘 형태로, 어느 화면에 있어도 같은 언어를 유지한다.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  src: { type: String, required: true },
  eyebrow: String,
  title: String,
  lead: String,
})

const shift = ref(0)
let raf = null
function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    shift.value = Math.min(window.scrollY * 0.22, 140)
    raf = null
  })
}
onMounted(() => { window.addEventListener('scroll', onScroll, { passive: true }); onScroll() })
onBeforeUnmount(() => { window.removeEventListener('scroll', onScroll); if (raf) cancelAnimationFrame(raf) })
</script>

<template>
  <section class="pgh">
    <div class="pgh__media" :style="{ transform: `translate3d(0,${shift}px,0) scale(1.07)` }">
      <img :src="src" alt="" />
    </div>
    <div class="pgh__veil" aria-hidden="true"></div>
    <div class="pgh__inner">
      <p v-if="eyebrow" class="pgh__eyebrow">{{ eyebrow }}</p>
      <h1 class="pgh__title">{{ title }}</h1>
      <p v-if="lead" class="pgh__lead">{{ lead }}</p>
    </div>
  </section>
</template>

<style scoped>
.pgh {
  position: relative; isolation: isolate; overflow: hidden;
  min-height: 460px; display: flex; align-items: flex-end;
  background: #1a1f18;
}
.pgh__media { position: absolute; inset: -7% 0; z-index: -2; will-change: transform; }
.pgh__media img { width: 100%; height: 100%; object-fit: cover; display: block; }
.pgh__veil {
  position: absolute; inset: 0; z-index: -1;
  background: linear-gradient(180deg, rgba(14,20,13,.62) 0%, rgba(14,20,13,.2) 34%,
              rgba(12,18,11,.82) 100%);
}
.pgh__inner { max-width: var(--maxw); margin: 0 auto; width: 100%; padding: 0 32px 54px; }
.pgh__eyebrow {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase;
  color: rgba(255,255,255,.74); margin-bottom: 14px;
}
.pgh__title {
  font-size: clamp(1.9rem, 4.4vw, 3.6rem); line-height: 1.04; font-weight: 840;
  letter-spacing: -0.045em; color: #fff; max-width: 20ch;
  text-shadow: 0 4px 34px rgba(0,0,0,.4);
}
.pgh__lead {
  margin-top: 16px; max-width: 62ch; font-size: 0.98rem; line-height: 1.66;
  color: rgba(255,255,255,.88); text-shadow: 0 2px 14px rgba(0,0,0,.5);
}
@media (max-width: 820px) {
  .pgh { min-height: 330px; }
  .pgh__inner { padding: 0 18px 38px; }
  .pgh__title { max-width: none; }
}
@media (prefers-reduced-motion: reduce) { .pgh__media { transform: none !important; } }
</style>
