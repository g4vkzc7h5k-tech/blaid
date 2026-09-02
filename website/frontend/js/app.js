// Shared behavior across every page: loading screen, nav toggles,
// scroll-reveal animation, and page-specific logic (commands,
// status, embed builder).

function initLoader() {
  const loader = document.querySelector(".loader");
  const page = document.querySelector(".page");
  if (!loader || !page) return;

  const reveal = () => {
    loader.classList.add("hidden");
    page.classList.add("revealed");
  };

  const minDelay = new Promise((resolve) => setTimeout(resolve, 550));
  const ready = new Promise((resolve) => {
    if (document.readyState === "complete") resolve();
    else window.addEventListener("load", resolve, { once: true });
  });

  Promise.all([minDelay, ready]).then(reveal);
  setTimeout(reveal, 1800);
}

function initTopMenu() {
  const toggle = document.querySelector(".topbar .menu-toggle");
  const panel = document.querySelector(".nav-panel");
  if (!toggle || !panel) return;

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle.classList.toggle("open");
    panel.classList.toggle("open");
  });

  document.addEventListener("click", (e) => {
    if (!panel.contains(e.target) && !toggle.contains(e.target)) {
      toggle.classList.remove("open");
      panel.classList.remove("open");
    }
  });
}

function initDotMenu() {
  const trigger = document.querySelector(".dot-trigger");
  const panel = document.querySelector(".dot-panel");
  if (!trigger || !panel) return;

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.classList.toggle("open");
  });

  document.addEventListener("click", (e) => {
    if (!panel.contains(e.target) && !trigger.contains(e.target)) {
      panel.classList.remove("open");
    }
  });
}

function initDocsMobileNav() {
  const trigger = document.querySelector(".docs-mobile-trigger");
  const sidebar = document.querySelector(".docs-sidebar");
  const overlay = document.querySelector(".docs-overlay");
  if (!trigger || !sidebar || !overlay) return;

  const open = () => {
    sidebar.classList.add("mobile-open");
    overlay.classList.add("visible");
  };
  const close = () => {
    sidebar.classList.remove("mobile-open");
    overlay.classList.remove("visible");
  };

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    sidebar.classList.contains("mobile-open") ? close() : open();
  });
  overlay.addEventListener("click", close);
  sidebar.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
}

function initReveal() {
  const els = document.querySelectorAll(".reveal:not(.reveal-armed)");
  if (!els.length) return;

  if (!("IntersectionObserver" in window)) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  els.forEach((el) => {
    el.classList.add("reveal-armed");
    void el.offsetHeight;
    observer.observe(el);
  });
}

function applyLinks() {
  document.querySelectorAll("[data-invite-link]").forEach((el) => (el.href = BLADE_LINKS.invite));
  document.querySelectorAll("[data-support-link]").forEach((el) => {
    if (BLADE_LINKS.support === "#") el.style.display = "none";
    else el.href = BLADE_LINKS.support;
  });
}

// ---------------------------------------------------------- commands page

function showSkeleton(container, count = 5) {
  container.innerHTML = Array.from({ length: count })
    .map(() => '<div class="skeleton-card"><div class="skeleton-line"></div><div class="skeleton-line"></div></div>')
    .join("");
}

