# AgentScope Notes

本文件用于记录从 AgentScope 官方文档或本地源码中查询到的有用内容，后续先查这里，再查官方文档：https://docs.agentscope.io/versions/2.0.3/zh

## AgentScope 2.0.3：事件流与 Human-in-the-loop

- `Agent.reply_stream(inputs)` 会流式返回 `AgentEvent`，适合展示 ReAct 中间过程；`Agent.reply(inputs)` 会消费事件，只返回最终 `Msg`。
- 中间步骤事件类型：
  - `ThinkingBlockStartEvent` / `ThinkingBlockDeltaEvent` / `ThinkingBlockEndEvent`：模型 reasoning/thinking。
  - `ToolCallStartEvent` / `ToolCallDeltaEvent` / `ToolCallEndEvent`：模型 act，即工具调用名称和参数。
  - `ToolResultStartEvent` / `ToolResultTextDeltaEvent` / `ToolResultEndEvent`：工具执行结果。
  - `ModelCallStartEvent` / `ModelCallEndEvent`：模型调用开始和 token usage。
- 权限确认机制：
  - 权限系统返回 ASK 时，agent 会发出 `RequireUserConfirmEvent`，其中包含待确认的 `tool_calls`。
  - 用户确认后，需要构造 `UserConfirmResultEvent(reply_id=event.reply_id, confirm_results=[ConfirmResult(...)])` 并再次传给 `reply_stream()` 继续执行。
  - `ConfirmResult.rules=None` 表示只批准本次调用，不添加长期 allow 规则。
- `PermissionMode.DEFAULT` 默认会询问大多数操作；可以在 `state.permission_context.ask_rules` 中为工具名加入 `PermissionRule(..., behavior=PermissionBehavior.ASK)`，强制这些工具每次都走确认。
- `PermissionMode.ACCEPT_EDITS` 会自动允许工作目录内的文件读写编辑；如果需要 human-in-loop，不要使用该模式。

## FastAPI WebSocket 集成建议

- 浏览器原生支持 `WebSocket`，不需要 React/Vue 等前端框架；原生 JS 可以直接 `new WebSocket("ws://...")`。
- AgentScope 的 `reply_stream()` 可以直接映射为 WebSocket JSON 消息；每个 `AgentEvent` 转成 `{category, title, content, event}` 这类前端友好的 payload。
- human-in-loop 可在服务端保留 `RequireUserConfirmEvent`，前端点击 Allow/Deny 后发送 `{type: "confirm", results: [...]}`，服务端构造 `UserConfirmResultEvent` 继续调用 `reply_stream()`。
- FastAPI 推荐用 app factory：`create_app()` 创建实例，`graphmind.server.main:app` 作为 uvicorn 入口，便于后续测试和扩展。
