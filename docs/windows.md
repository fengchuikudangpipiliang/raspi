# Face3 管理员系统

uv run uvicorn main:app --host 127.0.0.1 --port 8020 --reload
这是一个运行在本地电脑上的管理员后台，用来通过 Tailscale 网络访问树莓派人脸识别考勤系统暴露出的设备侧管理员 API。

当前项目严格围绕 [raspberry_pi_admin_api.md](/d:/code/ras_pi/raspberry_pi_admin_api.md) 描述的接口展开，实现目标是：

- 在 Windows 本地启动一个独立的管理后台。
- 不直接修改树莓派业务逻辑，只消费树莓派已经暴露的 HTTP API。
- 把树莓派设备状态、成员数据、人脸档案、考勤记录整合成可视化页面。
- 对接口调用做统一封装，保证后续继续扩展时不会把请求逻辑散落到页面里。

---

## 1. 项目已经完成了什么

当前版本已经完成以下能力，并且已经与实际树莓派设备完成过联调：

- 仪表盘
  - 展示树莓派健康状态。
  - 展示树莓派性能指标。
  - 展示今日考勤汇总。
  - 支持触发树莓派重新加载配置。
- 成员管理
  - 展示成员名单。
  - 展示用户列表。
  - 展示单个用户详情。
  - 支持更新用户状态。
  - 支持重置用户密码。
- 人脸档案
  - 展示已上传的人脸档案列表。
  - 支持按审核状态筛选待审核 / 已通过 / 已驳回。
  - 支持查看单条人脸档案的审核详情。
  - 支持提交通过 / 驳回 / 改回待审核的审核结果。
  - 通过本地代理方式显示人脸图片。
  - 支持删除指定人脸档案。
- 考勤记录
  - 展示考勤记录列表。
  - 展示今日考勤汇总。
  - 支持查看考勤快照代理链接。

结合目前实际联调结果，以下页面已经验证可工作：

- 仪表盘页面可以正确显示树莓派运行参数。
- 人脸档案页面可以正确显示已上传的人脸信息。
- 考勤记录页面可以正确显示已有考勤记录。
- 成员管理页面已兼容内置 `admin` 用户，不会再因为 `roster_member_id = null` 报“数据结构与文档不一致”。

---

## 2. 本项目的定位

这个项目不是树莓派端服务本身，而是“管理员前台/后台”。

职责边界如下：

- 树莓派项目负责：
  - 摄像头采集。
  - 人脸识别。
  - SQLite 数据写入。
  - 暴露 `/api/admin/*` 管理员接口。
- 本地管理员系统负责：
  - 读取环境变量，定位树莓派。
  - 附带管理员 Token 调用树莓派接口。
  - 把接口数据渲染成页面。
  - 对图片接口做本地代理，避免浏览器直接暴露 Token。

这样拆分之后，树莓派和管理员系统是低耦合的：

- 树莓派可以持续独立运行。
- 管理员系统可以部署在任意一台已加入 Tailnet 的电脑上。
- 后续页面重构、界面调整不需要去动树莓派采集逻辑。

---

## 3. 技术栈

- Python 3.9
- FastAPI
- Jinja2
- httpx
- pydantic / pydantic-settings
- uv
- Uvicorn

技术选型说明：

- 使用 FastAPI 作为本地管理员服务框架，路由清晰、异步支持好。
- 使用 Jinja2 模板快速落地传统后台页面，便于先把业务跑通。
- 使用 httpx 异步客户端统一请求树莓派，方便后续继续扩展接口。
- 使用 pydantic 做远端返回结构校验，能尽早发现“文档和真实返回不一致”的问题。
- 使用 uv 管理依赖，减少环境差异与安装成本。

---

## 4. 项目结构

