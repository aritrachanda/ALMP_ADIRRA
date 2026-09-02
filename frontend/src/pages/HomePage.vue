<template>
  <q-page class="home-page">
    <!-- ═══════════════════ Hero banner ═══════════════════ -->
    <section class="hero">
      <div class="hero-grid"></div>
      <div class="hero-inner">
        <div class="hero-layout">
          <div class="hero-main">
            <div class="hero-copy-block">
              <h1 class="hero-title">ADIRRA</h1>
              <p class="hero-phase">Starting with governance and target alignment.</p>
              <p class="hero-subtitle">
                The first ADIRRA slice brings together AI-assisted source onboarding through discovery,
                agent-driven business meaning and regulatory context enrichment, reviewable target mapping,
                and portable outputs for BIRD and CRDM.
              </p>
              <div class="hero-signals">
                <span v-for="signal in heroSignals" :key="signal" class="hero-signal-chip">{{ signal }}</span>
              </div>
            </div>

            <!-- Band cards -->
            <div class="band">
              <div v-for="b in bandItems" :key="b.label" class="band-card">
                <div class="band-label">{{ b.label }}</div>
                <div class="band-copy">{{ b.copy }}</div>
              </div>
            </div>
          </div>

          <aside class="hero-side">
            <div class="hero-side-intro">Management Roadmap</div>
            <h2 class="hero-side-title">What is in progress now and what follows next.</h2>
            <p class="hero-side-copy">
              The roadmap frames the current build stage and the next development steps,
              so the right side carries product meaning instead of empty space.
            </p>

            <div class="roadmap roadmap-vertical">
              <div v-for="r in roadmapItems" :key="r.label" class="roadmap-card">
                <div class="roadmap-label">{{ r.label }}</div>
                <div class="roadmap-copy">{{ r.copy }}</div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>

    <!-- Quick-nav buttons -->
    <div class="quick-nav q-mt-lg">
      <q-btn v-for="nav in quickNavItems" :key="nav.to" :to="nav.to" :icon="nav.icon" :label="nav.label" color="primary" outline no-caps class="q-mr-sm" />
    </div>

    <!-- ═══════════════════ How It Works ═══════════════════ -->
    <section class="content-section q-mt-lg">
      <div class="section-tag">How It Works</div>
      <h2 class="section-title">The management story starts from governed onboarding.</h2>
      <p class="section-intro">
        The current app is strongest when it presents data management as a controlled operating flow. A source is
        discovered, described, linked to business meaning, aligned to target models, and surfaced as something that
        can be reviewed, exported, and discussed operationally.
      </p>
      <div class="grid-2">
        <div class="steps">
          <div v-for="step in howSteps" :key="step.num" class="step-card">
            <div class="step-num">{{ step.num }}</div>
            <div>
              <h3>{{ step.title }}</h3>
              <p>{{ step.copy }}</p>
            </div>
          </div>
        </div>
        <div class="pillar-list">
          <div v-for="p in howPillars" :key="p.label" class="pillar-row">
            <div class="pillar-label">{{ p.label }}</div>
            <div class="pillar-copy">{{ p.copy }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Features ═══════════════════ -->
    <section class="content-section section-amber q-mt-lg">
      <div class="section-tag">Features</div>
      <h2 class="section-title">Feature areas that make the management claim believable today.</h2>
      <p class="section-intro">
        The strongest features are the ones a user can verify immediately in the current app. They show a product
        that already manages the first lifecycle stages of regulatory data work, even if later-stage monitoring and
        remediation are still on the roadmap.
      </p>
      <div class="grid-3">
        <div v-for="f in features" :key="f.title" class="info-card">
          <h3>{{ f.title }}</h3>
          <p>{{ f.copy }}</p>
          <div class="card-note">{{ f.note }}</div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Capabilities (nav cards) ═══════════════════ -->
    <section class="content-section section-purple q-mt-lg">
      <div class="section-tag">Capabilities</div>
      <h2 class="section-title">What you can do today</h2>
      <p class="section-intro">
        The current app supports a practical flow from source understanding to governed meaning
        and target-model alignment.
      </p>
      <div class="capability-grid">
        <router-link v-for="cap in capabilities" :key="cap.to" :to="cap.to" class="capability-card" :class="cap.colorClass">
          <q-icon :name="cap.icon" size="28px" class="cap-icon" />
          <h3>{{ cap.name }}</h3>
          <p>{{ cap.description }}</p>
        </router-link>
      </div>
    </section>

    <!-- ═══════════════════ Agents ═══════════════════ -->
    <section class="content-section section-blue q-mt-lg">
      <div class="section-tag">Agent System</div>
      <h2 class="section-title">Why the product is agentic, not just AI-assisted.</h2>
      <p class="section-intro">
        The app is built around specialised agents with distinct responsibilities instead of a single generic model call.
        Pages and API routes invoke the right agent for the task, and those agents share catalogs, glossary terms,
        mappings, and regulatory retrieval layers as common working context.
      </p>
      <div class="agent-grid">
        <div v-for="agent in agentCards" :key="agent.title" class="info-card agent-card">
          <div class="agent-name-row">
            <h3>{{ agent.title }}</h3>
            <span class="agent-surface">{{ agent.surface }}</span>
          </div>
          <p>{{ agent.copy }}</p>
        </div>
      </div>
      <div class="orchestration-grid q-mt-md">
        <div v-for="flow in orchestrationFlows" :key="flow.label" class="flow-card">
          <div class="flow-label">{{ flow.label }}</div>
          <div class="flow-copy">{{ flow.copy }}</div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Living Compliance ═══════════════════ -->
    <section class="content-section section-green q-mt-lg">
      <div class="section-tag">Living Compliance</div>
      <h2 class="section-title">Policy boundaries that the agent system reads and enforces.</h2>
      <p class="section-intro">
        In the stronger ADIRRA story, policy is not a PDF sitting beside the workflow. It becomes an operating boundary
        for discovery, glossary enrichment, mapping, and agent execution, so sensitive data handling and review gates
        can remain attached to the same artefacts the user is actively managing.
      </p>
      <div class="pillar-list">
        <div v-for="p in compliancePillars" :key="p.label" class="pillar-row">
          <div class="pillar-label">{{ p.label }}</div>
          <div class="pillar-copy">{{ p.copy }}</div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Compliance ═══════════════════ -->
    <section class="content-section section-rose q-mt-lg">
      <div class="section-tag">Compliance</div>
      <h2 class="section-title">Regulatory alignment and AI governance as product features.</h2>
      <p class="section-intro">
        The most credible position is that ADIRRA contains the agent framework within defined policy and regulatory
        boundaries. That includes data handling controls, reviewable AI activity, and alignment to formal obligations
        such as GDPR, the EU AI Act, BCBS 239, and related financial-services governance expectations.
      </p>
      <div class="grid-3">
        <div v-for="c in complianceCards" :key="c.title" class="info-card">
          <h3>{{ c.title }}</h3>
          <p>{{ c.copy }}</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Architecture ═══════════════════ -->
    <section class="content-section section-slate q-mt-lg">
      <div class="section-tag">Architecture</div>
      <h2 class="section-title">An agentic architecture that fits the app you actually have.</h2>
      <p class="section-intro">
        The architecture is practical rather than abstract: FastAPI routes and page actions invoke focused agents,
        those agents work against shared YAML and RAG artefacts, and the resulting outputs come back into the UI as
        reviewable glossary entries, mapping proposals, regulatory context, and exportable management assets.
      </p>
      <div class="grid-2">
        <div class="stack">
          <div v-for="layer in archLayers" :key="layer.title" class="stack-layer">
            <h3>{{ layer.title }}</h3>
            <p>{{ layer.copy }}</p>
          </div>
        </div>
        <div>
          <!-- Flow diagram -->
          <div class="arch-diagram">
            <div class="arch-head">
              <span class="arch-dot one"></span>
              <span class="arch-dot two"></span>
              <span class="arch-dot three"></span>
              <span class="arch-title-label">adirra app flow</span>
            </div>
            <div class="arch-flow">
              <template v-for="(node, idx) in archNodes" :key="node.label">
                <div class="arch-node">
                  <div class="arch-node-label">{{ node.label }}</div>
                  <div class="arch-node-copy">
                    <strong>{{ node.title }}</strong>
                    {{ node.copy }}
                  </div>
                  <div class="arch-node-tools">
                    <template v-for="(tool, ti) in node.tools" :key="ti">{{ tool }}<br v-if="ti < node.tools.length - 1"></template>
                  </div>
                </div>
                <div v-if="idx < archNodes.length - 1" class="arch-arrow">{{ node.arrow }}</div>
              </template>
            </div>
          </div>
          <div class="chip-row q-mt-sm">
            <span v-for="chip in archChips" :key="chip" class="chip">{{ chip }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════ Roadmap ═══════════════════ -->
    <section class="content-section section-violet q-mt-lg">
      <div class="section-tag">Roadmap</div>
      <h2 class="section-title">Where the ADIRRA direction goes next</h2>
      <div class="phase-grid">
        <div v-for="p in phases" :key="p.title" class="phase-card">
          <div class="phase-badge" :class="p.badgeClass">{{ p.badge }}</div>
          <h3>{{ p.title }}</h3>
          <p>{{ p.description }}</p>
        </div>
      </div>
    </section>

    <!-- Bottom nav -->
    <div class="quick-nav q-mt-lg q-mb-xl">
      <q-btn v-for="nav in bottomNavItems" :key="nav.to" :to="nav.to" :icon="nav.icon" :label="nav.label" color="primary" outline no-caps class="q-mr-sm" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
const bandItems = [
  { label: 'Discover', copy: 'Profile source structures and inspect technical context before mapping starts.' },
  { label: 'Describe', copy: 'Turn tables and columns into catalog and glossary meaning with reusable business context.' },
  { label: 'Map', copy: 'Generate source-to-target suggestions with rationale, confidence, and reviewable status.' },
  { label: 'Control', copy: 'Show review state, audit visibility, dashboards, and export packages as managed outputs.' },
];

const heroSignals = ['AI-assisted onboarding', 'Agent-driven enrichment', 'Reviewable mapping', 'BIRD + CRDM ready'];

const roadmapItems = [
  { label: 'Now', copy: 'Discovery, catalog context, glossary meaning, target mapping, dashboards, and exportable artefacts.' },
  { label: 'Next', copy: 'Data quality controls, reference data handling, review queues, and publish-ready handoffs that extend the current governance slice into a fuller data management workflow.' },
  { label: 'Later', copy: 'Data architecture views, data modelling support, continuous monitoring, remediation actions, and broader operating controls across the managed data lifecycle.' },
];

const quickNavItems = [
  { to: '/standards/glossary', icon: 'menu_book', label: 'Open Glossary' },
  { to: '/workspace/mapping', icon: 'alt_route', label: 'Open Mapping Workspace' },
];

const bottomNavItems = [
  { to: '/tools/dashboard', icon: 'dashboard', label: 'Open Dashboard' },
  { to: '/system/settings', icon: 'settings', label: 'Open Settings' },
  { to: '/system/about', icon: 'info', label: 'Open About' },
];

// ── How It Works ──
const howSteps = [
  { num: '01', title: 'Discovery frames the source estate', copy: 'Use Discovery to inspect profiled source structures and identify what is actually available before any governance work is attempted.' },
  { num: '02', title: 'Data Catalog captures technical context', copy: 'Catalog entries and annotation overlays hold descriptions and instructions that make source assets understandable and reusable.' },
  { num: '03', title: 'Business Glossary grounds business meaning', copy: 'Terms, synonyms, categories, related objects, and stewardship context provide the semantic layer that mapping work can build on.' },
  { num: '04', title: 'Mapping aligns the source to BIRD and CRDM', copy: 'The mapping page produces source-to-target suggestions with confidence, rationale, and derivation needs that can be reviewed rather than blindly accepted.' },
  { num: '05', title: 'Dashboard and Settings expose the outputs', copy: 'Once artefacts exist, the app surfaces coverage views, export packaging, and a clearer management view of what this first slice has produced.' },
];

const howPillars = [
  { label: 'Onboard', copy: 'Sources enter a controlled flow instead of remaining undocumented technical assets.' },
  { label: 'Interpret', copy: 'Technical descriptions and glossary terms turn structures into business-ready, reviewable meaning.' },
  { label: 'Align', copy: 'Target mapping converts that meaning into regulatory outputs with confidence and rationale.' },
  { label: 'Export', copy: 'The resulting artefacts become visible, portable, and ready for downstream review and handoff.' },
];

// ── Features ──
const features = [
  { title: 'Catalog plus glossary linkage', copy: 'Terms can point back to related source objects, which helps connect business meaning with the technical source landscape instead of treating them as separate silos.', note: 'Page fit: Data Catalog + Business Glossary' },
  { title: 'AI-assisted mapping with rationale', copy: 'Mapping suggestions include confidence and derivation cues, so users can inspect what looks direct, what needs logic, and what remains unmapped.', note: 'Page fit: Mapping + Dashboard' },
  { title: 'Regulatory target orientation', copy: 'The flow is oriented around real targets such as BIRD and CRDM rather than generic data-model exercises, which keeps the demo grounded in regulatory use cases.', note: 'Page fit: Mapping + targets' },
  { title: 'Import and export centre', copy: 'Settings now acts as a central place to package glossary, catalog, and mapping artefacts, which is more realistic than scattering export actions across pages.', note: 'Page fit: Settings' },
  { title: 'Management visibility', copy: 'Dashboard provides a demo-safe way to show coverage, review state, and governance outputs without reducing the product to a static brochure.', note: 'Page fit: Dashboard' },
  { title: 'Human review remains visible', copy: 'The current app emphasizes suggestions, coverage, and approval-ready artefacts instead of pretending that AI closes governance decisions without oversight.', note: 'Page fit: Glossary + Mapping + Dashboard' },
];

// ── Capabilities (navigation cards) ──
const capabilities = [
  { to: '/standards/glossary', icon: 'menu_book', name: 'Business Glossary', description: 'Define and maintain business terms with domains, categories, and AI-assisted context enrichment.', colorClass: 'cap-amber' },
  { to: '/workspace/mapping', icon: 'alt_route', name: 'Mapping Workspace', description: 'Mappings into targets such as BIRD and CRDM are generated with confidence and rationale so they can be reviewed, refined, and challenged.', colorClass: 'cap-rose' },
];

const agentCards = [
  { title: 'Chat orchestrator agent', surface: 'Chat', copy: 'The chat agent is the top-level conversational orchestrator. It handles multi-turn requests and uses tool-calling to reach glossary, catalog, mapping, CRR, DPM, data-query, and chart capabilities.' },
  { title: 'Mapping agent', surface: 'Mapping', copy: 'The generic mapping agent loads source and target catalogs, scores semantic matches, and writes reviewable source-to-target proposals with rationale, confidence, and transformation hints.' },
  { title: 'BIRD mapping agent', surface: 'Mapping variant', copy: 'A specialised BIRD-oriented mapping variant uses framework-aware prompts and BIRD vocabulary so mapping can be grounded in regulatory target semantics instead of generic similarity alone.' },
  { title: 'Glossary agent', surface: 'Glossary', copy: 'The glossary agent manages glossary CRUD, AI drafting, cross-references, and context enrichment so terms remain connected to the technical source estate and regulatory meaning.' },
  { title: 'Catalog agent', surface: 'Data Catalog', copy: 'The catalog agent generates business descriptions and mapping instructions for source metadata, turning raw schema discovery into reusable technical and semantic context for downstream work.' },
  { title: 'CRR retrieval agent', surface: 'Glossary + Chat', copy: 'The CRR agent uses RAG over CRR3 article content to bring regulatory text into chat and glossary enrichment workflows when a term needs rule-backed context.' },
  { title: 'DPM retrieval agent', surface: 'Glossary + Chat', copy: 'The DPM agent uses retrieval over DPM datapoints, tables, and cells so reporting-model context can be attached to glossary terms and answered through chat.' },
];

const orchestrationFlows = [
  { label: 'Page or API trigger', copy: 'Discovery, Catalog, Glossary, Mapping, and Chat pages call focused FastAPI routes rather than sending every interaction through one undifferentiated model endpoint.' },
  { label: 'Specialist execution', copy: 'Those routes instantiate the right specialist agent for the job: chat orchestrates tools, mapping runs table and column alignment, glossary enriches terms, and CRR or DPM retrieval supplies regulation-specific context.' },
  { label: 'Shared artefact layer', copy: 'Agents are connected through shared sources, targets, glossary, mappings, project configuration, and RAG indexes, so one agent’s output becomes another part of the product’s working context.' },
];

// ── Living Compliance ──
const compliancePillars = [
  { label: 'Pre-flight policy gates', copy: 'Agent actions can be framed as operating inside explicit policy boundaries, so sensitive discovery or enrichment work can be blocked, escalated, or routed for approval before processing continues.' },
  { label: 'PII and classification controls', copy: 'Discovery and governance flows can surface personal-data indicators, classifications, and handling expectations instead of leaving those checks outside the operating workflow.' },
  { label: 'Human approval points', copy: 'Glossary review status, mapping confidence, and managed approvals keep the agent system reviewable rather than letting AI-generated actions pass as silent automation.' },
  { label: 'Runtime enforcement trail', copy: 'The value is not just policy authoring but policy observability: what was checked, what was restricted, and what moved forward as a governed artefact.' },
];

// ── Compliance ──
const complianceCards = [
  { title: 'EU AI Act and AI governance posture', copy: 'The agentic layer should remain bounded by explicit rules, auditability, and human oversight so AI-assisted governance outputs align with emerging AI accountability expectations instead of bypassing them.' },
  { title: 'GDPR and sensitive data handling', copy: 'Classification, PII detection, transmission controls, and approval gates belong inside the same management flow that discovers and enriches data, which makes data protection part of execution rather than an afterthought.' },
  { title: 'BCBS 239 and regulated data control', copy: 'Traceable mappings, quality-oriented governance, and reviewable lineage support the kind of aggregation accuracy, transparency, and control posture expected in regulated banking data environments.' },
  { title: 'BIRD, CRR, and DPM grounding', copy: 'The regulatory story is also domain-specific: glossary and mapping outputs can carry CRR and DPM context while target alignment stays tied to BIRD and CRDM rather than generic model language.' },
  { title: 'Auditability and explainability', copy: 'Confidence scores, derivation cues, related objects, review states, and managed outputs all contribute to an explainable discussion of what the agent system proposed and what humans accepted.' },
  { title: 'Policy as runtime control', copy: 'The strongest product position is that policy is read as an execution boundary around the agents, so the governance system can stop, flag, or route activity when official handling rules are encountered.' },
];

// ── Architecture ──
const archLayers = [
  { title: 'Source discovery and profiling', copy: 'Discovery and source catalogs establish the technical baseline by profiling source structures and storing reusable metadata in YAML artefacts.' },
  { title: 'Agent execution layer', copy: 'Chat, glossary, catalog, mapping, CRR, and DPM agents sit behind page actions and API routes, each handling a narrower responsibility with the shared project configuration.' },
  { title: 'Shared artefact and retrieval layer', copy: 'Sources, targets, glossary YAML, mappings, and CRR or DPM RAG indexes provide the persistent context that lets agents connect technical assets, business meaning, and regulatory knowledge.' },
  { title: 'Management surfaces', copy: 'Dashboard, Settings, and the core working pages expose those outputs as reviewable managed artefacts instead of isolated AI text responses.' },
];

const archNodes = [
  { label: 'Profile', title: 'Discovery + connectors', copy: 'Profiles source schemas and establishes the technical context used by the rest of the app.', tools: ['DuckDB', 'source catalogs'], arrow: 'HAND OFF' },
  { label: 'Enrich', title: 'Catalog and glossary agents', copy: 'Catalog and glossary agents convert source structure into descriptions, terms, related objects, and stewardship context.', tools: ['catalog_agent', 'glossary_agent', 'glossary YAML'], arrow: 'ADD CONTEXT' },
  { label: 'Ground', title: 'CRR and DPM retrieval agents', copy: 'Regulatory retrieval agents pull in CRR3 and DPM evidence so definitions and conversations can be anchored in external model and rule content.', tools: ['crr_agent', 'dpm_agent', 'RAG indexes'], arrow: 'INFORM' },
  { label: 'Align', title: 'Mapping agents + targets', copy: 'Generic and BIRD-specific mapping agents generate target proposals with confidence, rationale, streaming progress events, and persisted mapping YAML outputs.', tools: ['mapping_agent', 'bird_mapping_agent', 'mappings/'], arrow: 'REVIEW' },
  { label: 'Orchestrate', title: 'Chat, API, and management surfaces', copy: 'The chat agent and FastAPI routes orchestrate specialist calls and return the outputs to UI pages, dashboards, and export surfaces for human review.', tools: ['chat_agent', 'FastAPI', 'Dashboard / Settings'], arrow: '' },
];

const archChips = ['sources/', 'targets/', 'glossary/', 'mappings/', 'rag/', 'api/routes/'];

// ── Roadmap ──
const phases = [
  { badge: 'Current', badgeClass: 'badge-current', title: 'Governance & alignment', description: 'Source onboarding, discovery, catalog descriptions, glossary meaning, target mapping, dashboards, and exportable artefacts.' },
  { badge: 'Next', badgeClass: 'badge-next', title: 'Operational data management', description: 'Data quality controls, reference data workflows, change impact views, review queues, and publish-ready handoffs into downstream governance processes.' },
  { badge: 'Future', badgeClass: 'badge-future', title: 'Broader management platform', description: 'Data architecture views, data modelling support, continuous monitoring, remediation actions, and wider operating controls across the managed data lifecycle.' },
];
</script>

<style lang="scss" scoped>
.home-page {
  padding: 1.5rem;
  background: #fdfdfd;
}

/* ── Hero ───────────────────────────────── */
.hero {
  position: relative;
  overflow: hidden;
  padding: 3rem 3rem 2.6rem;
  border-radius: 30px;
  border: 1px solid rgba(13, 77, 161, 0.14);
  background:
    radial-gradient(circle at top right, rgba(83, 187, 255, 0.22), transparent 28%),
    radial-gradient(circle at bottom left, rgba(25, 111, 185, 0.18), transparent 26%),
    linear-gradient(135deg, #071826 0%, #0b2134 48%, #12385a 100%);
  color: #f7fbff;
}

.hero-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(circle at center, black 34%, transparent 82%);
  pointer-events: none;
}

.hero-inner {
  position: relative;
  z-index: 1;
}

.hero-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.9fr);
  gap: 1.4rem;
  align-items: stretch;
}