async function loadCommands() {
  const body = document.querySelector(".cmd-body");
  const chipBar = document.querySelector(".chip-bar");
  if (!body) return;

  showSkeleton(body, 6);

  const searchInput = document.querySelector("#cmd-search-input");
  let allCommands = [];
  let byCategory = {};
  let activeCategory = "__all__";

  function renderCard(cmd) {
    const card = document.createElement("div");
    card.className = "cmd-card reveal";

    const argsValue = cmd.syntax || "—";
    const permsValue = cmd.permissions && cmd.permissions.length ? cmd.permissions.join(", ") : "Everyone";

    card.innerHTML = `
      <div class="cmd-card-top">
        <span class="cmd-name">,${cmd.name}</span>
        <button class="copy-btn" data-copy=",${cmd.name}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy
        </button>
      </div>
      <p class="cmd-desc">${cmd.description}</p>
      <div class="cmd-meta">
        <div class="cmd-meta-block">
          <p class="label">Arguments</p>
          <p class="value">${argsValue}</p>
        </div>
        <div class="cmd-meta-block">
          <p class="label">Permissions</p>
          <p class="value perm">${permsValue}</p>
        </div>
      </div>
    `;
    return card;
  }

  function renderChips() {
    if (!chipBar) return;
    chipBar.innerHTML = "";

    const allChip = document.createElement("button");
    allChip.className = "chip" + (activeCategory === "__all__" ? " active" : "");
    allChip.textContent = `All (${allCommands.length})`;
    allChip.dataset.category = "__all__";
    chipBar.appendChild(allChip);

    Object.keys(byCategory).sort().forEach((cat) => {
      const chip = document.createElement("button");
      chip.className = "chip" + (activeCategory === cat ? " active" : "");
      chip.textContent = `${cat} (${byCategory[cat].length})`;
      chip.dataset.category = cat;
      chipBar.appendChild(chip);
    });

    chipBar.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        if (chip.dataset.category === activeCategory) return;
        activeCategory = chip.dataset.category;
        renderChips();
        renderTab();
      });
    });
  }

  function renderTab() {
    // Tab switch: swap content in place with a quick slide/fade,
    // never scrolling the page - this also keeps the DOM small (only
    // the active category's cards ever exist at once), which matters
    // for lower-memory mobile browsers.
    body.classList.add("tab-out");

    setTimeout(() => {
      body.innerHTML = "";

      const list = activeCategory === "__all__" ? allCommands : byCategory[activeCategory] || [];

      if (list.length === 0) {
        const empty = document.createElement("p");
        empty.style.color = "var(--text-faint)";
        empty.style.textAlign = "center";
        empty.style.padding = "60px 0";
        empty.textContent = "No commands match your search.";
        body.appendChild(empty);
      } else if (activeCategory === "__all__") {
        Object.keys(byCategory).sort().forEach((cat) => {
          const section = document.createElement("div");
          const bar = document.createElement("div");
          bar.className = "category-bar";
          bar.innerHTML = `<span>${cat}</span><span class="count">${byCategory[cat].length}</span>`;
          section.appendChild(bar);
          byCategory[cat].forEach((cmd) => section.appendChild(renderCard(cmd)));
          body.appendChild(section);
        });
      } else {
        list.forEach((cmd) => body.appendChild(renderCard(cmd)));
      }

      body.querySelectorAll(".copy-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          navigator.clipboard.writeText(btn.dataset.copy);
          const original = btn.innerHTML;
          btn.textContent = "Copied";
          setTimeout(() => (btn.innerHTML = original), 1200);
        });
      });

      initReveal();
      body.classList.remove("tab-out");
      body.classList.add("tab-in");
      setTimeout(() => body.classList.remove("tab-in"), 220);
    }, 120);
  }

  function applySearch(commands) {
    byCategory = {};
    commands.forEach((cmd) => {
      if (!byCategory[cmd.category]) byCategory[cmd.category] = [];
      byCategory[cmd.category].push(cmd);
    });
    if (!byCategory[activeCategory] && activeCategory !== "__all__") activeCategory = "__all__";
    renderChips();
    renderTab();
  }

  try {
    const res = await fetch(`${API_BASE}/api/commands`);
    const data = await res.json();
    allCommands = data.commands || [];
    applySearch(allCommands);

    const heading = document.querySelector(".cmd-header h1");
    if (heading) heading.textContent = `Commands (${allCommands.length})`;
  } catch (err) {
    body.innerHTML = `<p style="color: var(--text-faint); text-align:center; padding: 60px 0;">Couldn't load commands right now.</p>`;
    return;
  }

  // Desktop scroll arrows for the chip bar (mobile relies on swipe/touch instead)
  const arrowLeft = document.querySelector(".chip-arrow-left");
  const arrowRight = document.querySelector(".chip-arrow-right");
  function updateArrows() {
    if (!arrowLeft || !arrowRight || !chipBar) return;
    arrowLeft.disabled = chipBar.scrollLeft <= 0;
    arrowRight.disabled = chipBar.scrollLeft >= chipBar.scrollWidth - chipBar.clientWidth - 1;
  }
  if (arrowLeft && arrowRight && chipBar) {
    arrowLeft.addEventListener("click", () => chipBar.scrollBy({ left: -220, behavior: "smooth" }));
    arrowRight.addEventListener("click", () => chipBar.scrollBy({ left: 220, behavior: "smooth" }));
    chipBar.addEventListener("scroll", updateArrows);
    updateArrows();
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase().trim();
      const filtered = !q
        ? allCommands
        : allCommands.filter(
            (c) =>
              c.name.toLowerCase().includes(q) ||
              c.description.toLowerCase().includes(q) ||
              (c.aliases || []).some((a) => a.toLowerCase().includes(q))
          );
      applySearch(filtered);
    });
  }
}

