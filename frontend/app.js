// ===== Configuration =====
// Set these to your Supabase project, or use the FastAPI server as fallback
const SUPABASE_URL = "https://qpntskjdcrttrwdelveh.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFwbnRza2pkY3J0dHJ3ZGVsdmVoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ0Mzk1OTMsImV4cCI6MjA5MDAxNTU5M30.LpLqSUUB0p_hy-m-AehYiiMwF5WjkPqj8rOdWGOcUpE";
const API_URL = "http://localhost:8111";  // FastAPI server fallback
const DEFAULT_TASK_ID = "cpc-camp-2026-summary";  // Set this to your task ID when using FastAPI mode

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
  laneAgents: [null],
  wPool: [],
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

  // Nav switching
  $$(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      $$(".nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      $$(".view").forEach(v => v.hidden = true);
      $(`#view-${view}`).hidden = false;
    });
  });

  // Join copy button
  const copyBtn = $("#join-copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const text = $("#join-instruction").textContent;
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
      });
    });
  }

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
  const [tasks, agents, proposals, reviews, samples, rounds, activity, wPool] = await Promise.all([
    sb.from("tasks").select("*").order("created_at"),
    sb.from("agents").select("*").order("registered_at"),
    sb.from("proposals").select("*").order("created_at"),
    sb.from("reviews").select("*").order("created_at"),
    sb.from("samples").select("*").order("created_at"),
    sb.from("rounds").select("*").order("round_index"),
    sb.from("activity").select("*").order("created_at", { ascending: false }).limit(50),
    sb.from("w_pool").select("*").order("slot_index"),
  ]);
  state.tasks = tasks.data || [];
  state.agents = agents.data || [];
  state.proposals = proposals.data || [];
  state.agentActivity = activity.data || [];
  state.wPool = wPool.data || [];
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

    try {
      const activityResp = await fetch(`${base}/activity/${taskId}`);
      state.agentActivity = await activityResp.json();
    } catch { state.agentActivity = []; }

    try {
      const wpoolResp = await fetch(`${base}/w-pool/${taskId}`);
      state.wPool = await wpoolResp.json();
    } catch { state.wPool = []; }
  }
}

// ===== Rendering =====
function renderAll() {
  window._cpcState = state; // Expose for CPC visualization
  renderTask();
  renderWCurrent();
  renderActivityFeed();
  renderAgents();
  renderDialogue();
  renderMHNGChain();
  renderConvergence();
  renderHistory();
  renderSamples();
}

function renderTask() {
  const taskId = state.selectedTaskId;
  const task = state.tasks.find(t => (t.id || t.task_id) === taskId);
  if (task) {
    const desc = task.description || "";
    $("#task-description").innerHTML = DOMPurify.sanitize(marked.parse(desc));

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
    $("#wcurrent-content").innerHTML = '<div class="empty waiting">Waiting for shared knowledge to emerge...</div>';
  }
}

function renderActivityFeed() {
  const events = [];
  for (const a of (state.agentActivity || [])) {
    const time = a.timestamp || a.created_at || "";
    const isToolUse = a.activity_type === "tool_use";
    const isThinking = a.activity_type === "thinking";
    const isScore = a.activity_type === "review_score";
    const icon = isToolUse ? "&#x1F527;" : isThinking ? "&#x1F4AD;" : isScore ? "&#x1F50D;" : "&#x26A1;";
    const cls = isToolUse ? "event-tool" : isThinking ? "event-thinking" : isScore ? "event-score" : "event-status";
    events.push({ agent_id: a.agent_id, time, html: `<div class="event ${cls} ${isNew(time) ? 'event-new' : ''}"><span class="event-icon">${icon}</span><span class="event-agent">${esc(a.agent_id)}</span> <span class="event-detail">${esc(a.detail)}</span><span class="event-time">${timeAgo(time)}</span></div>` });
  }

  events.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
  $("#activity-count").textContent = events.length;

  // Agent filter dropdown
  const allAgentIds = [...new Set([
    ...events.map(e => e.agent_id),
    ...(state.agents || []).map(a => a.id || a.agent_id),
  ].filter(Boolean))];

  const toggles = $("#agent-toggles");
  const selected = state.laneAgents[0];
  const options = `<option value="">All agents</option>` +
    allAgentIds.map(id => `<option value="${esc(id)}" ${selected === id ? 'selected' : ''}>${esc(id)}</option>`).join("");
  toggles.innerHTML = `<select class="agent-select" id="agent-filter">${options}</select>`;
  $("#agent-filter").addEventListener("change", (e) => {
    state.laneAgents[0] = e.target.value || null;
    renderActivityFeed();
  });

  // Render events
  const feed = $("#activity-feed-0");
  const filtered = selected ? events.filter(e => e.agent_id === selected) : events;
  const latest = filtered.slice(0, 30);

  feed.innerHTML = latest.map(e => e.html).join("")
    || '<div class="empty waiting">Waiting for agents to start investigating...</div>';
}

