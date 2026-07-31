/**
 * ECharts 공통 테마.
 * 라이트/다크 모두에서 대비를 유지하고, 격자·축을 최대한 눌러
 * 데이터 자체가 먼저 읽히도록 한다.
 */
import * as echarts from 'echarts/core'
import {
  BarChart, LineChart, ScatterChart, BoxplotChart, HeatmapChart, CustomChart, MapChart,
} from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
  MarkAreaComponent, DataZoomComponent, VisualMapComponent, TitleComponent,
  GraphicComponent, GeoComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, LineChart, ScatterChart, BoxplotChart, HeatmapChart, CustomChart, MapChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent,
  MarkAreaComponent, DataZoomComponent, VisualMapComponent, TitleComponent,
  GraphicComponent, GeoComponent, CanvasRenderer,
])

export { echarts }

export const isDark = () =>
  window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches

export const palette = {
  forest: '#2e7d4f',
  forestLight: '#7cbf95',
  forestDark: '#1c4a32',
  amber: '#d97706',
  sky: '#0284c7',
  rose: '#be123c',
  grey: '#94a3b8',
  series: ['#2e7d4f', '#d97706', '#0284c7', '#be123c', '#7c3aed', '#0f766e', '#a16207', '#4b5563'],
}

export function theme() {
  const dark = isDark()
  return {
    text: dark ? '#eaf0f2' : '#14181a',
    muted: dark ? '#a9b6bd' : '#4b565c',
    subtle: dark ? '#84939b' : '#6b767d',
    grid: dark ? '#253036' : '#e8edef',
    axis: dark ? '#33424a' : '#c2cacf',
    surface: dark ? '#141b1e' : '#ffffff',
    tooltipBg: dark ? 'rgba(20,27,30,.96)' : 'rgba(255,255,255,.98)',
    tooltipBorder: dark ? '#33424a' : '#dfe5e8',
  }
}

/** 모든 차트가 공유하는 기본 옵션 */
export function baseOption(over = {}) {
  const t = theme()
  return {
    textStyle: {
      fontFamily:
        'Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif',
      color: t.text,
    },
    grid: { left: 8, right: 14, top: 26, bottom: 8, containLabel: true, ...(over.grid || {}) },
    tooltip: {
      trigger: 'axis',
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      borderWidth: 1,
      padding: [9, 12],
      textStyle: { color: t.text, fontSize: 12.5 },
      extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.12);border-radius:9px;',
      axisPointer: { type: 'line', lineStyle: { color: t.axis, type: 'dashed' } },
      ...(over.tooltip || {}),
    },
    legend: {
      icon: 'roundRect', itemWidth: 10, itemHeight: 10, itemGap: 14,
      textStyle: { color: t.muted, fontSize: 12 },
      top: 0, right: 0,
      ...(over.legend || {}),
    },
    ...over,
  }
}

export function axisX(over = {}) {
  const t = theme()
  return {
    type: 'category',
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.subtle, fontSize: 11.5, margin: 10 },
    splitLine: { show: false },
    ...over,
  }
}

export function axisY(over = {}) {
  const t = theme()
  return {
    type: 'value',
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: t.subtle, fontSize: 11.5 },
    splitLine: { lineStyle: { color: t.grid, type: [4, 4] } },
    nameTextStyle: { color: t.subtle, fontSize: 11, padding: [0, 0, 6, 0] },
    ...over,
  }
}

/** 값에 따라 초록/붉은색을 고르는 막대 색 */
export const diverging = (v) => (v >= 0 ? palette.forest : palette.rose)

/* ==========================================================================
   차트 헬퍼
   막대·선을 매번 손으로 꾸미면 화면마다 미묘하게 달라진다. 여기 모아 두고
   전 차트가 같은 결을 갖게 한다.
   ========================================================================== */

/** 세로 막대용 그라디언트. 위가 진하고 아래로 옅어져 막대가 서 있는 느낌이 난다. */
export function vGrad(color, from = 1, to = 0.55) {
  return {
    type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
    colorStops: [
      { offset: 0, color: mix(color, from) },
      { offset: 1, color: mix(color, to) },
    ],
  }
}

/** 가로 막대용 그라디언트 (왼→오) */
export function hGrad(color, from = 0.6, to = 1) {
  return {
    type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
    colorStops: [
      { offset: 0, color: mix(color, from) },
      { offset: 1, color: mix(color, to) },
    ],
  }
}

/** hex 색의 불투명도를 조절한다 */
function mix(hex, alpha) {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255
  return `rgba(${r},${g},${b},${alpha})`
}
export { mix }

