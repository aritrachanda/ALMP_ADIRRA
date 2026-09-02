<template>
  <q-page class="about-page">
    <!-- Hero -->
    <div class="about-hero">
      <div class="about-kicker">Product position</div>
      <h2>ADIRRA, starting with governance and target alignment.</h2>
      <p>
        The current product is best understood as the first operational slice of a broader data management direction:
        understand source data, attach business meaning, connect regulatory context, and generate reviewable mapping outputs through a set of specialised agents rather than one generic assistant.
      </p>
      <div class="chip-row">
        <span v-for="c in chips" :key="c" class="about-chip">{{ c }}</span>
      </div>
    </div>

    <!-- What the app does today -->
    <div class="about-section">
      <h3>What the app already does today</h3>
      <p>
        The most credible story is the one the user can verify directly in the interface.
        The app already supports a practical flow from source understanding to governed meaning and target-model alignment.
      </p>
    </div>

    <div class="about-grid">
      <div v-for="card in capCards" :key="card.title" class="about-card" :class="card.colorClass">
        <h4>{{ card.title }}</h4>
        <p>{{ card.description }}</p>
      </div>
    </div>

    <div class="about-section q-mt-lg">
      <h3>What makes the product agentic</h3>
      <p>
        The app has an actual agent roster behind the product surfaces. FastAPI routes and page actions call specialised
        agents for chat orchestration, glossary enrichment, catalog description generation, target mapping, and CRR or DPM retrieval.
        Those agents share the same catalogs, glossary terms, mappings, project configuration, and retrieval indexes.
      </p>
    </div>

    <div class="agent-grid">
      <div v-for="agent in agentCards" :key="agent.title" class="about-card agent-card" :class="agent.colorClass">
        <div class="agent-topline">{{ agent.surface }}</div>
        <h4>{{ agent.title }}</h4>
        <p>{{ agent.description }}</p>
      </div>
    </div>

    <!-- Two-column info -->
    <div class="two-col q-mt-lg">
      <div class="about-strip">
        <h4>How the agents are orchestrated today</h4>
        <p>
          Agentic behavior in the current app is explicit. Pages and routes trigger focused agents, the chat layer orchestrates
          tool usage across multiple knowledge sources, and mapping runs can stream progress while persisting outputs for review.
        </p>
        <ul>
          <li>Chat uses an orchestrator agent to reach glossary, source, target, mapping, CRR, DPM, query, and chart tools.</li>
          <li>Glossary and catalog pages invoke specialist agents that enrich persistent artefacts rather than returning throwaway text.</li>
          <li>Mapping routes invoke mapping agents that write reviewable YAML outputs and can stream structured progress events.</li>
          <li>Human review still remains central through statuses, rationale, related objects, and visible outputs.</li>
        </ul>
      </div>
      <div class="about-strip">
        <h4>How policy and regulation bound the agents</h4>
        <p>
          The product story is stronger when the agent layer is described as operating within explicit governance boundaries.
          In practice, that means data handling rules, review gates, and regulatory context are part of execution, not separate documentation.
        </p>
        <ul>
          <li>Agent actions should sit inside policy boundaries for classification, sensitive-data handling, and approval checkpoints.</li>
          <li>GDPR and similar obligations matter here because discovery and enrichment can surface personal and restricted data indicators.</li>
          <li>The EU AI Act is relevant because the governance value of ADIRRA depends on explainability, human oversight, and auditable agent behavior.</li>
          <li>CRR, DPM, and BIRD grounding keep regulatory outputs tied to formal reporting context rather than generic AI-generated language.</li>
        </ul>
      </div>
    </div>

    <div class="about-strip q-mt-lg">
      <h4>How the architecture is connected</h4>
      <p>
        The architectural connection is shared context. Discovery, catalog, glossary, mapping, and regulatory retrieval
        all feed and consume the same project assets, which is what makes the agent system coherent instead of fragmented.
      </p>
      <ul>
        <li>Source and target catalogs provide the technical substrate for enrichment and mapping agents.</li>
        <li>Glossary YAML and mapping YAML persist outputs so agents build on prior work instead of starting from zero.</li>
        <li>CRR and DPM RAG indexes supply regulation and reporting-model grounding to chat and glossary enrichment.</li>
        <li>FastAPI routes connect the frontend pages to these specialised services in a controlled, inspectable way.</li>
      </ul>
    </div>

    <div class="about-strip q-mt-lg">
      <h4>Where the broader ADIRRA direction goes next</h4>
      <p>
        The next stage should look more like a fuller data management platform, not just more generic workflow polish.
        That means expanding from governance and mapping into the operational disciplines that data teams expect to manage together.
      </p>
      <ul>
        <li>Data quality checks, exception handling, and remediation workflows</li>
        <li>Reference data management and controlled business vocabularies</li>
        <li>Data architecture views across domains, systems, and downstream usage</li>
        <li>Data modelling support for target structures, semantic alignment, and change impact</li>
      </ul>
    </div>

    <!-- Tech stack -->
    <div class="about-section q-mt-lg q-mb-xl">
      <h3>Technology Stack</h3>
      <div class="chip-row q-mt-sm">
        <span v-for="t in techStack" :key="t" class="about-chip">{{ t }}</span>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
