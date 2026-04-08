<script setup lang="ts">
import { onMounted, ref } from 'vue'
import DashboardView from './views/DashboardView.vue'
import LogsView from './views/LogsView.vue'
import BackupsView from './views/BackupsView.vue'
import { useTunator } from './composables/useTunator'
import { api } from './services/api'

const tab = ref<'dashboard'|'config'|'onions'|'logs'|'diagnostics'|'backups'>('dashboard')
const { loading, busyAction, toast, environment, status, diagnostics, logs, rawTorrc, onions, backups, configForm, refreshAll, action } = useTunator()
const onionForm = ref({ name: '', public_port: 80, target_host: '127.0.0.1', target_port: 3000, access_password: '' })

async function saveConfig() {
  busyAction.value = 'save-config'
  try {
    const updates = { ...configForm }
    const preview = await api<{valid:boolean;errors:string[];diff:string}>('/api/config/preview', { method: 'POST', body: JSON.stringify({ updates }) })
    if (!preview.valid) throw new Error(preview.errors.join('; '))
    if (preview.diff && !window.confirm(`Aplicar mudanças no torrc?\n\n${preview.diff.split('\n').slice(0, 20).join('\n')}`)) return
    const result = await api<{warnings?: string[]}>('/api/config/apply', { method: 'POST', body: JSON.stringify({ updates }) })
    toast.value = result.warnings?.length ? result.warnings.join('; ') : 'torrc atualizado.'
    await refreshAll()
  } catch (err:any) { toast.value = err.message || String(err) }
  finally { busyAction.value = '' }
}

async function createOnion() {
  busyAction.value = 'create-onion'
  try {
    await api('/api/onions', { method: 'POST', body: JSON.stringify(onionForm.value) })
    toast.value = 'Onion criado.'
    onionForm.value = { name: '', public_port: 80, target_host: '127.0.0.1', target_port: 3000, access_password: '' }
    await refreshAll()
  } catch (err:any) { toast.value = err.message || String(err) }
  finally { busyAction.value = '' }
}

async function deleteOnion(name: string) {
  if (!window.confirm(`Remover onion ${name} do torrc?`)) return
  await api(`/api/onions/${encodeURIComponent(name)}`, { method: 'DELETE' })
  await refreshAll()
}

function handleToast(message: string) { toast.value = message }

onMounted(refreshAll)
</script>

<template>
  <main class="page">
    <header class="hero row-between"><h1>Tunator</h1><button class="secondary" @click="refreshAll" :disabled="loading">Atualizar</button></header>
    <p v-if="toast" class="toast">{{ toast }}</p>
    <nav class="tabs">
      <button v-for="name in ['dashboard','config','onions','logs','diagnostics','backups']" :key="name" class="secondary" @click="tab=name as any">{{ name }}</button>
    </nav>

    <DashboardView v-if="tab==='dashboard'" :environment="environment" :status="status" :busy-action="busyAction" @action="action" />

    <section v-if="tab==='config'" class="grid two">
      <article class="card">
        <h2>Configuração</h2>
        <label>SOCKSPort <input v-model="configForm.SOCKSPort" /></label>
        <label>ControlPort <input v-model="configForm.ControlPort" /></label>
        <label>DataDirectory <input v-model="configForm.DataDirectory" /></label>
        <label>Log <input v-model="configForm.Log" /></label>
        <label>ExcludeNodes (avançado) <input v-model="configForm.ExcludeNodes" /></label>
        <button @click="saveConfig" :disabled="busyAction!==''">Salvar com preview</button>
      </article>
      <article class="card"><h2>Preview do torrc</h2><textarea class="logs" :value="rawTorrc" readonly /></article>
    </section>

    <section v-if="tab==='onions'" class="card">
      <h2>Onion Services</h2>
      <div class="grid four">
        <label>Nome <input v-model="onionForm.name" /></label>
        <label>Porta pública <input v-model.number="onionForm.public_port" type="number" /></label>
        <label>Host interno <input v-model="onionForm.target_host" /></label>
        <label>Porta interna <input v-model.number="onionForm.target_port" type="number" /></label>
      </div>
      <button @click="createOnion" :disabled="busyAction!==''">Criar onion</button>
      <div v-for="item in onions" :key="item.name" class="row-between"><span>{{ item.name }} — {{ item.hostname || 'pendente' }}</span><button class="danger" @click="deleteOnion(item.name)">Remover</button></div>
    </section>

    <LogsView v-if="tab==='logs'" :logs="logs" />

    <section v-if="tab==='diagnostics'" class="card">
      <h2>Diagnóstico</h2>
      <button class="secondary" @click="api('/api/diagnostics/run',{method:'POST'}).then(refreshAll)">Rodar</button>
      <ul><li v-for="item in diagnostics?.checks || []" :key="item.name"><strong>{{ item.ok ? 'OK' : 'Falhou' }}</strong> — {{ item.name }}: {{ item.details }}</li></ul>
    </section>

    <BackupsView v-if="tab==='backups'" :items="backups" @restored="refreshAll" @toast="handleToast" />
  </main>
</template>

<style scoped>
:global(body){margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f2f6fa;color:#17324a}
.page{max-width:1200px;margin:0 auto;padding:20px}.row-between{display:flex;justify-content:space-between;gap:12px;align-items:center}
.grid{display:grid;gap:12px}.two{grid-template-columns:1fr 1fr}.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.card{background:#fff;border:1px solid #d4e0eb;border-radius:10px;padding:14px}.hero{margin-bottom:12px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
button{padding:8px 10px;border-radius:8px;border:none;background:#2f78b7;color:#fff;cursor:pointer}button.secondary{background:#e5eef7;color:#1d4f7f;border:1px solid #b8d0e5}button.danger{background:#c85b5b}
label{display:flex;flex-direction:column;gap:4px}input,textarea{padding:7px;border:1px solid #bcd0e2;border-radius:8px}.logs{width:100%;min-height:260px;white-space:pre-wrap}
.toast{padding:10px;background:#eaf4ff;border:1px solid #b4d1ef;border-radius:8px}
@media (max-width:900px){.two,.four{grid-template-columns:1fr}}
</style>