/** 선 그래프 아래에 깔 면적 그라디언트 */
export function areaGrad(color, top = 0.22) {
  return {
    type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
    colorStops: [
      { offset: 0, color: mix(color, top) },
      { offset: 1, color: mix(color, 0) },
    ],
  }
}

/**
 * 세로 막대 시리즈.
 * 강조할 항목 하나만 진하게 두고 나머지는 눌러, 답이 먼저 눈에 들어오게 한다.
 */
export function barV(values, { highlight = -1, color = palette.forest,
  muted = palette.grey, label, width = '52%', radius = 7 } = {}) {
  const t = theme()
  return {
    type: 'bar', barWidth: width,
    data: values.map((v, i) => ({
      value: v,
      itemStyle: {
        color: i === highlight ? vGrad(color) : vGrad(muted, 0.62, 0.34),
        borderRadius: [radius, radius, 0, 0],
      },
    })),
    label: label ? {
      show: true, position: 'top', distance: 6,
      color: t.muted, fontSize: 11.5, fontWeight: 650, formatter: label,
    } : { show: false },
    animationDuration: 620,
    animationEasing: 'cubicOut',
    animationDelay: (i) => i * 45,
  }
}

/** 가로 막대 시리즈 */
export function barH(values, { highlight = -1, color = palette.forest,
  muted = palette.grey, label, width = '62%', radius = 6 } = {}) {
  const t = theme()
  return {
    type: 'bar', barWidth: width,
    data: values.map((v, i) => ({
      value: v,
      itemStyle: {
        color: i === highlight ? hGrad(color) : hGrad(muted, 0.34, 0.6),
        borderRadius: [0, radius, radius, 0],
      },
    })),
    label: label ? {
      show: true, position: 'right', distance: 7,
      color: t.muted, fontSize: 11, fontWeight: 600, formatter: label,
    } : { show: false },
    animationDuration: 620,
    animationEasing: 'cubicOut',
    animationDelay: (i) => i * 40,
  }
}

/** 값 부호에 따라 초록/빨강이 갈리는 가로 막대 */
export function barDiverging(values, { label, width = '62%' } = {}) {
  const t = theme()
  return {
    type: 'bar', barWidth: width,
    data: values.map((v) => ({
      value: v,
      itemStyle: {
        color: v >= 0 ? hGrad(palette.forest, 0.62, 1) : hGrad(palette.rose, 1, 0.62),
        borderRadius: v >= 0 ? [0, 6, 6, 0] : [6, 0, 0, 6],
      },
    })),
    label: label ? {
      show: true, position: (v) => (v >= 0 ? 'right' : 'left'),
      color: t.muted, fontSize: 10.5, fontWeight: 600, formatter: label,
    } : { show: false },
    animationDuration: 620, animationEasing: 'cubicOut',
    animationDelay: (i) => i * 36,
  }
}

/** 면적이 깔린 부드러운 선 */
export function lineArea(data, { color = palette.forest, name, width = 3,
  area = true, dashed = false, yAxisIndex = 0 } = {}) {
  return {
    name, type: 'line', smooth: 0.28, symbol: 'none', yAxisIndex,
    data,
    lineStyle: { width, color, type: dashed ? 'dotted' : 'solid' },
    ...(area ? { areaStyle: { color: areaGrad(color) } } : {}),
    animationDuration: 800, animationEasing: 'cubicOut',
  }
}

/** 기준선 — '전국 평균' 같은 참조값을 눈에 띄지 않게 얹는다 */
export function refLine(value, text, { axis = 'y', color = palette.amber } = {}) {
  return {
    symbol: 'none', silent: true,
    lineStyle: { color, type: 'dashed', width: 1.5, opacity: 0.85 },
    label: {
      formatter: text, color, fontSize: 10.5, fontWeight: 650,
      position: axis === 'y' ? 'insideEndTop' : 'insideMiddleTop',
      backgroundColor: 'rgba(255,255,255,.82)', padding: [2, 5], borderRadius: 4,
    },
    data: [axis === 'y' ? { yAxis: value } : { xAxis: value }],
  }
}

/** 공통 툴팁 — 화면마다 다시 쓰지 않도록 한다 */
export function tip(formatter, trigger = 'axis') {
  const t = theme()
  return {
    trigger,
    backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
    padding: [10, 13],
    textStyle: { color: t.text, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 10px 30px rgba(0,0,0,.14);border-radius:10px;',
    axisPointer: {
      type: trigger === 'axis' ? 'shadow' : 'line',
      shadowStyle: { color: 'rgba(46,125,79,.07)' },
    },
    formatter,
  }
}