```text
.
├─ app/
│  ├─ clients/
│  │  └─ pi_admin_client.py
│  ├─ routers/
│  │  ├─ proxy.py
│  │  └─ web.py
│  ├─ services/
│  │  └─ admin_console_service.py
│  ├─ __init__.py
│  ├─ app_factory.py
│  ├─ config.py
│  ├─ dependencies.py
│  ├─ exceptions.py
│  └─ models.py
├─ static/
│  └─ styles.css
├─ templates/
│  ├─ attendance.html
│  ├─ base.html
│  ├─ dashboard.html
│  ├─ face_profiles.html
│  ├─ members.html
│  └─ user_detail.html
├─ .env
├─ .env.example
├─ .gitignore
├─ .python-version
├─ main.py
├─ pyproject.toml
├─ README.md
├─ raspberry_pi_admin_api.md
└─ uv.lock
```

核心目录职责如下：

- `app/clients/`
  - 封装对树莓派管理员 API 的调用。
- `app/services/`
  - 聚合多个接口数据，供页面层直接使用。
- `app/routers/`
  - 页面路由和图片代理路由。
- `app/models.py`
  - 统一定义远端返回结构模型。
- `templates/`
  - 页面模板。
- `static/`
  - 页面样式。

---

## 5. 核心实现说明

### 5.1 统一请求层

[pi_admin_client.py](/d:/code/ras_pi/app/clients/pi_admin_client.py) 是整个管理员系统的数据入口。

这里完成了以下工作：

- 自动拼接 `FACE3_PI_BASE_URL`。
- 自动附带 `Authorization: Bearer <token>`。
- 自动处理超时与网络异常。
- 自动把非 2xx 响应转换成业务异常。
- 自动把远端 JSON 校验成强类型模型。
- 自动兼容图片等二进制接口。

这样做的好处是：

- 页面层不需要知道请求细节。
- 以后新增接口时，只需要在客户端里补一个方法。
- 如果要统一调整超时、请求头、异常处理，只改一处即可。

### 5.2 服务层聚合

[admin_console_service.py](/d:/code/ras_pi/app/services/admin_console_service.py) 负责把页面真正要的数据组合起来。

例如：

- 仪表盘页面同时需要：
  - `device/health`
  - `device/metrics`
  - `attendance/today-summary`
- 成员管理页面同时需要：
  - `roster-members`
  - `users`
- 考勤记录页面同时需要：
  - `attendance`
  - `attendance/today-summary`

这些组合逻辑放在服务层，而不是页面路由里，能保持页面层更薄、更清晰。

### 5.3 页面层

[web.py](/d:/code/ras_pi/app/routers/web.py) 负责：

- 读取查询参数和表单参数。
- 调用服务层。
- 把结果交给 Jinja2 模板渲染。
- 在发生异常时，把友好的错误消息显示到页面上。

页面本身不直接写请求逻辑，也不直接处理 Token。

### 5.4 图片代理

[proxy.py](/d:/code/ras_pi/app/routers/proxy.py) 负责图片代理。

这样做是为了避免前端页面直接拿树莓派接口地址加 Token 去请求图片资源。

目前代理的资源有：

- 人脸档案图片
- 考勤抓拍图

优势：

- 浏览器侧不暴露管理员 Token。
- 页面 `<img>` 直接使用本地路由即可。
- 后续如果要切换鉴权策略，不需要改模板结构。

### 5.5 数据模型校验

[models.py](/d:/code/ras_pi/app/models.py) 里定义了远端响应模型，目的是：

- 提前发现树莓派真实返回与文档描述不一致的问题。
- 避免“前端拿到一个字段后才发现不存在”的隐性错误。
- 把接口约束显式化。

这是这次联调里最有价值的一层保护，因为它真的帮我们发现了实际问题。

---

## 6. 页面与接口映射

### 6.1 仪表盘

页面：

- `/`

对应接口：

- `GET /api/admin/device/health`
- `GET /api/admin/device/metrics`
- `GET /api/admin/attendance/today-summary`
- `POST /api/admin/device/reload-config`

页面用途：

