// Ticket builder logic - Panel / Forms / Options, matching the bot's
// real data model field-for-field (see website/backend/main.py's
// TicketPanelSettings / TicketOptionSettings / TicketFormSettings).

const BUTTON_ACTIONS = ["claim", "close", "reopen", "delete"];
const MESSAGE_TYPES = [
  ["greeting", "Greeting"], ["greeting_dm", "Greeting DM"], ["claim", "Claim"], ["move", "Move"],
  ["close", "Close"], ["close_dm", "Close DM"], ["reopen", "Reopen"], ["reopen_dm", "Reopen DM"],
  ["auto_close", "Auto-Close"], ["auto_delete", "Auto-Delete"], ["inactivity", "Inactivity"],
  ["required_roles", "Required Roles (denial message)"],
];
const FIELD_TYPES = [
  ["short_text", "Short Text"], ["long_text", "Long Text"], ["checkbox", "Checkbox"],
  ["select", "Select"], ["role_select", "Role Select"], ["user_select", "User Select"], ["channel_select", "Channel Select"],
];

let formCount = 0;
let optionCount = 0;
let currentGuildId = null;
let guildCategories = [];
let guildRoles = [];

function el(html) {
  const div = document.createElement("div");
  div.innerHTML = html.trim();
  return div.firstElementChild;
}

function categoryOptions(selectedId) {
  const opts = ['<option value="">None</option>'];
  guildCategories.forEach((c) => opts.push(`<option value="${c.id}" ${c.id === selectedId ? "selected" : ""}>${c.name}</option>`));
  return opts.join("");
}

function roleCheckboxes(name, selectedIds = []) {
  if (!guildRoles.length) return '<p style="color: var(--text-faint); font-size: 0.84rem;">No roles loaded yet - pick a server first.</p>';
  return guildRoles
    .map(
      (r) => `
      <label class="role-check">
        <input type="checkbox" name="${name}" value="${r.id}" ${selectedIds.includes(r.id) ? "checked" : ""}>
        ${r.name}
      </label>`
    )
    .join("");
}

function collectCheckedRoles(container, name) {
  return [...container.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);
}

// ---------------------------------------------------------- Forms

function addFormCard(container) {
  formCount += 1;
  const key = `form_${formCount}`;
  const card = el(`
    <div class="entity-card" data-form-key="${key}">
      <div class="entity-card-top">
        <input type="text" class="entity-title-input form-name" placeholder="Form name" value="Form ${formCount}">
        <button class="question-remove entity-remove" type="button" title="Remove form">&times;</button>
      </div>
      <div class="field-row">
        <div class="field-group">
          <label>Modal title</label>
          <input type="text" class="form-modal-title" placeholder="Open a Ticket" value="Open a Ticket">
        </div>
        <div class="field-group" style="display:flex; align-items:flex-end;">
          <label style="display:flex; align-items:center; gap:8px; margin:0;">
            <input type="checkbox" class="form-filtering"> Enable word filtering
          </label>
        </div>
      </div>
      <div class="fields-list"></div>
      <button class="btn secondary add-field-btn" type="button" style="margin-top: 10px;">+ Add field</button>
    </div>
  `);

  card.querySelector(".entity-remove").addEventListener("click", () => card.remove());
  card.querySelector(".add-field-btn").addEventListener("click", () => addFieldRow(card.querySelector(".fields-list")));
  container.appendChild(card);
  addFieldRow(card.querySelector(".fields-list"));
}

