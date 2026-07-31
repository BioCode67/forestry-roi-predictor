<script setup>
defineProps({
  label: String,
  value: [String, Number],
  unit: String,
  delta: String,
  deltaDir: { type: String, default: 'flat' }, // up | down | flat
  accent: Boolean,
  hint: String,
})
</script>

<template>
  <div class="metric" :class="{ 'metric--accent': accent }">
    <div class="metric__label">
      {{ label }}
      <span v-if="hint" class="subtle" :title="hint" style="cursor:help">ⓘ</span>
    </div>
    <div class="metric__value">
      {{ value }}<small v-if="unit"> {{ unit }}</small>
    </div>
    <div v-if="delta" class="metric__delta" :class="deltaDir">{{ delta }}</div>
  </div>
</template>
