从现在开始你遵守这些规则：
1. 你是资深高级工程师，注意开闭原则，高内聚低耦合
2. 代码风格简洁优美，复用性高，注意开闭原则等6大法则，注意设计模式。
3. 严格执行命令本身，不要延伸需求。
4. 做防御性编程，考虑到边缘情况（Edge Cases），并加入必要的错误处理逻辑
5. 所有新增内容同步写入 README.md。
6. 编写代码都要在代码的本身那个文件加上注释，比如一个方法，那么就给这个方法加上详细注释，可能比较难理解加上注释等等

to do:
1.做人脸注册流
新增用户
采集/上传人脸图片
提取人脸编码
保存到 users 和 face_profiles

2.再做人脸身份识别
从数据库读取已注册编码
拿实时画面中的人脸编码去比对
识别出姓名 / 未知用户
在 / 页面显示识别结果
# face3

基于树莓派的人脸识别考勤项目。

本项目当前定位是一个可持续迭代的完整工程骨架，目标不是只做一次性演示，而是逐步形成一套包含前端界面、后端接口、SQLite 数据层、摄像头采集、人脸注册、实时识别、考勤记录、后台管理的完整系统。

## 文档维护约定

从现在开始，本项目后续所有新增模块、页面、流程、约定、运行方式、目录变化，都统一归纳到本 `README.md` 中维护。

这份文档承担以下职责：

- 项目总体说明
- 当前实现进度说明
- 技术方案说明
- 目录结构说明
- 数据库结构说明
- 前端页面说明
- 后续开发任务流说明
- 运行方式说明

后续每完成一个阶段，都应同步更新本文件。

## 一、项目目标

本项目用于实现一个部署在树莓派设备上的人脸识别考勤系统。

核心使用场景如下：

- 树莓派连接摄像头，作为考勤终端
- 用户站在设备前方，系统自动识别人脸并完成签到
- 管理员可以通过后台查看用户信息、考勤记录、终端状态和异常信息
- 系统可以在局域网或单机环境中运行

本项目最终要解决的问题不是单纯“识别人脸”，而是完整地打通下面这条链路：

`用户注册 -> 人脸录入 -> 特征保存 -> 实时识别 -> 自动签到 -> 后台查看记录`

## 二、当前技术栈

当前技术路线已经确定为：

- 前端：Bootstrap
- 后端：FastAPI
- 数据库：SQLite
- 摄像头采集：OpenCV
- 人脸识别：`face_recognition`
- 部署设备：树莓派
- 模板渲染：Jinja2--它的核心作用是**“换汤不换药”**：定义网站通用的结构（头部、脚本、样式），而把具体变化的内容留给子页面去填充。

### 为什么当前选择 `face_recognition`

当前项目是考勤场景，重点是“注册人脸并进行身份比对”，因此第一阶段优先选择 `face_recognition`，原因如下：

- 更贴合“人脸编码 -> 人脸比对 -> 身份识别”的流程
- 对考勤项目来说，上手成本更低
- 适合先完成第一版完整闭环
- 后续如果需要更高效的人脸检测能力，可以再考虑引入 MediaPipe 做辅助检测

当前决策是：

- 第一版先用 `face_recognition` 跑通完整业务
- 后续再根据树莓派性能情况决定是否引入更轻量的检测前置方案

## 三、当前项目整体架构思路

项目逻辑分为五层：

### 1. 配置层

负责管理整个项目的运行参数，比如：

- Web 服务地址
- 摄像头编号
- 图像尺寸
- SQLite 路径
- 考勤时间段
- 人脸识别阈值

当前实现文件：

- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)
- [env.json](/home/luck/face3/env.json)

### 2. 数据层

负责：

- 建立 SQLite 连接
- 初始化表结构
- 管理事务
- 提供基础数据访问接口

当前实现文件：

- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)
- [scripts/database/__init__.py](/home/luck/face3/scripts/database/__init__.py)
- [scripts/database/demo.py](/home/luck/face3/scripts/database/demo.py)

### 3. 摄像头采集层

负责：

- 打开摄像头
- 获取视频帧
- 对图像做基础压缩与格式转换

当前实现文件：

- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

### 4. Web 页面层

负责：

- 提供待识别用户端界面
- 提供外网用户门户界面
- 通过 FastAPI + Jinja2 输出 HTML 页面

当前实现文件：

- [main.py](/home/luck/face3/main.py)
- [templates/base.html](/home/luck/face3/templates/base.html)
- [templates/user_screen.html](/home/luck/face3/templates/user_screen.html)
- [static/css/site.css](/home/luck/face3/static/css/site.css)
- [funnel_test_app.py](/home/luck/face3/scripts/web/funnel_test_app.py)
- [funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)

### 5. 识别与考勤业务层

负责：

- 人脸注册
- 特征提取
- 特征比对
- 去重签到
- 迟到判断
- 异常处理

当前实现文件：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)
- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

当前状态：

- 已经落下“严格版树莓派摄像头人脸识别模块”
- 已经接入树莓派本地摄像头线程
- 已经可以把识别成功结果写入 `attendance_records`
- 已经会在成功签到时落盘保存现场快照到 `data/snapshots/`

## 四、当前已完成内容

截至当前，项目已经完成以下内容。

### 1. 配置系统

已经实现一个基于 JSON 的配置加载类，支持：

- 默认配置
- `env.json` 覆盖默认值
- 配置热重载
- 字典式访问
- 属性式访问

当前已经覆盖的配置内容包括：

- Web 服务配置
- 摄像头配置
- 摄像头 JPEG 质量配置
- 严格识别目标帧率配置
- 人脸识别相关配置
- SQLite 相关配置
- 文件目录配置
- 考勤时间配置
- 外网用户门户会话配置
- 本地成员名单文件路径
- 设备信息配置
- 管理员 API Token 配置

### 2. SQLite 数据库基础设施

已经完成 SQLite 最小可用底座，包括：

- 自动创建数据库文件目录
- 自动建表
- 事务管理
- 连接管理
- 外键约束
- 基础 Repository 封装

已创建的数据表：

- `roster_members`
- `users`
- `face_profiles`
- `attendance_records`

### 3. 前端原型界面

当前保留了终端页和外网用户门户两类前端页面入口。

#### 待识别用户界面

路由：

- `/`
- `/video_feed`

主要内容：

- 摄像头识别舞台区
- 人脸框提示区域
- 当前识别状态提示
- 今日签到统计概览
- 识别指引
- 现场公告

设计目标：

- 让站在终端前的用户一眼知道自己该怎么站
- 让页面具备“正在识别”的实时感
- 保持界面简洁、清晰、偏终端设备风格

当前已接通：

- MJPEG 实时视频流
- 摄像头后台线程持续读帧
- 基于 `face_recognition` 的轻量级人脸框检测
- 摄像头不可用时的占位提示画面
- 前端每 10 秒探测一次后台心跳，后台中断时自动切换为离线提示文案
- 首页在线探测与视频流错误状态已经拆分，不再因为单次视频流报错就直接误判“后台失联”
- 本地 `127.0.0.1` / `localhost` 访问时只开放这组终端页入口，避免现场设备浏览器误入其他页面

#### 外网用户门户界面

路由：

- `/portal/register`
- `/portal/login`
- `/portal/home`
- `/portal/face`

主要内容：

- 首次注册页
- 正式密码登录页
- 登录后的用户中心
- 登录后的人脸资料现场拍摄页

设计目标：

- 让树莓派终端页和外网用户门户彻底分离
- 首次注册时强制校验本地名单和管理员预置初始密码
- 登录态下再做人脸上传，避免匿名公网接口直接入库
- 登录态下再做人脸现场拍摄和提交，避免匿名公网接口直接入库
- 后续容易继续扩展为密码修改、历史记录、审核结果页
- 非本地访问时，这组门户页面会成为唯一保留的前端页面入口

当前 UI 已完成一轮统一刷新：

- 终端页、登录页、注册页、用户中心页、上传页已经统一到同一套亮色轻玻璃设计语言
- 全局视觉改为更简洁、清亮、不冗余的浅色风格，弱化原先偏暖偏厚重的质感
- 交互动效统一为轻量平滑过渡，并补充 `prefers-reduced-motion` 兼容
- `scripts/web/templates/funnel_test.html` 不再维持独立深色风格，已并入统一门户样式体系
- `main.py` 与 `scripts/web/funnel_test_app.py` 的模板加载器已调整为可复用公共 `base.html`
- 用户可见的门户页路由已经补齐互通关系，`/portal/face` 可直接返回 `/portal/home`
- 页面里原先偏测试、偏说明性的长文案已压缩，只保留必要状态与操作信息
- 用户中心里的“已上传人脸档案”独立列表已移除，相关功能已合并进账号概览
- 成功上传人脸资料后会进入重新上传冷却期，当前通过 `portal_face_reupload_cooldown_seconds` 控制，测试值为 300 秒
- 登录页、注册页、用户中心页、人脸资料页已经继续收口为更接近成品页的布局，不再保留开发期眉标和大段解释性文字
- 人脸资料页会根据当前账号状态展示重新上传是否可用；冷却期内即使手工进入页面，也会看到锁定提示并禁止重新提交

### 4. 外网用户门户与名单注册流

当前已经实现一条面向单位内部成员的最小业务闭环：

- 服务启动时自动读取 `data/member_roster.csv`
- 运行期间如果检测到 `data/member_roster.csv` 被修改，也会自动热同步到 `roster_members`
- 名单导入到 `roster_members`
- 用户使用“姓名 + 学号/工号 + 初始密码”完成首次注册
- 注册成功时强制设置新密码
- 后续登录只认新密码，不再认初始密码
- 登录后才能进入外网人脸拍摄页
- `/portal/face` 直接复用 `funnel_test.html` 的动作挑战界面
- 现场拍照提交会复用现有 `RegistrationValidationPipeline`
- 校验通过后提取编码并写入 `face_profiles`
- 管理员 API 已支持直接新增和修改名单成员，并会把变更同时写回 CSV 与 SQLite

当前新增模块：

- [scripts/web/account_security.py](/home/luck/face3/scripts/web/account_security.py)
- [scripts/web/roster_import_service.py](/home/luck/face3/scripts/web/roster_import_service.py)
- [scripts/web/portal_submission_service.py](/home/luck/face3/scripts/web/portal_submission_service.py)
- [templates/portal_register.html](/home/luck/face3/templates/portal_register.html)
- [templates/portal_login.html](/home/luck/face3/templates/portal_login.html)
- [templates/portal_home.html](/home/luck/face3/templates/portal_home.html)
- [scripts/web/templates/funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)
- [data/member_roster.csv](/home/luck/face3/data/member_roster.csv)

当前门禁规则：

- 不在本地名单中的编号不能注册
- 名字与名单不匹配不能注册
- 初始密码错误不能注册
- 已完成首次注册的编号不能重复注册
- 注册时必须设置符合规则的新密码
- 未登录用户不能访问人脸上传接口
- 每个账号的人脸档案数量有上限，避免被无限写入

### 5. FastAPI 页面入口

当前 [main.py](/home/luck/face3/main.py) 已经实现：

