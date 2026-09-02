<template>
  <div ref="graphContainer" style="width: 100%; height: 600px; border: 1px solid #e0e0e0; border-radius: 8px; background: #fff;" />
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue';
import { Network } from 'vis-network';
import { DataSet } from 'vis-data';
import type { MappingResult } from 'src/types';

const props = defineProps<{ mapping: MappingResult }>();

const graphContainer = ref<HTMLElement | null>(null);
let network: Network | null = null;

const CONF_HIGH = 0.7;
const CONF_MED = 0.4;

function confidenceColor(c: number): string {
  if (c >= CONF_HIGH) return '#16a34a';
  if (c >= CONF_MED) return '#ca8a04';
  return '#b91c1c';
}

function buildGraph() {
  if (!graphContainer.value || !props.mapping) return;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodesMap: Record<string, any> = {};
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edgesList: any[] = [];
  // Track edge counts per pair for curving
  const pairCounts: Record<string, number> = {};
  const pairIndex: Record<string, number> = {};

  for (const mt of props.mapping.tables) {
    if (mt.status === 'discarded') continue;
    const tgtId = `tgt::${mt.target_schema}.${mt.target_table}`;
    if (!nodesMap[tgtId]) {
      nodesMap[tgtId] = {
        id: tgtId,
        label: mt.target_table + (mt.columns ? `\n(${mt.columns.length} cols)` : ''),
        title: `Target: ${mt.target_schema}.${mt.target_table}`,
        group: 'target',
      };
    }

    for (const col of mt.columns) {
      if (col.status === 'discarded' || !col.source_table) continue;

      const srcId = `src::${col.source_schema ?? ''}.${col.source_table}`;
      if (!nodesMap[srcId]) {
        nodesMap[srcId] = {
          id: srcId,
          label: col.source_table,
          title: `Source: ${col.source_schema ?? ''}.${col.source_table}`,
          group: 'source',
        };
      }

      const pairKey = `${srcId}||${tgtId}`;
      pairCounts[pairKey] = (pairCounts[pairKey] || 0) + 1;

      const conf = col.confidence ?? 0;
      const confStr = ` (${(conf * 100).toFixed(0)}%)`;
      edgesList.push({
        from: srcId,
        to: tgtId,
        color: { color: confidenceColor(conf) },
        title: `${col.source_column ?? '?'} → ${col.target_column}${confStr}`,
        _pairKey: pairKey,
      });
    }
  }

  // Assign roundness for parallel edges
  for (const e of edgesList) {
    const count = pairCounts[e._pairKey];
    const idx = pairIndex[e._pairKey] ?? 0;
    pairIndex[e._pairKey] = idx + 1;
    if (count === 1) {
      e.smooth = { type: 'curvedCW', roundness: 0 };
    } else {
      const roundness = -0.5 + (idx / (count - 1));
      e.smooth = { type: 'curvedCW', roundness: Math.round(roundness * 1000) / 1000 };
    }
    delete e._pairKey;
  }

  // Position nodes: sources left (x=0), targets right (x=600)
  const srcNodes = Object.values(nodesMap).filter((n) => n.group === 'source');
  const tgtNodes = Object.values(nodesMap).filter((n) => n.group === 'target');
  srcNodes.forEach((n, i) => { n.x = 0; n.y = i * 100; n.fixed = true; });
  tgtNodes.forEach((n, i) => { n.x = 600; n.y = i * 100; n.fixed = true; });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodes = new DataSet<any>(Object.values(nodesMap));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const edges = new DataSet<any>(edgesList);

  network?.destroy();
  network = new Network(graphContainer.value, { nodes, edges }, {
    groups: {
      source: { color: { background: '#3b82f6', border: '#2563eb' }, font: { color: '#fff', size: 14 }, shape: 'box', margin: 10 },
      target: { color: { background: '#898989', border: '#6b6b6b' }, font: { color: '#fff', size: 14 }, shape: 'box', margin: 10 },
    },
    layout: { improvedLayout: false },
    physics: false,
    edges: { arrows: { to: { enabled: true, scaleFactor: 0.8 } }, font: { size: 0 } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
  });

  network.once('afterDrawing', () => {
    network?.fit({ animation: false });
  });
}

onMounted(buildGraph);
watch(() => props.mapping, buildGraph, { deep: true });
onBeforeUnmount(() => network?.destroy());
</script>
