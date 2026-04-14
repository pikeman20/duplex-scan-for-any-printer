<template src="./Dashboard.html"></template>
<style scoped src="./Dashboard.css"></style>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import type { Ref } from 'vue';
// Import existing stores
import { useScansStore } from '@/stores/scans';

// Status refresh interval (30 seconds)
const STATUS_REFRESH_INTERVAL = 30000;

// Initialize stores
const scansStore = useScansStore();

// Timer for periodic updates
const statusTimer = ref<NodeJS.Timeout | null>(null);

// Computed properties for status classes
const botStatusClass = computed(() => {
  if (!scansStore.botStatus) return 'disconnected';
  return scansStore.botStatus.connected ? 'connected' : 'disconnected';
});

const botStatusText = computed(() => {
  if (!scansStore.botStatus) return 'Unknown';
  return scansStore.botStatus.connected ? 'Connected' : 'Disconnected';
});

const sessionStatusClass = computed(() => {
  if (!scansStore.sessionStatus) return 'disconnected';
  const state = scansStore.sessionStatus.state;
  if (state === 'WAIT_CONFIRM') return 'waiting';
  if (state === 'CONFIRMED' || state === 'REJECTED') return 'connected';
  return 'disconnected';
});

const sessionStatusText = computed(() => {
  if (!scansStore.sessionStatus) return 'Unknown';
  const state = scansStore.sessionStatus.state;
  if (state === 'WAIT_CONFIRM') return 'Waiting';
  if (state === 'CONFIRMED') return 'Confirmed';
  if (state === 'REJECTED') return 'Rejected';
  return 'Idle';
});

// Refresh status
const refreshStatus = () => {
  scansStore.fetchBotStatus();
  scansStore.fetchSessionStatus();
};

// Open bot config (placeholder for now)
const openBotConfig = () => {
  alert('Bot configuration would open here');
};

// Set up periodic updates
onMounted(() => {
  // Fetch initial status
  refreshStatus();

  // Set up periodic updates
  statusTimer.value = setInterval(() => {
    refreshStatus();
  }, STATUS_REFRESH_INTERVAL);
});

onBeforeUnmount(() => {
  if (statusTimer.value) {
    clearInterval(statusTimer.value);
  }
});
</script>