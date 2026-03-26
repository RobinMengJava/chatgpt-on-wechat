# chatgpt-on-wechat 部署踩坑记录

> 环境：OpenCloudOS（CentOS/RHEL 系）、Python 3.9、root 用户

---

## 1. pip 安装依赖失败：openai==0.27.8 找不到

**错误**
```
ERROR: Could not find a version that satisfies the requirement openai==0.27.8
```

**原因**：系统默认 Python 版本是 3.6，openai 0.27.8 要求 Python >=3.7.1，pip 自动过滤掉了不兼容版本。镜像源无关。

**解决**：升级 Python 到 3.9。
```bash
dnf install python39 -y
python3.9 --version  # 验证
```

安装依赖时指定 python3.9：
```bash
python3.9 -m pip install -r requirements.txt
```

---

## 2. 升级 Python 后 python3 仍指向 3.6

**原因**：系统默认 `python3` 命令软链接没有更新。

**解决**：启动和安装时显式使用 `python3.9`，不修改系统默认值，避免影响系统其他工具。
```bash
python3.9 -m pip install -r requirements.txt
nohup python3.9 app.py &
```

---

## 3. 启动时 nohup.out 文件不存在

**错误**
```
tail: 无法打开'nohup.out' 读取数据: No such file or directory
```

**原因**：`nohup python3.9 app.py & tail -f nohup.out` 中 tail 比 nohup 先执行，文件还未创建。

**解决**：忽略该警告，稍等片刻后手动执行：
```bash
tail -f nohup.out
```

---

## 4. config.json 格式错误

**错误**
```
JSONDecodeError: Expecting ',' delimiter: line 4 column 24
```

**原因**：config.json 中 JSON 格式有误，常见原因：
- 漏写逗号 `,`
- 最后一项后多了逗号
- 使用了中文引号 `""` 而非英文引号 `""`

**解决**：检查并修正 config.json，重点看报错指向的行列号。

---

## 5. 缺少模块：web、websocket

**错误**
```
ModuleNotFoundError: No module named 'web'
ModuleNotFoundError: No module named 'websocket'
```

**原因**：第一次 `pip install -r requirements.txt` 因 openai 版本问题报错中断，后续依赖未安装完整。

**解决**：升级 Python 后重新完整安装：
```bash
python3.9 -m pip install -r requirements.txt
```

---

## 6. 渠道配置项为空导致启动失败

**错误**
```
TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'
```

**原因**：config.json 中启用了某个渠道（如 `wechatcom_app`），但对应的配置项（token、aes_key、corp_id 等）未填写，程序拿到 `None`。

**解决**：在 config.json 中填写对应渠道的完整配置，或将 `channel_type` 改为实际使用的渠道：
```json
"channel_type": "wechatmp"
```

---

## 7. 端口无法访问

**原因**：服务器安全组已开放，但系统防火墙未放行。

**解决**：
```bash
# 查看防火墙状态
firewall-cmd --state

# 查看已开放端口
firewall-cmd --list-ports

# 开放 9989 端口
firewall-cmd --add-port=9989/tcp --permanent
firewall-cmd --reload
```

---

## 8. 重启项目

```bash
# 找到进程
ps aux | grep app.py

# 杀掉并重启（一行）
pkill -f app.py && sleep 1 && nohup python3.9 app.py &

# 查看日志
tail -f nohup.out
```

---

## 正确的完整启动流程

```bash
# 1. 进入项目目录
cd /usr/local/server/agent/chatgpt-on-wechat

# 2. 安装依赖（首次）
python3.9 -m pip install -r requirements.txt

# 3. 启动
nohup python3.9 app.py &

# 4. 查看日志
tail -f nohup.out
```
