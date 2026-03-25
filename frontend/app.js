// ===== Configuration =====
// Set these to your Supabase project, or use the FastAPI server as fallback
const SUPABASE_URL = "";  // e.g. "https://xxx.supabase.co"
const SUPABASE_ANON_KEY = "";
const API_URL = "http://localhost:8111";  // FastAPI server fallback
const DEFAULT_TASK_ID = "demo-perf";  // Set this to your task ID when using FastAPI mode

// Use Supabase if configured, otherwise fall back to FastAPI REST
let sb = null;
if (SUPABASE_URL && SUPABASE_ANON_KEY && window.supabase) {
  sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}

// ===== State =====
let state = {
  tasks: [],
  agents: [],
  proposals: [],
  reviews: [],
  samples: [],
  rounds: [],
  selectedTaskId: null,
  prevProposalCount: 0,
  prevReviewCount: 0,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ===== Initialization =====
document.addEventListener("DOMContentLoaded", () => {
  fetchAll();
  setInterval(fetchAll, 3000);

  $("#modal-close").addEventListener("click", () => { $("#proposal-modal").hidden = true; });
  $("#proposal-modal").addEventListener("click", (e) => {
    if (e.target === $("#proposal-modal")) $("#proposal-modal").hidden = true;
  });
  $("#about-btn").addEventListener("click", () => { $("#about-modal").hidden = false; });
  $("#about-close").addEventListener("click", () => { $("#about-modal").hidden = true; });
  $("#about-modal").addEventListener("click", (e) => {
    if (e.target === $("#about-modal")) $("#about-modal").hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      $("#proposal-modal").hidden = true;
      $("#about-modal").hidden = true;
    }
  });

  // Render KaTeX
  $$(".math-tex").forEach((el) => {
    katex.render(el.textContent, el, { throwOnError: false });
  });
});

// ===== Data Fetching =====
async function fetchAll() {
  try {
    if (sb) {
      await fetchFromSupabase();
    } else {
      await fetchFromAPI();
    }
    renderAll();
    $("#connection-status").className = "status-dot online";
  } catch (err) {
    console.error("Fetch error:", err);
    $("#connection-status").className = "status-dot offline";
  }
}

async function fetchFromSupabase() {
  const [tasks, agents, proposals, reviews, samples, rounds] = await Promise.all([
    sb.from("tasks").select("*").order("created_at"),
    sb.from("agents").select("*").order("registered_at"),
    sb.from("proposals").select("*").order("created_at"),
    sb.from("reviews").select("*").order("created_at"),
    sb.from("samples").select("*").order("created_at"),
    sb.from("rounds").select("*").order("round_index"),
  ]);
  state.tasks = tasks.data || [];
  state.agents = agents.data || [];
  state.proposals = proposals.data || [];
  state.reviews = reviews.data || [];
  state.samples = samples.data || [];
  state.rounds = rounds.data || [];
  if (!state.selectedTaskId && state.tasks.length > 0) {
    state.selectedTaskId = state.tasks[0].id;
  }
}

async function fetchFromAPI() {
  const base = API_URL;
  const resp = await fetch(`${base}/health`);
  if (!resp.ok) throw new Error("Server not reachable");

  const agentsResp = await fetch(`${base}/agents`);
  state.agents = await agentsResp.json();

  if (!state.selectedTaskId) state.selectedTaskId = DEFAULT_TASK_ID;
  if (state.selectedTaskId) {
    const taskId = state.selectedTaskId;
    try {
      const taskResp = await fetch(`${base}/tasks/${taskId}`);
      if (taskResp.ok) {
        const task = await taskResp.json();
        state.tasks = [task];
      }
    } catch {}

    try {
      const samplesResp = await fetch(`${base}/samples/${taskId}`);
      state.samples = await samplesResp.json();
    } catch { state.samples = []; }

    try {
      const diagResp = await fetch(`${base}/diagnostics/${taskId}`);
      state.diagnostics = await diagResp.json();
    } catch {}

    try {
      const roundResp = await fetch(`${base}/rounds/${taskId}/current`);
      const roundData = await roundResp.json();
      if (roundData.round_index !== undefined) {
        state.rounds = [roundData];
      }
    } catch {}

    try {
      const proposalsResp = await fetch(`${base}/proposals/${taskId}`);
      state.proposals = await proposalsResp.json();
    } catch { state.proposals = []; }

    try {
      const reviewsResp = await fetch(`${base}/reviews/${taskId}`);
      state.reviews = await reviewsResp.json();
    } catch { state.reviews = []; }
  }
}

