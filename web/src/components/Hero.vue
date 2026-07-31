<script setup>
/**
 * 풀블리드 히어로.
 * 외부 이미지는 오프라인·CSP 환경에서 깨지므로, 골든아워 하늘과 능선을
 * CSS 그라디언트와 SVG 실루엣으로 그린다. 파일 의존이 없어 항상 같게 보인다.
 */
defineProps({
  eyebrow: String,
  title: String,
  lead: String,
  compact: Boolean,
})
</script>

<template>
  <section class="hero" :class="{ 'hero--compact': compact }">
    <div class="hero__sky" aria-hidden="true"></div>
    <div class="hero__scrim" aria-hidden="true"></div>

    <svg class="hero__ridge" viewBox="0 0 1440 320" preserveAspectRatio="none" aria-hidden="true">
      <path class="ridge ridge--far"
        d="M0,214 L120,186 L240,206 L360,158 L480,192 L600,150 L720,180 L840,140 L960,176 L1080,150 L1200,184 L1320,160 L1440,190 L1440,320 L0,320 Z" />
      <path class="ridge ridge--mid"
        d="M0,246 L110,222 L220,250 L330,206 L440,238 L560,200 L680,232 L800,196 L920,230 L1040,204 L1160,236 L1290,212 L1440,240 L1440,320 L0,320 Z" />
      <g class="ridge ridge--near">
        <path d="M0,282 L1440,282 L1440,320 L0,320 Z" />
        <!-- 침엽수 실루엣 -->
        <path v-for="(x, i) in 48" :key="i"
          :d="`M${x * 30 - 22},${282 - (i % 4) * 7 - 16} l7,${(i % 4) * 7 + 16} l-14,0 Z`" />
      </g>
    </svg>

    <div class="hero__inner">
      <p v-if="eyebrow" class="hero__eyebrow">{{ eyebrow }}</p>
      <h1 class="hero__title">{{ title }}</h1>
      <p v-if="lead" class="hero__lead">{{ lead }}</p>
      <div v-if="$slots.default" class="hero__slot"><slot /></div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border-radius: 0 0 var(--r-xl) var(--r-xl);
  padding: 104px 32px 96px;
  margin-bottom: 30px;
}
.hero--compact { padding: 62px 32px 86px; }

.hero__sky {
  position: absolute; inset: 0; z-index: -2;
  background:
    radial-gradient(120% 90% at 78% 12%, #ffe6b8 0%, rgba(255,230,184,0) 58%),
    linear-gradient(178deg, #f6d9a6 0%, #edbf87 34%, #c98f5c 64%, #7d5a3c 100%);
}
@media (prefers-color-scheme: dark) {
  .hero__sky {
    background:
      radial-gradient(120% 90% at 78% 12%, #6b4a2a 0%, rgba(107,74,42,0) 58%),
      linear-gradient(178deg, #3a2c1e 0%, #2a2318 36%, #1b2018 68%, #101512 100%);
  }
}

.hero__scrim {
  position: absolute; inset: 0 0 auto; height: 170px; z-index: -1;
  background: linear-gradient(180deg, rgba(60,38,14,.32), rgba(60,38,14,0));
}

.hero__ridge {
  position: absolute; left: 0; right: 0; bottom: -1px; z-index: -1;
  width: 100%; height: 54%;
}
.ridge--far  { fill: #6f7f5e; opacity: .42; }
.ridge--mid  { fill: #4a5c42; opacity: .62; }
.ridge--near { fill: #22331f; }
@media (prefers-color-scheme: dark) {
  .ridge--far  { fill: #2c3a2a; opacity: .55; }
  .ridge--mid  { fill: #1d2a1d; opacity: .75; }
  .ridge--near { fill: #0d150d; }
}

.hero__inner { max-width: var(--maxw); margin: 0 auto; position: relative; }

.hero__eyebrow {
  font-size: 0.74rem; font-weight: 700; letter-spacing: 0.19em;
  text-transform: uppercase; color: rgba(255,255,255,.82);
  margin-bottom: 14px;
  text-shadow: 0 1px 8px rgba(60,36,12,.4);
}

.hero__title {
  font-size: clamp(1.95rem, 5vw, 3.9rem);
  line-height: 1.02;
  font-weight: 820;
  letter-spacing: -0.045em;
  color: #fff;
  /* 한글은 글자 폭이 넓어 ch 단위가 과하게 잡힌다 */
  max-width: 15ch;
  text-shadow: 0 2px 22px rgba(50,30,10,.34);
}

.hero__lead {
  margin-top: 18px;
  max-width: 56ch;
  font-size: clamp(0.95rem, 1.35vw, 1.1rem);
  line-height: 1.62;
  color: rgba(255,255,255,.93);
  text-shadow: 0 1px 10px rgba(50,30,10,.4);
}

.hero__slot { margin-top: 26px; }

@media (max-width: 820px) {
  .hero { padding: 64px 18px 84px; border-radius: 0 0 var(--r-lg) var(--r-lg); }
  .hero--compact { padding: 46px 18px 66px; }
  .hero__title { max-width: none; }
}
</style>
