# Git 提交规约（zzdzz-pose-tool）

> 母本：`lisay-govel-generator开发规约.md` §5 拆分版（2026-08-27），2026-09-03 按本项目适配。
> 适配点：scope 表按本项目模块重写；构建校验由 `mvn compile` 改为 `pytest`；新增姿态资产提交约定；修正母本"subject ≤ 50"与钩子检查 > 70 的不一致（统一为 ≤ 50）。

---

## §1. Conventional Commits 格式

所有 commit 必须同时满足格式规范（本节）+ 原子性规范（§2）。

```
<type>(<scope>): <subject>

<body>

<footer>
```

### type（必填，固定 11 取值，不发明新词）

`feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `chore` / `build` / `ci` / `revert`

### scope（选填，本项目模块表）

| scope | 覆盖范围 |
|---|---|
| `schema` | pose.json 格式定义（`src/pose_tool/schema.py`、`schemas/`） |
| `render` | 骨架图渲染器（`src/pose_tool/render.py`） |
| `diff` | 语义 diff（`src/pose_tool/diff.py`） |
| `cli` | 命令行与批量/索引（`cli.py`、`batch.py`、`library.py`） |
| `poses` | 姿态资产库内容（`poses/` 下 pose.json / meta.yaml / preview.png / index.yaml） |
| `import` | 外部姿态数据导入（`src/pose_tool/importers.py`） |
| `webui` | Web 前端（`webui/` 下 Vue 组件与构建产物） |
| `git` | 提交规约、钩子、.gitignore |
| `build` | pyproject / 依赖 / 打包 |

### subject / body / footer

- subject：**中文**、动词开头、≤ 50 字符、不加句号、不写"改了点东西"
- body（可选）：写清为什么 / 怎么改 / 影响面，`-` 列表，72 字符换行；格式（schema）变更必须写明对旧 pose.json 的迁移方式
- footer（可选）：`Closes #123`；破坏性变更必须 `BREAKING CHANGE: xxx` + 迁移路径

## §2. 原子性提交

1. 一个 commit = 一件事，不混搭
2. **每个 commit 后 `python -m pytest -q` 必须全绿**（本项目的"可构建"判定）
3. 业务逻辑改动必须带对应测试
4. 不混入无关改动（顺手格式化单独成 commit）
5. 粒度适中：一个完整特性 3~8 个 commit

### 资产提交约定（本项目特有）

- `pose.json` 与其派生的 `preview.png`、`meta.yaml` 是**同一逻辑变更**，必须进同一个 commit，禁止拆开
- `renders/` 为批量渲染产物，已被 .gitignore 排除，**永不提交**；提交对象是 `poses/*/preview.png`
- 新增姿态用 `feat(poses)`；只改数值不改语义的修正用 `fix(poses)`
- pose.json 格式版本（`version` 字段）变更属于 `BREAKING CHANGE`，必须写迁移路径

## §3. 语言约定（强制）

- subject 必须中文开头（技术名词、库名、命令、文件名可保留英文）
- 禁止 `feat: add login` 这类英文 subject
- footer 标记（`Closes` / `BREAKING CHANGE` / `Refs`）保留英文 + 中文描述

## §4. commit-msg 钩子（强制）

钩子位于 `.githooks/commit-msg`，检查：① `<type>(<scope>): ` 前缀合法；② subject 中文开头；③ subject ≤ 50 字符；④ 不以句号结尾。不合规直接拒绝提交。

启用（克隆后执行一次）：

```bash
git config core.hooksPath .githooks
```

## §5. 流程分阶段说明

单人 MVP 阶段：§1~§4 全部强制，PR review 流程（母本 §3）暂缓，作为提交前自检清单使用。引入协作者或 CI 后，PR 阶段按母本流程执行强制检查。

## §6. 反面示例

| 反面写法 | 错在哪 |
|---|---|
| `git commit -m "更新代码"` | 无 type / scope / 中文 subject |
| `feat: 改了很多东西` | subject 模糊 |
| `fix(poses): 修改姿态.` | 结尾句号 |
| `feat(render): add renderer` | 英文 subject |
| 一个 commit 同时改 schema + render + 新增姿态 | 原子性破坏，无法单独 revert |
| 只提交 pose.json 不更新 preview.png | 资产两半不一致（§2 资产约定） |