- 判断树莓派是否在线。
- 判断数据库是否可用。
- 查看 CPU 温度、负载、内存、磁盘使用情况。
- 查看当日签到人数与缺勤人数。

### 6.2 成员管理

页面：

- `/members`
- `/users/{user_id}`

对应接口：

- `GET /api/admin/roster-members`
- `GET /api/admin/users`
- `GET /api/admin/users/{user_id}`
- `POST /api/admin/users/{user_id}/status`
- `POST /api/admin/users/{user_id}/password/reset`

页面用途：

- 查看成员名单与用户列表的对应关系。
- 查看某个用户是否已经注册。
- 查看用户是否具备人脸档案。
- 执行用户启用、停用与密码重置。

### 6.3 人脸档案

页面：

- `/face-profiles`

对应接口：

- `GET /api/admin/face-profiles`
- `GET /api/admin/face-profiles/{face_profile_id}`
- `POST /api/admin/face-profiles/{face_profile_id}/review`
- `GET /api/admin/face-profiles/{face_profile_id}/image`
- `DELETE /api/admin/face-profiles/{face_profile_id}`

本地代理接口：

- `GET /proxy/face-profiles/{face_profile_id}/image`

页面用途：

- 查看已上传的人脸档案。
- 处理用户新上传的人脸审核。
- 按用户 ID 或编号筛选。
- 按审核状态筛选待审核 / 已通过 / 已驳回。
- 查看审核备注、审核人和审核时间。
- 提交通过 / 驳回 / 改回待审核。
- 删除指定人脸档案。

### 6.4 考勤记录

页面：

- `/attendance`

对应接口：

- `GET /api/admin/attendance`
- `GET /api/admin/attendance/today-summary`
- `GET /api/admin/attendance/{attendance_id}/snapshot`

本地代理接口：

- `GET /proxy/attendance/{attendance_id}/snapshot`

页面用途：

- 查看当天或指定日期考勤。
- 按编号或姓名筛选记录。
- 查看抓拍图入口。

---

## 7. 环境变量说明

把 `.env.example` 复制为 `.env` 后按实际环境修改。

示例：

```env
FACE3_PI_BASE_URL=http://100.74.44.24:5000
FACE3_PI_ADMIN_TOKEN=face3-admin-change-this-token
FACE3_REQUEST_TIMEOUT_SECONDS=15
APP_TITLE=Face3 管理员系统
APP_HOST=127.0.0.1
APP_PORT=8000
```

字段说明：

- `FACE3_PI_BASE_URL`
  - 树莓派管理员 API 的完整基地址。
  - 只写到主机和端口，不要手动拼 `/api/admin`。
  - 当前联调推荐使用 Tailscale 内网地址，例如 `http://100.74.44.24:5000`。
- `FACE3_PI_ADMIN_TOKEN`
  - 必须与树莓派 `env.json` 里的 `admin_api_token` 完全一致。
- `FACE3_REQUEST_TIMEOUT_SECONDS`
  - 本地管理员系统请求树莓派的超时时间。
- `APP_TITLE`
  - 本地管理员系统页面标题。
- `APP_HOST`
  - 本地服务监听地址。
- `APP_PORT`
  - 本地服务默认端口。

注意事项：

- 树莓派本身如果是 `uvicorn --host 0.0.0.0 --port 5000`，那这里通常就应该用 `http://...:5000`，而不是 `https://...:5000`。
- 如果你使用的是 Tailscale Funnel 暴露出来的 HTTPS 地址，那 `FACE3_PI_BASE_URL` 应该写 Funnel 的 HTTPS 根地址，而不是本地 5000 端口地址。
- 当前这个项目的实际联调已经确认，直接走 Tailnet 内网地址更简单、更稳定。

---

## 8. 安装依赖

项目依赖通过 `uv` 管理。

```bash
uv sync
```

如果当前环境里 `uv` 默认缓存目录权限不足，可以临时指定仓库内缓存目录：