function renderDialogue() {
  const taskId = state.selectedTaskId;
  const feed = $("#dialogue-feed");
  if (!feed) return;

  const proposals = state.proposals.filter(p => p.task_id === taskId || !sb);
  const reviews = state.reviews.filter(r => r.task_id === taskId || !sb);

  // Build dialogues: match reviews to proposals to form conversations
  const dialogues = [];

  for (const r of reviews) {
    const proposal = proposals.find(p => (p.id || p.proposal_id) === r.proposal_id);
    if (!proposal) continue;

    const alpha = typeof r.log_alpha === "number"
      ? Math.min(1, Math.exp(Math.min(r.log_alpha, 5))).toFixed(2) : "?";
    const resultCls = r.accepted ? "dialogue-accepted" : "dialogue-rejected";
    const resultIcon = r.accepted ? "&#x2705;" : "&#x274C;";
    const resultText = r.accepted ? "Accepted" : "Rejected";
    const wPreview = (proposal.current_w || "").slice(0, 100);
    const wPrimePreview = (proposal.proposed_w || "").slice(0, 100);

    dialogues.push({
      time: r.created_at || "",
      html: `<div class="dialogue-card ${resultCls} ${isNew(r.created_at) ? 'event-new' : ''}">
        <div class="dialogue-agents">
          <span class="agent-icon">&#x1F916;</span>
          <span class="dialogue-speaker">${esc(proposal.agent_id)}</span>
          <span class="dialogue-arrow">&#x27A1;</span>
          <span class="agent-icon">&#x1F916;</span>
          <span class="dialogue-listener">${esc(r.reviewer_id)}</span>
        </div>
        <div class="dialogue-comparison">
          <div class="dialogue-w">
            <div class="dialogue-label">w (sampled)</div>
            <div class="dialogue-w-preview">${esc(wPreview) || '(empty)'}${wPreview.length >= 100 ? '...' : ''}</div>
          </div>
          <div class="dialogue-vs">vs</div>
          <div class="dialogue-w clickable" data-proposal-id="${esc(proposal.id || proposal.proposal_id || '')}">
            <div class="dialogue-label">w' (proposed)</div>
            <div class="dialogue-w-preview">${esc(wPrimePreview)}${wPrimePreview.length >= 100 ? '...' : ''}</div>
          </div>
        </div>
        <div class="dialogue-result-row">
          <span class="dialogue-verdict">${resultIcon} ${resultText}</span>
          <span class="dialogue-score">r=${alpha}</span>
          <span class="dialogue-scores">${r.score_proposed?.toFixed(0) || '?'} / ${r.score_current?.toFixed(0) || '?'}</span>
          <span class="dialogue-time">${timeAgo(r.created_at)}</span>
        </div>
      </div>`
    });
  }

  // Show pending proposals — check if paired (reviewer evaluating) or not yet paired
  const reviewedProposalIds = new Set(reviews.map(r => r.proposal_id));

  // Build a map of proposal_id -> reviewer from activity events
  const scoringAgents = new Set();
  for (const a of (state.agentActivity || [])) {
    if (a.activity_type === "status" && a.detail === "scoring") scoringAgents.add(a.agent_id);
  }

  for (const p of proposals) {
    const pid = p.id || p.proposal_id;
    if (reviewedProposalIds.has(pid)) continue;
    const preview = (p.proposed_w || "").slice(0, 150);

    // Check if any activity suggests this is being reviewed
    const isBeingReviewed = scoringAgents.size > 0;
    const statusText = isBeingReviewed ? "evaluating..." : "awaiting pair";
    const statusCls = isBeingReviewed ? "dialogue-reviewing" : "dialogue-pending";
    const statusIcon = isBeingReviewed ? "&#x1F914;" : "&#x23F3;";

    dialogues.push({
      time: p.created_at || "",
      html: `<div class="dialogue-card ${statusCls} ${isNew(p.created_at) ? 'event-new' : ''}">
        <div class="dialogue-agents">
          <span class="agent-icon">&#x1F916;</span>
          <span class="dialogue-speaker">${esc(p.agent_id)}</span>
          <span class="dialogue-arrow">${statusIcon}</span>
          <span class="dialogue-listener">${statusText}</span>
        </div>
        <div class="dialogue-comparison">
          <div class="dialogue-w clickable" data-proposal-id="${esc(pid)}">
            <div class="dialogue-label">w' (proposed)</div>
            <div class="dialogue-w-preview">${esc(preview)}${preview.length >= 150 ? '...' : ''}</div>
          </div>
        </div>
      </div>`
    });
  }

  dialogues.sort((a, b) => (b.time || "").localeCompare(a.time || ""));
  $("#dialogue-count").textContent = dialogues.length;

  feed.innerHTML = dialogues.map(d => d.html).join("")
    || '<div class="empty waiting">Waiting for agents to propose and play the language game...</div>';

  feed.querySelectorAll("[data-proposal-id]").forEach(el => {
    el.addEventListener("click", () => showProposalModal(el.dataset.proposalId));
  });
}

