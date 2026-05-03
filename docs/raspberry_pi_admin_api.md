# 树莓派设备侧管理员 API 文档

这份文档描述的是 **树莓派项目本身暴露的设备侧 API**。  
你未来在 Windows 电脑上编写的管理员项目，不需要和树莓派项目放在一起运行，只需要通过 Tailscale 网络访问这些 HTTP 接口即可。

## 1. 使用方式

推荐访问方式：

- Windows 电脑安装 Tailscale
- 树莓派安装 Tailscale
- 两台设备加入同一个 Tailnet
- Windows 管理项目直接请求树莓派的 Tailscale 地址

推荐示例：

- `http://100.x.x.x:5000/api/admin/device/health`
- `http://raspberrypi.your-tailnet.ts.net:5000/api/admin/device/health`

不推荐第一版就走真正公网暴露。  
管理员项目和树莓派都在 Tailscale 里时，直接走 Tailnet 内网更安全。

## 2. 树莓派配置

树莓派项目配置文件是：

- [env.json](/home/luck/face3/env.json)

管理员 API 相关配置项：

```json
{
  "web_host": "0.0.0.0",
  "web_port": 5000,
  "device_id": "face3-pi-01",
  "device_name": "Face3 Raspberry Pi",
  "device_location": "实验室门口",
  "admin_api_token": "face3-admin-change-this-token"
}
```

说明：

- `web_host` 必须是 `0.0.0.0`，这样 Windows 电脑才能通过网络访问
- `device_id` 是设备唯一标识
- `device_name` 是设备展示名称
- `device_location` 是安装位置
- `admin_api_token` 是管理员项目调用 API 时必须携带的鉴权令牌

上线前必须把 `admin_api_token` 改成你自己的随机长字符串。

## 3. 启动方式

在树莓派项目根目录执行：

```bash
cd /home/luck/face3
source .venv/bin/activate
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

如果你后面正式部署，建议去掉 `--reload`。

## 4. 鉴权方式

所有管理员 API 都要求鉴权。

推荐请求头：

```http
Authorization: Bearer 你的admin_api_token
```

也兼容：

```http
X-Admin-Token: 你的admin_api_token
```

推荐统一使用 `Authorization: Bearer ...`。

如果 Token 错误，服务会返回：

```json
{
  "detail": "管理员 API 鉴权失败。"
}
```

HTTP 状态码：

- `401`：Token 错误
- `503`：树莓派没有配置 `admin_api_token`

## 5. 返回格式约定

### 5.1 成功返回

详情接口一般返回：

```json
{
  "ok": true,
  "data": {
    "...": "..."
  }
}
```

列表接口一般返回：

```json
{
  "ok": true,
  "items": [],
  "total": 0
}
```

### 5.2 失败返回

业务错误一般返回：

```json
{
  "detail": "错误说明"
}
```

或者：

```json
{
  "ok": false,
  "message": "错误说明"
}
```

Windows 管理项目应优先按 HTTP 状态码判断是否成功，再读取 JSON 内容。

## 6. 接口总览

当前已经实现的接口分成 5 组：

- 设备信息与健康
- 成员与用户
- 人脸档案
- 考勤记录
- 管理控制

### 6.1 设备信息与健康

- `GET /api/admin/device/info`
- `GET /api/admin/device/health`
- `GET /api/admin/device/metrics`
- `POST /api/admin/device/reload-config`

### 6.2 成员与用户

- `GET /api/admin/roster-members`
- `POST /api/admin/roster-members/sync`
- `POST /api/admin/roster-members`
- `PUT /api/admin/roster-members/{roster_member_id}`
- `GET /api/admin/users`
- `GET /api/admin/users/{user_id}`
- `POST /api/admin/users/{user_id}/status`
- `POST /api/admin/users/{user_id}/password/reset`

### 6.3 人脸档案

- `GET /api/admin/face-profiles`
- `GET /api/admin/face-profiles/{face_profile_id}/image`
- `DELETE /api/admin/face-profiles/{face_profile_id}`

### 6.4 考勤记录

- `GET /api/admin/attendance`
- `GET /api/admin/attendance/today-summary`
- `GET /api/admin/attendance/{attendance_id}/snapshot`

## 7. 详细接口说明

### 7.1 获取设备基础信息

`GET /api/admin/device/info`

用途：

- 管理员后台首页展示设备信息
- 标识当前连接的是哪台树莓派

示例请求：

```http
GET /api/admin/device/info HTTP/1.1
Authorization: Bearer your-admin-token
```

示例返回：

```json
{
  "ok": true,
  "data": {
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00"
  }
}
```

### 7.2 获取设备健康状态

`GET /api/admin/device/health`

用途：

- 展示树莓派是否还活着
- 展示数据库是否可用
- 展示摄像头线程是否在运行
- 展示成员名单、人脸目录等基础文件状态

示例返回：

```json
{
  "ok": true,
  "data": {
    "ok": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00",
    "app_uptime_seconds": 155.3,
    "database": {
      "ok": true,
      "sqlite_path": "data/face3.db"
    },
    "camera": {
      "configured": true,
      "running": false,
      "last_frame_at": null,
      "last_opened_at": null,
      "last_error": null,
      "detected_faces": 0
    },
    "files": {
      "roster_exists": true,
      "faces_dir_exists": true,
      "snapshots_dir_exists": true
    },
    "admin_api": {
      "token_configured": true,
      "using_default_token": false
    }
  }
}
```

字段说明：

- `data.ok`：设备侧整体健康是否通过
- `database.ok`：数据库是否可访问
- `camera.running`：本地摄像头线程当前是否正在运行
- `camera.last_frame_at`：最后一次成功拿到摄像头帧的时间
- `admin_api.using_default_token`：是否还在使用默认 Token，生产环境应为 `false`

### 7.3 获取设备性能指标

`GET /api/admin/device/metrics`

用途：

- 后台展示 CPU 负载、内存、磁盘、温度

示例返回：

```json
{
  "ok": true,
  "data": {
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-20T20:10:00+08:00",
    "server_time": "2026-04-20T20:12:35+08:00",
    "system_uptime_seconds": 86400.2,
    "app_uptime_seconds": 155.3,
    "load_average": {
      "one_min": 0.25,
      "five_min": 0.18,
      "fifteen_min": 0.12
    },
    "memory": {
      "total_bytes": 2013265920,
      "available_bytes": 1288490188,
      "used_bytes": 724775732,
      "usage_percent": 36.0
    },
    "disk": {
      "path": "/home/luck/face3/data",
      "total_bytes": 62312374272,
      "available_bytes": 41231237120,
      "used_bytes": 21081137152,
      "usage_percent": 33.83
    },
    "temperature": {
      "cpu_celsius": 51.6
    },
    "process": {
      "pid": 12345
    }
  }
}
```

### 7.4 重新加载配置

`POST /api/admin/device/reload-config`

用途：

- 管理员项目修改树莓派 `env.json` 后，让树莓派重新加载配置

请求体：

- 无

示例返回：

```json
{
  "ok": true,
  "data": {
    "changed": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口"
  }
}
```

### 7.5 获取成员名单

`GET /api/admin/roster-members`

查询参数：

- `search`：按姓名或学号/工号模糊过滤
- `status`：按状态过滤，支持 `active` 或 `disabled`

示例：

```http
GET /api/admin/roster-members?search=张&status=active
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "name": "张三",
      "code": "S2026001",
      "role": "member",
      "status": "active",
      "created_at": "2026-04-20 10:00:00",
      "updated_at": "2026-04-20 10:00:00",
      "registered": true
    }
  ],
  "total": 1
}
```

### 7.6 获取用户列表

`GET /api/admin/users`

查询参数：

- `search`：按姓名或编号模糊过滤
- `status`：按成员状态过滤，支持 `active` 或 `disabled`
- `registered_only`：是否只返回已注册账号，`true` 或 `false`

示例：

```http
GET /api/admin/users?registered_only=true
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 2,
      "roster_member_id": 1,
      "name": "张三",
      "code": "S2026001",
      "role": "member",
      "status": "active",
      "registered": true,
      "password_changed_at": "2026-04-20 10:58:26",
      "last_login_at": "2026-04-20 11:40:12",
      "created_at": "2026-04-20 10:58:26",
      "face_profiles_count": 1,
      "face_profile_ready": true
    }
  ],
  "total": 1
}
```

### 7.7 获取单个用户详情

`GET /api/admin/users/{user_id}`

示例返回：

```json
{
  "ok": true,
  "data": {
    "id": 2,
    "roster_member_id": 1,
    "name": "张三",
    "code": "S2026001",
    "role": "member",
    "status": "active",
    "registered": true,
    "password_changed_at": "2026-04-20 10:58:26",
    "last_login_at": "2026-04-20 11:40:12",
    "created_at": "2026-04-20 10:58:26",
    "face_profiles_count": 1,
    "face_profile_ready": true,
    "face_profiles": [
      {
        "id": 2,
        "user_id": 2,
        "name": "张三",
        "code": "S2026001",
        "image_path": "data/faces/S2026001/20260420115512-1f76d4cc.jpeg",
        "created_at": "2026-04-20 03:55:12",
        "image_url": "/api/admin/face-profiles/2/image"
      }
    ]
  }
}
```

### 7.8 更新用户状态

`POST /api/admin/users/{user_id}/status`

用途：

- 启用或停用某个用户
- 实际上更新的是该用户关联的成员名单状态

请求体：

```json
{
  "status": "disabled"
}
```

允许值：

- `active`
- `disabled`

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2,
    "status": "disabled"
  }
}
```

