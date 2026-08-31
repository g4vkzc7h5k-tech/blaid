// Shared behavior across every page: loading screen, nav toggles,
// and (on the commands page) fetching + rendering live command data
// from the backend's /api/commands endpoint.

function initLoader() {
  const loader = document.querySelector(".loader");
  const page = document.querySelector(".page");
  if (!loader || !page) return;

  const reveal = () => {
    loader.classList.add("hidden");
    page.classList.add("revealed");
  };

  // Minimum show time so the loader is a deliberate beat, not a flicker,
  // even on a fast connection - but never blocks longer than ~900ms.
  const minDelay = new Promise((resolve) => setTimeout(resolve, 550));
  const ready = new Promise((resolve) => {
    if (document.readyState === "complete") resolve();
    else window.addEventListener("load", resolve, { once: true });
  });

  Promise.all([minDelay, ready]).then(reveal);
  // Hard fallback in case something above never resolves.
  setTimeout(reveal, 1800);
}

function initTopMenu() {
  const toggle = document.querySelector(".menu-toggle");
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

function initSidebarToggle() {
  const toggle = document.querySelector(".docs-sidebar .menu-toggle");
  const sidebar = document.querySelector(".docs-sidebar");
  if (!toggle || !sidebar) return;

  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("sidebar-collapsed");
  });
}

function applyLinks() {
  const inviteEls = document.querySelectorAll("[data-invite-link]");
  inviteEls.forEach((el) => (el.href = BLADE_LINKS.invite));

  const supportEls = document.querySelectorAll("[data-support-link]");
  supportEls.forEach((el) => {
    if (BLADE_LINKS.support === "#") {
      el.style.display = "none";
    } else {
      el.href = BLADE_LINKS.support;
    }
  });
}

// ---------------------------------------------------------- commands page

const CATEGORY_ICONS = {}; // reserved for future per-category icons

async function loadCommands() {
  const body = document.querySelector(".cmd-body");
  if (!body) return;

  const searchInput = document.querySelector("#cmd-search-input");
  let allCommands = [];

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
      const bar = document.createElement("div");
      bar.className = "category-bar";
      bar.innerHTML = `<span>${category}</span><span class="count">${byCategory[category].length} command${byCategory[category].length === 1 ? "" : "s"}</span>`;
      body.appendChild(bar);

      byCategory[category].forEach((cmd) => {
        const card = document.createElement("div");
        card.className = "cmd-card";

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
        body.appendChild(card);
      });
    });

    body.querySelectorAll(".copy-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy);
        const original = btn.innerHTML;
        btn.textContent = "Copied";
        setTimeout(() => (btn.innerHTML = original), 1200);
      });
    });
  }

  try {
    const res = await fetch(`${API_BASE}/api/commands`);
    const data = await res.json();
    allCommands = data.commands || [];
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

document.addEventListener("DOMContentLoaded", () => {
  initLoader();
  initTopMenu();
  initDotMenu();
  initSidebarToggle();
  applyLinks();
  loadCommands();
});
