const statusEl = document.querySelector("#status");
const mobileStatusEl = document.querySelector("#mobileStatus");
const conversationEl = document.querySelector("#conversation");
const chatScrollEl = document.querySelector("#chatScroll");
const taskForm = document.querySelector("#taskForm");
const taskInput = document.querySelector("#taskInput");
const runBtn = document.querySelector("#runBtn");
const clearBtn = document.querySelector("#clearBtn");
const mobileClearBtn = document.querySelector("#mobileClearBtn");
const confirmPanel = document.querySelector("#confirmPanel");
const confirmCalls = document.querySelector("#confirmCalls");
const allowBtn = document.querySelector("#allowBtn");
const denyBtn = document.querySelector("#denyBtn");
const turnsNav = document.querySelector("#turnsNav");
const contextLabel = document.querySelector("#contextLabel");
const mobileContextLabel = document.querySelector("#mobileContextLabel");
const contextBar = document.querySelector("#contextBar");

let socket;
let pendingToolCalls = [];
let turnCounter = 0;
let activeTurn = null;
let isRunning = false;

const actInputs = new Map();

function connect() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws/agent`);

  socket.addEventListener("open", () => {
    setStatus("Connected");
    runBtn.disabled = false;
  });

  socket.addEventListener("close", () => {
    setStatus("Disconnected");
    runBtn.disabled = true;
  });

  socket.addEventListener("message", (event) => {
    handlePayload(JSON.parse(event.data));
  });
}

function handlePayload(payload) {
  updateContext(payload.context);

  if (payload.category === "session") {
    setStatus(`Session ${payload.session_id.slice(0, 8)}`);
    return;
  }

  if (payload.category === "internal" || payload.category === "event") {
    return;
  }

  if (!activeTurn) {
    activeTurn = createTurn("Agent activity", "");
  }

  switch (payload.category) {
    case "assistant":
      ensureAssistantMessage();
      break;
    case "assistant_delta":
      appendAssistantText(payload.content || "");
      break;
    case "reasoning":
      ensureStep("reasoning", "Reasoning");
      break;
    case "reasoning_delta":
      appendStepText("reasoning", payload.content || "");
      break;
    case "act":
      ensureStep(`act-${payload.tool_call_id}`, payload.title || "Tool call");
      actInputs.set(payload.tool_call_id, "");
      break;
    case "act_delta":
      actInputs.set(
        payload.tool_call_id,
        (actInputs.get(payload.tool_call_id) || "") + (payload.content || ""),
      );
      break;
    case "act_end":
      appendStepText(
        `act-${payload.tool_call_id}`,
        prettyJson(actInputs.get(payload.tool_call_id) || "{}"),
      );
      actInputs.delete(payload.tool_call_id);
      break;
    case "confirm":
      pendingToolCalls = payload.tool_calls || [];
      renderConfirmation(payload);
      appendStepText("approval", formatConfirmationSummary(pendingToolCalls), {
        title: "Waiting for approval",
      });
      break;
    case "tool_response":
      ensureStep(
        `tool-${payload.tool_call_id}`,
        payload.title || "Tool response",
      );
      break;
    case "tool_response_delta":
      appendStepText(`tool-${payload.tool_call_id}`, payload.content || "");
      break;
    case "tool_response_end":
      appendStepText(
        `tool-${payload.tool_call_id}`,
        `\n[${payload.state}]`,
      );
      break;
    case "usage":
      updateTurnMeta(payload.content);
      break;
    case "done":
      finishTurn();
      break;
    case "error":
      appendSystemNotice(payload.content || payload.title || "Error");
      finishTurn();
      break;
    default:
      if (payload.title || payload.content) {
        appendStepText(
          `misc-${payload.category}`,
          formatContent(payload.content),
          { title: payload.title || payload.category },
        );
      }
  }

  scrollToBottom();
}

function createTurn(title, userText) {
  turnCounter += 1;
  const turnId = `turn-${turnCounter}`;

  const wrapper = document.createElement("section");
  wrapper.className = "turn";
  wrapper.id = turnId;
  wrapper.dataset.turn = String(turnCounter);

  const user = document.createElement("article");
  user.className = "message-row user-row";
  user.innerHTML = `
    <div class="message-bubble user-bubble">${escapeHtml(userText)}</div>
  `;

  const assistant = document.createElement("article");
  assistant.className = "message-row assistant-row";
  assistant.innerHTML = `
    <div class="avatar">G</div>
    <div class="assistant-stack">
      <details class="steps-panel hidden">
        <summary>Work details</summary>
        <div class="steps-list"></div>
      </details>
      <div class="message-bubble assistant-bubble">
        <div class="assistant-text assistant-markdown"></div>
      </div>
      <div class="turn-meta"></div>
    </div>
  `;

  wrapper.append(user, assistant);
  conversationEl.append(wrapper);
  addTurnNav(turnId, title || `Round ${turnCounter}`);

  return {
    id: turnId,
    el: wrapper,
    assistantText: assistant.querySelector(".assistant-text"),
    assistantRaw: "",
    stepsPanel: assistant.querySelector(".steps-panel"),
    stepsList: assistant.querySelector(".steps-list"),
    meta: assistant.querySelector(".turn-meta"),
    steps: new Map(),
  };
}

function addTurnNav(turnId, title) {
  const button = document.createElement("button");
  button.className = "turn-nav-item";
  button.type = "button";
  button.textContent = `${turnCounter}. ${compactTitle(title)}`;
  button.addEventListener("click", () => {
    document.querySelector(`#${turnId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  });
  turnsNav.append(button);
}

