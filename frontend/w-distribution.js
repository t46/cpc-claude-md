/**
 * W Distribution Visualization
 *
 * Embeds w samples using transformers.js (in-browser), projects to 1D via PCA,
 * and renders a kernel density estimate plot.
 * Slider controls which round's distribution is displayed.
 */

// Cache embeddings to avoid re-computing
const embeddingCache = new Map();
let _pipeline = null;
let _pipelineLoading = false;
let _pipelineFailed = false;

async function getEmbeddingPipeline() {
  if (_pipeline) return _pipeline;
  if (_pipelineFailed) return null;
  if (_pipelineLoading) {
    // Wait for loading to complete
    while (_pipelineLoading) await new Promise(r => setTimeout(r, 200));
    return _pipeline;
  }

  _pipelineLoading = true;
  try {
    const { pipeline } = await import("https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/dist/transformers.min.js");
    _pipeline = await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", { dtype: "fp32" });
    return _pipeline;
  } catch (e) {
    console.error("Failed to load transformers.js:", e);
    _pipelineFailed = true;
    return null;
  } finally {
    _pipelineLoading = false;
  }
}

async function getEmbeddings(texts) {
  const results = new Array(texts.length).fill(null);
  const uncached = [];

  for (let i = 0; i < texts.length; i++) {
    const key = texts[i].slice(0, 200);
    if (embeddingCache.has(key)) {
      results[i] = embeddingCache.get(key);
    } else {
      uncached.push(i);
    }
  }

  if (uncached.length > 0) {
    const pipe = await getEmbeddingPipeline();
    if (!pipe) return results;

    for (const idx of uncached) {
      try {
        const output = await pipe(texts[idx].slice(0, 256), { pooling: "mean", normalize: true });
        const vec = Array.from(output.data);
        embeddingCache.set(texts[idx].slice(0, 200), vec);
        results[idx] = vec;
      } catch {}
    }
  }

  return results;
}

// Simple PCA: project high-dim vectors to 1D (first principal component)
function projectTo1D(vectors) {
  if (vectors.length === 0) return [];
  const dim = vectors[0].length;

  // Compute mean
  const mean = new Array(dim).fill(0);
  for (const v of vectors) {
    for (let i = 0; i < dim; i++) mean[i] += v[i];
  }
  for (let i = 0; i < dim; i++) mean[i] /= vectors.length;

  // Center
  const centered = vectors.map(v => v.map((x, i) => x - mean[i]));

  // Power iteration to find first PC
  let pc = new Array(dim).fill(0).map(() => Math.random() - 0.5);
  for (let iter = 0; iter < 50; iter++) {
    const newPc = new Array(dim).fill(0);
    for (const v of centered) {
      const dot = v.reduce((s, x, i) => s + x * pc[i], 0);
      for (let i = 0; i < dim; i++) newPc[i] += dot * v[i];
    }
    const norm = Math.sqrt(newPc.reduce((s, x) => s + x * x, 0)) || 1;
    pc = newPc.map(x => x / norm);
  }

  // Project
  return centered.map(v => v.reduce((s, x, i) => s + x * pc[i], 0));
}

// Kernel Density Estimation (Gaussian kernel)
function kde(values, numPoints = 100) {
  if (values.length === 0) return { x: [], y: [] };

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const margin = range * 0.2;
  const h = range / Math.max(values.length, 1) * 1.5; // Bandwidth

  const x = [];
  const y = [];
  for (let i = 0; i < numPoints; i++) {
    const xi = (min - margin) + (range + 2 * margin) * i / (numPoints - 1);
    let density = 0;
    for (const v of values) {
      const u = (xi - v) / h;
      density += Math.exp(-0.5 * u * u) / (h * Math.sqrt(2 * Math.PI));
    }
    density /= values.length;
    x.push(xi);
    y.push(density);
  }

  return { x, y };
}

