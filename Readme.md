# 创建一个健壮的、可自愈的 Docker 串口服务

本文档旨在指导您如何配置一个 Docker Compose 项目，使其能够稳定、可靠地与物理串口设备（如 USB 转串口的单片机）进行通信。

**最终目标：**
1.  **稳定设备识别**：无论 USB 设备插在哪个物理端口，服务总能找到它。
2.  **开机自动启动**：主机重启后，服务会自动运行。
3.  **故障自愈**：在服务运行期间，如果 USB 设备被拔出再插上，服务能够自动重启并恢复通信。

---

## 步骤一：为串口设备创建固定的 udev 符号链接

这是最关键的基础。我们将为您的 USB 设备创建一个永久不变的“别名”（如 `/dev/ttyMCU`），解决因重新插拔导致设备名（如 `/dev/ttyACM0`, `/dev/ttyACM1`）变化的问题。

#### 1. 查找设备的唯一属性 (Vendor ID & Product ID)

将您的单片机连接到电脑上，打开终端。

*   运行 `lsusb` 命令，找到代表您设备的行。
    ```bash
    $ lsusb
    Bus 001 Device 007: ID 1a86:7523 QinHeng Electronics CH340 serial converter
    ```
    记下 `ID` 后面的两个十六进制数。在此例中，`idVendor` 是 `1a86`，`idProduct` 是 `7523`。

#### 2. 创建 udev 规则文件

*   使用编辑器创建一个新的 udev 规则文件：
    ```bash
    sudo nano /etc/udev/rules.d/99-mcu.rules
    ```

*   将以下内容粘贴到文件中。**请务必将 `1a86` 和 `7523` 替换为您自己设备的值**。
    ```
    SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="ttyMCU", MODE="0666"
    ```
    - `SYMLINK+="ttyMCU"`：为该设备创建一个名为 `ttyMCU` 的符号链接。
    - `MODE="0666"`：设置权限，确保 Docker 容器内有权访问该设备。

#### 3. 应用规则

*   保存文件后，运行以下命令让规则立即生效：
    ```bash
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ```

*   现在，拔下并重新插入您的设备。通过 `ls -l /dev/ttyMCU` 命令验证符号链接是否已成功创建。

---

## 步骤二：配置 Docker Compose 以实现自愈和重启

接下来，我们修改 `compose.yaml` 和 Python 代码，让应用具备故障恢复能力。

#### 1. 修改 `compose.yaml`

编辑您的 `compose.yaml` 文件，对 `serial-service` 进行如下修改：

```yaml
services:
  # ... 其他服务

  serial-service:
    build:
      context: ./serial_service
      dockerfile: Dockerfile
    container_name: serial-service
    
    # 1. 直接挂载稳定的设备链接
    devices:
      - "/dev/ttyMCU:/dev/ttyMCU"
      
    # 2. 添加重启策略，这是实现自愈的关键！
    restart: on-failure
    
    depends_on:
      rabbitmq-service:
        condition: service_healthy
    networks:
      - app-network
    environment:
      - RABBITMQ_DEFAULT_USER=user
      - RABBITMQ_DEFAULT_PASS=password

  # ... 其他服务
```
*   **`devices`**: 我们现在硬编码这个由 `udev` 创建的、永不改变的设备路径。
*   **`restart: on-failure`**: 告诉 Docker，只有当这个容器因错误（以非零状态码退出）而停止时，才自动重启它。

#### 2. 修改 Python 代码以在错误时强制退出

当串口断开时，我们需要让 Python 程序以“失败”状态彻底退出，从而触发 Docker 的重启策略。

**关键点**：如果错误发生在子线程中，必须使用 `os._exit(1)` 来终止整个进程，而不是 `sys.exit(1)`（后者只会终止当前线程）。

编辑 `serial_service/main.py` 文件：

