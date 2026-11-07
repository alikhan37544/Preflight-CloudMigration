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

  function showEvidence(evidenceId, fallbackPath) {
    if (!drawer) return;
    drawer.textContent = "";
    const evidence = evidenceById[evidenceId];
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
    const loc = evidence.locator || {};
    locator.textContent = `${loc.kind || "line"} ${loc.value || ""}${loc.line ? ":" + loc.line : ""}`;

    const excerpt = document.createElement("pre");
    excerpt.className = "evidence-excerpt";
    excerpt.textContent = evidence.excerpt || "";

    const meta = document.createElement("div");
    meta.className = "muted";
    meta.textContent = `Method: ${evidence.method || "unknown"}. Excerpt SHA-256: ${(evidence.excerpt_sha || "").slice(0, 12)}`;

    drawer.append(head, path, locator, excerpt, meta);
    drawer.scrollIntoView({ behavior: "smooth", block: "center" });
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
        const data = await postJson(`/api/runs/${runId}/assistant`, { question });
        assistantResult.textContent = "";
        const block = document.createElement("div");
        block.className = "answer-block" + (data.grounded ? "" : " refusal");
        const answer = document.createElement("p");
        answer.textContent = data.answer;
        block.append(answer);
        if (data.citations && data.citations.length) {
          const cite = document.createElement("div");
          cite.className = "muted";
          cite.textContent = "Citations: " + data.citations.join(", ");
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
        await postJson(`/api/runs/${runId}/decisions`, {
          object_type: objectType,
          object_id: objectId,
          action,
          reason: reasons[action] || "Reviewer decision.",
        });
        const row = button.closest("tr");
        const stateText = action === "accept" ? "accepted" : action === "reject" ? "rejected" : action === "defer" ? "deferred" : "edited";
        if (row) {
          const state = row.querySelector("[data-state]");
          if (state) state.textContent = stateText;
          row.classList.remove("row-accepted", "row-rejected", "row-deferred");
          row.classList.add(`row-${stateText}`);
        }
        const detailState = document.querySelector(".detail-panel [data-state]");
        if (detailState && objectType === "finding") detailState.textContent = stateText;
        notify(`Recorded ${action} for ${objectId}.`);
        if (objectType === "finding") {
          setTimeout(() => window.location.reload(), 700);
        } else if (objectType === "mapping" && action === "reject") {
          setTimeout(() => {
            window.location.href = `/reconstruction?run=${encodeURIComponent(runId)}&tab=assumptions`;
          }, 900);
        }
      } catch (error) {
        notify(error.message, true);
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
    if (!importProgress && !waitPanel) return;
    const bar = importBar || document.querySelector("[data-run-bar]");
    const label = importLabel || document.querySelector("[data-run-label]");
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      let status;
      try {
        status = await pollRun(id);
      } catch (error) {
        if (label) label.textContent = error.message;
        return;
      }
      const percent = (status.progress && status.progress.percent) || 0;
      if (bar) bar.value = Math.max(2, percent);
      if (label) label.textContent = `${status.stage} - ${Math.round(percent)}%`;
      if (status.status === "succeeded") {
        window.location.href = `/?run=${encodeURIComponent(id)}`;
        return;
      }
      if (status.status === "failed" || status.status === "cancelled") {
        if (label) label.textContent = `Run ${status.status}. See run history.`;
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    if (label) label.textContent = "Run is taking longer than expected. Open run history.";
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
