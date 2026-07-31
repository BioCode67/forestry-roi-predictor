<script setup>
import { computed, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import PageHero from '../components/PageHero.vue'
import StatStrip from '../components/StatStrip.vue'
import RegionMap from '../components/RegionMap.vue'
import PageHead from '../components/PageHead.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { areaGrad, axisX, axisY, barDiverging, barH, baseOption, lineArea,
  palette, refLine, theme, tip, vGrad } from '../lib/charts'

const prod = ref(null)
const loading = ref(true)
const error = ref('')
const picked = ref('밤')

const region = ref(null)
api.region().then((d) => { region.value = d }).catch(() => {})

api.production()
  .then((d) => { prod.value = d })
  .catch((e) => { error.value = e.message })
  .finally(() => { loading.value = false })

const items = computed(() => {
  if (!prod.value) return []
  return Object.keys(prod.value.단가추이).filter((k) => prod.value.지역단가프리미엄[k])
})
watch(items, (l) => { if (l.length && !l.includes(picked.value)) picked.value = l[0] })

const strip = computed(() => {
  if (!prod.value) return []
  const t = prod.value.단가추이, p2 = prod.value.지역단가프리미엄
  const rise = Object.entries(t).filter(([k]) => p2[k])
    .sort((a, b) => b[1].단가_변화율_pct - a[1].단가_변화율_pct)[0]
  const gap = Object.entries(p2).sort((a, b) => b[1].지역격차_배 - a[1].지역격차_배)[0]
  return [
    { label: '조사 기간', value: `${prod.value.연도[0]}~${prod.value.연도.at(-1)}`, note: '전국 시·군 실측' },
    { label: '조사 건수', value: fmt.int(prod.value.관측), unit: '건', note: `${prod.value.품목수}개 품목` },
    rise && { label: '값이 가장 많이 오른 작물', value: rise[0],
      unit: ` ${fmt.signed(rise[1].단가_변화율_pct, 0)}%`, note: '첫 해 대비' },
    gap && { label: '지역 차이가 가장 큰 작물', value: gap[0],
      unit: ` ${fmt.dec(gap[1].지역격차_배, 1)}배`, note: `${gap[1].최고지역} vs ${gap[1].최저지역}` },
  ].filter(Boolean)
})

const trend = computed(() => prod.value?.단가추이?.[picked.value])
const prem = computed(() => prod.value?.지역단가프리미엄?.[picked.value])
const spec = computed(() => prod.value?.지역특화도_LQ?.[picked.value])
const last = computed(() => trend.value?.연도별?.at(-1))

const trendOption = computed(() => {
  if (!trend.value) return null
  const t = theme()
  const d = trend.value.연도별
  return baseOption({
    grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },
    legend: { data: ['kg당 값', '생산량'] },
    tooltip: {
      trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => {
        const r = d[ps[0].dataIndex]
        return `<b>${r.연도}년</b><br/>kg당 <b>${fmt.int(r.가중평균단가)}원</b>` +
          `<br/>생산량 ${fmt.int(r.생산량 / 1000)}톤<br/>생산금액 ${fmt.won(r.생산금액)}` +
          `<br/>생산 시군구 ${r.시군구수}곳`
      },
    },
    xAxis: axisX({ data: d.map((r) => `${r.연도}`) }),
    yAxis: [
      axisY({ name: 'kg당 원', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.int(v) } }),
      axisY({ name: '톤', position: 'right', splitLine: { show: false },
        axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.int(v) } }),
    ],
    series: [
      { name: '생산량', type: 'bar', yAxisIndex: 1, barWidth: '42%',
        data: d.map((r) => r.생산량 / 1000),
        itemStyle: { color: vGrad(palette.grey, 0.5, 0.22), borderRadius: [7, 7, 0, 0] },
        animationDuration: 620 },
      { name: 'kg당 값', type: 'line', smooth: 0.28, symbolSize: 11,
        data: d.map((r) => r.가중평균단가),
        lineStyle: { width: 3.4, color: palette.forest,
          shadowColor: 'rgba(46,125,79,.3)', shadowBlur: 10, shadowOffsetY: 3 },
        itemStyle: { color: '#fff', borderColor: palette.forest, borderWidth: 3 },
        areaStyle: { color: areaGrad(palette.forest, 0.14) },
        animationDuration: 900 },
    ],
  })
})

const premOption = computed(() => {
  if (!prem.value) return null
  const t = theme()
  const rows = [...prem.value.지역].reverse()
  return baseOption({
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    legend: { show: false },
    tooltip: { trigger: 'item', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (p) => {
        const r = rows[p.dataIndex]
        return `<b>${r.시도}</b><br/>kg당 ${fmt.int(r.가중평균단가)}원<br/>전국 대비 ${
          fmt.signed(r.전국대비_pct)}%<br/>생산량 ${fmt.int(r.생산량 / 1000)}톤`
      } },
    xAxis: axisY({ axisLabel: { color: t.subtle, fontSize: 11, formatter: '{value}%' } }),
    yAxis: axisX({ data: rows.map((r) => r.시도), axisLabel: { color: t.muted, fontSize: 11.5 } }),
    series: [barDiverging(rows.map((r) => r.전국대비_pct),
      { label: (p) => `${fmt.signed(p.value, 0)}%` })],
  })
})

