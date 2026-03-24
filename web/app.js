const form = document.querySelector("#probeForm");
const submitButton = document.querySelector("#submitButton");
const statusPill = document.querySelector("#statusPill");
const summaryPanel = document.querySelector("#summaryPanel");
const findingsPanel = document.querySelector("#findingsPanel");
const detailPanel = document.querySelector("#detailPanel");

const STORAGE_KEY = "relay-probe-ui:last-config";

const percent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const seconds = (value) => (value == null ? "--" : `${Number(value).toFixed(2)}s`);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function saveDraft(payload) {
  const draft = { ...payload, api_key: "" };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
}

function loadDraft() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const draft = JSON.parse(raw);
    Object.entries(draft).forEach(([key, value]) => {
      const field = form.elements.namedItem(key);
      if (!field) return;
      if (field.type === "checkbox") {
        field.checked = Boolean(value);
      } else {
        field.value = value;
      }
    });
  } catch (_) {
    // Ignore malformed local state.
  }
}

function setStatus(label, mode = "idle") {
  statusPill.textContent = label;
  statusPill.classList.remove("running", "error");
  if (mode === "running") statusPill.classList.add("running");
  if (mode === "error") statusPill.classList.add("error");
}

function gradeClass(grade) {
  return `grade-${String(grade || "").toLowerCase()}`;
}

function severityClass(severity) {
  return `severity-${severity || "low"}`;
}

function pillClass(flag) {
  if (flag === true) return "good";
  if (flag === false) return "bad";
  return "warn";
}

function renderSummary(report) {
  const { overview, config } = report;
  summaryPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <p class="panel-kicker">Overview</p>
        <h2>${escapeHtml(overview.headline)}</h2>
      </div>
      <span class="grade ${gradeClass(overview.grade)}">${escapeHtml(overview.grade)}</span>
    </div>
    <p class="summary-copy">
      本次检测基于 ${escapeHtml(config.models.join(", "))}，重复 ${escapeHtml(config.requests)}
      次，并发 ${escapeHtml(config.concurrency)}。这不是对真实上游的绝对证明，但足够帮你识别明显的伪装和不稳定。
    </p>
    <div class="metric-grid">
      <article class="metric-card">
        <span class="metric-label">综合分数</span>
        <div class="metric-value">${escapeHtml(overview.score)}</div>
        <p class="metric-sub">综合稳定性和元数据一致性</p>
      </article>
      <article class="metric-card">
        <span class="metric-label">平均成功率</span>
        <div class="metric-value">${escapeHtml(percent(overview.avg_success_rate))}</div>
        <p class="metric-sub">重复请求返回成功的比例</p>
      </article>
      <article class="metric-card">
        <span class="metric-label">平均 P95 延迟</span>
        <div class="metric-value">${escapeHtml(seconds(overview.avg_latency_p95_s))}</div>
        <p class="metric-sub">
          ${overview.aliasing_suspected ? "存在别名嫌疑" : "未发现明显别名证据"}
        </p>
      </article>
    </div>
  `;
}

function renderFindings(report) {
  const findings = report.findings
    .map(
      (finding) => `
        <article class="finding-card">
          <header>
            <div>
              <h3>${escapeHtml(finding.title)}</h3>
            </div>
            <span class="severity ${severityClass(finding.severity)}">${escapeHtml(finding.severity)}</span>
          </header>
          <p class="detail-copy">${escapeHtml(finding.detail)}</p>
        </article>
      `
    )
    .join("");

  const listing = report.models_endpoint;
  const listingBlock = listing.enabled
    ? `
      <article class="finding-card">
        <header>
          <div><h3>/models 元数据</h3></div>
          <span class="severity ${severityClass(listing.error ? "medium" : "low")}">
            ${listing.error ? "partial" : "ok"}
          </span>
        </header>
        <p class="detail-copy">
          ${
            listing.error
              ? escapeHtml(listing.error)
              : `HTTP ${listing.status}，返回了 ${listing.models_returned} 个模型 ID。`
          }
        </p>
        ${
          listing.sample_ids?.length
            ? `<div class="code-strip">${escapeHtml(listing.sample_ids.join(", "))}</div>`
            : ""
        }
      </article>
    `
    : `
      <article class="finding-card">
        <header>
          <div><h3>/models 元数据</h3></div>
          <span class="severity severity-low">skipped</span>
        </header>
        <p class="detail-copy">这次你选择了跳过模型列表接口检测。</p>
      </article>
    `;

  findingsPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <p class="panel-kicker">Findings</p>
        <h2>关键发现</h2>
      </div>
    </div>
    <div class="findings-list">
      ${findings}
      ${listingBlock}
    </div>
  `;
}

