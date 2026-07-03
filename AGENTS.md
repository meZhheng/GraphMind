# GraphMind 开发规范

## 文档引用
- AgentScope 官方文档：https://docs.agentscope.io/versions/2.0.3/zh
- 本地笔记：`docs/agentscope-notes.md`（每次查询有用内容后更新）
- 查询顺序：先查本地笔记，再查官方文档

## 服务端口配置
- **默认端口**: 5277
- **启动命令**: `uvicorn graphmind.server.main:app --reload --host 127.0.0.1 --port 5277`
- **访问地址**: http://127.0.0.1:5277
- **注意**: 所有启动脚本和文档中的端口必须统一使用 5277

## Git 提交规范
- 遵循 Conventional Commits 规范
- 每次代码修改后生成标准化的 commit message
- 使用 `git commit` 提交变更

## 开发流程
1. 构建前端样式：`npm install && npm run build`
2. 启动服务：使用默认端口 5277
3. 访问地址：http://127.0.0.1:5277
