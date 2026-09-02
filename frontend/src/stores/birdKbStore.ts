import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { BirdGroup, BirdEntity, BirdEntityDetail, GraphData, ChainHop, TableData } from 'src/api/bird';
import * as api from 'src/api/bird';

export const useBirdKbStore = defineStore('birdKb', () => {
  const selectedLayer = ref<string>('LDM');
  const selectedFramework = ref<string>('All');
  const selectedGroup = ref<BirdGroup | null>(null);
  const selectedEntity = ref<BirdEntity | null>(null);

  const groups = ref<BirdGroup[]>([]);
  const entities = ref<BirdEntity[]>([]);
  const entityDetail = ref<BirdEntityDetail | null>(null);
  const graphData = ref<GraphData>({ nodes: [], edges: [], level: 1 });
  const chainData = ref<ChainHop[]>([]);
  const chainVisible = ref(false);
  const tableData = ref<TableData>({ rows: [], total: 0, capped: false });

  const loadingGroups = ref(false);
  const loadingEntities = ref(false);
  const loadingDetail = ref(false);
  const loadingGraph = ref(false);
  const loadingChain = ref(false);
  const loadingTable = ref(false);

  // AI assistant page-context payload
  const pageContext = computed(() => ({
    module: 'bird-kb',
    layer: selectedLayer.value,
    framework: selectedFramework.value,
    group_id: selectedGroup.value?.cube_group_id ?? null,
    group_name: selectedGroup.value?.name ?? null,
    entity_id: selectedEntity.value?.cube_id ?? null,
    entity_name: selectedEntity.value?.name ?? null,
  }));

  async function loadGroups() {
    loadingGroups.value = true;
    try {
      groups.value = await api.getGroups(selectedLayer.value, selectedFramework.value);
    } finally {
      loadingGroups.value = false;
    }
  }

  async function loadGraph(groupId?: string) {
    loadingGraph.value = true;
    try {
      graphData.value = await api.getGraph(selectedLayer.value, groupId, selectedFramework.value);
    } finally {
      loadingGraph.value = false;
    }
  }

  async function selectLayer(layer: string) {
    selectedLayer.value = layer;
    selectedGroup.value = null;
    selectedEntity.value = null;
    entityDetail.value = null;
    chainData.value = [];
    chainVisible.value = false;
    entities.value = [];
    await Promise.all([loadGroups(), loadGraph()]);
  }

  async function selectFramework(framework: string) {
    selectedFramework.value = framework;
    selectedGroup.value = null;
    selectedEntity.value = null;
    entityDetail.value = null;
    chainData.value = [];
    chainVisible.value = false;
    entities.value = [];
    await Promise.all([loadGroups(), loadGraph()]);
  }

  async function selectGroup(group: BirdGroup) {
    selectedGroup.value = group;
    selectedEntity.value = null;
    entityDetail.value = null;
    chainData.value = [];
    chainVisible.value = false;
    loadingEntities.value = true;
    try {
      entities.value = await api.getEntities(group.cube_group_id, selectedLayer.value, selectedFramework.value);
    } finally {
      loadingEntities.value = false;
    }
    await loadGraph(group.cube_group_id);
  }

  async function selectEntity(entity: BirdEntity) {
    selectedEntity.value = entity;
    chainVisible.value = false;
    loadingDetail.value = true;
    try {
      entityDetail.value = await api.getEntityDetail(entity.cube_id);
    } finally {
      loadingDetail.value = false;
    }
  }

  async function loadChain() {
    if (!selectedEntity.value) return;
    chainVisible.value = true;
    loadingChain.value = true;
    try {
      const result = await api.getChain(selectedEntity.value.cube_id);
      chainData.value = result.chain;
    } finally {
      loadingChain.value = false;
    }
  }

  async function loadTable() {
    loadingTable.value = true;
    try {
      tableData.value = await api.getTable({
        layer: selectedLayer.value,
        group: selectedGroup.value?.cube_group_id,
        framework: selectedFramework.value !== 'All' ? selectedFramework.value : undefined,
      });
    } finally {
      loadingTable.value = false;
    }
  }

  function clearSelection() {
    selectedGroup.value = null;
    selectedEntity.value = null;
    entityDetail.value = null;
    chainData.value = [];
    chainVisible.value = false;
  }

  return {
    selectedLayer, selectedFramework, selectedGroup, selectedEntity,
    groups, entities, entityDetail,
    graphData, chainData, chainVisible,
    tableData, loadingTable,
    loadingGroups, loadingEntities, loadingDetail, loadingGraph, loadingChain,
    pageContext,
    loadGroups, loadGraph, selectLayer, selectFramework, selectGroup, selectEntity,
    loadChain, loadTable, clearSelection,
  };
});
