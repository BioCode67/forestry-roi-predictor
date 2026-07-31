<script setup>
/** 어려운 용어에 붙는 도움말. 평소엔 쉬운 말만 보이고, 눌러야 정식 명칭이 나온다. */
import { ref } from 'vue'
import { TERMS } from '../lib/terms'

const props = defineProps({ k: String, label: String })
const open = ref(false)
const t = TERMS[props.k] || {}
</script>

<template>
  <span class="term">
    <button class="term__btn" @click="open = !open" :aria-expanded="open">
      {{ label || t.easy || k }}<span class="term__mark">?</span>
    </button>
    <span v-if="open" class="term__pop" @click="open = false">
      <b>{{ t.easy }}</b>
      <span class="term__desc">{{ t.desc }}</span>
      <span v-if="t.formal" class="term__formal">통계 용어: {{ t.formal }}</span>
    </span>
  </span>
</template>

<style scoped>
.term { position: relative; display: inline; }
.term__btn {
  border: 0; background: none; padding: 0; color: inherit; font: inherit;
  border-bottom: 1px dashed var(--border-strong); cursor: help;
}
.term__mark {
  font-size: 0.68em; vertical-align: super; margin-left: 1px;
  color: var(--forest-500); font-weight: 700;
}
.term__pop {
  position: absolute; left: 0; top: calc(100% + 7px); z-index: 80;
  width: 290px; padding: 12px 14px;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--r-md); box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column; gap: 6px;
  font-size: 0.83rem; line-height: 1.55; font-weight: 400;
  color: var(--text); cursor: pointer; text-align: left;
}
.term__desc { color: var(--text-muted); }
.term__formal { color: var(--text-subtle); font-size: 0.76rem; padding-top: 5px; border-top: 1px solid var(--border); }
</style>
