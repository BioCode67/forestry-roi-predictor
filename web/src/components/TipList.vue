<script setup>
/** 실행 가능한 제안 목록. 분석 결과가 아니라 '이렇게 하세요'를 말한다. */
defineProps({ tips: { type: Array, default: () => [] } })
</script>

<template>
  <ul v-if="tips.length" class="tips">
    <li v-for="(t, i) in tips" :key="i" class="tip" :class="`tip--${t.tone || 'good'}`">
      <span class="tip__icon" aria-hidden="true"></span>
      <span class="tip__text">
        <b>{{ t.title }}</b>
        <span class="tip__desc">{{ t.desc }}</span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.tips { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.tip {
  display: flex; gap: 12px; align-items: flex-start;
  padding: 14px 16px; border-radius: var(--r-md);
  background: var(--surface); border: 1px solid var(--border);
  border-left: 3px solid var(--forest-500);
}
.tip--warn { border-left-color: var(--amber-500); }
.tip--info { border-left-color: var(--sky-500); }
.tip__icon {
  flex: none; width: 8px; height: 8px; border-radius: 50%;
  margin-top: 7px; background: var(--forest-500);
}
.tip--warn .tip__icon { background: var(--amber-500); }
.tip--info .tip__icon { background: var(--sky-500); }
.tip__text { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tip__text b { font-size: 0.95rem; font-weight: 680; }
.tip__desc { font-size: 0.875rem; color: var(--text-muted); line-height: 1.6; }
</style>
