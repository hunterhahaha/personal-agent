# 手动验证：msg_json.parts → 渲染态 映射（任务 2.6）

## 状态：手动验证（无测试框架）

当前 `assistant/frontend/package.json` 未配置 jest 或 vitest 测试框架，
因此本任务以手动验证方式记录快照测试的等价覆盖。

---

## 验证场景

### 输入：复合消息（含三种 part 类型）

```json
{
  "role": "assistant",
  "parts": [
    { "type": "text", "text": "这是正文内容" },
    { "type": "reasoning", "text": "这是推理过程..." },
    { "type": "toolcall", "tool": "run_terminal", "id": "call_001", "args": { "command": "ls" }, "metadata": {}, "state": {} }
  ],
  "content": "这是正文内容",
  "toolCalls": [{ "name": "run_terminal", "args": { "command": "ls" } }]
}
```

### 预期渲染态

1. **TextPart(type:"text")** → 通过 `<ReactMarkdown>` 渲染为 Markdown 内容
2. **TextPart(type:"reasoning")** → 通过 `<ReasoningBlock>` 渲染为可折叠推理区块（默认折叠）
3. **PartToolCall(type:"toolcall")** → 由 `<ToolCallsPanel>` 渲染为工具调用面板（在消息气泡上方）

### 渲染逻辑位置

- 文件：`src/app/(dashboard)/chat/page.tsx`
- 关键代码段（约第 270-295 行）：
  ```tsx
  msg.parts.map((part: MsgPart, idx: number) => {
    if (part.type === "reasoning") {
      return <ReasoningBlock key={...} content={(part as PartText).text} />;
    }
    if (part.type === "text") {
      return <ReactMarkdown key={...}>{(part as PartText).text}</ReactMarkdown>;
    }
    // toolcall parts handled by ToolCallsPanel above
    return null;
  })
  ```

### 过滤逻辑验证

- `uniqueMessages` 使用三条件合取判定空消息：
  - `!msg.parts || msg.parts.length === 0`
  - `!msg.toolCalls || msg.toolCalls.length === 0`
  - `!msg.content?.trim()`
- 只有三者同时为真时才过滤，确保仅含工具调用的消息不会被误删。

---

## 手动验证步骤

1. 启动前端开发服务器：`cd assistant/frontend && npm run dev`
2. 打开一个对话，发送一条会触发 reasoning + 工具调用的消息
3. 验证：
   - [ ] reasoning 区块可见且默认折叠
   - [ ] 正文 Markdown 正常渲染
   - [ ] 工具调用面板显示在消息气泡上方
4. 刷新页面，验证历史消息加载后：
   - [ ] reasoning 区块仍然可见（从 parts 恢复）
   - [ ] 仅含工具调用的助理消息不消失

---

## 未来改进

当项目引入 vitest 或 jest 后，应将本文档转化为自动化快照测试：
- 使用 `@testing-library/react` 渲染消息组件
- 对上述复合消息输入执行 `toMatchSnapshot()`
- 覆盖 parts 为空时的 fallback 渲染路径

---

## 锚点

- [锚] design.md §5.2 组 A
- 关联任务：2.2（store parts 结构）、2.3（page.tsx 渲染层）