// ---------------------------------------------------------- status page

function formatUptime(seconds) {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

async function loadStatus() {
  const line = document.querySelector("#status-line");
  if (!line) return;

  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();

    if (!data.online) {
      line.innerHTML = `<span class="status-dot offline"></span>Offline${data.reason ? " — " + data.reason : ""}`;
      return;
    }

    line.innerHTML = `<span class="status-dot online"></span>Online`;
    document.querySelector("#stat-guilds").textContent = data.guild_count?.toLocaleString() ?? "—";
    document.querySelector("#stat-users").textContent = data.user_count?.toLocaleString() ?? "—";
    document.querySelector("#stat-latency").textContent = data.latency_ms != null ? `${data.latency_ms}ms` : "—";
    const uptimeSeconds = Date.now() / 1000 - data.started_at;
    document.querySelector("#stat-uptime").textContent = formatUptime(uptimeSeconds);
  } catch (err) {
    line.innerHTML = `<span class="status-dot offline"></span>Couldn't reach the API.`;
  }
}

// ---------------------------------------------------------- variables page

async function loadVariables() {
  const groupsEl = document.querySelector("#var-groups");
  if (!groupsEl) return;

  showSkeleton(groupsEl, 8);

  try {
    const res = await fetch(`${API_BASE}/api/variables`);
    const data = await res.json();
    groupsEl.innerHTML = Object.entries(data.groups)
      .map(
        ([group, vars]) => `
          <h2>${group}</h2>
          ${vars
            .map(
              (v) => `
            <div class="cmd-card reveal">
              <span class="cmd-name">${v.name}</span>
              <p class="cmd-desc">${v.description} — e.g. <code>${v.example}</code></p>
            </div>
          `
            )
            .join("")}
        `
      )
      .join("");
    initReveal();
  } catch (err) {
    groupsEl.innerHTML = `<p style="color: var(--text-faint);">Couldn't reach the API.</p>`;
  }
}

// ---------------------------------------------------------- embed builder
//
// Builds Blade's own script syntax (see core/script_parser.py), NOT raw
// Discord embed JSON - e.g. {embed}$v{title: Hi {user.mention}}$v...
// so the output can be pasted directly into any Blade command that
// accepts a custom script (,tickets message, ,joindm message, etc.).

