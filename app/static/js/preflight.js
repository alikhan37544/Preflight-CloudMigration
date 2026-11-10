(() => {
  "use strict";

  const runId = document.body.dataset.runId || "";
  const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const toast = document.querySelector("[data-toast]");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let toastTimer = null;

  function motionBehavior() {
    return reducedMotion.matches ? "auto" : "smooth";
  }

  function notify(message, isError = false) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("visible");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("visible"), 4200);
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let detail = "Request failed";
      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch (error) {
        /* keep the default message */
      }
      throw new Error(detail);
    }
    return response.json();
  }

  /* Responsive navigation: collapse the primary nav behind a toggle on small screens. */
  const sidebar = document.querySelector(".sidebar");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navToggleHint = document.querySelector("[data-nav-toggle-hint]");

  function setNavOpen(open) {
    if (!sidebar || !navToggle) return;
    sidebar.classList.toggle("nav-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (navToggleHint) navToggleHint.textContent = open ? "Close" : "Menu";
  }

  if (sidebar && navToggle) {
    navToggle.addEventListener("click", () => {
      setNavOpen(!sidebar.classList.contains("nav-open"));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sidebar.classList.contains("nav-open")) {
        setNavOpen(false);
        navToggle.focus();
      }
    });
    const desktopQuery = window.matchMedia("(min-width: 981px)");
    const closeOnDesktop = (event) => {
      if (event.matches) setNavOpen(false);
    };
    if (desktopQuery.addEventListener) desktopQuery.addEventListener("change", closeOnDesktop);
    else desktopQuery.addListener(closeOnDesktop);
  }

  /* Horizontally scrollable tables: show the cue only when columns really overflow. */
  function syncScrollRegion(region) {
    if (!region) return;
    const previous = region.previousElementSibling;
    const hint = previous && previous.matches("[data-scroll-hint]") ? previous : null;
    const scrollable = region.scrollWidth > region.clientWidth + 1;
    region.classList.toggle("is-scrollable", scrollable);
    if (hint) hint.hidden = !scrollable;
  }

  function syncScrollRegions() {
    document.querySelectorAll("[data-table-scroll]").forEach(syncScrollRegion);
  }

  syncScrollRegions();
  window.addEventListener("resize", syncScrollRegions, { passive: true });
  if (typeof ResizeObserver !== "undefined") {
    document.querySelectorAll("[data-table-scroll]").forEach((region) => {
      new ResizeObserver(() => syncScrollRegion(region)).observe(region);
    });
  }

  /* Tabs: ARIA tablist with roving tabindex, arrow keys, and URL sync. */
  const tablist = document.querySelector('[role="tablist"]');
  const tabs = Array.from(document.querySelectorAll(".tab[data-tab]"));

  function activateTab(tab, options = {}) {
    if (!tab) return;
    const name = tab.dataset.tab;
    tabs.forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-selected", selected ? "true" : "false");
      item.tabIndex = selected ? 0 : -1;
      const controlled = item.getAttribute("aria-controls");
      const panel = controlled ? document.getElementById(controlled) : null;
      if (panel) {
        panel.classList.toggle("active", selected);
        panel.hidden = !selected;
      }
    });
    if (options.focus) tab.focus();
    if (options.updateUrl !== false) {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", name);
      window.history.replaceState({}, "", url);
    }
    window.requestAnimationFrame(syncScrollRegions);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab));
  });
  if (tablist && tabs.length) {
    tablist.addEventListener("keydown", (event) => {
      const current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      let next = null;
      if (event.key === "ArrowRight") next = tabs[(current + 1) % tabs.length];
      else if (event.key === "ArrowLeft") next = tabs[(current - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        event.preventDefault();
        activateTab(next, { focus: true });
      }
    });
  }

  /* Client-side feature filter */
  const featureEmpty = document.querySelector("[data-feature-empty]");
  document.querySelectorAll("[data-filter-target]").forEach((input) => {
    input.addEventListener("input", () => {
      const term = input.value.trim().toLowerCase();
      let visible = 0;
      document.querySelectorAll("[data-feature-row]").forEach((row) => {
        const hide = term.length > 0 && !row.textContent.toLowerCase().includes(term);
        row.hidden = hide;
        if (!hide) visible += 1;
      });
      if (featureEmpty) featureEmpty.hidden = visible > 0;
    });
  });

  /* Evidence drawer */
  const evidenceScript = document.getElementById("evidence-data");
  let evidenceById = {};
  if (evidenceScript) {
    try {
      evidenceById = JSON.parse(evidenceScript.textContent || "{}");
    } catch (error) {
      evidenceById = {};
    }
  }
  const drawer = document.querySelector("[data-evidence-drawer]");
  const inlineEvidence = document.querySelector("[data-evidence-inline]");
  const inlineBody = document.querySelector("[data-evidence-inline-body]");

  function evidenceLocator(evidence) {
    const loc = evidence.locator || {};
    const kind = (loc.kind || "").toLowerCase();
    const text = loc.value || "";
    const line = loc.line;
    if (text && kind && text.toLowerCase().startsWith(`${kind} `)) return text;
    if (text && kind) return `${kind} ${text}${line ? `:${line}` : ""}`;
    if (kind) return `${kind}${line ? ` ${line}` : ""}`;
    return text || "unknown";
  }

  function buildEvidenceParts(evidence) {
    const head = document.createElement("div");
    head.className = "evidence-head";
    const confidence = document.createElement("span");
    confidence.className = "pill pill-confidence";
    confidence.textContent = evidence.confidence;
    const id = document.createElement("code");
    id.textContent = evidence.evidence_id;
    head.append(confidence, id);

    const path = document.createElement("div");
    path.className = "evidence-path";
    path.textContent = evidence.path;

    const locator = document.createElement("div");
    locator.className = "evidence-locator";
    locator.textContent = evidenceLocator(evidence);

    const excerpt = document.createElement("pre");
    excerpt.className = "evidence-excerpt";
    excerpt.textContent = evidence.excerpt || "";

    const meta = document.createElement("div");
    meta.className = "muted";
    meta.textContent = `Method: ${evidence.method || "unknown"}. Excerpt SHA-256: ${(evidence.excerpt_sha || "").slice(0, 12)}`;
    return { head, path, locator, excerpt, meta };
  }

  function showInlineEvidence(evidenceId, fallbackPath) {
    if (!inlineEvidence || !inlineBody) return;
    inlineBody.textContent = "";
    const evidence = evidenceById[evidenceId];
    if (!evidence) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = fallbackPath
        ? `${fallbackPath} - structural node; no evidence record is attached.`
        : "Select an evidence-bearing node.";
      inlineBody.append(empty);
      inlineEvidence.hidden = false;
      return;
    }
    const parts = buildEvidenceParts(evidence);
    inlineBody.append(parts.head, parts.path, parts.locator, parts.excerpt, parts.meta);
    inlineEvidence.hidden = false;
  }

  function showEvidence(evidenceId, fallbackPath) {
    const evidence = evidenceById[evidenceId];
    showInlineEvidence(evidenceId, fallbackPath);
    if (!drawer) return;
    drawer.textContent = "";
    if (!evidence) {
      const empty = document.createElement("div");
      empty.className = "empty-inline";
      const title = document.createElement("p");
      title.textContent = fallbackPath || "No source record is attached to this node.";
      const hint = document.createElement("p");
      hint.className = "muted";
      hint.textContent = "This node is structural. Select an evidence-bearing node or feature.";
      empty.append(title, hint);
      drawer.append(empty);
      return;
    }
    const parts = buildEvidenceParts(evidence);
    drawer.append(parts.head, parts.path, parts.locator, parts.excerpt, parts.meta);
  }

  const spineSelectedNote = document.querySelector("[data-spine-selected]");

  function addSelectedOutline(node) {
    if (node.querySelector(".node-selected-outline")) return;
    const box = node.querySelector("rect");
    if (!box) return;
    const outline = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    outline.setAttribute("class", "node-selected-outline");
    outline.setAttribute("x", String(Number(box.getAttribute("x")) - 3));
    outline.setAttribute("y", String(Number(box.getAttribute("y")) - 3));
    outline.setAttribute("width", String(Number(box.getAttribute("width")) + 6));
    outline.setAttribute("height", String(Number(box.getAttribute("height")) + 6));
    outline.setAttribute("rx", "6");
    node.insertBefore(outline, box);
  }

  document.querySelectorAll("[data-evidence-id]:not([data-evidence-id=''])").forEach((node) => {
    const activate = () => {
      document.querySelectorAll(".spine-node.selected").forEach((item) => {
        item.classList.remove("selected");
        item.setAttribute("aria-pressed", "false");
        const outline = item.querySelector(".node-selected-outline");
        if (outline) outline.remove();
      });
      node.classList.add("selected");
      node.setAttribute("aria-pressed", "true");
      addSelectedOutline(node);
      if (spineSelectedNote) {
        const evidenceId = node.dataset.evidenceId || "";
        spineSelectedNote.textContent = evidenceId ? `Selected ${evidenceId}` : "Selected structural node";
      }
      showEvidence(node.dataset.evidenceId, node.dataset.path);
    };
    node.addEventListener("click", activate);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
  });

  /* Spine overflow hint and direct-link selected node */
  const spineScroll = document.querySelector("[data-spine-scroll]");
  const spineHint = document.querySelector("[data-spine-scroll-hint]");
  function syncSpineHint() {
    if (!spineScroll || !spineHint) return;
    const scrollable = spineScroll.scrollWidth > spineScroll.clientWidth + 1;
    spineHint.hidden = !scrollable;
    spineScroll.classList.toggle("is-scrollable", scrollable);
  }
  if (spineScroll) {
    syncSpineHint();
    window.addEventListener("resize", syncSpineHint, { passive: true });
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(syncSpineHint).observe(spineScroll);
    }
    const selectedNode = spineScroll.querySelector(".spine-node.selected");
    if (selectedNode) {
      const nodeBox = selectedNode.getBoundingClientRect();
      const scrollBox = spineScroll.getBoundingClientRect();
      const target = spineScroll.scrollLeft + (nodeBox.left - scrollBox.left)
        - (scrollBox.width - nodeBox.width) / 2;
      spineScroll.scrollTo({ left: Math.max(0, target), behavior: motionBehavior() });
    }
  }

  /* Assistant: short transcript, newest at bottom, retryable errors. */
  const assistantForm = document.querySelector("[data-assistant-form]");
  const assistantResult = document.querySelector("[data-assistant-result]");
  const assistantTranscript = document.querySelector("[data-assistant-transcript]");
  const assistantHint = document.querySelector("[data-assistant-hint]");
  const assistantSubmit = document.querySelector("[data-assistant-submit]");
  const assistantMaxTurns = 5;
  let assistantPending = false;

  function citationHref(evidenceId) {
    const url = new URL("/", window.location.origin);
    url.searchParams.set("run", runId);
    const featureId = assistantForm ? assistantForm.dataset.featureId || "" : "";
    if (featureId) url.searchParams.set("feature", featureId);
    url.searchParams.set("evidence", evidenceId);
    url.hash = "evidence-drawer";
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function buildCitationCard(citationId) {
    const evidence = evidenceById[citationId];
    const card = document.createElement("a");
    card.className = "citation-card";
    card.href = citationHref(citationId);
    card.setAttribute(
      "aria-label",
      `Open evidence ${citationId}${evidence && evidence.path ? ` ${evidence.path}` : ""}`
    );
    if (!evidence) {
      const top = document.createElement("div");
      top.className = "citation-top";
      const code = document.createElement("code");
      code.textContent = citationId;
      const missing = document.createElement("span");
      missing.className = "citation-missing";
      missing.textContent = "Open evidence";
      top.append(code, missing);
      card.append(top);
      return card;
    }
    const parts = buildEvidenceParts(evidence);
    const top = document.createElement("div");
    top.className = "citation-top";
    const open = document.createElement("span");
    open.className = "citation-open";
    open.textContent = "Open evidence \u2192";
    top.append(parts.head, open);
    card.append(top, parts.path, parts.locator, parts.excerpt);
    return card;
  }

  function buildAnswer(data) {
    const block = document.createElement("div");
    block.className = "answer-block" + (data.grounded ? "" : " refusal");
    const answer = document.createElement("p");
    answer.textContent = data.answer;
    block.append(answer);
    if (data.citations && data.citations.length) {
      const cite = document.createElement("div");
      cite.className = "citation-list";
      const heading = document.createElement("div");
      heading.className = "muted";
      heading.textContent = "Citations (open the evidence panel)";
      cite.append(heading);
      data.citations.forEach((citationId) => cite.append(buildCitationCard(citationId)));
      block.append(cite);
    }
    if (data.missing_evidence && data.missing_evidence.length) {
      const missing = document.createElement("div");
      missing.className = "muted";
      missing.textContent = "Would need: " + data.missing_evidence.join("; ");
      block.append(missing);
    }
    return block;
  }

  function trimTranscript() {
    while (assistantTranscript.children.length > assistantMaxTurns) {
      assistantTranscript.firstElementChild.remove();
    }
  }

  function createTurn(question) {
    const turn = document.createElement("div");
    turn.className = "assistant-turn";
    const asked = document.createElement("p");
    asked.className = "assistant-question";
    asked.textContent = question;
    const body = document.createElement("div");
    body.className = "assistant-answer";
    turn.append(asked, body);
    assistantTranscript.append(turn);
    trimTranscript();
    if (assistantHint) assistantHint.hidden = true;
    return { turn, body };
  }

  function buildErrorBlock(message, retry) {
    const box = document.createElement("div");
    box.className = "assistant-error";
    box.setAttribute("role", "alert");
    const text = document.createElement("p");
    text.textContent = message;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-small";
    button.textContent = "Retry";
    button.addEventListener("click", retry);
    box.append(text, button);
    return box;
  }

  async function askAssistant(question, existingTurn) {
    if (assistantPending) return;
    assistantPending = true;
    const turn = existingTurn || createTurn(question);
    turn.body.textContent = "";
    const pending = document.createElement("p");
    pending.className = "assistant-pending";
    pending.textContent = "Searching evidence...";
    turn.body.append(pending);
    if (assistantSubmit) assistantSubmit.disabled = true;
    if (assistantForm) assistantForm.setAttribute("aria-busy", "true");
    try {
      const featureId = assistantForm ? assistantForm.dataset.featureId || "" : "";
      const payload = featureId ? { question, feature_id: featureId } : { question };
      const data = await postJson(`/api/runs/${runId}/assistant`, payload);
      turn.body.textContent = "";
      turn.body.append(buildAnswer(data));
    } catch (error) {
      turn.body.textContent = "";
      const detail = error && error.message && error.message !== "Request failed"
        ? ` (${error.message})`
        : "";
      turn.body.append(buildErrorBlock(
        `Could not get an answer${detail}. Check that the run is still available, then retry.`,
        () => askAssistant(question, turn)
      ));
    } finally {
      assistantPending = false;
      if (assistantSubmit) assistantSubmit.disabled = false;
      if (assistantForm) assistantForm.removeAttribute("aria-busy");
      if (assistantTranscript) assistantTranscript.scrollTop = assistantTranscript.scrollHeight;
    }
  }

  if (assistantForm && assistantResult && assistantTranscript && runId) {
    assistantForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = assistantForm.querySelector('input[name="question"]');
      const question = ((input || {}).value || "").trim();
      if (!question) return;
      if (input) input.value = "";
      askAssistant(question);
    });
  }

  document.querySelectorAll("[data-assistant-prompt]").forEach((chip) => {
    chip.addEventListener("click", () => {
      if (!assistantForm) return;
      const input = assistantForm.querySelector('input[name="question"]');
      if (input) input.value = chip.dataset.assistantPrompt || "";
      assistantForm.requestSubmit();
    });
  });

  /* Decisions */
  const STATE_CLASSES = [
    "state-pending", "state-open", "state-accepted",
    "state-rejected", "state-deferred", "state-edited",
  ];

  function updateState(container, stateText) {
    if (!container) return;
    container.querySelectorAll("[data-state]").forEach((state) => {
      state.textContent = stateText;
      state.classList.remove(...STATE_CLASSES);
      state.classList.add(`state-${stateText}`);
    });
  }

  function replaceDecisionButtons(container, stateText) {
    if (!container) return;
    const actions = container.querySelector(".detail-actions")
      || container.querySelector(".change-actions")
      || container.querySelector(".actions-col")
      || container.querySelector(".decision-actions");
    if (!actions) return;
    actions.querySelectorAll("[data-decision]").forEach((button) => button.remove());
    let recorded = actions.querySelector(".decision-recorded");
    if (!recorded) {
      recorded = document.createElement("p");
      recorded.className = "decision-recorded";
      recorded.setAttribute("role", "status");
      actions.append(recorded);
    }
    recorded.classList.remove(...STATE_CLASSES);
    recorded.classList.add(`state-${stateText}`);
    recorded.textContent = `Decision recorded: ${stateText}`;
    recorded.setAttribute("tabindex", "-1");
    recorded.focus({ preventScroll: true });
  }

  async function latestAssumptionFor(mappingId) {
    try {
      const response = await fetch(`/api/runs/${runId}/assumptions`);
      if (!response.ok) return null;
      const data = await response.json();
      const items = (data.assumptions || []).filter((item) => (item.assumption_id || "").startsWith("A-DEC-"));
      const related = items.filter((item) => item.related_mapping_id === mappingId);
      return related.length ? related[related.length - 1] : (items.length ? items[items.length - 1] : null);
    } catch (error) {
      return null;
    }
  }

  function appendAssumptionRow(assumption) {
    const body = document.querySelector("[data-assumptions-body]");
    if (!body || !assumption || !assumption.assumption_id) return;
    if (body.querySelector(`[data-assumption-id="${assumption.assumption_id}"]`)) return;
    const row = document.createElement("tr");
    row.dataset.assumptionId = assumption.assumption_id;
    row.classList.add("assumption-new");

    const idCell = document.createElement("td");
    const id = document.createElement("code");
    id.textContent = assumption.assumption_id;
    const flag = document.createElement("span");
    flag.className = "pill pill-info assumption-new-flag";
    flag.textContent = "new";
    idCell.append(id, flag);

    const statementCell = document.createElement("td");
    statementCell.textContent = assumption.statement || "";
    const basis = document.createElement("div");
    basis.className = "muted";
    basis.textContent = assumption.impact_basis || "";
    statementCell.append(basis);

    const impactCell = document.createElement("td");
    const impact = document.createElement("span");
    impact.className = `pill pill-impact impact-${assumption.impact || "medium"}`;
    impact.textContent = assumption.impact || "medium";
    impactCell.append(impact);

    const rangeCell = document.createElement("td");
    const range = assumption.impact_range_days || [1.0, 2.0];
    rangeCell.textContent = `${Math.round(range[0])}-${Math.round(range[1])} engineer-days`;
    const caveat = document.createElement("div");
    caveat.className = "muted";
    caveat.textContent = assumption.impact_caveat || "";
    rangeCell.append(caveat);

    const questionCell = document.createElement("td");
    questionCell.textContent = assumption.question_to_ask || "";
    const ownerCell = document.createElement("td");
    ownerCell.className = "assumption-owner";
    ownerCell.textContent = assumption.owner || "unassigned";
    const statusCell = document.createElement("td");
    statusCell.textContent = assumption.status || "open";

    row.append(idCell, statementCell, impactCell, rangeCell, questionCell, ownerCell, statusCell);
    body.prepend(row);
    const counter = document.querySelector('.tab[data-tab="assumptions"] .counter');
    if (counter) counter.textContent = String(body.querySelectorAll("[data-assumption-id]").length);
  }

  function focusAssumptionRow(assumptionId) {
    const tab = document.querySelector('.tab[data-tab="assumptions"]');
    if (tab) activateTab(tab);
    if (!assumptionId) return;
    const row = document.querySelector(`[data-assumption-id="${assumptionId}"]`);
    if (!row) return;
    row.classList.add("assumption-new");
    row.setAttribute("tabindex", "-1");
    row.scrollIntoView({ behavior: motionBehavior(), block: "center" });
    row.focus({ preventScroll: true });
  }

  function showAssumptionNotice(assumption, mappingId) {
    const notice = document.querySelector("[data-assumption-notice]");
    if (!notice) return;
    notice.textContent = "";
    const title = document.createElement("strong");
    title.textContent = assumption ? "New assumption" : "Rejection recorded";
    const label = document.createElement("span");
    if (assumption) {
      const code = document.createElement("code");
      code.textContent = assumption.assumption_id;
      label.append(" ", code, ` created from the ${mappingId} rejection. `);
      if (assumption.impact) label.append(`Impact: ${assumption.impact}. `);
      if (assumption.question_to_ask) label.append(assumption.question_to_ask);
    } else {
      label.textContent = ` for ${mappingId} was saved; open the assumption register to review the new A-DEC row.`;
    }
    const link = document.createElement("a");
    link.href = `/reconstruction?run=${encodeURIComponent(runId)}&tab=assumptions`;
    link.className = "btn btn-small btn-ghost";
    link.textContent = "View assumption register";
    if (assumption) {
      link.dataset.assumptionJump = assumption.assumption_id;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        focusAssumptionRow(assumption.assumption_id);
      });
    }
    notice.append(title, label, document.createElement("br"), link);
    notice.hidden = false;
    const box = notice.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) {
      notice.scrollIntoView({ behavior: motionBehavior(), block: "nearest" });
    }
  }

  const decisionDialog = document.querySelector("[data-decision-dialog]");
  const decisionForm = document.querySelector("[data-decision-form]");
  const decisionTitle = document.querySelector("[data-decision-title]");
  const decisionObjectType = document.querySelector("[data-decision-object-type]");
  const decisionObjectId = document.querySelector("[data-decision-object-id]");
  const decisionObjectSummary = document.querySelector("[data-decision-object-summary]");
  const decisionReason = document.querySelector("[data-decision-reason]");
  const decisionEdit = document.querySelector("[data-decision-edit]");
  const decisionValue = document.querySelector("[data-decision-value]");
  const decisionValueLabel = document.querySelector("[data-decision-value-label]");
  const decisionError = document.querySelector("[data-decision-error]");
  const decisionConsequence = document.querySelector("[data-decision-consequence]");
  const decisionConfirm = document.querySelector("[data-decision-confirm]");
  let pendingDecision = null;
  const ACTION_STATES = { accept: "accepted", reject: "rejected", defer: "deferred", edit: "edited" };
  const ACTION_UI = {
    accept: {
      verb: "Accept",
      confirm: "Record acceptance",
      consequence: "This records acceptance in the audit trail. No assumption is created.",
      danger: false,
    },
    reject: {
      verb: "Reject",
      confirm: "Record rejection",
      consequence: "This creates an assumption and records the rejection in the audit trail.",
      danger: true,
    },
    defer: {
      verb: "Defer",
      confirm: "Record deferral",
      consequence: "This records the deferral in the audit trail; the item stays pending.",
      danger: false,
    },
    edit: {
      verb: "Edit",
      confirm: "Record edit",
      consequence: "This records the corrected value and your reason in the audit trail.",
      danger: false,
    },
  };

  function showDecisionError(message) {
    if (!decisionError) return;
    decisionError.textContent = message;
    decisionError.hidden = false;
  }

  function clearDecisionError() {
    if (!decisionError) return;
    decisionError.textContent = "";
    decisionError.hidden = true;
  }

  function openDecisionDialog(button) {
    if (!decisionDialog || !decisionForm) return;
    const action = button.dataset.decision;
    const objectType = button.dataset.objectType;
    const objectId = button.dataset.objectId;
    const label = button.dataset.objectLabel || `${objectType} ${objectId}`;
    const summary = button.dataset.objectSummary || "";
    const ui = ACTION_UI[action] || ACTION_UI.accept;
    const isEdit = action === "edit";
    pendingDecision = { action, objectType, objectId, label };
    if (decisionTitle) decisionTitle.textContent = `${ui.verb} ${label}`;
    if (decisionObjectType) decisionObjectType.textContent = objectType;
    if (decisionObjectId) decisionObjectId.textContent = objectId;
    if (decisionObjectSummary) {
      decisionObjectSummary.textContent = summary || "No source-to-target summary is available.";
    }
    if (decisionConsequence) {
      decisionConsequence.textContent = (
        action === "reject" && objectType !== "mapping"
          ? "This records the rejection in the audit trail."
          : ui.consequence
      );
    }
    decisionDialog.classList.toggle("is-danger", ui.danger);
    decisionForm.dataset.action = action;
    if (decisionReason) {
      decisionReason.value = "";
      decisionReason.placeholder = "Why is this decision correct?";
    }
    if (decisionEdit) decisionEdit.hidden = !isEdit;
    if (decisionValue) {
      decisionValue.required = isEdit;
      decisionValue.value = isEdit ? button.dataset.editValue || "" : "";
    }
    if (decisionValueLabel) {
      decisionValueLabel.textContent = `${button.dataset.editLabel || "Edited value"} (required)`;
    }
    if (decisionConfirm) {
      decisionConfirm.textContent = ui.confirm;
      decisionConfirm.classList.toggle("btn-danger", ui.danger);
      decisionConfirm.classList.toggle("btn-primary", !ui.danger);
    }
    clearDecisionError();
    decisionDialog.showModal();
    if (decisionReason) {
      decisionReason.focus();
      decisionReason.setSelectionRange(0, 0);
    }
  }

  function closeDecisionDialog() {
    pendingDecision = null;
    if (decisionDialog && decisionDialog.open) decisionDialog.close();
  }

  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!runId) return;
      openDecisionDialog(button);
    });
  });
  document.querySelectorAll("[data-decision-cancel]").forEach((button) => {
    button.addEventListener("click", closeDecisionDialog);
  });
  if (decisionDialog) {
    decisionDialog.addEventListener("click", (event) => {
      if (event.detail > 1) return;
      if (event.target === decisionDialog) closeDecisionDialog();
    });
    decisionDialog.addEventListener("close", () => {
      pendingDecision = null;
    });
  }

  if (decisionForm) {
    decisionForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!pendingDecision) return;
      const decision = pendingDecision;
      const reason = (decisionReason && decisionReason.value || "").trim();
      const editedValue = (decisionValue && decisionValue.value || "").trim();
      if (!reason) {
        showDecisionError("Enter a reason before recording the decision.");
        if (decisionReason) decisionReason.focus();
        return;
      }
      if (decision.action === "edit" && !editedValue) {
        showDecisionError("Enter the edited value before recording the decision.");
        if (decisionValue) decisionValue.focus();
        return;
      }
      clearDecisionError();
      const confirmText = decisionConfirm ? decisionConfirm.textContent : "";
      const cancelButtons = decisionDialog
        ? Array.from(decisionDialog.querySelectorAll("[data-decision-cancel]"))
        : [];
      if (decisionConfirm) {
        decisionConfirm.disabled = true;
        decisionConfirm.textContent = "Recording...";
      }
      cancelButtons.forEach((button) => { button.disabled = true; });
      try {
        const payload = {
          object_type: decision.objectType,
          object_id: decision.objectId,
          action: decision.action,
          reason,
        };
        if (decision.action === "edit") payload.edited_value = editedValue;
        const data = await postJson(`/api/runs/${runId}/decisions`, payload);
        const stateText = (decision.objectType === "finding" && decision.action === "edit")
          ? "accepted"
          : ACTION_STATES[decision.action] || decision.action;
        closeDecisionDialog();

        const localContainer = decision.objectType === "finding"
          ? document.querySelector(".detail-panel")
          : null;
        const row = decision.objectType === "mapping"
          ? document.querySelector(`[data-mapping-row="${decision.objectId}"]`)
          : decision.objectType === "finding"
            ? document.querySelector(`[data-finding-row="${decision.objectId}"]`)
            : document.querySelector(`[data-change-block="${decision.objectId}"]`);
        updateState(localContainer, stateText);
        updateState(row, stateText);
        if (row && row.matches("tr")) {
          row.classList.remove(
            "row-pending", "row-open", "row-accepted", "row-rejected", "row-deferred", "row-edited"
          );
          row.classList.add(`row-${stateText}`);
        }
        if (decision.objectType === "mapping" && decision.action === "edit" && row) {
          const target = row.querySelector("[data-mapping-target]");
          if (target) target.textContent = (data.object && data.object.target_name) || editedValue;
        }
        replaceDecisionButtons(row, stateText);
        replaceDecisionButtons(localContainer, stateText);
        if (decision.objectType === "finding") {
          const url = new URL(window.location.href);
          url.searchParams.set("selected", decision.objectId);
          window.history.replaceState({}, "", url);
        }
        notify(`Recorded ${decision.action} for ${decision.objectId}.`);
        if (decision.objectType === "mapping" && decision.action === "reject") {
          let assumption = data.assumption || null;
          if (!assumption) assumption = await latestAssumptionFor(decision.objectId);
          appendAssumptionRow(assumption);
          showAssumptionNotice(assumption, decision.objectId);
        }
      } catch (error) {
        const message = error && error.message ? error.message : "Request failed";
        const hint = /already/i.test(message)
          ? " Refresh the page to see the current state, or cancel and choose another item."
          : " Try again, or cancel to keep the current state.";
        showDecisionError(message + hint);
      } finally {
        if (decisionConfirm) {
          decisionConfirm.disabled = false;
          decisionConfirm.textContent = confirmText;
        }
        cancelButtons.forEach((button) => { button.disabled = false; });
      }
    });
  }

  document.querySelectorAll("[data-delete-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.deleteRun;
      if (!confirm(`Delete run ${id} and its draft?`)) return;
      try {
        await postJson(`/api/runs/${id}/delete`, {});
        notify(`Deleted ${id}.`);
        const row = button.closest("tr");
        if (row) row.remove();
        if (!document.querySelector("[data-run-row]")) {
          const table = document.querySelector("[data-runs-table]");
          const empty = document.querySelector("[data-runs-empty]");
          if (table) table.hidden = true;
          if (empty) empty.hidden = false;
        }
      } catch (error) {
        notify(error.message, true);
      }
    });
  });

  /* Import and progress */
  const importProgress = document.querySelector("[data-import-progress]");
  const importBar = document.querySelector("[data-import-bar]");
  const importLabel = document.querySelector("[data-import-label]");

  async function pollRun(id) {
    const response = await fetch(`/api/runs/${id}/status`);
    if (!response.ok) throw new Error("Run status unavailable");
    return response.json();
  }

  function runDestination(id) {
    const waitPanel = document.querySelector("[data-run-wait]");
    const returnTo = waitPanel && waitPanel.dataset.returnTo;
    if (returnTo) {
      try {
        const url = new URL(returnTo, window.location.origin);
        url.searchParams.set("run", id);
        return `${url.pathname}${url.search}${url.hash}`;
      } catch (error) {
        /* fall back to the workbench below */
      }
    }
    return `/?run=${encodeURIComponent(id)}`;
  }

  async function watchRun(id) {
    const waitPanel = document.querySelector("[data-run-wait]");
    if (importProgress) importProgress.hidden = false;
    if (!importProgress && !waitPanel) {
      window.location.href = runDestination(id);
      return true;
    }
    const bar = importBar || document.querySelector("[data-run-bar]");
    const label = importLabel || document.querySelector("[data-run-label]");
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      let status;
      try {
        status = await pollRun(id);
      } catch (error) {
        if (label) label.textContent = error.message;
        return false;
      }
      const percent = (status.progress && status.progress.percent) || 0;
      if (bar) bar.value = Math.max(2, percent);
      if (label) label.textContent = `${status.stage} - ${Math.round(percent)}%`;
      if (status.status === "succeeded") {
        window.location.href = runDestination(id);
        return true;
      }
      if (status.status === "failed" || status.status === "cancelled") {
        if (label) label.textContent = `Run ${status.status}. See run history.`;
        return false;
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    if (label) label.textContent = "Run is taking longer than expected. Open run history.";
    return false;
  }

  document.querySelectorAll("[data-import]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const data = await postJson("/api/runs", {
          project_id: "demo",
          fixture_id: button.dataset.import,
          force: true,
        });
        notify(`Started ${data.run_id}.`);
        if (data.status === "succeeded") {
          window.location.href = runDestination(data.run_id);
          return;
        }
        await watchRun(data.run_id);
      } catch (error) {
        notify(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  });

  const uploadForm = document.querySelector("[data-upload-form]");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = uploadForm.querySelector('input[type="file"]');
      if (!input || !input.files || !input.files.length) return;
      const formData = new FormData();
      formData.append("file", input.files[0]);
      const button = uploadForm.querySelector("button[type=submit]");
      if (button) button.disabled = true;
      try {
        const response = await fetch("/api/imports", {
          method: "POST",
          headers: { "X-CSRF-Token": csrf },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Import failed");
        notify(`Started ${data.run_id}.`);
        if (data.status === "succeeded") {
          window.location.href = runDestination(data.run_id);
          return;
        }
        await watchRun(data.run_id);
      } catch (error) {
        notify(error.message, true);
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  const wait = document.querySelector("[data-run-wait]");
  if (wait) {
    watchRun(wait.dataset.runId || runId);
  }

  /* Copy buttons */
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = (button.dataset.copy || "").trim();
      if (!value) {
        notify("No snapshot hash is available to copy.", true);
        return;
      }
      try {
        if (!navigator.clipboard) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(value);
        notify("Snapshot hash copied.");
      } catch (error) {
        const area = document.createElement("textarea");
        area.value = value;
        document.body.append(area);
        area.select();
        document.execCommand("copy");
        area.remove();
        notify("Snapshot hash copied.");
      }
    });
  });

  /* Findings: after Inspect, bring the detail heading into view and focus it. */
  const detailHeading = document.getElementById("finding-detail-heading");
  function focusFindingDetail() {
    if (!detailHeading) return;
    detailHeading.focus({ preventScroll: true });
    detailHeading.scrollIntoView({ behavior: "auto", block: "start" });
  }
  if (detailHeading && new URLSearchParams(window.location.search).has("selected")) {
    window.requestAnimationFrame(focusFindingDetail);
  }
  document.querySelectorAll("[data-detail-jump]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (!detailHeading) return;
      event.preventDefault();
      focusFindingDetail();
      window.history.replaceState({}, "", "#finding-detail-heading");
    });
  });

  /* Limitations disclosure label mirrors the open state. */
  document.querySelectorAll("details.limitations").forEach((details) => {
    const hint = details.querySelector("[data-details-hint], .details-hint");
    if (!hint) return;
    const sync = () => { hint.textContent = details.open ? "collapse" : "expand"; };
    details.addEventListener("toggle", sync);
    sync();
  });

  /* Autonomous migrator: launch and follow the agent handoffs live. */
  const migrationPanel = document.querySelector("[data-migration-panel]");
  const migrationButton = document.querySelector("[data-migration-start]");
  let migrationPolling = false;

  async function watchMigration() {
    if (!runId || migrationPolling) return;
    migrationPolling = true;
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline) {
      let state;
      try {
        const response = await fetch(`/api/runs/${runId}/migration`, {
          headers: { "Accept": "application/json" },
        });
        if (!response.ok) throw new Error("Could not read migration state");
        state = await response.json();
      } catch (error) {
        migrationPolling = false;
        notify(error.message, true);
        return;
      }
      const bar = document.querySelector("[data-migration-bar]");
      const label = document.querySelector("[data-migration-label]");
      if (bar && typeof state.progress === "number") bar.value = state.progress;
      if (label) {
        const current = state.current_agent ? `Running ${state.current_agent}` : state.status;
        label.textContent = `${current} · ${Math.round(state.progress || 0)}%`;
      }
      (state.agents || []).forEach((agent) => {
        const card = document.querySelector(`[data-agent="${agent.agent_id}"]`);
        if (!card) return;
        card.classList.remove("agent-queued", "agent-running", "agent-done", "agent-failed");
        card.classList.add(`agent-${agent.status}`);
        const stateLabel = card.querySelector(".agent-state");
        if (stateLabel) stateLabel.textContent = agent.status;
        const summary = card.querySelector(".agent-summary");
        if (summary && agent.summary) summary.textContent = agent.summary;
      });
      const summary = state.summary || {};
      Object.keys(summary).forEach((key) => {
        const node = document.querySelector(`[data-migration-stat="${key}"]`);
        if (node) node.textContent = summary[key];
      });
      if (["completed", "completed_with_gates", "failed"].includes(state.status)) {
        window.location.reload();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    migrationPolling = false;
    notify("Migration is taking longer than expected. Refresh the page to inspect it.", true);
  }

  if (migrationPanel && migrationButton) {
    if (migrationPanel.dataset.migrationStatus === "running") {
      watchMigration();
    }
    migrationButton.addEventListener("click", async () => {
      migrationButton.disabled = true;
      try {
        const force = migrationButton.dataset.migrationForce === "1";
        await postJson(`/api/runs/${runId}/migration`, { force });
        notify("Migration running.");
        const hasRenderedState = Boolean(migrationPanel.dataset.migrationStatus);
        if (hasRenderedState) {
          migrationButton.disabled = false;
          await watchMigration();
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 650));
        window.location.reload();
      } catch (error) {
        migrationButton.disabled = false;
        notify(error.message, true);
      }
    });
  }
})();
