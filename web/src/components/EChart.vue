<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { echarts } from '../lib/charts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '300px' },
  /** 옵션 교체 시 이전 시리즈를 지울지 여부 */
  replace: { type: Boolean, default: true },
})

const el = ref(null)
const chart = shallowRef(null)
let ro = null
let mq = null

function render() {
  if (!chart.value || !props.option) return
  chart.value.setOption(props.option, props.replace)
}

function rebuild() {
  if (chart.value) chart.value.dispose()
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
}

onMounted(() => {
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  render()

  ro = new ResizeObserver(() => chart.value && chart.value.resize())
  ro.observe(el.value)

  // 시스템 테마가 바뀌면 색을 다시 계산해야 하므로 통째로 다시 그린다
  if (window.matchMedia) {
    mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener?.('change', rebuild)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
  mq?.removeEventListener?.('change', rebuild)
  chart.value?.dispose()
})

watch(() => props.option, render, { deep: true })
</script>

<template>
  <div ref="el" class="chart" :style="{ height }" />
</template>