// Draw density plot on canvas
function drawDensity(canvas, densities, options = {}) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.parentElement.clientWidth;
  const H = canvas.height = options.height || 120;

  ctx.clearRect(0, 0, W, H);

  if (!densities || densities.x.length === 0) {
    ctx.fillStyle = "rgba(107, 125, 142, 0.5)";
    ctx.font = "italic 13px sans-serif";
    ctx.textAlign = "center";
    const msg = densities === false ? "Embedding API unavailable" : "Waiting for embeddings...";
    ctx.fillText(msg, W / 2, H / 2);
    return;
  }

  const maxY = options.globalMaxY || Math.max(...densities.y) || 1;
  const pad = { top: 10, bottom: 25, left: 10, right: 10 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  // Draw fill
  ctx.beginPath();
  ctx.moveTo(pad.left, H - pad.bottom);
  for (let i = 0; i < densities.x.length; i++) {
    const x = pad.left + (i / (densities.x.length - 1)) * plotW;
    const y = pad.top + plotH * (1 - densities.y[i] / maxY);
    ctx.lineTo(x, y);
  }
  ctx.lineTo(pad.left + plotW, H - pad.bottom);
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, pad.top, 0, H - pad.bottom);
  grad.addColorStop(0, "rgba(123, 140, 255, 0.3)");
  grad.addColorStop(1, "rgba(192, 132, 252, 0.05)");
  ctx.fillStyle = grad;
  ctx.fill();

  // Draw line
  ctx.beginPath();
  for (let i = 0; i < densities.x.length; i++) {
    const x = pad.left + (i / (densities.x.length - 1)) * plotW;
    const y = pad.top + plotH * (1 - densities.y[i] / maxY);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = "rgba(123, 140, 255, 0.8)";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Draw sample dots on x-axis
  if (options.projections) {
    const xMin = densities.x[0];
    const xMax = densities.x[densities.x.length - 1];
    const xRange = xMax - xMin || 1;
    for (const p of options.projections) {
      const x = pad.left + ((p - xMin) / xRange) * plotW;
      ctx.beginPath();
      ctx.arc(x, H - pad.bottom - 3, 3, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(192, 132, 252, 0.7)";
      ctx.fill();
    }
  }

  // X-axis label
  ctx.fillStyle = "rgba(107, 125, 142, 0.6)";
  ctx.font = "11px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("← w space (1D projection) →", W / 2, H - 3);
}

// Main: render distribution for a specific round, using global axis from all samples
async function renderWDistribution(samples, roundIndex, canvas) {
  if (samples.length < 2) {
    drawDensity(canvas, null);
    return;
  }

  // Embed ALL samples to get a shared PCA projection and axis
  const allTexts = samples.map(s => s.content || "");
  const allEmbeddings = await getEmbeddings(allTexts);

  const validAll = [];
  const validRoundIndices = [];
  for (let i = 0; i < allEmbeddings.length; i++) {
    if (allEmbeddings[i]) {
      validAll.push(allEmbeddings[i]);
      validRoundIndices.push(samples[i].round_index ?? 0);
    }
  }

  if (validAll.length < 2) {
    drawDensity(canvas, validAll.length === 0 ? false : null);
    return;
  }

  // Project ALL to 1D with shared PCA
  const allProjections = projectTo1D(validAll);

  // Global axis range (shared across all rounds)
  const globalMin = Math.min(...allProjections);
  const globalMax = Math.max(...allProjections);

  // Filter to selected round's projections
  const roundProjections = [];
  for (let i = 0; i < allProjections.length; i++) {
    if (validRoundIndices[i] === roundIndex) {
      roundProjections.push(allProjections[i]);
    }
  }

  if (roundProjections.length === 0) {
    drawDensity(canvas, null);
    return;
  }

  // KDE with fixed global axis
  const densities = kdeFixed(roundProjections, globalMin, globalMax);

  // Also compute global KDE for max-y reference (so y-axis is also comparable)
  const globalDensities = kdeFixed(allProjections, globalMin, globalMax);
  const globalMaxY = Math.max(...globalDensities.y);

  drawDensity(canvas, densities, { projections: roundProjections, globalMaxY });
}

// KDE with fixed x-axis range
function kdeFixed(values, xMin, xMax, numPoints = 100) {
  if (values.length === 0) return { x: [], y: [] };

  const range = xMax - xMin || 1;
  const margin = range * 0.15;
  const h = range / Math.max(values.length, 1) * 1.5;

  const x = [];
  const y = [];
  for (let i = 0; i < numPoints; i++) {
    const xi = (xMin - margin) + (range + 2 * margin) * i / (numPoints - 1);
    let density = 0;
    for (const v of values) {
      const u = (xi - v) / h;
      density += Math.exp(-0.5 * u * u) / (h * Math.sqrt(2 * Math.PI));
    }
    density /= values.length;
    x.push(xi);
    y.push(density);
  }

  return { x, y };
}

// Export for app.js
window.renderWDistribution = renderWDistribution;