function showProposalModal(proposalId) {
  const p = state.proposals.find(x => (x.id || x.proposal_id) === proposalId);
  if (!p) return;

  $("#modal-title").textContent = `Proposal by ${p.agent_id}`;
  $("#modal-meta").textContent = `Round ${p.round_index ?? '?'} | ${p.created_at ? new Date(p.created_at).toLocaleString() : ''}`;
  $("#modal-proposed-w").innerHTML = DOMPurify.sanitize(marked.parse(p.proposed_w || "(empty)"));
  $("#modal-reasoning").innerHTML = DOMPurify.sanitize(marked.parse(p.reasoning || "(no reasoning recorded)"));
  $("#modal-observations").innerHTML = DOMPurify.sanitize(marked.parse(p.observation_summary || "(no observations recorded)"));
  $("#proposal-modal").hidden = false;
}

function renderAgents() {
  const list = $("#agents-list");
  const agents = state.agents;
  $("#agent-count").textContent = agents.length;

  if (agents.length === 0) {
    list.innerHTML = '<div class="empty waiting">Waiting for agents to join...</div>';
    return;
  }

  list.innerHTML = agents.map(a => {
    const id = a.id || a.agent_id;
    const spec = a.specialization || "";
    const lastSeen = a.last_seen;
    const status = getAgentStatus(lastSeen);
    const statusLabel = status === "active" ? "active" : status === "idle" ? "idle" : "offline";
    const lastSeenText = lastSeen ? timeAgo(lastSeen) : "never";
    return `<div class="agent-card">
      <span class="agent-icon-small">&#x1F916;</span>
      <span class="agent-dot ${status}"></span>
      <div class="agent-info">
        <span class="agent-name">${esc(id)}</span>
        <span class="agent-spec">${esc(spec)}</span>
      </div>
      <span class="agent-status-label ${status}">${statusLabel}</span>
      <span class="agent-lastseen">${lastSeenText}</span>
    </div>`;
  }).join("");
}

