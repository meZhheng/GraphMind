const statusEl = document.querySelector("#status");
const eventsEl = document.querySelector("#events");
const taskForm = document.querySelector("#taskForm");
const taskInput = document.querySelector("#taskInput");
const runBtn = document.querySelector("#runBtn");
const clearBtn = document.querySelector("#clearBtn");
const confirmPanel = document.querySelector("#confirmPanel");
const confirmCalls = document.querySelector("#confirmCalls");
const allowBtn = document.querySelector("#allowBtn");
const denyBtn = document.querySelector("#denyBtn");

let socket;
let pendingToolCalls = [];
const openBlocks = new Map();
const actInputs = new Map();

function connect() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws/agent`);

  socket.addEventListener("open", () => {
    statusEl.textContent = "Connected";
    runBtn.disabled = false;
  });

  socket.addEventListener("close", () => {
    statusEl.textContent = "Disconnected";
    runBtn.disabled = true;
  });

  socket.addEventListener("message", (event) => {
    handlePayload(JSON.parse(event.data));
  });
}

function handlePayload(payload) {
  if (payload.category === "session") {
    statusEl.textContent = `Session ${payload.session_id.slice(0, 8)}`;
    return;
  }

  if (payload.category === "reasoning_delta") {
    appendDelta("reasoning", "Reasoning", payload.content);
    return;
  }

  if (payload.category === "assistant_delta") {
    appendDelta("assistant", "Assistant", payload.content);
    return;
  }

  if (payload.category === "act_delta") {
    const current = actInputs.get(payload.tool_call_id) || "";
    actInputs.set(payload.tool_call_id, current + payload.content);
    return;
  }

  if (payload.category === "act_end") {
    const rawInput = actInputs.get(payload.tool_call_id) || "{}";
    actInputs.delete(payload.tool_call_id);
    appendEvent("act", "Tool input", prettyJson(rawInput));
    return;
  }

  if (payload.category === "tool_response_delta") {
    appendDelta(
      `tool-${payload.tool_call_id}`,
      "Tool response",
      payload.content,
    );
    return;
  }

  if (payload.category === "confirm") {
    pendingToolCalls = payload.tool_calls || [];
    renderConfirmation(payload);
  }

  appendEvent(payload.category, payload.title || payload.type, payload.content);
}

function appendDelta(key, title, delta) {
  let card = openBlocks.get(key);
  if (!card) {
    card = createEventCard(key, title, "");
    openBlocks.set(key, card);
  }
  const body = card.querySelector(".event-body");
  body.textContent += delta || "";
  scrollEvents();
}

function appendEvent(category, title, content) {
  createEventCard(category, title, formatContent(content));
  scrollEvents();
}

function createEventCard(category, title, content) {
  const card = document.createElement("article");
  card.className = "event-card";
  card.dataset.category = category;

  const heading = document.createElement("div");
  heading.className = "event-title";
  heading.textContent = title || category;

  const body = document.createElement("pre");
  body.className = "event-body";
  body.textContent = content || "";

  card.append(heading, body);
  eventsEl.append(card);
  return card;
}

function renderConfirmation(payload) {
  confirmPanel.classList.remove("hidden");
  confirmCalls.innerHTML = "";

  for (const toolCall of pendingToolCalls) {
    const item = document.createElement("div");
    item.className = "rounded-md border border-amber-500/30 bg-zinc-950 p-3";
    item.innerHTML = `
      <div class="text-sm font-medium text-amber-100">${escapeHtml(toolCall.name)}</div>
      <pre class="mt-2 whitespace-pre-wrap break-words text-xs text-zinc-300">${escapeHtml(toolCall.pretty_input || toolCall.input || "{}")}</pre>
    `;
    confirmCalls.append(item);
  }
}

function sendConfirmation(confirmed) {
  if (!pendingToolCalls.length) {
    return;
  }

  socket.send(
    JSON.stringify({
      type: "confirm",
      results: pendingToolCalls.map((toolCall) => ({
        tool_call_id: toolCall.id,
        confirmed,
      })),
    }),
  );

  confirmPanel.classList.add("hidden");
  pendingToolCalls = [];
}

function formatContent(content) {
  if (content == null) {
    return "";
  }
  if (typeof content === "string") {
    return content;
  }
  return JSON.stringify(content, null, 2);
}

function prettyJson(raw) {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function scrollEvents() {
  eventsEl.scrollTop = eventsEl.scrollHeight;
}

taskForm.addEventListener("submit", (event) => {
  event.preventDefault();
  openBlocks.clear();
  actInputs.clear();
  socket.send(
    JSON.stringify({
      type: "run",
      content: taskInput.value,
    }),
  );
});

clearBtn.addEventListener("click", () => {
  eventsEl.innerHTML = "";
  openBlocks.clear();
  actInputs.clear();
});

allowBtn.addEventListener("click", () => sendConfirmation(true));
denyBtn.addEventListener("click", () => sendConfirmation(false));

runBtn.disabled = true;
connect();