```bash
UV_CACHE_DIR=.uv-cache uv sync
```

Windows PowerShell 示例：

```powershell
$env:UV_CACHE_DIR = "d:\code\ras_pi\.uv-cache"
uv sync
```

当前项目已使用的主要依赖如下：

- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `jinja2`
- `pydantic-settings`
- `python-multipart`

其中：

- `python-multipart` 是表单路由必需依赖。
- `httpx` 用于请求树莓派。
- `jinja2` 用于页面模板渲染。

---

## 9. VS Code / Cursor 配置说明

仓库已包含工作区级 VS Code 配置 [settings.json](d:/code/ras_pi/.vscode/settings.json)，会默认把解释器指向项目自己的 `.venv\Scripts\python.exe`。

这一步的目的，是解决编辑器里出现以下提示：

- `无法解析导入 "fastapi"`
- `无法解析导入 "fastapi.templating"`
- `无法解析导入 "pydantic"`
- `无法解析导入 "pydantic_settings"`

这些提示通常不是“真的缺包”，而是编辑器没有切到项目自己的虚拟环境。

如果编辑器里仍然看到 `Pylance(reportMissingImports)`，可以按下面顺序处理：

1. 关闭并重新打开当前工作区。
2. 执行 `Python: Select Interpreter`。
3. 确认选择的是 `d:\code\ras_pi\.venv\Scripts\python.exe`。
4. 执行 `Developer: Reload Window`。

---

## 10. 树莓派端如何启动

树莓派项目侧必须先启动管理员 API。

在树莓派项目目录执行：

```bash
cd /home/luck/face3
source .venv/bin/activate
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

启动条件：

- `web_host` 必须允许外部访问。
- `admin_api_token` 必须已配置。
- 当前电脑必须能通过 Tailnet 或指定地址访问树莓派。

推荐先在树莓派本机验证：

```bash
curl -i http://127.0.0.1:5000/api/admin/device/health \
  -H "Authorization: Bearer face3-admin-change-this-token"
```

如果这里返回 `200 OK` 和 JSON，就说明树莓派管理员 API 正常。

---

## 11. 本地管理员系统如何启动

在当前项目根目录执行：

```powershell
uv run uvicorn main:app --host 127.0.0.1 --port 8020 --reload
```

或者使用脚本入口：

```powershell
uv run face3-admin
```

注意：

- 如果你手动指定了 `--port 8020`，那么浏览器访问地址就是 `http://127.0.0.1:8020`。
- 如果你使用 `uv run face3-admin`，则默认读取 `.env` 里的 `APP_HOST` 和 `APP_PORT`。

启动顺序建议：

1. 先启动树莓派管理员 API。
2. 再启动本地管理员系统。
3. 最后打开浏览器访问本地地址。

---

## 12. 本次开发具体做了哪些工作

这一部分是对“这边到底写了什么”的详细说明。

### 12.1 从零搭建本地管理员后台项目

完成了以下基础设施搭建：

- 初始化 `pyproject.toml`
- 建立 `app/` 包结构
- 建立模板目录与静态资源目录
- 增加 `.env.example`
- 增加 `.gitignore`
- 增加 `.vscode/settings.json`

### 12.2 实现配置层

[config.py](/d:/code/ras_pi/app/config.py) 负责：

- 从 `.env` 读取配置。
- 校验 `FACE3_PI_BASE_URL` 是否是合法 HTTP/HTTPS 地址。
- 校验超时时间是否大于 0。
- 统一提供解密后的管理员 Token。

### 12.3 实现统一异常体系

[exceptions.py](/d:/code/ras_pi/app/exceptions.py) 定义了：

- `AdminConsoleError`
- `RemoteApiError`
- `RemoteApiTransportError`
- `RemoteApiResponseError`

作用是把网络错误、结构错误、业务错误区分开，页面提示更明确。

### 12.4 实现强类型模型

[models.py](/d:/code/ras_pi/app/models.py) 定义了：