.hero-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 100%;
  gap: 1.15rem;
}

.hero-copy-block {
  max-width: 720px;
}

.hero-side {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 1.15rem;
  border-radius: 28px;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.09) 0%, rgba(132, 204, 255, 0.08) 100%),
    rgba(7, 20, 35, 0.34);
  border: 1px solid rgba(159, 209, 255, 0.15);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
  backdrop-filter: blur(12px);
}

.hero-side-intro {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 800;
  color: #9fd1ff;
  margin-bottom: 0.75rem;
}

.hero-side-title {
  margin: 0;
  font-size: 1.45rem;
  line-height: 1.15;
  letter-spacing: -0.03em;
  color: #f8fbff;
}

.hero-side-copy {
  margin: 0.75rem 0 1rem;
  font-size: 0.94rem;
  line-height: 1.65;
  color: rgba(241, 248, 255, 0.78);
}

.kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.38rem 0.82rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.08);
  color: #9fd1ff;
  font-size: 0.77rem;
  font-weight: 800;
  letter-spacing: 0.11em;
  text-transform: uppercase;
  margin-bottom: 1.1rem;
}

.kicker-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #59d2ff;
  box-shadow: 0 0 0 6px rgba(89, 210, 255, 0.12);
}

.hero-title {
  font-size: clamp(2.4rem, 4.9vw, 4.4rem);
  line-height: 1.02;
  font-weight: 800;
  letter-spacing: -0.045em;
  margin: 0 0 0.45rem 0;
}

