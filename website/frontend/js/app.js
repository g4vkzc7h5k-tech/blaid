// Shared behavior across every page: loading screen, nav toggles,
// scroll-reveal animation, and page-specific logic (commands,
// status, embed builder).

function initLoader() {
  const loader = document.querySelector(".loader");
  const page = document.querySelector(".page");
  const logo = document.querySelector(".loader-logo");
  if (!loader || !page) return;

  const reveal = () => {
    loader.classList.add("hidden");
    page.classList.add("revealed");
  };

  // The glow-then-shrink animation (see loader-glow-shrink in CSS) is
  // 1.4s - the page must never open before that finishes, so it's the
  // floor here, not just a nice-to-have minimum.
  const animationDuration = 1400;
  const minDelay = new Promise((resolve) => setTimeout(resolve, animationDuration));
  const ready = new Promise((resolve) => {
    if (document.readyState === "complete") resolve();
    else window.addEventListener("load", resolve, { once: true });
  });

  Promise.all([minDelay, ready]).then(reveal);
  setTimeout(reveal, 2600); // hard ceiling in case something hangs
}

function initTopMenu() {
  const toggle = document.querySelector(".topbar .menu-toggle");
  const panel = document.querySelector(".nav-panel");
  if (!toggle || !panel) return;

  const isMobileNow = () => window.matchMedia("(max-width: 860px)").matches;

  // On mobile only: move the panel to be a direct child of <body>,
  // and build a real (not pseudo-element) backdrop, also appended
  // straight to <body>. This sidesteps CSS stacking-context problems
  // entirely (an ancestor like .page or .topbar having its own
  // stacking context due to position/transform/filter, trapping the
  // panel/backdrop below other content no matter what z-index was
  // set on them) - there's no ancestor left to get trapped inside
  // once both live directly on body. Desktop is untouched: the panel
  // stays exactly where it is, inline in the topbar.
  let backdrop = null;
  if (isMobileNow()) {
    document.body.appendChild(panel);
    backdrop = document.createElement("div");
    backdrop.className = "mobile-nav-backdrop";
    document.body.appendChild(backdrop);
  }

  const openMenu = () => {
    toggle.classList.add("open");
    panel.classList.add("open");
    if (backdrop) {
      backdrop.classList.add("visible");
      document.body.classList.add("nav-open");
    }
  };

  const closeMenu = () => {
    toggle.classList.remove("open");
    panel.classList.remove("open");
    backdrop?.classList.remove("visible");
    document.body.classList.remove("nav-open");
  };

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    panel.classList.contains("open") ? closeMenu() : openMenu();
  });

  backdrop?.addEventListener("click", closeMenu);

  document.addEventListener("click", (e) => {
    if (!panel.contains(e.target) && !toggle.contains(e.target) && !(backdrop && backdrop.contains(e.target))) {
      closeMenu();
    }
  });

  panel.querySelectorAll("a").forEach((a) => a.addEventListener("click", closeMenu));
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

function initDocsSections() {
  const sidebarLinks = document.querySelectorAll(".docs-sidebar a[href^='#']");
  const sections = document.querySelectorAll(".docs-content > section[id]");
  const crumbCurrent = document.querySelector(".docs-crumb .current");
  if (!sidebarLinks.length || !sections.length) return;

  // Expandable sub-groups (Automation / Roles / Messages / Scripting)
  document.querySelectorAll(".docs-nav-expand").forEach((btn) => {
    const target = document.getElementById(btn.dataset.target);
    if (!target) return;
    btn.addEventListener("click", () => {
      btn.classList.toggle("open");
      target.classList.toggle("open");
    });
  });

  function showSection(id) {
    sections.forEach((s) => (s.style.display = s.id === id ? "block" : "none"));
    sidebarLinks.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${id}`));
    if (crumbCurrent) {
      const matchingLink = [...sidebarLinks].find((a) => a.getAttribute("href") === `#${id}`);
      if (matchingLink) crumbCurrent.textContent = matchingLink.textContent;
    }
    // If the target link lives inside a collapsed sub-group, open that
    // group too, so the active item is actually visible.
    const activeLink = [...sidebarLinks].find((a) => a.getAttribute("href") === `#${id}`);
    const parentSub = activeLink?.closest(".docs-nav-sub");
    if (parentSub) {
      parentSub.classList.add("open");
      const expandBtn = document.querySelector(`.docs-nav-expand[data-target="${parentSub.id}"]`);
      expandBtn?.classList.add("open");
    }
    document.querySelector(".docs-content")?.scrollTo({ top: 0 });
  }

  sidebarLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (!href.startsWith("#")) return; // full-page links (Commands, Variables) behave normally
      e.preventDefault();
      const id = href.slice(1);
      showSection(id);
      history.replaceState(null, "", href);
    });
  });

  // Land on whichever section the URL hash points to (or the first one)
  const initialId = (window.location.hash || sidebarLinks[0].getAttribute("href")).slice(1);
  if (document.getElementById(initialId)) {
    showSection(initialId);
  }

  // Search: filters the sidebar link list by text match - matching
  // links stay, non-matching ones (and now-empty group labels) hide.
  const searchInput = document.querySelector("#docs-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll(".docs-nav-group").forEach((group) => {
        let anyVisible = false;
        group.querySelectorAll("a").forEach((a) => {
          const matches = !q || a.textContent.toLowerCase().includes(q);
          a.classList.toggle("search-hidden", !matches);
          if (matches) anyVisible = true;
        });
        const label = group.querySelector(".docs-nav-label");
        if (label) label.classList.toggle("search-hidden", !anyVisible);
      });
    });
  }
}