- 设备信息模型
- 健康信息模型
- 性能指标模型
- 成员名单模型
- 用户列表与用户详情模型
- 人脸档案模型
- 考勤记录模型
- 今日汇总模型
- 通用详情响应与列表响应包裹模型

### 12.5 实现树莓派 API 客户端

[pi_admin_client.py](/d:/code/ras_pi/app/clients/pi_admin_client.py) 已实现：

- 设备信息接口
- 设备健康接口
- 设备性能接口
- 设备重载配置接口
- 成员名单接口
- 用户列表接口
- 用户详情接口
- 用户状态修改接口
- 用户密码重置接口
- 人脸档案列表接口
- 人脸档案详情接口
- 人脸档案审核接口
- 删除人脸档案接口
- 考勤记录接口
- 今日汇总接口
- 人脸图接口
- 抓拍图接口

### 12.6 实现服务层

[admin_console_service.py](/d:/code/ras_pi/app/services/admin_console_service.py) 负责：

- 聚合多个接口给仪表盘用
- 聚合成员名单和用户列表给成员管理页用
- 聚合考勤记录和汇总给考勤页用
- 包装修改用户状态、重置密码、人脸审核、人脸删除等动作

### 12.7 实现页面路由

[web.py](/d:/code/ras_pi/app/routers/web.py) 实现了：

- `/`
- `/members`
- `/users/{user_id}`
- `/face-profiles`
- 人脸档案审核表单
- `/attendance`
- 用户状态更新表单
- 用户密码重置表单
- 删除人脸档案表单
- 页面级错误回显

### 12.8 实现图片代理

[proxy.py](/d:/code/ras_pi/app/routers/proxy.py) 实现了：

- `GET /proxy/face-profiles/{face_profile_id}/image`
- `GET /proxy/attendance/{attendance_id}/snapshot`

### 12.9 完成前端页面

模板文件完成如下页面：

- [dashboard.html](/d:/code/ras_pi/templates/dashboard.html)
- [members.html](/d:/code/ras_pi/templates/members.html)
- [user_detail.html](/d:/code/ras_pi/templates/user_detail.html)
- [face_profiles.html](/d:/code/ras_pi/templates/face_profiles.html)
- [attendance.html](/d:/code/ras_pi/templates/attendance.html)

视觉层完成如下内容：

- 左侧导航布局
- 仪表盘卡片布局
- 表格布局
- 筛选表单布局
- 图片卡片布局
- 响应式适配

### 12.10 2026-04-25 页面视觉增强

在不修改任何业务功能、路由和表单交互的前提下，补做了一轮前端视觉升级，目标是让管理员后台更像“设备控制台”，同时保留当前温暖、克制、适合长时间查看的风格。

本次主要增强包括：

- 统一增强页面层次感
  - 通过更细的背景渐变、网格纹理、玻璃面板和更强的卡片层级，让页面不再只靠平面卡片堆叠。
- 增加轻量动态效果
  - 页面区块新增入场动画。
  - 卡片、按钮、图片、分页和表格行新增悬浮反馈。
  - 模态框新增柔和弹入效果。
  - 性能条和重点信息块新增更自然的过渡。
- 强化设备控制台气质
  - 顶部信息条、侧边栏、状态胶囊、表格头部和预览区域的视觉细节统一增强。
  - 更强调“监控面板 / 本地控制台”而不是普通 CRUD 后台。
- 保持无障碍与稳定性
  - 没有修改任何后端接口调用逻辑。
  - 没有修改任何页面业务能力。
  - 对 `prefers-reduced-motion` 做了兼容，避免动效影响可访问性。
  - 修复了“成员管理”导航悬浮操作框被主内容区遮挡的层级问题。
  - 仪表盘删除了部分冗余文案，并把“设备基础信息 / 设备健康”合并为单张“设备概览”卡片。
  - 左侧主导航增强为 hover 放大反馈，当前悬浮项会更明显。

