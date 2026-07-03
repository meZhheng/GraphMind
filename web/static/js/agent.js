const statusEl = document.querySelector("#status");
const mobileStatusEl = document.querySelector("#mobileStatus");
const conversationEl = document.querySelector("#conversation");
const chatScrollEl = document.querySelector("#chatScroll");
const taskForm = document.querySelector("#taskForm");
const taskInput = document.querySelector("#taskInput");
const runBtn = document.querySelector("#runBtn");
const newSessionBtn = document.querySelector("#newSessionBtn");
const mobileNewSessionBtn = document.querySelector("#mobileNewSessionBtn");
const clearBtn = document.querySelector("#clearBtn");
const mobileClearBtn = document.querySelector("#mobileClearBtn");
const confirmPanel = document.querySelector("#confirmPanel");
const confirmCalls = document.querySelector("#confirmCalls");
const confirmSubmitBtn = document.querySelector("#confirmSubmitBtn");
const sessionsNav = document.querySelector("#sessionsNav");
const contextLabel = document.querySelector("#contextLabel");
const mobileContextLabel = document.querySelector("#mobileContextLabel");
const contextBar = document.querySelector("#contextBar");

let socket;
let pendingToolCalls = [];
let pendingToolDecisions = new Map();
let turnCounter = 0;
let activeTurn = null;
let isRunning = false;
let isConnected = false;
let isAwaitingConfirmation = false;
let currentSessionId = "";
let currentSessionStartedAt = "";
let selectedSessionId = "";
let currentContext = {
  current_tokens: 0,
  max_tokens: 0,
};
let reconnectTimer = 0;
let reconnectAttempts = 0;

const actInputs = new Map();
const SESSION_HISTORY_KEY = "graphmind.sessionHistory";

function connect(sessionId = "") {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  const nextSocket = new WebSocket(
    `${protocol}://${window.location.host}/ws/agent${query}`,
  );
  socket = nextSocket;

  nextSocket.addEventListener("open", () => {
    if (socket !== nextSocket) {
      return;
    }
    isConnected = true;
    reconnectAttempts = 0;
    setStatus("Connected");
    refreshInputState();
  });

  nextSocket.addEventListener("close", () => {
    if (socket !== nextSocket) {
      return;
    }
    const wasBusy = isRunning || isAwaitingConfirmation;
    isConnected = false;
    isRunning = false;
    isAwaitingConfirmation = false;
    if (wasBusy) {
      appendSystemNotice("Connection lost while the agent was working.");
    }
    setStatus("Disconnected");
    refreshInputState();
    scheduleReconnect();
  });

  nextSocket.addEventListener("error", () => {
    if (socket !== nextSocket) {
      return;
    }
    appendSystemNotice("WebSocket error. Please start a new session or reload.");
  });

  nextSocket.addEventListener("message", (event) => {
    if (socket !== nextSocket) {
      return;
    }
    handlePayload(JSON.parse(event.data));
  });
}

function scheduleReconnect() {
  if (!currentSessionId || reconnectTimer || reconnectAttempts >= 5) {
    return;
  }
  reconnectAttempts += 1;
  const delay = Math.min(4000, 500 * reconnectAttempts);
  setStatus(`Reconnecting ${reconnectAttempts}/5...`);
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = 0;
    if (!isConnected) {
      connect(currentSessionId);
    }
  }, delay);
}

