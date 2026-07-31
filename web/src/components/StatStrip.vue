<script setup>
/**
 * 배너 바로 아래에 걸치는 요약 띠.
 * 사진에서 본문으로 넘어가는 구간이 비어 보이지 않게 하고,
 * 그 화면에서 볼 핵심 숫자를 먼저 알려준다.
 */
defineProps({ items: { type: Array, default: () => [] } })
</script>

<template>
  <div v-if="items.length" class="strip">
    <div class="strip__inner">
      <div v-for="(it, i) in items" :key="i" class="strip__cell">
        <p class="strip__label">{{ it.label }}</p>
        <p class="strip__value">{{ it.value }}<small v-if="it.unit">{{ it.unit }}</small></p>
        <p v-if="it.note" class="strip__note">{{ it.note }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strip {
  margin: -46px auto 30px;
  max-width: var(--maxw);
  position: relative; z-index: 2;
  padding: 0 30px;
}
.strip__inner {
  display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.strip__cell {
  padding: 20px 24px;
  border-left: 1px solid var(--border);
}
.strip__cell:first-child { border-left: 0; }
.strip__label {
  font-size: 0.75rem; font-weight: 600; color: var(--text-subtle);
  margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.strip__value {
  font-size: 1.5rem; font-weight: 780; letter-spacing: -0.038em;
  font-variant-numeric: tabular-nums; line-height: 1.1;
}
.strip__value small { font-size: 0.58em; font-weight: 640; color: var(--text-muted); margin-left: 2px; }
.strip__note { margin-top: 5px; font-size: 0.76rem; color: var(--text-muted); }

@media (max-width: 900px) {
  .strip { margin: -30px auto 22px; padding: 0 16px; }
  .strip__inner { grid-auto-flow: row; grid-auto-columns: auto; }
  .strip__cell { border-left: 0; border-top: 1px solid var(--border); }
  .strip__cell:first-child { border-top: 0; }
}
</style>