### 12.11 完成联调修复

这次联调过程中，实际修复了以下问题：

- 缺少 `.env` 时本地服务无法正常连接树莓派。
- `.env` 中把 `http://100.x.x.x:5000` 误写成了 `https://100.x.x.x:5000`。
- 编辑器未选中项目 `.venv` 导致误报“缺少导入”。
- `python-multipart` 缺失导致表单路由无法注册。
- 成员管理页面因 `/api/admin/users` 中 `admin` 用户的 `roster_member_id = null` 导致模型校验失败。

---

## 13. 实际联调结论

经过联调，当前推荐连接方式如下：

```env
FACE3_PI_BASE_URL=http://100.74.44.24:5000
FACE3_PI_ADMIN_TOKEN=face3-admin-change-this-token
```

树莓派端：

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

本地管理员端：

```powershell
uv run uvicorn main:app --host 127.0.0.1 --port 8020 --reload
```

浏览器访问：

```text
http://127.0.0.1:8020
```

联调过程中已经确认：

- Windows 到树莓派 `100.74.44.24:5000` 可以直接访问。
- 树莓派 `device/health`、`device/metrics`、`attendance/today-summary` 返回正常。
- 本地仪表盘可以正确展示树莓派参数。
- 本地人脸档案页可以正确显示已上传人脸图片。
- 本地考勤记录页可以正确显示已有考勤信息。
- 成员管理页已修复 `admin` 用户导致的结构校验问题。

---

## 14. 已知边界

- 当前版本只面向单台树莓派设备，不包含多设备聚合。
- 当前版本没有管理员账号体系，完全依赖树莓派提供的 Token。
- 当前版本没有离线缓存与断线重试队列。
- 当前版本没有对图片做本地缓存。
- 当前版本没有实现成员名单导入。
- 当前版本没有实现考勤人工补录或修正。
- 设备侧如果存在独立的内置用户，例如 `admin`，其 `roster_member_id` 可能为 `null`，本地管理员系统已兼容该情况。

---

## 15. 常见问题排查

### 15.1 页面提示“树莓派接口调用失败，HTTP 502”

优先检查：

- `.env` 里的 `FACE3_PI_BASE_URL` 是否写对。
- 你是不是把 `http://...:5000` 错写成了 `https://...:5000`。
- 树莓派服务是否真的在 `0.0.0.0:5000` 监听。
- 电脑是否能直接访问树莓派 Tailscale IP。

建议直接在 Windows 上测试：

```powershell
curl http://100.74.44.24:5000/api/admin/device/health `
  -H "Authorization: Bearer face3-admin-change-this-token"
