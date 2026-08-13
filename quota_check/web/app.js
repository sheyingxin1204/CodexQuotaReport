(function () {
  "use strict";

  var state = {
    data: null,
    view: "cards",
    search: "",
    planFilter: "",
    statusFilter: "",
    sort: "email",
    pollTimer: null
  };

  var severityText = {
    ok: "正常",
    warning: "预警",
    critical: "危险",
    no_data: "无数据",
    error: "异常"
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined) {
      node.textContent = text;
    }
    return node;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtPercent(value) {
    if (value === null || value === undefined) {
      return "--";
    }
    return String(Math.round(value * 10) / 10) + "%";
  }

  function fmtWindow(minutes) {
    if (!minutes) {
      return "";
    }
    if (minutes === 300) {
      return "5小时";
    }
    var days = minutes / 1440;
    if (Number.isInteger(days)) {
      return days + "天";
    }
    var hours = minutes / 60;
    if (Number.isInteger(hours)) {
      return hours + "小时";
    }
    return minutes + "分钟";
  }

  function fmtTime(iso) {
    if (!iso) {
      return "未知";
    }
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return "未知";
    }
    function pad(value) {
      return String(value).padStart(2, "0");
    }
    return (
      date.getFullYear() +
      "-" +
      pad(date.getMonth() + 1) +
      "-" +
      pad(date.getDate()) +
      " " +
      pad(date.getHours()) +
      ":" +
      pad(date.getMinutes())
    );
  }

  function fmtReset(unix) {
    if (!unix) {
      return "未知";
    }
    return fmtTime(new Date(unix * 1000).toISOString());
  }

  function showToast(message, isError) {
    var toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    toast.style.background = isError ? "#991b1b" : "";
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(function () {
      toast.classList.add("hidden");
    }, 3200);
  }

  function authIcon() {
    var span = document.createElement("span");
    span.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>' +
      '<path d="M14 2v6h6"/>' +
      '<path d="M12 18v-6"/>' +
      '<path d="m9 15 3 3 3-3"/>' +
      "</svg>";
    return span;
  }

  function makeAuthButton(codeHome) {
    var button = el("button", "auth-link");
    button.type = "button";
    button.title = "打开此账号的 auth.json";
    button.appendChild(authIcon());
    button.appendChild(document.createTextNode("auth.json"));
    button.addEventListener("click", function () {
      openAuthFile(codeHome);
    });
    return button;
  }

  function openAuthFile(codeHome) {
    fetch("/api/open-auth?code_home=" + encodeURIComponent(codeHome))
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (data.ok) {
          showToast("已用默认程序打开 auth.json");
        } else {
          showToast(data.error || "无法打开 auth.json", true);
        }
      })
      .catch(function () {
        showToast("请求失败，无法打开 auth.json", true);
      });
  }

  function gaugeColor(value) {
    if (value === null || value === undefined) {
      return "#94a3b8";
    }
    if (value <= 10) {
      return "#dc2626";
    }
    if (value <= 30) {
      return "#d97706";
    }
    return "#16a34a";
  }

  function planClass(plan) {
    plan = String(plan || "").toLowerCase();
    if (plan === "free") {
      return "free";
    }
    if (plan === "api" || plan.indexOf("api") >= 0) {
      return "api";
    }
    return "";
  }

  function buildGauge(limit, label, sub) {
    var block = el("div", "gauge-block");
    var percent = limit && limit.remaining_percent !== null && limit.remaining_percent !== undefined
      ? Math.max(0, Math.min(100, limit.remaining_percent))
      : 0;
    var color = gaugeColor(limit ? limit.remaining_percent : null);
    var gauge = el("div", "gauge");
    gauge.style.setProperty("--p", String(percent));
    gauge.style.setProperty("--gauge-color", color);
    var inner = el("div", "gauge-inner", fmtPercent(limit ? limit.remaining_percent : null));
    inner.style.color = color;
    gauge.appendChild(inner);
    block.appendChild(gauge);
    block.appendChild(el("div", "gauge-label", label));
    block.appendChild(el("div", "gauge-sub", sub || ""));
    return block;
  }

  function detail(label, value) {
    var node = el("div", "detail");
    node.appendChild(el("div", "detail-label", label));
    node.appendChild(el("div", "detail-value", value || "未知"));
    return node;
  }

  function renderCard(account, aliasMap) {
    var card = el("article", "account-card sev-" + account.severity);

    var head = el("div", "card-head");
    var title = el("div", "card-title");
    title.appendChild(el("h3", "", account.label));
    title.appendChild(el("div", "email", account.email || "未登录"));
    head.appendChild(title);

    var meta = el("div", "card-meta");
    meta.appendChild(el("span", "plan-badge " + planClass(account.plan_type), account.plan_type || "未知"));
    meta.appendChild(el("span", "status-dot"));
    head.appendChild(meta);
    card.appendChild(head);

    var gauges = el("div", "gauges");
    var weeklyWindow = account.weekly ? fmtWindow(account.weekly.window_minutes) : "无";
    var fiveHourWindow = account.five_hour ? fmtWindow(account.five_hour.window_minutes) : "无";
    gauges.appendChild(
      buildGauge(
        account.weekly,
        "主额度 · " + weeklyWindow,
        account.weekly && account.weekly.resets_at_unix
          ? "重置 " + fmtReset(account.weekly.resets_at_unix)
          : ""
      )
    );
    gauges.appendChild(
      buildGauge(
        account.five_hour,
        "5小时额度",
        account.five_hour && account.five_hour.resets_at_unix
          ? "重置 " + fmtReset(account.five_hour.resets_at_unix)
          : "该套餐无此窗口"
      )
    );
    card.appendChild(gauges);

    var details = el("div", "card-details");
    var alias = aliasMap[account.code_home] || "";
    details.appendChild(detail("快捷方式", alias || account.label));
    details.appendChild(detail("套餐", account.plan_type || "未知"));
    details.appendChild(detail("更新时间", fmtTime(account.snapshot_at_utc)));
    details.appendChild(
      detail(
        "累计 tokens",
        account.total_tokens !== null && account.total_tokens !== undefined
          ? account.total_tokens.toLocaleString()
          : "未知"
      )
    );
    card.appendChild(details);
    var actionRow = el("div", "card-action");
    actionRow.appendChild(makeAuthButton(account.code_home));
    card.appendChild(actionRow);

    if (account.error) {
      card.appendChild(el("div", "error-box", account.error));
    }
    if (account.source_path) {
      var source = el("div", "muted");
      source.style.cssText = "font-size:11px;word-break:break-all;";
      source.textContent = account.source_path;
      card.appendChild(source);
    }
    return card;
  }

  function renderTable(accounts, aliasMap) {
    var wrapper = el("div", "table-view");
    var table = el("table");
    var thead = el("thead");
    var headRow = el("tr");
    ["邮箱", "快捷方式", "套餐", "主额度", "主额度重置", "5小时", "5小时重置", "更新时间", "状态", "操作"].forEach(function (label) {
      headRow.appendChild(el("th", "", label));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = el("tbody");
    accounts.forEach(function (account) {
      var row = el("tr");
      var emailCell = el("td", "email-cell", account.email || "未登录");
      row.appendChild(emailCell);
      row.appendChild(el("td", "", aliasMap[account.code_home] || account.label));
      row.appendChild(el("td", "", account.plan_type || "未知"));
      row.appendChild(
        el(
          "td",
          "",
          account.weekly
            ? fmtPercent(account.weekly.remaining_percent) +
              " · " +
              fmtWindow(account.weekly.window_minutes)
            : "-"
        )
      );
      row.appendChild(
        el(
          "td",
          "",
          account.weekly && account.weekly.resets_at_unix
            ? fmtReset(account.weekly.resets_at_unix)
            : "-"
        )
      );
      row.appendChild(
        el(
          "td",
          "",
          account.five_hour
            ? fmtPercent(account.five_hour.remaining_percent) +
              " · " +
              fmtWindow(account.five_hour.window_minutes)
            : "-"
        )
      );
      row.appendChild(
        el(
          "td",
          "",
          account.five_hour && account.five_hour.resets_at_unix
            ? fmtReset(account.five_hour.resets_at_unix)
            : "-"
        )
      );
      row.appendChild(el("td", "", fmtTime(account.snapshot_at_utc)));
      var statusCell = el("td", "", severityText[account.severity] || account.status);
      statusCell.style.color = gaugeColor(
        account.severity === "ok"
          ? 50
          : account.severity === "warning"
            ? 20
            : account.severity === "critical"
              ? 5
              : null
      );
      row.appendChild(statusCell);
      var actionCell = el("td", "actions-cell");
      actionCell.appendChild(makeAuthButton(account.code_home));
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    wrapper.appendChild(table);
    return wrapper;
  }

  function filteredAccounts() {
    var report = state.data && state.data.report;
    if (!report) {
      return [];
    }
    var query = state.search.trim().toLowerCase();
    var aliasMap = {};
    (report.candidates || []).forEach(function (candidate) {
      aliasMap[candidate.code_home] = candidate.alias || "";
    });
    var accounts = report.accounts.filter(function (account) {
      if (state.planFilter && account.plan_type !== state.planFilter) {
        return false;
      }
      if (state.statusFilter && account.severity !== state.statusFilter) {
        return false;
      }
      if (query) {
        var haystack = [
          account.email,
          account.label,
          account.code_home,
          aliasMap[account.code_home]
        ]
          .join(" ")
          .toLowerCase();
        if (haystack.indexOf(query) < 0) {
          return false;
        }
      }
      return true;
    });

    function minRemaining(account) {
      var values = [];
      if (account.weekly && account.weekly.remaining_percent !== null) {
        values.push(account.weekly.remaining_percent);
      }
      if (account.five_hour && account.five_hour.remaining_percent !== null) {
        values.push(account.five_hour.remaining_percent);
      }
      return values.length ? Math.min.apply(null, values) : null;
    }

    accounts.sort(function (a, b) {
      if (state.sort === "remaining") {
        var ra = minRemaining(a);
        var rb = minRemaining(b);
        if (ra === null) {
          return 1;
        }
        if (rb === null) {
          return -1;
        }
        return ra - rb;
      }
      if (state.sort === "plan") {
        return String(a.plan_type).localeCompare(String(b.plan_type));
      }
      if (state.sort === "updated") {
        return String(b.snapshot_at_utc || "").localeCompare(String(a.snapshot_at_utc || ""));
      }
      return String(a.email || a.label).localeCompare(String(b.email || b.label));
    });
    return accounts;
  }

  function renderSummary(accounts) {
    var counts = { ok: 0, warning: 0, critical: 0, no_data: 0, error: 0 };
    accounts.forEach(function (account) {
      counts[account.severity] = (counts[account.severity] || 0) + 1;
    });
    var total = accounts.length;
    var container = document.getElementById("summary");
    container.textContent = "";
    var items = [
      ["总数", total, ""],
      ["正常", counts.ok, "sev-ok"],
      ["预警", counts.warning, "sev-warning"],
      ["危险", counts.critical, "sev-critical"],
      ["无数据/异常", counts.no_data + counts.error, "sev-no_data"]
    ];
    items.forEach(function (item) {
      var stat = el("div", "stat " + item[2]);
      stat.appendChild(el("div", "stat-label", item[0]));
      stat.appendChild(el("div", "stat-value", String(item[1])));
      container.appendChild(stat);
    });
  }

  function renderAccounts() {
    var report = state.data && state.data.report;
    var accounts = filteredAccounts();
    var aliasMap = {};
    (report && report.candidates || []).forEach(function (candidate) {
      aliasMap[candidate.code_home] = candidate.alias || "";
    });

    var container = document.getElementById("accounts");
    container.textContent = "";
    if (!report) {
      container.appendChild(el("div", "empty", "正在扫描本地 Codex 账号，首次加载可能需要一点时间..."));
      return;
    }
    if (!accounts.length) {
      container.appendChild(el("div", "empty", "没有符合筛选条件的账号"));
      return;
    }
    container.className = "cards";
    if (state.view === "cards") {
      accounts.forEach(function (account) {
        container.appendChild(renderCard(account, aliasMap));
      });
    } else {
      container.appendChild(renderTable(accounts, aliasMap));
    }
  }

  function renderHeaderAndProgress() {
    var data = state.data;
    if (!data) {
      return;
    }
    document.getElementById("versionLine").textContent =
      "v" + data.version + " · " + (data.codex_path ? "codex CLI 已找到" : "codex CLI 未找到");
    document.getElementById("lastUpdated").textContent = data.refreshed_at
      ? "更新于 " + fmtTime(data.refreshed_at)
      : "尚未生成报告";
    document.getElementById("codexPath").textContent = data.codex_path
      ? "codex: " + data.codex_path
      : "codex CLI 未找到，仅读取历史会话数据";

    var progress = document.getElementById("progressPanel");
    if (data.refreshing) {
      progress.classList.remove("hidden");
      var last = data.progress_log[data.progress_log.length - 1] || "正在加载...";
      document.getElementById("progressText").textContent = last;
      document.getElementById("refreshBtn").disabled = true;
    } else {
      progress.classList.add("hidden");
      document.getElementById("refreshBtn").disabled = false;
    }
  }

  function render() {
    var data = state.data;
    var accounts = (data && data.report ? data.report.accounts : []).slice();
    renderSummary(accounts);
    renderAccounts();
    renderHeaderAndProgress();
  }

  function fetchState() {
    return fetch("/api/state")
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        state.data = data;
        render();
        updatePolling();
        return data;
      })
      .catch(function () {
        // 服务刚启动时可能还没就绪，下一次轮询会重试
      });
  }

  function updatePolling() {
    var shouldPoll = state.data && state.data.refreshing;
    if (shouldPoll && !state.pollTimer) {
      state.pollTimer = setInterval(fetchState, 1500);
    }
    if (!shouldPoll && state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function wireToolbar() {
    document.getElementById("searchInput").addEventListener("input", function (event) {
      state.search = event.target.value;
      renderAccounts();
    });
    document.getElementById("planFilter").addEventListener("change", function (event) {
      state.planFilter = event.target.value;
      renderAccounts();
    });
    document.getElementById("statusFilter").addEventListener("change", function (event) {
      state.statusFilter = event.target.value;
      renderAccounts();
    });
    document.getElementById("sortSelect").addEventListener("change", function (event) {
      state.sort = event.target.value;
      renderAccounts();
    });
    document.getElementById("viewCards").addEventListener("click", function () {
      state.view = "cards";
      document.getElementById("viewCards").classList.add("active");
      document.getElementById("viewTable").classList.remove("active");
      renderAccounts();
    });
    document.getElementById("viewTable").addEventListener("click", function () {
      state.view = "table";
      document.getElementById("viewTable").classList.add("active");
      document.getElementById("viewCards").classList.remove("active");
      renderAccounts();
    });
    document.getElementById("refreshBtn").addEventListener("click", function () {
      fetch("/api/refresh", { method: "POST" })
        .then(function (response) {
          return response.json();
        })
        .then(function () {
          fetchState();
        });
    });
  }

  function wireExport() {
    var menu = document.getElementById("exportMenu");
    document.getElementById("exportBtn").addEventListener("click", function (event) {
      event.stopPropagation();
      menu.classList.toggle("hidden");
    });
    menu.querySelectorAll("button").forEach(function (button) {
      button.addEventListener("click", function () {
        window.open("/api/export?format=" + encodeURIComponent(button.dataset.format), "_blank");
        menu.classList.add("hidden");
      });
    });
    document.addEventListener("click", function () {
      menu.classList.add("hidden");
    });
  }

  function wireSettings() {
    var dialog = document.getElementById("settingsDialog");
    var pathList = document.getElementById("extraPaths");

    function openSettings() {
      var config = state.data.config;
      document.getElementById("cfgScanHome").checked = config.scan_home;
      document.getElementById("cfgScanProfiles").checked = config.scan_profiles;
      document.getElementById("cfgRefreshOnStart").checked = config.refresh_on_start;
      document.getElementById("cfgTimeout").value = config.refresh_timeout_seconds;
      document.getElementById("cfgOutputDir").value = config.output_dir || "";
      pathList.textContent = "";
      (config.extra_code_homes || []).forEach(addPathRow);
      dialog.classList.remove("hidden");
    }

    function addPathRow(value) {
      var row = el("div", "path-row");
      var input = el("input");
      input.type = "text";
      input.placeholder = "例如 C:\\Users\\me\\.codex_extra 或 ~/.codex_y";
      input.value = value || "";
      var remove = el("button", "", "×");
      remove.type = "button";
      remove.title = "移除";
      remove.addEventListener("click", function () {
        row.remove();
      });
      row.appendChild(input);
      row.appendChild(remove);
      pathList.appendChild(row);
    }

    function closeSettings() {
      dialog.classList.add("hidden");
    }

    document.getElementById("settingsBtn").addEventListener("click", openSettings);
    document.getElementById("closeSettings").addEventListener("click", closeSettings);
    document.getElementById("cancelSettings").addEventListener("click", closeSettings);
    document.getElementById("addPath").addEventListener("click", function () {
      addPathRow("");
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) {
        closeSettings();
      }
    });
    document.getElementById("saveSettings").addEventListener("click", function () {
      var paths = [];
      pathList.querySelectorAll("input").forEach(function (input) {
        if (input.value.trim()) {
          paths.push(input.value.trim());
        }
      });
      var payload = {
        scan_home: document.getElementById("cfgScanHome").checked,
        scan_profiles: document.getElementById("cfgScanProfiles").checked,
        refresh_on_start: document.getElementById("cfgRefreshOnStart").checked,
        refresh_timeout_seconds: parseInt(document.getElementById("cfgTimeout").value, 10) || 60,
        output_dir: document.getElementById("cfgOutputDir").value.trim(),
        extra_code_homes: paths
      };
      fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
        .then(function (response) {
          return response.json();
        })
        .then(function () {
          closeSettings();
          fetchState();
        });
    });
  }

  function init() {
    wireToolbar();
    wireExport();
    wireSettings();
    fetchState();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