- 启动时初始化数据库
- 启动时同步本地成员名单
- 运行时按文件变更自动热同步本地成员名单
- 挂载静态资源目录
- 提供树莓派终端页和外网用户门户页路由
- 提供基于 Session 的登录态
- 提供 `/video_feed` 摄像头流接口
- 提供 `/healthz` 前端心跳接口
- 提供 `/api/admin/*` 设备侧管理员 API
- 提供名单强制同步、名单新增、名单修改等设备侧管理员写接口
- 提供基于访问来源的入口策略：本地只保留终端页，非本地只保留门户页，历史遗留 `/admin` 页面已下线
- 已为核心页面文件补充结构注释，便于后续继续开发和阅读
- `base.html` 已改为优先使用本地静态前端资源，不再依赖 CDN
- 上传页模板现在也继承公共 `base.html`，不再维护一份完全独立的内联样式页面

### 6. Tailscale Funnel 独立测试页

为避免影响主项目运行逻辑，当前新增了一个独立测试应用：
使用方式
.venv/bin/python -m uvicorn funnel_test_app:app --host 127.0.0.1 --port 8010
- [funnel_test_app.py](/home/luck/face3/funnel_test_app.py)
- [funnel_test_app.py](/home/luck/face3/scripts/web/funnel_test_app.py)
- [funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)

用途：

- 单独启动一个公网用户资料提交 Web 服务
- 不依赖主项目摄像头线程
- 不依赖 SQLite
- 先把“公网入口 + 用户资料采集 + 照片提交”这条链路跑通

当前已支持：

- 浏览器申请摄像头权限并现场采集
- 前端照片预览
- 姓名、学号/工号、电话、备注信息填写
- 授权勾选校验
- 后端图片类型校验
- 后端图片大小限制
- 低流量分步动作挑战
- 动作步骤进度展示
- 采集区单屏紧凑操作布局
- 同人一致性校验
- 可信注册照自动挑选
- 摄像头实时预览镜像校正
- 纸张/屏幕翻拍检测
- 后端注册质量校验流水线
- 单人脸数量检测
- 人脸区域尺寸检测
- 模糊度检测
- 亮度检测
- 姿态检测
- 五官关键点完整性检测
- 后端本地落盘保存
- 每次提交生成独立登记编号

当前保存目录：

- `data/funnel_registrations/<submission_id>/face.xxx`
- `data/funnel_registrations/<submission_id>/metadata.json`

当前质量校验实现文件：

- [registration_validation.py](/home/luck/face3/scripts/web/registration_validation.py)

当前设计特点：

- 使用独立 `RegistrationValidationPipeline` 编排各个校验器
- 每个校验器单独负责一种能力，符合开闭原则和高内聚低耦合
- 校验结果统一输出为 `passed / code / message / score / threshold`
- 前端会把每项校验结果逐项展示给用户

建议测试方式：

```bash
.venv/bin/uvicorn scripts.web.funnel_test_app:app --host 127.0.0.1 --port 8010
sudo tailscale funnel 8010
```

如果 Funnel 打通，手机浏览器打开对应公网地址后，应当能看到公网用户资料提交页，并可执行：

- 开启摄像头
- 开始动作挑战
- 按步骤抓拍当前动作
- 提交资料并拿到登记编号

### 7. 摄像头实时流、严格识别与自动考勤

当前 [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py) 已实现：

- 后台线程持续读取摄像头
- 根据配置设置分辨率和帧率
- 镜像和旋转处理
- 周期性重载已注册人脸库
- 每隔若干帧执行一次严格识别
- 将识别结果叠加到原始画面上
- 识别稳定成功后自动写入 `attendance_records`
- 自动保存现场抓拍图到 `data/snapshots/<日期>/`
- 编码成 JPEG 后通过 MJPEG 持续推送给前端

当前这样设计的原因是：

- 比“每个请求都临时打开一次摄像头”更流畅
- 更适合树莓派持续运行
- `detect_every_n_frames` 可以降低 CPU 压力
- 即使摄像头失败，页面也不会直接崩，而是显示占位提示
- 已注册人脸库定时热重载，避免新增用户后必须重启整个服务
- 识别成功后走冷却时间，避免同一个人站在镜头前被重复签到
- 采集线程与识别线程已解耦，严格识别不会再直接拖垮 MJPEG 画面刷新率

### 8. 严格版树莓派摄像头人脸识别模块

当前新增模块：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)

这个模块的定位不是“简单框出一张脸”，而是给树莓派终端提供一套可以真正用于考勤的严格识别引擎。

#### 模块做了什么

它主要完成下面 10 件事：

1. 从 SQLite 读取所有可识别的人脸档案
2. 只加载“已经正式注册且状态正常”的用户
3. 对每一帧图像做人脸检测
4. 拒绝无人脸和多人脸场景
5. 拒绝脸太小、太模糊、太暗、太亮、姿态不正的帧
6. 对合格单人脸提取编码
7. 和本地已注册编码库做距离比对
8. 拒绝距离过大或结果歧义过高的识别结果
9. 要求同一身份连续多帧稳定命中
10. 稳定成功后再进入考勤写入资格

#### 它为什么叫“严格识别”

因为它不是“只要像就认”，而是把识别拆成多道门禁：

- 单人门禁
- 图像质量门禁
- 姿态门禁
- 身份距离门禁
- 多帧稳定门禁
- 考勤冷却门禁
- 考勤时间窗门禁

只有全部满足，才会返回 `attendance_ready`。

#### 模块内部核心数据结构

1. `KnownFaceProfile`

作用：

- 表示一条已注册人脸档案
- 包含 `face_profile_id / user_id / code / name / image_path / encoding`

2. `PoseSummary`

作用：

- 保存当前帧的人脸姿态摘要
- 包含：
  - `roll_angle`
  - `yaw_offset`
  - `signed_yaw`
  - `pitch_ratio`

3. `RecognitionResult`

作用：

- 表示“当前这一帧”严格识别的完整结果
- 既可以给摄像头线程使用，也可以给调试日志、状态面板和后续前端状态接口使用

它包含的信息有：

- 是否成功
- 失败原因
- 当前画面里有几张脸
- 是否已经识别出身份
- 是否已经满足写考勤条件
- 当前识别到的用户 ID / 姓名 / 编号
- 匹配距离与置信度
- 当前稳定帧数
- 冷却剩余时间
- 是否处于考勤时间段内
- 人脸面积、清晰度、亮度、姿态等中间指标

#### 模块内部主流程

`process_frame(frame_bgr)` 的处理顺序如下：

1. 输入校验

- 空帧直接拒绝
- 没有已注册人脸库直接拒绝

2. 图像预处理

- 根据配置做镜像校正
- 根据配置做旋转校正

3. 人脸检测

- 用缩放后的图像做人脸检测，降低树莓派计算压力
- 没有人脸则返回 `no_face`
- 超过一张脸则返回 `multi_face`

4. 人脸尺寸门禁

- 计算人脸区域在整张图中的占比
- 太小直接返回 `face_too_small`

5. 图像质量门禁

- 对脸部 ROI 做 Laplacian 方差
- 太模糊返回 `image_blurry`

6. 亮度门禁

- 对脸部 ROI 做灰度均值统计
- 过暗或过亮返回 `bad_lighting`

7. 姿态门禁

- 提取人脸 landmarks
- 计算 `roll / yaw / pitch`
- 歪头过大返回 `roll_too_large`
- 侧脸过大返回 `yaw_too_large`
- 抬头低头异常返回 `pitch_bad`

8. 人脸编码提取

- 对当前合格人脸提取 128 维编码
- 提取失败返回 `face_encoding_failed`

9. 身份匹配

- 用当前编码和本地 `known_encodings` 做距离计算
- 最小距离超过阈值则返回 `unknown`
- 如果第一名和第二名太接近，则返回 `ambiguous_match`

10. 多帧稳定确认

- 不是“一帧命中就签到”
- 必须连续多帧识别到同一身份
- 如果还没达到稳定帧数，返回 `match_not_stable_yet`

11. 考勤时间段门禁

- 如果当前时间不在考勤时间窗内
- 返回 `outside_attendance_window`

12. 冷却时间门禁

- 如果同一个人刚刚签到过
- 在冷却期内返回 `attendance_cooldown`

13. 最终放行

- 所有条件都满足时
- 返回 `attendance_ready`

#### 当前严格识别里已经实现的规则

当前已经启用的规则包括：

- 必须是单人入镜
- 人脸面积必须达到最低占比
- 人脸编码距离必须小于系统阈值
- 候选结果不能过于接近，避免误认
- 同一身份只需要最短稳定确认
- 同一身份存在签到冷却时间
- 必须在考勤时间段内才允许写记录

#### 2026-04-22 这一版对严格识别做了什么调整

为了避免“终端画面更流畅了，但识别人太难通过”的问题，这一版把识别策略从“多重质量门禁”改成了“适合考勤现场的快速匹配”。

主要变化：

- 不再把模糊、亮度、姿态等条件作为硬性拦截门槛
- 识别主链路收敛为：
  - 单人检测
  - 人脸面积校验
  - 直接提取编码
  - 与已注册人脸库做距离匹配
  - 最短稳定确认后写入考勤
- 人脸最小面积占比进一步下调，用户不必贴得很近
- 编码距离阈值放宽到 `0.52`
- 稳定确认次数下调到 `1`
- 严格识别目标频率上调到 `5 FPS`

这次调整的目标是：

- 保留“单人入镜 + 编码比对 + 冷却时间 + 时间窗”这些真正影响正确性的约束
- 去掉那些会明显拖慢速度、却不一定提升考勤体验的重门槛
- 让系统先做到“准确识别对应的人脸”和“尽快签到”

#### 终端画面图例文档

我把树莓派终端页里所有可见元素都单独写成了一份文档，便于你后续继续改前端、调后端，或者让 Windows 端 AI 理解页面含义：

- [docs/terminal_recognition_overlay.md](/home/luck/face3/docs/terminal_recognition_overlay.md)

这份文档说明了：

- 页面外层在线/离线提示的含义
- 当前终端页只保留哪些提示
- 每一种识别状态码是什么意思
- 当前版本为什么比之前更容易识别和更容易签到
- 中文字体为什么以前会变成 `????`，现在又是怎么解决的

#### 当前模块还额外提供了什么能力

除了识别本身，它还额外提供：

1. `reload_known_faces()`

作用：

- 从数据库重新加载全部已注册编码
- 供摄像头线程定时热更新使用

2. `prepare_frame()`

作用：

- 统一做镜像和旋转处理
- 避免摄像头线程和识别逻辑各自重复处理方向

3. `annotate_frame()`

作用：

- 保留视频叠加接口
- 当前默认不再绘制常驻调试 HUD
- 便于后续如果需要恢复调试层时继续复用

4. `mark_attendance_committed()`

作用：

- 只有外层真正把考勤记录写入数据库成功后，才开始冷却计时
- 避免“识别成功但数据库写入失败”时误进入冷却状态

5. `known_faces_count()`

作用：

- 返回当前内存中已加载的人脸档案数量
- 便于调试和后台状态展示

#### 这个模块没有做什么

为了边界清晰，这个模块没有直接负责：

