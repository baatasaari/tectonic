"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const groups = [
  {
    id: "experience",
    name: "Customer experience",
    label: "EXPERIENCE",
    color: "#b8cb94",
    modules: ["conversational-engine", "intent-detection", "multi-modality"],
    desc: "Understand the customer. Carry the conversation.",
    agents: ["Support concierge", "Intent specialist", "Channel coordinator"],
    x: 290,
    y: 90,
  },
  {
    id: "knowledge",
    name: "Knowledge & memory",
    label: "KNOWLEDGE",
    color: "#7eae9b",
    modules: [
      "agentic-rag",
      "knowledge-base",
      "vector-db",
      "graph-db",
      "context-engineering",
      "short-term-memory",
      "long-term-memory",
      "data-source-plugins",
    ],
    desc: "Find the right evidence. Keep its provenance.",
    agents: ["Knowledge researcher", "Groundedness critic", "Context curator"],
    x: 565,
    y: 155,
  },
  {
    id: "execution",
    name: "Agent execution",
    label: "EXECUTION",
    color: "#b6a1c4",
    modules: [
      "workflow-engine",
      "tool-orchestration",
      "llm-gateway",
      "mcp",
      "a2a",
    ],
    desc: "Coordinate each step, model request and tool call.",
    agents: ["Workflow coordinator", "Order specialist", "Response composer"],
    x: 150,
    y: 205,
  },
  {
    id: "assurance",
    name: "Trust & assurance",
    label: "ASSURANCE",
    color: "#d4b68a",
    modules: [
      "guardrails",
      "human-oversight",
      "sentinel-agents",
      "evaluation-framework",
      "regulatory-compliance",
    ],
    desc: "Bound autonomy. Escalate decisions to people.",
    agents: ["Safety sentinel", "Review coordinator", "Evaluation specialist"],
    x: 550,
    y: 375,
  },
  {
    id: "operations",
    name: "Platform operations",
    label: "OPERATIONS",
    color: "#81a6c1",
    modules: [
      "observability",
      "auditability",
      "finops",
      "billing-and-metering",
      "deployment-strategy",
      "llmops",
      "promptops",
    ],
    desc: "Understand performance, lineage and cost.",
    agents: ["Trace analyst", "Cost steward", "Release coordinator"],
    x: 255,
    y: 370,
  },
  {
    id: "foundation",
    name: "Identity & access",
    label: "FOUNDATIONS",
    color: "#b3b796",
    modules: [
      "identity-and-access",
      "multi-tenancy",
      "secrets-and-credential-management",
      "agent-cards",
      "agent-marketplace",
      "sdk-and-developer-portal",
    ],
    desc: "Scope identities, tenants and platform capabilities.",
    agents: ["Tenant coordinator", "Identity steward", "Access guardian"],
    x: 710,
    y: 275,
  },
];
const agents = groups.flatMap((g) =>
  g.agents.map((name, i) => ({
    id: g.id + "-" + i,
    name,
    group: g.id,
    module: g.modules[i % g.modules.length],
    role: i === 0 ? "Coordinator" : "Specialist",
  })),
);
const scenarioData = {
  policy: {
    name: "Answer with evidence",
    question: "What is your returns policy?",
    desc: "Knowledge retrieval → grounded response",
    answer:
      "Items may be returned within 30 days of delivery, unused and in their original packaging. Refunds go to the original payment method within 5–7 business days after receipt.",
    steps: [
      [
        "experience",
        "Understand the request",
        "intent-detection",
        { intent: "policy_question", confidence: 0.97 },
      ],
      [
        "knowledge",
        "Retrieve the returns policy",
        "agentic-rag",
        {
          document: "Returns Policy",
          version: 1,
          passage: "Items may be returned within 30 days of delivery.",
          score: 0.94,
        },
      ],
      [
        "knowledge",
        "Check the evidence",
        "agentic-rag",
        { groundedness: 0.92, outcome: "sufficient" },
      ],
      [
        "assurance",
        "Apply response guardrails",
        "guardrails",
        { decision: "allow", policy: "customer-support" },
      ],
      [
        "execution",
        "Compose the response",
        "llm-gateway",
        {
          logical_agent: "compose-response-agent",
          input_tokens: 486,
          output_tokens: 94,
        },
      ],
      [
        "operations",
        "Record the outcome",
        "auditability",
        { event: "conversation.turn.completed", cost_estimate_usd: 0.0012 },
      ],
    ],
  },
  order: {
    name: "Act through a tool",
    question: "Where is order #A1029?",
    desc: "Intent classification → order-system tool",
    answer:
      "Order #A1029 has shipped. The merchant fixture records an estimated arrival of 2 September 2026. This is a demonstration order, not a live delivery status.",
    steps: [
      [
        "experience",
        "Recognise order status",
        "intent-detection",
        { intent: "order_status", confidence: 0.98 },
      ],
      [
        "execution",
        "Extract the order reference",
        "llm-gateway",
        {
          logical_agent: "order-lookup-agent",
          tool_arguments: { order_id: "A1029" },
        },
      ],
      [
        "execution",
        "Call get_order_status",
        "tool-orchestration",
        {
          tool: "get_order_status",
          request: { order_id: "A1029" },
          result: { status: "shipped", eta: "2026-09-02" },
          source: "merchant fixture",
        },
      ],
      ["assurance", "Screen the response", "guardrails", { decision: "allow" }],
      [
        "execution",
        "Compose order update",
        "llm-gateway",
        { input_tokens: 328, output_tokens: 52 },
      ],
      [
        "operations",
        "Record tool and response",
        "auditability",
        { event: "tool.invocation.completed", cost_estimate_usd: 0.0008 },
      ],
    ],
  },
  refund: {
    name: "Keep a human in control",
    question: "I want an $850 refund for order #A1029.",
    desc: "Threshold decision → review → resume",
    answer:
      "The reviewer has approved the $850 refund request. The demonstration workflow has resumed and recorded the decision. No payment has been executed.",
    steps: [
      [
        "experience",
        "Recognise the refund request",
        "intent-detection",
        { intent: "refund_request", confidence: 0.98 },
      ],
      [
        "execution",
        "Extract amount and order",
        "llm-gateway",
        { refund_amount: 850, currency: "USD", order_id: "A1029" },
      ],
      [
        "assurance",
        "Evaluate refund threshold",
        "workflow-engine",
        { amount: 850, threshold: 500, decision: "escalate" },
      ],
      [
        "assurance",
        "Wait for reviewer decision",
        "human-oversight",
        { status: "pending", reason: "Refund exceeds $500 threshold" },
      ],
      [
        "execution",
        "Resume approved workflow",
        "workflow-engine",
        { resume: "review_decision", status: "completed" },
      ],
      [
        "operations",
        "Record decision and outcome",
        "auditability",
        { event: "review.resolved", cost_estimate_usd: 0.0015 },
      ],
    ],
  },
};
let catalogue = [],
  timer = null,
  canvasMode = "spatial",
  filter = "",
  category = "all",
  backend = { mode: "demo", live_available: false },
  toastTimer;
