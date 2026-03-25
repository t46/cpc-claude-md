/**
 * W Distribution Visualization
 *
 * Embeds w samples using Hugging Face API, projects to 1D via PCA,
 * and renders a kernel density estimate plot.
 * Slider controls which round's distribution is displayed.
 */

const HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2";
const HF_API = `https://api-inference.huggingface.co/pipeline/feature-extraction/${HF_MODEL}`;

// Cache embeddings to avoid re-computing
const embeddingCache = new Map();

async function getEmbedding(text) {
  const key = text.slice(0, 200); // Cache key
  if (embeddingCache.has(key)) return embeddingCache.get(key);

  try {
    const resp = await fetch(HF_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs: text.slice(0, 512) }), // Truncate for model limit
    });
    if (!resp.ok) return null;
    const embedding = await resp.json();
    // HF returns [[...vector...]] for single input
    const vec = Array.isArray(embedding[0]) ? embedding[0] : embedding;
    embeddingCache.set(key, vec);
    return vec;
  } catch {
    return null;
  }
}

async function getEmbeddings(texts) {
  // Batch: try to get all at once, fall back to individual
  const uncached = [];
  const results = new Array(texts.length);

  for (let i = 0; i < texts.length; i++) {
    const key = texts[i].slice(0, 200);
    if (embeddingCache.has(key)) {
      results[i] = embeddingCache.get(key);
    } else {
      uncached.push(i);
    }
  }

  if (uncached.length > 0) {
    try {
      const inputs = uncached.map(i => texts[i].slice(0, 512));
      const resp = await fetch(HF_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs }),
      });
      if (resp.ok) {
        const embeddings = await resp.json();
        for (let j = 0; j < uncached.length; j++) {
          const vec = Array.isArray(embeddings[j]) ? embeddings[j] : null;
          if (vec) {
            embeddingCache.set(texts[uncached[j]].slice(0, 200), vec);
            results[uncached[j]] = vec;
          }
        }
      }
    } catch {}
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

  const maxY = Math.max(...densities.y) || 1;
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

// Main: render distribution for a specific round
async function renderWDistribution(samples, roundIndex, canvas) {
  // Filter samples for this round or all rounds up to this one
  const roundSamples = samples.filter(s => s.round_index <= roundIndex);
  if (roundSamples.length === 0) {
    drawDensity(canvas, null);
    return;
  }

  const texts = roundSamples.map(s => s.content || "");
  const embeddings = await getEmbeddings(texts);

  // Filter out nulls
  const validEmbeddings = [];
  const validTexts = [];
  for (let i = 0; i < embeddings.length; i++) {
    if (embeddings[i]) {
      validEmbeddings.push(embeddings[i]);
      validTexts.push(texts[i]);
    }
  }

  if (validEmbeddings.length < 2) {
    drawDensity(canvas, validEmbeddings.length === 0 ? false : null);
    return;
  }

  const projections = projectTo1D(validEmbeddings);
  const densities = kde(projections);
  drawDensity(canvas, densities, { projections });
}

// Export for app.js
window.renderWDistribution = renderWDistribution;
