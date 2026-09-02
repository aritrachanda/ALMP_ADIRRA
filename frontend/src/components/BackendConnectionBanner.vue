<template>
  <div v-if="!connectivity.backendUp" class="backend-conn-banner" role="alert">
    <span class="backend-conn-pulse" aria-hidden="true">
      <span class="pulse-ring"></span>
      <span class="pulse-ring pulse-ring--delay"></span>
      <span class="pulse-dot"></span>
    </span>
    <span class="backend-conn-text">
      Sorry! Backend server is down — this banner will keep checking every 10s and be cleared when
      the server is up and running!
    </span>
  </div>
</template>

<script setup lang="ts">
import { useConnectivityStore } from 'src/stores/connectivityStore';

const connectivity = useConnectivityStore();
</script>

<style scoped>
.backend-conn-banner {
  position: sticky;
  top: 0;
  left: 0;
  right: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--adirra-danger);
  color: #fff;
}

.backend-conn-pulse {
  position: relative;
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.pulse-dot {
  position: relative;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  z-index: 1;
}

.pulse-ring {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid #fff;
  opacity: 0;
  animation: backend-conn-pulse-ring 1.8s ease-out infinite;
}

.pulse-ring--delay {
  animation-delay: 0.9s;
}

@keyframes backend-conn-pulse-ring {
  0% {
    transform: scale(1);
    opacity: 0.8;
  }
  100% {
    transform: scale(3.2);
    opacity: 0;
  }
}

.backend-conn-text {
  font-size: 13px;
  font-weight: 600;
}

@media (prefers-reduced-motion: reduce) {
  .pulse-ring {
    animation: none;
    opacity: 0;
  }
}
</style>