const initial = () => ({
  tenant: "Acme",
  runs: [],
  documents: [
    {
      id: "returns-v1",
      name: "Returns Policy",
      type: "MD",
      status: "Approved",
      version: 1,
      content:
        "Acme Corp Return Policy: Items may be returned within 30 days of delivery for a full refund, provided they are unused and in original packaging. Refunds are issued to the original payment method within 5–7 business days of receiving the returned item.",
    },
  ],
  config: {
    name: "Acme Support Agent",
    description: "Governed customer support, grounded in company knowledge.",
    instructions:
      "Answer using approved evidence. Escalate refunds above the configured threshold. Do not claim payments were executed.",
    model: "Demo provider · deterministic",
    temperature: "0",
    tokens: "1024",
    threshold: "500",
    welcome: "Hello. How can I help with your order today?",
  },
  events: [],
});
let state;
try {
  state = JSON.parse(localStorage.getItem("tectonic.console.v1")) || initial();
  if (!Array.isArray(state.runs)) state = initial();
} catch {
  state = initial();
}
const save = () => {
  try {
    localStorage.setItem("tectonic.console.v1", JSON.stringify(state));
  } catch {
    toast("Browser storage is full. Export your runs before adding more.");
  }
};
const currentRuns = () => state.runs.filter((r) => r.tenant === state.tenant);
const groupFor = (m) => groups.find((g) => g.modules.includes(m)) || groups[0];
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4200);
}
function go(path) {
  location.hash = "/" + path;
}
function heading(kicker, title, subtitle, buttons = "") {
  return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-buttons">${buttons}</div></div>`;
}
const linkButton = (title, path, cls = "") =>
  `<button class="${cls}" data-go="${path}">${title}</button>`;
const pill = (text, cls = "") =>
  `<span class="badge ${cls}">${esc(text)}</span>`;
