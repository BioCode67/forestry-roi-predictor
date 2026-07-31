<script setup>
import { computed, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const ins = ref(null)
const loading = ref(true)
const error = ref('')
const gradeItem = ref('밤')
const leaderItem = ref('밤')

api.insights()
  .then((d) => { ins.value = d })
  .catch((e) => { error.value = e.message })
  .finally(() => { loading.value = false })

const gradeItems = computed(() => Object.keys(ins.value?.등급별_단가 || {}))
const leaderItems = computed(() => Object.keys(ins.value?.선도임가_격차 || {}))
watch(gradeItems, (l) => { if (l.length && !l.includes(gradeItem.value)) gradeItem.value = l[0] })
watch(leaderItems, (l) => { if (l.length && !l.includes(leaderItem.value)) leaderItem.value = l[0] })

const grade = computed(() => ins.value?.등급별_단가?.[gradeItem.value])
const sim = computed(() => ins.value?.등급전환_시뮬레이션?.[gradeItem.value])
const leader = computed(() => ins.value?.선도임가_격차?.[leaderItem.value])

const gradeOption = computed(() => {
  if (!grade.value) return null
  const t = theme()
  const rows = grade.value.등급
  const vals = rows.map((r) => r.단가_원per단위수량)
  const hi = vals.indexOf(Math.max(...vals))
  return baseOption({
    grid: { left: 8, right: 14, top: 30, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => {
        const r = rows[ps[0].dataIndex]
        return `<b>${r.구분}</b><br/>단가 <b>${fmt.int(r.단가_원per단위수량)}원</b>` +
          `<br/>생산 임가 비율 ${fmt.dec(r.생산임가_비율_pct, 0)}%` +
          (r.생산임가내_물량비중_pct != null
            ? `<br/>생산 임가 내 물량비중 ${fmt.dec(r.생산임가내_물량비중_pct, 0)}%` : '')
      } },
    xAxis: axisX({ data: rows.map((r) => r.구분) }),
    yAxis: axisY({ name: '원 / 수량단위', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: (v) => fmt.int(v) } }),
    series: [{
      type: 'bar', barWidth: '50%',
      data: vals.map((v, i) => ({ value: v,
        itemStyle: { color: i === hi ? palette.forest : palette.grey,
          borderRadius: [5, 5, 0, 0], opacity: i === hi ? 1 : 0.7 } })),
      label: { show: true, position: 'top', color: t.muted, fontSize: 11,
        formatter: (p) => `${fmt.int(p.value)}원` },
    }],
  })
})

const ageOption = computed(() => {
  const a = ins.value?.수령별_수익성
  if (!a) return null
  const t = theme()
  const keys = Object.keys(a)
  const cats = a[keys[0]].구간.map((r) => r.수령구간)
  return baseOption({
    grid: { left: 8, right: 14, top: 32, bottom: 8, containLabel: true },
    legend: { data: keys },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} ${fmt.dec(p.value)}%`).join('<br/>') },
    xAxis: axisX({ data: cats }),
    yAxis: axisY({ name: 'ROI 중앙값 (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: '{value}%' } }),
    series: keys.map((k, i) => ({
      name: k, type: 'line', smooth: 0.2, symbolSize: 8,
      data: cats.map((c) => a[k].구간.find((r) => r.수령구간 === c)?.ROI중앙값 ?? null),
      lineStyle: { width: 2.8, color: palette.series[i] },
      itemStyle: { color: palette.series[i] },
    })).concat([{
      type: 'line', name: '', silent: true, symbol: 'none', data: cats.map(() => 0),
      lineStyle: { color: t.axis, type: 'dashed', width: 1 }, tooltip: { show: false },
    }]),
  })
})

const leaderOption = computed(() => {
  if (!leader.value) return null
  const t = theme()
  const labels = ['노동비', '비료비', '농약비', '감가상각비', '위탁영농비']
  const lead = labels.map((x) => leader.value.선도임가[`${x}_비중pct`] ?? null)
  const rest = labels.map((x) => leader.value.이외임가[`${x}_비중pct`] ?? null)
  return baseOption({
    grid: { left: 8, right: 14, top: 32, bottom: 8, containLabel: true },
    legend: { data: ['선도임가', '이외임가'] },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} ${fmt.dec(p.value)}%`).join('<br/>') },
    xAxis: axisX({ data: labels }),
    yAxis: axisY({ name: '경영비 대비 비중 (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: '{value}%' } }),
    series: [
      { name: '선도임가', type: 'bar', barWidth: '32%', data: lead,
        itemStyle: { color: palette.forest, borderRadius: [4, 4, 0, 0] } },
      { name: '이외임가', type: 'bar', barWidth: '32%', data: rest,
        itemStyle: { color: palette.grey, opacity: 0.72, borderRadius: [4, 4, 0, 0] } },
    ],
  })
})