### 7.9 重置用户登录密码

`POST /api/admin/users/{user_id}/password/reset`

用途：

- 仅针对已经完成首次注册的用户
- 直接重置 `users.password_hash`

请求体：

```json
{
  "new_password": "TempPass2026",
  "confirm_password": "TempPass2026"
}
```

密码规则：

- 至少 8 个字符
- 至少包含 1 个字母和 1 个数字
- 不能直接包含完整学号/工号
- 不能与姓名完全相同

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2
  }
}
```

### 7.10 获取人脸档案列表

`GET /api/admin/face-profiles`

查询参数：

- `limit`：返回条数，默认 100，最大 200
- `user_id`：按用户 ID 过滤
- `code`：按学号/工号精确过滤

示例：

```http
GET /api/admin/face-profiles?code=S2026001
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 2,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "image_path": "data/faces/S2026001/20260420115512-1f76d4cc.jpeg",
      "created_at": "2026-04-20 03:55:12",
      "image_url": "/api/admin/face-profiles/2/image"
    }
  ],
  "total": 1
}
```

### 7.11 获取人脸图片

`GET /api/admin/face-profiles/{face_profile_id}/image`

用途：

- 管理员后台直接显示用户人脸图片

说明：

- 这个接口直接返回图片文件，不是 JSON
- 仍然需要带管理员 Token

Windows 管理项目可直接把这个 URL 作为 `<img>` 或图片下载地址使用。  
如果使用浏览器组件或前端框架，需要确保请求头里能带上 `Authorization`。

### 7.12 删除人脸档案

`DELETE /api/admin/face-profiles/{face_profile_id}`

用途：

- 删除数据库中的人脸档案记录
- 同时删除磁盘上的照片文件

成功返回：

```json
{
  "ok": true,
  "data": {
    "deleted": true,
    "face_profile_id": 2
  }
}
```

### 7.13 获取考勤记录列表

`GET /api/admin/attendance`

查询参数：

- `limit`：默认 50，最大 300
- `date`：按日期过滤，格式 `YYYY-MM-DD`
- `code`：按编号精确过滤
- `name`：按姓名模糊过滤

示例：

```http
GET /api/admin/attendance?date=2026-04-20&limit=100
```

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 11,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "check_type": "check_in",
      "check_time": "2026-04-20 08:01:25",
      "snapshot_path": "data/snapshots/20260420/xxx.jpg",
      "snapshot_url": "/api/admin/attendance/11/snapshot",
      "confidence": 0.91
    }
  ],
  "total": 1
}
```

### 7.14 获取今日考勤汇总

`GET /api/admin/attendance/today-summary`

查询参数：

- `date`：可选，格式 `YYYY-MM-DD`

说明：

- 如果不传 `date`，默认返回树莓派本地当天的汇总

示例返回：

```json
{
  "ok": true,
  "data": {
    "date": "2026-04-20",
    "registered_users": 12,
    "checked_in_users": 9,
    "attendance_records": 9,
    "absent_users": 3
  }
}
```

### 7.15 获取考勤快照

`GET /api/admin/attendance/{attendance_id}/snapshot`

用途：

- 在管理员后台查看某条考勤记录对应的抓拍图

说明：

- 该接口直接返回图片文件，不是 JSON
- 如果该考勤记录没有快照，会返回 `404`

## 8. Windows 管理项目推荐调用方式

推荐把树莓派基地址和 Token 配成环境变量：

```txt
FACE3_PI_BASE_URL=http://raspberrypi.tailnet-name.ts.net:5000
FACE3_PI_ADMIN_TOKEN=your-admin-token
```

请求时统一带：

```http
Authorization: Bearer your-admin-token
```

推荐在 Windows 管理项目里封装一个统一请求层：

- 自动拼接 `base_url`
- 自动附带 Bearer Token
- 自动处理 `401`
- 自动把非 2xx 转成异常

## 9. 建议的 Windows 后台页面对应关系

你后面 Windows 管理项目可以直接按下面映射做：

- 仪表盘
  - `/api/admin/device/health`
  - `/api/admin/device/metrics`
  - `/api/admin/attendance/today-summary`

- 成员管理
  - `/api/admin/roster-members`
  - `/api/admin/users`
  - `/api/admin/users/{user_id}`
  - `/api/admin/users/{user_id}/status`
  - `/api/admin/users/{user_id}/password/reset`

- 人脸档案
  - `/api/admin/face-profiles`
  - `/api/admin/face-profiles/{face_profile_id}/image`
  - `/api/admin/face-profiles/{face_profile_id}`

- 考勤记录
  - `/api/admin/attendance`
  - `/api/admin/attendance/today-summary`
  - `/api/admin/attendance/{attendance_id}/snapshot`

## 10. 当前版本限制

当前设备侧 API 已经够你编写第一版管理员项目，但有几个边界需要明确：

- 暂时没有多树莓派聚合能力
- 暂时没有管理员账号体系，只有 Token 鉴权
- 暂时没有考勤记录人工修改接口
- `face_profile` 和 `attendance` 图片访问仍然依赖管理员请求时附带 Token

## 11. 推荐下一步

等你 Windows 管理项目第一版能跑起来以后，树莓派这边建议继续加：

- 考勤记录人工补录/修正接口
- 成员名单批量导入、删除和 Excel 导入接口
- 人脸档案审核与替换接口
- 操作日志接口
- 管理员 Token 轮换机制

## 12. 文档对应源码

本次 API 主要实现位置：

- [main.py](/home/luck/face3/main.py)
- [scripts/admin_api.py](/home/luck/face3/scripts/admin_api.py)
- [scripts/device_status_service.py](/home/luck/face3/scripts/device_status_service.py)
- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)
- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)

## 13. 2026-04-21 增量变更记录

这一节只写 **相对于上一版文档新增的变化**，方便 Windows 管理项目按增量适配。

### 13.1 是否改动了 Windows 端原有接口

没有改动已有接口的：

- 路由路径
- HTTP 方法
- 鉴权方式
- 主要返回结构外层格式

也就是说，下面这些接口地址没有变：

- `/api/admin/device/info`
- `/api/admin/device/health`
- `/api/admin/device/metrics`
- `/api/admin/roster-members`
- `/api/admin/users`
- `/api/admin/users/{user_id}`
- `/api/admin/face-profiles`
- `/api/admin/attendance`
- `/api/admin/attendance/today-summary`

所以如果 Windows 那边已经按这些地址写请求，**请求本身不会失效**。

### 13.2 本次属于“新增字段”，不是破坏性修改

这次新增的是树莓派本地严格识别接入后带出来的状态字段，主要体现在：

- `GET /api/admin/device/health`

`data.camera` 下新增字段：

- `known_faces_count`
- `last_attendance_message`
- `last_attendance_record`

新增字段示例：

```json
{
  "camera": {
    "configured": true,
    "running": true,
    "last_frame_at": "2026-04-21T09:30:10+08:00",
    "last_opened_at": "2026-04-21T09:28:00+08:00",
    "last_error": null,
    "detected_faces": 1,
    "known_faces_count": 3,
    "last_attendance_message": "签到成功: 张三/S2026001",
    "last_attendance_record": {
      "attendance_id": 15,
      "user_id": 2,
      "name": "张三",
      "code": "S2026001",
      "confidence": 0.93,
      "snapshot_path": "data/snapshots/20260421/20260421093010-S2026001.jpg"
    }
  }
}
```

说明：

- `known_faces_count`：当前树莓派终端已加载到内存中的可识别人脸档案数量
- `last_attendance_message`：最近一次识别状态提示，适合 Windows 后台首页直接显示
- `last_attendance_record`：最近一次真正写入成功的考勤记录摘要