- 打开摄像头
- 持续读帧
- MJPEG 推流
- 写数据库考勤记录
- 保存快照文件
- 管理员后台展示

这些都交给外层去做。

这样设计的好处是：

- 模块边界清晰
- 后续接到别的摄像头源也能复用
- 可以单独测试识别逻辑，不强绑定 Web 或摄像头线程
- 符合高内聚、低耦合和开闭原则

### 9. 严格识别接入树莓派摄像头后新增的行为

当前 [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py) 在接入严格识别后，新增了这些运行行为：

1. 启动时初始化严格识别器

- 会尝试创建 `StrictFaceRecognizer`
- 会立即加载当前数据库中的已注册人脸编码

2. 定时热重载人脸库

- 默认每 60 秒重新加载一次人脸档案
- 这样用户在外网门户刚完成人脸注册后，树莓派终端不需要重启太久就能识别到新用户

3. 识别状态实时写入终端内存

- 当前帧识别结果会保存在 `self.recognition_result`
- 当前终端状态文案会保存在 `self.last_attendance_message`
- 最近一次真正写入成功的签到记录摘要会保存在 `self.last_attendance_record`

4. 自动写入考勤记录

- 一旦 `RecognitionResult.attendance_ready == True`
- 外层摄像头线程会自动执行：
  - 保存现场快照
  - 写入 `attendance_records`
  - 通知识别器开启冷却时间

5. 自动保存现场快照

- 快照保存目录：
  - `data/snapshots/<YYYYMMDD>/`
- 文件名格式：
  - `<时间戳>-<人员编号>.jpg`

6. 终端叠字信息更真实

当前终端画面已经去掉常驻调试叠字、扫描取景框和底部等待状态条。

现在只保留：

- 摄像头原始画面
- 左上角一块很小的实时进度提示
- 签到成功后的短暂成功提示
- 摄像头异常时的占位提示

7. 采集线程与识别线程解耦

这是当前树莓派终端提升帧率最关键的一次改造。

旧实现的问题：

- 摄像头线程在同一个循环里同时做：
  - 读帧
  - 严格识别
  - 叠字
  - JPEG 编码
  - MJPEG 推流
- 只要严格识别稍慢，整个视频流就会一起卡住

新实现的改法：

- 采集线程只负责尽快读取摄像头、取最新识别结果做叠加，然后持续输出画面
- 识别线程单独运行，只处理“最新的一帧”
- 识别线程不会追赶旧帧，因此不会不断积压待处理图像

这样做的结果是：

- 严格识别仍然存在
- 但严格识别不再直接阻塞视频流刷新
- 远端页面看到的 MJPEG 流畅度会明显好于“全部堆在一个线程”的实现

8. 终端页前端装饰层已大幅精简

这次把这些 UI 从终端页里移除了：

- 青色扫描取景框
- 扫描线
- 底部等待识别状态条
- 视频流内部左上角常驻调试面板

这样做的原因是：

- 这些元素会遮挡真实摄像头画面
- 对“是否签到成功”这个核心目标帮助不大
- 长时间显示会让终端页更像演示页，而不是现场设备页
- 现在的终端页逻辑是“平时尽量干净，只有成功时给反馈”

同时新增了一块左上角小进度提示：

- 通过 `/api/terminal/status` 获取轻量状态
- 默认每 10 秒刷新一次，避免终端页产生过高频率轮询日志
- 只显示很短的标签、说明和一条细进度条
- 目的是让终端前的人知道“系统是否正在识别”，但不遮挡画面主体

9. 摄像头连续读帧失败时会主动自恢复

当前摄像头线程不再在 `camera read failed` 状态里无限停留。

现在的处理方式是：

- 如果 `capture.read()` 偶发失败，会先显示占位提示
- 如果连续多次读帧失败，系统会主动释放当前摄像头句柄
- 下一轮再重新按正常流程打开摄像头

这样做的原因是：

- 树莓派摄像头在现场运行时，偶发读帧失败并不一定代表设备永久不可用
- 主动释放再重连，通常比“保持一个半失效句柄反复 read”更容易恢复
- 能降低终端长期卡在“摄像头读取失败”占位图上的概率

10. JPEG 压缩质量做成了配置项

新增配置项：

- `camera_jpeg_quality`

作用：

- 控制视频流 JPEG 质量
- 可以在“图像清晰度”和“推流带宽/编码开销”之间做平衡

11. 严格识别目标频率做成了配置项

新增配置项：

- `recognition_target_fps`

作用：

- 控制严格识别线程每秒最多处理多少帧
- 这不是视频流帧率，而是“识别线程的工作频率”
- 把识别频率和画面刷新率分开后，终端性能更容易调优

12. 摄像头叠字已支持中文字体

新增文件：

- [scripts/camera/frame_text.py](/home/luck/face3/scripts/camera/frame_text.py)

作用：

- 统一负责树莓派视频帧内的文字绘制
- 优先查找系统中文字体或项目内字体
- 使用 Pillow 而不是 `cv2.putText`
- 解决终端画面里中文变成 `????` 的问题

字体查找顺序：

1. `env.json` 中显式配置的 `camera_overlay_font_path`
2. 项目 `static/fonts/` 下的字体
3. 树莓派系统常见中文字体，例如：
   - `wqy-zenhei`
   - `wqy-microhei`
   - `Noto Sans CJK`
   - `DroidSansFallbackFull`

### 10. 树莓派摄像头识别模块当前仍然保留的降级能力

如果严格识别器初始化失败，例如：

- `face_recognition` 模块不可用
- 数据库异常
- 识别人脸库加载失败

当前摄像头线程不会直接崩掉，而是回退到原先的简单人脸框检测逻辑。

这样做的意义是：

- 终端页至少还能继续显示摄像头画面
- 不会因为识别模块异常导致整条视频流直接中断
- 便于现场排查

## 五、数据库设计说明

当前 SQLite 表结构如下。

### 1. `roster_members`

成员名单表，存储允许注册的单位内部成员。

字段：

- `id`：主键
- `name`：姓名
- `code`：唯一学号/工号
- `role`：成员角色
- `status`：状态，当前支持 `active / disabled`
- `initial_password_hash`：管理员预置初始密码的哈希
- `created_at`：创建时间
- `updated_at`：更新时间

作用：

- 作为首次注册的白名单来源
- 把“允许注册的人”和“已经正式注册的人”拆开，降低耦合
- 后续可以继续扩展为班级、课题组、部门维度的导入来源

### 2. `users`

用户主表，存储系统中已登记的身份对象。

字段：

- `id`：主键
- `roster_member_id`：关联名单成员
- `name`：姓名
- `code`：唯一编号，可用于学号、工号或人员编码
- `password_hash`：正式登录密码哈希
- `password_changed_at`：首次注册或改密时间
- `last_login_at`：最后登录时间
- `created_at`：创建时间

作用：

- 作为所有用户身份信息的主表
- 保存正式登录凭证
- 后续人脸信息、考勤信息都通过 `user_id` 进行关联

### 3. `face_profiles`

人脸特征表，存储与用户相关的人脸资料。

字段：

- `id`：主键
- `user_id`：所属用户
- `image_path`：原始图片路径
- `encoding`：人脸编码字符串
- `created_at`：创建时间

作用：

- 将用户和人脸特征对应起来
- 后续识别时从这里读取特征进行比对

### 4. `attendance_records`

考勤记录表，存储识别成功或考勤相关流水。

字段：

- `id`：主键
- `user_id`：所属用户
- `check_type`：签到类型
- `check_time`：记录时间
- `snapshot_path`：现场抓拍图路径
- `confidence`：识别置信度

作用：

- 存放实际签到流水
- 供后台页面查询和统计

时间约定：

- `created_at`、`updated_at`、`password_changed_at`、`last_login_at`、`check_time` 统一按设备当前本地时区写入
- 当前默认按树莓派本机时区使用，不再直接依赖 SQLite `CURRENT_TIMESTAMP` 的 UTC 默认值
- 这样可以避免后台看到的记录时间比实际时间少 8 小时

## 六、当前目录结构

当前项目核心目录结构如下：

```text
face3/
├── main.py
├── env.json
├── README.md
├── data/
│   ├── face3.db
│   └── member_roster.csv
├── scripts/
│   ├── camera/
│   │   └── camera.py
│   ├── config/
│   │   └── config.py
│   ├── database/
│       ├── __init__.py
│       ├── demo.py
│       └── sqlite_db.py
│   └── web/
│       ├── account_security.py
│       ├── portal_submission_service.py
│       ├── registration_validation.py
│       └── roster_import_service.py
├── static/
│   └── css/
│       └── site.css
└── templates/
    ├── admin_dashboard.html
    ├── base.html
    ├── portal_home.html
    ├── portal_login.html
    ├── portal_register.html
    └── user_screen.html
```

说明：

- `main.py`：FastAPI 入口
- `env.json`：项目运行配置
- `scripts/config/`：配置系统
- `scripts/database/`：SQLite 数据层
- `scripts/camera/`：摄像头采集层
- `templates/`：前端页面模板
- `static/`：静态资源
- `data/`：本地数据库及后续人脸图片、快照等数据目录
- `data/member_roster.csv`：管理员预置成员名单与初始密码来源

## 七、前端页面设计说明

当前项目既包含原型展示页，也已经开始接通部分真实业务页。

### 1. 待识别用户页的定位

这是面向普通使用者的终端页。

设计重点：

- 大面积展示识别区域
- 强调视觉引导
- 少操作、少干扰
- 适合全屏显示在树莓派终端上

目前页面上预留的未来扩展点包括：

- 实时摄像头画面
- 人脸框叠加
- 识别成功提示
- 签到成功动画
- 失败重试提醒
- 时间显示
- 校区/教室/终端编号显示

### 2. 管理员后台页的定位

这里描述的是管理员后台这类界面的目标形态。当前树莓派主应用已经不再暴露 `/admin` 页面，管理员统一走 Windows 侧后台，但信息结构和功能定位仍然沿用这套设计思路。

设计重点：

- 信息密度高于终端页
- 数据概览直观
- 后续容易扩展为真正的管理系统

目前页面上预留的未来扩展点包括：

- 用户管理
- 人脸录入入口
- 考勤记录筛选
- 异常记录审核
- 数据导出
- 终端在线状态监控
- 权限角色管理

### 3. 外网用户门户页的定位

这是面向单位内部普通成员的外网入口。

设计重点：

- 与树莓派终端识别页彻底分离
- 首次注册只允许名单内成员进入
- 初始密码只用于首次注册，不用于后续登录
- 登录后才能做人脸资料现场拍摄

目前页面上已接通的能力包括：

- 首次注册
- 正式密码登录
- Session 登录态
- 用户中心状态展示
- 单图人脸质量校验
- 人脸编码提取和 `face_profiles` 入库

## 八、开发任务流

当前项目建议按以下四个主任务流推进。

### 任务 1：配置与数据层

目标：

- 完成项目基础配置
- 完成 SQLite 数据层

当前状态：

- 已完成基础版本

后续细化方向：

- 增加更多配置分组
- 增加日志配置
- 增加数据库备份配置

### 任务 2：人脸注册流