const regionOption = computed(() => {
  const m = ins.value?.['지역x품목']?.matrix
  if (!m) return null
  const t = theme()
  const items = Object.keys(m)
  const regions = [...new Set(items.flatMap((i) => Object.keys(m[i])))]
  const data = []
  let min = Infinity, max = -Infinity
  regions.forEach((r, ri) => items.forEach((it, ii) => {
    const v = m[it][r]
    if (v == null) return
    data.push([ii, ri, v])
    min = Math.min(min, v); max = Math.max(max, v)
  }))
  return baseOption({
    grid: { left: 8, right: 14, top: 12, bottom: 56, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => `${regions[p.value[1]]} · ${items[p.value[0]]}<br/>ROI <b>${fmt.dec(p.value[2])}%</b>` },
    xAxis: axisX({ data: items, splitArea: { show: true } }),
    yAxis: axisX({ type: 'category', data: regions, splitArea: { show: true } }),
    visualMap: {
      min, max, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: ['#be123c', '#f5f5f4', '#2e7d4f'] },
      textStyle: { color: t.subtle, fontSize: 11 }, itemWidth: 12, itemHeight: 90,
    },
    series: [{
      type: 'heatmap', data,
      label: { show: true, fontSize: 10.5, color: '#111',
        formatter: (p) => fmt.dec(p.value[2], 0) },
      itemStyle: { borderColor: t.surface, borderWidth: 1.5 },
    }],
  })
})
</script>

