<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getJSON } from '../api'

const runs = ref([])
const runId = ref('')
const conflicts = ref([])
const changes = ref([])
const err = ref('')

const runQuery = computed(() =>
  runId.value === '' ? '' : `?run_id=${encodeURIComponent(runId.value)}`
)
const conflictLost = computed(() => conflicts.value.filter((c) => c.reason === 'authority_lost').length)
const conflictPure = computed(() => conflicts.value.length - conflictLost.value)

async function load() {
  err.value = ''
  try {
    conflicts.value = await getJSON('/api/conflicts' + runQuery.value)
    changes.value = await getJSON('/api/authority-changes' + runQuery.value)
  } catch (e) {
    err.value = String(e.message || e)
  }
}

function reasonClass(reason) {
  if (reason === 'authority_lost') return 'danger'
  if (reason === 'authority_equal' || reason === 'authority_unknown') return 'warn'
  return 'danger'
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
    <h1>冲突队列与权威裁决</h1>
    <p class="muted">
      同业务键、非键字段分歧时：传入源权威序更高 → 覆盖 Canonical 并留权威变更依据；
      更低 → 不得改主数据，按 <span class="mono">authority_lost</span> 隔离；
      相等或无法判定 → 冲突隔离，禁止静默覆盖。
    </p>
    <div class="panel">
      <label>
        Run
        <select v-model="runId">
          <option value="">全部</option>
          <option v-for="r in runs" :key="r.id" :value="r.id">
            #{{ r.id }} · {{ r.source_name }} · {{ r.mode }}
          </option>
        </select>
      </label>
      <span class="muted" style="margin-left:1rem">
        冲突 {{ conflictPure }} · 权威落败隔离 {{ conflictLost }} · 权威覆盖 {{ changes.length }}
      </span>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>

    <div class="panel">
      <h3>隔离记录（conflicts）</h3>
      <p v-if="!conflicts.length" class="muted">暂无隔离记录。</p>
      <div v-for="c in conflicts" :key="c.id" class="panel" style="margin-bottom:0.75rem">
        <p>
          #{{ c.id }} · run {{ c.run_id }} · {{ c.source_name }} ·
          <span class="mono">{{ c.business_key }}</span> ·
          <span class="tag" :class="reasonClass(c.reason)">{{ c.reason }}</span>
          <span class="muted"> · {{ c.created_at }}</span>
        </p>
        <p class="mono muted">
          归属源 {{ c.owner_source_name || ('#' + (c.owner_source_id ?? '?')) }}
          （权威序 {{ c.owner_authority_rank ?? '未知' }}）
          ← 传入源 {{ c.source_name }}（权威序 {{ c.incoming_authority_rank ?? '未知' }}）
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
          <div>
            <div class="muted">existing（主数据保持）</div>
            <pre class="mono">{{ JSON.stringify(c.existing, null, 2) }}</pre>
          </div>
          <div>
            <div class="muted">incoming（被隔离）</div>
            <pre class="mono">{{ JSON.stringify(c.incoming, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>权威变更依据（authority changes）</h3>
      <p v-if="!changes.length" class="muted">暂无权威覆盖记录。</p>
      <div v-for="a in changes" :key="a.id" class="panel" style="margin-bottom:0.75rem">
        <p>
          #{{ a.id }} · run {{ a.run_id }} · <span class="mono">{{ a.business_key }}</span> ·
          <span class="tag ok">authority_override</span>
          <span class="muted"> · {{ a.created_at }}</span>
        </p>
        <p class="mono muted">
          {{ a.previous_source_name || ('#' + (a.previous_source_id ?? '?')) }}
          （权威序 {{ a.previous_authority_rank ?? '未知' }}）
          → {{ a.source_name }}（权威序 {{ a.incoming_authority_rank ?? '未知' }}）
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
          <div>
            <div class="muted">previous payload</div>
            <pre class="mono">{{ JSON.stringify(a.previous, null, 2) }}</pre>
          </div>
          <div>
            <div class="muted">incoming payload（已写入主数据）</div>
            <pre class="mono">{{ JSON.stringify(a.incoming, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
pre {
  background: #0a1422;
  padding: 0.75rem;
  border-radius: 8px;
  overflow: auto;
  max-height: 240px;
}
</style>
