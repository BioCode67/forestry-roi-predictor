const BASE = import.meta.env.VITE_API_BASE || ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j.detail) detail = j.detail
    } catch { /* 본문이 JSON이 아니면 상태 코드만 남긴다 */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  health: () => req('/api/health'),
  meta: () => req('/api/meta'),
  predict: (body) => req('/api/predict', { method: 'POST', body: JSON.stringify(body) }),
  predictItem: (body) => req('/api/predict/item', { method: 'POST', body: JSON.stringify(body) }),
  itemDistribution: () => req('/api/item/distribution'),
  shipping: (sector) => req(`/api/shipping/${encodeURIComponent(sector)}`),
  insights: () => req('/api/insights'),
  production: () => req('/api/production'),
  management: () => req('/api/management'),
  subsidy: () => req('/api/subsidy'),
  region: () => req('/api/region'),
  portfolio: () => req('/api/portfolio'),
  advice: (body) => req('/api/advice', { method: 'POST', body: JSON.stringify(body) }),
}

/* ---------------------------------------------------------------- 포맷터 */
const nf = new Intl.NumberFormat('ko-KR')

export const fmt = {
  int: (v) => (v == null || !isFinite(v) ? '—' : nf.format(Math.round(v))),
  dec: (v, d = 1) =>
    v == null || !isFinite(v)
      ? '—'
      : v.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (v, d = 1) => (v == null || !isFinite(v) ? '—' : `${fmt.dec(v, d)}%`),
  signed: (v, d = 1) =>
    v == null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${fmt.dec(v, d)}`,
  /** 큰 금액을 억/만 단위로 줄여 표기한다 */
  won: (v) => {
    if (v == null || !isFinite(v)) return '—'
    const a = Math.abs(v)
    if (a >= 1e8) return `${(v / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}억원`
    if (a >= 1e4) return `${(v / 1e4).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}만원`
    return `${nf.format(Math.round(v))}원`
  },
  wonFull: (v) => (v == null || !isFinite(v) ? '—' : `${nf.format(Math.round(v))}원`),
}