<template>
  <main class="content">
    <div class="container">
      <SectionHead
        title="수익 개선 인사이트"
        desc="예측 모델이 '얼마를 벌 수 있는가'에 답한다면, 이 화면은 '어떻게 하면 더 벌 수 있는가'에 대한 정량 근거입니다. 기술통계 계층이며 예측 모델의 설명변수로는 쓰지 않습니다."
        badge="임산물생산비조사" badge-kind="green"
      />

      <DataState :loading="loading" :error="error">
        <template v-if="ins">
          <!-- ① 등급 단가 -->
          <div class="card">
            <div class="card__head"><h3>품질 등급 · 가공 형태별 단가</h3></div>
            <div class="card__body">
              <div class="chips" style="margin-bottom:14px">
                <button v-for="i in gradeItems" :key="i" class="chip"
                        :class="{ 'chip--active': gradeItem === i }" @click="gradeItem = i">{{ i }}</button>
              </div>
              <div class="grid grid--32">
                <EChart v-if="gradeOption" :option="gradeOption" height="300px" />
                <div class="stack stack--md">
                  <MetricCard v-if="grade?.직접비교_가능" accent label="최고 / 최저 단가 배수"
                    :value="fmt.dec(grade.최고_최저_단가배수, 2)" unit="배" />
                  <div class="table-wrap">
                    <table>
                      <thead><tr><th>{{ grade?.종류 }}</th><th class="num">단가</th><th class="num">생산 임가</th></tr></thead>
                      <tbody>
                        <tr v-for="r in grade?.등급" :key="r.구분">
                          <td>{{ r.구분 }}</td>
                          <td class="num">{{ fmt.int(r.단가_원per단위수량) }}원</td>
                          <td class="num">{{ fmt.dec(r.생산임가_비율_pct, 0) }}%</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p class="caveat">{{ grade?.주석 }}</p>
                </div>
              </div>
              <div v-if="sim" class="note note--good mt-md">
                <strong>품질 개선 효과</strong> — {{ sim.전환_시나리오 }} 시 단위면적당 수취액
                <b>{{ fmt.signed(sim.수취액_증가_원per단위면적, 0) === '—' ? '—'
                  : (sim.수취액_증가_원per단위면적 >= 0 ? '+' : '') + fmt.wonFull(sim.수취액_증가_원per단위면적) }}</b>
                증가 (등급 간 단가차 {{ fmt.int(sim.단가차_원) }}원 × 전환 물량).
                <div class="fs-sm mt-sm">{{ sim.가정 }}</div>
              </div>
            </div>
          </div>

          <!-- ② 수령 -->
          <div class="card mt-lg">
            <div class="card__head">
              <h3>수령(樹齡)별 수익성 곡선</h3>
              <span class="badge badge--amber">갱신·개식 판단</span>
            </div>
            <div class="card__body">
              <EChart v-if="ageOption" :option="ageOption" height="330px" />
              <div class="grid grid--3 mt-md" style="gap:10px">
                <MetricCard v-for="(v, k) in ins.수령별_수익성" :key="k"
                  :label="`${k} 최고 수익 구간`" :value="v.최고구간"
                  :delta="`${fmt.dec(v.최고ROI, 0)}% · 최저 ${v.최저구간} ${fmt.dec(v.최저ROI, 0)}%`"
                  delta-dir="up" />
              </div>
              <p class="caveat mt-sm">
                수익성이 정점을 지나 하락하는 구간은 갱신·개식 또는 수형 개선을 검토할 시점을 시사합니다.
              </p>
            </div>
          </div>

          <!-- ③ 선도임가 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>선도임가 벤치마크 — 비목 구조의 차이</h3></div>
            <div class="card__body">
              <div class="chips" style="margin-bottom:14px">
                <button v-for="i in leaderItems" :key="i" class="chip"
                        :class="{ 'chip--active': leaderItem === i }" @click="leaderItem = i">{{ i }}</button>
              </div>
              <div class="grid grid--32">
                <EChart v-if="leaderOption" :option="leaderOption" height="290px" />
                <div class="stack stack--md">
                  <div class="grid grid--2" style="gap:10px">
                    <MetricCard label="선도임가 ROI"
                      :value="fmt.dec(leader?.선도임가?.ROI중앙값, 0)" unit="%" accent
                      :delta="`표본 ${fmt.int(leader?.표본?.선도임가)}호`" delta-dir="flat" />
                    <MetricCard label="이외임가 ROI"
                      :value="fmt.dec(leader?.이외임가?.ROI중앙값, 0)" unit="%"
                      :delta="`표본 ${fmt.int(leader?.표본?.이외임가)}호`" delta-dir="flat" />
                  </div>
                  <MetricCard label="총 노동시간 (선도 / 이외)"
                    :value="`${fmt.int(leader?.선도임가?.총노동시간)} / ${fmt.int(leader?.이외임가?.총노동시간)}`"
                    unit="시간" />
                </div>
              </div>
              <div v-if="leader?.해석_유의" class="note note--warn mt-md fs-sm">
                <strong>해석 유의</strong> — {{ leader.해석_유의 }}
              </div>
            </div>
          </div>

          <!-- ④ 지역×품목 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>지역 × 품목 수익성 지도</h3></div>
            <div class="card__body">
              <EChart v-if="regionOption" :option="regionOption" height="420px" />
              <p class="caveat mt-sm">표본 15건 이상인 조합만 표시합니다.</p>
            </div>
          </div>

          <div class="note note--info mt-lg fs-sm">{{ ins.note }}</div>
        </template>
      </DataState>
    </div>
  </main>
</template>