function handlePayload(payload) {
  if (payload.category === "session") {
    const requestedSessionId = payload.requested_session_id || "";
    const sessionRestored = Boolean(payload.restored);
    currentSessionId = payload.session_id;
    currentSessionStartedAt =
      getCurrentSession()?.startedAt || new Date().toISOString();

    if (requestedSessionId && !sessionRestored) {
      selectedSessionId = payload.session_id;
      clearConversationState();
      updateContext(payload.context);
      applySessionStatus(payload.session_status);
      appendSystemNotice(
        `Previous session ${requestedSessionId.slice(0, 8)} expired. Started a new session.`,
      );
      setStatus(`Session ${payload.session_id.slice(0, 8)}`);
      renderSessionHistory();
      refreshInputState();
      return;
    }

    selectedSessionId = payload.session_id;
    updateContext(payload.context);
    applySessionStatus(payload.session_status);
    restorePendingConfirmation(payload.pending_confirmation);
    setStatus(
      requestedSessionId && sessionRestored
        ? `Restored ${payload.session_id.slice(0, 8)}`
        : `Session ${payload.session_id.slice(0, 8)}`,
    );
    renderSessionHistory();
    refreshInputState();
    return;
  }

  updateContext(payload.context);
  applySessionStatus(payload.session_status);

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
      {
        const note = consumeAssistantDraft();
        const step = ensureStep(
          `act-${payload.tool_call_id}`,
          payload.title || "Tool call",
        );
        if (note) {
          appendStepNote(step, note);
        }
      }
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
      isRunning = false;
      isAwaitingConfirmation = pendingToolCalls.length > 0;
      renderConfirmation(payload);
      for (const toolCall of pendingToolCalls) {
        appendStepText(
          `approval-${toolCall.id}`,
          `${toolCall.name}\n${toolCall.pretty_input || toolCall.input || "{}"}`,
          { title: `Waiting for approval: ${toolCall.name}` },
        );
      }
      refreshInputState();
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
      if (payload.pending_confirmation) {
        restorePendingConfirmation(payload.pending_confirmation);
      }
      appendSystemNotice(payload.content || payload.title || "Error");
      if (!isAwaitingConfirmation) {
        finishTurn();
      }
      break;
    default:
      if (payload.pending_confirmation) {
        restorePendingConfirmation(payload.pending_confirmation);
      }
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
  window.GraphMindRounds?.addTurn(turnId, turnCounter);

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

function ensureAssistantMessage() {
  if (!activeTurn.assistantRaw.trim()) {
    activeTurn.assistantText.innerHTML = "";
  }
}

function appendAssistantText(text) {
  activeTurn.assistantRaw += text;
  renderAssistantMarkdown(activeTurn);
}

function consumeAssistantDraft() {
  const note = activeTurn.assistantRaw.trim();
  if (!note) {
    return "";
  }
  activeTurn.assistantRaw = "";
  renderAssistantMarkdown(activeTurn);
  return note;
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
    <div class="step-note hidden"></div>
    <pre class="step-body"></pre>
  `;
  activeTurn.stepsList.append(item);
  activeTurn.stepsPanel.classList.remove("hidden");
  activeTurn.stepsPanel.open = true;

  step = {
    item,
    note: item.querySelector(".step-note"),
    body: item.querySelector(".step-body"),
  };
  activeTurn.steps.set(key, step);
  return step;
}

function appendStepText(key, text, options = {}) {
  const step = ensureStep(key, options.title || key);
  step.body.textContent += text;
}

function appendStepNote(step, text) {
  step.item.dataset.kind = "note";
  step.note.classList.remove("hidden");
  step.note.textContent = text;
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
  activeTurn.stepsPanel.open = false;
  isRunning = false;
  persistCurrentSession();
  refreshInputState();
  activeTurn = null;
}

function renderConfirmation(payload) {
  if (!payload) {
    return;
  }
  pendingToolCalls = payload.tool_calls || [];
  pendingToolDecisions = new Map();
  isAwaitingConfirmation = pendingToolCalls.length > 0;
  confirmPanel.classList.remove("hidden");
  confirmCalls.innerHTML = "";

  for (const toolCall of pendingToolCalls) {
    const item = document.createElement("div");
    item.className = "confirm-call";

    const title = document.createElement("div");
    title.className = "confirm-call-title";
    title.textContent = toolCall.name;

    const body = document.createElement("pre");
    body.className = "confirm-call-body";
    body.textContent = toolCall.pretty_input || toolCall.input || "{}";

    const actions = document.createElement("div");
    actions.className = "confirm-call-actions";

    const allow = document.createElement("button");
    allow.className = "decision-button allow-choice";
    allow.type = "button";
    allow.textContent = "Allow";
    allow.addEventListener("click", () => {
      setToolDecision(toolCall.id, true, item);
    });

    const deny = document.createElement("button");
    deny.className = "decision-button deny-choice";
    deny.type = "button";
    deny.textContent = "Deny";
    deny.addEventListener("click", () => {
      setToolDecision(toolCall.id, false, item);
    });

    actions.append(allow, deny);
    item.append(title, body, actions);
    confirmCalls.append(item);
  }
  updateConfirmSubmitState();
}

function applySessionStatus(status) {
  if (!status) {
    return;
  }
  isRunning = Boolean(status.is_running);
  isAwaitingConfirmation = Boolean(status.is_awaiting_confirmation);
}

function restorePendingConfirmation(payload) {
  if (!payload) {
    isAwaitingConfirmation = false;
    pendingToolCalls = [];
    pendingToolDecisions = new Map();
    confirmPanel.classList.add("hidden");
    return;
  }
  renderConfirmation(payload);
}

function setToolDecision(toolCallId, confirmed, item) {
  pendingToolDecisions.set(toolCallId, confirmed);
  item.querySelector(".allow-choice")?.classList.toggle("selected", confirmed);
  item.querySelector(".deny-choice")?.classList.toggle("selected", !confirmed);
  updateConfirmSubmitState();
}

function updateConfirmSubmitState() {
  confirmSubmitBtn.disabled =
    !pendingToolCalls.length ||
    pendingToolDecisions.size !== pendingToolCalls.length;
}

function sendConfirmation() {
  if (!pendingToolCalls.length) {
    return;
  }
  if (pendingToolDecisions.size !== pendingToolCalls.length) {
    appendSystemNotice("Choose Allow or Deny for every pending tool call.");
    return;
  }

  isAwaitingConfirmation = false;
  isRunning = true;
  refreshInputState();
  socket.send(
    JSON.stringify({
      type: "confirm",
      results: pendingToolCalls.map((toolCall) => ({
        tool_call_id: toolCall.id,
        confirmed: Boolean(pendingToolDecisions.get(toolCall.id)),
      })),
    }),
  );

  confirmPanel.classList.add("hidden");
  pendingToolCalls = [];
  pendingToolDecisions = new Map();
  updateConfirmSubmitState();
}

function updateContext(context) {
  if (!context) {
    return;
  }
  currentContext = {
    current_tokens: context.current_tokens || 0,
    max_tokens: context.max_tokens || 0,
  };
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

function loadSessionHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(SESSION_HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSessionHistory(history) {
  localStorage.setItem(
    SESSION_HISTORY_KEY,
    JSON.stringify(history.slice(0, 20)),
  );
}

function captureSnapshot() {
  return {
    html: conversationEl.innerHTML,
    turns: turnCounter,
    context: currentContext,
  };
}

function persistCurrentSession(update = {}) {
  if (!currentSessionId || turnCounter === 0) {
    return;
  }

  upsertSessionHistory({
    id: currentSessionId,
    startedAt: currentSessionStartedAt,
    updatedAt: new Date().toISOString(),
    turns: turnCounter,
    lastTask: update.lastTask || getCurrentSession()?.lastTask || "Current session",
    snapshot: captureSnapshot(),
    context: currentContext,
    ...update,
  });
}

function getCurrentSession() {
  return loadSessionHistory().find((session) => session.id === currentSessionId);
}

function upsertSessionHistory(update) {
  if (!update.id) {
    return;
  }

  const history = loadSessionHistory();
  const existing = history.find((session) => session.id === update.id);
  if (existing) {
    Object.assign(existing, update);
  } else {
    history.unshift(update);
  }
  history.sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
  saveSessionHistory(history);
  renderSessionHistory();
}

function deleteSession(sessionId) {
  const history = loadSessionHistory().filter(
    (session) => session.id !== sessionId,
  );
  saveSessionHistory(history);

  if (selectedSessionId === sessionId) {
    clearConversationState();
    selectedSessionId = currentSessionId;
  }

  if (currentSessionId === sessionId) {
    reconnectForFreshSession();
  }

  renderSessionHistory();
  refreshInputState();
}

function reconnectToSession(sessionId) {
  isConnected = false;
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = 0;
  }
  if (socket && socket.readyState !== WebSocket.CLOSED) {
    socket.close();
  }
  connect(sessionId);
}

function selectSession(sessionId) {
  const session = loadSessionHistory().find((item) => item.id === sessionId);
  if (!session) {
    return;
  }

  if (selectedSessionId === currentSessionId) {
    persistCurrentSession();
  }

  selectedSessionId = sessionId;
  restoreSessionSnapshot(session);
  if (sessionId === currentSessionId) {
    setStatus(`Session ${sessionId.slice(0, 8)}`);
  } else {
    setStatus(`Opening ${sessionId.slice(0, 8)}`);
    reconnectToSession(sessionId);
  }
  renderSessionHistory();
  refreshInputState();
}

function restoreSessionSnapshot(session) {
  activeTurn = null;
  pendingToolCalls = [];
  confirmPanel.classList.add("hidden");
  actInputs.clear();
  conversationEl.innerHTML = session.snapshot?.html || "";
  turnCounter = session.snapshot?.turns || session.turns || 0;
  updateContext(session.snapshot?.context || session.context);
  window.GraphMindRounds?.reset();

  const turns = [...conversationEl.querySelectorAll(".turn")];
  for (const [index, turn] of turns.entries()) {
    if (!turn.id) {
      turn.id = `turn-${index + 1}`;
    }
    window.GraphMindRounds?.addTurn(turn.id, index + 1);
  }
  scrollToBottom();
}

function renderSessionHistory() {
  if (!sessionsNav) {
    return;
  }

  const history = loadSessionHistory();
  sessionsNav.innerHTML = "";

  if (!history.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "No sessions yet";
    sessionsNav.append(empty);
    return;
  }

  for (const session of history) {
    const item = document.createElement("div");
    item.className = "session-item";
    item.classList.toggle("active", session.id === selectedSessionId);
    item.innerHTML = `
      <button class="session-open" type="button">
        <span class="session-title">${escapeHtml(session.lastTask || "Untitled session")}</span>
        <span class="session-meta">${escapeHtml(formatSessionMeta(session))}</span>
      </button>
      <button class="session-delete" type="button" aria-label="Delete session">&times;</button>
    `;
    item.querySelector(".session-open").addEventListener("click", () => {
      selectSession(session.id);
    });
    item.querySelector(".session-delete").addEventListener("click", (event) => {
      event.stopPropagation();
      deleteSession(session.id);
    });
    sessionsNav.append(item);
  }
}

function formatSessionMeta(session) {
  const turns = session.turns || 0;
  const id = session.id ? session.id.slice(0, 8) : "local";
  return `${turns} round${turns === 1 ? "" : "s"} · ${id}`;
}

function isViewingArchivedSession() {
  return Boolean(selectedSessionId && selectedSessionId !== currentSessionId);
}

function refreshInputState() {
  const archived = isViewingArchivedSession();
  const ready = isConnected && Boolean(currentSessionId);
  taskInput.disabled = archived || !ready || isAwaitingConfirmation;
  taskInput.placeholder = isAwaitingConfirmation
    ? "Approve or deny the pending tool call first."
    : archived
      ? "Select the current session to continue chatting."
      : "Message GraphMind...";
  runBtn.disabled = !ready || isRunning || archived || isAwaitingConfirmation;
  newSessionBtn.disabled = isRunning;
  mobileNewSessionBtn.disabled = isRunning;
  clearBtn.disabled = isRunning;
  mobileClearBtn.disabled = isRunning;
}

function clearConversationState() {
  conversationEl.innerHTML = "";
  window.GraphMindRounds?.reset();
  confirmPanel.classList.add("hidden");
  pendingToolCalls = [];
  pendingToolDecisions = new Map();
  isAwaitingConfirmation = false;
  activeTurn = null;
  turnCounter = 0;
  actInputs.clear();
}

function reconnectForFreshSession() {
  currentSessionId = "";
  currentSessionStartedAt = "";
  selectedSessionId = "";
  isConnected = false;
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = 0;
  }
  if (socket && socket.readyState !== WebSocket.CLOSED) {
    socket.close();
  }
  connect();
}

function createNewSession() {
  if (isRunning) {
    return;
  }

  if (selectedSessionId === currentSessionId) {
    persistCurrentSession();
  }
  clearConversationState();
  setStatus("Starting new session...");
  reconnectForFreshSession();
  renderSessionHistory();
  refreshInputState();
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

  turn.assistantText.innerHTML = renderMarkdown(source);
}

function renderMarkdown(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let list = [];
  let quote = [];
  let code = [];
  let inCode = false;

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!list.length) {
      return;
    }
    blocks.push(
      `<ul>${list.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`,
    );
    list = [];
  };

  const flushQuote = () => {
    if (!quote.length) {
      return;
    }
    blocks.push(`<blockquote>${renderInlineMarkdown(quote.join(" "))}</blockquote>`);
    quote = [];
  };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        flushQuote();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      code.push(line);
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      flushQuote();
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      flushQuote();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      flushParagraph();
      flushQuote();
      list.push(unordered[1]);
      continue;
    }

    const ordered = /^\d+\.\s+(.+)$/.exec(trimmed);
    if (ordered) {
      flushParagraph();
      flushQuote();
      list.push(ordered[1]);
      continue;
    }

    const quoted = /^>\s?(.+)$/.exec(trimmed);
    if (quoted) {
      flushParagraph();
      flushList();
      quote.push(quoted[1]);
      continue;
    }

    flushList();
    flushQuote();
    paragraph.push(trimmed);
  }

  if (inCode) {
    blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  }
  flushParagraph();
  flushList();
  flushQuote();

  return blocks.join("");
}

function renderInlineMarkdown(source) {
  let html = escapeHtml(source);
  const codeSpans = [];

  html = html.replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@CODE_${codeSpans.length}@@`;
    codeSpans.push(`<code>${code}</code>`);
    return token;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  html = html.replace(
    /@@CODE_(\d+)@@/g,
    (_, index) => codeSpans[Number(index)] || "",
  );

  return html;
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

  if (isViewingArchivedSession()) {
    return;
  }

  if (!currentSessionId || !socket || socket.readyState !== WebSocket.OPEN) {
    setStatus("Connecting...");
    refreshInputState();
    return;
  }

  isRunning = true;
  refreshInputState();
  activeTurn = createTurn(content, content);
  actInputs.clear();
  upsertSessionHistory({
    id: currentSessionId,
    startedAt: currentSessionStartedAt,
    updatedAt: new Date().toISOString(),
    turns: turnCounter,
    lastTask: compactTitle(content),
    context: currentContext,
    snapshot: captureSnapshot(),
  });
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
  clearConversationState();
  selectedSessionId = currentSessionId;
  const history = loadSessionHistory().filter(
    (session) => session.id !== currentSessionId,
  );
  saveSessionHistory(history);
  renderSessionHistory();
  refreshInputState();
}

clearBtn.addEventListener("click", clearConversation);
mobileClearBtn.addEventListener("click", clearConversation);
newSessionBtn.addEventListener("click", createNewSession);
mobileNewSessionBtn.addEventListener("click", createNewSession);
confirmSubmitBtn.addEventListener("click", sendConfirmation);

taskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    taskForm.requestSubmit();
  }
});

runBtn.disabled = true;
renderSessionHistory();
connect();
