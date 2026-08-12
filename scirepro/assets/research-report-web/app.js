(function () {
  "use strict";

  const report = window.__SCIREPRO_REPORT__ || window.__REPROFIG_REPORT__;
  if (!report || report.schemaVersion !== "reprofig.report/v3") {
    document.body.textContent = "SciRepro 报告数据无效。";
    return;
  }

  const levelLabels = {
    "direct-recompute": "原案例可复算",
    "mechanism-reproduction": "机制可复现",
    "alternative-validation": "可替代验证",
    "editable-reconstruction": "可编辑重构",
    "image-derived-reconstruction": "图像衍生重构",
    "original-case-blocked": "原案例受阻"
  };
  const acquisitionModeLabels = {
    "paper-with-images": "论文与目标图像",
    "paper-with-figure-references": "按论文图号提取",
    "images-only": "仅目标图像"
  };
  const workflowModeLabels = {
    "scientific-reproduction": "科学复现",
    "image-derived-reconstruction": "图像衍生重构"
  };
  const audienceLabels = {
    local: "本地研判版",
    public: "公开分享版"
  };
  const qaStatusLabels = {
    verified: "提取已核验",
    "needs-review": "待人工核验",
    passed: "核验通过",
    failed: "核验未通过",
    unknown: "核验状态未知"
  };
  const bundleStateLabels = {
    "embedded-local": "本地报告已嵌入",
    "embedded-public": "公开报告已嵌入",
    "omitted-rights": "公开报告未分发图像"
  };
  const stateLabels = {
    verified: ["✓", "已核验"],
    derivable: ["↗", "可推导"],
    assumable: ["◇", "可设定"],
    missing: ["×", "缺失"],
    "not-required": ["—", "不适用"]
  };
  const routeLabels = { ready: "可执行", conditional: "有条件", blocked: "受阻" };
  const confidenceLabels = { high: "高置信度", medium: "中等置信度", low: "低置信度" };
  const environmentStatusLabels = { verified: "路线级已核验", available: "已检测，待实机核验", unknown: "状态未知", missing: "未检测到" };
  const provisioningLabels = { "existing-only": "需现有授权环境", "isolated-open-source": "可隔离配置" };
  const originLabels = { paper: "论文明确", code: "代码明确", derived: "分析推导", assumption: "透明假设", user: "用户指定" };
  const validationKindLabels = {
    "qualitative-pattern": "定性现象",
    quantitative: "定量指标",
    comparative: "比较关系",
    structural: "结构特征",
    "visual-fidelity": "视觉还原"
  };
  const requirementCategoryLabels = {
    environment: "运行环境",
    input: "输入数据",
    method: "方法实现",
    protocol: "实验流程",
    validation: "验证标准"
  };
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
  const environmentsById = new Map((report.environment || []).map((environment) => [environment.environmentId, environment]));
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

  function sectionHeading(step, title, description) {
    const header = node("header", "section-head");
    append(header, node("span", "step-marker", step), node("h3", null, title));
    if (description) header.appendChild(node("p", null, description));
    return header;
  }

  function textList(items, className, emptyText) {
    const list = node("ul", className || "plain-list");
    if (!items || !items.length) {
      list.appendChild(node("li", "empty-item", emptyText || "无"));
      return list;
    }
    items.forEach((item) => list.appendChild(node("li", null, item)));
    return list;
  }

  function sourceAnchor(source, className) {
    if (!source) return null;
    const externalHref = safeExternalHref(source.url);
    const localHref = safeAssetPath(source.artifact && source.artifact.relativePath);
    const href = externalHref || localHref;
    if (!href) return node("span", className || "evidence-ref", source.title);
    const link = node("a", className || "evidence-ref", source.title);
    link.href = href;
    if (externalHref) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    return link;
  }

  function renderEvidenceRefs(refs) {
    const wrapper = node("span", "evidence-refs");
    (refs || []).forEach((sourceId) => {
      const source = sourcesById.get(sourceId);
      if (source) wrapper.appendChild(sourceAnchor(source, "evidence-ref"));
    });
    return wrapper.childNodes.length ? wrapper : null;
  }

  function labeledBlock(label, value, className) {
    const wrapper = node("div", className || "labeled-block");
    append(wrapper, node("span", "field-label", label), node("p", null, value));
    return wrapper;
  }

  function renderPills(items, className, emptyText) {
    const wrapper = node("div", className || "pill-list");
    if (!items || !items.length) {
      wrapper.appendChild(node("span", "muted-pill", emptyText || "无"));
      return wrapper;
    }
    items.forEach((item) => wrapper.appendChild(node("span", "text-pill", item)));
    return wrapper;
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

  function workflowMode(figure) {
    return (figure && figure.target && figure.target.workflowMode) || (figure && figure.workflowMode) || null;
  }

  function isImageDerived(figure) {
    return workflowMode(figure) === "image-derived-reconstruction";
  }

  function targetCanBeApproved(figure) {
    const bundleState = figure && figure.image && figure.image.bundleState;
    return Boolean(
      report.audience === "local" &&
      figure &&
      figure.target &&
      typeof figure.target.targetSha256 === "string" &&
      figure.target.targetSha256 &&
      figure.image &&
      bundleState === "embedded-local" &&
      safeImagePath(figure.image)
    );
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

  function requirementCanRun(requirement) {
    if (!requirement) return false;
    if (["verified", "not-required"].includes(requirement.state)) return true;
    const expected = requirement.state === "derivable" ? "frozen" : requirement.state === "assumable" ? "accepted" : null;
    return expected && requirement.resolution && requirement.resolution.status === expected &&
      typeof requirement.resolution.basis === "string" && requirement.resolution.basis.trim().length > 0;
  }

  function routeHasBoundedEstimate(route) {
    const estimate = route && route.estimated;
    return estimate && ["downloadBytes", "diskBytes", "runtimeMinutes", "costUsd"]
      .every((field) => Number.isFinite(estimate[field]) && estimate[field] >= 0);
  }

  function routeIsBlocked(figure, route) {
    if (!route || route.status === "blocked" || (route.blockers || []).length) return true;
    if (!routeHasBoundedEstimate(route)) return true;
    const blockingRequirements = new Set(
      (figure.requirements || []).filter((requirement) => requirement.blocking).map((requirement) => requirement.requirementId)
    );
    if ((route.requirementIds || []).some((requirementId) => blockingRequirements.has(requirementId))) return true;
    const requirementsById = new Map((figure.requirements || []).map((requirement) => [requirement.requirementId, requirement]));
    const routeRequirements = (route.requirementIds || [])
      .map((requirementId) => requirementsById.get(requirementId))
      .filter(Boolean);
    if (routeRequirements.some((requirement) => !requirementCanRun(requirement))) return true;
    const routeEnvironments = (route.environmentIds || [])
      .map((environmentId) => environmentsById.get(environmentId))
      .filter(Boolean);
    const environmentStates = routeEnvironments.map((environment) => environment.status);
    if (route.status === "ready" && environmentStates.some((state) => state !== "verified")) return true;
    if (route.status === "conditional") {
      const unresolved = routeEnvironments.filter((environment) => ["unknown", "missing"].includes(environment.status));
      if (unresolved.some((environment) => environment.provisioning === "existing-only")) return true;
      if (unresolved.length && !(route.effects || []).includes("install")) return true;
    }
    return false;
  }

  function defaultRoute(figure) {
    const recommended = routeFor(figure, figure.reproduction && figure.reproduction.recommendedRouteId);
    if (recommended && !routeIsBlocked(figure, recommended)) return recommended;
    return (figure.routes || []).find((route) => !routeIsBlocked(figure, route)) || (figure.routes || [])[0] || null;
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

  function renderRouteExecution(route, open) {
    const details = node("details", "route-execution");
    details.open = Boolean(open);
    details.appendChild(node("summary", null, "执行条件、影响与资源"));
    const body = node("div", "route-execution-body");
    body.appendChild(labeledBlock("运行引擎", route.engine || "未指定", "compact-field"));
    const environments = (route.environmentIds || []).map((environmentId) => environmentsById.get(environmentId)).filter(Boolean);
    const environmentText = environments.length
      ? environments.map((environment) => {
          const status = environmentStatusLabels[environment.status] || environment.status;
          const provisioning = provisioningLabels[environment.provisioning] || environment.provisioning;
          return `${environment.label}（${status}；${provisioning}）`;
        }).join("、")
      : "无单独环境依赖";
    body.appendChild(labeledBlock("环境", environmentText, "compact-field"));
    body.appendChild(renderRouteFacts(route));
    if (route.plan && route.plan.length) {
      const plan = node("div", "execution-plan");
      plan.appendChild(node("span", "field-label", "执行步骤"));
      plan.appendChild(textList(route.plan, "numbered-list"));
      body.appendChild(plan);
    }
    details.appendChild(body);
    return details;
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
    const firstFigure = figures[0];
    const imageOnly = firstFigure && isImageDerived(firstFigure) && !report.paper;
    const audienceLabel = audienceLabels[report.audience] || "受众未声明";
    document.getElementById("paper-title").textContent = report.paper ? report.paper.title : "目标图像重构研判";
    document.getElementById("report-summary").textContent = report.summary.objective;
    const topbarTagline = document.querySelector(".topbar p");
    if (topbarTagline) {
      topbarTagline.textContent = "";
      const audienceBadge = node("span", "audience-badge", audienceLabel);
      audienceBadge.dataset.audience = report.audience || "unknown";
      append(topbarTagline, node("span", "topbar-label", "读图 · 研判 · 验证"), audienceBadge);
    }
    const meta = document.getElementById("report-meta");
    [["报告", report.reportId], ["目标图", figures.length], ["报告受众", audienceLabel], [imageOnly ? "工作模式" : "总体研判", imageOnly ? "图像衍生重构" : report.summary.oneLine]].forEach(([label, value]) => {
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
    figures.forEach((figure, index) => {
      const button = node("button", "figure-tab");
      button.type = "button";
      button.dataset.figureId = figure.figureId;
      button.dataset.omitted = figure.image && figure.image.bundleState === "omitted-rights" ? "true" : "false";
      button.setAttribute("aria-current", figure.figureId === currentFigureId ? "true" : "false");
      button.setAttribute("aria-label", `${index + 1} / ${figures.length} · ${figure.label} · ${figure.understanding.visualSummary}`);
      button.addEventListener("click", () => {
        currentFigureId = figure.figureId;
        Array.from(tabs.children).forEach((tab) => {
          tab.setAttribute("aria-current", tab.dataset.figureId === currentFigureId ? "true" : "false");
        });
        renderDetail();
        document.getElementById("figure-detail").scrollIntoView({ behavior: "smooth", block: "start" });
      });
      button.appendChild(node("span", "figure-tab-index", String(index + 1).padStart(2, "0")));
      const copy = node("span", "figure-tab-copy");
      append(copy,
        node("span", "figure-tab-label", `${figure.label} · ${levelLabels[figure.reproduction.level] || figure.reproduction.level}`),
        node("span", "figure-tab-title", figure.understanding.visualSummary),
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
    const understanding = figure.understanding;
    const generation = figure.generationLogic;
    const observationsById = new Map((understanding.observations || []).map((observation) => [observation.observationId, observation]));
    const validationTargetsById = new Map((figure.validationTargets || []).map((target) => [target.targetId, target]));

    const header = node("header", "detail-head");
    append(header,
      node("div", "detail-kicker", `${figure.label} · ${figure.section || (isImageDerived(figure) ? "目标图像" : "论文图")}`),
      node("h2", null, understanding.visualSummary),
      node("p", "caption", figure.caption)
    );
    const headerBadges = node("div", "header-badges");
    const levelBadge = node("span", "badge", levelLabels[figure.reproduction.level] || figure.reproduction.level);
    levelBadge.dataset.level = figure.reproduction.level;
    append(headerBadges,
      levelBadge,
      node("span", "confidence-badge", confidenceLabels[figure.reproduction.confidence] || figure.reproduction.confidence),
      node("span", "workflow-badge", workflowModeLabels[workflowMode(figure)] || workflowMode(figure) || "工作模式未声明")
    );
    header.appendChild(headerBadges);
    root.appendChild(header);

    const target = figure.target || {};
    const materialization = target.materialization || {};
    const imagePath = safeImagePath(figure.image);
    const targetSection = node("section", "content-section target-section");
    targetSection.appendChild(sectionHeading("00", "复现对象", "先确认本次分析绑定的是哪一张原图，再阅读解释与候选路线。"));
    const targetLayout = node("div", "target-layout");
    const targetVisual = node("figure", "target-visual");
    if (imagePath) {
      const targetImage = node("img");
      targetImage.src = imagePath;
      targetImage.alt = `${figure.label}: ${figure.caption || understanding.visualSummary}`;
      targetImage.decoding = "async";
      targetVisual.appendChild(targetImage);
      targetVisual.appendChild(node("figcaption", null, figure.caption || understanding.visualSummary));
    } else if (figure.image && figure.image.bundleState === "omitted-rights") {
      const notice = node("div", "target-rights-notice");
      append(notice,
        node("span", "target-rights-icon", "○"),
        node("strong", null, "公开版未分发目标图像"),
        node("p", null, "该图只用于本地研判，未获得再分发许可。请回到本地报告核对原图；当前目标不能导出执行批准单。")
      );
      targetVisual.appendChild(notice);
    } else {
      targetVisual.appendChild(node("p", "figure-placeholder", "目标图像未被嵌入；请检查第 0 阶段图像物化结果。"));
    }
    const targetFacts = node("div", "target-facts");
    const workflow = workflowModeLabels[target.workflowMode] || target.workflowMode || "未声明";
    const acquisition = acquisitionModeLabels[target.acquisitionMode] || target.acquisitionMode || "未声明";
    const materializedPage = materialization.page === undefined ? target.paperPage : materialization.page;
    const renderDpi = materialization.renderDpi || target.dpi;
    const captionIncluded = materialization.captionIncluded === undefined ? target.captionIncluded : materialization.captionIncluded;
    const qaStatus = materialization.qaStatus || target.qaStatus;
    const sourceFileName = materialization.sourceFileName || target.sourceFileName;
    const pageText = materializedPage === undefined || materializedPage === null ? "—" : `PDF 第 ${materializedPage} 页`;
    const dpiText = renderDpi ? `${renderDpi} DPI` : "原始图像";
    const captionText = captionIncluded === true ? "包含原始图注" : captionIncluded === false ? "未包含原始图注" : "图注状态未知";
    const factGrid = node("dl", "target-fact-grid");
    [
      ["获取方式", acquisition],
      ["工作模式", workflow],
      ["请求对象", target.requestedRef || target.requestedAs || target.figureReference || figure.label],
      ["来源位置", pageText],
      ["物化方式", materialization.method || (target.acquisitionMode === "paper-with-figure-references" ? "PDF 高分辨率渲染与裁切" : "目标图像规范化")],
      ["图像规格", `${dpiText} · ${captionText}`],
      ["质量核验", qaStatusLabels[qaStatus] || qaStatus || "未声明"],
      ["报告分发", bundleStateLabels[figure.image && figure.image.bundleState] || (figure.image && figure.image.bundleState) || "未声明"],
      ["展示图像", figure.image && figure.image.bundleState === "omitted-rights"
        ? "未嵌入（版权限制）"
        : figure.image && figure.image.displayProxy
          ? "轻量视觉代理（目标哈希仍绑定原图）"
          : "完整目标图"]
    ].forEach(([label, value]) => {
      const fact = node("div", "target-fact");
      append(fact, node("dt", null, label), node("dd", null, value));
      factGrid.appendChild(fact);
    });
    targetFacts.appendChild(factGrid);
    const hash = node("div", "target-hash");
    append(hash, node("span", "field-label", "目标原图 SHA-256"), node("code", null, target.targetSha256 || "未记录"));
    hash.title = target.targetSha256 || "";
    targetFacts.appendChild(hash);
    if (report.audience !== "public" && sourceFileName) targetFacts.appendChild(labeledBlock("源文件", sourceFileName, "target-source"));
    append(targetLayout, targetVisual, targetFacts);
    targetSection.appendChild(targetLayout);
    root.appendChild(targetSection);

    const readingSection = node("section", "content-section reading-section");
    readingSection.appendChild(sectionHeading("01", "读图", isImageDerived(figure) ? "先记录图上可直接观察到的结构与视觉编码，不把图像外观反推为论文事实。" : "先区分图上可直接观察到的现象，再进入论文解释。"));
    const observationPanel = node("div", "observation-panel observation-panel-wide");
    observationPanel.appendChild(node("h4", null, "可观察事实"));
    (understanding.observations || []).forEach((observation) => {
      const item = node("article", "observation");
      const meta = node("div", "observation-meta");
      append(meta,
        node("span", "location-chip", observation.location),
        node("span", "confidence-text", confidenceLabels[observation.confidence] || observation.confidence)
      );
      append(item, meta, node("p", null, observation.statement), renderEvidenceRefs(observation.evidenceRefs));
      observationPanel.appendChild(item);
    });
    readingSection.appendChild(observationPanel);
    root.appendChild(readingSection);

    const evidenceSection = node("section", "content-section evidence-section");
    evidenceSection.appendChild(sectionHeading("02", isImageDerived(figure) ? "图像边界" : "证据作用", isImageDerived(figure) ? "仅凭目标图像可以重建视觉结构，但不能据此声称恢复了原数据、原方法或论文结论。" : "把论文主张、作者解释和图本身的证据边界分开呈现。"));
    const evidenceGrid = node("div", "evidence-grid");
    if (isImageDerived(figure)) {
      append(evidenceGrid,
        labeledBlock("从图像能够确认", understanding.visualSummary, "evidence-card claim-card"),
        labeledBlock("可重建范围", understanding.evidenceRole || "版式、几何、文本与可见曲线关系。", "evidence-card role-card"),
        labeledBlock("不能由图像确认", understanding.authorInterpretation || "原始数据、生成算法、参数与科学主张。", "evidence-card interpretation-card")
      );
    } else {
      append(evidenceGrid,
        labeledBlock("论文用这张图支持什么", understanding.paperClaim, "evidence-card claim-card"),
        labeledBlock("它在论证中的作用", understanding.evidenceRole, "evidence-card role-card"),
        labeledBlock("作者如何解释", understanding.authorInterpretation, "evidence-card interpretation-card")
      );
    }
    const limitations = node("div", "evidence-card limitations-card");
    limitations.appendChild(node("span", "field-label", "证据边界"));
    limitations.appendChild(textList(understanding.limitations, "plain-list", "未声明额外限制"));
    evidenceGrid.appendChild(limitations);
    evidenceSection.appendChild(evidenceGrid);
    root.appendChild(evidenceSection);

    const generationSection = node("section", "content-section generation-section");
    generationSection.appendChild(sectionHeading("03", "生成链", "沿输入、方法与绘图映射还原这张图是怎样产生的。"));
    const generationGrid = node("div", "generation-grid");
    const inputColumn = node("div", "generation-column");
    inputColumn.appendChild(node("h4", null, "输入"));
    (generation.inputs || []).forEach((generationInput) => {
      const card = node("article", "generation-card");
      append(card,
        node("span", "origin-chip", originLabels[generationInput.origin] || generationInput.origin),
        node("strong", null, generationInput.label),
        node("p", null, generationInput.description),
        renderEvidenceRefs(generationInput.evidenceRefs)
      );
      inputColumn.appendChild(card);
    });
    const stepColumn = node("div", "generation-column");
    stepColumn.appendChild(node("h4", null, "处理与分析步骤"));
    const pipeline = node("ol", "pipeline");
    (generation.steps || []).forEach((step) => {
      const item = node("li", "pipeline-step");
      const copy = node("div");
      append(copy,
        node("span", "origin-chip", originLabels[step.origin] || step.origin),
        node("strong", null, step.label),
        node("p", null, step.description),
        renderEvidenceRefs(step.evidenceRefs)
      );
      item.appendChild(copy);
      pipeline.appendChild(item);
    });
    stepColumn.appendChild(pipeline);
    append(generationGrid, inputColumn, stepColumn);
    generationSection.appendChild(generationGrid);
    const plotCard = node("div", "plot-mapping");
    append(plotCard,
      node("span", "field-label", "绘图映射"),
      node("p", null, generation.plotMapping.description),
      renderPills(generation.plotMapping.encodings, "encoding-list", "未声明单独视觉编码"),
      renderEvidenceRefs(generation.plotMapping.evidenceRefs)
    );
    generationSection.appendChild(plotCard);
    const unknowns = node("div", "unknowns");
    unknowns.appendChild(node("span", "field-label", "尚不确定"));
    unknowns.appendChild(textList(generation.unknowns, "plain-list", "当前没有未披露的生成链缺口"));
    generationSection.appendChild(unknowns);
    root.appendChild(generationSection);

    const validationSection = node("section", "content-section validation-section");
    validationSection.appendChild(sectionHeading("04", "验证目标", "先定义什么结果算复现成功，再讨论路线是否可行。"));
    const validationGrid = node("div", "validation-grid");
    (figure.validationTargets || []).forEach((target) => {
      const card = node("article", "validation-card");
      append(card,
        node("span", "validation-kind", validationKindLabels[target.kind] || target.kind),
        node("span", "origin-chip", originLabels[target.origin] || target.origin),
        node("h4", null, target.label),
        labeledBlock("观察量", target.observable, "validation-field"),
        labeledBlock("成功判据", target.criterion, "validation-field criterion-field"),
        labeledBlock("能够支持到什么程度", target.supportsClaim, "validation-field"),
        renderEvidenceRefs(target.evidenceRefs)
      );
      validationGrid.appendChild(card);
    });
    validationSection.appendChild(validationGrid);
    root.appendChild(validationSection);

    const assessmentSection = node("section", "content-section assessment-section");
    assessmentSection.appendChild(sectionHeading("05", "复现研判", "在科学目标清楚之后，说明可复现层级、置信度和依据。"));
    const assessment = node("div", "assessment-box");
    const assessmentBadge = node("span", "badge", levelLabels[figure.reproduction.level] || figure.reproduction.level);
    assessmentBadge.dataset.level = figure.reproduction.level;
    append(assessment,
      assessmentBadge,
      node("span", "confidence-badge", confidenceLabels[figure.reproduction.confidence] || figure.reproduction.confidence),
      node("h4", null, figure.reproduction.verdict),
      node("p", null, figure.reproduction.assessment)
    );
    assessmentSection.appendChild(assessment);
    root.appendChild(assessmentSection);

    const routesSection = node("section", "content-section routes");
    routesSection.appendChild(sectionHeading("06", "候选复现路线", "先比较每条路线承诺的科学范围，再展开执行代价。"));
    const routeList = node("div", "route-list");
    (figure.routes || []).forEach((route) => {
      const scope = route.scientificScope;
      const card = node("article", "route");
      const effectivelyBlocked = routeIsBlocked(figure, route);
      card.dataset.status = effectivelyBlocked ? "blocked" : route.status;
      const label = node("label", "route-choice");
      const radio = node("input");
      radio.type = "radio";
      radio.name = `route-${figure.figureId}`;
      radio.value = route.routeId;
      radio.disabled = effectivelyBlocked;
      radio.checked = currentRoutes.get(figure.figureId) === route.routeId;
      radio.addEventListener("change", () => {
        currentRoutes.set(figure.figureId, route.routeId);
        renderDetail();
        updateApproval();
      });
      const copy = node("span", "route-copy");
      append(copy, node("strong", null, route.label), node("small", null, scope.goal));
      const statusGroup = node("span", "route-status-group");
      if (route.recommended) statusGroup.appendChild(node("span", "recommended-chip", "推荐"));
      statusGroup.appendChild(node("span", "route-status", routeLabels[effectivelyBlocked ? "blocked" : route.status] || route.status));
      append(label, radio, copy, statusGroup);
      card.appendChild(label);

      if (route.blockers && route.blockers.length) {
        const blockers = node("div", "route-blockers");
        blockers.appendChild(node("strong", null, "阻断原因"));
        blockers.appendChild(textList(route.blockers, "plain-list"));
        card.appendChild(blockers);
      }

      const science = node("div", "route-science");
      science.appendChild(labeledBlock(isImageDerived(figure) ? "对重构目标的覆盖" : "对论文主张的覆盖", scope.claimCoverage, "route-claim"));
      const reproduced = (scope.reproducesObservationIds || []).map((observationId) => {
        const observation = observationsById.get(observationId);
        return observation ? observation.statement : observationId;
      });
      const targetLabels = (scope.validationTargetIds || []).map((targetId) => {
        const target = validationTargetsById.get(targetId);
        return target ? target.label : targetId;
      });
      const scopeGrid = node("div", "scope-grid");
      [
        ["将复现的现象", reproduced, "未声明"],
        ["不会复现", scope.doesNotReproduce, "无已知排除项"],
        ["替代与重建", scope.substitutions, "无替代"],
        ["透明假设", scope.assumptions, "无额外假设"],
        ["采用的验证目标", targetLabels, "未声明"]
      ].forEach(([title, items, emptyText]) => {
        const group = node("div", "scope-group");
        group.appendChild(node("span", "field-label", title));
        group.appendChild(renderPills(items, "scope-pills", emptyText));
        scopeGrid.appendChild(group);
      });
      science.appendChild(scopeGrid);
      science.appendChild(labeledBlock("推荐理由与权衡", scope.recommendationRationale, "route-rationale"));
      const deliverableLabels = (route.deliverables || []).map((item) => `${item.label}（${item.extension}）`);
      const deliverables = node("div", "route-deliverables");
      deliverables.appendChild(node("span", "field-label", "预期产物"));
      deliverables.appendChild(renderPills(deliverableLabels, "deliverable-list", "未声明产物"));
      science.appendChild(deliverables);
      card.appendChild(science);
      card.appendChild(renderRouteExecution(route, false));
      routeList.appendChild(card);
    });
    routesSection.appendChild(routeList);
    root.appendChild(routesSection);

    const chosen = routeFor(figure, currentRoutes.get(figure.figureId));
    const executionSection = node("section", "content-section execution-section");
    executionSection.appendChild(sectionHeading("07", "执行条件", "这些条件决定如何安全执行，不决定图件在论文中的科学意义。"));
    const requirements = node("div", "requirements");
    const requirementsById = new Map((figure.requirements || []).map((requirement) => [requirement.requirementId, requirement]));
    const chosenRequirements = chosen ? (chosen.requirementIds || []).map((requirementId) => requirementsById.get(requirementId)).filter(Boolean) : [];
    chosenRequirements.forEach((requirement) => {
      const row = node("div", "requirement");
      row.dataset.blocking = requirement.blocking ? "true" : "false";
      const status = stateLabels[requirement.state] || ["?", requirement.state];
      const state = node("span", "requirement-state", `${status[0]} ${status[1]}`);
      state.dataset.state = requirement.state;
      const labelCopy = node("span", "requirement-label");
      append(labelCopy,
        node("strong", null, requirement.label),
        node("small", null, requirementCategoryLabels[requirement.category] || requirement.category)
      );
      const detail = requirement.resolution
        ? `${requirement.detail} · ${requirement.resolution.status === "accepted" ? "已接受" : "已冻结"}：${requirement.resolution.basis}`
        : requirement.detail;
      append(row, state, labelCopy, node("span", "requirement-detail", detail));
      if (requirement.blocking) row.appendChild(node("span", "blocking-chip", "阻断"));
      requirements.appendChild(row);
    });
    executionSection.appendChild(requirements);
    if (chosen && !routeIsBlocked(figure, chosen) && chosen.parameters && chosen.parameters.length) executionSection.appendChild(renderParameters(figure, chosen));
    if (chosen) executionSection.appendChild(renderRouteExecution(chosen, true));

    const includeLabel = node("label", "include-row");
    const includeInput = node("input");
    includeInput.type = "checkbox";
    includeInput.checked = included.has(figure.figureId);
    const targetUnavailable = !targetCanBeApproved(figure);
    includeInput.disabled = targetUnavailable || !chosen || routeIsBlocked(figure, chosen);
    includeInput.addEventListener("change", () => {
      if (includeInput.checked) included.add(figure.figureId);
      else included.delete(figure.figureId);
      updateApproval();
    });
    const includeText = targetUnavailable
      ? "当前报告未携带可核验的目标原图，不能生成执行批准单"
      : (includeInput.disabled ? "当前没有可批准路线" : "选择这张图和当前路线，准备执行确认");
    append(includeLabel, includeInput, node("span", null, includeText));
    executionSection.appendChild(includeLabel);

    const sourceBox = node("div", "sources");
    sourceBox.appendChild(node("span", "field-label", "本图主要证据来源"));
    (figure.sourceRefs || []).slice(0, 3).forEach((sourceId) => {
      const source = sourcesById.get(sourceId);
      const link = sourceAnchor(source, "source-link");
      if (link) sourceBox.appendChild(link);
    });
    executionSection.appendChild(sourceBox);
    root.appendChild(executionSection);
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
        if (!Object.prototype.hasOwnProperty.call(spec, "default")) {
          const unset = node("option", null, spec.required ? "请选择" : "未设置");
          unset.value = "";
          input.appendChild(unset);
        }
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
    const selected = figures.filter((figure) => included.has(figure.figureId) && targetCanBeApproved(figure));
    document.getElementById("approval-panel").hidden = selected.length === 0;
    const effects = new Set();
    let parametersValid = true;
    selected.forEach((figure) => {
      const route = routeFor(figure, currentRoutes.get(figure.figureId));
      if (!route || routeIsBlocked(figure, route)) parametersValid = false;
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
    button.textContent = selected.length ? `导出 ${selected.length} 张图的执行批准单` : "导出执行批准单";
    const selectedRoutes = selected.map((figure) => routeFor(figure, currentRoutes.get(figure.figureId))).filter(Boolean);
    const approvalSummary = document.getElementById("approval-summary");
    approvalSummary.textContent = "";
    selected.forEach((figure) => {
      const route = routeFor(figure, currentRoutes.get(figure.figureId));
      if (!route) return;
      const scope = route.scientificScope;
      const card = node("article", "approval-route");
      append(card,
        node("span", "approval-figure", figure.label),
        node("h3", null, route.label),
        node("p", null, scope.claimCoverage)
      );
      const validationLabels = (scope.validationTargetIds || []).map((targetId) => {
        const target = (figure.validationTargets || []).find((item) => item.targetId === targetId);
        return target ? target.label : targetId;
      });
      const deliverableLabels = (route.deliverables || []).map((item) => item.label);
      const summaryGrid = node("div", "approval-route-grid");
      [["假设", scope.assumptions, "无额外假设"], ["验证目标", validationLabels, "未声明"], ["产物", deliverableLabels, "未声明"]].forEach(([label, items, emptyText]) => {
        const field = node("div", "approval-route-field");
        field.appendChild(node("span", "field-label", label));
        field.appendChild(renderPills(items, "scope-pills", emptyText));
        summaryGrid.appendChild(field);
      });
      card.appendChild(summaryGrid);
      approvalSummary.appendChild(card);
    });
    if (selected.length) {
      const boundary = node("p", "approval-boundary", `${aggregateRouteFacts(selectedRoutes)} · ${overwriteRouteSelected ? "所选路线要求覆盖文件；本静态页面只导出新建文件批准单，请改选无覆盖路线或重新生成逐文件审批报告。" : "仅创建新文件；超过上限须重新批准。"}`);
      approvalSummary.appendChild(boundary);
    }
  }

  function exportApproval() {
    const selectedFigures = [];
    const effects = new Set();
    figures.filter((figure) => included.has(figure.figureId) && targetCanBeApproved(figure)).forEach((figure) => {
      const route = routeFor(figure, currentRoutes.get(figure.figureId));
      if (!route || routeIsBlocked(figure, route)) return;
      (route.effects || []).forEach((effect) => effects.add(effect));
      selectedFigures.push({
        figureId: figure.figureId,
        sourceImageSha256: figure.target.targetSha256,
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
    link.download = `${approvalId}.scirepro-approval.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  function renderAppendix() {
    const root = document.getElementById("appendix-content");
    root.textContent = "";

    const integritySection = node("section", "appendix-integrity");
    integritySection.appendChild(node("h3", null, "目标与报告资产校验"));
    if (report.targetSet && report.targetSet.manifestSha256) {
      const manifest = node("p", "appendix-manifest");
      append(manifest, node("span", "field-label", "Phase 0 清单 SHA-256"), node("code", null, report.targetSet.manifestSha256));
      integritySection.appendChild(manifest);
    }
    const targetList = node("ul", "appendix-list appendix-target-list");
    figures.forEach((figure) => {
      const item = node("li", "appendix-item appendix-target-item");
      append(item, node("strong", null, `${figure.label} · ${(figure.target && figure.target.targetId) || figure.figureId}`));
      const hashes = node("dl", "appendix-hashes");
      [
        ["目标原图", figure.target && figure.target.targetSha256],
        ["报告 PNG 资产", figure.image && figure.image.sha256]
      ].forEach(([label, value]) => {
        const row = node("div", "appendix-hash-row");
        const digest = node("dd");
        digest.appendChild(value ? node("code", null, value) : node("span", "hash-unavailable", "未嵌入 / 未记录"));
        append(row, node("dt", null, `${label} SHA-256`), digest);
        hashes.appendChild(row);
      });
      item.appendChild(hashes);
      targetList.appendChild(item);
    });
    integritySection.appendChild(targetList);
    root.appendChild(integritySection);

    const envSection = node("section");
    envSection.appendChild(node("h3", null, "本机环境"));
    const envList = node("ul", "appendix-list");
    (report.environment || []).forEach((environment) => {
      const item = node("li", "appendix-item");
      const status = environmentStatusLabels[environment.status] || environment.status;
      const provisioning = provisioningLabels[environment.provisioning] || environment.provisioning;
      append(item, node("strong", null, `${environment.label} · ${status}`), node("small", null, `${provisioning} · ${environment.version || "版本未知"} · ${environment.detail || "无补充说明"}`));
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
      if (source.access && (source.access.checkedAt || source.access.note)) {
        item.appendChild(node("small", null, [source.access.checkedAt, source.access.note].filter(Boolean).join(" · ")));
      }
      if (source.note) item.appendChild(node("small", null, source.note));
      if (source.artifact && source.artifact.sha256) {
        const artifactHash = node("p", "appendix-artifact-hash");
        const artifactLabel = `${source.artifact.fileName || "本地来源工件"} · ${formatBytes(source.artifact.sizeBytes)}`;
        append(artifactHash, node("span", null, `${artifactLabel} · SHA-256`), node("code", null, source.artifact.sha256));
        item.appendChild(artifactHash);
      }
      sourceList.appendChild(item);
    });
    sourceSection.appendChild(sourceList);
    root.appendChild(sourceSection);
  }

  initialize();
}());
