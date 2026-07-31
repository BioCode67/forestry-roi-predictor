<script setup>
/**
 * 내부 화면 상단 띠.
 * 홈의 풀 히어로와 같은 언어를 쓰되 높이를 낮춰, 화면을 옮겨도
 * 같은 서비스 안에 있다는 느낌이 끊기지 않게 한다.
 */
defineProps({ title: String, desc: String, badge: String, badgeKind: { type: String, default: 'grey' } })
</script>

<template>
  <div class="pagehead">
    <div class="pagehead__glow" aria-hidden="true"></div>
    <div class="pagehead__inner">
      <div class="row row--wrap" style="gap:10px">
        <h1>{{ title }}</h1>
        <span v-if="badge" class="badge" :class="`badge--${badgeKind}`">{{ badge }}</span>
      </div>
      <p v-if="desc" class="pagehead__desc">{{ desc }}</p>
    </div>
  </div>
</template>

<style scoped>
.pagehead {
  position: relative; overflow: hidden;
  margin: -30px -30px 26px;
  padding: 34px 30px 30px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg,
    color-mix(in srgb, var(--forest-50) 92%, transparent), transparent);
}
@media (prefers-color-scheme: dark) {
  .pagehead { background: linear-gradient(180deg, #14201a, transparent); }
}
.pagehead__glow {
  position: absolute; right: -80px; top: -120px; width: 420px; height: 300px;
  border-radius: 50%; pointer-events: none;
  background: radial-gradient(circle, rgba(217,139,63,.16), transparent 68%);
}
.pagehead__inner { max-width: var(--maxw); margin: 0 auto; position: relative; }
.pagehead__desc {
  margin-top: 9px; max-width: 76ch;
  font-size: 0.9rem; line-height: 1.62; color: var(--text-muted);
}
@media (max-width: 1080px) { .pagehead { margin: -20px -16px 20px; padding: 26px 16px 22px; } }
</style>