目标：

- 新增用户
- 上传或拍摄人脸图片
- 提取人脸编码
- 保存到 `face_profiles`

预期产物：

- 用户注册接口
- 图片上传页面
- 人脸编码保存逻辑

当前状态：

- 已完成“名单导入 -> 首次注册改密 -> 正式登录 -> 现场拍照/备用选图 -> 单图入库”的最小闭环
- 独立 Funnel 动作挑战页仍保留，用于后续升级成更严格的公网采集入口
- 树莓派本地终端的严格识别与考勤写入已经接通

真实业务中的常见处理方式：

- 不会直接信任用户随手上传的一张照片，而是先做基础质量校验
- 要求照片中必须只有一张清晰正脸，且人脸面积不能过小
- 检查模糊、逆光、过暗、过曝、遮挡、侧脸、低头等问题
- 通常要求用户提交多张照片，而不是只交一张
- 很多系统会优先引导用户现场拍照，而不是纯相册上传
- 对高风险场景会增加活体检测，防止用户拿别人照片、截图或屏幕翻拍来冒充
- 注册成功前常常还会加入人工审核，尤其是第一次建档时
- 用户身份和照片不会只靠“用户自己填什么就信什么”，而是要绑定学号、工号、手机号、管理员审批等外部身份信息
- 生产环境会保留审核日志、提交时间、来源方式和失败原因，便于追溯

对本项目的建议治理流程：

- 先做人脸检测，没有检测到脸直接拒绝
- 检测到多张脸直接拒绝，要求重新拍
- 对人脸框大小、清晰度、亮度做最低门槛判断
- 当前公网注册入口只保留摄像头现场采集，不再提供本地文件上传
- 每个用户至少采集 3 张合格照片
- 先进入待审核状态，管理员确认后再正式写入 `face_profiles`
- 后续如果条件允许，再补活体检测或人工复核入口

当前已实现的公网注册链路：

- 页面入口只允许浏览器摄像头现场采集
- 前端先请求后端创建一次动作挑战 `challenge_id`
- 后端从离线模板中随机生成一组 3 步动作：`正脸 -> 轻微左/右侧转 -> 正脸`
- 用户每完成一步，只上传一张压缩后的抓拍图，不再持续发送视频帧
- 后端对当前抓拍图执行单人、人脸尺寸、关键点完整性、姿态规则和同人一致性校验
- 所有步骤都通过后，后端会从通过的正脸抓拍里自动挑出最清晰的一张作为最终注册照
- 正式提交时，前端不再上传最终图片，只提交 `challenge_id`
- 后端根据 `challenge_id` 读取可信注册照，再走现有 `RegistrationValidationPipeline`
- 最终注册照会额外执行纸张/屏幕翻拍检测，尽量拦截拿手机播放预录视频或纸张照片冒充的情况
- 质量校验通过后才保存到 `data/funnel_registrations/<submission_id>/`
- 质量校验失败时，该 challenge 直接作废，必须重新做一次动作挑战

当前活体调优说明：

- 第一轮实测发现“连续眨眼 + 连续送帧”在移动端浏览器下容易漏检自然眨眼，同时后端逐帧分析成本偏高
- 当前已改为“分步动作挑战”，每一步只上传一张抓拍图，显著降低网络流量和后端解码压力
- 现在的挑战步骤基于本地固定模板生成，不依赖在线模型下载
- 后端会在步骤级别做姿态校验和同人一致性校验，避免中途换人继续挑战
- 最终注册照从通过步骤的正脸抓拍里按清晰度自动挑选，减少用户额外拍照次数
- 左右转头门槛已经放宽成“轻微侧转即可通过”，减少普通摄像头下因为转头过猛或过小导致的连续失败

本次新增模块：

- `scripts/web/liveness.py`
  - `ActionChallengeSession`
  - `ActionChallengeAnalyzer`
  - `LivenessChallengeService`
  - `TrustedCapture`
- `scripts/web/funnel_test_app.py`
  - 新增 `POST /api/liveness/challenges`
  - 新增 `POST /api/liveness/challenges/{challenge_id}/captures`
  - `POST /api/submissions` 改为只接受 `challenge_id`
- `scripts/web/templates/funnel_test.html`
  - 改成纯摄像头动作挑战流程
  - 移除连续送帧活体逻辑
  - 前端新增步骤抓拍、步骤进度展示、可信注册照预览和提交门禁
- `scripts/web/registration_validation.py`
  - 新增姿态度量、清晰度评分、人脸编码提取和纸张/屏幕翻拍检测的复用函数

建议的实现架构：

- 不把所有校验逻辑硬写在一个接口函数里，而是拆成独立校验器
- 采用“采集层 -> 质量校验层 -> 活体校验层 -> 审核层 -> 入库层”的流水线结构
- 每个校验器只负责一种能力，例如：
  - `FaceCountValidator`：检查是否只有一张脸
  - `FaceSizeValidator`：检查人脸占比是否足够大
  - `BlurValidator`：检查是否模糊
  - `BrightnessValidator`：检查过暗/过曝
  - `OcclusionValidator`：检查遮挡
  - `PoseValidator`：检查是否大角度侧脸
  - `LivenessValidator`：检查活体
- 每个校验器输出统一结果结构，例如：`passed / code / message / score`
- 主流程只负责编排这些校验器，不关心每个算法细节
- 以后要新增规则时，只新增一个校验器并挂到流水线里，避免改核心主流程

这样做的好处：

- 符合开闭原则：对扩展开放，对修改关闭
- 高内聚：每个模块只管一种质量问题
- 低耦合：活体、模糊、遮挡、亮度等能力可以独立替换
- 方便调参：每个校验项可以单独调整阈值
- 方便审计：能明确知道一张照片为什么失败

当前动作挑战方案说明：

- 不把“注册活体”塞进单张图片质量校验流水线，因为动作挑战本质上是多张抓拍之间的顺序关系，不是单图问题
- 不采用“先挑战通过，再让用户额外拍一张注册照”的模式，因为这样仍然存在挑战通过后换照片的漏洞
- 当前注册端采用“摄像头预览 -> 分步动作挑战 -> 从挑战通过的抓拍中挑选最终注册照 -> 后端质量校验 -> 待审核保存”的链路
- 前端只负责开启摄像头、展示当前步骤、抓拍当前动作和展示步骤进度
- 后端负责动作步骤校验、同人一致性比对、最佳正脸抓拍挑选和可信注册照读取
- 当前入口只有摄像头模式，后续树莓派考勤端也会延续“本地动作挑战 + 同流识别”的思路

建议的模块拆分：

- `ActionChallengeSession`：负责一次动作挑战会话的创建、过期时间、当前步骤和已通过抓拍
- `ActionChallengeAnalyzer`：负责判断当前抓拍是否满足动作步骤，并做同人一致性校验
- `LivenessChallengeService`：负责串联挑战创建、抓拍校验、完成判定和可信注册照读取
- `LivenessResult`：统一返回 `passed / code / message / steps`，供前端展示挑战状态
- `TrustedCapture`：负责把最终可信注册照和步骤进度一起交给正式提交流程

建议的交互顺序：

- 用户选择“摄像头采集”
- 前端开启摄像头后，先请求后端创建一次动作挑战
- 页面显示当前步骤，例如“第 1 步：正视镜头”
- 用户拍摄当前步骤，前端只上传这一张抓拍图
- 后端返回当前步骤是否通过，以及下一步动作指引
- 所有步骤通过后，后端直接从已通过抓拍里挑出最终注册照
- 被选中的最终注册照继续走现有 `RegistrationValidationPipeline`
- 质量校验通过后再保存为 `pending_review`

动作挑战的核心思路：

- 每一步先做人脸检测和 landmarks 提取
- 使用关键点估计轻量姿态，校验当前抓拍是否满足“正脸 / 轻微左转 / 轻微右转”等动作要求
- 每一步都提取人脸编码，并和第一步抓拍做同人一致性比对
- 全部步骤通过后，从所有正脸抓拍里按 Laplacian 清晰度挑出最终注册照
- 最终注册照还会做纸张/屏幕翻拍检测，重点看包裹人脸的矩形边框、周期纹理和高亮反光信号
- 如果检测到多人脸、脸过小、姿态不符、关键点缺失、换人、疑似翻拍或超时，当前步骤直接失败并要求重试

这样接入的原因：

- 不破坏现有单图质量校验流水线，符合开闭原则
- 活体挑战和图片质量检测职责分离，模块边界清晰
- 后续如果要把“左转头”替换成“右转头”“点头”“张嘴”，只需要替换动作步骤规则，不需要改注册主流程
- 动作挑战成功和最终注册照被强绑定，能显著降低“先挑战、后换照片”的绕过风险

如何实现判断“画质太模糊、太暗、被遮挡”：

- 模糊：对脸部 ROI 做 Laplacian variance，低于阈值拒绝
- 光线：检查灰度均值，检查高亮像素比例、低亮像素比例，检查脸部区域左右亮度差
- 遮挡：用 landmarks 看眼睛、鼻尖、嘴角是否稳定存在，关键区域缺失或置信度低则拒绝
- 姿态：根据关键点估计 yaw/pitch/roll，超阈值拒绝
- 单人：多张脸直接拒绝
- 纸张/屏幕翻拍：在最终正脸注册照上检测包裹式矩形边框、疑似屏幕/印刷周期纹理和低饱和高亮反光，多信号同时命中时拒绝

### 任务 3：实时识别考勤流

目标：

- 摄像头实时取流
- 检测人脸
- 比对人脸特征
- 写入考勤记录

预期产物：

- 摄像头识别主循环
- 去重逻辑
- 置信度判定
- 考勤时间判定

当前状态：

- 已完成实时视频流和人脸框检测
- 已完成严格身份识别模块接入
- 已完成自动写入 `attendance_records`
- 已完成自动保存考勤快照

### 任务 4：后台管理与查询流

目标：

- 接通 Windows 管理后台或对应的数据查询界面
- 从数据库读取真实数据
- 显示今日考勤、用户列表、设备状态

预期产物：

- 管理后台接口
- 表格查询
- 筛选与统计
- 异常信息展示

当前状态：

- 树莓派本地 HTML 原型页已完成
- 设备侧管理员 API 已接通，可供 Windows 管理项目通过 Tailscale 调用
- 管理员端页面能力已经转移到 Windows 侧项目实现，树莓派主应用不再暴露 `/admin` 页面

## 九、当前运行方式

### 1. 进入项目目录

```bash
cd /home/luck/face3
```

### 2. 激活虚拟环境

Linux / 树莓派环境下：

```bash
source .venv/bin/activate
```

### 3. 启动 FastAPI 页面

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

页面访问地址：

- `http://127.0.0.1:5000/`

本地访问策略：

- 本地 `127.0.0.1` / `localhost` 只允许访问终端页 `/`
- 同一台树莓派上的浏览器如果手工改地址访问 `/portal/*` 或 `/admin`，会直接得到 `404`
- 终端页依赖的 `/video_feed`、`/healthz`、`/api/terminal/status` 仍然保留给本地首页使用

### 4. 外网用户门户首次使用说明

