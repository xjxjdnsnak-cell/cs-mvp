# CS-Net 安全最佳实践审查报告

## 执行摘要

本次审查针对 CS-Net 项目的 Python/Flask 后端代码进行了安全扫描。项目主要使用 Flask 3.1.2 作为 Web 框架，包含一个主 Web 应用 (`demo_analysis/web_app.py`) 和一个标注工具 (`scripts/annotator/__main__.py`)。

审查发现了 **2 个高危问题**、**2 个中危问题** 和 **3 个低危问题**。最严重的问题包括：开发服务器以 debug 模式运行、以及通过 subprocess 执行用户可控路径的命令。建议优先修复高危问题。

---

## 严重级别发现

### [CRIT-001] Flask 开发服务器以 debug=True 运行

- **规则 ID**: FLASK-DEPLOY-002
- **严重程度**: Critical
- **位置**: `demo_analysis/web_app.py:622`
- **证据**:
  ```python
  if __name__ == "__main__":
      app.run(host="127.0.0.1", port=7860, debug=True)
  ```
- **影响**: `debug=True` 会启用交互式调试器。如果该入口被用于生产环境，攻击者可以通过调试器执行任意代码，等同于远程代码执行 (RCE)。
- **修复**: 使用环境变量控制 debug 模式，生产环境必须关闭：
  ```python
  import os
  debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
  app.run(host="127.0.0.1", port=7860, debug=debug_mode)
  ```
- **缓解**: 确保生产部署使用 gunicorn/uwsgi 等 WSGI 服务器，而非 `app.run()`。

---

## 高危级别发现

### [HIGH-001] subprocess.Popen 执行用户可控路径的命令

- **规则 ID**: FLASK-INJECT-002
- **严重程度**: High
- **位置**: `demo_analysis/web_app.py:237-265`
- **证据**:
  ```python
  cmd = [
      sys.executable,
      "-m",
      "demo_analysis.get_round_win_rate",
      "--demo_path",
      str(upload_path),      # 用户上传的文件路径（已保存到服务端，相对安全）
      "--model_root",
      model_path,            # 来自 request.form，用户可控！
      "--device",
      device,                # 来自 request.form，用户可控！
      "--output",
      str(output_path),
      "--batch_size",
      batch_size,            # 来自 request.form，用户可控！
  ]
  proc = subprocess.Popen(cmd, ...)
  ```
- **影响**: 虽然 `cmd` 以列表形式传递（非 shell 字符串），但 `--model_root`、`--device`、`--batch_size` 参数直接取自用户提交的表单数据，未经过严格校验。恶意用户可能通过构造特殊参数值（如 `--model_root` 包含特殊字符或路径遍历）影响子进程行为。虽然当前风险较 shell=True 低，但仍属于用户输入进入命令执行的攻击面。
- **修复**: 对所有来自 `request.form` 的参数进行严格校验：
  - `model_path`: 使用 `normalize_model_root()` 校验后，再验证路径是否真实存在且为目录
  - `device`: 只允许 `cpu` 或 `cuda` / `cuda:N` 格式
  - `batch_size`: 转换为整数并限制范围（如 1-512）
- **缓解**: 考虑使用 Python 直接调用模块函数，而非通过 subprocess 启动新进程。

### [HIGH-002] 未设置 SECRET_KEY

- **规则 ID**: FLASK-CONFIG-001
- **严重程度**: High
- **位置**: `demo_analysis/web_app.py:50`
- **证据**:
  ```python
  app = Flask(__name__, template_folder="templates", static_folder="static")
  ```
- **影响**: Flask 应用未设置 `SECRET_KEY`。虽然当前应用未显式使用 session 或 cookie 认证，但一旦未来添加相关功能，默认的 session 签名将不安全，攻击者可伪造 session cookie。
- **修复**: 从环境变量加载 `SECRET_KEY`：
  ```python
  app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)
  ```
- **缓解**: 如果确认应用完全不使用 session/cookie，可记录为已知风险并持续监控。

---

## 中危级别发现

### [MED-001] 文件上传缺少大小限制

- **规则 ID**: FLASK-LIMITS-001 / FLASK-UPLOAD-001
- **严重程度**: Medium
- **位置**: `demo_analysis/web_app.py:444-477`
- **证据**:
  ```python
  @app.post("/api/analyze")
  def analyze_demo():
      dem_file = request.files.get("demo_file")
      # ... 直接保存文件，无大小检查
      dem_file.save(upload_path)
  ```