### 13.3 本次新增的运行行为

树莓派本地终端识别现在已经接入严格识别流程。

新增行为：

- 本地摄像头会对已注册用户做严格人脸识别
- 满足稳定识别条件后，会自动写入 `attendance_records`
- 同时自动保存一张考勤快照到 `data/snapshots/...`

这意味着 Windows 端已有的下面两个接口，现在会开始读到真实新增数据：

- `GET /api/admin/attendance`
- `GET /api/admin/attendance/today-summary`

如果 Windows 后台之前已经实现了考勤记录列表和今日汇总页面，那么现在它们应该会自然看到新识别产生的数据，不需要改请求地址。

### 13.4 Windows 端是否一定能接收到

结论：

- 如果 Windows 端只是按接口地址发请求并读取已有字段，那么**可以继续正常工作**
- 如果 Windows 端对 JSON 做了“严格字段白名单反序列化”，那就需要把新增字段设为可选字段

最稳妥的建议：

- Windows 端数据模型对 `device/health` 的 `camera` 对象使用“可选字段兼容”
- 不要要求返回 JSON 必须和旧版字段完全一致

推荐把下面 3 个字段在 Windows 端定义为可选：

- `known_faces_count?: number`
- `last_attendance_message?: string | null`
- `last_attendance_record?: object | null`

### 13.5 Windows 端 AI 需要重点知道的结论

给 Windows 侧 AI 的一句话总结：

- 本次没有改管理员 API 的路由和鉴权
- 只是给 `/api/admin/device/health` 增加了几个可选字段
- 树莓派本地终端现在会自动写入真实考勤记录和快照
- 所以 Windows 侧只需要兼容新增字段，不需要重写原有请求层

## 14. 2026-04-22 增量变更记录

这一节只描述 **本次和考勤规则有关的增量变化**，方便 Windows 侧 AI 直接理解，不用反复翻前文。

### 14.1 为什么这次要改

本次改动的核心原因不是“为了做一个更复杂的考勤系统”，而是为了解决两个现实问题：

- 树莓派终端在识别成功后，之前会直接写考勤记录，容易在测试时连续生成多条重复签到
- Windows 管理端虽然能看到结果，但以前很难知道“这条记录为什么被写入”或者“为什么这次识别明明成功了却没有写入”

所以这一版新增了一个 **轻量、可配置、可解释** 的考勤规则层，放在“识别成功”和“真正写数据库”之间。

它的设计意图是：

- 让树莓派端在识别成功后，先按业务规则做最后一层门禁
- 让测试阶段可以使用更宽松的规则，方便反复演示
- 让后期切回正式规则时，不需要重写主流程，只要改配置
- 让 Windows 管理端能读到“当前设备到底按什么规则在运行”和“最近一次为什么放行/拦截”

### 14.2 这次没有改什么

本次 **没有** 修改这些内容：

- 管理员 API 路由地址
- Bearer Token 鉴权方式
- 考勤记录列表接口地址
- 快照读取接口地址

也就是说，Windows 端原来的请求 URL 可以继续使用。

### 14.3 当前树莓派实际生效的考勤规则

本次已经把考勤规则做成配置项。

当前树莓派 `env.json` 默认配置为：

- `attendance_rule_mode = interval_only`
- `attendance_duplicate_block_seconds = 60`
- `attendance_daily_check_in_limit = 1`
- `attendance_policy_feedback_seconds = 4`

当前这套配置的真实含义是：

- 现在处于 **测试友好模式**
- 同一用户识别成功后，`60` 秒内再次识别成功，不会重复写入签到
- 超过 `60` 秒后，可以再次写入，方便你反复测试
- 虽然配置里仍保留“每天最多签到 1 次”的参数，但在 `interval_only` 模式下，当前主要执行的是“固定时间间隔拦截”

后期如果要切回更接近正式使用的规则，只需要把：

- `attendance_rule_mode`

改成：

- `daily_once`

就会切换为“每天最多签到 N 次”的规则，不需要改代码主流程。

### 14.4 本次管理员 API 新增的可见字段

这次没有新增路由，但有两类返回内容变得更丰富了。

#### 一类：设备级考勤规则摘要

下面两个接口返回的 `data` 里，现在会包含：

- `attendance_policy`

涉及接口：

- `GET /api/admin/device/info`
- `GET /api/admin/device/metrics`
- `GET /api/admin/device/health`

新增字段示例：

```json
{
  "attendance_policy": {
    "rule_mode": "interval_only",
    "duplicate_block_seconds": 60,
    "daily_check_in_limit": 1,
    "policy_feedback_seconds": 4,
    "attendance_window": {
      "start_time": "00:00",
      "end_time": "23:59"
    },
    "testing_friendly": true
  }
}
```

字段解释：

- `rule_mode`：当前规则模式。`interval_only` 表示测试友好的“间隔限制模式”，`daily_once` 表示更正式的“每天限制模式”
- `duplicate_block_seconds`：同一用户两次成功签到之间，至少要间隔多少秒
- `daily_check_in_limit`：在 `daily_once` 模式下，每天允许的最大签到次数
- `policy_feedback_seconds`：一次规则判定结果在终端状态区保留多少秒，方便现场观察
- `attendance_window`：当前设备允许签到的基础时间窗
- `testing_friendly`：是否处于更适合现场反复演示的测试规则模式

这组字段的意义不是为了“做 UI 花活”，而是为了让 Windows 端能够解释设备行为。  
以后如果管理员看到某台树莓派明明识别到人却没有继续写库，先看 `attendance_policy`，就能知道这是不是设备当前规则本来就不允许。

#### 二类：最近一次规则判定结果

`GET /api/admin/device/health` 的 `data.camera` 下，现在新增：

- `last_policy_event`

示例：

```json
{
  "camera": {
    "last_policy_event": {
      "code": "attendance_duplicate_interval_blocked",
      "label": "重复签到",
      "detail": "当前规则限制 60 秒内只允许签到一次，还需等待 41 秒。",
      "percent": 100,
      "allowed": false,
      "at": "2026-04-22T20:40:18+08:00",
      "user_id": 2,
      "name": "张三",
      "code_text": "S2026001"
    }
  }
}
```

这个对象的意义是：

- 告诉管理员端“最近一次业务规则判断，到底是放行了还是拦截了”
- 不是识别引擎层面的模糊/侧脸/多人入镜原因
- 而是更靠近业务写库层的最终结论

常见 `code` 含义：

- `attendance_recorded`：已经真正写入签到记录
- `attendance_duplicate_interval_blocked`：被“短时间重复签到限制”拦截
- `attendance_daily_limit_reached`：被“每天最大签到次数限制”拦截
- `attendance_allowed`：规则校验通过，允许写入

### 14.5 Windows 侧 AI 需要特别注意什么

Windows 侧不要再把“识别成功”直接等同于“已经写入考勤”。

更准确的理解应该是：

1. 先有人脸识别成功
2. 再经过树莓派本地考勤规则判断
3. 最后才真正写入 `attendance_records`

这意味着：

- 如果只看终端视频上“已匹配”，不能保证数据库里一定新增了记录
- 更可靠的判断应该结合：
  - `camera.last_policy_event`
  - `camera.last_attendance_record`
  - `/api/admin/attendance` 最新一条记录

### 14.6 这次改动的创新点到底是什么

这次不是简单加一个“冷却时间”变量，而是把原来容易混在一起的两层逻辑拆开了：

- 第一层：识别层
  - 负责判断是不是这个人
  - 负责判断当前画面是否满足识别条件

- 第二层：考勤规则层
  - 负责判断“即使已经识别成功，这次要不要真的写入数据库”

这样拆开的价值在于：

- 终端识别逻辑和业务规则逻辑不会继续纠缠在一起
- 测试模式和正式模式都能复用同一条写库链路
- Windows 端以后做日志、解释、排查时会更清楚
- 后续如果改成“每天一次签到”“每天一次签到加一次签退”，不需要推翻现有结构

### 14.7 给 Windows 侧 AI 的最终一句话总结

本次管理员 API **没有改路由**，但树莓派设备状态相关接口现在多了一层“考勤规则可解释信息”。

Windows 侧如果要正确理解树莓派当前行为，至少要兼容这两类新增字段：

- `attendance_policy`
- `camera.last_policy_event`

这次改动的本质目的，是让“识别成功”和“最终写库成功”这两个阶段彻底分开，并且都能被管理员端读懂。

## 15. 当前源码对齐版完整接口契约

这一节的目标不是再讲设计思路，而是给 Windows 管理端一个 **可以直接照着实现请求层、数据模型和功能按钮** 的完整契约说明。  
如果前文某些示例和这里有出入，以这一节和当前源码实现为准。