1. 先编辑 [data/member_roster.csv](/home/luck/face3/data/member_roster.csv)，维护单位成员姓名、学号/工号、角色、初始密码和状态。
2. 启动服务后，系统会在 startup 阶段自动把名单同步到 `roster_members`，后续运行期间如果 CSV 再次变化，也会按文件变更自动热同步。
3. 用户访问 `/portal/register`，使用管理员分发的初始密码完成首次注册，并设置新密码。
4. 首次注册成功后，系统会自动跳转到 `/portal/face` 现场拍摄人脸资料。
5. 后续登录统一访问 `/portal/login`，只使用新密码。

如果你不想再手工改 CSV，也可以直接通过设备侧管理员 API 维护名单：

- `POST /api/admin/roster-members/sync`
- `POST /api/admin/roster-members`
- `PUT /api/admin/roster-members/{roster_member_id}`

### 5. 外网访问方式

当前项目最适合的外网访问方式是把整个主应用端口暴露出去，而不是只暴露单独测试页。

推荐方式一：Tailscale Funnel

先启动主应用：

```bash
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

再开 Funnel：

```bash
sudo tailscale funnel 5000
```

执行成功后，Tailscale 会返回一个公网地址，例如：

```text
https://<你的设备名>.<随机后缀>.ts.net
```

此时外网访问方式就是把本地地址替换成这个公网域名：

- 首次注册页：`https://<你的域名>/portal/register`
- 登录页：`https://<你的域名>/portal/login`
- 用户中心：`https://<你的域名>/portal/home`
- 人脸上传页：`https://<你的域名>/portal/face`

说明：

- 公网 Funnel 域名不再暴露树莓派终端页 `/`，访问根路径时会自动跳到 `/portal/login`
- `/portal/*` 是公网用户门户，给成员在手机或电脑浏览器访问
- 历史遗留的 `/admin` 页面已经下线，管理员统一走 Windows 后台 + `/api/admin/*`
- 如果用户未登录，直接访问 `/portal/home` 或 `/portal/face` 会自动跳到 `/portal/login`

推荐方式二：内网穿透或反向代理

如果你不用 Tailscale，也可以把 `5000` 端口通过下面任一方式暴露到公网：

- 路由器端口映射
- `frp`
- `nginx` 反向代理 + 公网域名
- 云服务器反向代理回树莓派

无论你用哪种方式，最终都要把公网流量转发到：

```text
http://树莓派IP:5000
```

### 6. 初始化数据库

如果只想验证 SQLite 是否可用，可以执行：

```bash
python main.py
```

或者：

```bash
python -m scripts.database.demo
```

### 7. 树莓派终端严格识别与考勤写入

当前主应用启动后，树莓派本地终端页已经不只是“显示视频流”，而是会真实执行严格识别和自动考勤。

启动命令：

```bash
cd /home/luck/face3
source .venv/bin/activate
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

终端页入口：

- `http://127.0.0.1:5000/`
- 或树莓派局域网/Tailscale 对应地址的 `/`

当前终端运行时会自动执行：

- 打开树莓派摄像头
- 加载本地已注册人脸库
- 周期性重载已注册编码
- 对实时画面执行严格识别
- 在画面上叠加识别状态
- 识别稳定成功后自动写入考勤记录
- 自动保存现场快照到 `data/snapshots/`
- 采集线程和识别线程分离运行，优先保障视频流刷新

当前识别结果写入位置：

- 数据库表：`attendance_records`
- 快照目录：`data/snapshots/<日期>/`

注意：

- 只有已经在 `face_profiles` 中存在编码的用户，终端才能识别
- 只有正式注册且状态正常的用户会被加载到识别人脸库
- 如果现场一直无人脸、多人脸、模糊、侧脸、歪头或亮度异常，终端不会写考勤记录
- 同一用户识别成功后会进入冷却时间，避免连续重复签到
- 识别层通过后，终端现在还会再经过一层可配置的考勤规则门禁，只有规则放行才真正写库
- 当前 `env.json` 已切到测试友好的 `interval_only` 模式，同一用户 `60` 秒内不会重复写入签到，便于现场反复测试
- 后续如果要切回更正式的规则，只需要把 `attendance_rule_mode` 改成 `daily_once`
- 如果你修改了 `camera_jpeg_quality` 或 `recognition_target_fps`，需要重启服务让新参数生效
- 如果你需要指定一套固定的中文字体，可以在 `env.json` 中配置 `camera_overlay_font_path`
- 当前终端页已把前端取景框、状态条和右侧信息卡整体缩小，并把视频流显示方式改成 `contain`
- 这样做的目的是尽量减少页面装饰层对真实摄像头画面的遮挡

### 8. Windows 管理端对接说明

Windows 侧管理员项目不需要启动这个仓库里的额外服务，它只需要通过 Tailscale 请求树莓派设备侧 API。

设备侧管理员 API 文档：

- [docs/raspberry_pi_admin_api.md](/home/luck/face3/docs/raspberry_pi_admin_api.md)

如果 Windows 侧只想看本次增量变化，重点阅读该文档最后的：

- `14. 2026-04-22 增量变更记录`

本次对 Windows 侧可见的新增内容主要有：

- `/api/admin/device/info`
  - 新增 `attendance_policy`
- `/api/admin/device/health` 的 `camera` 对象新增：
  - `known_faces_count`
  - `last_attendance_message`
  - `last_attendance_record`
- `/api/admin/device/health`
  - 新增 `attendance_policy`
  - `camera` 下新增 `last_policy_event`
- `/api/admin/device/metrics`
  - 新增 `attendance_policy`
- `GET /api/admin/attendance`
  - 现在会开始读到树莓派终端实时新增的真实签到记录
- `GET /api/admin/attendance/today-summary`
  - 现在会随着树莓派本地识别成功而实时变化

说明：

- 本次没有修改已有管理员 API 的路由地址
- 本次没有修改管理员 API 的 Bearer Token 鉴权方式
- 本次主要是“新增字段”和“开始产生真实考勤数据”，不是破坏性修改
- 最新一轮又新增了考勤规则策略摘要和最近一次规则判定结果，方便 Windows 端解释为什么这次识别被放行或拦截

### 9. 首页在线探测策略说明

当前树莓派终端首页会同时做两类探测：

1. 后台心跳探测

- 使用 `/healthz`
- 用于判断树莓派 Web 后端是否还在线

2. 视频流可用性探测

- 使用 `/video_feed`
- 用于判断 MJPEG 视频流是否正常显示

当前实现已经把这两者分开处理：

- 单次视频流报错不再直接判定后台失联
- 只有 `/healthz` 连续多次失败时，首页才会切到“离线”
- 视频流异常时，页面会优先尝试自动重连视频流
- `/healthz` 和 `/api/terminal/status` 默认都按 10 秒节奏轮询，减轻本地日志刷屏和无意义请求

这样做的原因：

- 某些远端浏览器、Tailscale 中继链路、代理链路下，MJPEG 图片流比普通 JSON 心跳更容易短时失败
- 如果把“视频流出错”和“后台挂了”混为一谈，就很容易出现误报
- 现在的策略更适合远端访问场景，也更符合真实含义

## 十、当前注意事项

### 1. 当前前端是原型页面

说明：

- 外网门户和管理员 HTML 页仍然有原型性质
- 但树莓派本地终端页对应的摄像头识别与考勤写入已经接通，不再只是纯展示

### 2. 当前后端依赖仍需补齐

项目已经开始使用 FastAPI、Jinja2、StaticFiles 等能力，因此后续需要确保依赖环境完整。

当前 `pyproject.toml` 中的人脸识别和图像处理依赖已存在，但 Web 相关依赖还需要根据实际运行情况补充。

### 3. 当前配置类会在导入时触发一次加载

因为项目中存在全局 `cfg = AppConfig()`，所以导入配置模块时会读取一次配置文件，这是当前设计的一部分。

## 十一、后续开发建议

接下来建议按下面顺序推进：

1. 继续优化树莓派终端页实时反馈
2. 完善 Windows 侧管理员后台前端页面
3. 增加考勤记录人工修正与补签能力
4. 继续完善成员名单在线维护能力，例如批量导入、删除和 Excel 导入
5. 增加审核、日志与异常追踪能力
6. 增加更细的统计、筛选、导出能力

## 十二、当前项目一句话总结

`face3` 当前已经具备：

- 配置系统
- SQLite 数据层
- 树莓派摄像头采集与严格识别
- FastAPI 页面入口
- 外网注册与人脸入库闭环
- 设备侧管理员 API
- 自动写入真实考勤记录

下一阶段的重点，是把 Windows 管理项目、树莓派终端实时反馈和后台运维能力继续做完整。

## 十三、2026-04-26 人脸审核流补充

这一轮补的是“用户上传 -> 管理员审核 -> 审核通过后才参与终端识别”这条链路。

### 1. 当前流程约定

现在用户门户上传人脸照片后，系统行为改成：

`用户上传照片 -> 质量校验通过 -> 保存 face_profiles -> 状态记为 pending -> 管理员审核 -> approved / rejected`

其中：

- 新上传的人脸档案默认进入 `pending`
- 审核通过后变成 `approved`
- 审核不通过后变成 `rejected`
- 树莓派终端严格识别器只会加载 `approved` 的人脸档案

这意味着：

- 用户上传成功，不代表立刻能在终端识别
- 只有管理员审核通过后，这张照片才会被终端识别人脸库加载
- 历史版本已经存在的人脸档案，在数据库升级时会自动回填为 `approved`，避免升级后现场识别全部失效

### 2. 数据库结构补充

`face_profiles` 表新增了 4 个审核字段：

- `review_status`
- `review_comment`
- `reviewed_at`
- `reviewed_by`

用途分别是：

- `review_status`：当前审核状态
- `review_comment`：管理员审核备注
- `reviewed_at`：审核完成时间
- `reviewed_by`：审核操作人标识

相关实现文件：

- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)

### 3. 用户门户页面补充

当前对外用户页面已经补上审核状态展示。

#### 用户中心 `/portal/home`

现在会展示：

- 最近上传状态
- 是否已经生效到终端识别
- 最近上传时间
- 审核备注
- 审核时间

按钮逻辑现在是：

- 从未上传：显示“上传人脸照片”
- 已上传：显示“查看照片”
- 冷却结束后：允许“重新上传人脸照片”
- 冷却未结束：按钮禁用，并显示剩余等待提示

#### 人脸资料页 `/portal/face`

现在会展示：

- 当前审核状态
- 最近上传时间
- 审核备注
- 重新上传冷却提示

上传成功后的返回文案也已经改成：

- “人脸资料已提交，等待管理员审核。审核通过后才会用于终端识别。”

相关实现文件：

- [templates/portal_home.html](/home/luck/face3/templates/portal_home.html)
- [scripts/web/templates/funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)
- [scripts/web/portal_submission_service.py](/home/luck/face3/scripts/web/portal_submission_service.py)

### 4. 终端识别规则补充

树莓派终端的人脸识别加载逻辑已经改成只读取：

- `review_status = approved`

也就是说：

- `pending` 不参与终端识别
- `rejected` 不参与终端识别
- 只有 `approved` 会进入终端识别人脸库

