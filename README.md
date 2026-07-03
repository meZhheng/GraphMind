# GraphMind

GraphMind 是一个基于 AgentScope 的图思维推理框架，旨在通过多智能体协作解决复杂的图结构推理问题。

## 功能特性

- 多智能体协作推理
- 图结构分析
- 思维链推理
- 可扩展的图任务支持
- 人机协作（Human-in-the-loop）：支持工具调用的用户确认机制
- 实时 WebSocket 通信
- 多会话管理

## 安装

```bash
pip install -r requirements.txt
```

## 配置

在项目根目录创建 `.env` 文件，配置 LLM 参数：

```bash
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your_api_key
MODEL_NAME=gpt-4o
```

## 启动 Agent Web 服务

构建前端样式：

```bash
npm install
npm run build:css
```

启动服务：

```bash
uvicorn graphmind.server.main:app --reload --host 127.0.0.1 --port 8000
```

然后访问 http://127.0.0.1:8000。

当前前端采用 Jinja2 模板 + 原生 JavaScript + WebSocket + 本地 Tailwind CLI：

- 页面模板：`web/templates/`
- Tailwind 输入：`web/static/css/input.css`
- Tailwind 输出：`web/static/dist/app.css`
- 前端逻辑：`web/static/js/`

WebSocket 是浏览器原生能力，不需要 React/Vue 等前端框架。开发样式时可运行 `npm run dev:css` 持续监听。

## 代码结构

```text
graphmind/
  agent/      # AgentScope agent 构建、权限、事件转换、会话管理
    - factory.py       # Agent 工厂函数
    - session.py       # 会话管理
    - middleware.py    # 工具调用参数清理
    - permissions.py   # 人机协作权限配置
    - store.py         # 会话存储
    - events.py        # 事件到 payload 转换
  api/        # FastAPI routes 和 app factory
    - app.py           # FastAPI 应用工厂
    - routes.py        # WebSocket 和 HTTP 路由
  core/       # 路径、环境变量和配置
    - config.py        # 配置加载
  server/     # uvicorn 入口
web/
  templates/  # Jinja2 HTML
  static/     # CSS/JS/assets
```

## 开发工具

项目提供以下文件操作工具：

- **Read**: 读取文件
- **Glob**: 文件模式匹配
- **Grep**: 正则表达式搜索
- **Write**: 写入文件
- **Edit**: 编辑文件
- **Bash**: 执行 shell 命令

## 许可证

MIT License
