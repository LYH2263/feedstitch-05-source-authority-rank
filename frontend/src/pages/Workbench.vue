<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'

const sources = ref([])
const sourceId = ref(null)
const mode = ref('incremental')
const last = ref(null)
const history = ref([])
const err = ref('')
const busy = ref(false)

async function refresh() {
  history.value = await getJSON('/api/runs')
}

async function runOnce() {
  err.value = ''
  busy.value = true
  try {
    last.value = await postJSON(`/api/sources/${sourceId.value}/runs`, { mode: mode.value })
    await refresh()
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

function ok(v) {
  return v ? 'ok' : 'danger'
}

onMounted(async () => {
  sources.value = await getJSON('/api/sources')
  if (sources.value.length) sourceId.value = sources.value[0].id
  await refresh()
})
</script>
<template>
  <div class="page">
    <h1>运行台</h1>
    <p class="muted">
      选源触发增量或全量。报告中的写入 / 冲突 / 权威隔离 / 跳过数应与
      <router-link to="/staging">Staging 处置</router-link>、<router-link to="/conflicts">冲突列表</router-link>
      及 <router-link to="/canonical">Canonical 条数</router-link>互相解释。
    </p>
    <div class="panel">
      <label>
        源
        <select v-model.number="sourceId">
          <option v-for="s in sources" :key="s.id" :value="s.id">
            {{ s.id }}. {{ s.name }}（权威序 {{ s.authority_rank }}）
          </option>
        </select>
      </label>
      <label style="margin-left:1rem">
        模式
        <select v-model="mode">
          <option value="incremental">incremental</option>
          <option value="full">full</option>
        </select>
      </label>
      <button style="margin-left:1rem" :disabled="busy || !sourceId" @click="runOnce">
        {{ busy ? '运行中…' : '执行 Run' }}
      </button>
    </div>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <div class="panel" v-if="last">
      <h3>最近一次报告 · Run #{{ last.id }}</h3>
      <p>
        <span class="tag" :class="last.status === 'ok' ? 'ok' : 'danger'">{{ last.status }}</span>
        <span class="muted"> · {{ last.source_name }}（权威序 {{ last.report?.source_authority_rank }}） · {{ last.mode }}</span>
      </p>
      <div class="tiles" style="grid-template-columns:repeat(5,1fr)">
        <div class="tile"><div class="hero-num">{{ last.report?.parsed_count }}</div><div class="muted">解析 parsed</div></div>
        <div class="tile"><div class="hero-num">{{ last.report?.upserted_count }}</div><div class="muted">写入 upserted</div></div>
        <div class="tile"><div class="hero-num">{{ last.report?.conflict_count }}</div><div class="muted">冲突隔离</div></div>
        <div class="tile"><div class="hero-num">{{ last.report?.authority_isolated_count }}</div><div class="muted">权威落败隔离</div></div>
        <div class="tile"><div class="hero-num">{{ last.report?.skipped_count }}</div><div class="muted">跳过 skipped</div></div>
      </div>
      <p class="mono muted">
        写入构成：insert {{ last.report?.inserted_count }} / update {{ last.report?.updated_count }} /
        权威覆盖 {{ last.report?.authority_override_count }} ·
        权威变更依据 {{ last.report?.authority_change_count }} 条
      </p>
      <p class="mono muted">
        canonical_count={{ last.report?.canonical_count }} ·
        staging_rows={{ last.report?.staging_rows_count }} ·
        conflict_rows={{ last.report?.conflict_rows_count }} ·
        watermark={{ last.report?.watermark_ts }}
      </p>
      <p v-if="last.report?.reconcile" class="mono">
        <span class="tag" :class="ok(last.report.reconcile.parsed_equals_dispositions)">parsed=处置合计</span>
        <span class="tag" :class="ok(last.report.reconcile.writes_equals_breakdown)">写入=构成</span>
        <span class="tag" :class="ok(last.report.reconcile.staging_rows_equal_parsed)">staging=parsed</span>
        <span class="tag" :class="ok(last.report.reconcile.conflict_rows_equal_quarantine)">conflict 行=隔离合计</span>
        <span class="tag" :class="ok(last.report.reconcile.authority_changes_equal_overrides)">权威依据=覆盖数</span>
      </p>
      <p class="mono muted">
        处置明细：<span v-for="(v, k) in last.report?.disposition_counts" :key="k">{{ k }}={{ v }}&nbsp;</span>
      </p>
    </div>
    <div class="panel">
      <h3>历史 Runs</h3>
      <table>
        <thead>
          <tr>
            <th>ID</th><th>源</th><th>模式</th><th>状态</th><th>parsed</th><th>写入</th><th>冲突</th><th>权威隔离</th><th>跳过</th><th>Canonical</th><th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in history" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.source_name }}</td>
            <td>{{ r.mode }}</td>
            <td><span class="tag" :class="r.status === 'ok' ? 'ok' : 'danger'">{{ r.status }}</span></td>
            <td>{{ r.parsed_count }}</td>
            <td>{{ r.upserted_count }}</td>
            <td>{{ r.conflict_count }}</td>
            <td>{{ r.authority_isolated_count }}</td>
            <td>{{ r.skipped_count }}</td>
            <td class="mono">{{ r.report?.canonical_count }}</td>
            <td class="mono">{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
