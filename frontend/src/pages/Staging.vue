<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getJSON } from '../api'

const runs = ref([])
const runId = ref('')
const rows = ref([])
const err = ref('')

const counts = computed(() => {
  const out = {}
  for (const r of rows.value) out[r.disposition] = (out[r.disposition] || 0) + 1
  return out
})

async function load() {
  err.value = ''
  try {
    const q = runId.value === '' ? '' : `?run_id=${encodeURIComponent(runId.value)}`
    rows.value = await getJSON('/api/staging' + q)
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function tagClass(d) {
  if (d === 'conflict' || d === 'authority_lost') return 'danger'
  if (d.startsWith('skip')) return 'warn'
  return 'ok'
}

onMounted(async () => {
  try {
    runs.value = await getJSON('/api/runs')
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  }
})
watch(runId, load)
</script>
<template>
  <div class="page">
    <h1>Staging</h1>
    <p class="muted">按 Run 查看暂存处置；处置合计应等于 Run 报告的 parsed_count。</p>
    <div class="panel">
      <label>
        Run
        <select v-model="runId">
          <option value="">最近 200 行（全部 Run）</option>
          <option v-for="r in runs" :key="r.id" :value="r.id">
            #{{ r.id }} · {{ r.source_name }} · {{ r.mode }} · parsed {{ r.parsed_count }}
          </option>
        </select>
      </label>
      <span class="muted" style="margin-left:1rem">行数 {{ rows.length }}</span>
      <p class="mono muted" style="margin-top:0.5rem">
        处置明细：<span v-for="(v, k) in counts" :key="k">{{ k }}={{ v }}&nbsp;</span>
      </p>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>run</th><th>source</th><th>key</th><th>event_ts</th><th>rev</th><th>disposition</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.run_id }}</td>
            <td>{{ r.source_id }}</td>
            <td class="mono">{{ r.business_key }}</td>
            <td class="mono">{{ r.event_ts }}</td>
            <td>{{ r.source_revision }}</td>
            <td><span class="tag" :class="tagClass(r.disposition)">{{ r.disposition }}</span></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="muted">暂无暂存行。</p>
    </div>
  </div>
</template>