.hero-phase {
  max-width: 720px;
  font-size: clamp(1.05rem, 2vw, 1.5rem);
  line-height: 1.35;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #9fd1ff;
  margin: 0 0 1rem 0;
}

.hero-subtitle {
  max-width: 720px;
  font-size: 0.98rem;
  line-height: 1.72;
  color: rgba(241, 248, 255, 0.84);
  margin: 0 0 0.8rem 0;
}

.hero-signals {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-top: 1.35rem;
}

.hero-signal-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.38rem 0.72rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(159, 209, 255, 0.14);
  color: #d8ebff;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.band {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.9rem;
  margin-top: 0.45rem;
  align-items: stretch;
}

.band-card {
  padding: 1rem 1.05rem;
  border-radius: 18px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.08);
  backdrop-filter: blur(8px);
  min-height: 168px;
}

.band-label {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(196, 228, 255, 0.74);
  font-weight: 700;
  margin-bottom: 0.35rem;
}

.band-copy {
  font-size: 0.92rem;
  line-height: 1.52;
  color: #f8fbff;
}

.roadmap {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
  margin-top: 1rem;
}

.roadmap-vertical {
  grid-template-columns: 1fr;
  margin-top: 0.2rem;
}

.roadmap-card {
  border-radius: 18px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.08);
  padding: 0.95rem 1rem;
  position: relative;
  overflow: hidden;
}