统一约定：

- 基础前缀：`/api/admin`
- 所有接口都要求管理员 Token
- 图片接口返回的是文件流，不是 JSON
- JSON 接口成功时统一返回 `{"ok": true, ...}`
- JSON 接口失败时优先看 HTTP 状态码，再看 `detail` 或 `message`

### 15.1 `GET /api/admin/device/info`

用途：

- 读取当前树莓派设备身份信息
- 读取当前生效的考勤规则摘要

请求参数：

- 无

成功返回：

```json
{
  "ok": true,
  "data": {
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-23T10:12:00+08:00",
    "server_time": "2026-04-23T10:30:12+08:00",
    "attendance_policy": {
      "rule_mode": "interval_only",
      "duplicate_block_seconds": 60,
      "daily_check_in_limit": 1,
      "policy_feedback_seconds": 4,
      "attendance_window": {
        "start_time": "00:00",
        "end_time": "23:59"
      },
      "testing_friendly": true
    }
  }
}
```

字段说明：

- `device_id`：设备唯一标识，适合在 Windows 端做节点主键
- `device_name`：设备展示名称
- `device_location`：安装位置
- `attendance_policy`：当前树莓派真正正在执行的考勤规则摘要

常见错误：

- `401`：管理员 Token 错误
- `503`：树莓派未配置管理员 Token

### 15.2 `GET /api/admin/device/health`

用途：

- 读取设备整体健康状态
- 读取摄像头运行信息
- 读取最近一次签到结果和最近一次规则判定结果

请求参数：

- 无

成功返回中的关键字段：

```json
{
  "ok": true,
  "data": {
    "ok": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口",
    "app_name": "face3",
    "hostname": "raspberrypi",
    "fqdn": "raspberrypi.tailnet-name.ts.net",
    "web_host": "0.0.0.0",
    "web_port": 5000,
    "started_at": "2026-04-23T10:12:00+08:00",
    "server_time": "2026-04-23T10:30:12+08:00",
    "attendance_policy": {
      "rule_mode": "interval_only",
      "duplicate_block_seconds": 60,
      "daily_check_in_limit": 1,
      "policy_feedback_seconds": 4,
      "attendance_window": {
        "start_time": "00:00",
        "end_time": "23:59"
      },
      "testing_friendly": true
    },
    "app_uptime_seconds": 1080.5,
    "database": {
      "ok": true,
      "sqlite_path": "data/face3.db"
    },
    "camera": {
      "configured": true,
      "running": true,
      "last_frame_at": "2026-04-23T10:30:10+08:00",
      "last_opened_at": "2026-04-23T10:28:00+08:00",
      "last_error": null,
      "detected_faces": 1,
      "known_faces_count": 3,
      "last_attendance_message": "签到成功: 张三/S2026001",
      "last_attendance_record": {
        "attendance_id": 22,
        "user_id": 2,
        "name": "张三",
        "code": "S2026001",
        "confidence": 0.91,
        "snapshot_path": "data/snapshots/20260423/20260423102341-S2026001.jpg"
      },
      "last_policy_event": {
        "code": "attendance_recorded",
        "label": "已签到",
        "detail": "张三 S2026001 签到成功",
        "percent": 100,
        "allowed": true,
        "at": "2026-04-23T10:23:41+08:00",
        "user_id": 2,
        "name": "张三",
        "code_text": "S2026001",
        "attendance_id": 22,
        "snapshot_path": "data/snapshots/20260423/20260423102341-S2026001.jpg"
      }
    },
    "files": {
      "roster_exists": true,
      "faces_dir_exists": true,
      "snapshots_dir_exists": true
    },
    "admin_api": {
      "token_configured": true,
      "using_default_token": false
    }
  }
}
```

字段说明：

- `data.ok`：整机健康状态汇总
- `database.ok`：数据库连通性
- `camera.running`：摄像头后台线程是否在运行
- `camera.last_error`：最近一次摄像头或识别错误
- `camera.known_faces_count`：已加载到识别器内存中的人脸档案数量
- `camera.last_attendance_message`：最近一次终端识别状态文案
- `camera.last_attendance_record`：最近一次真实写库成功的签到摘要
- `camera.last_policy_event`：最近一次业务规则判断结果，Windows 管理端应把它理解为“最后一步门禁解释”

对 Windows 管理端很重要的一点：

- `last_attendance_record` 表示“真的已经写进数据库”
- `last_policy_event` 表示“最近一次规则判断结论”
- 不要只根据终端页上“已匹配”去判断签到是否成功

### 15.3 `GET /api/admin/device/metrics`

用途：

- 读取树莓派运行指标
- 读取当前考勤规则摘要

请求参数：

- 无

成功返回中的关键字段：

- `system_uptime_seconds`
- `app_uptime_seconds`
- `load_average`
- `memory`
- `disk`
- `temperature.cpu_celsius`
- `process.pid`
- `attendance_policy`

说明：

- 这个接口更偏设备监控，不直接承担业务列表展示
- 但它同样会返回 `attendance_policy`，方便 Windows 端在设备详情页统一展示当前规则

### 15.4 `POST /api/admin/device/reload-config`

用途：

- 树莓派重新读取 `env.json`
- 让修改后的配置热加载生效

请求体：

- 无

成功返回：

```json
{
  "ok": true,
  "data": {
    "changed": true,
    "device_id": "face3-pi-01",
    "device_name": "Face3 Raspberry Pi",
    "device_location": "实验室门口"
  }
}
```

字段说明：

- `changed = true`：本次检测到配置变化并已重新加载
- `changed = false`：调用成功，但配置文件没有变化

Windows 端可实现的功能：

- “重新加载树莓派配置”按钮

### 15.5 `GET /api/admin/roster-members`

用途：

- 获取成员名单原始记录
- 判断某个名单成员是否已经注册

查询参数：

- `search`：可选，按姓名或编号过滤
- `status`：可选，只支持 `active` 或 `disabled`

成功返回单项字段：

- `id`
- `name`
- `code`
- `role`
- `status`
- `created_at`
- `updated_at`
- `registered`

字段说明：

- `registered = true`：该成员已经完成正式注册
- `registered = false`：名单里有这个人，但还没完成首次注册

Windows 端可实现的功能：

- 名单管理页
- “是否已完成注册”筛选

### 15.6 `GET /api/admin/users`

用途：

- 获取已创建的用户账号列表

查询参数：

- `search`：可选，按姓名或编号过滤
- `status`：可选，按成员状态过滤
- `registered_only`：可选，`true` 或 `false`

成功返回单项字段：

- `id`
- `roster_member_id`
- `name`
- `code`
- `role`
- `status`
- `registered`
- `password_changed_at`
- `last_login_at`
- `created_at`
- `face_profiles_count`
- `face_profile_ready`

字段说明：

- `registered`：是否已经设置正式登录密码
- `face_profiles_count`：已上传的人脸档案数量
- `face_profile_ready`：是否至少具备一份人脸档案

Windows 端可实现的功能：

- 用户列表页
- 已注册/未注册筛选
- 已录脸/未录脸筛选

### 15.7 `GET /api/admin/users/{user_id}`

用途：

- 获取单个用户详情
- 同时附带这个人的人脸档案列表

路径参数：

- `user_id`：必须为有效用户 ID

成功返回：

- 外层仍是 `{"ok": true, "data": {...}}`
- `data` 包含用户摘要字段
- `data.face_profiles` 为数组

`face_profiles` 单项字段：

- `id`
- `user_id`
- `name`
- `code`
- `image_path`
- `created_at`
- `image_url`

常见错误：

- `404`：用户不存在

Windows 端可实现的功能：

- 用户详情页
- 单个用户的人脸档案卡片

### 15.8 `POST /api/admin/users/{user_id}/status`

用途：

- 启用或停用用户

注意：

- 这个接口实际改的是该用户所关联的 `roster_members.status`
- 不是单独改 `users` 表里的字段

请求体：

```json
{
  "status": "disabled"
}
```

允许值：

