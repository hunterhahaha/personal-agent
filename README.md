# Personal AI Assistant

本项目只包含三个需要关注的部分：

- `assistant/frontend`：前端界面
- `assistant/backend`：后端服务
- `assistant/skills`：技能目录

## 目录

```text
assistant/
├── frontend/
├── backend/
└── skills/
```

## 后端

后端目录：

```text
assistant/backend/
├── app/
├── .env # 搜索服务使用tavily，需要配置API才能使用搜索。也支持searxng / Being，但需要自己部署本地服务，并进行相关配置；不需要理会.env里的模型配置，在前端配置即可，但是记得启用，前端配置完后没有默认启用；
├── .gitignore
└── requirements.txt
```

启动：

```powershell
cd assistant/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

地址：

- `http://localhost:8003`
- `http://localhost:8003/health`
- `http://localhost:8003/api`

## 前端

前端目录：

```text
assistant/frontend/
```

启动：

```powershell
cd assistant/frontend
npm install
npm run dev
```

地址：

- `http://localhost:3000`

前端开发环境请求后端地址：

- `http://localhost:8003/api`

## Skills

Skill 目录：

```text
assistant/skills/
└── skill-name/
    └── SKILL.md
```

`SKILL.md` 需要包含 frontmatter：

```md
---
name: skill-name
description: Describe when this skill should be used.
---

# Skill Name

Skill instructions here.
```

禁用某个 Skill：

```text
assistant/skills/skill-name/.disabled
```

校验：

```powershell
cd assistant
python scripts/validate_skills.py
```