```python
import os
import sys
import time
import logging
from serial import Serial, SerialException # 导入 SerialException

# ... (其他导入和配置)

# 串口配置
SERIAL_PORT = "/dev/ttyMCU"  # 使用 udev 创建的固定路径
SERIAL_BAUDRATE = 9600

# 这是一个示例的线程工作函数
def serial_worker_thread():
    """在子线程中运行的串口读写逻辑"""
    while True:
        try:
            # ... 在这里是您打开串口、循环读写的核心逻辑 ...
            # with Serial(SERIAL_PORT, SERIAL_BAUDRATE) as ser:
            #     while True:
            #         data = ser.read(10)
            #         if data:
            #             # 处理数据
            #             pass
            pass # 占位符，替换为您的代码

        except SerialException as e:
            # 捕获串口相关的特定错误 (如设备断开)
            logging.error(f"串口通信失败: {e}. 服务将强制退出并等待重启...")
            time.sleep(3) # 留出时间让日志刷盘
            os._exit(1) # 强制终止整个进程，触发 Docker 重启

        except Exception as e:
            # 捕获所有其他未知错误
            logging.error(f"发生未预料的错误: {e}. 服务将强制退出并等待重启...")
            time.sleep(3)
            os._exit(1) # 同样强制终止整个进程

# 在您的主函数中
if __name__ == '__main__':
    # ... 启动你的 RabbitMQ 连接等 ...
    
    # ... 创建并启动上述线程 ...
    # thread = threading.Thread(target=serial_worker_thread)
    # thread.start()
    
    # ... 主线程可以做其他事或等待 ...
```

---

## 步骤三：配置 systemd 以实现开机自启

最后，我们将 Docker Compose 项目本身封装成一个标准的 Linux 系统服务，由 `systemd` 管理。

#### 1. 创建 systemd 服务文件

*   创建一个新的服务单元文件：
    ```bash
    sudo nano /etc/systemd/system/ytj-backend.service
    ```

#### 2. 编写服务文件内容

*   将以下内容粘贴进去。**务必修改 `WorkingDirectory` 为您项目 `compose.yaml` 所在的绝对路径**。

    ```ini
    [Unit]
    Description=My YTJ Backend Docker Compose Service
    Requires=docker.service
    After=docker.service network-online.target

    [Service]
    Type=oneshot
    RemainAfterExit=yes

    # !!! 修改为你项目 compose.yaml 文件所在的绝对路径 !!!
    WorkingDirectory=/home/user/ytj-backend

    # 启动命令
    ExecStart=/usr/local/bin/docker-compose up -d

    # 停止命令
    ExecStop=/usr/local/bin/docker-compose down

    [Install]
    WantedBy=multi-user.target
    ```
    *注意：如果您的 docker-compose 命令是 `docker compose` (无连字符)，请将 `ExecStart` 和 `ExecStop` 中的 `/usr/local/bin/docker-compose` 替换为 `/usr/bin/docker compose`。*


#### 3. 启用并管理服务

*   **重新加载 systemd 配置**：
    ```bash
    sudo systemctl daemon-reload
    ```

*   **设置开机自启动**：
    ```bash
    sudo systemctl enable ytj-backend.service
    ```

*   **立即手动启动服务进行测试**：
    ```bash
    sudo systemctl start ytj-backend.service
    ```

*   **检查服务状态**：
    ```bash
    sudo systemctl status ytj-backend.service
    ```

---

## 总结：完整的工作流程

现在，您的系统已经完全自动化和健壮：

1.  **开机**: `systemd` 会在 Docker 服务启动后，自动执行 `docker-compose up -d` 来启动您的所有服务。
2.  **正常运行**: `serial-service` 通过固定的 `/dev/ttyMCU` 路径与您的单片机稳定通信。
3.  **当 USB 被拔出**:
    *   Python 子线程中的串口读写操作失败，抛出 `SerialException`。
    *   `except` 块捕获异常，并调用 `os._exit(1)`。
    *   整个 `serial-service` 容器进程以失败状态码 `1` 退出。
    *   Docker 检测到失败，并根据 `restart: on-failure` 策略，立即尝试重启该容器。
4.  **当 USB 被重新插入**:
    *   `udev` 自动将 `/dev/ttyMCU` 符号链接指向新的设备路径 (如 `/dev/ttyACM1`)。
    *   新启动的 `serial-service` 容器再次尝试连接 `/dev/ttyMCU`，并成功恢复通信。

您已成功构建了一个无需人工干预、具备高度可用性的物联网后台服务。