相关实现文件：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)
- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

说明：

- 终端识别人脸库当前默认每 `60` 秒自动热重载一次
- 所以管理员审核通过后，通常不需要手工重启服务

### 5. Windows 管理端 API 补充

设备侧管理员 API 现在已经补上了人脸审核相关能力。

新增/增强的能力包括：

- `GET /api/admin/face-profiles`
  - 支持 `review_status` 过滤
- `GET /api/admin/face-profiles/{face_profile_id}`
  - 获取单条人脸档案详情
- `POST /api/admin/face-profiles/{face_profile_id}/review`
  - 提交审核结果

人脸档案返回字段新增：

- `review_status`
- `review_comment`
- `reviewed_at`
- `reviewed_by`
- `recognition_enabled`

相关实现文件：

- [scripts/admin_api.py](/home/luck/face3/scripts/admin_api.py)
- [docs/raspberry_pi_admin_api.md](/home/luck/face3/docs/raspberry_pi_admin_api.md)

Windows 端现在最少应接住这几个场景：

1. 拉取待审核列表
2. 查看照片原图
3. 填写通过或驳回结果
4. 展示审核备注、审核时间、审核人

### 6. 当前重新上传策略

重新上传冷却仍然保留，并且已经写入配置：

- `portal_face_reupload_cooldown_seconds`

当前测试值仍然是：

- `300` 秒，也就是 `5` 分钟

对应文件：

- [env.json](/home/luck/face3/env.json)
- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)

后续正式上线时，这个值可以改回：

- `86400` 秒，也就是 `24` 小时

## 十四、2026-04-26 驳回原因与轻量存储补充

这一轮继续把人脸审核流往正式系统的方向收了一步，重点是：

1. 驳回原因不再只是一段自由备注，而是支持结构化可选项
2. 人脸照片不再在树莓派本地长期堆积，只保留当前一份
3. 驳回历史只保留最近三次，避免小系统数据越来越重

### 1. 驳回原因结构化

当前内置的驳回原因包括：

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

实现文件：

- [scripts/face_review.py](/home/luck/face3/scripts/face_review.py)

系统现在会同时保存：

- `review_reason_codes`
- `review_comment`

其中：

- `review_reason_codes` 用于固定原因多选
- `review_comment` 用于补充说明

### 2. 用户和管理员都能看到驳回原因

当前展示逻辑：

- 用户中心 `/portal/home` 会显示最近驳回原因和最近三次驳回记录
- 人脸资料页 `/portal/face` 会显示当前驳回原因和最近三次驳回记录
- Windows 管理端相关 API 会返回固定原因编码、中文标签和最近驳回历史

相关文件：

- [templates/portal_home.html](/home/luck/face3/templates/portal_home.html)
- [scripts/web/templates/funnel_test.html](/home/luck/face3/scripts/web/templates/funnel_test.html)
- [scripts/web/portal_submission_service.py](/home/luck/face3/scripts/web/portal_submission_service.py)
- [scripts/admin_api.py](/home/luck/face3/scripts/admin_api.py)

### 3. 最近三次驳回历史

系统现在新增了一张轻量历史表：

- `face_rejection_history`

用途：

- 给用户查看最近几次被驳回的原因
- 给 Windows 管理端查看最近几次审核失败记录
- 不需要依赖保留旧照片文件，也能知道为什么被驳回

当前规则：

- 每个用户只保留最近 `3` 次驳回历史
- 超过 `3` 次时，自动删除更早记录

相关配置：

- `portal_face_rejection_history_limit`

当前值：

- `3`

相关文件：

- [env.json](/home/luck/face3/env.json)
- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)
- [scripts/database/sqlite_db.py](/home/luck/face3/scripts/database/sqlite_db.py)

### 4. 当前照片替换策略

为了减少树莓派本地无意义的数据堆积，用户重新上传人脸照片时，系统现在会：

1. 先完成照片质量校验和编码提取
2. 删除该账号之前保留的人脸照片文件
3. 删除旧的 `face_profiles` 记录
4. 只保存当前这一次新上传的照片

也就是说：

- 系统只保留“当前照片”这一份
- 不再长期保留历史旧照片
- 但最近三次驳回原因仍然会单独保留

当前配置里 `portal_max_face_profiles` 也已经同步收成：

- `1`

### 5. Windows 管理端新增可见能力

管理员 API 这次新增或增强了这些能力：

- `GET /api/admin/face-profiles/rejection-reasons`
  - 返回固定驳回原因列表
- `GET /api/admin/users/{user_id}`
  - 返回 `recent_face_rejections`
- `GET /api/admin/face-profiles/{face_profile_id}`
  - 返回 `recent_rejections`
- `POST /api/admin/face-profiles/{face_profile_id}/review`
  - 支持 `review_reason_codes`

文档已同步到：

- [docs/raspberry_pi_admin_api.md](/home/luck/face3/docs/raspberry_pi_admin_api.md)

## 十五、2026-04-26 考勤场景活体检测方案

这一轮明确了活体检测的使用场景：

- 不是注册上传时使用
- 而是每天用户站到树莓派前进行实时考勤时使用

### 1. 当前最适合本项目的活体思路

结合树莓派算力、当前系统结构和考勤场景体验，当前最适合 `face3` 的方案是：

`被动活体检测 -> 人脸识别 -> 灰区再触发主动活体`

也就是：

1. 用户进入摄像头画面
2. 先做轻量被动活体检测
3. 被动活体通过后再做人脸识别
4. 如果活体分数或识别分数落在灰区，再触发一次简单动作挑战
5. 通过后才允许签到

### 2. 当前推荐模型

当前最推荐直接接入的是 OpenVINO 的：

- `anti-spoof-mn3`

推荐原因：

- 轻量
- 官方文档明确
- 输入固定为 `128x128`
- 输出就是 `real / spoof` 二分类概率
- 更适合树莓派 CPU 场景做前置被动活体

模型定位：

- 用于挡住手机翻拍、纸质照片、卡通头像、静态假脸等明显伪造输入
- 不建议单独作为唯一活体方案
- 更适合和后续简单动作挑战组合使用

### 3. 建议在项目里的接入位置

第一阶段建议接入：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)

推荐插入顺序：

1. 检测到单张人脸
2. 裁剪人脸区域
3. 送入 `anti-spoof-mn3`
4. 活体分数足够高才进入人脸编码识别
5. 活体分数灰区时，再提示用户做一次简单转头挑战

### 4. 推荐阈值思路

现场试跑后，第一版阈值已经调整成更包容的考勤策略：

- `real_score >= 0.55`：直接进入识别
- `0.30 <= real_score < 0.55`：灰区，先允许进入识别，后续再接主动活体
- `real_score < 0.30`：记为一次低分，连续多帧低分后拒绝签到

说明：

- 考勤场景优先避免真人被单帧误杀
- 后续仍然要根据树莓派摄像头、现场补光和真实样本继续微调

### 5. 模型下载建议

当前建议优先通过 OpenVINO Open Model Zoo 下载并转换：

- 模型名：`anti-spoof-mn3`

建议把模型放到项目目录下，例如：

- `third_party/openvino_models/`

这样后续接入代码时，模型路径管理会更清晰。

### 6. 推荐下载命令

下面这组命令用于：

1. 安装 OpenVINO Python 包
2. 拉取 Open Model Zoo 仓库
3. 下载 `anti-spoof-mn3`
4. 转换为 OpenVINO IR

推荐在项目根目录执行：

```bash
cd /home/luck/face3
uv venv .venv-omz --python 3.9
source .venv-omz/bin/activate
uv pip install --python .venv-omz/bin/python --upgrade pip setuptools wheel
uv pip install --python .venv-omz/bin/python "openvino-dev==2024.6.0"
mkdir -p third_party
git clone --depth 1 https://github.com/openvinotoolkit/open_model_zoo.git third_party/open_model_zoo
uv run --no-project --python .venv-omz/bin/python python third_party/open_model_zoo/tools/model_tools/downloader.py --name anti-spoof-mn3 --output_dir third_party/openvino_models
uv run --no-project --python .venv-omz/bin/python python third_party/open_model_zoo/tools/model_tools/converter.py --name anti-spoof-mn3 --download_dir third_party/openvino_models --output_dir third_party/openvino_models_ir
```

转换完成后，推荐使用的模型路径通常类似：

```bash
/home/luck/face3/third_party/openvino_models_ir/public/anti-spoof-mn3/FP32/anti-spoof-mn3.xml
```

对应权重文件通常是：

```bash
/home/luck/face3/third_party/openvino_models_ir/public/anti-spoof-mn3/FP32/anti-spoof-mn3.bin
```

如果你本机 `omz_downloader` 和 `omz_converter` 命令已经可用，也可以直接用：

```bash
cd /home/luck/face3
source .venv-omz/bin/activate
uv run --no-project --python .venv-omz/bin/python omz_downloader --name anti-spoof-mn3 --output_dir third_party/openvino_models
uv run --no-project --python .venv-omz/bin/python omz_converter --name anti-spoof-mn3 --download_dir third_party/openvino_models --output_dir third_party/openvino_models_ir
```

说明：

- 当前树莓派环境如果仍然使用 Python `3.9`，建议固定使用 `openvino-dev==2024.6.0`
- 因为更新的 `openvino` 包已经要求 Python `3.10+`
- 当前文档里的 Python 包安装和模型工具执行命令已经统一改成 `uv`
- 当前 `anti-spoof-mn3` 在 Open Model Zoo 中下载的是 `ONNX` 文件，因此这里不需要额外安装 `requirements-pytorch.in`
- 如果去安装 `requirements-pytorch.in`，在当前项目目录下还可能把项目自己的 `dlib` 依赖一起卷进来，导致树莓派本地编译非常耗时
- `uv run` 在项目目录里默认会先同步当前项目环境；如果只是执行下载脚本，不希望把 `face3` 自己的 `dlib` 等依赖一起带上，必须加 `--no-project`
- 这里单独使用 `.venv-omz` 作为模型工具环境，避免影响主项目 `.venv`

## 十六、2026-04-26 考勤活体检测第一版已接入

这次已经把第一版“被动活体前置”真正接到每天考勤的终端识别主链路里了。

### 1. 当前实际执行顺序

终端实时识别链路现在变成：

`检测单人脸 -> 裁剪人脸区域 -> anti-spoof-mn3 被动活体 -> 低分连续确认 -> 人脸编码识别 -> 稳定帧 -> 写入考勤`

也就是说：

- 如果模型判断疑似照片、翻拍或假脸，会先允许继续做人脸匹配，但暂不写考勤
- 只有连续多帧低分确认后，才会拦截
- 如果活体分数处于灰区，当前版本会继续进入识别，不再单帧硬拒绝
- 后续第二版再把“灰区触发主动转头挑战”补进去

### 2. 当前新增的代码位置

新增文件：

- [scripts/camera/anti_spoof_service.py](/home/luck/face3/scripts/camera/anti_spoof_service.py)

已接入文件：

- [scripts/camera/strict_face_recognition.py](/home/luck/face3/scripts/camera/strict_face_recognition.py)
- [scripts/camera/camera.py](/home/luck/face3/scripts/camera/camera.py)

