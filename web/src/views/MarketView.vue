<script setup>
import { computed, ref, watch } from 'vue'
import EChart from '../components/EChart.vue'
import MetricCard from '../components/MetricCard.vue'
import SectionHead from '../components/SectionHead.vue'
import DataState from '../components/DataState.vue'
import { api, fmt } from '../lib/api'
import { axisX, axisY, baseOption, palette, theme } from '../lib/charts'

const prod = ref(null)
const loading = ref(true)
const error = ref('')
const picked = ref('밤')

api.production()
  .then((d) => { prod.value = d })
  .catch((e) => { error.value = e.message })
  .finally(() => { loading.value = false })

const items = computed(() => {
  if (!prod.value) return []
  return Object.keys(prod.value.단가추이).filter((k) => prod.value.지역단가프리미엄[k])
})
watch(items, (l) => { if (l.length && !l.includes(picked.value)) picked.value = l[0] })

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
    legend: { data: ['물량가중 단가', '생산량'] },
    tooltip: {
      trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => {
        const r = d[ps[0].dataIndex]
        return `<b>${r.연도}년</b><br/>단가 <b>${fmt.int(r.가중평균단가)}원/kg</b>` +
          `<br/>생산량 ${fmt.int(r.생산량 / 1000)}톤<br/>생산금액 ${fmt.won(r.생산금액)}` +
          `<br/>생산 시군구 ${r.시군구수}곳`
      },
    },
    xAxis: axisX({ data: d.map((r) => `${r.연도}`) }),
    yAxis: [
      axisY({ name: '원/kg', axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.int(v) } }),
      axisY({ name: '톤', position: 'right', splitLine: { show: false },
        axisLabel: { color: t.subtle, fontSize: 11.5, formatter: (v) => fmt.int(v) } }),
    ],
    series: [
      { name: '생산량', type: 'bar', yAxisIndex: 1, barWidth: '38%',
        data: d.map((r) => r.생산량 / 1000),
        itemStyle: { color: palette.grey, opacity: 0.42, borderRadius: [4, 4, 0, 0] } },
      { name: '물량가중 단가', type: 'line', smooth: 0.2, symbolSize: 9,
        data: d.map((r) => r.가중평균단가),
        lineStyle: { width: 3, color: palette.forest },
        itemStyle: { color: palette.forest } },
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
        return `<b>${r.시도}</b><br/>단가 ${fmt.int(r.가중평균단가)}원/kg<br/>전국 대비 ${
          fmt.signed(r.전국대비_pct)}%<br/>생산량 ${fmt.int(r.생산량 / 1000)}톤`
      } },
    xAxis: axisY({ axisLabel: { color: t.subtle, fontSize: 11, formatter: '{value}%' } }),
    yAxis: axisX({ data: rows.map((r) => r.시도), axisLabel: { color: t.muted, fontSize: 11.5 } }),
    series: [{
      type: 'bar', barWidth: '62%',
      data: rows.map((r) => ({
        value: r.전국대비_pct,
        itemStyle: { color: r.전국대비_pct >= 0 ? palette.forest : palette.rose,
          borderRadius: r.전국대비_pct >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4], opacity: 0.9 },
      })),
      label: { show: true, position: 'right', color: t.muted, fontSize: 10.5,
        formatter: (p) => `${fmt.signed(p.value, 0)}%` },
    }],
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
        { name: '단가 변화 (녹색 상승 / 적색 하락)', itemStyle: { color: palette.forest } },
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
      { name: '단가 변화 (녹색 상승 / 적색 하락)', type: 'bar', barWidth: '34%',
        data: rows.map((r) => ({ value: r.chg,
          itemStyle: { color: r.chg >= 0 ? palette.forest : palette.rose } })),
        label: { show: true, position: 'right', color: t.muted, fontSize: 10.5,
          formatter: (p) => `${fmt.signed(p.value, 0)}%` } },
      { name: '생산량 변화', type: 'bar', barWidth: '34%',
        data: rows.map((r) => ({ value: r.prod, itemStyle: { color: palette.grey, opacity: 0.6 } })) },
    ],
  })
})
</script>

