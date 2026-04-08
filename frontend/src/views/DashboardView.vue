<script setup lang="ts">
import type { EnvironmentResponse, StatusResponse } from '../types/api'
defineProps<{ environment: EnvironmentResponse | null; status: StatusResponse | null; busyAction: string }>()
const emit = defineEmits<{ (e:'action', value:'start'|'stop'|'restart'):void }>()
</script>

<template>
  <section class="grid two">
    <article class="card">
      <h2>Status</h2>
      <p><strong>Serviço:</strong> {{ status?.status || (status?.running ? 'running' : 'stopped') }}</p>
      <p><strong>Mensagem:</strong> {{ status?.message || '—' }}</p>
      <p><strong>PID:</strong> {{ status?.pid ?? '—' }}</p>
      <p><strong>Versão Tor:</strong> {{ status?.tor_version || '—' }}</p>
      <p><strong>Bootstrap:</strong> {{ status?.bootstrap_progress ?? '—' }}%</p>
      <div class="actions">
        <button @click="emit('action','start')" :disabled="busyAction !== ''">Iniciar</button>
        <button class="secondary" @click="emit('action','restart')" :disabled="busyAction !== ''">Reiniciar</button>
        <button class="danger" @click="emit('action','stop')" :disabled="busyAction !== ''">Parar</button>
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
</template>