function addFieldRow(container) {
  const typeOptions = FIELD_TYPES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  const row = el(`
    <div class="question-row field-def-row">
      <div class="field-group" style="max-width:160px;">
        <label>Type</label>
        <select class="field-type">${typeOptions}</select>
      </div>
      <div class="field-group">
        <label>Label</label>
        <input type="text" class="field-label" placeholder="What's the issue?">
      </div>
      <div class="field-group" style="display:flex; align-items:flex-end;">
        <label style="display:flex; align-items:center; gap:6px; margin:0; white-space:nowrap;">
          <input type="checkbox" class="field-required" checked> Required
        </label>
      </div>
      <button class="question-remove" type="button" title="Remove">&times;</button>
    </div>
  `);
  row.querySelector(".question-remove").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function collectForms() {
  return [...document.querySelectorAll("#forms-list .entity-card")].map((card) => ({
    key: card.dataset.formKey,
    name: card.querySelector(".form-name").value.trim() || "Untitled Form",
    modal_title: card.querySelector(".form-modal-title").value.trim() || "Ticket Form",
    enable_filtering: card.querySelector(".form-filtering").checked,
    fields: [...card.querySelectorAll(".field-def-row")]
      .map((row) => ({
        field_type: row.querySelector(".field-type").value,
        label: row.querySelector(".field-label").value.trim(),
        required: row.querySelector(".field-required").checked,
      }))
      .filter((f) => f.label),
  }));
}

function formSelectOptions(selectedKey) {
  const forms = collectForms();
  const opts = ['<option value="">None</option>'];
  forms.forEach((f) => opts.push(`<option value="${f.key}" ${f.key === selectedKey ? "selected" : ""}>${f.name}</option>`));
  return opts.join("");
}

// ---------------------------------------------------------- Options

function addOptionCard(container) {
  optionCount += 1;
  const buttonRows = BUTTON_ACTIONS.map(
    (action) => `
    <div class="button-ux-row" data-action="${action}">
      <span class="button-ux-label">${action.charAt(0).toUpperCase() + action.slice(1)}</span>
      <input type="text" class="bux-label" placeholder="Label" value="${action.charAt(0).toUpperCase() + action.slice(1)}">
      <input type="text" class="bux-emoji" placeholder="Emoji (optional)">
      <select class="bux-color">
        <option value="blue">Blue</option><option value="gray">Gray</option><option value="green">Green</option><option value="red">Red</option>
      </select>
      <label class="bux-reason"><input type="checkbox"> Requires reason</label>
    </div>`
  ).join("");

  const messageRows = MESSAGE_TYPES.map(
    ([key, label]) => `
    <div class="field-group message-row" data-msg-key="${key}">
      <label>${label}</label>
      <textarea rows="2" placeholder="Leave empty to use the default"></textarea>
    </div>`
  ).join("");

  const card = el(`
    <div class="entity-card" data-option-key="option_${optionCount}">
      <div class="entity-card-top">
        <input type="text" class="entity-title-input option-name" placeholder="Option name" value="Option ${optionCount}">
        <button class="question-remove entity-remove" type="button" title="Remove option">&times;</button>
      </div>

      <div class="option-subtabs">
        <button class="option-subtab active" data-sub="style">Style</button>
        <button class="option-subtab" data-sub="categories">Categories</button>
        <button class="option-subtab" data-sub="naming">Naming</button>
        <button class="option-subtab" data-sub="permissions">Permissions</button>
        <button class="option-subtab" data-sub="roles">Roles</button>
        <button class="option-subtab" data-sub="buttons">Button UX</button>
        <button class="option-subtab" data-sub="form">Form</button>
        <button class="option-subtab" data-sub="messages">Messages</button>
        <button class="option-subtab" data-sub="automation">Automation</button>
      </div>

      <div class="option-sub-content" data-sub-content="style">
        <div class="field-row">
          <div class="field-group">
            <label>Button/dropdown label</label>
            <input type="text" class="opt-label" placeholder="General Support">
          </div>
          <div class="field-group">
            <label>Emoji (optional)</label>
            <input type="text" class="opt-emoji">
          </div>
        </div>
        <div class="field-row">
          <div class="field-group">
            <label>Button style</label>
            <select class="opt-style">
              <option value="blue">Blue</option><option value="gray">Gray</option><option value="green">Green</option><option value="red">Red</option>
            </select>
          </div>
          <div class="field-group">
            <label>Description (dropdown only)</label>
            <input type="text" class="opt-description">
          </div>
        </div>
      </div>

      <div class="option-sub-content" data-sub-content="categories" style="display:none;">
        <div class="field-row">
          <div class="field-group">
            <label>Default category</label>
            <select class="opt-default-category">${categoryOptions()}</select>
          </div>
          <div class="field-group">
            <label>Claim category</label>
            <select class="opt-claim-category">${categoryOptions()}</select>
          </div>
        </div>
        <div class="field-row">
          <div class="field-group">
            <label>Close category</label>
            <select class="opt-close-category">${categoryOptions()}</select>
          </div>
          <div class="field-group">
            <label>Transcript channel</label>
            <select class="opt-transcript-channel"></select>
          </div>
        </div>
      </div>

      <div class="option-sub-content" data-sub-content="naming" style="display:none;">
        <div class="field-group">
          <label>Channel name format</label>
          <input type="text" class="opt-naming" value="{ticket.case}-{ticket.author.name}">
        </div>
        <div class="field-row">
          <div class="field-group">
            <label>Claim rename template (optional)</label>
            <input type="text" class="opt-claim-rename">
          </div>
          <div class="field-group">
            <label>Close rename template (optional)</label>
            <input type="text" class="opt-close-rename">
          </div>
        </div>
      </div>

      <div class="option-sub-content" data-sub-content="permissions" style="display:none;">
        <div class="checkbox-row">
          <label><input type="checkbox" class="opt-creator-can-close" checked> Creator can close</label>
          <label><input type="checkbox" class="opt-close-on-leave"> Auto-close if creator leaves</label>
        </div>
      </div>

      <div class="option-sub-content" data-sub-content="roles" style="display:none;">
        <h4 class="role-group-title">Required roles</h4>
        <label class="checkbox-row" style="margin-bottom:8px;"><input type="checkbox" class="opt-require-all"> Require ALL selected roles (default: any)</label>
        <div class="role-grid required-roles-grid">${roleCheckboxes("required_" + optionCount)}</div>

        <h4 class="role-group-title">Support roles</h4>
        <div class="checkbox-row" style="margin-bottom:8px;">
          <label><input type="checkbox" class="opt-keep-visible" checked> Keep visible on claim</label>
          <label><input type="checkbox" class="opt-can-speak" checked> Can speak on claim</label>
        </div>
        <div class="role-grid support-roles-grid">${roleCheckboxes("support_" + optionCount)}</div>

        <h4 class="role-group-title">Trainee roles</h4>
        <div class="checkbox-row" style="margin-bottom:8px;">
          <label><input type="checkbox" class="opt-trainee-claim"> Can claim</label>
          <label><input type="checkbox" class="opt-trainee-close"> Can close</label>
          <label><input type="checkbox" class="opt-trainee-speak"> Can speak</label>
        </div>
        <div class="role-grid trainee-roles-grid">${roleCheckboxes("trainee_" + optionCount)}</div>
      </div>

      <div class="option-sub-content" data-sub-content="buttons" style="display:none;">
        ${buttonRows}
      </div>

      <div class="option-sub-content" data-sub-content="form" style="display:none;">
        <div class="field-group">
          <label>Attached form</label>
          <select class="opt-form-select">${formSelectOptions()}</select>
        </div>
      </div>

      <div class="option-sub-content" data-sub-content="messages" style="display:none;">
        ${messageRows}
      </div>

      <div class="option-sub-content" data-sub-content="automation" style="display:none;">
        <div class="field-row">
          <div class="field-group">
            <label>Auto-close (minutes, optional)</label>
            <input type="number" class="opt-auto-close" min="0">
          </div>
          <div class="field-group">
            <label>Auto-delete (minutes, optional)</label>
            <input type="number" class="opt-auto-delete" min="0">
          </div>
          <div class="field-group">
            <label>Inactivity (minutes, optional)</label>
            <input type="number" class="opt-inactivity" min="0">
          </div>
        </div>
      </div>
    </div>
  `);

  card.querySelector(".entity-remove").addEventListener("click", () => card.remove());
  card.querySelectorAll(".option-subtab").forEach((tab) => {
    tab.addEventListener("click", () => {
      card.querySelectorAll(".option-subtab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      card.querySelectorAll(".option-sub-content").forEach((c) => (c.style.display = "none"));
      card.querySelector(`[data-sub-content="${tab.dataset.sub}"]`).style.display = "block";
    });
  });

  // Populate transcript channel select once channels are loaded (see loadGuildData)
  card.dataset.needsChannelSelect = "true";

  container.appendChild(card);
  refreshTranscriptChannelSelects();
}

function refreshTranscriptChannelSelects() {
  const channelSelect = document.querySelector("#channel-select");
  if (!channelSelect) return;
  const optionsHtml = '<option value="">None</option>' + channelSelect.innerHTML;
  document.querySelectorAll(".opt-transcript-channel").forEach((sel) => {
    if (!sel.dataset.populated) {
      sel.innerHTML = optionsHtml;
      sel.dataset.populated = "true";
    }
  });
}

function collectOptions() {
  return [...document.querySelectorAll("#options-list .entity-card")].map((card) => {
    const buttonConfigs = {};
    card.querySelectorAll(".button-ux-row").forEach((row) => {
      buttonConfigs[row.dataset.action] = {
        label: row.querySelector(".bux-label").value.trim() || row.dataset.action,
        emoji: row.querySelector(".bux-emoji").value.trim() || null,
        color: row.querySelector(".bux-color").value,
        requires_reason: row.querySelector(".bux-reason input").checked,
      };
    });

    const messages = {};
    card.querySelectorAll(".message-row").forEach((row) => {
      const value = row.querySelector("textarea").value.trim();
      if (value) messages[row.dataset.msgKey] = value;
    });

    return {
      name: card.querySelector(".option-name").value.trim() || "Option",
      label: card.querySelector(".opt-label").value.trim() || "Support",
      emoji: card.querySelector(".opt-emoji").value.trim() || null,
      button_style: card.querySelector(".opt-style").value,
      button_description: card.querySelector(".opt-description").value.trim() || null,
      default_category_id: card.querySelector(".opt-default-category").value || null,
      claim_category_id: card.querySelector(".opt-claim-category").value || null,
      close_category_id: card.querySelector(".opt-close-category").value || null,
      transcript_channel_id: card.querySelector(".opt-transcript-channel").value || null,
      channel_name_format: card.querySelector(".opt-naming").value.trim() || "{ticket.case}-{ticket.author.name}",
      claim_rename_template: card.querySelector(".opt-claim-rename").value.trim() || null,
      close_rename_template: card.querySelector(".opt-close-rename").value.trim() || null,
      creator_can_close: card.querySelector(".opt-creator-can-close").checked,
      close_on_leave: card.querySelector(".opt-close-on-leave").checked,
      require_all_roles: card.querySelector(".opt-require-all").checked,
      required_role_ids: collectCheckedRoles(card.querySelector(".required-roles-grid"), card.querySelector(".required-roles-grid input").name),
      keep_staff_visible_on_claim: card.querySelector(".opt-keep-visible").checked,
      staff_can_speak_on_claim: card.querySelector(".opt-can-speak").checked,
      support_role_ids: collectCheckedRoles(card.querySelector(".support-roles-grid"), card.querySelector(".support-roles-grid input")?.name || ""),
      trainees_can_claim: card.querySelector(".opt-trainee-claim").checked,
      trainees_can_close: card.querySelector(".opt-trainee-close").checked,
      trainees_can_speak: card.querySelector(".opt-trainee-speak").checked,
      trainee_role_ids: collectCheckedRoles(card.querySelector(".trainee-roles-grid"), card.querySelector(".trainee-roles-grid input")?.name || ""),
      button_configs: buttonConfigs,
      form_key: card.querySelector(".opt-form-select").value || null,
      messages,
      auto_close_timer: parseInt(card.querySelector(".opt-auto-close").value) || null,
      auto_delete_timer: parseInt(card.querySelector(".opt-auto-delete").value) || null,
      inactivity_timer: parseInt(card.querySelector(".opt-inactivity").value) || null,
    };
  });
}

// ---------------------------------------------------------- Panel preview

function updatePanelPreview() {
  const title = document.querySelector("#p-title")?.value || "";
  const desc = document.querySelector("#p-desc")?.value || "";
  const buttonLabel = document.querySelector("#p-button-label")?.value || "Open Ticket";
  document.querySelector("#pp-title").textContent = title;
  document.querySelector("#pp-desc").textContent = desc;
  document.querySelector("#pp-button").textContent = buttonLabel;
}

// ---------------------------------------------------------- guild data loading

async function loadGuildData(guildId) {
  currentGuildId = guildId;
  const channelSelect = document.querySelector("#channel-select");
  const logChannelSelect = document.querySelector("#p-log-channel");
  const categorySelect = document.querySelector("#p-category");
  const closedCategorySelect = document.querySelector("#p-closed-category");

  [channelSelect, logChannelSelect].forEach((s) => (s.innerHTML = "<option>Loading...</option>"));
  [categorySelect, closedCategorySelect].forEach((s) => (s.innerHTML = "<option>Loading...</option>"));

  try {
    const [chRes, catRes, roleRes] = await Promise.all([
      fetch(`${API_BASE}/api/guilds/${guildId}/channels`, { credentials: "include" }),
      fetch(`${API_BASE}/api/guilds/${guildId}/categories`, { credentials: "include" }),
      fetch(`${API_BASE}/api/guilds/${guildId}/roles`, { credentials: "include" }),
    ]);
    const channels = (await chRes.json()).channels || [];
    guildCategories = (await catRes.json()).categories || [];
    guildRoles = (await roleRes.json()).roles || [];

    const channelOptsHtml = channels.map((c) => `<option value="${c.id}">#${c.name}</option>`).join("");
    channelSelect.innerHTML = channelOptsHtml;
    logChannelSelect.innerHTML = '<option value="">None</option>' + channelOptsHtml;
    categorySelect.innerHTML = categoryOptions();
    closedCategorySelect.innerHTML = categoryOptions();

    document.querySelectorAll(".opt-transcript-channel").forEach((sel) => (sel.dataset.populated = ""));
    refreshTranscriptChannelSelects();
    document.querySelectorAll(".opt-default-category, .opt-claim-category, .opt-close-category").forEach((sel) => {
      sel.innerHTML = categoryOptions();
    });
  } catch (err) {
    channelSelect.innerHTML = "<option>Couldn't load</option>";
  }
}

// ---------------------------------------------------------- init

function initTicketBuilder() {
  const app = document.querySelector("#tickets-app");
  const loggedOut = document.querySelector("#tickets-logged-out");
  if (!app || !loggedOut) return;

  const loginBtn = document.querySelector("#login-btn");
  if (loginBtn) loginBtn.href = `${API_BASE}/api/auth/login`;

  const guildSelect = document.querySelector("#guild-select");
  const sendStatus = document.querySelector("#send-status");

  document.querySelectorAll(".ticket-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".ticket-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".ticket-tab-content").forEach((c) => (c.style.display = "none"));
      document.querySelector(`#tab-${tab.dataset.tab}`).style.display = "block";
    });
  });

  document.querySelector("#add-form-btn").addEventListener("click", () => addFormCard(document.querySelector("#forms-list")));
  document.querySelector("#add-option-btn").addEventListener("click", () => addOptionCard(document.querySelector("#options-list")));

  ["#p-title", "#p-desc", "#p-button-label"].forEach((sel) => {
    document.querySelector(sel).addEventListener("input", updatePanelPreview);
  });
  updatePanelPreview();

  guildSelect.addEventListener("change", () => loadGuildData(guildSelect.value));

  document.querySelector("#send-btn").addEventListener("click", async () => {
    const panel = {
      title: document.querySelector("#p-title").value,
      description: document.querySelector("#p-desc").value,
      button_label: document.querySelector("#p-button-label").value,
      channel_id: document.querySelector("#channel-select").value,
      log_channel_id: document.querySelector("#p-log-channel").value || null,
      category_id: document.querySelector("#p-category").value || null,
      closed_category_id: document.querySelector("#p-closed-category").value || null,
      delete_delay_seconds: parseInt(document.querySelector("#p-delete-delay").value) || 0,
      max_open_tickets: parseInt(document.querySelector("#p-max-open").value) || 1,
      auto_pin_controls: document.querySelector("#p-auto-pin").checked,
      claims_enabled: document.querySelector("#p-claims-enabled").checked,
      logs_enabled: document.querySelector("#p-logs-enabled").checked,
      log_message_template: document.querySelector("#p-log-message").value.trim() || null,
      channel_name_format: document.querySelector("#p-naming").value.trim() || "{ticket.case}-{ticket.author.name}",
      case_padding: parseInt(document.querySelector("#p-case-padding").value) || 0,
      dropdown_placeholder: document.querySelector("#p-dropdown-placeholder").value.trim() || null,
      mode: document.querySelector("#p-mode").value,
    };

    const payload = {
      guild_id: guildSelect.value,
      panel,
      forms: collectForms(),
      options: collectOptions(),
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

  fetch(`${API_BASE}/api/auth/me`, { credentials: "include" })
    .then((res) => res.json())
    .then((data) => {
      if (!data.logged_in) {
        loggedOut.style.display = "block";
        return;
      }
      app.style.display = "block";
      guildSelect.innerHTML = (data.guilds || []).map((g) => `<option value="${g.id}">${g.name}</option>`).join("");
      if (data.guilds && data.guilds.length) loadGuildData(data.guilds[0].id);
    })
    .catch(() => {
      loggedOut.style.display = "block";
    });
}

document.addEventListener("DOMContentLoaded", initTicketBuilder);
