<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../services/api'
import type { BackupItem } from '../types/api'

const props = defineProps<{ items: BackupItem[] }>()
const emit = defineEmits<{ (e:'restored'):void; (e:'toast', value:string):void }>()
const busy = ref(false)
async function restore(name: string) {
  busy.value = true
  try {
    await api('/api/config/backups/restore', { method: 'POST', body: JSON.stringify({ backup_name: name }) })
    emit('toast', `Backup ${name} restaurado.`)
    emit('restored')
  } catch (err:any) { emit('toast', err.message || String(err)) }
  finally { busy.value = false }
}
</script>
<template>
  <article class="card">
    <h2>Backups</h2>
    <div v-for="item in props.items" :key="item.name" class="row-between">
      <span><code>{{ item.name }}</code> ({{ item.size_bytes }} bytes)</span>
      <button class="secondary" :disabled="busy" @click="restore(item.name)">Restaurar</button>
    </div>
  </article>
</template>