// ===== Rendering =====
function renderAll() {
  renderTask();
  renderWCurrent();
  renderActivityFeed();
  renderAgents();
  renderMHNGChain();
  renderConvergence();
}

function renderTask() {
  const taskId = state.selectedTaskId;
  const task = state.tasks.find(t => (t.id || t.task_id) === taskId);
  if (task) {
    const desc = task.description || "";
    $("#task-description").textContent = desc.length > 300 ? desc.slice(0, 300) + "..." : desc;

    const maxRounds = task.max_rounds || 100;
    const currentRound = state.rounds.length > 0
      ? Math.max(...state.rounds.map(r => r.round_index || 0))
      : 0;
    const pct = Math.min(100, (currentRound / maxRounds) * 100);
    $("#round-progress").innerHTML = `
      <div class="progress-label">Round ${currentRound} / ${maxRounds}</div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
    `;
  }
}

function renderWCurrent() {
  const taskId = state.selectedTaskId;
  const accepted = state.samples.filter(s => s.accepted && (s.task_id === taskId || !s.task_id));
  if (accepted.length > 0) {
    const latest = accepted[accepted.length - 1];
    const html = DOMPurify.sanitize(marked.parse(latest.content || ""));
    $("#wcurrent-content").innerHTML = html;
  } else {
    $("#wcurrent-content").textContent = "No accepted samples yet";
  }
}

function renderActivityFeed() {
  const feed = $("#activity-feed");
  const taskId = state.selectedTaskId;
  const events = [];

  // Build events from proposals and reviews
  const proposals = state.proposals.filter(p => p.task_id === taskId || !sb);
  const reviews = state.reviews.filter(r => r.task_id === taskId || !sb);

  for (const p of proposals) {
    const time = p.created_at ? timeAgo(p.created_at) : "";
    const obs = p.observation_summary ? p.observation_summary.slice(0, 120) : "";
    events.push({
      time: p.created_at || "",
      html: `<div class="event event-propose ${isNew(p.created_at) ? 'event-new' : ''}">
        <span class="event-icon">&#x1F7E2;</span>
        <span class="event-agent">${esc(p.agent_id)}</span> proposed
        ${obs ? `<span class="event-obs">"${esc(obs)}${obs.length >= 120 ? '...' : ''}"</span>` : ''}
        <span class="event-time">${time}</span>
      </div>`
    });
  }

  for (const r of reviews) {
    const time = r.created_at ? timeAgo(r.created_at) : "";
    const icon = r.accepted ? "&#x2705;" : "&#x274C;";
    const cls = r.accepted ? "event-accept" : "event-reject";
    const alpha = typeof r.log_alpha === "number" ? `&alpha;=${Math.exp(Math.min(r.log_alpha, 5)).toFixed(2)}` : "";
    events.push({
      time: r.created_at || "",
      html: `<div class="event ${cls} ${isNew(r.created_at) ? 'event-new' : ''}">
        <span class="event-icon">${icon}</span>
        <span class="event-agent">${esc(r.reviewer_id)}</span>
        ${r.accepted ? "ACCEPTED" : "rejected"}
        <span class="event-scores">(${r.score_proposed?.toFixed(0) || '?'}/${r.score_current?.toFixed(0) || '?'}) ${alpha}</span>
        <span class="event-time">${time}</span>
      </div>`
    });
  }

  // Sort by time descending, take latest 20
  events.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
  const latest = events.slice(0, 20);

  feed.innerHTML = latest.map(e => e.html).join("") || '<div class="empty">Waiting for agent activity...</div>';
  $("#activity-count").textContent = events.length;

  // Detect new events for animation
  state.prevProposalCount = proposals.length;
  state.prevReviewCount = reviews.length;
}