```

### 15.2 页面改了 `.env` 还是不生效

这是因为 `.env` 改动不一定会让现有 `uvicorn --reload` 进程重新完整加载配置。

建议：

1. 停掉当前本地管理员服务。
2. 重新启动 `uvicorn`。
3. 浏览器强制刷新。

### 15.3 编辑器报“无法解析导入 fastapi”

这是解释器没有切到项目 `.venv`，不是实际缺包。

处理方式：

1. 选择解释器为 `.venv\Scripts\python.exe`
2. Reload Window

### 15.4 成员管理页面报“树莓派返回的数据结构与文档不一致”

这次联调里已经确认原因：

- `/api/admin/users` 中内置 `admin` 用户返回了 `roster_member_id: null`
- 文档示例未体现这一点
- 本地模型原先写成了必填 `int`

当前版本已经兼容，不需要额外处理。

### 15.5 表单路由启动时报 multipart 相关错误

说明缺少：

- `python-multipart`

当前版本已经写入依赖，执行：

```bash
uv sync
```

即可。

---

## 16. 开发验证

可以先执行语法编译检查：

```bash
uv run python -m compileall main.py app
```

也可以单独做运行导入验证：

```bash
uv run python -c "from main import app; print(app.title)"
```

如果需要页面级验证，可以直接启动服务后访问：

- `/`
- `/members`
- `/face-profiles`
- `/attendance`

---

## 17. 后续建议

如果继续迭代，建议按下面顺序推进：

1. 优化成员管理页面
   - 明确区分“成员名单用户”和“内置系统用户”。
2. 增加更细粒度的错误提示
   - 把“文档不一致”具体到字段级。
3. 增加操作日志
   - 记录密码重置、状态修改、人脸删除。
4. 增加多设备支持
   - 支持在本地切换多台树莓派。
5. 增加认证与会话层
   - 避免当前所有管理员能力都依赖单个 Token。

---

## 18. 参考文档

- 项目接口规范文档：
  - [raspberry_pi_admin_api.md](/d:/code/ras_pi/raspberry_pi_admin_api.md)

- 关键实现文件：
  - [main.py](/d:/code/ras_pi/main.py)
  - [app_factory.py](/d:/code/ras_pi/app/app_factory.py)
  - [config.py](/d:/code/ras_pi/app/config.py)
  - [pi_admin_client.py](/d:/code/ras_pi/app/clients/pi_admin_client.py)
  - [admin_console_service.py](/d:/code/ras_pi/app/services/admin_console_service.py)
  - [web.py](/d:/code/ras_pi/app/routers/web.py)
  - [proxy.py](/d:/code/ras_pi/app/routers/proxy.py)
  - [models.py](/d:/code/ras_pi/app/models.py)

---

## 19. 2026-04-26 审核流补充同步

这一次是跟随树莓派侧 `admin2th.md` 的 `15.20` 与 `15.21` 增量，把管理员后台继续补齐到新的审核语义。

### 19.1 新增对接的接口与字段

- 新增对接 `GET /api/admin/face-profiles/rejection-reasons`
  - 用于拉取固定驳回原因选项列表。
- `POST /api/admin/face-profiles/{face_profile_id}/review`
  - 现在支持提交 `review_reason_codes`。
- `FaceProfile` 相关字段新增并已接入本地模型：
  - `review_reason_codes`
  - `review_reason_labels`
  - `recent_rejections`
- `GET /api/admin/users/{user_id}` 返回的用户详情已接入：
  - `recent_face_rejections`
  - `face_profile_recognition_ready`
- 用户汇总 / 用户详情新增并已接入：
  - `approved_face_profiles_count`
  - `pending_face_profiles_count`
  - `rejected_face_profiles_count`

### 19.2 管理员页面同步结果

- 人脸档案审核页 `/face-profiles`
  - 已增加固定驳回原因多选区。
  - 驳回时校验规则已调整为：
    - 至少选择一个固定原因，或填写补充备注，两者满足其一即可。
  - 已展示当前档案的固定驳回原因标签。
  - 已展示最近三次驳回历史。
  - 已增加降级处理：
    - 即使 `GET /api/admin/face-profiles/rejection-reasons` 临时失败，页面也仍可打开，管理员可先用补充备注继续审核。
- 用户详情页 `/users/{user_id}`
  - 已展示 `face_profile_recognition_ready`。
  - 已展示审核通过 / 待审核 / 已驳回计数。
  - 已展示最近三次人脸驳回历史。
  - 已展示每条人脸档案的审核状态、识别启用状态和驳回原因标签。
- 成员管理页 `/members`
  - 用户列表里已补轻量审核计数：
    - `A / P / R = approved / pending / rejected`
  - 用户列表里的人脸状态现在区分为：
    - `uploaded / missing`
    - `recognition / pending review`

### 19.3 当前与树莓派侧保持一致的业务语义

- `face_profile_ready`
  - 代表用户是否上传过照片。
- `face_profile_recognition_ready`
  - 代表用户是否已经存在一张“审核通过且可参与识别”的照片。
- 设备侧当前只保留用户最近一次上传成功的人脸照片。
- 历史驳回原因只保留最近三次，不再长期保留旧照片文件。
