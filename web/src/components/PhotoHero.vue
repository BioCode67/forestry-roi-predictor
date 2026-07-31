<script setup>
/**
 * 풀스크린 사진 히어로.
 * 참고한 템플릿처럼 사진이 화면을 꽉 채우고, 제목이 하단에 크게 얹힌다.
 * 스크롤에 따라 배경이 천천히 밀려 깊이감을 준다(패럴랙스).
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  src: { type: String, required: true },
  eyebrow: String,
  title: String,
  lead: String,
})

const shift = ref(0)
const loaded = ref(false)
let raf = null

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    // 배경을 스크롤의 30%만 움직여 앞뒤 층이 분리돼 보이게 한다
    shift.value = Math.min(window.scrollY * 0.3, 260)
    raf = null
  })
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  if (raf) cancelAnimationFrame(raf)
})
</script>

<template>
  <section class="ph">
    <div class="ph__media" :style="{ transform: `translate3d(0, ${shift}px, 0) scale(1.08)` }">
      <img :src="src" alt="" @load="loaded = true" :class="{ 'is-loaded': loaded }" />
    </div>
    <div class="ph__veil" aria-hidden="true"></div>

    <div class="ph__body">
      <div class="ph__inner">
        <p v-if="eyebrow" class="ph__eyebrow">{{ eyebrow }}</p>
        <h1 class="ph__title">{{ title }}</h1>
        <p v-if="lead" class="ph__lead">{{ lead }}</p>
        <slot />
      </div>
    </div>

    <div class="ph__scroll" aria-hidden="true">
      <span class="ph__scrollline"></span>
      <span class="ph__scrolltext">아래로 내려 보세요</span>
    </div>
  </section>
</template>

<style scoped>
.ph {
  position: relative;
  min-height: min(94vh, 940px);
  display: flex; align-items: flex-end;
  overflow: hidden;
  isolation: isolate;
  background: #1a1f18;
}

.ph__media { position: absolute; inset: -8% 0 -8%; z-index: -2; will-change: transform; }
.ph__media img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  opacity: 0; transition: opacity .8s ease;
}
.ph__media img.is-loaded { opacity: 1; }

.ph__veil {
  position: absolute; inset: 0; z-index: -1;
  background:
    linear-gradient(180deg, rgba(18,24,16,.52) 0%, rgba(18,24,16,.12) 26%,
                    rgba(18,24,16,.34) 62%, rgba(12,18,11,.86) 100%);
}

.ph__body { width: 100%; padding: 0 32px 92px; }
.ph__inner { max-width: var(--maxw); margin: 0 auto; }

.ph__eyebrow {
  font-size: 0.76rem; font-weight: 700; letter-spacing: 0.22em;
  text-transform: uppercase; color: rgba(255,255,255,.78);
  margin-bottom: 18px;
}

.ph__title {
  font-size: clamp(2.3rem, 6.2vw, 5.4rem);
  line-height: 0.99;
  font-weight: 850;
  letter-spacing: -0.05em;
  color: #fff;
  max-width: 16ch;
  text-shadow: 0 4px 40px rgba(0,0,0,.42);
}

.ph__lead {
  margin-top: 22px; max-width: 54ch;
  font-size: clamp(0.96rem, 1.3vw, 1.14rem);
  line-height: 1.65;
  color: rgba(255,255,255,.9);
  text-shadow: 0 2px 16px rgba(0,0,0,.5);
}

.ph__scroll {
  position: absolute; right: 34px; bottom: 92px; z-index: 1;
  display: flex; flex-direction: column; align-items: center; gap: 10px;
}
.ph__scrollline {
  width: 1px; height: 54px; background: rgba(255,255,255,.42);
  position: relative; overflow: hidden;
}
.ph__scrollline::after {
  content: ""; position: absolute; inset: 0; background: #fff;
  transform-origin: top; animation: drip 2.1s cubic-bezier(.6,.1,.3,1) infinite;
}
@keyframes drip {
  0%   { transform: scaleY(0); transform-origin: top; }
  45%  { transform: scaleY(1); transform-origin: top; }
  55%  { transform: scaleY(1); transform-origin: bottom; }
  100% { transform: scaleY(0); transform-origin: bottom; }
}
.ph__scrolltext {
  font-size: 0.68rem; letter-spacing: 0.14em; color: rgba(255,255,255,.68);
  writing-mode: vertical-rl;
}

@media (max-width: 820px) {
  .ph { min-height: 78vh; }
  .ph__body { padding: 0 18px 64px; }
  .ph__title { max-width: none; }
  .ph__scroll { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ph__media { transform: none !important; }
  .ph__scrollline::after { animation: none; }
}
</style>
