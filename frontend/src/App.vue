<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

type StatusResponse = { running: boolean; source: string; message: string; pid?: number | null }
type EnvironmentResponse = { os_name: string; tor_installed: boolean; tor_source: string; tor_binary_path?: string | null; torrc_path?: string | null; log_path?: string | null; bundle_download_url?: string | null }
type OnionItem = {
  name: string
  directory: string
  public_port: number
  target_host: string
  target_port: number
  hostname?: string | null
  hostname_path?: string | null
  hostname_ready?: boolean
}
type ConfigResponse = { raw: string; base_options: Record<string, string>; onion_services: OnionItem[] }
type DiagnosticItem = { name: string; ok: boolean; details: string }

const apiBase = ((import.meta as any).env?.VITE_API_BASE || '').replace(/\/$/, '')
const loading = ref(false)
const busyAction = ref('')
const toast = ref('')
const environment = ref<EnvironmentResponse | null>(null)
const status = ref<StatusResponse | null>(null)
const diagnostics = ref<DiagnosticItem[]>([])
const logs = ref<string[]>([])
const rawTorrc = ref('')
const configForm = reactive({
  SOCKSPort: '9050',
  ControlPort: '9051',
  DataDirectory: '',
  Log: '',
})
const onionForm = reactive({
  name: '',
  public_port: 80,
  target_host: '127.0.0.1',
  target_port: 3000,
})
const onions = ref<OnionItem[]>([])

