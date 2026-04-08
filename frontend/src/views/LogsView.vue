<script setup lang="ts">
import type { LogEntry } from '../types/api'
defineProps<{ logs: LogEntry[] }>()
</script>
<template><article class="card"><h2>Logs recentes</h2><pre class="logs">{{ logs.map((entry) => `[${entry.level || 'info'}] ${entry.message || entry.raw}`).join('\n') }}</pre></article></template>
