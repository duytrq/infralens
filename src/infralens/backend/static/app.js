"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const active = (run) => run && ["queued", "running"].includes(run.status);
  const statuses = {queued:"Đang chờ",running:"Đang chạy",succeeded:"Hoàn tất",failed:"Lỗi",cancelled:"Đã hủy",interrupted:"Gián đoạn"};
  const gateStatuses = {passed:"Gate đạt",failed:"Gate chặn",incomplete:"Gate chưa kết luận"};
  const comparisons = {new:"Mới",no_longer_reported:"Không còn được báo cáo",changed:"Đã thay đổi",unchanged:"Giữ nguyên",indeterminate:"Chưa xác định"};
  let token = "", projects = [], epoch = 0, selection = 0, selected = null, report = null;
  let pageBefore = null, nextBefore = null, timer = null, polling = false, submitting = false;
  let historyKey = "";
  let plan = null, fileVersion = 0, attempt = null;
  const requests = new Set();
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function badge(text, kind) { return node("span", text, `badge ${kind || ""}`); }
  function notice(message = "") { $("notice").textContent = message; $("notice").hidden = !message; }
  function resetDetail() {
    selection++; selected = null; report = null;
    $("detail-title").textContent = "Chọn một lượt kiểm tra";
    $("run-meta").textContent = "";
    $("report").hidden = true; $("resources").replaceChildren();
    $("report-notes").replaceChildren(); $("comparison-content").replaceChildren();
    $("gate-result").replaceChildren();
    $("run-state").hidden = false;
    $("run-state").textContent = "Chọn “Xem” để đọc báo cáo và so sánh với lượt trước.";
    $("cancel-run").hidden = true; $("download").disabled = true;
    for (const id of ["resources", "high", "medium", "unknown"]) $("stat-" + id).textContent = "—";
  }
  function disconnect(message = "") {
    epoch++; token = ""; projects = []; plan = null; attempt = null; fileVersion++;
    clearInterval(timer); timer = null;
    for (const controller of requests) controller.abort();
    requests.clear(); resetDetail(); historyKey = "";
    $("token").value = ""; $("plan-file").value = "";
    $("project-context").textContent = ""; $("plan-label").textContent = "Chưa chọn plan.";
    $("history-body").replaceChildren(); $("project").replaceChildren();
    $("session").hidden = true; $("workspace").hidden = true;
    $("connect-form").hidden = false; $("welcome").hidden = false;
    notice(message);
  }
  async function api(path, options = {}) {
    const controller = new AbortController(); requests.add(controller);
    try {
      const response = await fetch(path, {...options, signal:controller.signal, cache:"no-store", credentials:"omit",
        headers:{"Authorization":`Bearer ${token}`, ...(options.body ? {"Content-Type":"application/json"} : {}), ...options.headers}});
      const data = await response.json();
      if (response.status === 401) { disconnect("Token không hợp lệ hoặc đã thay đổi. Hãy kết nối lại."); throw new DOMException("Session ended", "AbortError"); }
      if (!response.ok) throw new Error(`${data.error?.message || "Yêu cầu thất bại"} (${data.error?.code || response.status})`);
      return data;
    } finally { requests.delete(controller); }
  }
  function error(error) { if (error.name !== "AbortError") notice(error.message || "Không thể kết nối backend."); }
  async function health() {
    try {
      const response = await fetch("/health", {cache:"no-store", credentials:"omit"});
      const data = await response.json();
      const ok = response.ok && data.status === "ok";
      $("health-dot").classList.toggle("online", ok);
      $("health").textContent = ok ? "Backend đang hoạt động" : "Worker cần được kiểm tra";
    } catch { $("health-dot").classList.remove("online"); $("health").textContent = "Backend mất kết nối"; }
  }
  function project() { return projects.find((p) => p.id === $("project").value); }
  function updateMode() {
    $("import-fields").hidden = $("mode").value !== "import";
    $("trace-fields").hidden = !$("trace").checked;
    $("lookback").disabled = !$("trace").checked;
  }
  function configureProject() {
    const p = project();
    resetDetail(); pageBefore = null; nextBefore = null; attempt = null; historyKey = "";
    plan = null; fileVersion++; $("plan-file").value = ""; $("plan-label").textContent = "Chưa chọn plan.";
    $("resource-filter").value = "";
    $("history-body").replaceChildren(); $("older").disabled = true;
    $("submit-run").disabled = !p || (!p.allow_refresh && !p.allow_import) || submitting;
    if (!p) { $("project-context").textContent = "Chưa có dự án được đăng ký."; return; }
    $("project-context").textContent = `Workspace: ${p.workspace} · tối đa ${p.max_timeout}s mỗi phase`;
    for (const option of $("mode").options) option.disabled = !p["allow_" + option.value];
    $("mode").value = p.allow_refresh ? "refresh" : "import";
    $("trace").checked = false; $("trace").disabled = !p.allow_trace;
    $("gate-priority").value = "off"; $("gate-unknown").checked = false;
    $("timeout").max = p.max_timeout; $("timeout").value = Math.min(120, p.max_timeout);
    updateMode(); notice();
  }
  function time(value) { return value ? new Date(value).toLocaleString("vi-VN") : "—"; }
  async function history() {
    const p = project(); if (!p || !token) return;
    const stamp = epoch, projectId = p.id, cursor = pageBefore, filter = $("status-filter").value, gateFilter = $("gate-status-filter").value;
    const query = new URLSearchParams({limit:"20"});
    if (cursor) query.set("before", cursor);
    if (filter) query.set("status", filter);
    if (gateFilter) query.set("gate_status", gateFilter);
    const data = await api(`/api/v1/projects/${encodeURIComponent(projectId)}/runs?${query}`);
    if (stamp !== epoch || project()?.id !== projectId || pageBefore !== cursor || $("status-filter").value !== filter || $("gate-status-filter").value !== gateFilter) return;
    nextBefore = data.next_before; $("older").disabled = nextBefore === null;
    $("history-note").textContent = cursor ? "Trang lịch sử cũ · Làm mới để về lượt gần nhất" : "20 lượt mỗi trang · tự cập nhật mỗi 3 giây";
    const key = JSON.stringify([data, selected?.id]);
    if (historyKey === key) return;
    historyKey = key;
    const rows = data.items.map((run) => {
      const row = node("tr", null, run.id === selected?.id ? "selected" : "");
      const identity = node("td"); identity.append(node("strong", `#${run.sequence} · ${run.id.slice(0, 8)}`), node("small", time(run.created_at)));
      const mode = node("td", run.mode === "import" ? "Plan import" : "Refresh");
      const status = node("td"); status.append(badge(statuses[run.status] || run.status, run.status));
      const result = node("td", run.has_drift === null ? "—" : run.has_drift ? "Có drift" : "Không ghi nhận drift");
      const gate = node("td");
      if (run.gate) gate.append(badge(gateStatuses[run.gate.status] || run.gate.status, "gate-" + run.gate.status));
      else gate.textContent = run.request.gate ? (active(run) ? "Đang chờ kết quả" : "Chưa đánh giá") : "Không bật";
      const action = node("td"), view = node("button", "Xem →", "text-button");
      view.type = "button"; view.setAttribute("aria-label", `Xem lượt #${run.sequence}`);
      view.addEventListener("click", () => inspect(run.id).catch(error)); action.append(view);
      row.append(identity, mode, status, result, gate, action); return row;
    });
    if (!rows.length) { const row = node("tr"), cell = node("td", "Chưa có lượt kiểm tra phù hợp.", "empty"); cell.colSpan = 6; row.append(cell); rows.push(row); }
    $("history-body").replaceChildren(...rows);
  }
  function valueText(value) {
    const labels = {sensitive:"[Đã ẩn: sensitive]",unknown:"[Chưa biết]",absent:"[Không có thuộc tính]",null:"null"};
    return value?.status === "known" ? JSON.stringify(value.value, null, 2) : labels[value?.status] || `[${value?.status || "Chưa biết"}]`;
  }
  function renderResources() {
    const filter = $("resource-filter").value.trim().toLowerCase();
    const resources = (report?.resources || []).filter((r) => r.address.toLowerCase().includes(filter));
    $("resources").replaceChildren(...resources.map((r) => {
      const card = node("article", null, "resource"), head = node("div", null, "resource-head"), title = node("div");
      title.append(node("h3", r.address), node("p", `${r.resource_type} · ${r.actions.join(", ")}`));
      head.append(title, badge(({high:"Ưu tiên cao",medium:"Trung bình",unknown:"Cần ngữ cảnh"})[r.assessment?.priority] || "Cần ngữ cảnh", r.assessment?.priority || "unknown"));
      const body = node("div", null, "resource-body");
      if (r.source) {
        body.append(node("p", `Source: ${r.source.status}${r.source.reason ? " · " + r.source.reason : ""}`, "source"));
        for (const location of r.source.locations || []) body.append(node("p", `${location.file}:${location.start_line}–${location.end_line} · cấu hình hiện tại`, "source"));
      }
      for (const [name, identity] of Object.entries(r.identifiers || {})) body.append(node("p", `${name}: ${valueText(identity)}${identity.source ? " · " + identity.source : ""}`, "source"));
      if (r.network_context) {
        const context = node("details"); context.append(node("summary", "Ngữ cảnh rule · gồm thuộc tính không đổi"));
        for (const [name, before] of Object.entries(r.network_context.before || {})) {
          const after = r.network_context.after?.[name];
          if (before.status === "absent" && after?.status === "absent") continue;
          const row = node("div", null, "delta"), values = node("div", null, "values");
          row.append(node("div", name, "delta-path"));
          for (const [label, value] of [["SAVED STATE", before], ["OBSERVED", after]]) {
            const column = node("div"); column.append(node("div", label, "value-label"), node("pre", valueText(value))); values.append(column);
          }
          row.append(values); context.append(row);
        }
        body.append(context);
      }
      for (const change of r.attributes || []) {
        const delta = node("div", null, "delta"), values = node("div", null, "values");
        delta.append(node("div", JSON.stringify(change.path), "delta-path"));
        for (const [label, value] of [["SAVED STATE", change.before], ["OBSERVED", change.after]]) {
          const column = node("div"); column.append(node("div", label, "value-label"), node("pre", valueText(value))); values.append(column);
        }
        delta.append(values); body.append(delta);
      }
      if (!r.attributes?.length) body.append(node("p", "Resource thay đổi; không có chênh lệch thuộc tính hiển thị.", "muted"));
      if (r.assessment) {
        const details = node("details"); details.append(node("summary", "Tín hiệu & hướng dẫn review"));
        const signals = node("ul"); for (const signal of r.assessment.signals || []) signals.append(node("li", signal.description)); details.append(signals);
        const steps = node("ul"); for (const step of r.assessment.guidance?.review_steps || []) steps.append(node("li", step)); details.append(steps);
        for (const choice of r.assessment.guidance?.choices || []) { details.append(node("p", choice.title)); const list = node("ul"); for (const step of choice.steps || []) list.append(node("li", step)); details.append(list); }
        body.append(details);
      }
      if (r.trace) {
        const details = node("details"); details.append(node("summary", `CloudTrail · ${r.trace.status}`));
        details.append(node("p", "Event là ứng viên liên quan, chưa chứng minh nguyên nhân gây drift."));
        if (r.trace.correlation === "exact_rule_id") details.append(node("p", `Tra lịch sử Security Group cha, đối chiếu đúng rule ID. Sự kiện chưa xác định được rule: ${r.trace.unresolved_rule_events}.`));
        if (r.trace.reason) details.append(node("p", r.trace.reason));
        for (const event of r.trace.events || []) details.append(node("p", `${time(event.event_time)} · ${event.event_name} · ${JSON.stringify(event.actor)} · ${event.event_id}`));
        body.append(details);
      }
      card.append(head, body); return card;
    }));
    if (!resources.length) $("resources").append(node("div", report?.resources?.length ? "Không có resource khớp bộ lọc." : "Không ghi nhận managed resource drift trong plan này.", "empty"));
  }
  function renderReport(data) {
    report = data; $("report").hidden = false; $("run-state").hidden = true; $("download").disabled = false;
    $("stat-resources").textContent = data.resources.length;
    for (const priority of ["high", "medium", "unknown"]) $("stat-" + priority).textContent = data.review_summary?.priority_counts?.[priority] ?? (data.resources.length ? "—" : 0);
    const notes = ["So sánh Terraform saved state với giá trị provider quan sát được. Ưu tiên review là gợi ý theo rule, cần đối chiếu ý định cấu hình."];
    if (selected.mode === "import") notes.unshift("PLAN IMPORT · Độ mới và độ phủ của plan chưa được xác minh.");
    if (selected.error_code) notes.unshift(`Lượt kết thúc với lỗi ${selected.error_code}; báo cáo có thể chưa đầy đủ.`);
    if (data.trace) notes.push(`CloudTrail: ${data.trace.status}${data.trace.message ? " · " + data.trace.message : ""}`);
    for (const normalization of data.normalizations || []) notes.push(`Normalized ${normalization.address} ${JSON.stringify(normalization.path)}: ${normalization.reason}`);
    $("report-notes").replaceChildren(...notes.map((n) => node("p", n)));
    renderGate(data.gate);
    if (data.notes?.length) {
      const details = node("details"); details.append(node("summary", `Phạm vi & lưu ý từ engine (${data.notes.length})`));
      for (const note of data.notes) details.append(node("p", note));
      $("report-notes").append(details);
    }
    renderResources();
  }
  function renderGate(gate) {
    const root = $("gate-result"); root.replaceChildren();
    if (!gate) { root.append(node("p", "Gate không bật cho lượt này.", "muted")); return; }
    const box = node("section", null, "gate-result " + gate.status);
    box.append(badge(gateStatuses[gate.status] || gate.status, "gate-" + gate.status));
    const criteria = gate.criteria, labels = [];
    if (criteria.any_drift) labels.push("bất kỳ drift");
    if (criteria.minimum_priority) labels.push(criteria.minimum_priority === "high" ? "ưu tiên cao" : "từ trung bình trở lên");
    if (criteria.unknown_priority) labels.push("chưa đủ ngữ cảnh");
    box.append(node("p", `Điều kiện chặn (HOẶC): ${labels.join(" · ")} · ${gate.matched_count} resource khớp · exit ${gate.exit_code}`));
    box.append(node("p", gate.status === "incomplete" ? "Tra cứu CloudTrail chưa đầy đủ; gate chưa thể kết luận." : "Kết quả gate độc lập với trạng thái thực thi. Gate đạt vẫn có thể có drift ngoài điều kiện đã chọn."));
    if (gate.matched_resources.length) {
      const details = node("details"), list = node("ul"); details.append(node("summary", "Resource khớp điều kiện chặn"));
      for (const match of gate.matched_resources) list.append(node("li", `${match.address} · ${match.priority} · ${match.reasons.join(", ")}`));
      details.append(list); box.append(details);
    }
    root.append(box);
  }
  function renderComparison(data) {
    const root = $("comparison-content"); root.replaceChildren();
    if (data.status === "baseline_missing") root.append(node("p", "Chưa có lượt thành công trước đó cùng project, mode và scope để so sánh.", "muted"));
    else {
      root.append(node("p", `Baseline ${data.baseline_run_id.slice(0, 8)} → ${data.current_run_id.slice(0, 8)}`, "muted"));
      const counts = node("div", null, "comparison-counts");
      for (const [key, label] of Object.entries(comparisons)) counts.append(badge(`${label}: ${data.summary[key] || 0}`, key));
      root.append(counts);
      for (const resource of data.resources) {
        const row = node("div", null, "comparison-row"); row.append(badge(comparisons[resource.status] || resource.status, resource.status), node("span", resource.address));
        if (resource.changed_paths?.length) row.append(node("div", `Paths: ${JSON.stringify(resource.changed_paths)}`, "muted")); root.append(row);
      }
    }
    for (const note of data.notes || []) root.append(node("p", note, "muted"));
    root.append(node("p", "“Không còn được báo cáo” chưa chứng nhận hạ tầng đã được sửa. Sensitive/unknown có thể khiến so sánh chưa xác định.", "muted"));
  }
  async function inspect(identity, poll = false) {
    const stamp = epoch, ticket = poll ? selection : ++selection;
    if (!poll) { selected = {id:identity}; report = null; $("resource-filter").value = ""; $("report").hidden = true; $("run-state").hidden = false; $("run-state").textContent = "Đang tải lượt kiểm tra…"; $("download").disabled = true; $("cancel-run").hidden = true; for (const id of ["resources","high","medium","unknown"]) $("stat-" + id).textContent = "—"; }
    const run = await api(`/api/v1/runs/${identity}`);
    if (stamp !== epoch || ticket !== selection) return;
    selected = run; $("detail-title").textContent = `Lượt #${run.sequence} · ${statuses[run.status] || run.status}`;
    $("run-meta").textContent = `${run.mode} · ${time(run.created_at)} · ${run.id}`;
    $("cancel-run").hidden = !active(run); $("cancel-run").disabled = run.cancel_requested;
    $("cancel-run").textContent = run.cancel_requested ? "Đang yêu cầu hủy…" : "Hủy lượt này";
    if (!run.has_report) { $("run-state").textContent = active(run) ? "Worker đang xử lý. Trang sẽ tự cập nhật khi có báo cáo." : `Không có báo cáo. ${run.error_code || statuses[run.status] || run.status}`; return; }
    const data = await api(`/api/v1/runs/${identity}/report`);
    if (stamp !== epoch || ticket !== selection) return;
    renderReport(data);
    if (run.status !== "succeeded") { $("comparison-content").replaceChildren(node("p", "Comparison yêu cầu lượt đã hoàn tất thành công.", "muted")); return; }
    $("comparison-content").replaceChildren(node("p", "Đang tải so sánh…", "muted"));
    try {
      const comparison = await api(`/api/v1/runs/${identity}/comparison`);
      if (stamp === epoch && ticket === selection) renderComparison(comparison);
    } catch (e) { if (stamp === epoch && ticket === selection && e.name !== "AbortError") $("comparison-content").replaceChildren(node("p", e.message, "muted")); }
  }
  async function tick() {
    if (polling || !token) return;
    polling = true;
    try { await history(); if (active(selected)) await inspect(selected.id, true); }
    catch (e) { error(e); } finally { polling = false; }
  }
  $("connect-form").addEventListener("submit", async (event) => {
    event.preventDefault(); $("connect").disabled = true; notice();
    token = $("token").value.trim(); $("token").value = "";
    const stamp = ++epoch;
    try {
      const data = await api("/api/v1/projects"); if (stamp !== epoch) return;
      projects = data.items; $("project").replaceChildren(...projects.map((p) => { const option = node("option", p.name); option.value = p.id; return option; }));
      $("connect-form").hidden = true; $("welcome").hidden = true; $("session").hidden = false; $("workspace").hidden = false;
      configureProject(); await history(); clearInterval(timer); timer = setInterval(tick, 3000);
    } catch (e) { if (stamp === epoch) disconnect(e.message || "Không thể kết nối backend."); }
    finally { $("connect").disabled = false; }
  });
  $("disconnect").addEventListener("click", () => disconnect("Đã ngắt kết nối và xóa token khỏi phiên tab."));
  $("project").addEventListener("change", () => { epoch++; configureProject(); history().catch(error); });
  $("mode").addEventListener("change", updateMode); $("trace").addEventListener("change", updateMode);
  $("plan-file").addEventListener("change", async () => {
    const file = $("plan-file").files[0], version = ++fileVersion; plan = null;
    $("plan-label").textContent = "Chưa chọn plan.";
    if (!file) return;
    try {
      if (file.size > 1900000) throw new Error("Plan vượt giới hạn giao diện 1,9 MB. Dùng CLI cho file lớn hơn.");
      const text = await file.text(); if (version !== fileVersion) return;
      plan = JSON.parse(text); $("plan-label").textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    } catch (e) { if (version === fileVersion) { plan = null; $("plan-label").textContent = "File JSON không hợp lệ hoặc quá lớn."; notice(e instanceof SyntaxError ? "Không đọc được JSON. Kiểm tra định dạng file Terraform plan." : e.message); } }
  });
  $("example").addEventListener("click", async () => {
    const version = ++fileVersion;
    try { const response = await fetch("/dashboard/demo-plan.json", {cache:"no-store"}); if (!response.ok) throw new Error("Không tải được plan ví dụ."); const data = await response.json(); if (version !== fileVersion || !token) return; plan = data; $("plan-file").value = ""; $("plan-label").textContent = "Ví dụ giả lập · 4 resource có drift · không gọi AWS"; notice(); }
    catch (e) { error(e); }
  });
  $("run-form").addEventListener("submit", async (event) => {
    event.preventDefault(); if (submitting || !project()) return;
    const p = project(), stamp = epoch, mode = $("mode").value;
    if (mode === "import" && (!plan || typeof plan !== "object" || Array.isArray(plan))) { notice("Hãy chọn Terraform plan JSON hoặc nạp ví dụ trước khi tạo lượt."); return; }
    const payload = {mode, timeout:Number($("timeout").value), trace:$("trace").checked, lookback_days:Number($("lookback").value)};
    const threshold = $("gate-priority").value, unknown = $("gate-unknown").checked;
    if (threshold !== "off" || unknown) payload.gate = {any_drift:threshold === "any", minimum_priority:["high", "medium"].includes(threshold) ? threshold : null, unknown_priority:unknown};
    if (mode === "import") payload.plan = plan;
    const body = JSON.stringify(payload), fingerprint = p.id + body;
    if (!attempt || attempt.fingerprint !== fingerprint) attempt = {fingerprint, key:crypto.randomUUID()};
    submitting = true; $("submit-run").disabled = true; notice();
    try {
      const data = await api(`/api/v1/projects/${encodeURIComponent(p.id)}/runs`, {method:"POST", body, headers:{"Idempotency-Key":attempt.key}});
      if (stamp !== epoch) return;
      if (project()?.id !== p.id) { notice("Lượt đã được tạo cho dự án trước đó; chọn lại dự án để xem."); return; }
      pageBefore = null; $("status-filter").value = ""; $("gate-status-filter").value = "";
      await inspect(data.run.id); await history();
      if (stamp !== epoch) return;
      attempt = null; notice(`${data.created ? "Đã tạo" : "Đã nhận lại"} lượt #${data.run.sequence}.`);
    } catch (e) { error(e); } finally { submitting = false; const current = project(); $("submit-run").disabled = !current || (!current.allow_import && !current.allow_refresh); }
  });
  $("cancel-run").addEventListener("click", async () => {
    if (!active(selected)) return; const id = selected.id, stamp = epoch;
    $("cancel-run").disabled = true;
    try { await api(`/api/v1/runs/${id}/cancel`, {method:"POST"}); if (stamp === epoch && selected?.id === id) await inspect(id, true); await history(); }
    catch (e) { error(e); if (stamp === epoch && selected?.id === id) $("cancel-run").disabled = false; }
  });
  for (const id of ["status-filter", "gate-status-filter"]) $(id).addEventListener("change", () => { pageBefore = null; nextBefore = null; $("older").disabled = true; history().catch(error); });
  $("refresh-history").addEventListener("click", () => { pageBefore = null; notice(); history().catch(error); health(); });
  $("older").addEventListener("click", () => { if (nextBefore !== null) { pageBefore = nextBefore; history().catch(error); } });
  $("resource-filter").addEventListener("input", renderResources);
  $("download").addEventListener("click", () => {
    if (!report || !selected) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], {type:"application/json"}));
    const link = node("a"); link.href = url; link.download = `infralens-${selected.id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  health();
})();
