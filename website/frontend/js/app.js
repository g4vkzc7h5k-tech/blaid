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

// Mobile docs sidebar - a dedicated trigger button (shown only under
// 860px, see CSS) opens the sidebar as a slide-in overlay, since the
// desktop sidebar toggle is hidden entirely on small screens.
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

  if (!("IntersectionObserver" in window)) {
    // No IntersectionObserver support - leave elements in their
    // default (visible) state rather than arming an animation that
    // could never trigger.
    return;
  }

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
    // Force a style flush so the browser registers the "armed" (hidden)
    // state before the observer can immediately flip it to in-view on
    // already-visible elements - otherwise the transition never plays.
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

async function loadCommands() {
  const body = document.querySelector(".cmd-body");
  const chipBar = document.querySelector(".chip-bar");
  if (!body) return;

  const searchInput = document.querySelector("#cmd-search-input");
  let allCommands = [];

  function renderChips(categories) {
    if (!chipBar) return;
    chipBar.innerHTML = "";
    const allChip = document.createElement("button");
    allChip.className = "chip active";
    allChip.textContent = "All";
    allChip.dataset.category = "";
    chipBar.appendChild(allChip);

    categories.forEach((cat) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = cat;
      chip.dataset.category = cat;
      chipBar.appendChild(chip);
    });

    chipBar.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        chipBar.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        const target = chip.dataset.category;
        if (!target) {
          render(allCommands);
          return;
        }
        const section = body.querySelector(`[data-category-section="${CSS.escape(target)}"]`);
        if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function render(commands) {
    body.innerHTML = "";

    if (commands.length === 0) {
      const empty = document.createElement("p");
      empty.style.color = "var(--text-faint)";
      empty.style.textAlign = "center";
      empty.style.padding = "60px 0";
      empty.textContent = "No commands match your search.";
      body.appendChild(empty);
      return;
    }

    const byCategory = {};
    commands.forEach((cmd) => {
      if (!byCategory[cmd.category]) byCategory[cmd.category] = [];
      byCategory[cmd.category].push(cmd);
    });

    Object.keys(byCategory).sort().forEach((category) => {
      const section = document.createElement("div");
      section.dataset.categorySection = category;

      const bar = document.createElement("div");
      bar.className = "category-bar";
      bar.innerHTML = `<span>${category}</span><span class="count">${byCategory[category].length} command${byCategory[category].length === 1 ? "" : "s"}</span>`;
      section.appendChild(bar);

      byCategory[category].forEach((cmd) => {
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
        section.appendChild(card);
      });

      body.appendChild(section);
    });

    body.querySelectorAll(".copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy);
        const original = btn.innerHTML;
        btn.textContent = "Copied";
        setTimeout(() => (btn.innerHTML = original), 1200);
      });
    });

    initReveal();
  }

  try {
    const res = await fetch(`${API_BASE}/api/commands`);
    const data = await res.json();
    allCommands = data.commands || [];
    const categories = [...new Set(allCommands.map((c) => c.category))].sort();
    renderChips(categories);
    render(allCommands);
  } catch (err) {
    body.innerHTML = `<p style="color: var(--text-faint); text-align:center; padding: 60px 0;">Couldn't load commands right now.</p>`;
    return;
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase().trim();
      if (!q) {
        render(allCommands);
        return;
      }
      const filtered = allCommands.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.description.toLowerCase().includes(q) ||
          (c.aliases || []).some((a) => a.toLowerCase().includes(q))
      );
      render(filtered);
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

// ---------------------------------------------------------- embed builder

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

    const payload = {
      title: v.title || null,
      description: v.desc || null,
      color: isValidColor ? parseInt(v.color.replace("#", ""), 16) : null,
      thumbnail: v.thumb ? { url: v.thumb } : null,
      image: v.image ? { url: v.image } : null,
      author: v["author-name"] ? { name: v["author-name"], icon_url: v["author-icon"] || null } : null,
      footer: v.footer || v["footer-icon"] ? { text: v.footer || null, icon_url: v["footer-icon"] || null } : null,
      fields: v["field-name"] || v["field-value"] ? [{ name: v["field-name"], value: v["field-value"], inline: false }] : [],
    };
    document.getElementById("json-output").textContent = JSON.stringify(payload, null, 2);
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

// ---------------------------------------------------------- variables page

async function loadVariables() {
  const groupsEl = document.querySelector("#var-groups");
  if (!groupsEl) return;

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
  if (document.querySelector("#status-line")) {
    setInterval(loadStatus, 30000);
  }
});