function nav(active) {
  const items = [
    ["overview", "◈", "Overview"],
    ["workspace", "⌘", "Agent workspace"],
    ["runs", "↳", "Activity & runs"],
    ["reviews", "▤", "Human reviews"],
    ["knowledge", "▧", "Knowledge"],
    ["agents", "⊞", "Agent setup"],
    ["assurance", "◎", "Assurance"],
    ["capabilities", "◇", "Capabilities"],
  ];
  $("#nav").innerHTML = items
    .map(
      ([id, icon, title], i) =>
        `${i === 0 ? '<div class="nav-group">OPERATE</div>' : i === 4 ? '<div class="nav-group">BUILD & ASSURE</div>' : ""}<a class="nav-link ${active === id ? "active" : ""}" href="#/${id}"><span class="nav-icon">${icon}</span>${title}${id === "reviews" ? `<span class="nav-count">${currentRuns().filter((r) => r.status === "awaiting review").length}</span>` : ""}</a>`,
    )
    .join("");
  $("#tenant-button").innerHTML =
    `<span class="avatar">${state.tenant[0]}</span><span>${esc(state.tenant)} Corporation<small>Support operations</small></span><span>⌄</span>`;
}
function metrics() {
  const runs = currentRuns(),
    done = runs.filter((r) => r.status === "completed");
  return `<div class="metrics">${[
    ["Agent teams", "06", "Across 34 platform modules", "workspace"],
    [
      "Demo conversations",
      String(runs.length).padStart(2, "0"),
      `${done.length} completed in this browser`,
      "runs",
    ],
    [
      "Human decisions",
      String(
        runs.filter((r) => r.status === "awaiting review").length,
      ).padStart(2, "0"),
      "Waiting for your attention",
      "reviews",
    ],
    [
      "Illustrative spend",
      "$" + done.reduce((a, r) => a + r.cost, 0).toFixed(4),
      "Demo estimates · not provider billing",
      "assurance",
    ],
  ]
    .map(
      ([title, note, caption, path]) =>
        `<button class="metric" data-go="${path}"><span class="metric-top">${title}<span>↗</span></span><strong>${note}</strong><span class="metric-bottom">${caption}</span></button>`,
    )
    .join("")}</div>`;
}
function desk(x, y, color) {
  return `<g transform="translate(${x} ${y})"><path d="M-19 4 L4 -8 L28 4 L5 17 Z" fill="#bfc9b6"/><path d="M-19 4V11L5 24V17Z" fill="#768c82"/><path d="M5 17V24L28 11V4Z" fill="#60786f"/><path d="M-14 10V23M23 10V23" stroke="#263e3b" stroke-width="4"/><path d="M-7 -10L10 -3V10L-7 3Z" fill="#243940" stroke="#94b9ac" stroke-width=".7"/><path d="M-4 -6L7 -1M-4 -2L4 2" stroke="${color}" opacity=".8"/><ellipse cx="3" cy="25" rx="8" ry="5" fill="#253b3e"/><path d="M-2 20V34L8 39V24Z" fill="${color}"/><circle cx="4" cy="15" r="5" fill="#e0c5a0"/><path d="M0 12Q4 7 8 13" fill="#293d3b"/></g>`;
}
function world() {
  const run = currentRuns().find((r) => r.status === "running"),
    active = run
      ? scenarioData[run.scenario].steps[Math.min(run.step, 5)][0]
      : "";
  return `<svg class="world" viewBox="0 0 900 530" role="img" aria-label="Six connected agent teams. Select a team to inspect its agents and modules."><defs><pattern id="grid" width="40" height="24" patternUnits="userSpaceOnUse" patternTransform="skewY(-26)"><path d="M40 0H0V24" fill="none" stroke="#32434b" stroke-width=".5"/></pattern><radialGradient id="glow"><stop stop-color="#78996b" stop-opacity=".18"/><stop offset="1" stop-color="#78996b" stop-opacity="0"/></radialGradient></defs><rect width="900" height="530" fill="url(#grid)" opacity=".6"/><ellipse cx="445" cy="268" rx="290" ry="210" fill="url(#glow)"/>${groups.map((g) => `<path class="flow-line ${active === g.id ? "hot" : ""}" d="M445 264 Q${g.x} 264 ${g.x} ${g.y + 20}" fill="none" stroke="${g.color}"/>`).join("")}<g><path d="M397 260L445 235L493 260L445 287Z" fill="#334747" stroke="#8da787"/><path d="M397 260V273L445 300L493 273V260L445 287Z" fill="#253738" stroke="#48605a"/><circle class="beacon" cx="445" cy="260" r="8" fill="#cfe6a2"/><text x="445" y="308" fill="#ccdbc3" font-size="10" letter-spacing="2" text-anchor="middle">CONTROL PLANE</text></g>${groups.map((g) => `<g class="zone" role="button" tabindex="0" data-go="workspace/${g.id}" aria-label="Open ${g.name}"><g transform="translate(${g.x} ${g.y})"><ellipse cx="0" cy="65" rx="105" ry="48" fill="#0e191f" opacity=".6"/><path d="M-97 18L0 -30L97 18L0 69Z" fill="${g.color}" opacity=".12"/><path d="M-97 18V38L0 89L97 38V18L0 69Z" fill="#24353b" stroke="#3e5357"/><path class="plate" d="M-97 18L0 -30L97 18L0 69Z" fill="${g.color}" fill-opacity=".34" stroke="${g.color}" stroke-opacity=".5"/>${desk(-33, 3, g.color)}${desk(20, -20, g.color)}${desk(26, 34, g.color)}<g transform="translate(-79 -58)"><rect width="159" height="25" rx="5" fill="#213139" stroke="#4b625b"/><circle cx="12" cy="12" r="3" fill="${g.color}"/><text x="24" y="16" class="zone-title">${g.label}</text></g><text x="0" y="109" text-anchor="middle" class="zone-sub">${g.modules.length} MODULES · ${g.agents.length} DEMO AGENTS</text>${active === g.id ? '<circle class="beacon" cx="0" cy="-24" r="9" fill="#e2efa7"/>' : ""}</g></g>`).join("")}</svg>`;
}
function canvas() {
  return `<section class="canvas-panel"><div class="canvas-toolbar"><div class="canvas-title">Your agents. One connected workspace.<small>Illustrative team topology · click any team to explore</small></div><div class="segmented"><button data-view="spatial" class="${canvasMode === "spatial" ? "selected" : ""}">Spatial view</button><button data-view="list" class="${canvasMode === "list" ? "selected" : ""}">List view</button></div></div>${canvasMode === "spatial" ? world() : `<div class="list-map">${groups.map((g) => `<button data-go="workspace/${g.id}"><span style="color:${g.color}">◈</span> ${g.name}<small>${g.modules.length} modules · ${g.agents.length} demo agents →</small></button>`).join("")}</div>`}<div class="canvas-bottom"><div class="legend"><span><i style="background:#bed890"></i>Ready</span><span><i style="background:#9abed1"></i>Executing</span><span><i style="background:#d4b68a"></i>Human decision</span></div><button data-action="tour">Explore a live-style run ↗</button></div></section>`;
}
function activity() {
  const records = currentRuns()
    .flatMap((r) =>
      r.history.map((s, i) => ({ run: r, text: s.title, time: s.time, id: i })),
    )
    .sort((a, b) => b.time - a.time)
    .slice(0, 5);
  return `<section class="activity"><div class="panel-heading"><h3>Execution feed</h3>${pill("DEMO EVENTS")}</div><div class="activity-list">${
    records.length
      ? records
          .map(
            (e) =>
              `<button class="activity-row" data-go="runs/${e.run.id}/steps/${e.id}"><span class="activity-dot">↳</span><span><strong>${esc(e.text)}</strong><small>${esc(e.run.id)} · ${new Date(e.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></span></button>`,
          )
          .join("")
      : [
          [
            "Knowledge researcher",
            "Retrieves approved support content",
            "knowledge",
          ],
          ["Order specialist", "Calls the merchant order system", "execution"],
          ["Safety sentinel", "Checks response policy", "assurance"],
          ["Review coordinator", "Pauses sensitive decisions", "assurance"],
          ["Trace analyst", "Records the execution trail", "operations"],
        ]
          .map(
            ([name, desc, group]) =>
              `<button class="activity-row" data-go="workspace/${group}"><span class="activity-dot">◇</span><span><strong>${name}</strong><small>${desc} · ready to demonstrate</small></span></button>`,
          )
          .join("")
  }</div><div class="activity-footer"><span>${records.length ? "Recorded in this demo" : "Start a scenario to see activity"}</span><a href="#/runs">View runs ↗</a></div></section>`;
}
function overview() {
  return (
    heading(
      "THE AGENT WORKSPACE",
      "A little less work. A lot more possibility.",
      "See your agents work together. Follow every action. Step in when it matters.",
      `${linkButton("Explore capabilities", "capabilities")}<button class="primary" data-action="tour">▶ Run a demonstration</button>`,
    ) +
    metrics() +
    `<div class="workspace-grid">${canvas()}${activity()}</div><div class="lower-grid"><section class="card"><div class="panel-heading"><h3>One product. Three real journeys.</h3>${pill("SUPPORT AGENT")}</div><div class="journeys">${Object.entries(
      scenarioData,
    )
      .map(
        ([key, s], i) =>
          `<button class="journey" data-scenario="${key}"><span class="number">0${i + 1}</span><div><h4>${s.name}</h4><p>${s.desc}</p></div><span class="arrow">↗</span></button>`,
      )
      .join(
        "",
      )}</div></section><section class="card pitch"><div><div class="eyebrow">FROM EXPLORATION TO IMPACT</div><h2>Your knowledge. Your tools.<br>Your first governed agent.</h2></div><p>Start with a focused support pilot. Connect your content, agree the boundaries, and see the evidence behind every response.</p><div class="pitch-bottom"><button class="primary small" data-action="lead">Design your pilot ↗</button><small>Knowledge · Action · Human oversight</small></div></section></div>`
  );
}
function workspace(id) {
  if (!id)
    return (
      heading(
        "CONNECTED INTELLIGENCE",
        "An operating space for your agents.",
        "Six functional teams mapped to the existing Tectonic module estate.",
        `<button class="primary" data-action="tour">▶ Run a demonstration</button>`,
      ) + canvas()
    );
  const g = groups.find((x) => x.id === id);
  if (!g) return notFound();
  return (
    heading(
      "AGENT TEAM",
      g.name,
      g.desc,
      linkButton("← All teams", "workspace"),
    ) +
    `<div class="notice">These named agents are demonstration personas. The modules below are implemented services in the repository; service health has not been inferred from this view.</div><div class="grid">${agents
      .filter((a) => a.group === id)
      .map(
        (a) =>
          `<a class="card module-card" href="#/agents/${a.id}"><span class="module-symbol">◈</span><h3>${a.name}</h3><p>${a.role} · ${esc(a.module)}</p><div class="bottom"><span>Inspect configuration & runs</span><span>↗</span></div></a>`,
      )
      .join(
        "",
      )}</div><div class="page-heading" style="margin-top:32px"><h2>Underlying capabilities</h2><span class="badge">${g.modules.length} modules</span></div><div class="grid">${g.modules.map(moduleCard).join("")}</div>`
  );
}
function moduleCard(id) {
  const m = catalogue.find((x) => x.id === id);
  if (!m) return "";
  return `<a class="card module-card" href="#/capabilities/${id}"><span class="module-symbol">${{ knowledge: "▧", assurance: "◎", execution: "⌘" }[groupFor(id).id] || "◇"}</span><h3>${esc(m.name)}</h3><p>${esc(moduleDescription(m))}</p><div class="bottom"><span>${m.routes.length} API operations</span><span>Explore ↗</span></div></a>`;
}
function moduleDescription(m) {
  const d = m.description.split("—").slice(1).join("—") || m.description;
  return d.replace(/^\s*Module\s*\d+[:.\s]*/i, "").slice(0, 165);
}
function capabilities(id, tab = "overview") {
  if (id) {
    const m = catalogue.find((x) => x.id === id);
    if (!m) return notFound();
    return (
      heading(
        "CAPABILITY / " + esc(groupFor(id).name.toUpperCase()),
        esc(m.name),
        esc(moduleDescription(m)),
        linkButton("← Catalogue", "capabilities"),
      ) +
      `<div class="tabs">${["overview", "api", "source"].map((t) => `<a href="#/capabilities/${id}/${t}" class="${t === tab ? "selected" : ""}">${{ overview: "Overview", api: "API operations", source: "Source & evidence" }[t]}</a>`).join("")}</div>` +
      (tab === "api"
        ? `<div class="card table-wrap"><table><thead><tr><th>METHOD</th><th>OPERATION</th><th>HANDLER</th></tr></thead><tbody>${m.routes.map((r, i) => `<tr><td>${pill(r.method)}</td><td><button class="mono" data-endpoint="${id}:${i}">${esc(r.path)}</button></td><td><small>${esc(r.handler)}</small></td></tr>`).join("")}</tbody></table></div>`
        : tab === "source"
          ? `<section class="card pad prose"><h2>Inspect the implementation</h2><p>Inventory extracted from Python route decorators at repository commit <code>7a48334</code>. A declared route is evidence of an API surface, not proof of production readiness.</p><a class="card-link" href="https://github.com/baatasaari/tectonic/tree/7a483344598225620184f4cf33439c0ab7d839a7/modules/${id}" target="_blank" rel="noopener">Open module source <span>↗</span></a><a class="card-link" href="https://github.com/baatasaari/tectonic/blob/7a483344598225620184f4cf33439c0ab7d839a7/modules/${id}/README.md" target="_blank" rel="noopener">Read module documentation <span>↗</span></a></section>`
          : `<div class="detail-grid"><section class="card pad prose"><span class="module-symbol">◇</span><h2 style="margin-top:20px">${esc(m.name)}</h2><p>${esc(m.description)}</p><div class="tag-list">${pill("Repository module")}${pill(groupFor(id).name)}${pill(m.routes.length + " operations")}</div><div class="notice">Explore the backend contract before connecting this capability to your pilot.</div>${linkButton("Inspect API operations →", "capabilities/" + id + "/api", "primary")}</section><section class="card pad"><h3>Explore the connected team</h3><p class="prose" style="margin:15px 0">${groupFor(id).desc}</p>${linkButton(groupFor(id).name + " ↗", "workspace/" + groupFor(id).id)}<div class="notice">The console does not call administrative module APIs from the browser.</div></section></div>`)
    );
  }
  return (
    heading(
      "CAPABILITY ATLAS",
      "The platform beneath the experience.",
      `${catalogue.length} modules. ${catalogue.reduce((n, m) => n + m.routes.length, 0)} declared operations. Explore the actual service contracts.`,
    ) +
    `<div class="filters"><input id="catalog-search" type="search" placeholder="Search capabilities or endpoints…" aria-label="Search capabilities" value="${esc(filter)}"><select id="catalog-category" aria-label="Capability category"><option value="all">All teams</option>${groups.map((g) => `<option value="${g.id}" ${g.id === category ? "selected" : ""}>${g.name}</option>`).join("")}</select><span id="catalog-count" class="badge"></span></div><div class="grid" id="catalog-results"></div>`
  );
}
function updateCatalogue() {
  const filtered = catalogue.filter(
    (m) =>
      (category === "all" || groupFor(m.id).id === category) &&
      JSON.stringify(m).toLowerCase().includes(filter.toLowerCase()),
  );
  $("#catalog-results").innerHTML =
    filtered.map((m) => moduleCard(m.id)).join("") ||
    '<div class="empty">No capabilities match. Try another search.</div>';
  $("#catalog-count").textContent = filtered.length + " capabilities";
}
function agentPage(id) {
  const a = agents.find((x) => x.id === id);
  if (id && !a) return notFound();
  return (
    heading(
      "AGENT STUDIO",
      a ? a.name : "Configure your support agent.",
      a
        ? "Inspect the role, associated module and demo activity."
        : "Set the experience and boundaries for your pilot.",
      linkButton("Explore agent teams", "workspace"),
    ) +
    (a
      ? `<div class="tag-list">${pill(a.role)}${pill(groupFor(a.module).name)}${pill("Demonstration persona")}</div><div class="detail-grid"><section class="card pad prose"><h2>Responsibility</h2><p>${groupFor(a.module).desc} This persona represents the ${esc(a.module)} module in the spatial demonstration.</p>${linkButton("Open module contract →", "capabilities/" + a.module, "primary")}<p>Observable activity includes step inputs, tool outputs, policy decisions and timings. Private model reasoning is not exposed.</p></section><section class="card pad"><h3>See this team at work</h3><div class="journeys">${Object.entries(
          scenarioData,
        )
          .map(
            ([k, s]) =>
              `<button class="journey" data-scenario="${k}">${s.name}<span class="arrow">↗</span></button>`,
          )
          .join("")}</div></section></div>`
      : `<div class="detail-grid"><section class="card pad"><form id="agent-form"><div class="form-grid">${[
          ["name", "Agent name"],
          ["description", "Description"],
          ["model", "Model"],
          ["temperature", "Temperature"],
          ["tokens", "Maximum response tokens"],
          ["threshold", "Refund threshold (USD)"],
        ]
          .map(
            ([key, label]) =>
              `<label>${label}<input name="${key}" value="${esc(state.config[key])}" required ${["temperature", "tokens", "threshold"].includes(key) ? `type="number" min="0" ${key === "temperature" ? 'max="2" step="0.1"' : key === "tokens" ? 'max="16000" min="1"' : 'max="100000"'}` : 'maxlength="160"'}></label>`,
          )
          .join(
            "",
          )}<label class="wide">System instructions<textarea name="instructions" required maxlength="4000">${esc(state.config.instructions)}</textarea></label><label class="wide">Welcome message<input name="welcome" value="${esc(state.config.welcome)}" required maxlength="500"></label></div><div class="form-actions"><button class="primary" type="submit">Save demo configuration</button><button type="button" data-action="tour">Test agent ↗</button></div></form></section><section class="card pad prose"><h2>Bounded by design.</h2><p>The support slice combines enterprise knowledge, the merchant order tool, policy checks and human review.</p><div class="tag-list">${pill("get_order_status")}${pill("Human escalation enabled")}</div><div class="notice">Configuration is saved in your browser for demonstration. It does not publish an agent or modify backend policies.</div><p>The original Ticket #82 fixture uses a $500 threshold and an $850 request. This console retains its USD semantics.</p></section></div>`)
  );
}
function startRun(scenario) {
  if (timer) {
    toast("Pause or finish the current run before starting another.");
    return;
  }
  const s = scenarioData[scenario],
    r = {
      id: "run-" + crypto.randomUUID().slice(0, 8),
      scenario,
      tenant: state.tenant,
      status: "running",
      step: 0,
      history: [],
      created: Date.now(),
      cost: { policy: 0.0012, order: 0.0008, refund: 0.0015 }[scenario],
    };
  state.runs.unshift(r);
  save();
  go("runs/" + r.id);
  tickRun(r.id);
}
function tickRun(id) {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const r = state.runs.find((x) => x.id === id);
    if (!r || r.status !== "running") {
      timer = null;
      return;
    }
    const s = scenarioData[r.scenario].steps[r.step];
    r.history.push({
      title: s[1],
      module: s[2],
      output: s[3],
      time: Date.now(),
      duration: 180 + r.step * 41,
    });
    if (r.scenario === "refund" && r.step === 3) {
      r.status = "awaiting review";
      timer = null;
      toast("The workflow is paused. A reviewer decision is required.");
    } else {
      r.step++;
      if (r.step >= scenarioData[r.scenario].steps.length) {
        r.status = "completed";
        timer = null;
        toast("Demonstration complete. The evidence trail is ready.");
      } else tickRun(id);
    }
    save();
    render();
  }, 1250);
}
function runPage(id, stepId) {
  if (!id)
    return (
      heading(
        "OBSERVABLE EXECUTION",
        "Every action has a story.",
        "Replay an illustrative run or inspect a recorded demo conversation.",
        `<button class="primary" data-action="tour">▶ New demonstration</button>`,
      ) +
      `<div class="card table-wrap"><table><thead><tr><th>RUN</th><th>JOURNEY</th><th>STATE</th><th>STEPS</th><th>CREATED</th></tr></thead><tbody>${currentRuns()
        .map(
          (r) =>
            `<tr><td><button class="mono" data-go="runs/${r.id}">${esc(r.id)} ↗</button></td><td>${scenarioData[r.scenario].name}</td><td>${pill(r.status, r.status === "awaiting review" ? "amber" : "")}</td><td>${r.history.length} / 6</td><td>${new Date(r.created).toLocaleString()}</td></tr>`,
        )
        .join(
          "",
        )}</tbody></table>${!currentRuns().length ? '<div class="empty">No runs yet. Start one of the three support journeys.<br>Each run records a navigable execution trail.</div>' : ""}</div>`
    );
  const r = currentRuns().find((x) => x.id === id);
  if (!r)
    return notFound("This run is not available in the selected demo tenant.");
  const s = scenarioData[r.scenario];
  if (stepId !== undefined) {
    const i = Number(stepId),
      step = s.steps[i],
      event = r.history[i];
    if (!step) return notFound();
    return (
      heading(
        "EXECUTION / STEP " + (i + 1),
        step[1],
        `${r.id} · ${step[2]} · illustrative execution`,
        linkButton("← Run detail", "runs/" + id),
      ) +
      `<div class="detail-grid"><section class="card pad"><h3>Observable output</h3>${event ? `<pre>${esc(JSON.stringify(event.output, null, 2))}</pre>` : '<div class="empty">This step has not executed yet.</div>'}<div class="run-summary"><div><small>State</small><strong>${event ? "Recorded" : "Pending"}</strong></div><div><small>Illustrative duration</small><strong>${event ? event.duration + " ms" : "—"}</strong></div></div></section><section class="card pad prose"><h3>Implementation contract</h3><p>This step maps to the ${esc(step[2])} module. Inspect its route declarations and source.</p>${linkButton("Explore module →", "capabilities/" + step[2], "primary")}<div class="notice">These are simulated outputs, not hidden reasoning or a live backend trace.</div></section></div>`
    );
  }
  return (
    heading(
      "RUN EXPLORER",
      s.name,
      `${r.id} · ${r.tenant} · Demonstration`,
      `${linkButton("← All runs", "runs")}<button data-export="${id}">Export evidence ↓</button>`,
    ) +
    `<div class="run-top">${pill(r.status, r.status === "awaiting review" ? "amber" : "")}${pill("support-agent-v1")}${pill("DEMO · simulated events")}${r.status === "running" ? `<button class="small" data-pause="${id}">Pause playback</button>` : r.status === "paused" ? `<button class="small primary" data-resume="${id}">Resume playback</button>` : ""}${r.status === "awaiting review" ? linkButton("Open human review →", "reviews/" + id, "primary") : ""}</div><div class="detail-grid"><section><div class="run-flow">${s.steps.map((st, i) => `<button class="run-step ${i < r.history.length ? "done" : ""} ${i === r.step ? "current" : ""}" data-go="runs/${id}/steps/${i}"><span class="step-number">${i < r.history.length ? "✓" : i + 1}</span><span><strong>${st[1]}</strong><small>${st[2]}</small></span><span class="step-status">${i < r.history.length ? r.history[i].duration + " ms" : i === r.step ? r.status : "Pending"} ↗</span></button>`).join("")}</div></section><section class="card"><div class="panel-heading"><h3>Customer conversation</h3>${pill("WEB")}</div><div class="chat"><div class="bubble user">${esc(s.question)}</div>${r.status === "completed" ? `<div class="bubble">${esc(r.decision === "rejected" ? "The reviewer declined the refund request. The decision and reason have been recorded." : s.answer)}${r.scenario === "policy" ? '<button class="citation" data-document="returns-v1">▧ Returns Policy · v1 · demo source ↗</button>' : ""}</div>` : r.status === "awaiting review" ? '<div class="bubble">This refund needs a human decision. Your conversation is paused while the reviewer assesses the request.</div>' : `<div class="typing">${r.status === "running" ? "● ● ● Agents are working through the steps…" : "Playback paused."}</div>`}</div><div class="pad"><div class="run-summary"><div><small>Recorded steps</small><strong>${r.history.length}/6</strong></div><div><small>Illustrative cost</small><strong>$${r.cost.toFixed(4)}</strong></div><div><small>Trace</small><strong>Demo</strong></div></div></div></section></div>`
  );
}
function reviewPage(id) {
  if (!id)
    return (
      heading(
        "HUMAN OVERSIGHT",
        "Autonomy, with a hand on the wheel.",
        "A sensitive decision pauses the workflow until a human reviews it.",
      ) +
      `<div class="card"><div class="panel-heading"><h3>Review queue</h3>${pill(currentRuns().filter((r) => r.status === "awaiting review").length + " pending", "amber")}</div>${
        currentRuns()
          .filter((r) => r.scenario === "refund")
          .map(
            (r) =>
              `<a class="card-link" href="#/reviews/${r.id}"><span><strong>$850 refund · Order A1029</strong><small style="display:block;margin-top:6px">${esc(r.id)} · ${r.tenant}</small></span>${pill(r.decision || r.status, r.status === "awaiting review" ? "amber" : "")}<span>↗</span></a>`,
          )
          .join("") ||
        '<div class="empty">No reviews yet.<br>Run the high-value refund scenario to create one.</div>'
      }</div>`
    );
  const r = currentRuns().find((x) => x.id === id && x.scenario === "refund");
  if (!r) return notFound();
  return (
    heading(
      "REVIEW / " + esc(id),
      "A decision that belongs to a person.",
      "Refund amount $850 · Fixture threshold $500",
      linkButton("← Review queue", "reviews"),
    ) +
    `<div class="detail-grid"><section class="card pad prose"><h2>Refund request</h2><p>“${esc(scenarioData.refund.question)}”</p><div class="notice">The request exceeds the support workflow’s automatic resolution limit. No payment has been initiated.</div><div class="tag-list">${pill(r.status, "amber")}${pill(r.claimed ? "Claimed by demo reviewer" : "Unclaimed")}</div>${linkButton("Inspect execution evidence →", "runs/" + r.id)}${r.decision ? `<p><strong>Decision: ${esc(r.decision)}</strong><br>${esc(r.reason)}</p>` : ""}</section><section class="card pad"><h3>Reviewer decision</h3><p class="prose" style="margin:15px 0">Claim the request, record a reason, then approve or reject. The demo resumes once.</p>${r.status === "awaiting review" ? `<form id="review-form" data-run="${id}"><label>Decision reason<textarea name="reason" required minlength="8" maxlength="1000" placeholder="Explain why this request should be approved or rejected…"></textarea></label><div class="form-actions">${!r.claimed ? `<button type="button" data-claim="${id}">Claim request</button>` : `<button class="primary" name="decision" value="approved">Approve & resume</button><button name="decision" value="rejected">Reject & resume</button>`}</div></form>` : '<div class="notice">This review is not pending. A second decision cannot be submitted.</div>'}</section></div>`
  );
}
function knowledge() {
  const docs = state.tenant === "Acme" ? state.documents : [];
  return (
    heading(
      "GROUNDED INTELLIGENCE",
      "Knowledge your agents can stand behind.",
      "Inspect the source content used in the demonstration.",
      `<button class="primary" data-action="upload">+ Add demo document</button>`,
    ) +
    `<div class="notice">This is a local document workspace. TXT and Markdown can be previewed; PDF and DOCX ingestion require the Knowledge Base backend. Demo uploads do not alter scenario answers.</div><section class="card">${docs.map((d) => `<div class="document"><span class="doc-icon">${esc(d.type)}</span><div><h4>${esc(d.name)}</h4><small>Version ${d.version} · ${d.status} · Local demo source</small></div><button data-document="${d.id}">Open source ↗</button></div>`).join("") || '<div class="empty">No documents in this demo tenant.</div>'}</section>`
  );
}
function assurance() {
  const runs = currentRuns(),
    done = runs.filter((r) => r.status === "completed");
  return (
    heading(
      "ASSURANCE & ECONOMICS",
      "Evidence is part of the experience.",
      "Review outcomes, decisions and illustrative costs for this browser session.",
      `<button data-action="export-all">Export demo evidence ↓</button>`,
    ) +
    metrics() +
    `<div class="detail-grid"><section class="card pad"><h2>Outcome distribution</h2><div class="chart-bars">${[
      "policy",
      "order",
      "refund",
    ]
      .map((k) => {
        const n = runs.filter((r) => r.scenario === k).length;
        return `<button style="height:${20 + Math.min(n * 15, 90)}px" data-action="outcome-${k}" aria-label="${k}: ${n} runs"><small>${k} · ${n}</small></button>`;
      })
      .join(
        "",
      )}</div><div class="notice" style="margin-top:40px">Counts come from your demo runs. Cost estimates are fixed scenario fixtures and must not be used as commercial pricing.</div></section><section class="card pad"><h2>Control coverage</h2>${[
      ["Guardrails", "guardrails"],
      ["Human review", "human-oversight"],
      ["Audit trail", "auditability"],
      ["Usage metering", "billing-and-metering"],
      ["Evaluation framework", "evaluation-framework"],
    ]
      .map(
        ([n, id]) =>
          `<a class="card-link" href="#/capabilities/${id}">${n}<span>Inspect implementation ↗</span></a>`,
      )
      .join(
        "",
      )}</section></div><section class="card" style="margin-top:22px"><div class="panel-heading"><h3>Recorded evidence</h3>${pill(done.length + " completed runs")}</div>${runs.map((r) => `<a class="card-link" href="#/runs/${r.id}"><span>${scenarioData[r.scenario].name}<small style="display:block;margin-top:5px">${esc(r.id)} · ${r.history.length} step records</small></span>${pill(r.status)}<span>↗</span></a>`).join("") || '<div class="empty">Run a demonstration to generate an inspectable evidence trail.</div>'}</section>`
  );
}
function notFound(message = "That page is not available.") {
  return `<div class="empty"><h2>${esc(message)}</h2><p style="margin:20px">Use the workspace navigation to continue exploring.</p>${linkButton("Return to overview", "overview", "primary")}</div>`;
}
function render() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean),
    [page = "overview", id, tab, step] = parts;
  nav(page);
  $("#breadcrumbs").innerHTML =
    `<a href="#/overview">Workspace</a><span>/</span><a href="#/${page}">${esc({ overview: "Overview", workspace: "Agent workspace", runs: "Activity & runs", reviews: "Human reviews", knowledge: "Knowledge", agents: "Agent setup", assurance: "Assurance", capabilities: "Capabilities" }[page] || "Page")}</a>${id ? `<span>/</span><span>${esc(id.replaceAll("-", " "))}</span>` : ""}`;
  const views = {
    overview: () => overview(),
    workspace: () => workspace(id),
    capabilities: () => capabilities(id, tab),
    agents: () => agentPage(id),
    runs: () => runPage(id, tab === "steps" ? step : undefined),
    reviews: () => reviewPage(id),
    knowledge,
    assurance,
  };
  $("#main").innerHTML = (views[page] || notFound)();
  if (page === "capabilities" && !id) updateCatalogue();
  document.title = `${page.charAt(0).toUpperCase() + page.slice(1)} · Tectonic`;
}
function dialog(title, content) {
  const m = $("#modal");
  m.innerHTML = `<div class="dialog-header"><h2>${title}</h2><button data-action="close" aria-label="Close dialog">×</button></div>${content}`;
  if (!m.open) m.showModal();
}
function documentView(id) {
  const d =
    state.tenant === "Acme" ? state.documents.find((x) => x.id === id) : null;
  if (!d) {
    toast("This document is not available in the selected tenant.");
    return;
  }
  dialog(
    esc(d.name),
    `<div class="tag-list">${pill("Version " + d.version)}${pill(d.status)}${pill("Demonstration source")}</div><div class="card pad prose"><p>${esc(d.content)}</p></div><div class="notice">Source passage preview. This citation is part of the scripted demonstration, not a live retrieval result.</div>${id !== "returns-v1" ? `<div class="form-actions"><button data-doc-status="${id}">${d.status === "Approved" ? "Withdraw" : "Approve"} demo document</button></div>` : ""}`,
  );
}
function exportData(data, name) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    }),
    url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function tour() {
  dialog(
    "Choose a journey.",
    `<p class="prose">Watch observable actions move through Tectonic’s support-agent slice. Each demonstration produces its own navigable trace.</p><div class="journeys">${Object.entries(
      scenarioData,
    )
      .map(
        ([key, s], i) =>
          `<button class="journey" data-scenario="${key}"><span class="number">0${i + 1}</span><div><h4>${s.name}</h4><p>${s.question}</p></div><span class="arrow">▶</span></button>`,
      )
      .join(
        "",
      )}</div><div class="notice">Simulated execution. The corresponding backend scenarios are defined in <code>tests/product-slices/test_support_agent.py</code>.</div>${backend.live_available ? '<button data-action="live-chat">Open connected backend chat ↗</button>' : ""}`,
  );
}
function lead() {
  dialog(
    "Let’s design your first pilot.",
    `<p class="prose" style="margin-bottom:20px">Tell us which customer journey you want to improve. We’ll capture a focused brief for a support-agent pilot.</p><form id="lead-form"><div class="form-grid"><label>Your name<input name="name" required maxlength="100" autocomplete="name"></label><label>Work email<input name="email" type="email" required maxlength="254" autocomplete="email"></label><label>Company<input name="company" required maxlength="160" autocomplete="organization"></label><label>Priority<select name="priority"><option>Customer support</option><option>Knowledge assistant</option><option>Human-reviewed automation</option></select></label><label class="wide">What would a successful pilot achieve?<textarea name="goal" required minlength="15" maxlength="2000" placeholder="The journey, your systems, and the outcome you want…"></textarea></label><label class="wide checkbox"><input type="checkbox" name="consent" required><span>I agree to have these details stored by this deployment’s operator for responding to this enquiry. No email is sent automatically.</span></label></div><div class="form-actions"><button class="primary" type="submit">Submit pilot enquiry ↗</button><small>Stored on this server · never in browser storage</small></div><p id="lead-error" role="alert" class="prose"></p></form>`,
  );
}
function search() {
  dialog(
    "Find your way.",
    `<input type="search" id="global-search" placeholder="Search agents, modules or journeys…" aria-label="Search workspace" style="width:100%"><div id="search-results" class="journeys"></div>`,
  );
  $("#global-search").focus();
  searchResults("");
}
function searchResults(q) {
  const list = [
    ...catalogue.map((m) => ({
      name: m.name,
      path: "capabilities/" + m.id,
      type: "Module",
    })),
    ...agents.map((a) => ({
      name: a.name,
      path: "agents/" + a.id,
      type: "Agent",
    })),
    ...currentRuns().map((r) => ({
      name: r.id,
      path: "runs/" + r.id,
      type: "Run",
    })),
  ]
    .filter((x) => x.name.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 12);
  $("#search-results").innerHTML =
    list
      .map(
        (x) =>
          `<button class="journey" data-go="${x.path}"><div><h4>${esc(x.name)}</h4><p>${x.type}</p></div><span class="arrow">↗</span></button>`,
      )
      .join("") || '<div class="empty">No matching results.</div>';
}
document.addEventListener("click", (e) => {
  const el = e.target.closest(
    "[data-go],[data-action],[data-view],[data-scenario],[data-document],[data-endpoint],[data-export],[data-pause],[data-resume],[data-claim],[data-doc-status]",
  );
  if (!el) return;
  const d = el.dataset;
  if (d.go) {
    $("#modal").close();
    go(d.go);
  } else if (d.view) {
    canvasMode = d.view;
    render();
  } else if (d.scenario) {
    $("#modal").close();
    startRun(d.scenario);
  } else if (d.document) documentView(d.document);
  else if (d.endpoint) {
    const [id, n] = d.endpoint.split(":"),
      r = catalogue.find((m) => m.id === id).routes[Number(n)];
    dialog(
      "API operation",
      `${pill(r.method)}<pre>${esc(r.path)}</pre><p class="prose">Handler: <code>${esc(r.handler)}</code><br>Declared in <code>${esc(r.source)}</code>.</p><div class="notice">Read-only contract inspection. No administrative API call will be executed.</div><a class="card-link" href="https://github.com/baatasaari/tectonic/blob/7a483344598225620184f4cf33439c0ab7d839a7/${r.source}" target="_blank" rel="noopener">Inspect source ↗</a>`,
    );
  } else if (d.export) {
    exportData(
      currentRuns().find((r) => r.id === d.export),
      d.export + ".json",
    );
  } else if (d.pause) {
    clearTimeout(timer);
    timer = null;
    state.runs.find((r) => r.id === d.pause).status = "paused";
    save();
    render();
  } else if (d.resume) {
    if (timer) {
      toast("Another run is already playing.");
      return;
    }
    state.runs.find((r) => r.id === d.resume).status = "running";
    save();
    tickRun(d.resume);
    render();
  } else if (d.claim) {
    const r = currentRuns().find((r) => r.id === d.claim);
    if (r && r.status === "awaiting review") {
      r.claimed = true;
      save();
      render();
      toast("Claimed by the demo reviewer.");
    }
  } else if (d.docStatus) {
    const doc = state.documents.find((x) => x.id === d.docStatus);
    doc.status = doc.status === "Approved" ? "Withdrawn" : "Approved";
    save();
    documentView(doc.id);
    render();
  } else actions(d.action);
});
function actions(action) {
  if (action === "reload") {
    location.reload();
    return;
  }
  if (action === "close") $("#modal").close();
  else if (action === "lead") lead();
  else if (action === "tour") tour();
  else if (action === "profile")
    dialog(
      "Demo operator",
      `<div class="prose"><p>Vijay Rentala · ${esc(state.tenant)} demonstration workspace.</p><p>Demo roles are interface personas, not authenticated backend permissions. The connected chat is restricted to the tenant configured by the server operator.</p></div>`,
    );
  else if (action === "reset") {
    dialog(
      "Reset this demonstration?",
      `<p class="prose">This removes locally saved demo runs, documents and settings. Server-stored pilot enquiries are unaffected.</p><div class="form-actions"><button class="primary" data-action="confirm-reset">Reset demo</button><button data-action="close">Cancel</button></div>`,
    );
  } else if (action === "confirm-reset") {
    clearTimeout(timer);
    timer = null;
    state = initial();
    save();
    $("#modal").close();
    go("overview");
    render();
    toast("Demo reset.");
  } else if (action === "export-all")
    exportData(
      { mode: "demonstration", tenant: state.tenant, runs: currentRuns() },
      "tectonic-demo-evidence.json",
    );
  else if (action === "upload") {
    dialog(
      "Add local knowledge",
      `<form id="document-form"><label>Document title<input name="name" required maxlength="120"></label><label style="margin-top:15px">TXT or Markdown file<input name="file" type="file" accept=".txt,.md,text/plain,text/markdown" required></label><div class="notice">Maximum 200 KB. Content stays in this browser. PDF and DOCX require backend ingestion.</div><button class="primary">Add document</button></form>`,
    );
  } else if (action.startsWith("outcome-")) {
    const key = action.slice(8);
    dialog(
      scenarioData[key].name,
      `<div class="journeys">${
        currentRuns()
          .filter((r) => r.scenario === key)
          .map(
            (r) =>
              `<button class="journey" data-go="runs/${r.id}">${r.id}<span class="arrow">↗</span></button>`,
          )
          .join("") || '<div class="empty">No runs for this scenario yet.</div>'
      }</div><button data-scenario="${key}">Start this demonstration →</button>`,
    );
  } else if (action === "live-chat") liveDialog();
}
document.addEventListener("input", (e) => {
  if (e.target.id === "catalog-search") {
    filter = e.target.value;
    updateCatalogue();
  }
  if (e.target.id === "global-search") searchResults(e.target.value);
});
document.addEventListener("change", (e) => {
  if (e.target.id === "catalog-category") {
    category = e.target.value;
    updateCatalogue();
  }
});
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    search();
  }
  if ((e.key === "Enter" || e.key === " ") && e.target.matches(".zone")) {
    e.preventDefault();
    go(e.target.dataset.go);
  }
});
$("#search-button").onclick = search;
$("#tenant-button").onclick = () =>
  dialog(
    "Switch demo workspace",
    `<p class="prose">Browser demonstration tenants only. This selector does not establish production tenant isolation.</p><div class="journeys">${["Acme", "Globex"].map((t) => `<button class="journey" data-tenant="${t}">${t} Corporation<span class="arrow">${t === state.tenant ? "✓" : "→"}</span></button>`).join("")}</div>`,
  );
