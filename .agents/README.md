# .agents — AI Agent Workspace Configuration

This folder contains configuration, commands, and skills for AI agents working in this workspace.

## Structure

```
.agents/
├── rules/          # Linting and code compliance rules
├── commands/       # Slash commands for quick agent instructions
├── skills/         # Reusable agent skills and expertise
└── README.md       # This file
```

---

## 📋 Rules

**Location:** `.agents/rules/`

Define code compliance and linting rules that are automatically enforced by AgentHub.

**Format:** Markdown (.md), YAML (.yaml), or JSON (.json)

**Example:** `.agents/rules/coding-standards.md`
```markdown
error: No console.log in production code :: console\.log\(
warn: TODO must reference ticket :: TODO(?!\(JIRA-\d+\))
```

**Features:**
- Real-time diagnostics while coding
- Configurable save blocking
- Build integration via `npm run check-rules`

---

## ⚡ Commands

**Location:** `.agents/commands/`

Quick slash command instructions that agents can execute. Type `/` in the editor to see available commands.

**Format:** Markdown (.md)

**Example:** `.agents/commands/review.md`
```markdown
# Code Review Command

You are a senior code reviewer. When reviewing code:
1. Check architectural correctness
2. Verify error handling
3. Ensure tests exist
4. Validate documentation
5. Check performance implications
```

**Usage:**
- Type `/` in editor → Select command → Agent executes instruction
- Commands are context-specific instructions, not shell scripts
- Can reference project-specific patterns and standards

---

## 🎯 Skills

**Location:** `.agents/skills/`

Reusable agent expertise and knowledge patterns. Skills provide specialized guidance for specific tasks.

**Format:** Markdown (.md) with frontmatter

**Example:** `.agents/skills/react-best-practices/skill.md`
```markdown
---
name: react-best-practices
description: React 18 + TypeScript best practices
status: ✅ Working
---

# React Best Practices

## Component Design
- Keep components small and focused
- Prefer functional components
- Extract reusable logic into custom hooks
...
```

**Types:**
- **Knowledge Skills:** Load specialized expertise into context
- **Automation Skills:** Execute specific procedures or validations

---

## 🚀 Quick Start

### 1. Add Rules

Create `.agents/rules/my-rules.md`:
```markdown
error: No hardcoded secrets :: (api[_-]?key|secret)[\s]*=\s*['"][^'"]{20,}['"]
warn: Prefer const over let :: \blet\b
```

### 2. Add Commands

Create `.agents/commands/deploy.md`:
```markdown
# Deploy Command

Deploy to staging environment:
1. Run tests: npm test
2. Build: npm run build
3. Deploy: npm run deploy:staging
```

### 3. Add Skills

Create `.agents/skills/testing/skill.md`:
```markdown
---
name: testing-best-practices
description: Testing patterns and strategies
---

# Testing Best Practices
- Write tests first (TDD)
- Test behavior, not implementation
...
```

### 4. Use Commands

Type `/` in editor → Select command → Agent executes

---

## 📖 References

- **AgentHub:** VS Code extension enforcing rules and managing agent workspace
- **Settings:** Configure via VS Code Settings → AgentHub
- **Build Integration:** Run `npm run check-rules` in CI/CD

---

**Built with ❤️ by [BuildWorks.AI](https://buildworks.ai)**

*Enterprise AI • Open Source First*

- 🌐 [Website](https://buildworks.ai)
- 💻 [GitHub](https://github.com/buildworksai)
- 💼 [LinkedIn](https://www.linkedin.com/company/buildworks-ai/)
- 📧 [info@buildworks.ai](mailto:info@buildworks.ai)
