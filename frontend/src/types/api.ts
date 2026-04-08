export type DiagnosticItem = { name: string; ok: boolean; details: string; recommendation?: string | null }
export type DiagnosticsPayload = { run_id?: string | null; checked_at?: string; source?: string; freshness?: string; checks: DiagnosticItem[] }
export type StatusResponse = {
  running: boolean
  source: string
  message: string
  pid?: number | null
  run_id?: string | null
  status?: string
  phase?: string
  managed_by_tunator?: boolean
  control_connected?: boolean
  control_authenticated?: boolean
  tor_version?: string | null
  bootstrap_phase?: string | null
  bootstrap_progress?: number | null
  latest_diagnostics?: DiagnosticsPayload | null
}
export type EnvironmentResponse = {
  os_name: string
  tor_installed: boolean
  tor_source: string
  tor_binary_path?: string | null
  torrc_path?: string | null
  log_path?: string | null
  bundle_download_url?: string | null
}
export type OnionItem = {
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
export type ConfigResponse = { raw: string; base_options: Record<string, string>; onion_services: OnionItem[] }
export type LogEntry = { raw: string; observed_at: string; timestamp?: string | null; level?: string | null; source?: string; message?: string | null }
export type BackupItem = { name: string; path: string; size_bytes: number; created_at: string }