const chips = ['Discovery', 'Data Catalog', 'Business Glossary', 'Mapping', 'Dashboard', 'Settings'];

const capCards = [
  { title: 'Discovery and source understanding', description: 'Connected datasets can be profiled and explored so the technical starting point is visible before any governance or mapping work begins.', colorClass: 'card-blue' },
  { title: 'Catalog and glossary alignment', description: 'Technical metadata and business definitions are brought closer together through descriptions, related objects, categories, and regulatory context.', colorClass: 'card-green' },
  { title: 'AI-assisted mapping', description: 'Mappings into targets such as BIRD and CRDM are generated with confidence and rationale so they can be reviewed, refined, and challenged.', colorClass: 'card-amber' },
  { title: 'Management surfaces', description: 'Dashboard and Settings make the current working set visible through coverage views, export options, integrations outlook, and import controls.', colorClass: 'card-rose' },
];

const agentCards = [
  { title: 'Chat orchestrator agent', surface: 'Chat', description: 'Routes conversational requests to specialised tools and knowledge sources instead of relying on one undirected prompt.', colorClass: 'card-blue' },
  { title: 'Mapping agent', surface: 'Mapping', description: 'Generates generic source-to-target mapping proposals with confidence, rationale, and transformation hints.', colorClass: 'card-amber' },
  { title: 'BIRD mapping agent', surface: 'Mapping variant', description: 'Adds BIRD-specific prompting and framework grounding for regulated target alignment work.', colorClass: 'card-rose' },
  { title: 'Glossary agent', surface: 'Glossary', description: 'Handles glossary CRUD, AI drafting, cross-references, and regulatory-context enrichment for terms.', colorClass: 'card-green' },
  { title: 'Catalog agent', surface: 'Data Catalog', description: 'Generates business descriptions and mapping instructions for discovered schema elements.', colorClass: 'card-blue' },
  { title: 'CRR retrieval agent', surface: 'Glossary + Chat', description: 'Brings CRR3 article context into the app through semantic retrieval over regulation text.', colorClass: 'card-rose' },
  { title: 'DPM retrieval agent', surface: 'Glossary + Chat', description: 'Brings DPM datapoint, table, and cell context into enrichment and chat workflows.', colorClass: 'card-amber' },
];

const techStack = ['Vue 3', 'Quasar 2', 'TypeScript', 'Vite', 'FastAPI', 'Python', 'Google Gemini', 'OpenAI', 'DuckDB', 'Chart.js'];
</script>

<style lang="scss" scoped>
.about-page {
  padding: 1.5rem;
  background: #fdfdfd;
}

.about-hero {
  padding: 1.2rem 1.25rem;
  border-radius: 20px;
  border: 1px solid #bfdbfe;
  background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 48%, #fff7ed 100%);
  margin-bottom: 1rem;

  h2 { margin: 0; color: #0f172a; font-size: 1.4rem; }
  p { margin: 0.5rem 0 0; color: #475569; }
}

.about-kicker {
  display: inline-block;
  padding: 0.24rem 0.6rem;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  margin-bottom: 0.8rem;
}

.chip-row {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.9rem;
}

.about-chip {
  padding: 0.28rem 0.62rem;
  border-radius: 999px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  color: #334155;
  font-size: 0.8rem;
  font-weight: 600;
}

.about-section {
  margin-top: 1rem;
  padding: 1rem 0;

  h3 {
    margin: 0 0 0.5rem;
    color: #0f172a;
    font-size: 1.18rem;
    line-height: 1.25;
    font-weight: 700;
  }
  p { margin: 0; color: #475569; }
}

.about-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem;
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem;
}

.about-card {
  padding: 1rem;
  border-radius: 18px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);

  h4 { margin: 0 0 0.5rem; color: #0f172a; font-size: 0.95rem; }
  p { margin: 0; color: #475569; font-size: 0.9rem; line-height: 1.6; }
}

.agent-card h4 {
  margin-top: 0;
}

.agent-topline {
  display: inline-flex;
  align-items: center;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #d7e3ef;
  color: #334155;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  margin-bottom: 0.6rem;
}

.card-blue { background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%); border-color: #bfdbfe; }
.card-green { background: linear-gradient(180deg, #ecfdf5 0%, #ffffff 100%); border-color: #bbf7d0; }
.card-amber { background: linear-gradient(180deg, #fffbeb 0%, #ffffff 100%); border-color: #fde68a; }
.card-rose { background: linear-gradient(180deg, #fff1f2 0%, #ffffff 100%); border-color: #fecdd3; }

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.about-strip {
  padding: 1rem 1.05rem;
  border-radius: 18px;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
  border: 1px solid #c7d2fe;

  h4 {
    margin: 0 0 0.5rem;
    color: #0f172a;
    font-size: 1rem;
    line-height: 1.3;
    font-weight: 700;
  }
  p { margin: 0 0 0.5rem; color: #475569; font-size: 0.9rem; }

  ul {
    margin: 0.5rem 0 0;
    padding-left: 1.2rem;
    color: #475569;
    font-size: 0.9rem;
    line-height: 1.7;
  }
}

@media (max-width: 720px) {
  .two-col { grid-template-columns: 1fr; }
}
</style>
