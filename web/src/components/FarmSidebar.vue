<script setup>
import { computed, inject } from 'vue'
import { fmt } from '../lib/api'

const meta = inject('meta')
const farm = inject('farm')

const CATS = [
  ['지역별', '지역'],
  ['업종별', '영림 업종'],
  ['임지규모별', '임지 규모'],
  ['전/겸업별', '전업 / 겸업'],
  ['연령별', '경영주 연령대'],
  ['가구원수별', '가구원 수'],
]

const MONEY = [
  ['임업경영비', '연간 임업경영비', 0, 500000000, 1000000,
    '종묘·비료·농약·고용노력·감가상각 등 임업 생산에 투입하는 연간 비용'],
  ['임업외소득', '임업외소득', -100000000, 500000000, 1000000, ''],
  ['기초_자본(순재산)', '기초 자본(순재산)', 0, 5000000000, 10000000, ''],
  ['연초보유', '연초 보유 현금', 0, 1000000000, 1000000, ''],
]

const options = (key) => {
  const d = meta.value?.codebook?.[key]
  return d ? Object.entries(d).map(([code, label]) => ({ code: Number(code), label })) : []
}

const years = [2019, 2020, 2021, 2022, 2023]

const totalScale = computed(() =>
  fmt.won(Number(farm.임업경영비) + Number(farm['기초_자본(순재산)'])))
</script>

<template>
  <div v-if="!meta" class="stack stack--sm">
    <div class="skeleton" style="height:13px;width:52%"></div>
    <div class="skeleton" style="height:34px"></div>
    <div class="skeleton" style="height:34px"></div>
    <div class="skeleton" style="height:34px"></div>
  </div>

  <template v-else>
    <div class="sidebar__group">
      <div class="sidebar__title">임가 제원</div>
      <div v-for="[key, label] in CATS" :key="key" class="field">
        <label class="field__label">{{ label }}</label>
        <select class="select" v-model.number="farm[key]">
          <option v-for="o in options(key)" :key="o.code" :value="o.code">{{ o.label }}</option>
        </select>
      </div>
      <p class="field__hint">임가경제조사 코드 체계와 동일한 구분입니다.</p>
    </div>

    <div class="sidebar__group">
      <div class="sidebar__title">경영 규모</div>
      <div v-for="[key, label, min, max, step, hint] in MONEY" :key="key" class="field">
        <label class="field__label">{{ label }}</label>
        <div class="input-money">
          <input class="input" type="number" v-model.number="farm[key]"
                 :min="min" :max="max" :step="step" />
          <span class="input-money__unit">원</span>
        </div>
        <input class="range mt-sm" type="range" v-model.number="farm[key]"
               :min="min" :max="max" :step="step" />
        <p class="field__hint">
          {{ fmt.won(farm[key]) }}<template v-if="hint"> · {{ hint }}</template>
        </p>
      </div>
    </div>

    <div class="sidebar__group">
      <div class="sidebar__title">기준 연도</div>
      <div class="chips">
        <button v-for="y in years" :key="y" class="chip"
                :class="{ 'chip--active': farm.조사연도 === y }"
                @click="farm.조사연도 = y">{{ y }}</button>
      </div>
    </div>

    <div class="note note--info fs-xs">
      입력값을 바꾸면 모든 화면이 즉시 다시 계산됩니다.
      현재 경영 규모 합계 <b>{{ totalScale }}</b>
    </div>
  </template>
</template>
