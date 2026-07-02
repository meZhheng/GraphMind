# GraphMind

GraphMind 是一个基于 AgentScope 的图思维推理框架，旨在通过多智能体协作解决复杂的图结构推理问题。

## 功能特性

- 多智能体协作推理
- 图结构分析
- 思维链推理
- 可扩展的图任务支持

## 安装

```bash
pip install -r requirements.txt
```

## 启动 Agent Web 服务

```bash
uvicorn graphmind.server.main:app --reload --host 127.0.0.1 --port 8000
```

然后访问 http://127.0.0.1:8000。

当前前端采用 Jinja2 模板 + 原生 JavaScript + WebSocket + Tailwind CDN：

- 页面模板：`web/templates/`
- 静态样式：`web/static/css/`
- 前端逻辑：`web/static/js/`

WebSocket 是浏览器原生能力，不需要 React/Vue 等前端框架。后续如果要改成本地 Tailwind 构建，可以新增 `tailwind.config.js` 和 `package.json`，把 Tailwind CLI 输出写到 `web/static/dist/`，模板入口保持不变。

## 代码结构

```text
graphmind/
  agent/      # AgentScope agent 构建、权限、事件转换、会话管理
  api/        # FastAPI routes 和 app factory
  core/       # 路径、环境变量和配置
  server/     # uvicorn 入口
web/
  templates/  # Jinja2 HTML
  static/     # CSS/JS/assets
```