function initEmbedBuilder() {
  const preview = document.querySelector("#preview");
  if (!preview) return;

  const ids = [
    "author-name", "author-icon", "title", "desc", "color", "thumb", "image",
    "field-name", "field-value", "footer", "footer-icon",
  ];
  const fields = Object.fromEntries(ids.map((id) => [id, document.getElementById(`f-${id}`)]));
  const colorPicker = document.getElementById("f-color-picker");

  function setImg(el, url) {
    if (url) {
      el.src = url;
      el.style.display = "inline-block";
    } else {
      el.style.display = "none";
    }
  }

  function buildScript(v, isValidColor) {
    const parts = ["{embed}"];

    if (v.title) parts.push(`{title: ${v.title}}`);
    if (v.desc) parts.push(`{description: ${v.desc}}`);
    if (isValidColor) parts.push(`{color: ${v.color}}`);
    if (v.thumb) parts.push(`{thumbnail: ${v.thumb}}`);
    if (v.image) parts.push(`{image: ${v.image}}`);

    if (v["author-name"]) {
      let authorPart = `name:${v["author-name"]}`;
      if (v["author-icon"]) authorPart += ` && icon:${v["author-icon"]}`;
      parts.push(`{author: ${authorPart}}`);
    }

    if (v["field-name"] || v["field-value"]) {
      parts.push(`{field: ${v["field-name"] || "\u200b"} && ${v["field-value"] || "\u200b"}}`);
    }

    if (v.footer || v["footer-icon"]) {
      let footerPart = v.footer || "";
      if (v["footer-icon"]) footerPart += ` && ${v["footer-icon"]}`;
      parts.push(`{footer: ${footerPart}}`);
    }

    return parts.join("$v");
  }

  function update() {
    const v = Object.fromEntries(ids.map((id) => [id, fields[id].value.trim()]));

    const authorEl = document.getElementById("p-author");
    if (v["author-name"]) {
      authorEl.style.display = "flex";
      document.getElementById("p-author-text").textContent = v["author-name"];
      setImg(document.getElementById("p-author-icon"), v["author-icon"]);
    } else {
      authorEl.style.display = "none";
    }

    const titleEl = document.getElementById("p-title");
    titleEl.textContent = v.title;
    titleEl.style.display = v.title ? "block" : "none";

    document.getElementById("p-desc").textContent = v.desc;
    setImg(document.getElementById("p-thumb"), v.thumb);
    setImg(document.getElementById("p-image"), v.image);

    const fieldsEl = document.getElementById("p-fields");
    if (v["field-name"] || v["field-value"]) {
      fieldsEl.style.display = "grid";
      document.getElementById("p-field-name").textContent = v["field-name"];
      document.getElementById("p-field-value").textContent = v["field-value"];
    } else {
      fieldsEl.style.display = "none";
    }

    const footerEl = document.getElementById("p-footer");
    if (v.footer || v["footer-icon"]) {
      footerEl.style.display = "flex";
      document.getElementById("p-footer-text").textContent = v.footer;
      setImg(document.getElementById("p-footer-icon"), v["footer-icon"]);
    } else {
      footerEl.style.display = "none";
    }

    const isValidColor = /^#[0-9a-fA-F]{6}$/.test(v.color);
    preview.style.borderLeftColor = isValidColor ? v.color : "var(--red)";
    if (isValidColor) colorPicker.value = v.color;

    document.getElementById("json-output").textContent = buildScript(v, isValidColor);
  }

  Object.values(fields).forEach((f) => f.addEventListener("input", update));
  colorPicker.addEventListener("input", () => {
    fields.color.value = colorPicker.value;
    update();
  });
  update();

  document.getElementById("copy-btn").addEventListener("click", (e) => {
    navigator.clipboard.writeText(document.getElementById("json-output").textContent);
    const btn = e.currentTarget;
    const original = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => (btn.textContent = original), 1200);
  });
}

// ---------------------------------------------------------- ticket builder

let questionCount = 0;

