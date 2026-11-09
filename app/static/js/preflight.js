(() => {
  "use strict";

  const runId = document.body.dataset.runId || "";
  const csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const toast = document.querySelector("[data-toast]");
  let toastTimer = null;

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

  /* Tabs */
  document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      document.querySelectorAll(".tab[data-tab]").forEach((item) => {
        item.classList.toggle("active", item === tab);
        item.setAttribute("aria-selected", item === tab ? "true" : "false");
      });
      document.querySelectorAll(".tab-panel[data-tab-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.tabPanel === name);
      });
    });
  });

  /* Client-side feature filter */
  document.querySelectorAll("[data-filter-target]").forEach((input) => {
    input.addEventListener("input", () => {
      const term = input.value.trim().toLowerCase();
      document.querySelectorAll("[data-feature-row]").forEach((row) => {
        row.hidden = term.length > 0 && !row.textContent.toLowerCase().includes(term);
      });
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
    return `${loc.kind || "line"} ${loc.value || ""}${loc.line ? ":" + loc.line : ""}`.trim();
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

  document.querySelectorAll("[data-evidence-id]").forEach((node) => {
    const activate = () => {
      document.querySelectorAll(".spine-node.selected").forEach((item) => item.classList.remove("selected"));
      node.classList.add("selected");
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

  /* Assistant */
  const assistantForm = document.querySelector("[data-assistant-form]");
  const assistantResult = document.querySelector("[data-assistant-result]");
  if (assistantForm && assistantResult && runId) {
    assistantForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = assistantForm.querySelector('input[name="question"]');
      const question = (input || {}).value || "";
      if (!question.trim()) return;
      assistantResult.textContent = "Searching evidence...";
      try {
        const featureId = assistantForm.dataset.featureId || "";
        const payload = featureId ? { question, feature_id: featureId } : { question };
        const data = await postJson(`/api/runs/${runId}/assistant`, payload);
        assistantResult.textContent = "";
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
          heading.textContent = "Citations";
          cite.append(heading);
          data.citations.forEach((citationId) => {
            const card = document.createElement("div");
            card.className = "citation-card";
            const evidence = evidenceById[citationId];
            if (!evidence) {
              const missing = document.createElement("span");
              missing.className = "citation-missing";
              missing.textContent = `${citationId} - no embedded source record`;
              card.append(missing);
              cite.append(card);
              return;
            }
            const parts = buildEvidenceParts(evidence);
            const top = document.createElement("div");
            top.className = "citation-top";
            top.append(parts.head, parts.locator);
            card.append(top, parts.path, parts.excerpt);
            cite.append(card);
          });
          block.append(cite);
        }
        if (data.missing_evidence && data.missing_evidence.length) {
          const missing = document.createElement("div");
          missing.className = "muted";
          missing.textContent = "Would need: " + data.missing_evidence.join("; ");
          block.append(missing);
        }
        assistantResult.append(block);
      } catch (error) {
        assistantResult.textContent = error.message;
      }
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
  function updateState(container, stateText) {
    if (!container) return;
    container.querySelectorAll("[data-state]").forEach((state) => {
      state.textContent = stateText;
    });
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

    const idCell = document.createElement("td");
    const id = document.createElement("code");
    id.textContent = assumption.assumption_id;
    idCell.append(id);

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
    ownerCell.textContent = assumption.owner || "unassigned";
    const statusCell = document.createElement("td");
    statusCell.textContent = assumption.status || "open";

    row.append(idCell, statementCell, impactCell, rangeCell, questionCell, ownerCell, statusCell);
    body.append(row);
    const counter = document.querySelector('.tab[data-tab="assumptions"] .counter');
    if (counter) counter.textContent = String(body.querySelectorAll("[data-assumption-id]").length);
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
    link.textContent = "View assumption register";
    notice.append(title, label, document.createElement("br"), link);
    notice.hidden = false;
    const box = notice.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) {
      notice.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!runId) return;
      const action = button.dataset.decision;
      const objectType = button.dataset.objectType;
      const objectId = button.dataset.objectId;
      const reasons = {
        accept: "Reviewer accepted after checking the cited evidence.",
        reject: "Reviewer rejected; a replacement decision is required.",
        defer: "Reviewer deferred pending more evidence.",
        edit: "Reviewer edited the value after reviewing the evidence.",
      };
      button.disabled = true;
      try {
        const data = await postJson(`/api/runs/${runId}/decisions`, {
          object_type: objectType,
          object_id: objectId,
          action,
          reason: reasons[action] || "Reviewer decision.",
        });
        const stateText = action === "accept" ? "accepted" : action === "reject" ? "rejected" : action === "defer" ? "deferred" : "edited";
        const localContainer = button.closest("tr") || button.closest(".diff-block");
        updateState(localContainer, stateText);
        if (localContainer) {
          localContainer.classList.remove("row-accepted", "row-rejected", "row-deferred");
          localContainer.classList.add(`row-${stateText}`);
        }
        if (objectType === "finding") {
          const row = document.querySelector(`[data-finding-row="${objectId}"]`);
          updateState(row, stateText);
          updateState(document.querySelector(".detail-panel"), stateText);
          const url = new URL(window.location.href);
          url.searchParams.set("selected", objectId);
          window.history.replaceState({}, "", url);
        }
        if (objectType === "change") {
          const block = button.closest(".diff-block");
          updateState(block, stateText);
        }
        notify(`Recorded ${action} for ${objectId}.`);
        if (objectType === "mapping" && action === "reject") {
          let assumption = data.assumption || null;
          if (!assumption) assumption = await latestAssumptionFor(objectId);
          appendAssumptionRow(assumption);
          showAssumptionNotice(assumption, objectId);
        }
      } catch (error) {
        notify(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  });

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

  async function watchRun(id) {
    const waitPanel = document.querySelector("[data-run-wait]");
    if (importProgress) importProgress.hidden = false;
    if (!importProgress && !waitPanel) {
      window.location.href = `/?run=${encodeURIComponent(id)}`;
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
        window.location.href = `/?run=${encodeURIComponent(id)}`;
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
          window.location.href = `/?run=${encodeURIComponent(data.run_id)}`;
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
          window.location.href = `/?run=${encodeURIComponent(data.run_id)}`;
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
      const value = button.dataset.copy || "";
      try {
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
})();