作用分别是：

- `anti_spoof_service.py`：加载 OpenVINO IR 模型并返回 `real/spoof` 分数
- `strict_face_recognition.py`：在做人脸编码前先执行被动活体门禁
- `camera.py`：把新的活体失败状态转成终端页进度提示文案

### 3. 当前新增配置项

已经加入配置系统：

- `attendance_liveness_enabled`
- `attendance_liveness_model_path`
- `attendance_liveness_device`
- `attendance_liveness_real_threshold`
- `attendance_liveness_gray_threshold`
- `attendance_liveness_fail_required_times`

当前 `env.json` 测试值是：

- `attendance_liveness_enabled = true`
- `attendance_liveness_model_path = third_party/openvino_models_ir/public/anti-spoof-mn3/FP32/anti-spoof-mn3.xml`
- `attendance_liveness_device = CPU`
- `attendance_liveness_real_threshold = 0.55`
- `attendance_liveness_gray_threshold = 0.30`
- `attendance_liveness_fail_required_times = 3`

相关文件：

- [env.json](/home/luck/face3/env.json)
- [scripts/config/config.py](/home/luck/face3/scripts/config/config.py)

### 4. 当前第一版行为说明

第一版先做的是最稳妥的被动活体前置，不在这次里硬接主动挑战状态机。

当前规则已经从“单帧硬拦”调整成更适合现场考勤的宽松策略：

- `real_score >= 0.55`：放行进入识别
- `0.30 <= real_score < 0.55`：灰区，也放行进入识别
- `real_score < 0.30`：记为一次低分；低分期间允许继续做人脸匹配，但不写考勤；连续 `3` 次低分后才判定疑似假脸

这么做是为了避免树莓派现场摄像头在过曝、模糊、角度轻微偏移时，把真人单帧误判成假脸。

对应终端提示已经补上：

- `疑似假脸`
- `活体重试`
- `重新对准`

### 5. 运行依赖说明

由于项目代码现在会在考勤链路里加载 OpenVINO 模型，因此项目运行环境需要：

- `openvino==2024.6.0`

依赖声明已经加入：

- [pyproject.toml](/home/luck/face3/pyproject.toml)

另外，`face_recognition_models` 当前仍然会因为内部使用 `pkg_resources` 打出一条已知兼容性警告。
项目里已经对这条启动噪音做了静默处理，不影响实际识别逻辑。

### 6. 下一步建议

下一轮最值得继续补的是：

1. 灰区触发简单转头挑战
2. 连续多帧活体分数平滑
3. 在管理员端显示最近一次活体分数与失败原因

## 十七、2026-04-26 Windows 管理端增量说明

这轮需要和 Windows 管理端同步的点，核心只有两类：

1. 哪些老接口没有改
2. 哪些审核相关接口和字段是新增的

### 1. 老设备接口没有改

下面这 4 个接口的地址和调用方式都没有改：

- `GET /api/admin/device/info`
- `GET /api/admin/device/health`
- `GET /api/admin/device/metrics`
- `POST /api/admin/device/reload-config`

2026-04-26 已按当前运行时配置实测通过：

- 树莓派地址：`http://100.74.44.24:5000`
- 管理员 token：`chenhao`

实测返回：

- `GET /api/admin/device/info` -> `200`
- `POST /api/admin/device/reload-config` -> `200`

所以如果 Windows 端现在连设备信息或重载配置都拿不到，优先查 Windows 端自己的请求链路，不要先怀疑这轮新增审核字段把老接口改坏了。

### 2. 新增的人脸审核接口

这轮新增或增强的是这组审核接口：

- `GET /api/admin/face-profiles/rejection-reasons`
- `GET /api/admin/face-profiles/{face_profile_id}`
- `GET /api/admin/face-profiles?review_status=pending`
- `POST /api/admin/face-profiles/{face_profile_id}/review`

审核提交现在支持：

- `review_status`
- `review_reason_codes`
- `review_comment`
- `reviewed_by`

### 3. Windows 端要补的字段

用户详情新增：

- `approved_face_profiles_count`
- `pending_face_profiles_count`
- `rejected_face_profiles_count`
- `face_profile_ready`
- `face_profile_recognition_ready`
- `recent_face_rejections`

人脸档案新增：

- `review_status`
- `review_reason_codes`
- `review_reason_labels`
- `review_comment`
- `reviewed_at`
- `reviewed_by`
- `recognition_enabled`
- `recent_rejections`

其中：

- `review_status` 取值为 `pending / approved / rejected`
- `recognition_enabled` 当前等价于 `review_status == approved`
- `face_profile_recognition_ready` 表示该用户是否已经有审核通过、可进入正式识别名单的照片

### 4. Windows 端建议补的功能

- 审核页先请求 `GET /api/admin/face-profiles/rejection-reasons`，渲染固定驳回原因多选项
- 驳回提交时至少带 `review_status` 和 `review_reason_codes`
- 列表页和详情页展示审核状态、驳回原因、审核备注、审核人、审核时间、最近三次驳回记录
- 用户详情页改用 `face_profile_recognition_ready` 判断“是否已进入正式识别”

### 5. 活体检测这轮暂时不要求 Windows 端改接口

这次接入的是树莓派终端本地“考勤前被动活体检测”，还没有新增 Windows 专用活体查询接口。

所以这轮对 Windows 端真正有影响的，是人脸审核接口和字段，不是设备接口地址。

更完整的对接说明见：

- [docs/raspberry_pi_admin_api.md](/home/luck/face3/docs/raspberry_pi_admin_api.md)

## 十八、2026-05-02 终端画面与快照保留增量

这一节记录 2026-05-02 之后新增的改动，前面的历史章节不再回填修改。

### 1. 终端画面清晰度调整

当前现场测试值已经调整为：

- `camera_width = 1280`
- `camera_height = 720`
- `camera_fps = 15`
- `camera_jpeg_quality = 84`

同时摄像头线程不会把低于目标分辨率的原始画面强行软件放大。这样如果摄像头实际只给低清帧，系统不会再额外插值放大一次，避免画面更糊。

### 2. 终端状态框刷新调整

`/api/terminal/status` 前端刷新间隔从 `10s` 调整为约 `0.8s`。

这个接口只返回轻量 JSON，不参与视频编码、人脸识别和 OpenVINO 推理。调整目的只是让左上角状态框在人脸离开后更快回到“等待人脸”，避免“已签到”停留太久。

### 3. 签到快照只保留最近 7 天

新增配置项：

- `attendance_snapshot_retention_days`

当前值：

- `attendance_snapshot_retention_days = 7`

说明：

- 签到成功时仍会保存现场快照，便于短期复核和异常排查
- 清理只删除 `data/snapshots/YYYYMMDD/` 下超过保留期的图片文件
- 不删除 `attendance_records` 考勤流水，所以历史统计不受影响
- 清理最多一天触发一次，放在签到成功后顺手执行

### 4. Windows 管理端需要补的快照字段

考勤记录返回中新增：

- `snapshot_available`

行为：

- `snapshot_available = true`：快照文件仍在，`snapshot_url` 返回图片接口路径
- `snapshot_available = false`：快照已过期清理或不存在，`snapshot_url = null`

Windows 管理端应使用 `snapshot_available` 控制“查看快照”按钮是否可用，不要只看 `snapshot_path`。

## 十九、2026-05-02 考勤端随机转头活体挑战

这一节记录 2026-05-02 新增的考勤端主动活体挑战。前面的历史章节不再回填修改。

### 1. 这次解决什么问题

单帧 `anti-spoof-mn3` 可以识别一部分照片、屏幕翻拍风险，但它不能单独可靠地区分“真人现场”和“手机播放预录视频”。

所以现在考勤端增加了随机动作挑战：

`识别到身份 -> 业务规则通过 -> 随机要求左/右转头 -> 要求回正脸 -> 再允许写入考勤`

### 2. 当前默认策略

当前 `env.json` 默认开启，但不是每次都触发：

- `attendance_liveness_challenge_enabled = true`
- `attendance_liveness_challenge_mode = risk`

这表示正常高置信度签到仍然直接出结果，只有下面这些可疑情况才触发轻量随机转头挑战：

- 被动活体处于灰区
- 被动活体连续低分
- 人脸识别距离接近阈值

这样做的原因是：

- 静态照片很难产生真实头部 yaw 变化
- 预录视频不知道本次随机要求左转还是右转
- 挑战与当前识别到的用户绑定，换人或人脸离开会重新开始
- 挑战有短时间窗口，过期后会重新随机
- 日常正常签到保留类似门禁的无感体验

### 3. 新增配置项

- `attendance_liveness_challenge_enabled`
- `attendance_liveness_challenge_mode`
- `attendance_liveness_challenge_ttl_seconds`
- `attendance_liveness_challenge_pass_seconds`
- `attendance_liveness_challenge_front_yaw_max`
- `attendance_liveness_challenge_side_yaw_min`
- `attendance_liveness_challenge_side_yaw_max`
- `attendance_liveness_challenge_distance_ratio`

当前测试值：

- `attendance_liveness_challenge_enabled = true`
- `attendance_liveness_challenge_mode = risk`
- `attendance_liveness_challenge_ttl_seconds = 8`
- `attendance_liveness_challenge_pass_seconds = 3`
- `attendance_liveness_challenge_front_yaw_max = 0.18`
- `attendance_liveness_challenge_side_yaw_min = 0.12`
- `attendance_liveness_challenge_side_yaw_max = 0.60`
- `attendance_liveness_challenge_distance_ratio = 0.85`

### 4. 终端页新增状态

左上角状态框会出现：

- `向左转头`
- `向右转头`
- `回到正脸`

用户只需要轻微转头，不需要大幅动作。

### 5. Windows 管理端影响

这次没有新增 Windows 专用接口。

随机转头挑战发生在树莓派终端本地识别流程里，Windows 端暂时不需要改接口调用。后续如果要在 Windows 管理端查看某次签到的活体挑战结果，再单独新增考勤活体审计字段。

## 二十、2026-05-02 活体检测产品约束：只做被动检测

这一节记录新的产品边界：考勤现场不能要求用户转头、眨眼、读数字或做其他配合动作。

因此当前默认配置已经关闭主动挑战：

- `attendance_liveness_challenge_enabled = false`
- `attendance_liveness_challenge_mode = off`

后续活体检测只从树莓派摄像头拍到的画面里做被动判断，重点方向是：

- 多帧 `anti-spoof-mn3` 分数平滑，而不是单帧判断
- 屏幕重放特征，比如摩尔纹、屏幕反光、局部过平纹理
- 时序一致性，比如人脸关键点的自然微动和整张平面移动差异
- RGB rPPG 生命体征线索，但只作为弱信号，不单独决定真假
- 签到快照和活体风险日志，便于现场调参和管理员复核

这意味着系统目标从“主动证明用户是真人”调整为“无感识别为主，基于被动画面风险降低照片和视频攻击通过率”。

## 二十一、2026-05-02 低负载被动活体融合第一版

这一节记录在“不要求用户做动作”的产品约束下，考勤端新增的被动活体融合实现。

### 1. 当前实现

