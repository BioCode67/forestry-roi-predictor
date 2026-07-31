<script setup>
/**
 * 시군구 단위 단가 지도.
 * 임산물생산조사는 시·군 단위로 조사되므로, 시도 9개로 접지 않고 그대로 보여준다.
 * "우리 군이 전국에서 몇 번째인가"를 한눈에 알 수 있게 하는 것이 목적이다.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { echarts } from '../lib/charts'
import EChart from './EChart.vue'
import { fmt } from '../lib/api'
import { axisX, barH, baseOption, hGrad, palette, refLine, theme } from '../lib/charts'

const props = defineProps({
  stats: { type: Object, default: null },   // { 지역: [...], 전국단가, ... }
  item: String,
})

const registered = ref(false)

onMounted(async () => {
  try {
    const res = await fetch('/geo/sgg_merged.json')
    if (!res.ok) return
    echarts.registerMap('sgg', await res.json())
    registered.value = true
  } catch { /* 지도 파일이 없으면 지도만 빠지고 나머지는 그대로 쓴다 */ }
})

const option = computed(() => {
  if (!registered.value || !props.stats?.지역?.length) return null
  const t = theme()
  const rows = props.stats.지역
  const vals = rows.map((r) => r.단가)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const byName = Object.fromEntries(rows.map((r) => [r.지역, r]))

  return {
    ...baseOption({ legend: { show: false } }),
    tooltip: {
      trigger: 'item',
      backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12.5 },
      extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.12);border-radius:9px;',
      formatter: (p) => {
        const r = byName[p.name]
        if (!r) return `${p.name}<br/><span style="opacity:.6">조사 자료 없음</span>`
        return `<b>${r.지역}</b><br/>kg당 <b>${fmt.int(r.단가)}원</b>`
          + `<br/>전국 평균 대비 ${fmt.signed(r.전국대비_pct)}%`
          + `<br/>생산량 ${fmt.int(r.생산량 / 1000)}톤`
      },
    },
    visualMap: {
      min: lo, max: hi, calculable: true, orient: 'vertical',
      left: 10, bottom: 20, itemWidth: 12, itemHeight: 130,
      text: [`${fmt.int(hi)}원`, `${fmt.int(lo)}원`],
      textStyle: { color: t.subtle, fontSize: 11 },
      inRange: { color: ['#f3f6f2', '#a8cfb4', '#4a9d6b', '#235e3f', '#10281c'] },
    },
    series: [{
      type: 'map', map: 'sgg', roam: true, zoom: 1.15,
      itemStyle: { borderColor: t.surface, borderWidth: 0.6, areaColor: t.grid },
      emphasis: {
        label: { show: true, color: '#fff', fontSize: 11, fontWeight: 700 },
        itemStyle: { areaColor: '#d97706', borderColor: '#fff', borderWidth: 1.4 },
      },
      select: { disabled: true },
      data: rows.map((r) => ({ name: r.지역, value: r.단가 })),
    }],
  }
})

/* 상위·하위 지역 막대 — 지도만으로는 순위를 읽기 어렵다 */
const rankOption = computed(() => {
  const rows = props.stats?.지역
  if (!rows?.length) return null
  const t = theme()
  const top = rows.slice(0, 8)
  const bottom = rows.slice(-5)
  const merged = [...bottom].reverse().concat([...top].reverse())
  return baseOption({
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: {
      trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => `${p.name}<br/><b>${fmt.int(p.value)}원/kg</b>`,
    },
    xAxis: { type: 'value', axisLabel: { show: false }, splitLine: { show: false },
      axisLine: { show: false }, axisTick: { show: false } },
    yAxis: axisX({ data: merged.map((r) => r.지역),
      axisLabel: { color: t.muted, fontSize: 11 } }),
    series: [{
      type: 'bar', barWidth: '64%',
      data: merged.map((r, i) => ({
        value: r.단가,
        itemStyle: {
          color: i >= bottom.length ? hGrad(palette.forest, 0.62, 1)
                                    : hGrad(palette.grey, 0.3, 0.55),
          borderRadius: [0, 6, 6, 0],
        },
      })),
      label: { show: true, position: 'right', distance: 7,
        color: t.muted, fontSize: 10.5, fontWeight: 600,
        formatter: (p) => `${fmt.int(p.value)}원` },
      markLine: refLine(props.stats.전국단가, '전국 평균', { axis: 'x' }),
      animationDuration: 640, animationEasing: 'cubicOut',
      animationDelay: (i) => i * 34,
    }],
  })
})
</script>

<template>
  <div>
    <div v-if="!registered" class="note note--info fs-sm">지도를 불러오는 중입니다…</div>
    <div v-else class="grid grid--23">
      <EChart v-if="option" :option="option" height="520px" />
      <div class="stack stack--md">
        <p class="fs-sm muted">
          진한 색일수록 kg당 받는 값이 높은 지역입니다. 지도를 끌거나 확대할 수 있습니다.
        </p>
        <EChart v-if="rankOption" :option="rankOption" height="400px" />
        <p class="caveat">
          위 8곳이 높은 지역, 아래 5곳이 낮은 지역입니다.
          생산량이 아주 적은 시·군은 몇 kg 거래가 단가를 흔들어 제외했습니다
          (문턱 {{ fmt.int(stats?.['생산량_문턱_kg']) }}kg, {{ stats?.['문턱미달_제외'] }}곳 제외).
        </p>
      </div>
    </div>
  </div>
</template>