.roadmap-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  border-radius: 999px;
  background: linear-gradient(180deg, #7dd3fc 0%, #38bdf8 100%);
}

.roadmap-card:nth-child(2)::before {
  background: linear-gradient(180deg, #93c5fd 0%, #818cf8 100%);
}

.roadmap-card:nth-child(3)::before {
  background: linear-gradient(180deg, #c4b5fd 0%, #f0abfc 100%);
}

.roadmap-label {
  font-size: 0.7rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #9fd1ff;
  font-weight: 800;
  margin-bottom: 0.35rem;
}

.roadmap-copy {
  color: #f8fbff;
  font-size: 0.9rem;
  line-height: 1.55;
}

/* ── Quick nav ──────────────────────────── */
.quick-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

/* ── Content sections ───────────────────── */
.content-section {
  --section-accent: #0d4da1;
  --section-soft: #f8fbff;
  --section-border: #e2edf8;
  --card-border: #e4edf7;
  --card-bg: #fbfdff;
  --accent-soft: #eaf3ff;
  --section-tag-bg: #eef5ff;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid var(--section-border);
  border-radius: 26px;
  padding: 1.5rem;
  box-shadow: 0 18px 34px rgba(13, 77, 161, 0.06);
}

.section-blue {
  --section-accent: #2563eb;
  --section-soft: #f5f9ff;
  --section-border: #dbeafe;
  --card-border: #d9e8ff;
  --card-bg: #f8fbff;
  --accent-soft: #dbeafe;
  --section-tag-bg: #eaf2ff;
}

.section-amber {
  --section-accent: #d97706;
  --section-soft: #fffaf0;
  --section-border: #fde7b2;
  --card-border: #f6dfad;
  --card-bg: #fffdfa;
  --accent-soft: #fef3c7;
  --section-tag-bg: #fff4d8;
}

.section-purple {
  --section-accent: #7c3aed;
  --section-soft: #faf7ff;
  --section-border: #ddd6fe;
  --card-border: #ddd6fe;
  --card-bg: #fcfbff;
  --accent-soft: #ede9fe;
  --section-tag-bg: #f3edff;
}

.section-green {
  --section-accent: #15803d;
  --section-soft: #f5fcf7;
  --section-border: #ccefd7;
  --card-border: #ccefd7;
  --card-bg: #fbfffc;
  --accent-soft: #dcfce7;
  --section-tag-bg: #eafbf0;
}

.section-rose {
  --section-accent: #e11d48;
  --section-soft: #fff7f8;
  --section-border: #fecdd3;
  --card-border: #ffd8dd;
  --card-bg: #fffafb;
  --accent-soft: #ffe4e6;
  --section-tag-bg: #fff0f2;
}

.section-slate {
  --section-accent: #0f3b68;
  --section-soft: #f3f8fc;
  --section-border: #d8e5f1;
  --card-border: #d7e3ef;
  --card-bg: #f9fcff;
  --accent-soft: #e2edf8;
  --section-tag-bg: #ebf3fa;
}

.section-violet {
  --section-accent: #6d28d9;
  --section-soft: #faf6ff;
  --section-border: #ddd6fe;
  --card-border: #e4dcff;
  --card-bg: #fcfbff;
  --accent-soft: #ede9fe;
  --section-tag-bg: #f5f0ff;
}

.section-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.66rem;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--section-accent);
  background: var(--section-tag-bg);
  margin-bottom: 0.55rem;
}

