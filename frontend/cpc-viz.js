/**
 * CPC Visualization: agents orbiting around shared knowledge w.
 *
 * Visual metaphor:
 * - Central glowing node = w (shared knowledge)
 * - Orbiting particles = agents (each with their own color)
 * - Lines flowing inward = proposals (agent → w)
 * - Pulses flowing outward = w influencing agents (w → agent)
 * - The cycle repeats, w grows brighter as consensus builds
 */

const canvas = document.getElementById("cpc-canvas");
if (canvas) {
  const ctx = canvas.getContext("2d");
  let W, H;
  let time = 0;
  let agents = [];
  let pulses = [];

  const AGENT_COLORS = [
    "#7b8cff", "#c084fc", "#34d399", "#fbbf24",
    "#f87171", "#60a5fa", "#a78bfa", "#2dd4bf",
    "#fb923c", "#e879f9",
  ];

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    W = canvas.width = rect.width;
    H = canvas.height = rect.height;
  }

  function initAgents(count) {
    agents = [];
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.3;
      const radius = Math.min(W, H) * 0.25 + Math.random() * 30;
      agents.push({
        angle,
        radius,
        speed: 0.003 + Math.random() * 0.004,
        size: 3 + Math.random() * 3,
        color: AGENT_COLORS[i % AGENT_COLORS.length],
        pulsePhase: Math.random() * Math.PI * 2,
      });
    }
  }

  function addPulse(fromAgent, toCenter) {
    const cx = W / 2, cy = H / 2;
    const ax = cx + Math.cos(fromAgent.angle) * fromAgent.radius;
    const ay = cy + Math.sin(fromAgent.angle) * fromAgent.radius;
    pulses.push({
      x: toCenter ? ax : cx,
      y: toCenter ? ay : cy,
      tx: toCenter ? cx : ax,
      ty: toCenter ? cy : ay,
      progress: 0,
      color: fromAgent.color,
      toCenter,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    time += 0.016;

    const cx = W / 2, cy = H / 2;

    // Central w glow
    const glowSize = 20 + Math.sin(time * 0.8) * 5;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowSize * 4);
    grad.addColorStop(0, "rgba(123, 140, 255, 0.3)");
    grad.addColorStop(0.3, "rgba(192, 132, 252, 0.1)");
    grad.addColorStop(1, "transparent");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    // Central node
    ctx.beginPath();
    ctx.arc(cx, cy, glowSize, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(123, 140, 255, 0.15)";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#7b8cff";
    ctx.fill();

    // "w" label
    ctx.fillStyle = "rgba(224, 232, 240, 0.6)";
    ctx.font = "italic 12px serif";
    ctx.textAlign = "center";
    ctx.fillText("w", cx, cy + 20);

    // Draw connection lines (faint)
    for (const agent of agents) {
      const ax = cx + Math.cos(agent.angle) * agent.radius;
      const ay = cy + Math.sin(agent.angle) * agent.radius;

      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(ax, ay);
      ctx.strokeStyle = agent.color.replace(")", ", 0.08)").replace("rgb", "rgba").replace("#", "");
      // Use hex to rgba
      const r = parseInt(agent.color.slice(1, 3), 16);
      const g = parseInt(agent.color.slice(3, 5), 16);
      const b = parseInt(agent.color.slice(5, 7), 16);
      ctx.strokeStyle = `rgba(${r},${g},${b},0.08)`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Draw agents
    for (const agent of agents) {
      agent.angle += agent.speed;
      const ax = cx + Math.cos(agent.angle) * agent.radius;
      const ay = cy + Math.sin(agent.angle) * agent.radius;

      // Agent glow
      const agentGlow = ctx.createRadialGradient(ax, ay, 0, ax, ay, agent.size * 4);
      const r = parseInt(agent.color.slice(1, 3), 16);
      const g = parseInt(agent.color.slice(3, 5), 16);
      const b = parseInt(agent.color.slice(5, 7), 16);
      agentGlow.addColorStop(0, `rgba(${r},${g},${b},0.2)`);
      agentGlow.addColorStop(1, "transparent");
      ctx.fillStyle = agentGlow;
      ctx.fillRect(ax - agent.size * 4, ay - agent.size * 4, agent.size * 8, agent.size * 8);

      // Agent dot
      ctx.beginPath();
      const pulse = 1 + Math.sin(time * 2 + agent.pulsePhase) * 0.2;
      ctx.arc(ax, ay, agent.size * pulse, 0, Math.PI * 2);
      ctx.fillStyle = agent.color;
      ctx.fill();

      // Randomly send pulses
      if (Math.random() < 0.003) addPulse(agent, true);
      if (Math.random() < 0.002) addPulse(agent, false);
    }

    // Draw pulses
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.progress += 0.02;
      if (p.progress >= 1) { pulses.splice(i, 1); continue; }

      const x = p.x + (p.tx - p.x) * p.progress;
      const y = p.y + (p.ty - p.y) * p.progress;
      const r = parseInt(p.color.slice(1, 3), 16);
      const g = parseInt(p.color.slice(3, 5), 16);
      const b = parseInt(p.color.slice(5, 7), 16);
      const alpha = 1 - p.progress;

      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  // Sync agent count with actual agents
  function syncAgents() {
    const count = (window._cpcState && window._cpcState.agents)
      ? Math.max(window._cpcState.agents.length, 5)
      : 7;
    if (agents.length !== count) {
      initAgents(count);
    }
  }

  window.addEventListener("resize", resize);
  resize();
  initAgents(7);
  setInterval(syncAgents, 5000);
  draw();
}
