<template>
  <div class="section-card q-mb-md">
    <div class="row items-center q-mb-md">
      <span class="section-label">{{ label }}</span>
      <q-badge v-if="aiGenerated" class="q-ml-sm ai-badge" outline>
        <q-icon name="bolt" size="12px" class="q-mr-xs" />AI-generated
      </q-badge>
      <q-space />
      <q-btn
        v-if="showGenerate"
        flat dense size="sm" no-caps
        :label="generateLabel || 'Generate'"
        icon="auto_awesome"
        color="primary"
        :loading="generating"
        @click="$emit('generate')"
        class="q-mr-xs"
      />
      <q-btn flat dense size="sm" icon="content_copy" color="grey-6" @click="$emit('copy')" />
      <q-btn v-if="showEditButton" flat dense size="sm" icon="edit" color="primary" @click="$emit('edit')" />
    </div>

    <template v-if="!editing">
      <div class="section-body" :class="{ 'text-grey-5': !value }">
        {{ value || 'Not set.' }}
      </div>
      <div v-if="aiGenerated" class="text-caption text-grey-5 q-mt-xs">
        AI-generated draft. Validate before use.
      </div>
    </template>

    <template v-else>
      <q-input
        :model-value="value"
        type="textarea"
        outlined dense
        rows="4"
        class="q-mt-sm"
        @update:model-value="editValue = String($event)"
      />
      <div class="row q-gutter-sm justify-end q-mt-sm">
        <q-btn flat dense label="Cancel" color="grey-7" @click="$emit('cancel')" />
        <q-btn flat dense label="Save" color="primary" @click="$emit('save', editValue)" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps<{
  label: string;
  value: string;
  aiGenerated?: boolean;
  editing?: boolean;
  generating?: boolean;
  showGenerate?: boolean;
  showEditButton?: boolean;
  generateLabel?: string;
}>();

defineEmits<{
  edit: [];
  save: [value: string];
  cancel: [];
  copy: [];
  generate: [];
}>();

const editValue = ref(props.value);

watch(() => props.value, (v) => {
  editValue.value = v;
});

watch(() => props.editing, (isEditing) => {
  if (isEditing) editValue.value = props.value;
});
</script>

<style scoped lang="scss">
.section-card {
  border-bottom: 1px solid #eee;
  padding-bottom: 16px;
}

.section-label {
  font-weight: 700;
  font-size: 14px;
  color: #2b2a31;
}

.section-body {
  font-size: 14px;
  line-height: 1.6;
  color: #2b2a31;
  white-space: pre-wrap;
}

.ai-badge {
  color: #c2410c !important;
  border-color: #fed7aa !important;
  background: #fff7ed !important;
  font-size: 11px;
  font-weight: 600;
}
</style>