.section-title {
  font-size: clamp(1.45rem, 3vw, 2.2rem);
  line-height: 1.1;
  letter-spacing: -0.035em;
  color: #10243a;
  margin: 0 0 0.75rem 0;
}

.section-intro {
  max-width: 760px;
  color: #516274;
  font-size: 0.98rem;
  line-height: 1.78;
  margin-bottom: 1.2rem;
}

/* ── Grid layouts ───────────────────────── */
.grid-2 {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 1rem;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.agent-card {
  min-height: 100%;
}

.agent-name-row {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-bottom: 0.45rem;
}

.agent-surface {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  padding: 0.24rem 0.56rem;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--section-accent);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.03em;
}

.orchestration-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.flow-card {
  border-radius: 18px;
  border: 1px solid var(--card-border);
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);
  padding: 1rem 1.05rem;
}

.flow-label {
  margin-bottom: 0.35rem;
  color: var(--section-accent);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.flow-copy {
  color: #556577;
  font-size: 0.92rem;
  line-height: 1.65;
}

/* ── How It Works — steps ───────────────── */
.steps {
  display: grid;
  gap: 0.8rem;
}

.step-card {
  display: grid;
  grid-template-columns: 58px 1fr;
  gap: 1rem;
  align-items: start;
  border-radius: 18px;
  border: 1px solid var(--card-border);
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);
  padding: 1rem 1.05rem;

  h3 { margin: 0 0 0.35rem 0; font-size: 0.98rem; color: #10243a; }
  p  { margin: 0; color: #556577; line-height: 1.66; font-size: 0.92rem; }
}

.step-num {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: var(--accent-soft);
  color: var(--section-accent);
  font-size: 0.94rem;
  font-weight: 800;
}

/* ── Pillar rows ────────────────────────── */
.pillar-list {
  display: grid;
  gap: 0.7rem;
}

.pillar-row {
  display: grid;
  grid-template-columns: 145px 1fr;
  gap: 0.8rem;
  align-items: baseline;
  border-radius: 16px;
  border: 1px solid var(--card-border);
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);
  padding: 0.85rem 1rem;
}

.pillar-label {
  color: var(--section-accent);
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.03em;
}

.pillar-copy {
  color: #556577;
  font-size: 0.9rem;
  line-height: 1.65;
}

/* ── Info cards (Features, Compliance) ──── */
.info-card {
  height: 100%;
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);
  border: 1px solid var(--card-border);
  border-radius: 20px;
  padding: 1.15rem 1.15rem 1.05rem;

  h3 { margin: 0 0 0.5rem 0; font-size: 1rem; color: #10243a; }
  p  { margin: 0; color: #556577; line-height: 1.7; font-size: 0.93rem; }
}

.card-note {
  margin-top: 0.7rem;
  color: var(--section-accent);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

/* ── Capability cards ───────────────────── */
.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}

.capability-card {
  display: block;
  padding: 1.15rem;
  border-radius: 20px;
  border: 1px solid #e4edf7;
  background: #fbfdff;
  text-decoration: none;
  transition: box-shadow 0.2s, border-color 0.2s;

  &:hover { box-shadow: 0 8px 24px rgba(13, 77, 161, 0.1); border-color: #bfdbfe; }
  .cap-icon { margin-bottom: 0.5rem; }
  h3 { margin: 0 0 0.5rem 0; font-size: 1rem; color: #10243a; }
  p  { margin: 0; color: #556577; line-height: 1.7; font-size: 0.93rem; }
}

.cap-blue   { border-color: #bfdbfe; background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%); .cap-icon { color: #2563eb; } }
.cap-green  { border-color: #bbf7d0; background: linear-gradient(180deg, #ecfdf5 0%, #ffffff 100%); .cap-icon { color: #16a34a; } }
.cap-amber  { border-color: #fde68a; background: linear-gradient(180deg, #fffbeb 0%, #ffffff 100%); .cap-icon { color: #d97706; } }
.cap-rose   { border-color: #fecdd3; background: linear-gradient(180deg, #fff1f2 0%, #ffffff 100%); .cap-icon { color: #e11d48; } }
.cap-purple { border-color: #c4b5fd; background: linear-gradient(180deg, #f5f3ff 0%, #ffffff 100%); .cap-icon { color: #7c3aed; } }

/* ── Architecture — stack layers ────────── */
.stack {
  display: grid;
  gap: 0.72rem;
}

.stack-layer {
  border-radius: 18px;
  border: 1px solid var(--card-border);
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);
  padding: 1rem 1.05rem;

  h3 { margin: 0 0 0.32rem 0; font-size: 0.94rem; color: #10243a; }
  p  { margin: 0; color: #556577; font-size: 0.9rem; line-height: 1.65; }
}

/* ── Architecture — flow diagram ────────── */
.arch-diagram {
  border-radius: 22px;
  border: 1px solid #dbe7f5;
  background: linear-gradient(180deg, #0b1e2f 0%, #102840 100%);
  padding: 1.15rem;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
}

.arch-head {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-bottom: 0.9rem;
}

.arch-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  &.one   { background: #2dd4bf; }
  &.two   { background: #f59e0b; }
  &.three { background: #ef4444; }
}

.arch-title-label {
  margin-left: auto;
  color: #9fc2e2;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
}

.arch-flow {
  display: grid;
  gap: 0.55rem;
}

.arch-node {
  display: grid;
  grid-template-columns: 96px 1fr 150px;
  gap: 0.8rem;
  align-items: center;
  padding: 0.85rem 0.95rem;
  border-radius: 16px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(161, 197, 235, 0.16);
}

.arch-node-label {
  color: #7dd3fc;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.arch-node-copy {
  color: #e7f3ff;
  font-size: 0.88rem;
  line-height: 1.55;

  strong {
    display: block;
    color: #ffffff;
    font-size: 0.93rem;
    margin-bottom: 0.18rem;
  }
}

.arch-node-tools {
  color: #8fb3d4;
  font-size: 0.74rem;
  line-height: 1.5;
  text-align: right;
  letter-spacing: 0.02em;
}

.arch-arrow {
  color: #7aa6cc;
  font-size: 0.86rem;
  letter-spacing: 0.12em;
  text-align: center;
  font-weight: 700;
}

/* ── Chips ──────────────────────────────── */
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.3rem 0.62rem;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--section-accent);
  font-size: 0.73rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

/* ── Phase cards ────────────────────────── */
.phase-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.phase-card {
  padding: 1.15rem;
  border-radius: 18px;
  border: 1px solid var(--card-border);
  background: linear-gradient(180deg, #ffffff 0%, var(--card-bg) 100%);

  h3 { margin: 0.5rem 0 0.4rem; font-size: 1rem; color: #10243a; }
  p  { margin: 0; color: #556577; font-size: 0.9rem; line-height: 1.65; }
}

.phase-badge {
  display: inline-block;
  padding: 0.22rem 0.58rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.badge-current { background: #dcfce7; color: #166534; }
.badge-next    { background: #dbeafe; color: #1e40af; }
.badge-future  { background: #ede9fe; color: #6d28d9; }

/* ── Responsive ─────────────────────────── */
@media (max-width: 980px) {
  .hero-layout { grid-template-columns: 1fr; }
  .band, .roadmap, .grid-3, .grid-2, .orchestration-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 720px) {
  .hero { padding: 2rem 1.35rem 1.8rem; }
  .hero-side { padding: 1rem; }
  .hero-side-title { font-size: 1.2rem; }
  .band, .roadmap, .grid-3, .grid-2, .orchestration-grid { grid-template-columns: 1fr; }
  .pillar-row { grid-template-columns: 1fr; gap: 0.3rem; }
  .step-card { grid-template-columns: 48px 1fr; }
  .arch-node { grid-template-columns: 1fr; gap: 0.3rem; }
  .arch-node-tools { text-align: left; }
}
</style>
