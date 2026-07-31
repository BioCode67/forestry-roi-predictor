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