- **影响**: 未设置 `MAX_CONTENT_LENGTH`，攻击者可上传超大文件导致磁盘耗尽或拒绝服务。
- **修复**: 设置 Flask 上传限制：
  ```python
  app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB，根据实际需求调整
  ```

### [MED-002] 缺少安全响应头

- **规则 ID**: FLASK-HEADERS-001
- **严重程度**: Medium
- **位置**: 全局（`demo_analysis/web_app.py`）
- **证据**: 未找到 `after_request` 钩子设置安全头的代码，未使用 Flask-Talisman。
- **影响**: 缺少 CSP、X-Content-Type-Options、X-Frame-Options 等安全头，增加 XSS、点击劫持等攻击风险。
- **修复**: 添加全局 after_request 钩子：
  ```python
  @app.after_request
  def add_security_headers(response):
      response.headers["X-Content-Type-Options"] = "nosniff"
      response.headers["X-Frame-Options"] = "SAMEORIGIN"
      response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self';"
      return response
  ```

---

## 低危级别发现

### [LOW-001] 开发服务器用于运行应用

- **规则 ID**: FLASK-DEPLOY-001
- **严重程度**: Low
- **位置**: `demo_analysis/web_app.py:622`, `scripts/annotator/__main__.py:185`
- **证据**:
  ```python
  app.run(host="127.0.0.1", port=7860, debug=True)
  app.run(host="127.0.0.1", port=7871)
  ```
- **影响**: `app.run()` 是 Flask 开发服务器，不适合生产环境。高并发下性能差，且未经安全加固。
- **修复**: 生产环境使用 gunicorn 或 uwsgi：
  ```bash
  gunicorn -w 4 -b 127.0.0.1:7860 "demo_analysis.web_app:app"
  ```

### [LOW-002] 未验证 Host 头

- **规则 ID**: FLASK-HOST-001
- **严重程度**: Low
- **位置**: `demo_analysis/web_app.py`
- **证据**: 未设置 `TRUSTED_HOSTS`。
- **影响**: 在某些部署场景下可能导致 Host 头攻击（如密码重置链接指向恶意域名）。
- **修复**:
  ```python
  app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1", "your-domain.com"]
  ```

### [LOW-003] 文件下载路由缺少路径遍历防护

- **规则 ID**: FLASK-PATH-001
- **严重程度**: Low
- **位置**: `demo_analysis/web_app.py:357-368`
- **证据**:
  ```python
  @app.get("/viewer/<path:filename>")
  def viewer_assets(filename: str):
      target = (VIEWER_DIR / filename).resolve()
      try:
          target.relative_to(VIEWER_DIR.resolve())
      except ValueError:
          return jsonify({"error": "invalid path"}), 404
  ```
- **影响**: 虽然使用了 `relative_to` 检查，但 `VIEWER_DIR.resolve()` 在路径不存在时行为可能不一致。当前实现基本正确，但建议额外使用 `safe_join` 加固。
- **修复**: 使用 Werkzeug 的 `safe_join`：
  ```python
  from werkzeug.security import safe_join
  target = safe_join(VIEWER_DIR, filename)
  if target is None:
      return jsonify({"error": "invalid path"}), 404
  ```

---

## 其他观察（信息级）

1. **CSRF 保护**: 应用未使用 CSRF 保护。但由于应用未使用 cookie-based 认证（API key 通过 POST body 传递），CSRF 风险较低。如果未来添加 session 认证，需启用 CSRF 保护。

2. **CORS**: 未配置 CORS，当前为同源策略默认行为，符合安全预期。

3. **API Key 传输**: LLM 总结功能通过 POST body 传输 `api_key`，虽非最佳实践（应使用服务端存储），但当前实现下不会暴露在 URL 中。

4. **Torch 反序列化**: `get_round_win_rate.py:114` 使用 `torch.load(..., weights_only=False)`。加载不受信任的 `.pt` / `.pth` 文件可能导致任意代码执行。建议确保模型文件来源可信，或考虑启用 `weights_only=True`（PyTorch 2.0+）。

---

## 修复优先级建议

| 优先级 | 问题 ID | 描述 |
|--------|---------|------|
| P0 | CRIT-001 | 关闭 debug 模式 |
| P0 | HIGH-001 | 校验 subprocess 参数 |
| P1 | HIGH-002 | 设置 SECRET_KEY |
| P1 | MED-001 | 设置文件上传大小限制 |
| P1 | MED-002 | 添加安全响应头 |
| P2 | LOW-001 | 使用生产级 WSGI 服务器 |
| P2 | LOW-002 | 设置 TRUSTED_HOSTS |
| P2 | LOW-003 | 使用 safe_join 加固文件路由 |
