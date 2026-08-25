# Xpeech Deck

Xpeech 简易多实例管理平台：在指定目录中克隆并管理多个 [Xpeech](https://gitee.com/luojiaaoo/xpeech) Docker Compose 实例。

- 每个实例直接从 Gitee 克隆一份独立 Xpeech Git 工作树
- 自动 fetch 全部实例，可在远程分支与标签之间切换版本
- 在线配置 Backend / Web Client 端口与 `conf.toml`
- 执行常用 Docker Compose 命令（Up / Start / Stop / Restart / Down / PS）
- 查看并拉取 Xpeech 构建基础镜像与 Browserless 镜像
- 通过 System Console 实时查看平台执行的 Docker 命令与响应
- 通过 URL Token 直接进入，无账号和登录页面

## 前置依赖

| 依赖 | 用途 |
|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | 后端运行与依赖管理 |
| Node.js 20+（含 npm） | 构建前端 |
| Docker Engine / Docker Desktop + Compose 插件 | 执行 `docker compose` |
| Git | 克隆、fetch 和切换 Xpeech 版本 |

平台、Docker 与全部 Xpeech 实例必须运行在同一台机器上。

## 安装

```bash
# 1. 克隆仓库
git clone git@github.com:luojiaaoo/xpeech-deck.git
cd xpeech-deck

# 2. 安装后端依赖
uv sync --group dev

# 3. 构建前端（产物输出到 xpeech_deck/static/）
cd frontend
npm install
npm run build
cd ..
```

## 配置

复制 `conf.toml.example` 为 `conf.toml` 并填写（该文件已被 `.gitignore` 忽略）：

```toml
token = "replace-with-your-token"
root_path = "/opt/xpeech-instances"      # Windows 示例："E:/xpeech-instances"
listen_port = 7801                       # 可选，Deck 自身监听端口
```

启动时平台会：

1. 读取项目根目录的 `conf.toml`，校验 `token` 非空、`listen_port` 为有效端口；
2. 将 `root_path` 转为绝对路径，不存在则自动创建；
3. 检查 `docker` 与 `git` 命令是否可执行（缺失时仅告警，对应操作会失败）。

## 启动

```bash
uv run python -m xpeech_deck
# 或安装后使用命令：xpeech-deck
```

平台默认监听 `http://localhost:7801`；可通过 `conf.toml` 的 `listen_port` 修改。

### 访问

使用带 Token 的地址直接进入：

```text
http://localhost:7801/?token=your-token
```

- Token 只保存在页面内存中，打开页面后自动从地址栏清除；
- 刷新页面后 Token 丢失，需重新使用带 `?token=xxx` 的地址；
- 不使用 Cookie / localStorage / 登录表单；
- 公开接口只有 `GET /health`，其余 `/api/*` 必须携带 `Authorization: Bearer <token>`。

## 使用

### 创建实例

点击「添加实例」，输入实例名（字母/数字开头，允许 `-` `_`，最长 63 字符）。平台会直接从 `https://gitee.com/luojiaaoo/xpeech.git` 浅克隆全部远程分支最近 20 次提交，保留 `.git/` 以便后续更新与切换版本，定时 fetch 会维持 20 层历史并同步标签。平台的 Gitee 网络命令固定使用 TLS 1.2 / HTTP 1.1 以兼容 WSL 本地代理；遇到 TLS 握手、连接重置等瞬时网络错误时会自动尝试最多 3 次，然后生成：

- `.env`：`COMPOSE_PROJECT_NAME` = 实例名，默认 `BACKEND_PORT=7878`、`WEB_CLIENT_PORT=7939`、`CDP_URL=ws://browserless:3000`
- `conf.toml`：由 `conf.toml.example` 复制而来

重复名称返回「实例已存在」，不支持覆盖创建。

### 更新与切换版本

- 使用 Token 打开网页后，平台会立即对全部实例执行一次 `git fetch --depth=20 --all --prune --tags`，此后每 60 秒重复一次；
- 点击实例行内的「切换」，可选择 Gitee 远程分支、标签或最近 20 次提交；
- 切换时执行 `git reset --hard <ref>`，已跟踪文件的本地修改会被覆盖，但平台生成且未被 Git 跟踪的 `.env` / `conf.toml` 不受影响；
- Git 操作与 Compose/镜像命令共用平台级互斥锁，如果定时 fetch 遇到正在执行的命令，会等待下一分钟再试。

### 配置实例

点击「配置」打开弹窗：

- 只允许修改 Backend 端口与 Web Client 端口（整数、1–65535、两者不能相同），保存时重新生成整个 `.env`，不提供 `.env` 原文编辑；
- `conf.toml` 在线编辑，保存前用 `tomllib` 校验语法，语法错误不覆盖原文件并返回错误行号；
- 不校验 API Key、飞书配置等字段内容，这些问题最终由 Compose 命令输出反馈。

### 自定义内置技能

点击实例行内的「技能管理」，可查看、上传、编辑、下载、迁移和删除该实例的自定义内置技能：

- 可直接上传 UTF-8 编码的 `SKILL.md`，平台从 YAML frontmatter 的 `name` 创建技能目录；包含 `scripts/`、`references/`、`assets/` 等资源时可上传 `.zip`，压缩包根目录或唯一的一级目录中必须包含 `SKILL.md`；
- 上传后技能目录会自动添加 `x-` 前缀（已有前缀不会重复添加），并安装到实例的 `xpeech/agent/skills/buildin/` 目录；
- 同名技能不会直接覆盖，确认后才会以新版本替换；单个压缩包最大 20 MB，解压后最大 100 MB、最多 2000 个文件；
- 可在线编辑并原子保存 `SKILL.md`（最大 1 MB），保存前校验 YAML frontmatter 中是否包含 `name`；
- 可将包含 `scripts/`、`references/`、`assets/` 的完整技能下载为 ZIP，或一次迁移到多个目标实例；迁移遇到同名技能时先统一确认，再执行覆盖；
- 页面只列出和删除 `x-*` 自定义技能，仓库自带技能不属于可管理范围；这些目录由 Xpeech 的 `.gitignore` 忽略，因此 fetch 或版本切换不会把它们纳入仓库文件。

### Compose 操作

| 按钮 | 命令 | 超时 |
|---|---|---|
| Up | `docker compose up -d --build` | 30 分钟 |
| Start | `docker compose start` | 5 分钟 |
| Stop | `docker compose stop` | 5 分钟 |
| Restart | `docker compose restart` | 5 分钟 |
| Down | `docker compose down` | 5 分钟 |
| PS | `docker compose ps` | 30 秒 |

- 命令在实例目录中执行，参数以列表传递（禁止 Shell 拼接）；
- 整个平台同一时间只允许运行一个受管命令；不同实例以及 Git、Compose、镜像操作之间也互斥，重复请求立即返回 409，不排队；
- 超时后终止命令并返回「命令执行超时」；
- 结束后弹窗展示退出码、stdout、stderr，成功/失败分别以绿色/红色提示，内容支持复制；
- `Down` 有确认提示，只下线容器，不删除实例目录和数据；
- 不保存任何执行历史，不自动刷新状态。

### 拉取镜像

点击顶部「拉取镜像」可检查并分别拉取：

- `docker.1panel.live/library/ubuntu:22.04`：Xpeech Dockerfile 使用的基础镜像；
- `ghcr.io/browserless/chromium:v2.55.0`：Xpeech Compose 使用的 Browserless 镜像。

弹窗展示镜像是否已存在，并在存在时显示镜像 ID、大小和创建时间。每个镜像可单独拉取，拉取完成后自动刷新对应状态。

### System Console
 
点击顶部「Console」打开系统控制台。Git、Compose 以及镜像操作产生的命令、stdout、stderr 和退出码会按 JSONL 格式逐条追加到日志文件；只有打开 Console 时才会读取历史，然后继续展示实时输出。默认路径是 `<root_path>/.xpeech-deck/console.jsonl`，也可在 `conf.toml` 中使用 `console_log_path` 指定绝对或项目相对路径。后端重启不会清空文件；「清空显示」只清空当前前端内容。

更新到带 Console 的版本后必须重启 Xpeech Deck 后端进程，使 `/api/console/stream` 路由完成注册；仅重新构建前端会出现“Console 接口尚未加载”的提示。

## 开发

### 后端测试

```bash
uv run pytest
```

覆盖：认证、Git 克隆/fetch/版本切换、实例列表、配置编辑（端口/TOML 校验）、Compose 命令参数/超时/互斥、镜像状态检查与拉取、系统控制台缓存与流式输出。

### 前端开发

```bash
cd frontend
npm run dev   # 开发服务器 :5173，/api 与 /health 默认代理到 :7801
```

后端需先启动（`uv run python -m xpeech_deck`）。如果修改了后端监听端口，开发前端时可通过 `VITE_BACKEND_URL` 指定代理目标，例如 `VITE_BACKEND_URL=http://localhost:9000 npm run dev`。生产构建：

```bash
cd frontend
npm run build   # 产物输出到 ../xpeech_deck/static/，由 FastAPI 统一托管
```

## 目录结构

```text
xpeech-deck/
├── xpeech_deck/                # 后端
│   ├── __main__.py             # 入口（uvicorn :listen_port）
│   ├── app.py                  # FastAPI 路由与静态托管
│   ├── config.py               # conf.toml 读取与启动检查
│   ├── auth.py                 # URL Token 认证
│   ├── instance_service.py     # 实例发现/创建/配置
│   ├── git_service.py          # Git 克隆/fetch/版本切换
│   ├── compose_service.py      # Compose 执行器（超时+互斥）
│   ├── image_service.py        # 镜像检查与拉取
│   ├── skill_service.py        # 自定义内置技能安全安装与管理
│   ├── console_service.py      # 系统控制台事件缓存与广播
│   ├── schemas.py              # Pydantic 模型
│   └── static/                 # 前端构建产物
├── frontend/                   # React + TypeScript + Vite + Ant Design
│   └── src/
│       ├── App.tsx
│       ├── api.ts
│       ├── types.ts
│       ├── InstanceTable.tsx
│       ├── CreateInstanceModal.tsx
│       ├── ConfigInstanceModal.tsx
│       ├── CommandResultModal.tsx
│       ├── SkillManagementModal.tsx
│       └── VersionInstanceModal.tsx
├── tests/                      # pytest 测试
├── conf.toml.example
├── pyproject.toml
└── README.md
```

## 注意事项

- 以单进程方式运行（默认 `uvicorn.run` 无多 worker），保证平台级命令互斥生效；
- 端口占用冲突不主动检测，由 `docker compose` 报错并展示给用户；
- 实例目录不提供删除功能。