<template>
  <main class="content">
    <div class="container">
      <SectionHead
        title="임산물 시장 · 단가"
        :desc="prod ? `${prod.연도[0]}~${prod.연도.at(-1)}년 · 시군구×품목 ${fmt.int(prod.관측)}개 관측. KAMIS가 다루지 않는 밤·대추·떫은감·표고·산나물의 실측 단가를 임업통계만으로 확보합니다.` : ''"
        badge="임산물생산조사" badge-kind="green"
      />

      <DataState :loading="loading" :error="error">
        <template v-if="prod">
          <div class="chips" style="margin-bottom:16px">
            <button v-for="i in items" :key="i" class="chip"
                    :class="{ 'chip--active': picked === i }" @click="picked = i">{{ i }}</button>
          </div>

          <div v-if="last" class="grid grid--4">
            <MetricCard accent :label="`${last.연도}년 전국 단가`"
              :value="fmt.int(last.가중평균단가)" unit="원/kg"
              :delta="`${fmt.signed(trend.단가_변화율_pct)}% (${prod.연도[0]}년 대비)`"
              :delta-dir="trend.단가_변화율_pct >= 0 ? 'up' : 'down'" />
            <MetricCard label="생산량 변화" :value="fmt.signed(trend.생산량_변화율_pct)" unit="%"
              :delta-dir="trend.생산량_변화율_pct >= 0 ? 'up' : 'down'"
              :delta="`${fmt.int(last.생산량 / 1000)}톤`" />
            <MetricCard label="시장 규모" :value="fmt.won(last.생산금액)"
              :delta="`생산 시군구 ${last.시군구수}곳`" delta-dir="flat" />
            <MetricCard v-if="prem" label="지역 단가 격차"
              :value="fmt.dec(prem.지역격차_배, 2)" unit="배"
              :delta="`${prem.최고지역} ${fmt.int(prem.최고단가)}원 vs ${prem.최저지역} ${fmt.int(prem.최저단가)}원`"
              delta-dir="flat" />
          </div>

          <div class="grid grid--2 mt-lg">
            <div class="card">
              <div class="card__head"><h3>단가 · 생산량 추이</h3></div>
              <div class="card__body"><EChart v-if="trendOption" :option="trendOption" height="300px" /></div>
            </div>
            <div class="card">
              <div class="card__head">
                <h3>시도별 단가 프리미엄</h3>
                <span v-if="prem" class="badge badge--grey">{{ prem.연도 }}년</span>
              </div>
              <div class="card__body">
                <EChart v-if="premOption" :option="premOption" height="300px" />
                <p v-if="prem" class="caveat mt-sm">
                  전국 물량가중 평균 {{ fmt.int(prem.전국_가중평균단가) }}원/kg 대비 편차입니다.
                </p>
              </div>
            </div>
          </div>

          <div v-if="spec" class="card mt-lg">
            <div class="card__head">
              <h3>{{ picked }} 주산지 특화도 (LQ)</h3>
              <span class="badge badge--sky">{{ spec.연도 }}년</span>
            </div>
            <div class="card__body">
              <p class="fs-sm muted" style="margin-bottom:10px">
                LQ = 지역 내 해당 품목 생산금액 비중 ÷ 전국 비중. 1보다 크면 그 지역이 특화되어 있다는 뜻입니다.
              </p>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>시도</th><th class="num">LQ</th><th class="num">생산금액</th><th class="num">전국 비중</th></tr></thead>
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
            <div class="card__head"><h3>전 품목 단가 · 생산량 변화</h3></div>
            <div class="card__body">
              <EChart v-if="allTrendOption" :option="allTrendOption" height="400px" />
              <p class="caveat mt-sm">
                대부분 품목에서 생산량이 줄고 단가가 오르는 구조가 나타납니다.
              </p>
            </div>
          </div>

          <div v-if="prod.가공부가가치 && Object.keys(prod.가공부가가치).length" class="section mt-lg">
            <SectionHead title="1차 가공의 경제성" />
            <div v-for="(v, k) in prod.가공부가가치" :key="k" class="card">
              <div class="card__head">
                <h3>{{ k }}</h3>
                <span class="badge" :class="v.판정 === '가공이 유리' ? 'badge--green' : 'badge--amber'">
                  {{ v.판정 }}
                </span>
              </div>
              <div class="card__body">
                <div class="grid grid--4" style="gap:10px">
                  <MetricCard label="원물 단가" :value="fmt.int(v.원물_단가)" unit="원/kg" />
                  <MetricCard label="가공품 단가" :value="fmt.int(v.가공품_단가)" unit="원/kg" />
                  <MetricCard label="실제 단가 배수" :value="fmt.dec(v.단가_배수, 2)" unit="배" />
                  <MetricCard label="손익분기 배수" :value="fmt.dec(v.손익분기_배수, 1)" unit="배"
                    accent :delta="`건조수율 ${v.건조수율}`" delta-dir="flat" />
                </div>
                <div class="note mt-md"
                     :class="v.판정 === '가공이 유리' ? 'note--good' : 'note--warn'">
                  {{ v.해석 }} 원물 1kg을 가공해 얻는 수취액은
                  <b>{{ fmt.int(v.원물1kg당_가공수취액) }}원</b>으로, 원물 직판({{ fmt.int(v.원물_단가) }}원)
                  대비 <b>{{ fmt.signed(v.원물직판대비_pct) }}%</b>입니다.
                </div>
                <p class="caveat mt-sm">{{ v.주의 }}</p>
              </div>
            </div>
          </div>

          <div class="card mt-lg">
            <div class="card__head"><h3>분석 전제</h3></div>
            <div class="card__body">
              <p class="fs-sm muted">{{ prod.주의 }}</p>
              <p class="fs-sm muted mt-sm">
                단가는 관측치 단순평균이 아니라 <b>생산금액 ÷ 생산량</b>(물량가중)으로 계산했습니다.
                소규모 시군구의 특이 단가가 전국 평균을 왜곡하지 않도록 하기 위함입니다.
              </p>
            </div>
          </div>
        </template>
      </DataState>
    </div>
  </main>
</template>