- `active`
- `disabled`

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2,
    "status": "disabled"
  }
}
```

常见错误：

- `400`：状态值非法
- `400`：该用户没有绑定成员名单，无法更新
- `404`：用户不存在

Windows 端可实现的功能：

- 用户启用/停用开关

### 15.9 `POST /api/admin/users/{user_id}/password/reset`

用途：

- 重置某个已注册用户的正式登录密码

请求体：

```json
{
  "new_password": "Abcd1234",
  "confirm_password": "Abcd1234"
}
```

密码规则：

- 至少 8 个字符
- 至少包含 1 个字母和 1 个数字
- 不能直接包含完整学号/工号
- 不能与姓名完全相同

成功返回：

```json
{
  "ok": true,
  "data": {
    "updated": true,
    "user_id": 2
  }
}
```

常见错误：

- `400`：请求体不是 JSON 对象
- `400`：密码不符合规则
- `400`：用户尚未完成首次注册，不能直接重置
- `404`：用户不存在

Windows 端可实现的功能：

- 管理员重置用户密码

这也是为什么 Windows 端后台必须把这个接口接上。  
不需要读取明文旧密码，只需要提交新密码即可完成管理员侧重置。

### 15.10 `GET /api/admin/face-profiles`

用途：

- 获取人脸档案列表

查询参数：

- `limit`：默认 100，最大 200
- `user_id`：可选，按用户 ID 过滤
- `code`：可选，按编号精确过滤

成功返回单项字段：

- `id`
- `user_id`
- `name`
- `code`
- `image_path`
- `created_at`
- `image_url`

Windows 端可实现的功能：

- 人脸档案列表
- 指定用户的人脸档案过滤

### 15.11 `GET /api/admin/face-profiles/{face_profile_id}/image`

用途：

- 读取指定人脸档案的原图

返回类型：

- 文件流
- 不是 JSON

常见错误：

- `404`：人脸档案不存在
- `404`：对应图片文件不存在
- `400`：路径非法

Windows 端实现注意事项：

- 如果是服务端去拉图，直接带 Bearer Token 请求即可
- 如果是前端浏览器直接请求图片 URL，要确认请求头能带上 `Authorization`

### 15.12 `DELETE /api/admin/face-profiles/{face_profile_id}`

用途：

- 删除一条人脸档案
- 同时尝试删除落盘图片文件

成功返回：

```json
{
  "ok": true,
  "data": {
    "deleted": true,
    "face_profile_id": 2
  }
}
```

常见错误：

- `404`：人脸档案不存在

Windows 端可实现的功能：

- 删除错误档案
- 删除重复档案
- 让用户重新上传更清晰的人脸资料

### 15.13 `GET /api/admin/attendance`

用途：

- 获取考勤记录列表

查询参数：

- `limit`：默认 50，最大 300
- `date`：可选，格式 `YYYY-MM-DD`
- `code`：可选，按编号精确过滤
- `name`：可选，按姓名模糊过滤

成功返回单项字段：

- `id`
- `user_id`
- `name`
- `code`
- `check_type`
- `check_time`
- `snapshot_path`
- `snapshot_url`
- `confidence`

字段说明：

- `check_type`：当前代码里主要是 `check_in`
- `snapshot_url`：如果存在快照，则返回对应图片接口路径
- `check_time`：树莓派本地时区时间字符串

Windows 端可实现的功能：

- 考勤流水表
- 按日期、姓名、工号筛选
- 点击查看对应快照

### 15.14 `GET /api/admin/attendance/today-summary`

用途：

- 读取某一天的考勤汇总

查询参数：

- `date`：可选，格式 `YYYY-MM-DD`

不传 `date` 时：

- 默认返回树莓派当前本地日期对应的汇总

成功返回字段：

- `date`
- `registered_users`
- `checked_in_users`
- `attendance_records`
- `absent_users`

字段说明：

- `registered_users`：当前用户总数
- `checked_in_users`：指定日期内至少签到过一次的不同用户数
- `attendance_records`：指定日期内总签到流水数
- `absent_users`：`registered_users - checked_in_users`

Windows 端可实现的功能：

- 仪表盘顶部汇总卡
- 指定日期的统计切换

### 15.15 `GET /api/admin/attendance/{attendance_id}/snapshot`

用途：

- 读取某条考勤记录对应的抓拍图

返回类型：

- 文件流

常见错误：

- `404`：考勤记录不存在
- `404`：该记录没有快照
- `404`：快照文件不存在
- `400`：路径非法

Windows 端可实现的功能：

- 考勤记录详情预览
- 快照查看与下载

### 15.16 Windows 管理端必须至少覆盖哪些功能

如果 Windows 管理端要覆盖树莓派目前已经暴露的全部能力，至少应该把下面这些功能接起来：

- 设备信息查看
  - `GET /api/admin/device/info`
  - `GET /api/admin/device/health`
  - `GET /api/admin/device/metrics`
- 配置热重载
  - `POST /api/admin/device/reload-config`
- 成员与用户查看
  - `GET /api/admin/roster-members`
  - `POST /api/admin/roster-members/sync`
  - `POST /api/admin/roster-members`
  - `PUT /api/admin/roster-members/{roster_member_id}`
  - `GET /api/admin/users`
  - `GET /api/admin/users/{user_id}`
- 用户状态管理
  - `POST /api/admin/users/{user_id}/status`
- 用户密码重置
  - `POST /api/admin/users/{user_id}/password/reset`
- 人脸档案查看与删除
  - `GET /api/admin/face-profiles`
  - `GET /api/admin/face-profiles/{face_profile_id}/image`
  - `DELETE /api/admin/face-profiles/{face_profile_id}`
- 考勤记录与快照查看
  - `GET /api/admin/attendance`
  - `GET /api/admin/attendance/today-summary`
  - `GET /api/admin/attendance/{attendance_id}/snapshot`

### 15.17 这份文档对 Windows 端的最终要求

Windows 端如果要“完成树莓派当前提供的所有功能”，最低要求是：

- 路由层把以上所有接口都接入
- 数据模型兼容新增字段，尤其是：
  - `attendance_policy`
  - `camera.last_policy_event`
- 对文件流接口和 JSON 接口做分开处理
- 把名单同步、名单新增、名单编辑、密码重置、用户状态更新、人脸删除这类写操作真正接到按钮事件，而不是只展示只读页面

这一节写完之后，Windows 端不需要再去猜接口能力边界。  
只要按这里逐项接入，就能覆盖树莓派目前已经提供的全部管理员功能。

### 15.18 2026-04-23 名单热同步与在线维护新增说明

这次新增的目标很明确：

- 解决 `data/member_roster.csv` 更新后，Windows 管理端查 `GET /api/admin/roster-members` 仍然看不到新成员的问题
- 允许 Windows 管理端直接通过设备侧管理员 API 新增和修改成员名单
- 确保名单写操作同时落到 SQLite 和 CSV，避免两边数据各自漂移

本次新增行为：

- 服务启动后，名单仍会先做一次初始化同步
- 运行期间如果检测到 `data/member_roster.csv` 文件发生变化，`/api/admin/roster-members`、`/api/admin/users`、`/api/admin/users/{user_id}`、注册与登录流程都会先尝试按文件变更自动热同步
- `POST /api/admin/users/{user_id}/status` 现在不再只改数据库，也会把对应名单状态同步回 CSV，避免后续文件热同步把状态又冲回旧值

本次新增接口如下：

#### 15.18.1 强制同步名单文件

`POST /api/admin/roster-members/sync`

用途：

- 让 Windows 管理端主动触发一次 CSV -> SQLite 的强制同步
- 适合你明确知道树莓派本地 CSV 已经被修改，希望立刻刷新后台数据时调用

请求体：

- 无

成功返回示例：

```json
{
  "ok": true,
  "data": {
    "synced": true,
    "roster_path": "data/member_roster.csv",
    "total_rows": 12,
    "created_count": 2,
    "updated_count": 10
  }
}
```

#### 15.18.2 新增成员名单

`POST /api/admin/roster-members`

请求体：

```json
{
  "name": "张三",
  "code": "S2026001",
  "role": "member",
  "status": "active",
  "initial_password": "Init123456"
}
```

字段说明：

- `name`：姓名，必填
- `code`：学号或工号，必填，系统会自动去空白并转大写
- `role`：角色，空值会回退为 `member`
- `status`：只允许 `active` 或 `disabled`
- `initial_password`：初始密码，必填，至少 6 位

成功返回示例：

```json
{
  "ok": true,
  "data": {
    "action": "created",
    "member": {
      "id": 8,
      "name": "张三",
      "code": "S2026001",
      "role": "member",
      "status": "active",
      "created_at": "2026-04-23 16:20:10",
      "updated_at": "2026-04-23 16:20:10",
      "registered": false
    }
  }
}
```

写入规则：

- 同时写入 `data/member_roster.csv`
- 同时写入 `roster_members`
- 如果编号已存在，会返回 `400`

#### 15.18.3 修改成员名单

`PUT /api/admin/roster-members/{roster_member_id}`

请求体：

```json
{
  "name": "张三",
  "code": "S2026001",
  "role": "teacher",
  "status": "disabled",
  "initial_password": "Init123456"
}
```

说明：

- `initial_password` 可选
- 如果该成员当前在 CSV 里还能找到原始行，不传 `initial_password` 时会自动沿用原来的初始密码
- 如果该成员当前在 CSV 里没有对应行，而你又要修复并写回 CSV，则需要显式补传 `initial_password`

当前限制：

- 暂不支持直接修改 `code`
- 如果确实录错编号，建议新建正确成员后，再人工处理旧编号数据

成功返回示例：

```json
{
  "ok": true,
  "data": {
    "action": "updated",
    "member": {
      "id": 8,
      "name": "张三",
      "code": "S2026001",
      "role": "teacher",
      "status": "disabled",
      "created_at": "2026-04-23 16:20:10",
      "updated_at": "2026-04-23 16:31:45",
      "registered": false
    }
  }
}
```

#### 15.18.4 Windows 管理端建议接法

如果 Windows 管理端要把“成员名单管理”这块补齐，建议至少接下面 4 个动作：

- 首屏查询：`GET /api/admin/roster-members`
- 手工强制刷新：`POST /api/admin/roster-members/sync`
- 新增成员：`POST /api/admin/roster-members`
- 编辑成员：`PUT /api/admin/roster-members/{roster_member_id}`

这样即使管理员还在手工编辑树莓派本地 CSV，Windows 端也能通过查询或强制同步看到最新结果；如果后面改成完全走 API 维护名单，也不需要再重启树莓派服务。

#### 15.19 2026-04-26 人脸档案审核流补充

从 `2026-04-26` 这次版本开始，用户门户上传的人脸照片不再默认直接生效，而是进入“待审核”状态。

当前约定如下：

- 新上传的人脸档案默认是 `pending`
- 管理员审核通过后状态变成 `approved`
- 管理员审核不通过后状态变成 `rejected`
- 树莓派终端的人脸识别只会加载 `approved` 的档案
- 历史版本已经存在的人脸档案，在数据库升级时会自动回填为 `approved`，避免现场识别突然全部失效

`review_status` 目前只允许这 3 个值：

- `pending`
- `approved`
- `rejected`

Windows 管理端至少应补齐这 3 个操作：

1. 拉取待审核照片列表
2. 查看单张照片和审核备注
3. 提交“通过 / 不通过”审核结果

##### 15.19.1 获取人脸档案列表时按审核状态过滤

`GET /api/admin/face-profiles`

新增查询参数：

- `review_status`

示例：

```http
GET /api/admin/face-profiles?review_status=pending&limit=50 HTTP/1.1
Authorization: Bearer your-admin-token
```

返回项现在新增这些字段：

- `review_status`
- `review_comment`
- `reviewed_at`
- `reviewed_by`
- `recognition_enabled`

示例返回：

```json
{
  "ok": true,
  "items": [
    {
      "id": 12,
      "user_id": 5,
      "name": "张三",
      "code": "S2026001",
      "image_path": "data/faces/S2026001/20260426112000-a1b2c3d4.jpeg",
      "review_status": "pending",
      "review_comment": null,
      "reviewed_at": null,
      "reviewed_by": null,
      "recognition_enabled": false,
      "created_at": "2026-04-26 11:20:00",
      "image_url": "/api/admin/face-profiles/12/image"
    }
  ],
  "total": 1
}
```

说明：

- `recognition_enabled=true` 只会出现在 `approved`
- Windows 管理端最常用的第一页通常就是 `review_status=pending`

##### 15.19.2 获取单条人脸档案详情

`GET /api/admin/face-profiles/{face_profile_id}`

用途：

- 审核弹窗或详情页显示完整状态
- 拉取审核备注、审核人、审核时间

示例返回：

```json
{
  "ok": true,
  "data": {
    "id": 12,
    "user_id": 5,
    "name": "张三",
    "code": "S2026001",
    "image_path": "data/faces/S2026001/20260426112000-a1b2c3d4.jpeg",
    "review_status": "pending",
    "review_comment": null,
    "reviewed_at": null,
    "reviewed_by": null,
    "recognition_enabled": false,
    "created_at": "2026-04-26 11:20:00",
    "image_url": "/api/admin/face-profiles/12/image"
  }
}
```

##### 15.19.3 审核人脸档案

`POST /api/admin/face-profiles/{face_profile_id}/review`

请求体：

```json
{
  "review_status": "approved",
  "review_comment": "正脸清晰，可用于考勤识别。",
  "reviewed_by": "windows-admin-01"
}
```

字段说明：

- `review_status` 必填，只允许 `pending`、`approved`、`rejected`
- `review_comment` 可选，建议 Windows 管理端在驳回时强制填写
- `reviewed_by` 可选，建议写入当前管理员账号、设备名或操作人标识

如果要驳回，示例：

```json
{
  "review_status": "rejected",
  "review_comment": "照片侧脸角度过大，请重新采集正脸。",
  "reviewed_by": "windows-admin-01"
}
```

成功返回示例：

```json
{
  "ok": true,
  "data": {
    "id": 12,
    "user_id": 5,
    "name": "张三",
    "code": "S2026001",
    "image_path": "data/faces/S2026001/20260426112000-a1b2c3d4.jpeg",
    "review_status": "approved",
    "review_comment": "正脸清晰，可用于考勤识别。",
    "reviewed_at": "2026-04-26 11:30:42",
    "reviewed_by": "windows-admin-01",
    "recognition_enabled": true,
    "created_at": "2026-04-26 11:20:00",
    "image_url": "/api/admin/face-profiles/12/image"
  }
}
```

说明：

- 审核通过后，树莓派终端只会在下一轮人脸库热重载后开始使用该照片
- 当前终端识别人脸库默认每 `60` 秒自动热重载一次，因此通常不需要手工重启服务
- 如果审核结果改回 `pending`，系统会清空审核时间、审核人和审核备注

##### 15.19.4 Windows 管理端页面建议

建议 Windows 管理端至少提供以下字段和动作：

- 列表字段：姓名、学号/工号、上传时间、审核状态
- 详情字段：照片、审核备注、审核时间、审核人
- 操作按钮：通过、驳回、查看原图
- 过滤器：全部 / 待审核 / 已通过 / 已驳回

这样用户门户、树莓派终端和 Windows 管理端的语义会保持一致：

- 用户上传后看到“待管理员审核”
- 管理员审核通过后，照片才参与终端识别
- 管理员驳回后，用户可以在冷却期结束后重新上传

#### 15.20 2026-04-26 驳回原因与数据精简补充

这次继续补了两类规则：

1. 驳回原因改成结构化可选项
2. 人脸照片不再长期堆积，只保留当前一份

##### 15.20.1 管理员驳回原因可选项

当前系统内置的驳回原因编码如下：

- `cartoon_avatar`：卡通头像或虚拟形象
- `screen_photo`：翻拍屏幕或电子设备照片
- `printed_photo`：纸质照片或非真人现场
- `face_not_clear`：人脸不清晰
- `bad_lighting`：光线过强或过暗
- `pose_invalid`：不是正脸或角度过大
- `occluded_face`：口罩、帽子或遮挡过多
- `multiple_faces`：画面中存在多人
- `info_mismatch`：身份信息与照片不符
- `other`：其他原因

Windows 管理端可以直接调用：

`GET /api/admin/face-profiles/rejection-reasons`

示例返回：

```json
{
  "ok": true,
  "items": [
    { "code": "cartoon_avatar", "label": "卡通头像或虚拟形象" },
    { "code": "screen_photo", "label": "翻拍屏幕或电子设备照片" }
  ],
  "total": 10
}
```

建议 Windows 管理端把这组数据渲染成多选项，再额外提供一个“补充备注”文本框。

##### 15.20.2 审核接口新增驳回原因字段

`POST /api/admin/face-profiles/{face_profile_id}/review`

现在支持新增字段：

- `review_reason_codes`

驳回示例：

```json
{
  "review_status": "rejected",
  "review_reason_codes": ["cartoon_avatar", "screen_photo"],
  "review_comment": "检测到头像样式异常，并且像是翻拍电子屏幕。",
  "reviewed_by": "windows-admin-01"
}
```

返回中会新增：

- `review_reason_codes`
- `review_reason_labels`
- `recent_rejections`

说明：

- 当 `review_status = rejected` 时，建议至少选择一个固定原因
- 当前后端规则是：驳回时至少要提供一种固定原因或补充备注

##### 15.20.3 最近三次驳回历史

为了让用户和管理员都能追踪最近几次失败原因，系统现在额外保留轻量驳回历史。

当前策略：

- 只保留最近 `3` 次驳回记录
- 超过 `3` 次时，自动删除更早的驳回历史
- 驳回历史只保存原因、备注、审核人、时间
- 不保存旧照片文件

相关返回位置：

- `GET /api/admin/users/{user_id}` 返回 `recent_face_rejections`
- `GET /api/admin/face-profiles/{face_profile_id}` 返回 `recent_rejections`
- `POST /api/admin/face-profiles/{face_profile_id}/review` 审核后返回 `recent_rejections`

另外，用户汇总返回里现在建议这样理解：

- `face_profile_ready`：用户是否已经上传过照片
- `face_profile_recognition_ready`：是否已经有审核通过、可参与终端识别的照片

##### 15.20.4 当前照片保留策略

为了避免树莓派本地长期堆积多份历史照片，用户每次重新上传成功后：

- 系统会先删除该账号之前的人脸照片文件
- 同时删除旧的 `face_profiles` 记录
- 然后只保留当前最新上传的这一份照片

也就是说：

- 当前系统只保留“当前照片”这一份
- 历史驳回原因保留最近三次
- 历史旧照片不保留

这套策略更适合树莓派这种小体量部署环境。

#### 15.21 2026-04-26 Windows 管理端增量对接说明

这一节只说明两件事：

1. 这轮树莓派侧到底改了哪些对 Windows 可见的接口和字段
2. Windows 管理端为了接住这些增量，需要补哪些代码

不要把这一节和普通故障排查混在一起看。

##### 15.21.1 这轮没有改动的老接口

下面这 4 个管理员设备接口，路由地址和调用方式都没有改：

- `GET /api/admin/device/info`
- `GET /api/admin/device/health`
- `GET /api/admin/device/metrics`
- `POST /api/admin/device/reload-config`

也就是说，这轮新增的“人脸审核”“驳回原因”“活体检测”并没有改掉 Windows 原来已经在用的设备管理接口。

2026-04-26 已按当前运行时配置实测通过：

- 树莓派地址：`http://100.74.44.24:5000`
- 管理员 token：`chenhao`

