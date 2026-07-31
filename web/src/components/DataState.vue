<script setup>
defineProps({ loading: Boolean, error: String, empty: Boolean, emptyText: String })
</script>

<template>
  <div v-if="loading" class="stack stack--sm" style="padding:8px 0">
    <div class="skeleton" style="height:15px;width:38%"></div>
    <div class="skeleton" style="height:210px"></div>
  </div>
  <div v-else-if="error" class="note note--danger">
    <strong>불러오지 못했습니다.</strong> {{ error }}
  </div>
  <div v-else-if="empty" class="note note--info">
    {{ emptyText || '표시할 데이터가 없습니다.' }}
  </div>
  <slot v-else />
</template>
