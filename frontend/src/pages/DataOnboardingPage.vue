<template>
  <q-page class="dob">
    <div class="dob-head">
      <div class="dob-eyebrow">Workspace</div>
      <h1 class="dob-title">Data Onboarding</h1>
    </div>

    <div class="panel-card dob-card">
      <div class="dob-icon">
        <q-icon name="input" size="30px" />
      </div>
      <div class="dob-badge">Coming soon</div>
      <p class="dob-text">
        Bring data into ADIRRA from files, databases and cloud storage — the entry point that feeds
        everything else in the workspace.
      </p>
    </div>
  </q-page>
</template>

<script setup lang="ts"></script>

<style scoped>
.dob {
  --accent: #0d5c54;
  --paper: #f6f4f0;
  --card-bg: rgba(255, 253, 248, 0.62);
  --border: #ddd6c8;
  --text: #1c1b18;
  --text-2: #86827a;

  background: var(--paper);
  color: var(--text);
  padding: 18px 20px 28px;
  flex-shrink: 0;
}

.dob-eyebrow {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--text-2);
}
.dob-title {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -.01em;
  margin: 2px 0 16px;
  line-height: 1.2;
}

.panel-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.dob-card {
  padding: 52px 24px;
  text-align: center;
}

.dob-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
  margin: 0 auto;
  border-radius: 50%;
  background: rgba(13, 92, 84, .09);
  color: var(--accent);
}

.dob-badge {
  display: inline-block;
  margin: 14px 0 10px;
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  color: #fdfffe;
  background: linear-gradient(160deg, #16887c 0%, var(--accent) 55%, #0a4a43 100%);
  box-shadow: 0 3px 10px -2px rgba(13, 92, 84, .45), inset 0 1px 0 rgba(255, 255, 255, .28);
}

.dob-text {
  font-size: 13px;
  color: var(--text-2);
  max-width: 54ch;
  margin: 0 auto;
  line-height: 1.6;
}
</style>