实测结果：

- `GET /api/admin/device/info` 返回 `200`
- `POST /api/admin/device/reload-config` 返回 `200`
- `GET /api/admin/face-profiles/rejection-reasons` 返回 `200`

所以如果 Windows 端现在连“设备信息”或“重新加载配置”都失败，优先不要怀疑是这轮新增字段把老接口改坏了。

##### 15.21.2 这轮新增或增强的 Windows 可见接口

本轮真正新增或增强的，是“人脸审核链路”这一组接口。

###### 新增 1：驳回原因字典

`GET /api/admin/face-profiles/rejection-reasons`

用途：

- 给 Windows 审核页加载固定驳回原因选项
- 让管理员不用手写自由文本

返回结构：

```json
{
  "ok": true,
  "items": [
    { "code": "cartoon_avatar", "label": "卡通头像或虚拟形象" }
  ],
  "total": 10
}
```

###### 新增 2：人脸档案详情

`GET /api/admin/face-profiles/{face_profile_id}`

用途：

- 查看单个人脸档案当前审核状态
- 查看审核备注、驳回原因和最近驳回历史

###### 增强 3：人脸档案列表支持审核状态过滤

`GET /api/admin/face-profiles?review_status=pending`

允许值：

- `pending`
- `approved`
- `rejected`

