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
    yAxis: axisY({ name: 'kg당 원', axisLabel: { color: t.subtle, fontSize: 11.5,
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
    yAxis: axisY({ name: '수익률 (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
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
    legend: { data: ['잘하는 농가', '보통 농가'] },
    tooltip: { trigger: 'axis', backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder,
      borderWidth: 1, textStyle: { color: t.text, fontSize: 12.5 },
      formatter: (ps) => `<b>${ps[0].axisValue}</b><br/>` +
        ps.map((p) => `${p.marker}${p.seriesName} ${fmt.dec(p.value)}%`).join('<br/>') },
    xAxis: axisX({ data: labels }),
    yAxis: axisY({ name: '쓴 돈 중 차지하는 몫 (%)', axisLabel: { color: t.subtle, fontSize: 11.5,
      formatter: '{value}%' } }),
    series: [
      { name: '잘하는 농가', type: 'bar', barWidth: '32%', data: lead,
        itemStyle: { color: palette.forest, borderRadius: [4, 4, 0, 0] } },
      { name: '보통 농가', type: 'bar', barWidth: '32%', data: rest,
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
        title="어떻게 하면 더 벌 수 있을까요"
        desc="앞 화면이 '얼마 남을까'였다면, 여기는 '무엇을 바꾸면 나아질까'입니다. 등급을 올릴 때, 나무 나이에 따라, 잘하는 농가와 비교했을 때 얼마나 차이가 나는지 실제 조사 자료로 확인해 보세요."
        badge="전국 생산비 조사" badge-kind="green"
      />

      <DataState :loading="loading" :error="error">
        <template v-if="ins">
          <!-- ① 등급 단가 -->
          <div class="card">
            <div class="card__head"><h3>등급을 올리면 얼마나 더 받나요</h3></div>
            <div class="card__body">
              <div class="chips" style="margin-bottom:14px">
                <button v-for="i in gradeItems" :key="i" class="chip"
                        :class="{ 'chip--active': gradeItem === i }" @click="gradeItem = i">{{ i }}</button>
              </div>
              <div class="grid grid--32">
                <EChart v-if="gradeOption" :option="gradeOption" height="300px" />
                <div class="stack stack--md">
                  <MetricCard v-if="grade?.직접비교_가능" accent label="제일 좋은 등급과 낮은 등급 차이"
                    :value="fmt.dec(grade.최고_최저_단가배수, 2)" unit="배" />
                  <div class="table-wrap">
                    <table>
                      <thead><tr><th>{{ grade?.종류 }}</th><th class="num">kg당 값</th><th class="num">이걸 내는 농가</th></tr></thead>
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
                <strong>선별만 잘해도</strong> — {{ sim.전환_시나리오 }} 시 단위면적당 수취액
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
              <h3>나무가 몇 년생일 때 가장 잘 벌까요</h3>
              <span class="badge badge--amber">나무 갱신 판단</span>
            </div>
            <div class="card__body">
              <EChart v-if="ageOption" :option="ageOption" height="330px" />
              <div class="grid grid--3 mt-md" style="gap:10px">
                <MetricCard v-for="(v, k) in ins.수령별_수익성" :key="k"
                  :label="`${k} — 가장 잘 버는 나이`" :value="v.최고구간"
                  :delta="`${fmt.dec(v.최고ROI, 0)}% · 최저 ${v.최저구간} ${fmt.dec(v.최저ROI, 0)}%`"
                  delta-dir="up" />
              </div>
              <p class="caveat mt-sm">
                수익이 꼭대기를 지나 내려가는 구간에 들어섰다면, 나무를 새로 심거나 수형을 손볼
                시점인지 살펴보실 만합니다.
              </p>
            </div>
          </div>

          <!-- ③ 선도임가 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>잘하는 농가는 어디에 돈을 쓰나요</h3></div>
            <div class="card__body">
              <div class="chips" style="margin-bottom:14px">
                <button v-for="i in leaderItems" :key="i" class="chip"
                        :class="{ 'chip--active': leaderItem === i }" @click="leaderItem = i">{{ i }}</button>
              </div>
              <div class="grid grid--32">
                <EChart v-if="leaderOption" :option="leaderOption" height="290px" />
                <div class="stack stack--md">
                  <div class="grid grid--2" style="gap:10px">
                    <MetricCard label="잘하는 농가 수익률"
                      :value="fmt.dec(leader?.선도임가?.ROI중앙값, 0)" unit="%" accent
                      :delta="`${fmt.int(leader?.표본?.선도임가)}곳 조사`" delta-dir="flat" />
                    <MetricCard label="보통 농가 수익률"
                      :value="fmt.dec(leader?.이외임가?.ROI중앙값, 0)" unit="%"
                      :delta="`${fmt.int(leader?.표본?.이외임가)}곳 조사`" delta-dir="flat" />
                  </div>
                  <MetricCard label="한 해 일한 시간 (잘하는 / 보통)"
                    :value="`${fmt.int(leader?.선도임가?.총노동시간)} / ${fmt.int(leader?.이외임가?.총노동시간)}`"
                    unit="시간" />
                </div>
              </div>
              <div v-if="leader?.해석_유의" class="note note--warn mt-md fs-sm">
                <strong>참고하실 점</strong> — '잘하는 농가'는 조사에서 성과가 좋다고 분류된 곳이라
              수익률 차이 자체가 크게 나오는 건 당연합니다. 눈여겨보실 부분은 수익률 숫자가 아니라
              <b>돈을 어디에 얼마나 쓰는지의 차이</b>입니다.
              </div>
            </div>
          </div>

          <!-- ④ 지역×품목 -->
          <div class="card mt-lg">
            <div class="card__head"><h3>어느 지역에서 무엇이 잘 되나요</h3></div>
            <div class="card__body">
              <EChart v-if="regionOption" :option="regionOption" height="420px" />
              <p class="caveat mt-sm">조사된 농가가 15곳 이상인 경우만 표시합니다. 빈 칸은 자료가 적어 판단하기 어려운 조합입니다.</p>
            </div>
          </div>

          <div class="note note--info mt-lg fs-sm">
            여기 숫자들은 전국 농가를 조사한 결과를 정리한 것입니다. "이렇게 하면 반드시 이만큼 오른다"는
            보장이 아니라 "이런 경향이 있다"는 참고 자료로 봐 주세요.
          </div>
        </template>
      </DataState>
    </div>
  </main>
</template>