const _isMobile = window.matchMedia("(max-width: 860px)").matches;

function initReveal() {
  const els = document.querySelectorAll(".reveal:not(.reveal-armed)");
  if (!els.length) return;

  // On mobile, per-card scroll-reveal (many IntersectionObserver
  // targets + forced reflows) was the likely cause of "a problem
  // occurred" tab crashes on long lists like Commands - cards just
  // show immediately there instead. Desktop keeps the animation.
  if (_isMobile || !("IntersectionObserver" in window)) return;

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

  // Batch the "armed" class + forced reflow into a single frame
  // instead of one reflow per element (layout thrashing) - this was
  // the more expensive part on longer lists, even before the mobile
  // skip above.
  els.forEach((el) => el.classList.add("reveal-armed"));
  requestAnimationFrame(() => {
    void document.body.offsetHeight; // single shared reflow
    els.forEach((el) => observer.observe(el));
  });
}

function applyLinks() {
  document.querySelectorAll("[data-invite-link]").forEach((el) => (el.href = BLADE_LINKS.invite));
  document.querySelectorAll("[data-support-link]").forEach((el) => {
    if (BLADE_LINKS.support === "#") el.style.display = "none";
    else el.href = BLADE_LINKS.support;
  });
}

// ---------------------------------------------------------- homepage dot field
//
// A small number of soft dots drifting slowly across the hero
// background on the homepage only. Pure canvas, no external libs,
// very low dot count and speed to stay cheap on mobile - pauses
// entirely when the tab isn't visible.

function initDotField() {
  const canvas = document.querySelector("#dot-field");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  let width, height, dots;
  const DOT_COUNT = _isMobile ? 26 : 46;

  function resize() {
    width = canvas.width = canvas.offsetWidth * devicePixelRatio;
    height = canvas.height = canvas.offsetHeight * devicePixelRatio;
  }

  function makeDots() {
    dots = Array.from({ length: DOT_COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: (Math.random() * 1.4 + 0.6) * devicePixelRatio,
      vx: (Math.random() - 0.5) * 0.12 * devicePixelRatio,
      vy: (Math.random() - 0.5) * 0.12 * devicePixelRatio,
      a: Math.random() * 0.35 + 0.12,
    }));
  }

  resize();
  makeDots();
  window.addEventListener("resize", () => {
    resize();
    makeDots();
  });

  let running = true;
  document.addEventListener("visibilitychange", () => {
    running = document.visibilityState === "visible";
    if (running) requestAnimationFrame(tick);
  });

  function tick() {
    if (!running) return;
    ctx.clearRect(0, 0, width, height);
    dots.forEach((d) => {
      d.x += d.vx;
      d.y += d.vy;
      if (d.x < 0) d.x = width;
      if (d.x > width) d.x = 0;
      if (d.y < 0) d.y = height;
      if (d.y > height) d.y = 0;

      ctx.beginPath();
      ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(47, 168, 201, ${d.a})`;
      ctx.fill();
    });
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
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
  const overallDot = document.querySelector("#status-overall-dot");
  const overallText = document.querySelector("#status-overall-text");
  if (!overallDot && !overallText) return; // old single-line layout not present - nothing to do

  const setPill = (id, online, textOnline, textOffline) => {
    const el = document.querySelector(`#${id}`);
    if (!el) return;
    el.classList.toggle("offline", !online);
    el.querySelector(".pill-text").textContent = online ? textOnline : textOffline;
  };

  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();

    // The very fact this fetch succeeded means the website backend
    // itself is reachable and responding - that's a real signal, not
    // a guess, so it's safe to show as genuinely monitored.
    setPill("svc-backend", true, "Operational", "Down");

    if (!data.online) {
      overallDot.className = "status-dot offline";
      overallText.textContent = data.reason ? `Offline — ${data.reason}` : "Offline";
      setPill("svc-bot", false, "Operational", "Down");
      setPill("svc-database", false, "Operational", "Unreachable");
      showIncident(data.reason || "The bot is currently offline.");
      return;
    }

    overallDot.className = "status-dot online";
    overallText.textContent = "All systems operational";
    setPill("svc-bot", true, "Operational", "Down");
    // The bot's SQLite database is embedded in the same process - if
    // the bot is reporting itself online at all, its DB connection is
    // inherently working too (there's no code path where the bot
    // stays up with a broken DB), so this is a real inference, not a
    // fabricated green light.
    setPill("svc-database", true, "Operational", "Unreachable");
    hideIncident();

    const guildsEl = document.querySelector("#stat-guilds");
    const usersEl = document.querySelector("#stat-users");
    const latencyEl = document.querySelector("#stat-latency");
    const uptimeEl = document.querySelector("#stat-uptime");
    if (guildsEl) guildsEl.textContent = data.guild_count?.toLocaleString() ?? "—";
    if (usersEl) usersEl.textContent = data.user_count?.toLocaleString() ?? "—";
    if (latencyEl) latencyEl.textContent = data.latency_ms != null ? `${data.latency_ms}ms` : "—";
    if (uptimeEl) {
      const uptimeSeconds = Date.now() / 1000 - data.started_at;
      uptimeEl.textContent = formatUptime(uptimeSeconds);
    }
  } catch (err) {
    overallDot.className = "status-dot offline";
    overallText.textContent = "Couldn't reach the API";
    setPill("svc-backend", false, "Operational", "Unreachable");
    setPill("svc-bot", false, "Operational", "Unknown");
    setPill("svc-database", false, "Operational", "Unknown");
    showIncident("Couldn't reach the status API right now.");
  }
}

