<script setup>
/** 결과를 한 문장으로 먼저 말해주는 큰 카드. 숫자보다 말이 먼저 읽히도록 한다. */
defineProps({ tone: { type: String, default: 'neutral' } })
</script>

<template>
  <div class="answer" :class="`answer--${tone}`">
    <div class="answer__body"><slot /></div>
    <div v-if="$slots.sub" class="answer__sub"><slot name="sub" /></div>
  </div>
</template>

<style scoped>
.answer {
  border-radius: var(--r-xl); padding: 26px 30px;
  background: linear-gradient(135deg, var(--forest-600), var(--forest-800));
  color: #fff; box-shadow: var(--shadow-lg);
}
.answer--warn { background: linear-gradient(135deg, #b45309, #7c2d12); }
.answer--flat { background: linear-gradient(135deg, #475569, #1e293b); }
.answer__body { font-size: 1.42rem; font-weight: 650; line-height: 1.5; letter-spacing: -0.02em; }
.answer__body :deep(b), .answer__body :deep(strong) {
  font-size: 1.34em; font-weight: 800; letter-spacing: -0.03em;
}
.answer__sub {
  margin-top: 14px; padding-top: 14px;
  border-top: 1px solid rgba(255,255,255,.22);
  font-size: 0.93rem; line-height: 1.6; opacity: .93; font-weight: 450;
}
@media (max-width: 720px) {
  .answer { padding: 20px 20px; }
  .answer__body { font-size: 1.14rem; }
}
</style>
