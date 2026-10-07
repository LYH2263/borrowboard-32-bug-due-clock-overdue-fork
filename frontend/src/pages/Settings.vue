<template>
  <div style="padding:16px;max-width:420px">
    <h1>设置 · 邻里互借</h1>
    <h3>全板宽限（自然日）</h3>
    <p class="muted">只给应还日加自然日，不会清掉任何已写下的截止钟点；只过日未到点的笔不会进逾期。</p>
    <input v-model.number="grace" type="number" min="0" />
    <button @click="save">保存宽限</button>
    <hr />
    <pre>{{ s }}</pre>
  </div>
</template>
<script setup>
import { ref, inject, onMounted } from 'vue'
import { api } from '../api'
const reloadBoard = inject('reloadBoard')
const s = ref('')
const grace = ref(0)
async function load() {
  const settings = await api('/settings')
  s.value = JSON.stringify(settings, null, 2)
  grace.value = Number(settings.grace_days || 0)
}
async function save() {
  // 成败都以服务端为准回拉：保存失败时设置与分栏一起停在改前，不各吃一半
  try {
    await api('/settings/grace_days', {
      method: 'PUT', body: JSON.stringify({ days: Number(grace.value) || 0 }),
    })
  } catch (e) { alert('保存宽限失败：' + e.message) }
  finally { await load(); await reloadBoard() }
}
onMounted(load)
</script>