function showIncident(message) {
  const box = document.querySelector("#status-incidents-box");
  const list = document.querySelector("#status-incidents-list");
  if (!box || !list) return;
  list.innerHTML = `<p class="incident-item">${message}</p>`;
  box.style.display = "block";
}

function hideIncident() {
  const box = document.querySelector("#status-incidents-box");
  if (box) box.style.display = "none";
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

function initSiteLoginChip() {
  const chip = document.querySelector("#login-chip");
  if (!chip) return;

  chip.href = `${API_BASE}/api/auth/login`;

  fetch(`${API_BASE}/api/auth/me`, { credentials: "include" })
    .then((res) => res.json())
    .then((data) => {
      if (!data.logged_in) return; // stays as the default "Login" link

      const avatarUrl = data.user.avatar
        ? `https://cdn.discordapp.com/avatars/${data.user.id}/${data.user.avatar}.png`
        : "https://cdn.discordapp.com/embed/avatars/0.png";

      chip.classList.add("has-avatar");
      chip.href = "#";
      chip.innerHTML = `<img src="${avatarUrl}" alt=""> ${data.user.username}`;
      chip.addEventListener("click", async (e) => {
        e.preventDefault();
        if (!confirm("Log out?")) return;
        await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
        window.location.reload();
      });
    })
    .catch(() => {
      // stays as the default "Login" link on any error
    });
}

// NOTE: language switching is UI-only for now - it remembers the
// choice but doesn't yet translate any page content. Wiring up real
// translations is a separate piece of work.
// Translations - keyed by [data-i18n="key"] on any element. Only the
// shared nav/footer plus the Home and Premium pages are covered so
// far; every other page's content still shows English regardless of
// the selected language until it gets the same data-i18n treatment.
const TRANSLATIONS = {
  en: {
    status_subtitle: "Real-time availability and performance across the blaid platform.",
    status_incidents_title: "Active Incidents",
    status_group_core: "Core Infrastructure", status_svc_bot: "Bot", status_svc_database: "Database", status_svc_backend: "Website Backend",
    status_group_platform: "Platform Service", status_svc_image: "Image API",
    status_group_integrations: "Platform Integrations", status_unmonitored: "Not independently monitored",
    docs_cat_start: "GETTING STARTED", docs_cat_security: "SECURITY", docs_cat_serverconfig: "SERVER CONFIGURATION",
    docs_cat_misc: "MISCELLANEOUS", docs_cat_resources: "RESOURCES", docs_cat_reference: "REFERENCE", docs_cat_premium: "PREMIUM",
    docs_crumb: "Docs", docs_search_ph: "Search docs...",
    tix_title: "Ticket Builder", tix_lead: "Build a full ticket panel - options, forms, and all - visually, and send it straight to your server.",
    tix_login_eyebrow: "Log in to get started", tix_login_step: "Sign in with Discord to pick a server you manage and build a ticket panel for it.",
    tix_login_btn: "Login with Discord",
    cmds_title: "Commands", cmds_search_ph: "Search commands...",
    status_title: "Status", status_checking: "Checking...", status_servers: "Servers",
    status_users: "Users", status_latency: "Latency", status_uptime: "Uptime",
    vars_title: "Variables", vars_lead: "Use these inside welcome, goodbye, boost, ticket, and level-up messages. Unknown placeholders are left untouched.",
    eb_title: "Embed Builder", eb_lead: "Build a Discord embed, preview it exactly as it renders in Discord, and copy blaid's own script format into any command that accepts a custom script.",
    eb_live_preview: "Live preview", eb_copy_script: "Copy Script",
    nav_home: "Home", nav_commands: "Commands", nav_embed_builder: "Embed Builder",
    nav_status: "Status", nav_tickets: "Tickets", nav_discord: "Discord",
    nav_docs: "Documentation", nav_premium: "Premium",
    footer_support: "Support Server", footer_privacy: "Privacy", footer_terms: "Terms",
    footer_cat_docs: "Documentation", footer_cat_support: "Support", footer_cat_legal: "Legal", footer_cat_community: "Community",
    footer_getting_started: "Getting Started", footer_moderation: "Moderation", footer_antinuke: "Antinuke",
    footer_music: "Music", footer_levels: "Levels", footer_voicemaster: "VoiceMaster",
    footer_get_help: "Get Help", footer_refunds: "Refunds", footer_join_discord: "Join our Discord",
    features_eyebrow: "Everything in one bot", features_title: "Built to replace half a dozen bots",
    features_lead: "Every category below is a real, working part of blaid - not a roadmap.",
    feat_mod_title: "Moderation & Security", feat_mod_desc: "Full moderation suite, antinuke, antiraid, honeypots, and a verification gate for risky new accounts.",
    feat_tickets_title: "Tickets & VoiceMaster", feat_tickets_desc: "Visually build ticket panels on this site, plus join-to-create voice channels with full owner controls.",
    feat_levels_title: "Leveling & Economy", feat_levels_desc: "XP, custom level-up cards, role rewards, and a full economy with 12 gambling games.",
    feat_fun_title: "Fun & Utility", feat_fun_desc: "Tic-Tac-Toe, BlackTea, AI answers, reaction/button roles, and a full embed scripting system.",
    home_title: "blaid is Discord's premier all-in-one app",
    home_lead: "Meet the leading bot for management and engagement. Built to elevate your community's experience, streamline server management, and provide you access to premium resources for every necessity.",
    home_invite_btn: "Invite to Discord",
    premium_title: "blaid Premium",
    premium_lead: "Two independent plans, purchased entirely through Discord's own checkout - we never see your payment details.",
    premium_howto_eyebrow: "How to get Premium",
    premium_howto_step: "Run ,premium in your server, pick a plan, and click the purchase button - Discord handles the checkout, and Premium activates automatically the moment payment goes through.",
    premium_server_name: "Server Premium",
    premium_server_blurb: "Raises limits and unlocks premium-only features for your whole server.",
    premium_customize_name: "Customize",
    premium_customize_blurb: "Give blaid a custom identity just for your server.",
    premium_get_server: "Get Server Premium",
    premium_get_customize: "Get Customize",
  },
  de: {
    status_subtitle: "Verfügbarkeit und Leistung der gesamten blaid-Plattform in Echtzeit.",
    status_incidents_title: "Aktuelle Störungen",
    status_group_core: "Kern-Infrastruktur", status_svc_bot: "Bot", status_svc_database: "Datenbank", status_svc_backend: "Website-Backend",
    status_group_platform: "Plattform-Dienst", status_svc_image: "Bild-API",
    status_group_integrations: "Plattform-Integrationen", status_unmonitored: "Wird nicht einzeln überwacht",
    docs_cat_start: "ERSTE SCHRITTE", docs_cat_security: "SICHERHEIT", docs_cat_serverconfig: "SERVER-EINSTELLUNGEN",
    docs_cat_misc: "SONSTIGES", docs_cat_resources: "RESSOURCEN", docs_cat_reference: "REFERENZ", docs_cat_premium: "PREMIUM",
    docs_crumb: "Doku", docs_search_ph: "Doku durchsuchen...",
    tix_title: "Ticket-Baukasten", tix_lead: "Baut ein komplettes Ticket-Panel - Options, Formulare, alles - visuell, und schickt es direkt an euren Server.",
    tix_login_eyebrow: "Loggt euch ein, um loszulegen", tix_login_step: "Meldet euch mit Discord an, um einen Server auszuwählen, den ihr verwaltet, und baut ein Ticket-Panel dafür.",
    tix_login_btn: "Mit Discord anmelden",
    cmds_title: "Befehle", cmds_search_ph: "Befehle durchsuchen...",
    status_title: "Status", status_checking: "Wird geprüft...", status_servers: "Server",
    status_users: "Nutzer", status_latency: "Latenz", status_uptime: "Laufzeit",
    vars_title: "Variablen", vars_lead: "Diese könnt ihr in Willkommens-, Abschieds-, Boost-, Ticket- und Level-Up-Nachrichten verwenden. Unbekannte Platzhalter bleiben unverändert.",
    eb_title: "Embed-Baukasten", eb_lead: "Baut ein Discord-Embed, seht die Vorschau genau so, wie es in Discord aussieht, und kopiert blaids eigenen Script-Code in jeden Befehl, der ein eigenes Script akzeptiert.",
    eb_live_preview: "Live-Vorschau", eb_copy_script: "Script kopieren",
    nav_home: "Start", nav_commands: "Befehle", nav_embed_builder: "Embed-Baukasten",
    nav_status: "Status", nav_tickets: "Tickets", nav_discord: "Discord",
    nav_docs: "Dokumentation", nav_premium: "Premium",
    footer_support: "Support-Server", footer_privacy: "Datenschutz", footer_terms: "AGB",
    footer_cat_docs: "Dokumentation", footer_cat_support: "Support", footer_cat_legal: "Rechtliches", footer_cat_community: "Community",
    footer_getting_started: "Erste Schritte", footer_moderation: "Moderation", footer_antinuke: "Antinuke",
    footer_music: "Musik", footer_levels: "Level", footer_voicemaster: "VoiceMaster",
    footer_get_help: "Hilfe bekommen", footer_refunds: "Rückerstattung", footer_join_discord: "Unserem Discord beitreten",
    features_eyebrow: "Alles in einem Bot", features_title: "Ersetzt ein halbes Dutzend andere Bots",
    features_lead: "Jede Kategorie unten ist ein echter, funktionierender Teil von blaid - kein Zukunftsversprechen.",
    feat_mod_title: "Moderation & Sicherheit", feat_mod_desc: "Volle Moderations-Werkzeuge, Antinuke, Antiraid, Honeypots und eine Verifizierungs-Schranke für riskante neue Konten.",
    feat_tickets_title: "Tickets & VoiceMaster", feat_tickets_desc: "Baut Ticket-Panels visuell auf dieser Seite, plus Join-to-Create-Sprachkanäle mit voller Besitzer-Kontrolle.",
    feat_levels_title: "Level & Wirtschaft", feat_levels_desc: "XP, eigene Level-Up-Karten, Rollen-Belohnungen und eine volle Wirtschaft mit 12 Glücksspielen.",
    feat_fun_title: "Spaß & Nützliches", feat_fun_desc: "Tic-Tac-Toe, BlackTea, KI-Antworten, Reaction-/Button-Rollen und ein komplettes Embed-Script-System.",
    home_title: "blaid ist Discords führende All-in-One-App",
    home_lead: "Der führende Bot für Verwaltung und Engagement. Entwickelt, um das Erlebnis eurer Community zu verbessern, die Serververwaltung zu vereinfachen und euch Zugang zu Premium-Funktionen für jeden Bedarf zu geben.",
    home_invite_btn: "Zu Discord einladen",
    premium_title: "blaid Premium",
    premium_lead: "Zwei unabhängige Pläne, komplett über Discords eigene Kaufabwicklung - wir sehen eure Zahlungsdaten nie.",
    premium_howto_eyebrow: "So bekommt ihr Premium",
    premium_howto_step: "Führt ,premium in eurem Server aus, wählt einen Plan, und klickt auf den Kaufen-Knopf - Discord übernimmt die Bezahlung, und Premium wird automatisch freigeschaltet, sobald die Zahlung durch ist.",
    premium_server_name: "Server Premium",
    premium_server_blurb: "Erhöht Limits und schaltet Premium-Funktionen für euren ganzen Server frei.",
    premium_customize_name: "Customize",
    premium_customize_blurb: "Gebt blaid eine eigene Identität nur für euren Server.",
    premium_get_server: "Server Premium holen",
    premium_get_customize: "Customize holen",
  },
  fr: {
    status_subtitle: "Disponibilité et performance en temps réel sur toute la plateforme blaid.",
    status_incidents_title: "Incidents en cours",
    status_group_core: "Infrastructure principale", status_svc_bot: "Bot", status_svc_database: "Base de données", status_svc_backend: "Backend du site",
    status_group_platform: "Service de plateforme", status_svc_image: "API image",
    status_group_integrations: "Intégrations de plateforme", status_unmonitored: "Non surveillé individuellement",
    docs_cat_start: "PREMIERS PAS", docs_cat_security: "SÉCURITÉ", docs_cat_serverconfig: "CONFIGURATION DU SERVEUR",
    docs_cat_misc: "DIVERS", docs_cat_resources: "RESSOURCES", docs_cat_reference: "RÉFÉRENCE", docs_cat_premium: "PREMIUM",
    docs_crumb: "Docs", docs_search_ph: "Rechercher dans la doc...",
    tix_title: "Créateur de tickets", tix_lead: "Créez un panneau de tickets complet - options, formulaires, tout - visuellement, et envoyez-le directement sur votre serveur.",
    tix_login_eyebrow: "Connectez-vous pour commencer", tix_login_step: "Connectez-vous avec Discord pour choisir un serveur que vous gérez et créer un panneau de tickets pour celui-ci.",
    tix_login_btn: "Se connecter avec Discord",
    cmds_title: "Commandes", cmds_search_ph: "Rechercher des commandes...",
    status_title: "Statut", status_checking: "Vérification...", status_servers: "Serveurs",
    status_users: "Utilisateurs", status_latency: "Latence", status_uptime: "Disponibilité",
    vars_title: "Variables", vars_lead: "À utiliser dans les messages de bienvenue, d'adieu, de boost, de ticket et de passage de niveau. Les paramètres inconnus restent inchangés.",
    eb_title: "Créateur d'embed", eb_lead: "Créez un embed Discord, prévisualisez-le exactement comme il apparaîtra sur Discord, et copiez le format de script propre à blaid dans toute commande qui accepte un script personnalisé.",
    eb_live_preview: "Aperçu en direct", eb_copy_script: "Copier le script",
    nav_home: "Accueil", nav_commands: "Commandes", nav_embed_builder: "Créateur d'embed",
    nav_status: "Statut", nav_tickets: "Tickets", nav_discord: "Discord",
    nav_docs: "Documentation", nav_premium: "Premium",
    footer_support: "Serveur de support", footer_privacy: "Confidentialité", footer_terms: "Conditions",
    footer_cat_docs: "Documentation", footer_cat_support: "Support", footer_cat_legal: "Mentions légales", footer_cat_community: "Communauté",
    footer_getting_started: "Premiers pas", footer_moderation: "Modération", footer_antinuke: "Antinuke",
    footer_music: "Musique", footer_levels: "Niveaux", footer_voicemaster: "VoiceMaster",
    footer_get_help: "Obtenir de l'aide", footer_refunds: "Remboursements", footer_join_discord: "Rejoindre notre Discord",
    features_eyebrow: "Tout dans un seul bot", features_title: "Conçu pour remplacer une demi-douzaine de bots",
    features_lead: "Chaque catégorie ci-dessous fait vraiment partie de blaid, pas une promesse future.",
    feat_mod_title: "Modération & Sécurité", feat_mod_desc: "Suite de modération complète, antinuke, antiraid, honeypots, et une porte de vérification pour les comptes récents à risque.",
    feat_tickets_title: "Tickets & VoiceMaster", feat_tickets_desc: "Créez des panneaux de tickets visuellement sur ce site, plus des salons vocaux à la demande avec contrôle total.",
    feat_levels_title: "Niveaux & Économie", feat_levels_desc: "XP, cartes de niveau personnalisées, récompenses de rôles, et une économie complète avec 12 jeux d'argent.",
    feat_fun_title: "Fun & Utilitaires", feat_fun_desc: "Morpion, BlackTea, réponses IA, rôles par réaction/bouton, et un système de script d'embed complet.",
    home_title: "blaid est l'application tout-en-un incontournable de Discord",
    home_lead: "Découvrez le bot de référence pour la gestion et l'engagement. Conçu pour améliorer l'expérience de votre communauté, simplifier la gestion du serveur et vous donner accès à des fonctionnalités premium pour chaque besoin.",
    home_invite_btn: "Inviter sur Discord",
    premium_title: "blaid Premium",
    premium_lead: "Deux plans indépendants, achetés entièrement via le paiement natif de Discord - nous ne voyons jamais vos informations de paiement.",
    premium_howto_eyebrow: "Comment obtenir Premium",
    premium_howto_step: "Exécutez ,premium sur votre serveur, choisissez un plan et cliquez sur le bouton d'achat - Discord gère le paiement, et Premium s'active automatiquement dès que le paiement est validé.",
    premium_server_name: "Server Premium",
    premium_server_blurb: "Augmente les limites et débloque des fonctionnalités premium pour tout votre serveur.",
    premium_customize_name: "Customize",
    premium_customize_blurb: "Donnez à blaid une identité personnalisée, propre à votre serveur.",
    premium_get_server: "Obtenir Server Premium",
    premium_get_customize: "Obtenir Customize",
  },
  es: {
    status_subtitle: "Disponibilidad y rendimiento en tiempo real de toda la plataforma blaid.",
    status_incidents_title: "Incidentes activos",
    status_group_core: "Infraestructura principal", status_svc_bot: "Bot", status_svc_database: "Base de datos", status_svc_backend: "Backend del sitio",
    status_group_platform: "Servicio de plataforma", status_svc_image: "API de imágenes",
    status_group_integrations: "Integraciones de plataforma", status_unmonitored: "No monitoreado de forma independiente",
    docs_cat_start: "PRIMEROS PASOS", docs_cat_security: "SEGURIDAD", docs_cat_serverconfig: "CONFIGURACIÓN DEL SERVIDOR",
    docs_cat_misc: "VARIOS", docs_cat_resources: "RECURSOS", docs_cat_reference: "REFERENCIA", docs_cat_premium: "PREMIUM",
    docs_crumb: "Docs", docs_search_ph: "Buscar en la documentación...",
    tix_title: "Creador de tickets", tix_lead: "Crea un panel de tickets completo - opciones, formularios, todo - visualmente, y envíalo directamente a tu servidor.",
    tix_login_eyebrow: "Inicia sesión para empezar", tix_login_step: "Inicia sesión con Discord para elegir un servidor que administres y crear un panel de tickets para él.",
    tix_login_btn: "Iniciar sesión con Discord",
    cmds_title: "Comandos", cmds_search_ph: "Buscar comandos...",
    status_title: "Estado", status_checking: "Comprobando...", status_servers: "Servidores",
    status_users: "Usuarios", status_latency: "Latencia", status_uptime: "Tiempo activo",
    vars_title: "Variables", vars_lead: "Úsalas en mensajes de bienvenida, despedida, boost, tickets y subida de nivel. Los marcadores desconocidos se dejan sin cambios.",
    eb_title: "Creador de embeds", eb_lead: "Crea un embed de Discord, previsualízalo exactamente como se verá en Discord, y copia el formato de script propio de blaid en cualquier comando que acepte un script personalizado.",
    eb_live_preview: "Vista previa en vivo", eb_copy_script: "Copiar script",
    nav_home: "Inicio", nav_commands: "Comandos", nav_embed_builder: "Creador de embeds",
    nav_status: "Estado", nav_tickets: "Tickets", nav_discord: "Discord",
    nav_docs: "Documentación", nav_premium: "Premium",
    footer_support: "Servidor de soporte", footer_privacy: "Privacidad", footer_terms: "Términos",
    footer_cat_docs: "Documentación", footer_cat_support: "Soporte", footer_cat_legal: "Legal", footer_cat_community: "Comunidad",
    footer_getting_started: "Primeros pasos", footer_moderation: "Moderación", footer_antinuke: "Antinuke",
    footer_music: "Música", footer_levels: "Niveles", footer_voicemaster: "VoiceMaster",
    footer_get_help: "Obtener ayuda", footer_refunds: "Reembolsos", footer_join_discord: "Únete a nuestro Discord",
    features_eyebrow: "Todo en un solo bot", features_title: "Hecho para reemplazar media docena de bots",
    features_lead: "Cada categoría de abajo es una parte real y funcional de blaid, no una promesa futura.",
    feat_mod_title: "Moderación y Seguridad", feat_mod_desc: "Suite de moderación completa, antinuke, antiraid, honeypots, y una puerta de verificación para cuentas nuevas riesgosas.",
    feat_tickets_title: "Tickets y VoiceMaster", feat_tickets_desc: "Crea paneles de tickets visualmente en este sitio, además de canales de voz bajo demanda con control total.",
    feat_levels_title: "Niveles y Economía", feat_levels_desc: "XP, tarjetas de nivel personalizadas, recompensas de roles, y una economía completa con 12 juegos de azar.",
    feat_fun_title: "Diversión y Utilidad", feat_fun_desc: "Tres en raya, BlackTea, respuestas de IA, roles por reacción/botón, y un sistema completo de scripts de embeds.",
    home_title: "blaid es la app todo-en-uno líder de Discord",
    home_lead: "Conoce el bot líder en gestión y participación. Diseñado para mejorar la experiencia de tu comunidad, simplificar la gestión del servidor y darte acceso a funciones premium para cada necesidad.",
    home_invite_btn: "Invitar a Discord",
    premium_title: "blaid Premium",
    premium_lead: "Dos planes independientes, comprados totalmente a través del sistema de pago propio de Discord - nunca vemos tus datos de pago.",
    premium_howto_eyebrow: "Cómo conseguir Premium",
    premium_howto_step: "Ejecuta ,premium en tu servidor, elige un plan y haz clic en el botón de compra - Discord gestiona el pago, y Premium se activa automáticamente en cuanto el pago se procesa.",
    premium_server_name: "Server Premium",
    premium_server_blurb: "Aumenta los límites y desbloquea funciones premium para todo tu servidor.",
    premium_customize_name: "Customize",
    premium_customize_blurb: "Dale a blaid una identidad personalizada solo para tu servidor.",
    premium_get_server: "Obtener Server Premium",
    premium_get_customize: "Obtener Customize",
  },
  pt: {
    status_subtitle: "Disponibilidade e desempenho em tempo real de toda a plataforma blaid.",
    status_incidents_title: "Incidentes ativos",
    status_group_core: "Infraestrutura principal", status_svc_bot: "Bot", status_svc_database: "Banco de dados", status_svc_backend: "Backend do site",
    status_group_platform: "Serviço de plataforma", status_svc_image: "API de imagem",
    status_group_integrations: "Integrações de plataforma", status_unmonitored: "Não monitorado individualmente",
    docs_cat_start: "PRIMEIROS PASSOS", docs_cat_security: "SEGURANÇA", docs_cat_serverconfig: "CONFIGURAÇÃO DO SERVIDOR",
    docs_cat_misc: "DIVERSOS", docs_cat_resources: "RECURSOS", docs_cat_reference: "REFERÊNCIA", docs_cat_premium: "PREMIUM",
    docs_crumb: "Docs", docs_search_ph: "Buscar na documentação...",
    tix_title: "Criador de tickets", tix_lead: "Crie um painel de tickets completo - opções, formulários, tudo - visualmente, e envie direto para o seu servidor.",
    tix_login_eyebrow: "Faça login para começar", tix_login_step: "Entre com o Discord para escolher um servidor que você administra e criar um painel de tickets para ele.",
    tix_login_btn: "Entrar com o Discord",
    cmds_title: "Comandos", cmds_search_ph: "Buscar comandos...",
    status_title: "Status", status_checking: "Verificando...", status_servers: "Servidores",
    status_users: "Usuários", status_latency: "Latência", status_uptime: "Tempo ativo",
    vars_title: "Variáveis", vars_lead: "Use-as em mensagens de boas-vindas, despedida, boost, tickets e level-up. Marcadores desconhecidos permanecem inalterados.",
    eb_title: "Criador de embed", eb_lead: "Crie um embed do Discord, veja a pré-visualização exatamente como aparecerá no Discord, e copie o formato de script próprio do blaid em qualquer comando que aceite um script personalizado.",
    eb_live_preview: "Pré-visualização ao vivo", eb_copy_script: "Copiar script",
    nav_home: "Início", nav_commands: "Comandos", nav_embed_builder: "Criador de embed",
    nav_status: "Status", nav_tickets: "Tickets", nav_discord: "Discord",
    nav_docs: "Documentação", nav_premium: "Premium",
    footer_support: "Servidor de suporte", footer_privacy: "Privacidade", footer_terms: "Termos",
    footer_cat_docs: "Documentação", footer_cat_support: "Suporte", footer_cat_legal: "Legal", footer_cat_community: "Comunidade",
    footer_getting_started: "Primeiros passos", footer_moderation: "Moderação", footer_antinuke: "Antinuke",
    footer_music: "Música", footer_levels: "Níveis", footer_voicemaster: "VoiceMaster",
    footer_get_help: "Obter ajuda", footer_refunds: "Reembolsos", footer_join_discord: "Entre no nosso Discord",
    features_eyebrow: "Tudo em um só bot", features_title: "Feito para substituir meia dúzia de bots",
    features_lead: "Cada categoria abaixo é uma parte real e funcional do blaid, não uma promessa futura.",
    feat_mod_title: "Moderação e Segurança", feat_mod_desc: "Suite de moderação completa, antinuke, antiraid, honeypots, e um portão de verificação para contas novas arriscadas.",
    feat_tickets_title: "Tickets e VoiceMaster", feat_tickets_desc: "Crie painéis de tickets visualmente neste site, além de canais de voz sob demanda com controle total.",
    feat_levels_title: "Níveis e Economia", feat_levels_desc: "XP, cartões de nível personalizados, recompensas de cargos, e uma economia completa com 12 jogos de azar.",
    feat_fun_title: "Diversão e Utilidade", feat_fun_desc: "Jogo da velha, BlackTea, respostas de IA, cargos por reação/botão, e um sistema completo de scripts de embed.",
    home_title: "blaid é o app tudo-em-um líder do Discord",
    home_lead: "Conheça o bot líder em gestão e engajamento. Feito para elevar a experiência da sua comunidade, simplificar a gestão do servidor e dar acesso a recursos premium para cada necessidade.",
    home_invite_btn: "Convidar para o Discord",
    premium_title: "blaid Premium",
    premium_lead: "Dois planos independentes, comprados totalmente pelo sistema de pagamento do próprio Discord - nunca vemos seus dados de pagamento.",
    premium_howto_eyebrow: "Como conseguir o Premium",
    premium_howto_step: "Execute ,premium no seu servidor, escolha um plano e clique no botão de compra - o Discord cuida do pagamento, e o Premium é ativado automaticamente assim que o pagamento é confirmado.",
    premium_server_name: "Server Premium",
    premium_server_blurb: "Aumenta os limites e libera recursos premium para todo o seu servidor.",
    premium_customize_name: "Customize",
    premium_customize_blurb: "Dê ao blaid uma identidade personalizada só para o seu servidor.",
    premium_get_server: "Obter Server Premium",
    premium_get_customize: "Obter Customize",
  },
};

function applyTranslations(lang) {
  const dict = TRANSLATIONS[lang] || TRANSLATIONS.en;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (dict[key]) el.textContent = dict[key];
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (dict[key]) el.placeholder = dict[key];
  });
}

function initLangSelect() {
  const select = document.querySelector("#lang-select");
  if (!select) return;

  const saved = localStorage.getItem("blaid_lang") || "en";
  select.value = saved;
  applyTranslations(saved);

  select.addEventListener("change", () => {
    localStorage.setItem("blaid_lang", select.value);
    applyTranslations(select.value);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initLoader();
  initTopMenu();
  initDotMenu();
  initDocsMobileNav();
  initDocsSections();
  applyLinks();
  initReveal();
  initDotField();
  loadCommands();
  loadStatus();
  initEmbedBuilder();
  loadVariables();
  initTicketBuilder();
  initSiteLoginChip();
  initLangSelect();
});
