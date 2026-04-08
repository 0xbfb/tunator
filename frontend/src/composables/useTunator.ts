import { computed, reactive, ref } from 'vue'
import { api } from '../services/api'
import type { BackupItem, ConfigResponse, DiagnosticsPayload, EnvironmentResponse, LogEntry, OnionItem, StatusResponse } from '../types/api'

export function useTunator() {
  const loading = ref(false)
  const busyAction = ref('')
  const toast = ref('')
  const environment = ref<EnvironmentResponse | null>(null)
  const status = ref<StatusResponse | null>(null)
  const diagnostics = ref<DiagnosticsPayload | null>(null)
  const logs = ref<LogEntry[]>([])
  const rawTorrc = ref('')
  const onions = ref<OnionItem[]>([])
  const backups = ref<BackupItem[]>([])
  const configForm = reactive({ SOCKSPort: '9050', ControlPort: '9051', DataDirectory: '', Log: '', ExcludeNodes: '' })

  const pendingOnions = computed(() => onions.value.filter((item) => !item.hostname_ready))

  async function refreshAll() {
    loading.value = true
    try {
      const [env, st, cfg, logRes, backupsRes] = await Promise.all([
        api<EnvironmentResponse>('/api/environment'),
        api<StatusResponse>('/api/status'),
        api<ConfigResponse>('/api/config'),
        api<{ entries: LogEntry[] }>('/api/logs?limit=120'),
        api<{ items: BackupItem[] }>('/api/config/backups'),
      ])
      environment.value = env
      status.value = st
      rawTorrc.value = cfg.raw
      logs.value = logRes.entries
      diagnostics.value = st.latest_diagnostics || diagnostics.value
      onions.value = cfg.onion_services || []
      backups.value = backupsRes.items || []
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

  async function action(name: 'start'|'stop'|'restart') {
    busyAction.value = name
    try {
      const res = await api<{message:string}>(`/api/service/${name}`, { method: 'POST' })
      toast.value = res.message
      await refreshAll()
    } catch (err:any) { toast.value = err.message || String(err) }
    finally { busyAction.value = '' }
  }

  return { loading, busyAction, toast, environment, status, diagnostics, logs, rawTorrc, onions, backups, configForm, pendingOnions, refreshAll, action }
}