function renderMHNGChain() {
  const chain = $("#mhng-chain");
  const reviews = state.reviews.filter(r => r.task_id === state.selectedTaskId || !sb);

  if (reviews.length === 0) {
    chain.innerHTML = '<div class="empty waiting">Waiting for the first language game...</div>';
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
      const alpha = typeof r.log_alpha === "number" ? Math.min(1, Math.exp(Math.min(r.log_alpha, 5))).toFixed(2) : "?";
      html += `<div class="chain-node ${cls}" title="Round ${ri}: ${r.accepted ? 'accepted' : 'rejected'}\nscores: ${r.score_proposed?.toFixed(0)}/${r.score_current?.toFixed(0)}\nr=${alpha}">
        <div class="chain-round">R${ri}</div>
        <div class="chain-alpha">r=${alpha}</div>
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
  $("#stat-samples").textContent = total;

  const currentRound = samples.length > 0
    ? Math.max(...samples.map(s => s.round_index || 0))
    : 0;
  $("#stat-round").textContent = currentRound;

  // Negative log-compatibility chart: -Σ logit(score_k(w)) per round
  // logit(s) = ln(s / (100 - s + 0.5)), approximating ln p(z^k | w)
  const reviews = state.reviews.filter(r => r.task_id === taskId || !sb);
  const logitScore = (s) => {
    s = Math.max(0.5, Math.min(99.5, s));
    return Math.log(s / (100 - s + 0.5));
  };

  const logCompatByRound = {};
  for (const r of reviews) {
    const ri = r.round_index || 0;
    if (!logCompatByRound[ri]) logCompatByRound[ri] = { sum: 0, count: 0 };
    const sp = r.score_proposed ?? 50;
    logCompatByRound[ri].sum += logitScore(sp);
    logCompatByRound[ri].count++;
  }

  const lcRoundKeys = Object.keys(logCompatByRound).map(Number).sort();
  const lcChart = $("#logcompat-chart");

  if (lcRoundKeys.length === 0) {
    lcChart.innerHTML = '<div class="empty">No data yet</div>';
    $("#stat-logcompat").textContent = "-";
    return;
  }

  // Compute per-round negative log-compatibility: -LC = -Σ_k logit(score_k(w))
  // This approximates a component of the variational free energy F.
  // Decreases as MHNG converges (lower = better).
  const nlcValues = lcRoundKeys.map(ri => {
    const d = logCompatByRound[ri];
    return d.count > 0 ? -(d.sum / d.count) : 0;
  });

  // Show latest value in stat
  const latestNLC = nlcValues[nlcValues.length - 1];
  $("#stat-logcompat").textContent = latestNLC.toFixed(2);

  // Normalize for bar display: higher bars = higher -LC (worse)
  const nlcMin = Math.min(...nlcValues);
  const nlcMax = Math.max(...nlcValues);
  const nlcRange = Math.max(nlcMax - nlcMin, 0.1);

  lcChart.innerHTML = lcRoundKeys.map((ri, i) => {
    const val = nlcValues[i];
    const pct = ((val - nlcMin) / nlcRange) * 100;
    return `<div class="conv-bar-wrap">
      <div class="conv-bar" style="height:${Math.max(4, pct)}%;background:var(--accent)" title="Round ${ri}: -LC = ${val.toFixed(3)}"></div>
      <div class="conv-bar-label">R${ri}</div>
    </div>`;
  }).join("");
}

function renderHistory() {
  const container = $("#w-history");
  if (!container) return;

  const taskId = state.selectedTaskId;
  const allSamples = state.samples.filter(s => s.task_id === taskId || !sb);
  const wPool = state.wPool || [];

  let html = "";

  // Show current W distribution if pool exists
  if (wPool.length > 0) {
    html += `<div class="w-pool-section">
      <h3>Current W Distribution (${wPool.length} slots)</h3>
      <div class="w-pool-grid">${wPool.map((slot, i) => {
        const preview = (slot.content || "").slice(0, 100);
        return `<div class="w-pool-slot">
          <div class="w-pool-slot-header">Slot ${i}</div>
          <div class="w-pool-slot-content">${esc(preview) || '(empty)'}${preview.length >= 100 ? '...' : ''}</div>
        </div>`;
      }).join("")}</div>
    </div>`;
  }

  // Group samples by round
  const byRound = {};
  for (const s of allSamples) {
    const ri = s.round_index ?? 0;
    if (!byRound[ri]) byRound[ri] = [];
    byRound[ri].push(s);
  }

  const roundKeys = Object.keys(byRound).map(Number).sort().reverse();

  if (roundKeys.length === 0 && wPool.length === 0) {
    container.innerHTML = '<div class="empty">No samples yet — w has not emerged.</div>';
    return;
  }

  html += roundKeys.map(ri => {
    const roundSamples = byRound[ri];
    const accepted = roundSamples.filter(s => s.accepted);
    const rejected = roundSamples.filter(s => !s.accepted);

    return `<div class="w-round">
      <div class="w-round-header">
        <span class="w-round-label">Round ${ri}</span>
        <span class="w-round-stats">${accepted.length} accepted, ${rejected.length} rejected</span>
      </div>
      <div class="w-round-samples">
        ${roundSamples.map(s => {
          const contentHtml = DOMPurify.sanitize(marked.parse(s.content || ""));
          const statusCls = s.accepted ? "w-sample-accepted" : "w-sample-rejected";
          const statusIcon = s.accepted ? "&#x2705;" : "&#x274C;";
          return `<div class="w-sample ${statusCls}">
            <div class="w-sample-header">
              <span>${statusIcon}</span>
              <span class="w-sample-by">by ${esc(s.proposer_id || '?')}</span>
              <span class="w-sample-time">${s.created_at ? timeAgo(s.created_at) : ''}</span>
            </div>
            <div class="w-sample-body markdown-body">${contentHtml}</div>
          </div>`;
        }).join("")}
      </div>
    </div>`;
  }).join("");

  container.innerHTML = html;
}

function renderSamples() {
  const taskId = state.selectedTaskId;
  const samples = state.samples.filter(s => s.task_id === taskId || !sb);
  const list = $("#samples-list");
  if (!list) return;

  $("#samples-count").textContent = samples.length;

  if (samples.length === 0) {
    list.innerHTML = '<div class="empty">No samples yet</div>';
    return;
  }

  // Show newest first
  const sorted = [...samples].reverse();
  list.innerHTML = sorted.map((s, i) => {
    const idx = samples.length - 1 - i;
    const status = s.accepted ? "accepted" : "rejected";
    const statusCls = s.accepted ? "sample-accepted" : "sample-rejected";
    const preview = (s.content || "").slice(0, 200);
    const previewHtml = DOMPurify.sanitize(marked.parse(preview + (preview.length >= 200 ? '...' : '')));
    return `<div class="sample-card ${statusCls}" data-sample-idx="${idx}">
      <div class="sample-header">
        <span class="sample-idx">w<sup>[${idx}]</sup></span>
        <span class="sample-status ${statusCls}">${status}</span>
        <span class="sample-round">Round ${s.round_index ?? '?'}</span>
        <span class="sample-by">by ${esc(s.proposer_id || '?')}</span>
        <span class="sample-time">${s.created_at ? timeAgo(s.created_at) : ''}</span>
      </div>
      <div class="sample-preview">${previewHtml}</div>
    </div>`;
  }).join("");

  // Click to expand sample
  list.querySelectorAll(".sample-card").forEach(el => {
    el.addEventListener("click", () => {
      const idx = parseInt(el.dataset.sampleIdx);
      const s = samples[idx];
      if (!s) return;
      $("#modal-title").textContent = `Sample w[${idx}]`;
      $("#modal-meta").textContent = `${s.accepted ? 'Accepted' : 'Rejected'} | Round ${s.round_index ?? '?'} | by ${s.proposer_id || '?'}`;
      $("#modal-proposed-w").innerHTML = DOMPurify.sanitize(marked.parse(s.content || "(empty)"));
      $("#modal-reasoning").textContent = "";
      $("#modal-observations").textContent = "";
      $("#proposal-modal").hidden = false;
    });
  });
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
