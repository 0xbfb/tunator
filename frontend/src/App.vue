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
  auth_enabled?: boolean
  auth_client_name?: string | null
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
  ExcludeNodes: '',
})
const onionForm = reactive({
  name: '',
  public_port: 80,
  target_host: '127.0.0.1',
  target_port: 3000,
  access_password: '',
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
    configForm.ExcludeNodes = cfg.base_options.ExcludeNodes || ''
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
      ExcludeNodes: configForm.ExcludeNodes,
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
    onionForm.access_password = ''
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
        <h1 class="title">Tunator</h1>
        <p class="subtitle">Painel local pra mexer no Tor sem ter que brigar com o torrc na mão.</p>
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
        <p><strong>Origem:</strong> {{ status?.source || '—' }}</p>
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
        <div class="country-blacklist">
          <span>Blacklist de países</span>
          <div class="country-chips">
            <button
              v-for="option in countryBlacklistOptions"
              :key="option.code"
              type="button"
              class="secondary chip"
              :class="{ active: selectedCountryBlacklist.includes(option.code) }"
              @click="toggleCountryBlacklist(option.code)"
            >
              {{ option.label }} ({{ option.code.toUpperCase() }})
            </button>
          </div>
        </div>
        <label>ExcludeNodes (avançado) <input v-model="configForm.ExcludeNodes" placeholder="{ru},{cn},{kp}" @blur="syncCountriesFromExcludeNodes" /></label>
        <p class="muted tiny">Use códigos ISO em chaves, separados por vírgula. Ex.: <code>{ru},{cn}</code></p>
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
        <label>Senha de acesso (opcional) <input v-model="onionForm.access_password" type="password" placeholder="mínimo 6 caracteres" /></label>
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
            <p v-if="item.auth_enabled"><strong>Acesso:</strong> protegido por senha (cliente: <code>{{ item.auth_client_name }}</code>)</p>

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
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');

:global(body) {
  margin: 0;
  background:
    radial-gradient(circle at 20% 10%, rgba(26, 94, 130, 0.35) 0%, rgba(7, 21, 39, 0.88) 38%, #02060d 100%),
    linear-gradient(180deg, #030811 0%, #02060d 100%);
  color: #d8f8ff;
  font-family: 'Rajdhani', 'Inter', Arial, sans-serif;
  font-size: 18px;
  line-height: 1.4;
}
.page {
  max-width: 1320px;
  margin: 0 auto;
  padding: 30px 28px 44px;
  position: relative;
}
.page::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    repeating-linear-gradient(
      180deg,
      rgba(132, 224, 255, 0.06) 0,
      rgba(132, 224, 255, 0.06) 1px,
      transparent 1px,
      transparent 3px
    );
  mix-blend-mode: screen;
  opacity: 0.2;
}
.hero, .row-between, .actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.hero {
  margin-bottom: 18px;
  border: 1px solid rgba(90, 219, 255, 0.26);
  border-radius: 14px;
  padding: 16px 18px;
  background: linear-gradient(130deg, rgba(9, 31, 47, 0.75), rgba(4, 16, 28, 0.65));
}
.title {
  margin: 0;
  font-size: clamp(2.1rem, 3vw, 2.8rem);
  letter-spacing: 0.14em;
}
.subtitle {
  margin: 6px 0 0;
  color: #9ad8e9;
  letter-spacing: 0.04em;
  font-size: 1.02rem;
}
.wrap-mobile { flex-wrap: wrap; }
.grid {
  display: grid;
  gap: 20px;
}
.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.card {
  background: linear-gradient(165deg, rgba(8, 22, 38, 0.9), rgba(4, 12, 24, 0.95));
  border: 1px solid rgba(90, 219, 255, 0.3);
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 0 0 1px rgba(46, 197, 255, 0.08), 0 14px 36px rgba(0, 0, 0, 0.42), inset 0 0 36px rgba(26, 107, 168, 0.12);
  backdrop-filter: blur(3px);
}
p {
  margin: 8px 0;
  line-height: 1.45;
}
label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 0.96rem;
  letter-spacing: 0.04em;
  color: #b4ecfa;
}
input, textarea, button {
  border-radius: 10px;
  border: 1px solid rgba(91, 211, 255, 0.34);
  background: rgba(2, 10, 20, 0.85);
  color: #def6ff;
  padding: 11px 12px;
  font-family: 'Rajdhani', 'Inter', Arial, sans-serif;
  font-size: 0.98rem;
  letter-spacing: 0.03em;
}
input:focus, textarea:focus {
  outline: none;
  border-color: #5eddff;
  box-shadow: 0 0 0 2px rgba(94, 221, 255, 0.22);
}
button {
  cursor: pointer;
  background: linear-gradient(90deg, #1b9bff, #14d4ff);
  color: #02111f;
  font-weight: 700;
  border: none;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  padding: 10px 14px;
}
button.secondary { background: linear-gradient(90deg, #19334a, #225a80); color: #d9f7ff; }
button.danger { background: linear-gradient(90deg, #96231f, #d84f2a); color: #fff4eb; }
button:disabled { opacity: .6; cursor: not-allowed; }
.toast {
  background: linear-gradient(90deg, rgba(24, 74, 120, 0.95), rgba(19, 153, 187, 0.95));
  border: 1px solid rgba(103, 228, 255, 0.4);
  padding: 12px 14px;
  border-radius: 12px;
  margin-bottom: 18px;
  letter-spacing: 0.04em;
}
.muted {
  color: #9cd8eb;
  margin-top: 0;
  line-height: 1.5;
}
.torrc-preview, .logs {
  width: 100%;
  min-height: 280px;
  font-family: 'Share Tech Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  box-sizing: border-box;
  font-size: 0.95rem;
  line-height: 1.42;
}
.onion-list {
  margin-top: 20px;
  display: grid;
  gap: 14px;
}
.onion-item {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  border: 1px solid rgba(75, 197, 255, 0.25);
  border-radius: 14px;
  padding: 16px;
  background: rgba(2, 10, 20, 0.88);
}
.onion-meta { flex: 1; }
.onion-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 140px;
}
.hostname-box {
  margin-top: 14px;
  padding: 14px;
  border-radius: 12px;
  background: #111827;
  border: 1px solid rgba(75, 197, 255, 0.25);
}
.hostname-box.pending {
  border-color: #bf6a2e;
  background: rgba(191, 106, 46, 0.2);
}
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.badge.ok {
  background: rgba(18, 165, 144, 0.22);
  color: #86fff0;
}
.badge.warn {
  background: rgba(214, 104, 47, 0.24);
  color: #ffd4a8;
}
.compact { justify-content: flex-start; }
.diagnostics {
  padding-left: 18px;
  margin: 10px 0 0;
  display: grid;
  gap: 10px;
}
pre, code {
  overflow-wrap: anywhere;
  font-family: 'Share Tech Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.94rem;
}
h1, h2 {
  letter-spacing: 0.11em;
  text-transform: uppercase;
  margin: 0 0 12px;
  line-height: 1.2;
}
h2 {
  font-size: 1.15rem;
  color: #c9f6ff;
}
.country-blacklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
}
.country-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
button.chip {
  padding: 8px 10px;
  font-size: 12px;
}
button.chip.active {
  background: linear-gradient(90deg, #1b9bff, #14d4ff);
  color: #02111f;
}
.tiny { font-size: 0.78rem; margin-top: -2px; line-height: 1.45; }
@media (max-width: 900px) {
  .two, .four { grid-template-columns: 1fr; }
  .stack-mobile { grid-template-columns: 1fr; }
  .onion-item { flex-direction: column; }
  .onion-actions { min-width: 0; }
  .page { padding: 22px 16px 30px; }
  .hero { padding: 14px; }
}
</style>
