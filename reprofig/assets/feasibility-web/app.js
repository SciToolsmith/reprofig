(function () {
  "use strict";

  const report = window.__REPROFIG_REPORT__;
  if (!report || report.schemaVersion !== "reprofig.report/v1") {
    document.body.textContent = "ReproFig 报告数据无效。";
    return;
  }

  const levelLabels = {
    "direct-recompute": "原案例可复算",
    "mechanism-reproduction": "机制可复现",
    "alternative-validation": "可替代验证",
    "editable-reconstruction": "可编辑重构",
    "original-case-blocked": "原案例受阻"
  };
  const stateLabels = {
    verified: ["✓", "已核验"],
    derivable: ["↗", "可推导"],
    assumable: ["◇", "可设定"],
    missing: ["×", "缺失"],
    "not-required": ["—", "不适用"]
  };
  const routeLabels = { ready: "可执行", conditional: "有条件", blocked: "受阻" };
  const canonicalGatedEffects = new Set(["network", "install", "login", "payment", "upload", "overwrite", "gpu", "shared-license", "external-publish"]);
  const effectLabels = {
    "run-local-code": "运行本机代码",
    "create-workspace-files": "创建工作区文件",
    network: "联网",
    install: "安装依赖",
    login: "登录",
    payment: "付费",
    upload: "上传",
    overwrite: "覆盖文件",
    gpu: "使用 GPU",
    "shared-license": "占用共享许可证",
    "external-publish": "对外发布"
  };
  const figures = report.figures || [];
  const sourcesById = new Map((report.sources || []).map((source) => [source.sourceId, source]));
  const currentRoutes = new Map();
  const included = new Set();
  const consents = new Set();
  const parameterValues = new Map();
  const sensitiveName = /(?:authorization|cookie|credential|password|private[_-]?key|secret|session|token)/i;
  const sensitiveQueryName = /^(?:access[_-]?key|api[_-]?key|auth|authorization|credential|password|secret|signature|sig|token|x-amz-.*)$/i;
  let currentFigureId = figures[0] && figures[0].figureId;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function append(parent, ...children) {
    children.filter(Boolean).forEach((child) => parent.appendChild(child));
    return parent;
  }

  function publicHostname(value) {
    const host = value.replace(/^\[|\]$/g, "").replace(/\.$/, "").toLowerCase();
    if (!host || !host.includes(".") || host === "localhost" || [".localhost", ".local", ".internal", ".intranet", ".corp", ".lan", ".home", ".onion"].some((suffix) => host.endsWith(suffix))) return false;
    if (host.includes(":")) return false; // Conservatively reject IP-literal URLs.
    if (/^\d+(?:\.\d+){3}$/.test(host)) {
      const parts = host.split(".").map(Number);
      if (parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return false;
      if (parts[0] === 0 || parts[0] === 10 || parts[0] === 127 || parts[0] >= 224) return false;
      if (parts[0] === 169 && parts[1] === 254) return false;
      if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return false;
      if (parts[0] === 192 && parts[1] === 168) return false;
      if (parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127) return false;
    }
    return true;
  }

  function safeExternalHref(value) {
    if (typeof value !== "string") return null;
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) return null;
      if (value.includes("#") || url.hash) return null;
      if (!publicHostname(url.hostname)) return null;
      for (const key of url.searchParams.keys()) if (sensitiveQueryName.test(key)) return null;
      return url.href;
    } catch (_error) {
      return null;
    }
  }

  function safeRelative(value) {
    if (typeof value !== "string" || !value || /[\\\u0000-\u001f\u007f]/.test(value) || value.includes("%") || value.includes("#")) return false;
    if (value.startsWith("/") || value.startsWith("~") || /^[A-Za-z][A-Za-z0-9+.-]*:/.test(value)) return false;
    const parts = value.split("/");
    return parts.every((part) => part && part !== "." && part !== "..");
  }

  function safeAssetPath(value) {
    return safeRelative(value) ? value : null;
  }

  function safeImagePath(image) {
    if (!image || image.mediaType !== "image/png") return null;
    const value = safeAssetPath(image.relativePath);
    return value && /\.png$/i.test(value) ? value : null;
  }

  function safeParameterValue(spec, value) {
    if (sensitiveName.test(spec.parameterId || "")) return { valid: false };
    if (value === undefined || value === null || value === "") return { valid: !spec.required, value };
    if (spec.type === "boolean") return { valid: typeof value === "boolean", value };
    if (spec.type === "integer") {
      const valid = Number.isInteger(value) && (spec.min === undefined || value >= spec.min) && (spec.max === undefined || value <= spec.max);
      return { valid, value };
    }
    if (spec.type === "number") {
      const valid = typeof value === "number" && Number.isFinite(value) && (spec.min === undefined || value >= spec.min) && (spec.max === undefined || value <= spec.max);
      return { valid, value };
    }
    if (spec.type === "enum") return { valid: typeof value === "string" && (spec.enum || []).includes(value), value };
    if (spec.type === "relative-path") return { valid: typeof value === "string" && safeRelative(value), value };
    if (spec.type === "string") return { valid: typeof value === "string" && value.length <= 4096, value };
    return { valid: false };
  }

  function containsSensitiveData(value, key) {
    if (key && sensitiveName.test(key)) return true;
    if (Array.isArray(value)) return value.some((item) => containsSensitiveData(item));
    if (value && typeof value === "object") return Object.entries(value).some(([childKey, child]) => containsSensitiveData(child, childKey));
    return false;
  }

  function randomUuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    if (!window.crypto || typeof window.crypto.getRandomValues !== "function") return null;
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }

  function routeFor(figure, routeId) {
    return (figure.routes || []).find((route) => route.routeId === routeId);
  }

  function defaultRoute(figure) {
    const recommended = routeFor(figure, figure.reproduction && figure.reproduction.recommendedRouteId);
    if (recommended && recommended.status !== "blocked") return recommended;
    return (figure.routes || []).find((route) => route.status !== "blocked") || null;
  }

  function needsConsent(effect) {
    return canonicalGatedEffects.has(effect) || (report.approvalPolicy.consentRequiredEffects || []).includes(effect);
  }

  function formatBytes(value) {
    if (value === null || value === undefined) return "待确认";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let amount = value;
    let unit = 0;
    while (amount >= 1024 && unit < units.length - 1) {
      amount /= 1024;
      unit += 1;
    }
    return `${unit === 0 ? amount : amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unit]}`;
  }

  function formatNumber(value, suffix) {
    return value === null || value === undefined ? "待确认" : `${value}${suffix}`;
  }

  function renderRouteFacts(route) {
    const wrapper = node("span", "route-facts");
    const effects = node("span", "effect-list");
    (route.effects || []).forEach((effect) => {
      const item = node("span", "effect-chip", `${effectLabels[effect] || effect} (${effect})${needsConsent(effect) ? " · 需授权" : ""}`);
      item.dataset.gated = needsConsent(effect) ? "true" : "false";
      effects.appendChild(item);
    });
    if (!(route.effects || []).length) effects.appendChild(node("span", "effect-chip", "无声明影响"));

    const estimate = route.estimated || {};
    const resources = node("span", "resource-list");
    [
      `下载 ≤ ${formatBytes(estimate.downloadBytes)}`,
      `磁盘 ≤ ${formatBytes(estimate.diskBytes)}`,
      `运行 ≤ ${formatNumber(estimate.runtimeMinutes, " 分钟")}`,
      estimate.gpu ? "GPU：需要" : "GPU：不需要",
      `费用 ≤ ${estimate.costUsd === null || estimate.costUsd === undefined ? "待确认" : `$${estimate.costUsd}`}`
    ].forEach((text) => resources.appendChild(node("span", "resource-chip", text)));
    append(wrapper, effects, resources);
    return wrapper;
  }

  function aggregateRouteFacts(routes) {
    const effects = new Set();
    routes.forEach((route) => (route.effects || []).forEach((effect) => effects.add(effect)));
    function total(field) {
      const values = routes.map((route) => route.estimated && route.estimated[field]);
      return values.every((value) => typeof value === "number" && Number.isFinite(value))
        ? values.reduce((sum, value) => sum + value, 0)
        : null;
    }
    const effectText = effects.size ? Array.from(effects).sort().map((effect) => `${effectLabels[effect] || effect}（${effect}${needsConsent(effect) ? "，需授权" : ""}）`).join("、") : "无";
    const gpu = routes.some((route) => route.estimated && route.estimated.gpu);
    return `影响：${effectText} · 资源上限合计：下载 ${formatBytes(total("downloadBytes"))}，磁盘 ${formatBytes(total("diskBytes"))}，运行 ${formatNumber(total("runtimeMinutes"), " 分钟")}，GPU ${gpu ? "需要" : "不需要"}，费用 ${total("costUsd") === null ? "待确认" : `$${total("costUsd")}`}`;
  }

  function initialize() {
    document.getElementById("paper-title").textContent = report.paper.title;
    document.getElementById("report-summary").textContent = report.summary.oneLine;
    const meta = document.getElementById("report-meta");
    [["报告", report.reportId], ["图片", figures.length]].forEach(([label, value]) => {
      const wrapper = node("div");
      append(wrapper, node("dt", null, label), node("dd", null, value));
      meta.appendChild(wrapper);
    });
    document.getElementById("output-root").value = `outputs/${report.reportId}`;
    figures.forEach((figure) => {
      const route = defaultRoute(figure);
      if (route) currentRoutes.set(figure.figureId, route.routeId);
    });
    renderTabs();
    renderDetail();
    renderAppendix();
    updateApproval();
    document.getElementById("output-root").addEventListener("input", updateApproval);
    document.getElementById("export-approval").addEventListener("click", exportApproval);
  }

  function renderTabs() {
    const tabs = document.getElementById("figure-tabs");
    tabs.textContent = "";
    tabs.style.setProperty("--figure-count", String(figures.length));
    figures.forEach((figure) => {
      const button = node("button", "figure-tab");
      button.type = "button";
      button.setAttribute("aria-current", figure.figureId === currentFigureId ? "true" : "false");
      button.addEventListener("click", () => {
        currentFigureId = figure.figureId;
        renderTabs();
        renderDetail();
        document.getElementById("figure-detail").scrollIntoView({ behavior: "smooth", block: "start" });
      });
      const imagePath = safeImagePath(figure.image);
      if (imagePath) {
        const image = node("img");
        image.src = imagePath;
        image.alt = "";
        button.appendChild(image);
      } else {
        button.appendChild(node("div", "figure-placeholder", figure.label));
      }
      const copy = node("span", "figure-tab-copy");
      append(copy,
        node("span", "figure-tab-label", `${figure.label} · ${levelLabels[figure.reproduction.level] || figure.reproduction.level}`),
        node("span", "figure-tab-title", figure.caption || figure.summary),
        node("span", "figure-tab-verdict", figure.reproduction.verdict)
      );
      button.appendChild(copy);
      tabs.appendChild(button);
    });
  }

  function renderDetail() {
    const figure = figures.find((item) => item.figureId === currentFigureId);
    if (!figure) return;
    const root = document.getElementById("figure-detail");
    root.textContent = "";

    const header = node("header", "detail-head");
    append(header,
      node("div", "detail-kicker", `${figure.label} · ${figure.section || "论文图"}`),
      node("h2", null, figure.reproduction.verdict),
      node("p", "caption", figure.caption)
    );
    root.appendChild(header);

    const grid = node("div", "detail-grid");
    const paper = node("figure", "figure-paper");
    const imagePath = safeImagePath(figure.image);
    if (imagePath) {
      const image = node("img");
      image.src = imagePath;
      image.alt = `${figure.label}: ${figure.caption || figure.summary}`;
      paper.appendChild(image);
    } else {
      paper.appendChild(node("p", "figure-placeholder", "本报告未捆绑原图。"));
    }

    const assessment = node("div", "assessment");
    const badge = node("span", "badge", levelLabels[figure.reproduction.level] || figure.reproduction.level);
    badge.dataset.level = figure.reproduction.level;
    append(assessment, badge, node("h3", null, figure.summary), node("p", "assessment-summary", figure.reproduction.assessment));

    const requirements = node("div", "requirements");
    (figure.requirements || []).forEach((requirement) => {
      const row = node("div", "requirement");
      const status = stateLabels[requirement.state] || ["?", requirement.state];
      const state = node("span", "requirement-state", `${status[0]} ${status[1]}`);
      state.dataset.state = requirement.state;
      append(row, state, node("span", "requirement-label", requirement.label), node("span", "requirement-detail", requirement.detail));
      requirements.appendChild(row);
    });
    assessment.appendChild(requirements);
    grid.appendChild(paper);
    grid.appendChild(assessment);
    root.appendChild(grid);

    const routesSection = node("section", "routes");
    routesSection.appendChild(node("h3", "section-title", "候选复现路线"));
    const routeList = node("div", "route-list");
    (figure.routes || []).forEach((route) => {
      const label = node("label", "route");
      const radio = node("input");
      radio.type = "radio";
      radio.name = `route-${figure.figureId}`;
      radio.value = route.routeId;
      radio.disabled = route.status === "blocked";
      radio.checked = currentRoutes.get(figure.figureId) === route.routeId;
      radio.addEventListener("change", () => {
        currentRoutes.set(figure.figureId, route.routeId);
        renderDetail();
        updateApproval();
      });
      const copy = node("span", "route-copy");
      append(copy, node("strong", null, route.label), node("small", null, `${route.engine || "未指定引擎"} · ${(route.plan || []).join(" → ")}`), renderRouteFacts(route));
      append(label, radio, copy, node("span", "route-status", routeLabels[route.status] || route.status));
      routeList.appendChild(label);
    });
    routesSection.appendChild(routeList);

    const chosen = routeFor(figure, currentRoutes.get(figure.figureId));
    if (chosen && chosen.parameters && chosen.parameters.length) {
      routesSection.appendChild(renderParameters(figure, chosen));
    }

    const includeLabel = node("label", "include-row");
    const includeInput = node("input");
    includeInput.type = "checkbox";
    includeInput.checked = included.has(figure.figureId);
    includeInput.disabled = !chosen || chosen.status === "blocked";
    includeInput.addEventListener("change", () => {
      if (includeInput.checked) included.add(figure.figureId);
      else included.delete(figure.figureId);
      updateApproval();
    });
    append(includeLabel, includeInput, node("span", null, includeInput.disabled ? "当前没有可批准路线" : "将这张图纳入批准单"));
    routesSection.appendChild(includeLabel);

    const sourceBox = node("div", "sources");
    (figure.sourceRefs || []).slice(0, 3).forEach((sourceId) => {
      const source = sourcesById.get(sourceId);
      if (!source) return;
      const externalHref = safeExternalHref(source.url);
      const localHref = safeAssetPath(source.artifact && source.artifact.relativePath);
      const href = externalHref || localHref;
      if (!href) return;
      const link = node("a", "source-link", source.title);
      link.href = href;
      if (externalHref) {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      sourceBox.appendChild(link);
    });
    routesSection.appendChild(sourceBox);
    root.appendChild(routesSection);
  }

  function renderParameters(figure, route) {
    const wrapper = node("div", "parameter-list");
    wrapper.appendChild(node("h3", "section-title", "路线参数"));
    route.parameters.forEach((spec) => {
      const key = `${figure.figureId}|${route.routeId}|${spec.parameterId}`;
      if (!parameterValues.has(key) && Object.prototype.hasOwnProperty.call(spec, "default")) {
        const checked = safeParameterValue(spec, spec.default);
        if (checked.valid) parameterValues.set(key, checked.value);
      }
      const label = node("label", "output-field");
      label.appendChild(node("span", null, `${spec.label}${spec.required ? " *" : ""} · ${spec.origin || "unknown"}`));
      let input;
      if (spec.type === "enum") {
        input = node("select");
        (spec.enum || []).forEach((value) => {
          const option = node("option", null, value);
          option.value = value;
          option.selected = parameterValues.get(key) === value;
          input.appendChild(option);
        });
      } else {
        input = node("input");
        input.type = spec.type === "boolean" ? "checkbox" : (spec.type === "integer" || spec.type === "number" ? "number" : "text");
        if (input.type === "checkbox") input.checked = Boolean(parameterValues.get(key));
        else if (parameterValues.has(key)) input.value = String(parameterValues.get(key));
        if (spec.min !== undefined) input.min = String(spec.min);
        if (spec.max !== undefined) input.max = String(spec.max);
        if (spec.type === "integer") input.step = "1";
      }
      input.addEventListener("input", () => {
        let value;
        if (spec.type === "boolean") value = input.checked;
        else if (spec.type === "integer") value = input.value === "" ? null : Number.parseInt(input.value, 10);
        else if (spec.type === "number") value = input.value === "" ? null : Number(input.value);
        else value = input.value;
        parameterValues.set(key, value);
        updateApproval();
      });
      label.appendChild(input);
      wrapper.appendChild(label);
    });
    return wrapper;
  }

  function collectParameters(figure, route) {
    const values = {};
    let valid = true;
    (route.parameters || []).forEach((spec) => {
      const key = `${figure.figureId}|${route.routeId}|${spec.parameterId}`;
      const value = parameterValues.has(key) ? parameterValues.get(key) : spec.default;
      const checked = safeParameterValue(spec, value);
      if (!checked.valid) valid = false;
      if (checked.valid && checked.value !== undefined && checked.value !== null && checked.value !== "") values[spec.parameterId] = checked.value;
    });
    return { values, valid };
  }

  function updateApproval() {
    const selected = figures.filter((figure) => included.has(figure.figureId));
    const effects = new Set();
    let parametersValid = true;
    selected.forEach((figure) => {
      const route = routeFor(figure, currentRoutes.get(figure.figureId));
      if (!route || route.status === "blocked") parametersValid = false;
      else {
        (route.effects || []).forEach((effect) => effects.add(effect));
        if (!collectParameters(figure, route).valid) parametersValid = false;
      }
    });
    const consentEffects = new Set(Array.from(effects).filter(needsConsent));
    const consentList = document.getElementById("consent-list");
    consentList.textContent = "";
    consentEffects.forEach((effect) => {
      const label = node("label", "consent-item");
      const input = node("input");
      input.type = "checkbox";
      input.checked = consents.has(effect);
      input.addEventListener("change", () => {
        if (input.checked) consents.add(effect);
        else consents.delete(effect);
        updateApproval();
      });
      append(label, input, node("span", null, `单独授权：${effectLabels[effect] || effect}（${effect}）`));
      consentList.appendChild(label);
    });

    const minimum = report.approvalPolicy.minFigures;
    const maximum = report.approvalPolicy.maxFigures;
    const outputValid = safeRelative(document.getElementById("output-root").value.trim());
    const consentsValid = Array.from(consentEffects).every((effect) => consents.has(effect));
    const overwriteRouteSelected = effects.has("overwrite");
    const button = document.getElementById("export-approval");
    button.disabled = selected.length < minimum || selected.length > maximum || !outputValid || !consentsValid || !parametersValid || overwriteRouteSelected;
    button.textContent = selected.length ? `导出 ${selected.length} 张图的批准单` : "导出批准单";
    const selectedRoutes = selected.map((figure) => routeFor(figure, currentRoutes.get(figure.figureId))).filter(Boolean);
    document.getElementById("approval-summary").textContent = selected.length
      ? `${selected.map((figure) => figure.label).join("、")} · ${aggregateRouteFacts(selectedRoutes)} · ${overwriteRouteSelected ? "所选路线要求覆盖文件；本静态页面只导出新建文件批准单，请改选无覆盖路线或重新生成逐文件审批报告。" : "仅创建新文件；超过上限须重新批准。"}`
      : "请在图片详情中选择路线并勾选“纳入批准单”。";
  }

  function exportApproval() {
    const selectedFigures = [];
    const effects = new Set();
    figures.filter((figure) => included.has(figure.figureId)).forEach((figure) => {
      const route = routeFor(figure, currentRoutes.get(figure.figureId));
      if (!route || route.status === "blocked") return;
      (route.effects || []).forEach((effect) => effects.add(effect));
      selectedFigures.push({
        figureId: figure.figureId,
        sourceImageSha256: (figure.image && figure.image.sha256) || null,
        routeId: route.routeId,
        parameters: collectParameters(figure, route).values,
        deliverables: (route.deliverables || []).map((item) => item.kind)
      });
    });
    if (effects.has("overwrite")) {
      window.alert("所选路线要求覆盖文件；本静态页面只支持导出新建文件批准单。");
      return;
    }
    const created = new Date();
    const ttl = report.approvalPolicy.ttlMinutes;
    const expires = new Date(created.getTime() + ttl * 60 * 1000);
    const approvalUuid = randomUuid();
    const idempotencyKey = randomUuid();
    if (!approvalUuid || !idempotencyKey) {
      window.alert("当前浏览器无法生成安全的批准单标识，请使用较新的浏览器打开报告。");
      return;
    }
    const approvalId = `apr-${approvalUuid}`;
    const approval = {
      schemaVersion: "reprofig.approval/v1",
      approvalId,
      reportId: report.reportId,
      reportSha256: report.integrity.reportSha256,
      decision: "approve",
      createdAt: created.toISOString(),
      expiresAt: expires.toISOString(),
      selectedFigures,
      outputPolicy: {
        relativeRoot: document.getElementById("output-root").value.trim(),
        mode: "create-only",
        overwrite: "never",
        explicitFiles: []
      },
      authorizedEffects: Array.from(effects).sort(),
      acknowledgements: Array.from(consents).filter((effect) => effects.has(effect)).map((effect) => ({ effect, acceptedAt: created.toISOString() })),
      idempotencyKey
    };
    if (containsSensitiveData(approval)) {
      window.alert("批准单包含禁止的敏感字段，请修改路线参数后重试。");
      return;
    }
    const blob = new Blob([`${JSON.stringify(approval, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${approvalId}.reprofig-approval.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  function renderAppendix() {
    const root = document.getElementById("appendix-content");
    root.textContent = "";
    const envSection = node("section");
    envSection.appendChild(node("h3", null, "本机环境"));
    const envList = node("ul", "appendix-list");
    (report.environment || []).forEach((environment) => {
      const item = node("li", "appendix-item");
      append(item, node("strong", null, `${environment.label} · ${environment.status}`), node("small", null, `${environment.version || "版本未知"} · ${environment.detail || "无补充说明"}`));
      envList.appendChild(item);
    });
    envSection.appendChild(envList);
    root.appendChild(envSection);

    const sourceSection = node("section");
    sourceSection.appendChild(node("h3", null, "来源与许可"));
    const sourceList = node("ul", "appendix-list");
    (report.sources || []).forEach((source) => {
      const item = node("li", "appendix-item");
      const access = source.access && source.access.state ? source.access.state : "unknown";
      const license = source.license && (source.license.spdxId || source.license.name || source.license.state);
      append(item, node("strong", null, source.title), node("small", null, `${source.publisher || "来源未知"} · ${access} · ${license || "许可未知"}`));
      sourceList.appendChild(item);
    });
    sourceSection.appendChild(sourceList);
    root.appendChild(sourceSection);
  }

  initialize();
}());