$("#modal").addEventListener("click", (e) => {
  const t = e.target.closest("[data-tenant]");
  if (t) {
    clearTimeout(timer);
    timer = null;
    state.runs
      .filter((r) => r.status === "running")
      .forEach((r) => (r.status = "paused"));
    state.tenant = t.dataset.tenant;
    save();
    $("#modal").close();
    go("overview");
    render();
  }
  if (e.target === $("#modal")) {
    const r = $("#modal").getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      $("#modal").close();
  }
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target,
    data = Object.fromEntries(new FormData(form));
  if (form.id === "agent-form") {
    state.config = data;
    save();
    toast("Demo configuration saved in this browser.");
  } else if (form.id === "review-form") {
    const r = currentRuns().find((x) => x.id === form.dataset.run);
    if (!r || !r.claimed || r.status !== "awaiting review") return;
    if (timer) {
      toast("Pause the other run before resuming this workflow.");
      return;
    }
    r.decision = e.submitter.value;
    r.reason = data.reason;
    r.status = "running";
    r.history[3].output = {
      status: r.decision,
      reason: r.reason,
      reviewer: "demo-reviewer",
    };
    r.step = 4;
    save();
    go("runs/" + r.id);
    tickRun(r.id);
  } else if (form.id === "document-form") {
    if (state.tenant !== "Acme") {
      toast("Switch to Acme to edit this demo knowledge workspace.");
      return;
    }
    const file = new FormData(form).get("file");
    if (file.size > 200000 || !/\.(txt|md)$/i.test(file.name)) {
      toast("Choose a TXT or Markdown file under 200 KB.");
      return;
    }
    state.documents.push({
      id: crypto.randomUUID(),
      name: data.name,
      version: 1,
      type: file.name.endsWith(".md") ? "MD" : "TXT",
      status: "Draft",
      content: await file.text(),
    });
    save();
    $("#modal").close();
    render();
    toast("Document added as a draft.");
  } else if (form.id === "lead-form") {
    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      const response = await fetch("/api/leads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...data, consent: true }),
        }),
        result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "Unable to save enquiry.");
      dialog(
        "Your pilot brief is captured.",
        `<div class="notice">Reference ${esc(result.id)}. Saved to this deployment’s enquiry store. No email has been sent.</div><p class="prose">The operator can export the enquiry and follow up with you.</p><div class="form-actions"><button class="primary" data-action="close">Continue exploring</button></div>`,
      );
    } catch (err) {
      $("#lead-error").textContent =
        "The enquiry was not saved. " + err.message;
      submit.disabled = false;
    }
  } else if (form.id === "live-form") {
    await sendLive(data.message, form);
  }
});
let liveSession = null;
function liveDialog() {
  dialog(
    "Connected support conversation",
    `<div class="notice">Real Conversational Engine responses for the server-configured tenant. Detailed step telemetry is not available through this adapter; spatial playback remains a demonstration.</div><div id="live-messages" class="chat"></div><form id="live-form"><label>Message<input name="message" required maxlength="4000" placeholder="What is your returns policy?"></label><div class="form-actions"><button class="primary">Send to backend</button></div></form>`,
  );
}
async function sendLive(message, form) {
  const button = form.querySelector("button");
  button.disabled = true;
  const add = (text, cls = "") => {
    const p = document.createElement("div");
    p.className = "bubble " + cls;
    p.textContent = text;
    $("#live-messages").append(p);
  };
  add(message, "user");
  try {
    if (!liveSession) {
      const response = await fetch("/api/runtime/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      liveSession = result.id;
    }
    const response = await fetch(
        "/api/runtime/sessions/" +
          encodeURIComponent(liveSession) +
          "/messages",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: message }),
        },
      ),
      result = await response.json();
    if (!response.ok) throw new Error(result.error);
    add(result.outbound_message?.content || "No response text returned.");
    form.reset();
  } catch (err) {
    add("Backend request failed: " + err.message);
  } finally {
    button.disabled = false;
  }
}
document.querySelector(".skip").addEventListener("click", (e) => {
  e.preventDefault();
  document.querySelector("#main").focus();
});
window.addEventListener("hashchange", () => {
  render();
  window.scrollTo(0, 0);
});
async function init() {
  try {
    const response = await fetch("catalog.json");
    if (!response.ok) throw new Error("Catalogue unavailable");
    catalogue = await response.json();
    state.runs
      .filter((r) => r.status === "running")
      .forEach((r) => (r.status = "paused"));
    render();
    fetch("/api/config")
      .then((r) => r.json())
      .then((c) => (backend = c))
      .catch(() => {});
  } catch (err) {
    $("#main").innerHTML =
      `<div class="empty"><h2>Could not load the capability catalogue.</h2><p>${esc(err.message)}</p><p>Start the console with <code>python apps/pilot-console/server.py</code>.</p><button data-action="reload">Retry</button></div>`;
  }
}
init();
