<script setup>
/** 템플릿의 중앙 정렬 대형 리드 문장. 섹션 사이의 숨 쉴 곳이 된다. */
defineProps({ kicker: String, text: String })
</script>

<template>
  <div class="lead">
    <p v-if="kicker" class="lead__kicker">{{ kicker }}</p>
    <p class="lead__text"><slot>{{ text }}</slot></p>
  </div>
</template>

<style scoped>
.lead { padding: 76px 24px 52px; text-align: center; }
.lead__kicker {
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase;
  color: var(--text-subtle); margin-bottom: 20px;
}
.lead__text {
  max-width: 30ch; margin: 0 auto;
  font-size: clamp(1.3rem, 2.9vw, 2.15rem); line-height: 1.45;
  font-weight: 500; letter-spacing: -0.03em; color: var(--text-muted);
}
.lead__text :deep(b) { color: var(--text); font-weight: 750; }
@media (max-width: 820px) { .lead { padding: 48px 18px 32px; } }
</style>