现在不再只看单帧 `anti-spoof-mn3` 结果，而是维护一个短时间滑动窗口：

- 窗口长度：`attendance_liveness_window_seconds = 2.0`
- 最少样本：`attendance_liveness_window_min_samples = 3`

系统在识别线程里融合：

- 多帧 `real_score`
- 多帧低分次数
- 灰区次数
- 人脸裁剪图的屏幕重放风险

这些计算只发生在现有低频识别线程里，不进入 MJPEG 视频推流线程。

### 2. 屏幕重放风险信号

当前第一版用轻量图像特征估计手机屏幕/视频重放风险：

- 高亮低饱和反光比例
- Canny 边缘密度
- 灰度频域高频能量比例

这些信号只在裁剪后的人脸小图上计算，内部会缩放到 `96x96`，负载可控。

### 3. 新增配置项

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

### 4. 当前判定方式

- 样本不足时，状态显示“正在确认”，暂不写入考勤
- 多帧结果稳定且风险低，直接签到
- 多帧 `real_score` 偏低，进入“正在确认”
- 连续低分或屏幕重放风险过高，判定“疑似假脸”

### 5. Windows 管理端影响

这次没有新增 Windows 专用接口。

活体融合发生在树莓派终端本地识别流程中。后续如果要让 Windows 端查看某次签到的活体分数、屏幕风险或判定原因，再追加新的审计字段。

## 二十二、2026-05-03 人脸识别后端升级：YuNet + SFace

这一节记录 2026-05-03 新增的识别后端升级。

### 1. 当前旧识别方式

原来的终端识别方式是：

`face_recognition/dlib -> 128维人脸编码 -> 与库中所有已审核人脸逐个计算距离 -> 取最近结果`

这个方式能用，但对侧脸、低清、遮挡、现场光线变化不算现代方案。

### 2. 新增识别后端

现在新增 OpenCV 官方链路：

`YuNet 人脸检测 -> SFace 对齐与特征提取 -> 余弦相似度匹配`

配置项：

- `recognition_model = auto`
- `face_yunet_model_path`
- `face_sface_model_path`
- `face_yunet_score_threshold`
- `face_yunet_nms_threshold`
- `face_yunet_top_k`
- `face_sface_cosine_threshold`

行为：

- 如果 YuNet/SFace 模型文件存在，系统优先使用 `opencv_sface`
- 如果模型文件不存在，系统自动回退到原来的 `face_recognition/dlib`
- 这样现场服务不会因为模型没下载而启动失败

### 3. 模型下载命令

在项目根目录执行：

```bash
cd /home/luck/face3
mkdir -p third_party/opencv_zoo
curl -L -o third_party/opencv_zoo/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L -o third_party/opencv_zoo/face_recognition_sface_2021dec.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

如果树莓派访问 GitHub 也不稳定，可以改用 jsDelivr 镜像：

```bash
cd /home/luck/face3
mkdir -p third_party/opencv_zoo
curl -L -o third_party/opencv_zoo/face_detection_yunet_2023mar.onnx \
  https://cdn.jsdelivr.net/gh/opencv/opencv_zoo@main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L -o third_party/opencv_zoo/face_recognition_sface_2021dec.onnx \
  https://cdn.jsdelivr.net/gh/opencv/opencv_zoo@main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
```

下载完成后重启服务即可。`recognition_model = auto` 会自动切到 `opencv_sface`。

### 4. 关于检索速度

当前用户规模下，仍然是逐个向量比对。

原因是：

- 每个人脸特征只有几百维
- 几百到几千人逐个算余弦相似度很快
- 真正耗时的是人脸检测、对齐、特征提取和活体判断

如果后续人数达到上万，再考虑接 FAISS/HNSW 这类向量索引。

### 5. 活体增强

考勤端被动活体融合里新增了“包裹人脸的矩形边框”检测，用来提高对纸张照片、手机屏幕边缘的风险感知。

它仍然是低负载信号，只对当前识别帧做轻量边缘/轮廓检测，不进入视频推流线程。

## 二十三、2026-05-03 终端页静态数据改为真实数据

这一节记录 2026-05-03 对树莓派本地终端页右侧信息区的整理。

### 1. 去掉的演示数据

终端页不再使用固定写死的演示数据：

- `教学楼 A 栋`
- `128 / 17 / 6`
- `上午签到时段：07:30 - 09:00`

这些内容之前只适合 UI 演示，现场运行时会误导用户。

### 2. 现在显示什么

右侧“今日概况”现在来自本地 SQLite 数据库：

- `已签到`：当天已经有考勤记录的去重用户数
- `未签到`：系统用户总数减去当天已签到用户数
- `总人数`：当前系统用户总数

右侧“现场公告”现在来自 `env.json`：

- `attendance_start_time`
- `attendance_end_time`
- `device_location`
- `attendance_snapshot_retention_days`

顶部位置标签也改为读取 `device_location`，未配置时回退到 `device_name` 或 `未设置`。

### 3. 新增本地终端接口

新增接口：

```text
GET /api/terminal/screen-data
```

这个接口只给树莓派本地终端页使用，返回右侧信息区需要的数据：

- `site_name`
- `tips`
- `today_stats`
- `announcements`

前端每 5 秒低频刷新一次，所以现场有人签到成功后，右侧概况会自动更新，不需要手动刷新页面。

### 4. 迟到数据说明

当前数据库没有单独的迟到字段，也没有把迟到状态写入考勤记录。

所以这次没有继续展示“迟到”数字。后续如果要显示迟到，需要先定义明确规则，例如：

- 超过 `attendance_start_time` 后签到算迟到
- 超过某个宽限分钟数后签到算迟到
- 或由 Windows 管理端下发课程/班次时间表

规则确定后，再给考勤记录增加迟到判定字段或在查询时按规则计算。

## 二十四、2026-05-15 管理员删除初始名单与激活人员

这一节记录 2026-05-15 对成员管理删除能力的补充。

### 1. 删除初始人员名单

新增管理员接口：

```text
DELETE /api/admin/roster-members/{roster_member_id}
```

用途：

- 删除尚未被用户激活的初始成员名单
- 同时从本地 CSV 成员名单文件和 SQLite 的 `roster_members` 表中移除记录
- 避免删除后下次 CSV 热同步又把同一成员重新写回数据库

安全边界：

- 如果该名单已经关联 `users` 用户记录，接口返回 `409`
- 已激活成员不能通过这个接口直接删除，防止产生孤儿用户
- 如果只是临时禁止注册或登录，优先把成员状态改为 `disabled`

### 2. 删除激活人员

新增管理员接口：

```text
DELETE /api/admin/users/{user_id}
```

用途：

- 删除已经激活的用户账号
- 同步清理该用户的人脸档案、驳回历史和考勤记录
- 尽量删除注册照和签到快照等本地文件

处理规则：

- `roster_members` 初始名单会保留，方便后续重新注册
- 如果要彻底移除某个人，应先删除激活用户，再删除对应初始名单
- 文件清理采用最佳努力策略，缺失文件或非法路径会记录到 `skipped_files`，不会影响数据库删除结果

## 二十五、2026-05-15 终端页低频接口轮询降噪

这一节记录 2026-05-15 对树莓派本地终端页轮询间隔的调整。

### 1. 调整原因

终端页会定时请求健康检查、识别状态和右侧展示数据。  
这些请求本身不会影响业务正确性，但在开发或运行时会持续刷出类似日志：

```text
GET /api/terminal/status
GET /api/terminal/screen-data
GET /healthz
```

为了减少日志噪声和本地请求频率，本次把这些辅助接口的前端轮询间隔统一放大 5 倍。

### 2. 当前间隔

- `/api/terminal/status`：从 `800ms` 调整为 `4000ms`
- `/api/terminal/screen-data`：从 `5000ms` 调整为 `25000ms`
- `/healthz`：从 `10000ms` 调整为 `50000ms`

### 3. 影响范围

- 不影响 `/video_feed` 视频流
- 不影响识别线程和考勤写入
- 只会让终端页文字状态、右侧统计和后端健康提示刷新得更慢

## 二十六、2026-05-15 终端识别页现场文案调整

这一节记录 2026-05-15 对树莓派本地终端识别页展示文案的调整。

### 1. 调整原因

终端页原来的提示里包含识别后端、活体检测状态等偏技术说明。  
这些内容更适合开发调试或文档说明，不适合直接展示给现场签到用户。

### 2. 调整内容

- 删除首页标题下方的说明句
- 保留原有页面布局和卡片结构
- 将“识别提示”改成更接近现场使用的口语提示

当前三条提示为：

- 一次只站一位同学，旁边有人请稍微让开一点
- 脸对着摄像头，眼睛和口鼻别被遮住
- 看到签到成功后再离开，没成功就稍微靠近一点

## 二十七、2026-05-15 终端视频画面清晰度调整

这一节记录 2026-05-15 对树莓派本地终端视频画面的清晰度优化。

### 1. 调整原因

终端页显示的是 `/video_feed` 输出的 MJPEG 视频流。  
如果 USB 摄像头在高分辨率下没有使用合适的输出格式，或者页面端 JPEG 压缩质量偏低，终端画面会显得发糊，人脸细节不够清楚。

### 2. 调整内容

- `camera_jpeg_quality` 从 `84` 调整为 `94`
- 新增 `camera_fourcc = MJPG`
- 摄像头打开时优先设置 `CAP_PROP_FOURCC`，让支持 MJPG 的 USB 摄像头输出更清晰的高分辨率画面

### 3. 注意事项

- 需要重启服务后生效
- 如果摄像头本身不支持 MJPG，OpenCV 会按设备能力回退
- 如果画面仍然模糊，优先检查摄像头焦距、镜头保护膜、光线和实际支持分辨率

## 二十八、2026-05-15 修复终端视频签到提示方框字

这一节记录 2026-05-15 对终端视频画面中签到成功叠字的修复。

### 1. 问题现象

签到成功时，终端视频画面底部会短暂叠加“某某 签到成功”的提示。  
在树莓派环境中，如果 Pillow 选择到的系统字体缺少某些字符，视频叠字会显示成一串方框。

### 2. 修复内容

- 默认叠字字体改为项目内置的 `static/vendor/fonts/noto-sans-sc-600.ttf`
- 字体候选路径统一按项目根目录解析，避免不同启动目录导致字体找不到
- 绘制文字前增加缺字检测，如果当前字体会渲染出 tofu 方框，就继续尝试下一个候选字体

### 3. 影响范围

- 只影响 `/video_feed` 里的视频叠字
- 不影响网页右侧提示、识别逻辑和考勤写入
- 修改后需要重启服务，让新的字体配置和代码生效

## 二十九、2026-05-16 LaTeX1 第一章中文文献引用调整

这一节记录 2026-05-16 对 `latex1` 论文第一章参考文献引用方式的调整。

### 1. 调整内容

- 第一章新增的中文文献引用改为单条顺序标注
- 避免多个中文文献挤在同一个 `\cite{...}` 中
- 参考文献表继续按正文首次出现顺序维护

### 2. 影响范围

- 修改文件：`latex1/chapters/chapter1.tex`
- 修改文件：`latex1/main.tex`
- 修改文件：`latex1/README.md`