function addQuestionRow(container) {
  questionCount += 1;
  const id = questionCount;
  const row = document.createElement("div");
  row.className = "question-row";
  row.dataset.qid = id;
  row.innerHTML = `
    <div class="field-group">
      <label>Question</label>
      <input type="text" class="q-label" placeholder="What do you need help with?">
    </div>
    <div class="field-group">
      <label>Placeholder</label>
      <input type="text" class="q-placeholder" placeholder="Optional">
    </div>
    <button class="question-remove" type="button" title="Remove">&times;</button>
  `;
  row.querySelector(".question-remove").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function collectQuestions(container) {
  return [...container.querySelectorAll(".question-row")]
    .map((row) => ({
      label: row.querySelector(".q-label").value.trim(),
      placeholder: row.querySelector(".q-placeholder").value.trim(),
      required: true,
    }))
    .filter((q) => q.label);
}

function initTicketBuilder() {
  const app = document.querySelector("#tickets-app");
  const loggedOut = document.querySelector("#tickets-logged-out");
  if (!app || !loggedOut) return;

  const loginBtn = document.querySelector("#login-btn");
  if (loginBtn) loginBtn.href = `${API_BASE}/api/auth/login`;

  const guildSelect = document.querySelector("#guild-select");
  const channelSelect = document.querySelector("#channel-select");
  const questionsList = document.querySelector("#questions-list");
  const sendStatus = document.querySelector("#send-status");

  // Tabs
  document.querySelectorAll(".ticket-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".ticket-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".ticket-tab-content").forEach((c) => (c.style.display = "none"));
      document.querySelector(`#tab-${tab.dataset.tab}`).style.display = "block";
    });
  });

  document.querySelector("#add-question-btn").addEventListener("click", () => addQuestionRow(questionsList));

  // Live panel preview
  function updatePreview() {
    document.querySelector("#pp-title").textContent = document.querySelector("#p-title").value;
    document.querySelector("#pp-desc").textContent = document.querySelector("#p-desc").value;
    document.querySelector("#pp-button").textContent = document.querySelector("#p-button-label").value || "Open Ticket";
    const color = document.querySelector("#p-color").value;
    if (/^#[0-9a-fA-F]{6}$/.test(color)) {
      document.querySelector("#panel-preview").style.borderLeftColor = color;
      document.querySelector("#pp-button").style.background = color;
    }
  }
  ["#p-title", "#p-desc", "#p-button-label", "#p-color"].forEach((sel) => {
    document.querySelector(sel).addEventListener("input", updatePreview);
  });
  document.querySelector("#p-color-picker").addEventListener("input", (e) => {
    document.querySelector("#p-color").value = e.target.value;
    updatePreview();
  });
  updatePreview();

  async function loadChannels(guildId) {
    channelSelect.innerHTML = "<option>Loading...</option>";
    try {
      const res = await fetch(`${API_BASE}/api/guilds/${guildId}/channels`, { credentials: "include" });
      const data = await res.json();
      channelSelect.innerHTML = (data.channels || [])
        .map((c) => `<option value="${c.id}">#${c.name}</option>`)
        .join("");
    } catch (err) {
      channelSelect.innerHTML = "<option>Couldn't load channels</option>";
    }
  }

  guildSelect.addEventListener("change", () => loadChannels(guildSelect.value));

  document.querySelector("#send-btn").addEventListener("click", async () => {
    const payload = {
      guild_id: guildSelect.value,
      channel_id: channelSelect.value,
      title: document.querySelector("#p-title").value,
      description: document.querySelector("#p-desc").value,
      color: document.querySelector("#p-color").value,
      button_label: document.querySelector("#p-button-label").value,
      category_name: document.querySelector("#o-category").value,
      log_channel_id: document.querySelector("#o-log-channel").value || null,
      support_role_id: document.querySelector("#o-support-role").value || null,
      naming_pattern: document.querySelector("#o-naming").value,
      questions: collectQuestions(questionsList),
    };

    sendStatus.textContent = "Sending...";
    sendStatus.style.color = "var(--text-faint)";

    try {
      const res = await fetch(`${API_BASE}/api/tickets/queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("request failed");
      sendStatus.textContent = "Queued! Your panel will appear in the channel within about 30 seconds.";
      sendStatus.style.color = "#3BA55D";
    } catch (err) {
      sendStatus.textContent = "Couldn't queue the panel - try again in a moment.";
      sendStatus.style.color = "var(--red-bright)";
    }
  });

  // Check login state
  fetch(`${API_BASE}/api/auth/me`, { credentials: "include" })
    .then((res) => res.json())
    .then((data) => {
      if (!data.logged_in) {
        loggedOut.style.display = "block";
        return;
      }
      app.style.display = "block";
      guildSelect.innerHTML = (data.guilds || [])
        .map((g) => `<option value="${g.id}">${g.name}</option>`)
        .join("");
      if (data.guilds && data.guilds.length) loadChannels(data.guilds[0].id);
    })
    .catch(() => {
      loggedOut.style.display = "block";
    });
}

document.addEventListener("DOMContentLoaded", () => {
  initLoader();
  initTopMenu();
  initDotMenu();
  initDocsMobileNav();
  applyLinks();
  initReveal();
  loadCommands();
  loadStatus();
  initEmbedBuilder();
  loadVariables();
  initTicketBuilder();
});