const pendingOnions = computed(() => onions.value.filter((item) => !item.hostname_ready))

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase}${path}`
  let res: Response
  try {
    res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
    })
  } catch (err: any) {
    const baseHint = apiBase || window.location.origin
    throw new Error(`Não consegui alcançar a API em ${baseHint}. Abra a interface pelo mesmo endereço do backend e confirme /health ou /docs.`)
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data?.detail?.message || data?.detail?.errors?.join('; ') || data?.message || 'Request failed')
  }
  return data as T
}

async function refreshAll() {
  loading.value = true
  try {
    const [env, st, cfg, logRes] = await Promise.all([
      api<EnvironmentResponse>('/api/environment'),
      api<StatusResponse>('/api/status'),
      api<ConfigResponse>('/api/config'),
      api<{ entries: string[] }>('/api/logs?limit=100'),
    ])
    environment.value = env
    status.value = st
    rawTorrc.value = cfg.raw
    logs.value = logRes.entries
    onions.value = cfg.onion_services || []
    configForm.SOCKSPort = cfg.base_options.SOCKSPort || '9050'
    configForm.ControlPort = cfg.base_options.ControlPort || '9051'
    configForm.DataDirectory = cfg.base_options.DataDirectory || ''
    configForm.Log = cfg.base_options.Log || ''
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    loading.value = false
  }
}

async function refreshHostnamesUntilReady() {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await refreshAll()
    if (!pendingOnions.value.length || !status.value?.running) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}

async function runDiagnostics() {
  busyAction.value = 'diagnostics'
  try {
    const result = await api<{ checks: DiagnosticItem[] }>('/api/diagnostics/run', { method: 'POST' })
    diagnostics.value = result.checks
    toast.value = 'Diagnóstico atualizado.'
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    busyAction.value = ''
  }
}

async function serviceAction(action: 'start' | 'stop' | 'restart') {
  busyAction.value = action
  try {
    const result = await api<{ message: string }>(`/api/service/${action}`, { method: 'POST' })
    toast.value = result.message
    await refreshAll()
    if ((action === 'start' || action === 'restart') && status.value?.running && pendingOnions.value.length) {
      await refreshHostnamesUntilReady()
    }
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    busyAction.value = ''
  }
}

async function saveConfig() {
  busyAction.value = 'save-config'
  try {
    const updates = {
      SOCKSPort: configForm.SOCKSPort,
      ControlPort: configForm.ControlPort,
      DataDirectory: configForm.DataDirectory,
      Log: configForm.Log,
    }
    const validation = await api<{ valid: boolean; errors: string[]; warnings: string[] }>('/api/config/validate', {
      method: 'POST',
      body: JSON.stringify({ updates }),
    })
    if (!validation.valid) {
      toast.value = validation.errors.join('; ')
      return
    }
    const result = await api<{ warnings?: string[] }>('/api/config/apply', {
      method: 'POST',
      body: JSON.stringify({ updates }),
    })
    toast.value = result.warnings?.length ? result.warnings.join('; ') : 'torrc atualizado.'
    await refreshAll()
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    busyAction.value = ''
  }
}

async function createOnion() {
  busyAction.value = 'create-onion'
  try {
    const result = await api<{ item: OnionItem; warnings?: string[] }>('/api/onions', {
      method: 'POST',
      body: JSON.stringify(onionForm),
    })
    toast.value = result.warnings?.length ? result.warnings.join('; ') : `Onion ${result.item.name} criado.`
    onionForm.name = ''
    await refreshAll()
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    busyAction.value = ''
  }
}

async function deleteOnion(name: string) {
  busyAction.value = `delete-${name}`
  try {
    await api(`/api/onions/${encodeURIComponent(name)}`, { method: 'DELETE' })
    toast.value = `Onion ${name} removido do torrc.`
    await refreshAll()
  } catch (err: any) {
    toast.value = err.message || String(err)
  } finally {
    busyAction.value = ''
  }
}

async function copyText(value: string | null | undefined, label: string) {
  if (!value) {
    toast.value = `${label} ainda não disponível.`
    return
  }
  try {
    await navigator.clipboard.writeText(value)
    toast.value = `${label} copiado.`
  } catch {
    toast.value = `Não consegui copiar ${label.toLowerCase()}.`
  }
}

onMounted(async () => {
  await refreshAll()
  await runDiagnostics()
})
</script>

<template>
  <main class="page">
    <header class="hero">
      <div>
        <h1>Tunator</h1>
        <p>Painel local pra mexer no Tor sem ter que brigar com o torrc na mão.</p>
      </div>
      <button class="secondary" @click="refreshAll" :disabled="loading">Atualizar</button>
    </header>

    <p v-if="toast" class="toast">{{ toast }}</p>

    <section class="grid two">
      <article class="card">
        <h2>Status</h2>
        <p><strong>Tor:</strong> {{ status?.running ? 'rodando' : 'parado' }}</p>
        <p><strong>Mensagem:</strong> {{ status?.message || '—' }}</p>
        <p><strong>PID:</strong> {{ status?.pid ?? '—' }}</p>
        <div class="actions">
          <button @click="serviceAction('start')" :disabled="busyAction !== ''">Iniciar</button>
          <button class="secondary" @click="serviceAction('restart')" :disabled="busyAction !== ''">Reiniciar</button>
          <button class="danger" @click="serviceAction('stop')" :disabled="busyAction !== ''">Parar</button>
        </div>
      </article>

      <article class="card">
        <h2>Ambiente</h2>
        <p><strong>SO:</strong> {{ environment?.os_name || '—' }}</p>
        <p><strong>Origem do Tor:</strong> {{ environment?.tor_source || '—' }}</p>
        <p><strong>Binário:</strong> <code>{{ environment?.tor_binary_path || 'não encontrado' }}</code></p>
        <p><strong>torrc:</strong> <code>{{ environment?.torrc_path || '—' }}</code></p>
        <p><strong>Logs:</strong> <code>{{ environment?.log_path || '—' }}</code></p>
      </article>
    </section>

    <section class="grid two stack-mobile">
      <article class="card">
        <h2>Configuração base do torrc</h2>
        <label>SOCKSPort <input v-model="configForm.SOCKSPort" /></label>
        <label>ControlPort <input v-model="configForm.ControlPort" /></label>
        <label>DataDirectory <input v-model="configForm.DataDirectory" /></label>
        <label>Log <input v-model="configForm.Log" /></label>
        <div class="actions">
          <button @click="saveConfig" :disabled="busyAction !== ''">Salvar torrc</button>
          <button class="secondary" @click="serviceAction('restart')" :disabled="busyAction !== ''">Reiniciar Tor</button>
        </div>
      </article>

      <article class="card">
        <h2>Preview do torrc</h2>
        <textarea class="torrc-preview" :value="rawTorrc" readonly />
      </article>
    </section>

    <section class="card">
      <div class="row-between wrap-mobile">
        <div>
          <h2>Onion services</h2>
          <p class="muted">Cria a pasta do onion, escreve <code>HiddenServiceDir</code> e <code>HiddenServicePort</code> no torrc e mostra o hostname quando o Tor gerar.</p>
        </div>
        <button class="secondary" @click="refreshHostnamesUntilReady" :disabled="busyAction !== '' || !onions.length">Atualizar hostnames</button>
      </div>

      <div class="grid four">
        <label>Nome da pasta <input v-model="onionForm.name" placeholder="meu-servico" /></label>
        <label>Porta pública <input v-model.number="onionForm.public_port" type="number" min="1" max="65535" /></label>
        <label>Host interno <input v-model="onionForm.target_host" placeholder="127.0.0.1" /></label>
        <label>Porta interna <input v-model.number="onionForm.target_port" type="number" min="1" max="65535" /></label>
      </div>

      <div class="actions">
        <button @click="createOnion" :disabled="busyAction !== ''">Criar onion</button>
        <button class="secondary" @click="serviceAction('restart')" :disabled="busyAction !== ''">Reiniciar Tor</button>
      </div>

      <div v-if="onions.length" class="onion-list">
        <div v-for="item in onions" :key="item.name" class="onion-item">
          <div class="onion-meta">
            <div class="row-between wrap-mobile">
              <strong>{{ item.name }}</strong>
              <span class="badge" :class="item.hostname_ready ? 'ok' : 'warn'">
                {{ item.hostname_ready ? 'hostname pronto' : 'hostname pendente' }}
              </span>
            </div>
            <p><code>{{ item.directory }}</code></p>
            <p>Publica {{ item.public_port }} → {{ item.target_host }}:{{ item.target_port }}</p>

            <div v-if="item.hostname_ready && item.hostname" class="hostname-box">
              <p><strong>Hostname:</strong></p>
              <code>{{ item.hostname }}</code>
              <div class="actions compact">
                <button class="secondary" @click="copyText(item.hostname, 'Hostname')">Copiar hostname</button>
                <button class="secondary" @click="copyText(item.hostname_path, 'Caminho do hostname')">Copiar caminho</button>
              </div>
            </div>

            <div v-else class="hostname-box pending">
              <p><strong>Hostname ainda não gerado.</strong></p>
              <p>Isso normalmente quer dizer uma destas coisas:</p>
              <ul>
                <li>o Tor ainda não iniciou com sucesso;</li>
                <li>a porta alvo não está acessível;</li>
                <li>o Tor subiu e caiu logo depois.</li>
              </ul>
              <p><strong>Arquivo esperado:</strong> <code>{{ item.hostname_path || `${item.directory}/hostname` }}</code></p>
            </div>
          </div>

          <div class="onion-actions">
            <button class="secondary" @click="copyText(item.directory, 'Pasta do onion')">Copiar pasta</button>
            <button class="danger" @click="deleteOnion(item.name)" :disabled="busyAction !== ''">Remover</button>
          </div>
        </div>
      </div>
      <p v-else>Nenhum onion cadastrado ainda.</p>
    </section>

    <section class="grid two stack-mobile">
      <article class="card">
        <div class="row-between">
          <h2>Diagnóstico</h2>
          <button class="secondary" @click="runDiagnostics" :disabled="busyAction !== ''">Rodar</button>
        </div>
        <ul class="diagnostics">
          <li v-for="check in diagnostics" :key="check.name">
            <strong>{{ check.ok ? 'OK' : 'Falhou' }}</strong> — {{ check.name }}<br />
            <span>{{ check.details }}</span>
          </li>
        </ul>
      </article>

      <article class="card">
        <h2>Logs recentes</h2>
        <pre class="logs">{{ logs.join('\n') }}</pre>
      </article>
    </section>
  </main>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #0f172a;
  color: #e5e7eb;
  font-family: Inter, Arial, sans-serif;
}
.page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
.hero, .row-between, .actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.wrap-mobile { flex-wrap: wrap; }
.grid {
  display: grid;
  gap: 16px;
}
.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.card {
  background: #111827;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 10px 30px rgba(0,0,0,.2);
}
label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 14px;
}
input, textarea, button {
  border-radius: 12px;
  border: 1px solid #475569;
  background: #0b1220;
  color: #e5e7eb;
  padding: 10px 12px;
}
button {
  cursor: pointer;
  background: #2563eb;
  border: none;
}
button.secondary { background: #374151; }
button.danger { background: #b91c1c; }
button:disabled { opacity: .6; cursor: not-allowed; }
.toast {
  background: #1d4ed8;
  padding: 12px 14px;
  border-radius: 12px;
}
.muted {
  color: #cbd5e1;
  margin-top: 0;
}
.torrc-preview, .logs {
  width: 100%;
  min-height: 280px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  box-sizing: border-box;
}
.onion-list {
  margin-top: 16px;
  display: grid;
  gap: 12px;
}
.onion-item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid #334155;
  border-radius: 14px;
  padding: 14px;
  background: #0b1220;
}
.onion-meta { flex: 1; }
.onion-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 140px;
}
.hostname-box {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: #111827;
  border: 1px solid #334155;
}
.hostname-box.pending {
  border-color: #92400e;
  background: rgba(146, 64, 14, 0.18);
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.badge.ok {
  background: rgba(22, 163, 74, 0.18);
  color: #86efac;
}
.badge.warn {
  background: rgba(217, 119, 6, 0.18);
  color: #fcd34d;
}
.compact { justify-content: flex-start; }
.diagnostics {
  padding-left: 18px;
}
pre, code { overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .two, .four { grid-template-columns: 1fr; }
  .stack-mobile { grid-template-columns: 1fr; }
  .onion-item { flex-direction: column; }
  .onion-actions { min-width: 0; }
}
</style>
