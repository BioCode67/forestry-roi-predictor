<script setup>
defineProps({ title: String, desc: String, badge: String, badgeKind: { type: String, default: 'grey' } })
</script>

<template>
  <div class="section__head">
    <div style="flex:1;min-width:0">
      <div class="row">
        <h2>{{ title }}</h2>
        <span v-if="badge" class="badge" :class="`badge--${badgeKind}`">{{ badge }}</span>
      </div>
      <p v-if="desc" class="section__desc">{{ desc }}</p>
    </div>
    <slot name="actions" />
  </div>
</template>