const allTrendOption = computed(() => {
  if (!prod.value) return null
  const t = theme()
  const rows = Object.entries(prod.value.단가추이)
    .filter(([k]) => items.value.includes(k))
    .map(([k, v]) => ({ item: k, chg: v.단가_변화율_pct, prod: v.생산량_변화율_pct ?? 0 }))
    .sort((a, b) => a.chg - b.chg)
  return baseOption({
    grid: { left: 8, right: 52, top: 30, bottom: 8, containLabel: true },
    legend: {
      data: [
        { name: '값 변화 (초록 오름 / 빨강 내림)', itemStyle: { color: palette.forest } },
        { name: '생산량 변화', itemStyle: { color: palette.grey } },
      ],
    },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} ${fmt.signed(p.value)}%`).join('<br/>') },
    xAxis: axisY({ axisLabel: { color: t.subtle, fontSize: 11, formatter: '{value}%' } }),
    yAxis: axisX({ data: rows.map((r) => r.item), axisLabel: { color: t.muted, fontSize: 11.5 } }),
    series: [
      { ...barDiverging(rows.map((r) => r.chg), { label: (p) => `${fmt.signed(p.value, 0)}%`, width: '36%' }),
        name: '값 변화 (초록 오름 / 빨강 내림)' },
      { name: '생산량 변화', type: 'bar', barWidth: '36%',
        data: rows.map((r) => ({
          value: r.prod,
          itemStyle: { color: 'rgba(148,163,184,.45)',
            borderRadius: r.prod >= 0 ? [0, 5, 5, 0] : [5, 0, 0, 5] },
        })), animationDuration: 620 },
    ],
  })
})
</script>

<template>
  <div>
    <PageHero
      src="/img/mountain.jpg"
      eyebrow="시장·단가"
      title="내 작물은 kg당 얼마 받나요"
      lead="전국 시·군마다 실제로 얼마에 팔렸는지 조사한 자료입니다. 같은 작물이라도 지역마다 받는 값이 꽤 다릅니다."
    />

    <StatStrip :items="strip" />

  <main class="content" style="padding-top:6px">
    <div class="container">

      <DataState :loading="loading" :error="error">
        <template v-if="prod">
          <div class="chips" style="margin-bottom:16px">
            <button v-for="i in items" :key="i" class="chip"
                    :class="{ 'chip--active': picked === i }" @click="picked = i">{{ i }}</button>
          </div>

          <div v-if="last" class="grid grid--4">
            <MetricCard accent :label="`${last.연도}년 전국 평균값`"
              :value="fmt.int(last.가중평균단가)" unit="원/kg"
              :delta="`${fmt.signed(trend.단가_변화율_pct)}% (${prod.연도[0]}년 대비)`"
              :delta-dir="trend.단가_변화율_pct >= 0 ? 'up' : 'down'" />
            <MetricCard label="전국 생산량 변화" :value="fmt.signed(trend.생산량_변화율_pct)" unit="%"
              :delta-dir="trend.생산량_변화율_pct >= 0 ? 'up' : 'down'"
              :delta="`${fmt.int(last.생산량 / 1000)}톤`" />
            <MetricCard label="전국에서 팔린 금액" :value="fmt.won(last.생산금액)"
              :delta="`생산 시군구 ${last.시군구수}곳`" delta-dir="flat" />
            <MetricCard v-if="prem" label="지역별 값 차이"
              :value="fmt.dec(prem.지역격차_배, 2)" unit="배"
              :delta="`${prem.최고지역} ${fmt.int(prem.최고단가)}원 vs ${prem.최저지역} ${fmt.int(prem.최저단가)}원`"
              delta-dir="flat" />
          </div>

          <div class="grid grid--2 mt-lg">
            <div class="card">
              <div class="card__head"><h3>몇 해 동안 값이 어떻게 변했나요</h3></div>
              <div class="card__body"><EChart v-if="trendOption" :option="trendOption" height="300px" /></div>
            </div>
            <div class="card">
              <div class="card__head">
                <h3>어느 지역이 값을 더 받나요</h3>
                <span v-if="prem" class="badge badge--grey">{{ prem.연도 }}년</span>
              </div>
              <div class="card__body">
                <EChart v-if="premOption" :option="premOption" height="300px" />
                <p v-if="prem" class="caveat mt-sm">
                  전국 평균 {{ fmt.int(prem.전국_가중평균단가) }}원/kg을 기준으로, 얼마나 높고 낮은지입니다.
                  값이 높은 지역은 품종·등급 구성이나 파는 곳이 다를 수 있습니다.
                </p>
              </div>
            </div>
          </div>

          <div v-if="region?.통계?.[picked]" class="card mt-lg">
            <div class="card__head">
              <h3>{{ picked }} — 전국 시·군 지도</h3>
              <span class="badge badge--green">
                {{ region.통계[picked].지역수 }}개 시·군 · {{ region.통계[picked].연도 }}년
              </span>
            </div>
            <div class="card__body">
              <p class="fs-sm muted" style="margin-bottom:12px">
                같은 {{ picked }}인데 시·군에 따라 kg당 받는 값이
                <b>{{ fmt.dec(region.통계[picked].격차_배, 1) }}배</b> 차이납니다
                ({{ region.통계[picked].최고.지역 }} {{ fmt.int(region.통계[picked].최고.단가) }}원 ·
                {{ region.통계[picked].최저.지역 }} {{ fmt.int(region.통계[picked].최저.단가) }}원).
              </p>
              <RegionMap :stats="region.통계[picked]" :item="picked" />
            </div>
          </div>

          <div v-if="spec" class="card mt-lg">
            <div class="card__head">
              <h3>{{ picked }}은 어디가 주산지인가요</h3>
              <span class="badge badge--sky">{{ spec.연도 }}년</span>
            </div>
            <div class="card__body">
              <p class="fs-sm muted" style="margin-bottom:10px">
                숫자가 클수록 그 지역이 이 작물에 집중하고 있다는 뜻입니다. 1이면 전국 평균 수준,
                2면 평균의 두 배로 집중된 주산지입니다.
              </p>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>지역</th><th class="num">집중도</th><th class="num">팔린 금액</th><th class="num">전국에서 차지하는 몫</th></tr></thead>
                  <tbody>
                    <tr v-for="(r, i) in spec.상위지역" :key="r.시도" :class="{ 'strong-row': i === 0 }">
                      <td>{{ r.시도 }}</td>
                      <td class="num">{{ fmt.dec(r.LQ, 2) }}</td>
                      <td class="num">{{ fmt.won(r.생산금액) }}</td>
                      <td class="num">{{ fmt.dec(r.전국비중_pct) }}%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div class="card mt-lg">
            <div class="card__head"><h3>다른 작물들은 어떤가요</h3></div>
            <div class="card__body">
              <EChart v-if="allTrendOption" :option="allTrendOption" height="400px" />
              <p class="caveat mt-sm">
                대부분 작물에서 생산량은 줄고 값은 오르는 흐름입니다. 기르는 사람이 줄어드는 만큼
                값이 받쳐주고 있다는 뜻이기도 합니다.
              </p>
            </div>
          </div>

          <div v-if="prod.가공부가가치 && Object.keys(prod.가공부가가치).length" class="section mt-lg">
            <SectionHead title="말리거나 가공하면 이득일까요" />
            <div v-for="(v, k) in prod.가공부가가치" :key="k" class="card">
              <div class="card__head">
                <h3>{{ k }}</h3>
                <span class="badge" :class="v.판정 === '가공이 유리' ? 'badge--green' : 'badge--amber'">
                  {{ v.판정 }}
                </span>
              </div>
              <div class="card__body">
                <div class="grid grid--4" style="gap:10px">
                  <MetricCard label="그대로 팔 때" :value="fmt.int(v.원물_단가)" unit="원/kg" />
                  <MetricCard label="가공해서 팔 때" :value="fmt.int(v.가공품_단가)" unit="원/kg" />
                  <MetricCard label="값이 몇 배 되나" :value="fmt.dec(v.단가_배수, 2)" unit="배" />
                  <MetricCard label="몇 배는 돼야 이득" :value="fmt.dec(v.손익분기_배수, 1)" unit="배"
                    accent :delta="`말리면 무게가 ${Math.round(1/v.건조수율)}분의 1로 줄어듭니다`" delta-dir="flat" />
                </div>
                <div class="note mt-md"
                     :class="v.판정 === '가공이 유리' ? 'note--good' : 'note--warn'">
                  {{ v.해석 }} 그대로 1kg을 팔면 {{ fmt.int(v.원물_단가) }}원인데,
                  같은 1kg을 가공해 팔면 <b>{{ fmt.int(v.원물1kg당_가공수취액) }}원</b>이 됩니다.
                  <b>{{ fmt.signed(v.원물직판대비_pct) }}%</b> 차이입니다.
                </div>
                <p class="caveat mt-sm">{{ v.주의 }}</p>
              </div>
            </div>
          </div>

          <div class="card mt-lg">
            <div class="card__head"><h3>이 숫자를 볼 때 참고하실 점</h3></div>
            <div class="card__body">
              <p class="fs-sm muted">{{ prod.주의 }}</p>
              <p class="fs-sm muted mt-sm">
                값은 시·군을 그냥 평균 낸 것이 아니라 <b>팔린 금액을 판 무게로 나눠</b> 구했습니다.
                생산량이 아주 적은 지역의 특이한 값이 전국 평균을 흔들지 않도록 하기 위해서입니다.
              </p>
            </div>
          </div>
        </template>
      </DataState>
    </div>
  </main>
  </div>
</template>
