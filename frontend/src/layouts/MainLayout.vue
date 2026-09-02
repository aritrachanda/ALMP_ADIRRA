<template>
  <q-layout view="hHh LpR fFf" class="main-layout-gradient">
    <BackendConnectionBanner />
    <TopMenu />

    <q-drawer
      v-model="sidebarOpen"
      :width="280"
      :mini-width="56"
      :mini="miniState"
      :breakpoint="0"
      class="sidebar-gradient"
      side="left"
      show-if-above
      :style="{ background: 'linear-gradient(180deg, #0a4a5c 0%, #0d2e4d 100%)' }"
    >
      <SideMenu :mini="miniState" @toggle-mini="miniState = !miniState" />
    </q-drawer>

    <q-page-container>
      <div class="page-content-wrapper">
        <router-view />
      </div>
    </q-page-container>

    <AylinFloater />
  </q-layout>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import TopMenu from 'src/components/TopMenu.vue';
import SideMenu from 'src/components/SideMenu.vue';
import AylinFloater from 'src/components/AylinFloater.vue';
import BackendConnectionBanner from 'src/components/BackendConnectionBanner.vue';
import { useConnectivityStore } from 'src/stores/connectivityStore';

const sidebarOpen = ref(true);
const miniState = ref(false); // expanded by default on every load

const connectivity = useConnectivityStore();
onMounted(() => connectivity.startPolling());
onBeforeUnmount(() => connectivity.stopPolling());
</script>