如果 Windows 端要做“待审核”“已通过”“已驳回”分页或标签过滤，就要用这个参数。

###### 增强 4：审核提交接口支持结构化驳回原因

`POST /api/admin/face-profiles/{face_profile_id}/review`

新增支持的提交字段：

- `review_status`
- `review_reason_codes`
- `review_comment`
- `reviewed_by`

典型提交示例：

```json
{
  "review_status": "rejected",
  "review_reason_codes": ["cartoon_avatar", "screen_photo"],
  "review_comment": "请上传本人正脸原始照片。",
  "reviewed_by": "admin01"
}
```

##### 15.21.3 这轮新增的返回字段

Windows 管理端如果当前是强类型 DTO、ViewModel 或前端显式字段绑定，就要把下面这些字段补进去。

###### 用户详情新增字段

- `approved_face_profiles_count`
- `pending_face_profiles_count`
- `rejected_face_profiles_count`
- `face_profile_ready`
- `face_profile_recognition_ready`
- `recent_face_rejections`

说明：

- `face_profile_ready` 表示用户是否已有可展示的人脸资料状态
- `face_profile_recognition_ready` 表示是否已有“审核通过、能进入终端正式识别名单”的照片
- `recent_face_rejections` 是用户最近三次驳回记录

###### 人脸档案新增字段

- `review_status`
- `review_reason_codes`
- `review_reason_labels`
- `review_comment`
- `reviewed_at`
- `reviewed_by`
- `recognition_enabled`
- `recent_rejections`

说明：

- `review_status` 取值为 `pending / approved / rejected`
- `review_reason_codes` 是稳定编码，适合程序处理
- `review_reason_labels` 是中文标签，适合直接显示
- `recognition_enabled` 当前等价于 `review_status == "approved"`
- `recent_rejections` 是当前用户最近三次驳回记录，方便详情页直接展示

##### 15.21.4 Windows 管理端需要补的功能

如果 Windows 端要完整接住这轮增量，至少要补下面这些点。

###### 1. 审核页加载固定驳回原因

打开审核页时，请先请求：

- `GET /api/admin/face-profiles/rejection-reasons`

把返回的 `items` 渲染成可多选的固定原因列表。

###### 2. 驳回提交改成结构化数据

驳回时不要只提交一段纯文本备注，至少应提交：

- `review_status`
- `review_reason_codes`

可选再补：

- `review_comment`
- `reviewed_by`

###### 3. 人脸列表和详情页展示审核状态

Windows 端至少应该显示：

- 审核状态
- 驳回原因
- 审核备注
- 审核时间
- 审核人
- 最近三次驳回记录

###### 4. 用户详情页增加“识别是否就绪”

请使用：

- `face_profile_recognition_ready`

不要再简单地把“上传过照片”直接等同于“已经能参加正式识别”。

因为这轮之后，只有审核通过的照片才进入正式识别名单。

##### 15.21.5 活体检测这轮没有新增 Windows 专用接口

这次树莓派终端接入的是第一版“考勤前被动活体检测”。

这部分改动只影响树莓派终端本地识别流程，目前没有新增下面这类接口：

- 活体分数查询接口
- 活体失败历史接口
- 活体策略远程配置接口

所以：

- Windows 端现在不需要因为活体检测第一版去改设备接口地址
- 也不需要因为活体检测第一版去改 `reload-config` 的调用方式

这轮对 Windows 端真正有影响的，还是上面的人脸审核接口和字段。

##### 15.21.6 如果 Windows 端现在报 502，要先怎么判断

如果 Windows 本地日志里看到：

```text
POST /device/reload-config HTTP/1.1" 303 See Other
GET /?error=树莓派接口调用失败，HTTP 502
```

这更像是：

- Windows 本地页面路由先收到了 `/device/reload-config`
- Windows 服务端再去请求树莓派 `/api/admin/device/reload-config`
- 上游失败后，Windows 服务端把错误包装成了自己的 `502`

由于 2026-04-26 已经用当前配置实测过树莓派老接口返回 `200`，所以这类 `502` 更应该优先排查 Windows 端自己的：

- 基础地址拼接
- `Authorization: Bearer chenhao`
- 本地代理或超时
- 上游错误包装逻辑

##### 15.21.7 最小对接清单

给 Windows 端同学的最小结论就是：

1. 老设备接口没改，不需要为了这轮审核和活体改老路由
2. 新增的是人脸审核接口和审核状态字段
3. Windows 端要补固定驳回原因、多选驳回提交、审核状态展示、识别就绪展示
4. 如果当前连 `device/info` 或 `reload-config` 都失败，先查 Windows 端请求链路，不要先怀疑这轮新增字段

优先先确认：

1. Windows 管理端保存的 Bearer Token 是否和树莓派当前 `env.json` 完全一致
2. Windows 管理端请求的端口是否仍然是 `5000`
3. Windows 管理端拼接的路径是否带了 `/api/admin/`

#### 15.22 2026-05-02 考勤快照保留策略增量

这一节记录 2026-05-02 新增的快照保留策略。前面的历史接口说明保持原口径，不再回填修改。

##### 15.22.1 树莓派侧做了什么

新增配置项：

- `attendance_snapshot_retention_days`

当前值：

- `7`

行为：