function ensureAssistantMessage() {
  if (!activeTurn.assistantRaw.trim()) {
    activeTurn.assistantText.innerHTML = "";
  }
}

function appendAssistantText(text) {
  activeTurn.assistantRaw += text;
  renderAssistantMarkdown(activeTurn);
}

function ensureStep(key, title) {
  let step = activeTurn.steps.get(key);
  if (step) {
    return step;
  }

  const item = document.createElement("div");
  item.className = "step-item";
  item.innerHTML = `
    <div class="step-title">${escapeHtml(title)}</div>
    <pre class="step-body"></pre>
  `;
  activeTurn.stepsList.append(item);
  activeTurn.stepsPanel.classList.remove("hidden");
  activeTurn.stepsPanel.open = true;

  step = {
    item,
    body: item.querySelector(".step-body"),
  };
  activeTurn.steps.set(key, step);
  return step;
}

function appendStepText(key, text, options = {}) {
  const step = ensureStep(key, options.title || key);
  step.body.textContent += text;
}

function appendSystemNotice(text) {
  const notice = document.createElement("div");
  notice.className = "system-notice";
  notice.textContent = text;
  conversationEl.append(notice);
}

function updateTurnMeta(usage) {
  if (!usage || !activeTurn) {
    return;
  }
  activeTurn.meta.textContent = `Input ${usage.input_tokens ?? 0} tokens · Output ${usage.output_tokens ?? 0} tokens`;
}

function finishTurn() {
  if (!activeTurn) {
    return;
  }
  activeTurn.assistantRaw = activeTurn.assistantRaw.trim();
  if (!activeTurn.assistantRaw) {
    activeTurn.assistantRaw = "Done.";
  }
  renderAssistantMarkdown(activeTurn);
  isRunning = false;
  runBtn.disabled = false;
  activeTurn = null;
}

function renderConfirmation(payload) {
  confirmPanel.classList.remove("hidden");
  confirmCalls.innerHTML = "";

  for (const toolCall of pendingToolCalls) {
    const item = document.createElement("div");
    item.className = "confirm-call";
    item.innerHTML = `
      <div class="text-sm font-medium text-amber-950">${escapeHtml(toolCall.name)}</div>
      <pre class="mt-2 whitespace-pre-wrap break-words text-xs text-amber-950/80">${escapeHtml(toolCall.pretty_input || toolCall.input || "{}")}</pre>
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

function updateContext(context) {
  if (!context) {
    return;
  }
  const current = context.current_tokens || 0;
  const max = context.max_tokens || 0;
  contextLabel.textContent = `${formatNumber(current)} / ${formatNumber(max)}`;
  mobileContextLabel.textContent = `${formatNumber(current)} / ${formatNumber(max)} tokens`;
  const pct = max > 0 ? Math.min(100, (current / max) * 100) : 0;
  contextBar.style.width = `${pct}%`;
}

function setStatus(text) {
  statusEl.textContent = text;
  mobileStatusEl.textContent = text;
}

function formatConfirmationSummary(toolCalls) {
  return toolCalls
    .map((call) => `${call.name}\n${call.pretty_input || call.input || "{}"}`)
    .join("\n\n");
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

function renderAssistantMarkdown(turn) {
  const source = turn.assistantRaw.trim();
  if (!source) {
    turn.assistantText.innerHTML = "";
    return;
  }

  if (window.marked) {
    window.marked.setOptions({
      breaks: true,
      gfm: true,
    });
    const html = window.marked.parse(source);
    turn.assistantText.innerHTML = window.DOMPurify
      ? window.DOMPurify.sanitize(html)
      : escapeHtml(source).replaceAll("\n", "<br>");
    return;
  }

  turn.assistantText.innerHTML = escapeHtml(source).replaceAll("\n", "<br>");
}

function compactTitle(title) {
  return String(title).replace(/\s+/g, " ").slice(0, 42);
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatScrollEl.scrollTop = chatScrollEl.scrollHeight;
  });
}

taskForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = taskInput.value.trim();
  if (!content || isRunning) {
    return;
  }

  isRunning = true;
  runBtn.disabled = true;
  activeTurn = createTurn(content, content);
  actInputs.clear();
  socket.send(
    JSON.stringify({
      type: "run",
      content,
    }),
  );
  taskInput.value = "";
  scrollToBottom();
});

function clearConversation() {
  conversationEl.innerHTML = "";
  turnsNav.innerHTML = "";
  confirmPanel.classList.add("hidden");
  pendingToolCalls = [];
  activeTurn = null;
  turnCounter = 0;
  actInputs.clear();
}

clearBtn.addEventListener("click", clearConversation);
mobileClearBtn.addEventListener("click", clearConversation);
allowBtn.addEventListener("click", () => sendConfirmation(true));
denyBtn.addEventListener("click", () => sendConfirmation(false));

taskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    taskForm.requestSubmit();
  }
});

runBtn.disabled = true;
connect();