function renderModelCard(modelReport) {
  const { id, single, json_capability: jsonCapability, stability, assessment } = modelReport;
  const summary = stability.summary;
  const compareNote = assessment.verdicts
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  const samples = stability.samples
    .map(
      (sample, index) => `
        <article class="sample-card">
          <h4>样本 ${index + 1}</h4>
          <p class="sample-meta">
            状态 ${escapeHtml(sample.status ?? "--")} · 延迟 ${escapeHtml(seconds(sample.latency_s))}
          </p>
          <div class="sample-pre">${escapeHtml(sample.text || sample.error || "(empty)")}</div>
        </article>
      `
    )
    .join("");

  return `
    <section class="detail-card">
      <header>
        <div>
          <p class="panel-kicker">Model</p>
          <h3>${escapeHtml(id)}</h3>
        </div>
        <span class="severity ${severityClass(
          assessment.label === "高风险" ? "high" : assessment.label === "需谨慎" ? "medium" : "low"
        )}">${escapeHtml(assessment.label)}</span>
      </header>

      <div class="model-stack">
        <div>
          <div class="detail-subgrid">
            <div class="mini-stat">
              <div class="label">成功率</div>
              <div class="value">${escapeHtml(percent(summary.success_rate))}</div>
            </div>
            <div class="mini-stat">
              <div class="label">精确一致率</div>
              <div class="value">${escapeHtml(percent(summary.exact_match_rate))}</div>
            </div>
            <div class="mini-stat">
              <div class="label">P95 延迟</div>
              <div class="value">${escapeHtml(seconds(summary.latency_p95_s))}</div>
            </div>
          </div>

          <div class="chip-row">
            <span class="pill ${pillClass(!assessment.route_rewritten)}">
              ${assessment.route_rewritten ? "路由被改写" : "模型 ID 一致"}
            </span>
            <span class="pill ${pillClass(jsonCapability.valid_json)}">
              ${jsonCapability.valid_json ? "JSON 能力正常" : "JSON 能力存疑"}
            </span>
            <span class="pill ${pillClass(!assessment.drifting)}">
              ${assessment.drifting ? "检测到漂移" : "路由表现稳定"}
            </span>
          </div>

          <div class="meta-list">
            <div class="meta-line"><strong>response_model:</strong> ${escapeHtml(single.response_model || "--")}</div>
            <div class="meta-line"><strong>system_fingerprint:</strong> ${escapeHtml(
              single.system_fingerprint || "--"
            )}</div>
            <div class="meta-line"><strong>响应文本:</strong> ${escapeHtml(single.text || single.error || "--")}</div>
          </div>

          <ul class="verdict-list">${compareNote}</ul>
        </div>

        <div class="detail-stack">
          <article class="compare-card">
            <h4>稳定性摘要</h4>
            <div class="code-strip">
response_models: ${escapeHtml((summary.response_models || []).join(", ") || "--")}
fingerprints: ${escapeHtml((summary.fingerprints || []).join(", ") || "--")}
output_hashes: ${escapeHtml((summary.unique_output_hashes || []).join(", ") || "--")}
            </div>
          </article>

          <article class="compare-card">
            <h4>JSON 检测</h4>
            <div class="meta-list">
              <div class="meta-line"><strong>状态:</strong> ${escapeHtml(String(jsonCapability.status ?? "--"))}</div>
              <div class="meta-line"><strong>valid_json:</strong> ${jsonCapability.valid_json ? "yes" : "no"}</div>
              <div class="meta-line"><strong>keys:</strong> ${escapeHtml(
                (jsonCapability.json_keys || []).join(", ") || "--"
              )}</div>
            </div>
          </article>
        </div>
      </div>

      <div class="sample-grid">
        ${samples || '<div class="empty-state">没有可展示的样本。</div>'}
      </div>
    </section>
  `;
}

function renderCompare(report) {
  if (!report.compare?.enabled) return "";

  const rows = report.compare.rows
    .map(
      (row) => `
        <div class="compare-row">
          <strong>${escapeHtml(row.requested_model)}</strong>
          <code>${escapeHtml(row.hash || "--")}</code>
          <span>${escapeHtml(row.response_model || row.error || "无 response_model")}</span>
        </div>
      `
    )
    .join("");

  return `
    <section class="compare-card">
      <h4>多模型比对</h4>
      <p class="list-note">
        ${
          report.compare.same_hash
            ? "不同模型 ID 返回了相同的输出哈希，存在共用后端的可能。"
            : "不同模型 ID 的输出没有出现完全重合的哈希。"
        }
      </p>
      <div class="compare-grid">${rows}</div>
    </section>
  `;
}

function renderDetails(report) {
  const modelCards = report.models.map(renderModelCard).join("");
  const compareBlock = renderCompare(report);

  detailPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <p class="panel-kicker">Deep Dive</p>
        <h2>模型明细</h2>
      </div>
    </div>
    <div class="detail-stack">
      ${compareBlock}
      ${modelCards}
    </div>
  `;
}

function collectPayload() {
  const data = new FormData(form);
  return {
    base_url: data.get("base_url")?.toString().trim(),
    api_key: data.get("api_key")?.toString().trim(),
    models: data.get("models")?.toString().trim(),
    requests: Number(data.get("requests")),
    concurrency: Number(data.get("concurrency")),
    timeout: Number(data.get("timeout")),
    temperature: Number(data.get("temperature")),
    max_tokens: Number(data.get("max_tokens")),
    skip_models_endpoint: data.get("skip_models_endpoint") === "on",
  };
}

async function runJsonRequest(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => ({ error: "Server returned invalid JSON." }));
  if (!response.ok) {
    throw new Error(body.error || "Probe failed.");
  }
  return body;
}

async function runProbe(payload) {
  return runJsonRequest("/api/probe", payload);
}

function renderError(message) {
  findingsPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <p class="panel-kicker">Findings</p>
        <h2>请求失败</h2>
      </div>
    </div>
    <article class="finding-card">
      <header>
        <div><h3>这次没有拿到有效结果</h3></div>
        <span class="severity severity-high">error</span>
      </header>
      <p class="detail-copy">${escapeHtml(message)}</p>
    </article>
  `;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = collectPayload();
  saveDraft(payload);

  setStatus("检测中…", "running");
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "正在检测";

  try {
    const report = await runProbe(payload);
    renderSummary(report);
    renderFindings(report);
    renderDetails(report);
    setStatus("检测完成");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    renderError(message);
    setStatus("出现错误", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "开始检测";
  }
});

loadDraft();