- 签到成功时仍会保存现场快照
- 系统只保留最近 7 天的快照图片
- 清理目标是 `data/snapshots/YYYYMMDD/` 下超过保留期的日期目录
- 只删除本地图片文件，不删除 `attendance_records`
- 历史考勤流水、统计、筛选仍然保留
- 清理最多一天触发一次，放在签到成功后执行，不参与实时识别循环

##### 15.22.2 Windows 可见 API 增量

`GET /api/admin/attendance` 的单条记录新增字段：

- `snapshot_available`

同时 `snapshot_url` 的含义调整为：

- 快照文件存在时，返回 `/api/admin/attendance/{attendance_id}/snapshot`
- 快照不存在或已过期清理时，返回 `null`

示例：

```json
{
  "id": 11,
  "user_id": 2,
  "name": "张三",
  "code": "S2026001",
  "check_type": "check_in",
  "check_time": "2026-05-02 08:01:25",
  "snapshot_path": "data/snapshots/20260502/xxx.jpg",
  "snapshot_available": true,
  "snapshot_url": "/api/admin/attendance/11/snapshot",
  "confidence": 0.91
}
```

快照过期后的示例：

```json
{
  "id": 3,
  "user_id": 2,
  "name": "张三",
  "code": "S2026001",
  "check_type": "check_in",
  "check_time": "2026-04-20 08:01:25",
  "snapshot_path": "data/snapshots/20260420/xxx.jpg",
  "snapshot_available": false,
  "snapshot_url": null,
  "confidence": 0.91
}
```

##### 15.22.3 Windows 管理端需要怎么改

考勤列表和详情页不要只用 `snapshot_path` 判断是否可以查看快照。

请改成：

- `snapshot_available = true`：显示或启用“查看快照”
- `snapshot_available = false`：隐藏或禁用“查看快照”

如果 Windows 端仍然请求已经过期的快照接口：

- `GET /api/admin/attendance/{attendance_id}/snapshot`

树莓派会返回 `404`。这不是接口故障，而是快照已经按 7 天保留策略清理。

#### 15.23 2026-05-02 考勤端随机转头活体挑战增量

这一节记录 2026-05-02 新增的考勤端主动活体挑战。前面的历史接口说明保持原口径，不再回填修改。

##### 15.23.1 树莓派侧做了什么

考勤端现在新增随机转头挑战，用来增强对照片和预录视频攻击的区分能力。

当前流程：

1. 检测单人脸
2. 执行 `anti-spoof-mn3` 被动活体风险判断
3. 完成人脸识别，确认当前用户身份
4. 判断考勤时间、冷却、重复签到等业务规则
5. 高置信度正常签到直接写入考勤
6. 只有活体灰区、连续低分或识别距离接近阈值时，才随机要求用户轻微向左或向右转头
7. 检测到指定方向后，要求用户回到正脸
8. 身份仍然一致且动作完成后，才写入考勤

这不是每次都让用户转头，而是把单帧模型分数、身份识别和随机动作过程组合成“风险触发”的二次确认。

##### 15.23.2 新增配置项

- `attendance_liveness_challenge_enabled`
- `attendance_liveness_challenge_mode`
- `attendance_liveness_challenge_ttl_seconds`
- `attendance_liveness_challenge_pass_seconds`
- `attendance_liveness_challenge_front_yaw_max`
- `attendance_liveness_challenge_side_yaw_min`
- `attendance_liveness_challenge_side_yaw_max`
- `attendance_liveness_challenge_distance_ratio`

当前树莓派测试值：

- `attendance_liveness_challenge_enabled = true`
- `attendance_liveness_challenge_mode = risk`
- `attendance_liveness_challenge_ttl_seconds = 8`
- `attendance_liveness_challenge_pass_seconds = 3`
- `attendance_liveness_challenge_front_yaw_max = 0.18`
- `attendance_liveness_challenge_side_yaw_min = 0.12`
- `attendance_liveness_challenge_side_yaw_max = 0.60`
- `attendance_liveness_challenge_distance_ratio = 0.85`

`attendance_liveness_challenge_mode` 当前支持：

- `always`：每次写入考勤前都要求随机转头挑战
- `risk`：只在活体灰区、连续低分或人脸距离接近阈值时要求挑战
- `off / disabled / false / none`：关闭主动挑战

当前为了兼顾门禁式体验和安全性，默认使用 `risk`。

##### 15.23.3 Windows 管理端需要怎么改

这次没有新增 Windows 专用接口，也没有改变现有管理员接口路径。

Windows 管理端暂时不需要为了这次随机转头挑战改接口调用。

如果后续要在 Windows 管理端查看某次签到的活体挑战详情，再新增考勤活体审计字段，例如：

- 挑战方向
- 是否挑战通过
- 活体分数
- 挑战耗时
- 失败原因

#### 15.24 2026-05-02 活体检测产品约束：只做被动检测

这一节记录新的产品边界：考勤现场不能要求用户转头、眨眼、读数字或做其他配合动作。

因此树莓派当前默认配置已经关闭主动挑战：

- `attendance_liveness_challenge_enabled = false`
- `attendance_liveness_challenge_mode = off`

后续活体检测只从树莓派摄像头拍到的画面里做被动判断。

##### 15.24.1 Windows 管理端影响

这次没有新增 Windows 专用接口，也没有改变现有接口路径。

Windows 端暂时只需要知道：

- 树莓派不会在正常考勤流程里要求用户做动作
- 活体判断结果仍然发生在树莓派本地
- 如果后续新增活体风险日志或审计字段，会继续追加到本文档最后

#### 15.25 2026-05-02 低负载被动活体融合第一版

这一节记录在“不要求用户做动作”的产品约束下，树莓派侧新增的被动活体融合实现。

##### 15.25.1 树莓派侧做了什么

考勤端现在不再只看单帧 `anti-spoof-mn3` 结果，而是维护短时间滑动窗口。

当前窗口配置：

- `attendance_liveness_window_seconds = 2.0`
- `attendance_liveness_window_min_samples = 3`

融合信号：

- 多帧 `real_score`
- 多帧低分次数
- 灰区次数
- 人脸裁剪图的屏幕重放风险

屏幕重放风险第一版只用轻量图像特征：

- 高亮低饱和反光比例
- Canny 边缘密度
- 灰度频域高频能量比例

这些计算只发生在树莓派本地低频识别线程里，不进入视频推流线程。

##### 15.25.2 新增配置项

- `attendance_liveness_window_seconds`
- `attendance_liveness_window_min_samples`
- `attendance_liveness_window_real_threshold`
- `attendance_liveness_window_replay_risk_threshold`
- `attendance_liveness_window_uncertain_real_threshold`
- `attendance_liveness_window_uncertain_replay_risk_threshold`

当前测试值：

- `attendance_liveness_window_seconds = 2.0`
- `attendance_liveness_window_min_samples = 3`
- `attendance_liveness_window_real_threshold = 0.45`
- `attendance_liveness_window_replay_risk_threshold = 0.72`
- `attendance_liveness_window_uncertain_real_threshold = 0.35`
- `attendance_liveness_window_uncertain_replay_risk_threshold = 0.55`

##### 15.25.3 Windows 管理端需要怎么改

这次没有新增 Windows 专用接口，也没有改变现有接口路径。

Windows 管理端暂时不需要修改请求代码。

如果后续要在 Windows 端展示某次签到的活体审计结果，可以再新增字段，例如：

- 多帧平均 `real_score`
- 屏幕重放风险分
- 是否连续低分
- 最终活体判定原因

#### 15.26 2026-05-03 人脸识别后端升级说明

这一节记录 2026-05-03 新增的人脸识别后端升级。

##### 15.26.1 树莓派侧做了什么

终端识别新增 OpenCV 官方链路：

`YuNet 人脸检测 -> SFace 对齐与特征提取 -> 余弦相似度匹配`

新增配置项：

- `recognition_model`
- `face_yunet_model_path`
- `face_sface_model_path`
- `face_yunet_score_threshold`
- `face_yunet_nms_threshold`
- `face_yunet_top_k`
- `face_sface_cosine_threshold`

当前默认：

- `recognition_model = auto`

行为：

- YuNet/SFace 模型文件存在时，树莓派优先使用 `opencv_sface`
- 模型文件不存在时，自动回退到原来的 `face_recognition/dlib`
- 这个改动不改变 Windows 管理端接口路径

##### 15.26.2 Windows 管理端需要怎么改

这次没有新增 Windows 专用接口，也没有改变现有接口返回结构。

Windows 管理端暂时不需要修改请求代码。

如果后续要展示树莓派当前实际使用的识别后端，可以再扩展设备信息接口，增加类似字段：

- `recognition_backend`
- `recognition_backend_available`
- `recognition_backend_error`