function renderAgents() {
  const list = $("#agents-list");
  const agents = state.agents;
  $("#agent-count").textContent = agents.length;

  if (agents.length === 0) {
    list.innerHTML = '<div class="empty">No agents registered</div>';
    return;
  }

  list.innerHTML = agents.map(a => {
    const id = a.id || a.agent_id;
    const spec = a.specialization || "";
    const lastSeen = a.last_seen;
    const status = getAgentStatus(lastSeen);
    return `<div class="agent-card">
      <span class="agent-dot ${status}"></span>
      <span class="agent-name">${esc(id)}</span>
      <span class="agent-spec">${esc(spec)}</span>
    </div>`;
  }).join("");
}

function renderMHNGChain() {
  const chain = $("#mhng-chain");
  const reviews = state.reviews.filter(r => r.task_id === state.selectedTaskId || !sb);

  if (reviews.length === 0) {
    chain.innerHTML = '<div class="empty">No MHNG steps yet</div>';
    return;
  }

  // Group by round
  const byRound = {};
  for (const r of reviews) {
    const ri = r.round_index || 0;
    if (!byRound[ri]) byRound[ri] = [];
    byRound[ri].push(r);
  }

  let html = '<div class="chain-line">';
  const roundKeys = Object.keys(byRound).map(Number).sort();

  for (const ri of roundKeys) {
    const roundReviews = byRound[ri];
    for (const r of roundReviews) {
      const cls = r.accepted ? "chain-accept" : "chain-reject";
      const alpha = typeof r.log_alpha === "number" ? Math.exp(Math.min(r.log_alpha, 5)).toFixed(2) : "?";
      html += `<div class="chain-node ${cls}" title="Round ${ri}: ${r.accepted ? 'accepted' : 'rejected'}\nscores: ${r.score_proposed?.toFixed(0)}/${r.score_current?.toFixed(0)}\n&alpha;=${alpha}">
        <div class="chain-round">R${ri}</div>
        <div class="chain-alpha">&alpha;=${alpha}</div>
        <div class="chain-scores">${r.score_proposed?.toFixed(0) || '?'} / ${r.score_current?.toFixed(0) || '?'}</div>
      </div>`;
      html += `<div class="chain-edge ${cls}"></div>`;
    }
  }

  html += '</div>';
  chain.innerHTML = html;
  // Scroll to end
  chain.scrollLeft = chain.scrollWidth;
}

function renderConvergence() {
  const taskId = state.selectedTaskId;
  const samples = state.samples.filter(s => s.task_id === taskId || !sb);

  const total = samples.length;
  const accepted = samples.filter(s => s.accepted).length;
  const rate = total > 0 ? (accepted / total * 100).toFixed(0) : "-";

  $("#stat-rate").textContent = rate !== "-" ? `${rate}%` : "-";
  $("#stat-samples").textContent = total;
  $("#stat-accepted").textContent = accepted;

  const currentRound = samples.length > 0
    ? Math.max(...samples.map(s => s.round_index || 0))
    : 0;
  $("#stat-round").textContent = currentRound;

  // Per-round acceptance bars
  const byRound = {};
  for (const s of samples) {
    const ri = s.round_index || 0;
    if (!byRound[ri]) byRound[ri] = { total: 0, accepted: 0 };
    byRound[ri].total++;
    if (s.accepted) byRound[ri].accepted++;
  }

  const bars = $("#convergence-bars");
  const roundKeys = Object.keys(byRound).map(Number).sort();
  if (roundKeys.length === 0) {
    bars.innerHTML = '<div class="empty">No data yet</div>';
    return;
  }

  bars.innerHTML = roundKeys.map(ri => {
    const d = byRound[ri];
    const pct = d.total > 0 ? (d.accepted / d.total * 100) : 0;
    return `<div class="conv-bar-wrap">
      <div class="conv-bar" style="height:${Math.max(4, pct)}%" title="Round ${ri}: ${d.accepted}/${d.total} accepted"></div>
      <div class="conv-bar-label">R${ri}</div>
    </div>`;
  }).join("");
}

// ===== Helpers =====
function esc(s) { return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function timeAgo(ts) {
  if (!ts) return "";
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 10) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function isNew(ts) {
  if (!ts) return false;
  return (Date.now() - new Date(ts).getTime()) < 10000; // Last 10 seconds
}

function getAgentStatus(lastSeen) {
  if (!lastSeen) return "offline";
  const diff = (Date.now() - new Date(lastSeen).getTime()) / 1000;
  if (diff < 60) return "active";
  if (diff < 300) return "idle";
  return "offline";
}
