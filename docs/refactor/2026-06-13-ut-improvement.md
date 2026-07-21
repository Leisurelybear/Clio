我正在为 vlog-editing-helper 项目完善单元测试覆盖率。请帮我系统性地梳理并补充 UT，重点关注涉及真实文件 I/O、外部 API（ffmpeg/ffprobe）、AI 调用（Gemini/OpenAI-compatible）的模块。
背景：

已有测试在 vlog_tool/tests/，使用 pytest，共享 fixture 在 conftest.py（tmp_config, empty_dir, config_yaml_content）
已覆盖：test_progress.py, test_log.py, test_utils.py, test_config.py, test_cut.py
尚未覆盖或覆盖不全的核心模块：

vlog_tool/ai/*（gemini.py, openai_compat.py, factory.py, base.py）— AI API 调用
vlog_tool/compress.py, vlog_tool/analyze.py, vlog_tool/pipeline.py — 涉及 ffmpeg/ffprobe 子进程
vlog_tool/tasks/*（analyze, compress, cut, label, plan, refine, scripts）— 编排逻辑，混合文件 I/O + AI 调用
vlog_tool/ui/services/file_service.py, project_service.py — 文件系统操作
vlog_tool/ui/routes/* — HTTP handler，依赖 BaseHTTPRequestHandler 和上面所有服务



请按以下步骤进行：

先逐个 view 上述模块，列出每个模块对外部资源的依赖点（子进程调用、HTTP 请求、文件读写、环境变量），整理成一张表，标注当前是否已 mock。
设计可复用的 mock 基础设施，加到 conftest.py 或新建 vlog_tool/tests/fixtures/ 下的辅助模块：

ffmpeg/ffprobe：用 monkeypatch 替换 subprocess.run/subprocess.Popen，返回可配置的 stdout/returncode，避免依赖真实视频文件和真实 ffmpeg 二进制
AI Provider：为 vlog_tool/ai/base.py 的抽象接口提供一个 FakeAIProvider，可配置返回值（含正常响应、JSON 解析失败、超时/异常场景），通过 factory.py 的注入点替换真实 provider
文件系统：优先使用 tmp_path/tmp_path_factory 构造真实临时目录结构（而不是 mock 整个 pathlib.Path），保证 file_service.py 等路径匹配逻辑被真实验证
HTTP handler：为 ui/routes/* 构造一个轻量 fake BaseHTTPRequestHandler（或用 unittest.mock.MagicMock + spec=），重点验证 _send_json 调用参数和路由分发逻辑，不需要起真实 HTTP server


对每个模块，补充测试用例，至少覆盖：

正常路径（happy path）
外部调用失败/异常（ffmpeg 报错、AI API 超时、JSON 格式错误、文件不存在）
边界条件（空文件列表、空配置、特殊字符文件名等）


每完成一个模块，运行 pytest vlog_tool/tests/ -v 确认现有测试不被破坏，再继续下一个。
优先级顺序：先做 ai/*（依赖最独立，mock 收益最大），再做 ui/services/file_service.py（已知有刚改过的 segment 匹配逻辑需要补测），然后 tasks/*，最后 ui/routes/*。
不要为了提高覆盖率而写脆弱的测试（比如 mock 内部实现细节导致测试和实现强耦合）；优先测试公开接口的输入输出契约。

每个模块完成后给我一个简短总结（新增测试数量、mock 了什么、发现的潜在 bug），不需要每次都贴全部代码diff。