<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, patchJSON } from '../api'

const rows = ref([])
const err = ref('')
const msg = ref('')

async function load() {
  rows.value = await getJSON('/api/sources')
}

async function saveAuthority(row) {
  err.value = ''
  msg.value = ''
  try {
    await patchJSON(`/api/sources/${row.id}/authority`, {
      authority_rank: Number(row.authority_rank) || 0,
    })
    msg.value = `源 ${row.id} 权威序已保存（数值越大越权威）`
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

onMounted(async () => {
  try {
    await load()
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>
<template>
  <div class="page">
    <h1>源管理</h1>
    <p class="muted">
      本地夹具源（json / jsonl / xml），不含活网爬虫。权威序为源级整数配置：
      <strong>数值越大越权威</strong>，同键非键字段分歧时由它决定覆盖或隔离。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>
    <p v-if="msg" class="tag ok">{{ msg }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>名称</th><th>格式</th><th>夹具</th><th>权威序</th><th>水位线</th><th>lookback</th><th></th><th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in rows" :key="s.id">
            <td>{{ s.id }}</td>
            <td>{{ s.name }}</td>
            <td><span class="mono">{{ s.format }}</span></td>
            <td class="mono">{{ s.fixture_path }}</td>
            <td>
              <input type="number" v-model.number="s.authority_rank" min="0" style="width:6rem" />
            </td>
            <td class="mono">{{ s.watermark_ts || '—' }}</td>
            <td>{{ s.lookback_seconds }}s</td>
            <td><button class="secondary" @click="saveAuthority(s)">保存权威序</button></td>
            <td class="muted">{{ s.note }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
