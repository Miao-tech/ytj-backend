import asyncio
import logging
import os
import json
from contextlib import asynccontextmanager
from datetime import datetime

import aio_pika
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# --- 1. 配置和日志 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# RabbitMQ 配置
MQ_HOST = os.getenv('MQ_HOST', 'rabbitmq-service')
MQ_PORT = int(os.getenv('MQ_PORT', 5672))
MQ_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'user')
MQ_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'password')

EXCHANGE_NAME = 'aio_exchange'
TO_SERIAL_ROUTING_KEY = 'to_serial_routing_key'
TO_SERIAL_QUEUE = 'to_serial_queue' 

FROM_SERIAL_ROUTING_KEY = 'from_serial_routing_key'
FROM_SERIAL_QUEUE = 'from_serial_queue' 

# 状态持久化文件路径
STATE_FILE_PATH = "/tmp/device_state.json"

# --- 2. FastAPI 生命周期管理 (Lifespan) ---
app_state = {}

# --- 辅助函数和全局状态 ---
led_states = {}  # LED状态字典，存储每个LED的开关状态

LED_COMMANDS = {
    1: 0x10, 2: 0x11, 3: 0x12, 4: 0x13, 5: 0x14,
    6: 0x15, 7: 0x16, 8: 0x17, 9: 0x18
}

# 状态持久化函数
def save_device_state(device_state, led_states_dict=None):
    """保存设备状态到文件"""
    try:
        state_data = {
            "last_stream_common": device_state.hex() if device_state else None,
            "led_states": led_states_dict if led_states_dict is not None else led_states,
            "timestamp": datetime.now().isoformat()
        }
        with open(STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, ensure_ascii=False, indent=2)
        logger.info(f"设备状态已保存: {state_data}")
    except Exception as e:
        logger.error(f"保存设备状态失败: {e}")

def load_device_state():
    """从文件加载设备状态"""
    global led_states
    try:
        if os.path.exists(STATE_FILE_PATH):
            with open(STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 加载LED状态
            if "led_states" in state_data:
                led_states = state_data["led_states"]
                logger.info(f"已加载LED状态: {led_states}")
            
            # 加载设备状态
            if state_data.get("last_stream_common"):
                device_state = bytes.fromhex(state_data["last_stream_common"])
                logger.info(f"已加载设备状态: {state_data}")
                return device_state
    except Exception as e:
        logger.error(f"加载设备状态失败: {e}")
    return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 应用启动时执行 ---
    loop = asyncio.get_event_loop()
    retry_interval = 5
    while True:
        try:
            logger.info(f"正在尝试连接到 RabbitMQ at {MQ_HOST}:{MQ_PORT}...")
            connection = await aio_pika.connect_robust(
                host=MQ_HOST, port=MQ_PORT, login=MQ_USER, password=MQ_PASS, loop=loop
            )
            channel = await connection.channel()
            exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
            
            # 发送指令队列
            toqueue = await channel.declare_queue(TO_SERIAL_QUEUE, durable=True)
            await toqueue.bind(exchange, routing_key=TO_SERIAL_ROUTING_KEY)
            logger.info(f"队列 '{TO_SERIAL_QUEUE}' 已声明并绑定到路由 '{TO_SERIAL_ROUTING_KEY}'")

            # 接收指令队列
            from_queue_args = {
                'x-max-length': 50,      # 队列最大长度50条消息
                'x-overflow': 'drop-head' # 当队列满时丢弃队头的旧消息
            }
            comequeue = await channel.declare_queue(FROM_SERIAL_QUEUE, durable=True, arguments=from_queue_args)
            await comequeue.bind(exchange, routing_key=FROM_SERIAL_ROUTING_KEY)
            logger.info(f"队列 '{FROM_SERIAL_QUEUE}' 已声明并绑定到路由 '{FROM_SERIAL_ROUTING_KEY}'")

            app_state["mq_connection"] = connection
            app_state["mq_channel"] = channel
            app_state["mq_exchange"] = exchange

            logger.info("✅ RabbitMQ 连接成功并完成设置!")
            
            # 在连接成功后，加载并显示设备状态信息
            await restore_device_state_on_startup()
            break
        except Exception as e:
            logger.error(f"RabbitMQ 连接失败: {e}. 将在 {retry_interval} 秒后重试...")
            await asyncio.sleep(retry_interval)
    yield
    
    # --- 应用关闭时执行 ---
    logger.info("正在关闭 RabbitMQ 连接...")
    if "mq_connection" in app_state:
        await app_state["mq_connection"].close()
    logger.info("RabbitMQ 连接已关闭。")

app = FastAPI(lifespan=lifespan)

# --- 中间件和静态文件 ---
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)
app.mount("/app", StaticFiles(directory="app"), name="static")

# --- 3. 依赖注入 ---
async def get_mq_channel() -> aio_pika.Channel:
    return app_state["mq_channel"]

async def get_mq_exchange() -> aio_pika.Exchange:
    return app_state["mq_exchange"]

# 在全局变量定义后加载状态
last_stream_common = load_device_state()  # 从文件加载之前的状态

async def send_serial_command(command_bytes: bytes, exchange: aio_pika.Exchange):
    await exchange.publish(aio_pika.Message(body=command_bytes), routing_key=TO_SERIAL_ROUTING_KEY)

async def check_current_status(exchange: aio_pika.Exchange, new_command: bytes = None):
    """检查当前状态，如果需要切换设备则先关闭当前设备"""
    global last_stream_common
    if last_stream_common is None: 
        return
    
    # 如果新命令和当前命令相同，不需要关闭（避免重复开启同一设备时的干扰）
    if new_command and last_stream_common == new_command:
        logger.info(f"设备已处于目标状态，无需重复操作: {last_stream_common.hex()}")
        return
    
    # 只有在切换到不同设备时才关闭当前设备
    if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]), exchange)
        logger.info("已发送关闭示波器的指令（切换设备）")
    elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
        await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]), exchange)
        logger.info("已发送关闭万用表的指令（切换设备）")

async def restore_previous_device(exchange: aio_pika.Exchange):
    global last_stream_common
    if last_stream_common:
        logger.info(f"正在恢复之前的设备状态: {last_stream_common.hex()}")
        await send_serial_command(last_stream_common, exchange)

# 新增：在应用启动时恢复设备状态的函数
async def restore_device_state_on_startup():
    """在应用启动时恢复设备状态"""
    global last_stream_common
    if last_stream_common:
        logger.info(f"检测到之前的设备状态，将在WebSocket连接时恢复: {last_stream_common.hex()}")
        # 判断设备类型并记录
        if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
            logger.info("检测到示波器之前处于开启状态")
        elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
            device_types = {0x02: "电阻档", 0x03: "通断档", 0x04: "直流电压档", 0x05: "交流电压档", 0x06: "直流电流档"}
            device_type = device_types.get(last_stream_common[0], "未知档位")
            logger.info(f"检测到万用表之前处于开启状态 - {device_type}")
    else:
        logger.info("没有检测到之前的设备状态，所有设备处于关闭状态")

# --- 4. API 端点 ---
@app.get("/", response_class=FileResponse)
async def read_index():
    return "app/index.html"

@app.get("/api/open_all_led")
async def open_all_led(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global led_states
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
        await send_serial_command(command, exchange)
        led_states[str(led_num)] = True  # 更新LED状态
    save_device_state(last_stream_common)  # 保存状态到文件
    return {"status": "success", "message": "成功发送打开所有LED灯的指令"}

@app.get("/api/close_all_led")
async def close_all_led(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global led_states
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
        await send_serial_command(command, exchange)
        led_states[str(led_num)] = False  # 更新LED状态
    save_device_state(last_stream_common)  # 保存状态到文件
    return {"status": "success", "message": "成功发送关闭所有LED灯的指令"}

@app.get("/api/open_led")
async def open_led(numbers: str, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global led_states
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
                await send_serial_command(command, exchange)
                led_states[str(led_num)] = True  # 更新LED状态
        save_device_state(last_stream_common)  # 保存状态到文件
        return {"status": "success", "message": f"成功发送打开 {len(led_numbers)} 个LED灯的指令"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

@app.get("/api/close_led")
async def close_led(numbers: str, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global led_states
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
                await send_serial_command(command, exchange)
                led_states[str(led_num)] = False  # 更新LED状态
        save_device_state(last_stream_common)  # 保存状态到文件
        return {"status": "success", "message": f"成功发送关闭 {len(led_numbers)} 个LED灯的指令"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

@app.get("/api/open_occ")
async def open_occ(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x08, 0x00, 0x01, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开示波器"}

@app.get("/api/close_occ")
async def close_occ(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]), exchange)
    last_stream_common = None
    save_device_state(last_stream_common)  # 保存状态到文件
    return {"status": "success", "message": "成功关闭示波器"}

@app.get("/api/open_resistense")
async def open_resistense(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x02, 0x00, 0x01, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-电阻档"}

@app.get("/api/open_cont")
async def open_cont(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x03, 0x00, 0x02, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-通断档"}

@app.get("/api/open_dcv")
async def open_dcv(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x04, 0x00, 0x03, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-直流电压档"}

@app.get("/api/open_acv")
async def open_acv(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x05, 0x00, 0x04, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-交流电压档"}

@app.get("/api/open_dca")
async def open_dca(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    command = bytes([0x06, 0x00, 0x05, 0xFE])
    await check_current_status(exchange, command)
    last_stream_common = command
    save_device_state(last_stream_common)  # 保存状态到文件
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-直流电流档"}

@app.get("/api/close_multimeter")
async def close_multimeter(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]), exchange)
    last_stream_common = None
    save_device_state(last_stream_common)  # 保存状态到文件
    return {"status": "success", "message": "成功关闭万用表"}

@app.get("/api/get_temperature")
async def get_temperature(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    await send_serial_command(bytes([0x0B, 0x00, 0x01, 0xFE]), exchange)
    await restore_previous_device(exchange)
    return {"status": "success", "message": "成功发送温度读取指令"}

@app.get("/api/get_gesture")
async def get_gesture(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    await send_serial_command(bytes([0x00, 0x00, 0x01, 0xFE]), exchange)
    await restore_previous_device(exchange)
    return {"status": "success", "message": "成功发送手势读取指令"}

@app.get("/api/get_distance")
async def get_distance(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    await send_serial_command(bytes([0x0C, 0x00, 0x01, 0xFE]), exchange)
    await restore_previous_device(exchange)
    return {"status": "success", "message": "成功发送测距读取指令"}

@app.get("/api/get_light")
async def get_light(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    await send_serial_command(bytes([0x0E, 0x00, 0x01, 0xFE]), exchange)
    await restore_previous_device(exchange)
    return {"status": "success", "message": "成功发送光照读取指令"}

@app.get("/api/power_supply_on")
async def power_supply_on(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    return {"status": "success", "message": "电源输出已开启"}

@app.get("/api/power_supply_off")
async def power_supply_off(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    return {"status": "success", "message": "电源输出已关闭"}

@app.get("/api/set_voltage")
async def set_voltage(voltage: float, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    if not (0 <= voltage <= 10.1):
        return {"status": "error", "message": "电压超出范围 (0-10.1V)"}
    command = None
    if voltage == 0.1: command = bytes([0x09, 0x00, 0x01, 0xFE])
    elif voltage == 1.0: command = bytes([0x09, 0x00, 0x64, 0xFE])
    elif voltage == 10.0: command = bytes([0x09, 0x03, 0xe8, 0xFE])
    elif voltage == 10.1: command = bytes([0x09, 0x03, 0xe9, 0xFE])
    
    if command:
        await send_serial_command(command, exchange)
        return {"status": "success", "message": f"电压设置为 {voltage}V"}
    return {"status": "error", "message": "无法为该电压值生成指令"}

@app.get("/api/set_waveform")
async def set_waveform(waveform: str, frequency: int, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    waveform_codes = {"sine": 0x01, "square": 0x02, "triangle": 0x03}
    freq_codes = {1: 0x01, 100: 0x64}
    waveform_code = waveform_codes.get(waveform.lower())
    freq_code = freq_codes.get(frequency)
    if waveform_code is None or freq_code is None:
        return {"status": "error", "message": "无效的波形或频率"}
    command = bytes([0x30, waveform_code, freq_code, 0xFE])
    await send_serial_command(command, exchange)
    return {"status": "success", "message": f"信号发生器设置: {waveform}波, {frequency}Hz"}

@app.get("/api/signal_generator_stop")
async def signal_generator_stop(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    return {"status": "success", "message": "信号发生器已停止"}

@app.get("/health")
async def health():
    return {"status": "success", "message": f"当前时间: {datetime.now().isoformat()}"}

# 新增：查询当前设备状态的API
@app.get("/api/device_status")
async def get_device_status():
    """获取当前设备状态"""
    global last_stream_common, led_states
    
    # 构建LED状态，确保所有LED都有状态
    led_ui_state = {}
    for led_num in range(1, 10):
        led_ui_state[f"led{led_num}"] = led_states.get(str(led_num), False)
    
    if last_stream_common is None:
        return {
            "status": "success", 
            "device_state": "closed",
            "device_type": None,
            "ui_state": {
                "oscilloscope_button": "closed",
                "multimeter_buttons": {
                    "resistance": "closed",
                    "continuity": "closed", 
                    "dc_voltage": "closed",
                    "ac_voltage": "closed",
                    "dc_current": "closed"
                },
                "led_states": led_ui_state
            },
            "message": "所有设备均已关闭"
        }
    
    # 判断设备类型
    if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        return {
            "status": "success",
            "device_state": "opened", 
            "device_type": "oscilloscope",
            "device_name": "示波器",
            "command_hex": last_stream_common.hex(),
            "ui_state": {
                "oscilloscope_button": "opened",
                "multimeter_buttons": {
                    "resistance": "closed",
                    "continuity": "closed",
                    "dc_voltage": "closed", 
                    "ac_voltage": "closed",
                    "dc_current": "closed"
                },
                "led_states": led_ui_state
            },
            "message": "示波器当前处于开启状态"
        }
    elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
        device_info = {
            0x02: {"type": "multimeter_resistance", "name": "万用表-电阻档", "ui_key": "resistance"},
            0x03: {"type": "multimeter_continuity", "name": "万用表-通断档", "ui_key": "continuity"}, 
            0x04: {"type": "multimeter_dc_voltage", "name": "万用表-直流电压档", "ui_key": "dc_voltage"},
            0x05: {"type": "multimeter_ac_voltage", "name": "万用表-交流电压档", "ui_key": "ac_voltage"},
            0x06: {"type": "multimeter_dc_current", "name": "万用表-直流电流档", "ui_key": "dc_current"}
        }
        info = device_info.get(last_stream_common[0], {"type": "unknown", "name": "未知设备", "ui_key": "unknown"})
        
        # 构建万用表按钮状态
        multimeter_buttons = {
            "resistance": "closed",
            "continuity": "closed",
            "dc_voltage": "closed",
            "ac_voltage": "closed", 
            "dc_current": "closed"
        }
        if info["ui_key"] in multimeter_buttons:
            multimeter_buttons[info["ui_key"]] = "opened"
        
        return {
            "status": "success",
            "device_state": "opened",
            "device_type": info["type"],
            "device_name": info["name"],
            "command_hex": last_stream_common.hex(),
            "ui_state": {
                "oscilloscope_button": "closed",
                "multimeter_buttons": multimeter_buttons,
                "led_states": led_ui_state
            },
            "message": f"{info['name']}当前处于开启状态"
        }
    else:
        return {
            "status": "success",
            "device_state": "unknown",
            "device_type": "unknown", 
            "command_hex": last_stream_common.hex(),
            "ui_state": {
                "oscilloscope_button": "unknown",
                "multimeter_buttons": {
                    "resistance": "unknown",
                    "continuity": "unknown",
                    "dc_voltage": "unknown",
                    "ac_voltage": "unknown",
                    "dc_current": "unknown"
                },
                "led_states": led_ui_state
            },
            "message": "检测到未知的设备状态"
        }

# 新增：前端页面加载时的状态初始化API
@app.get("/api/init_ui_state")
async def init_ui_state():
    """前端页面加载时调用，获取完整的UI状态信息"""
    global last_stream_common
    
    # 获取设备状态
    device_status = await get_device_status()
    
    # 添加额外的初始化信息
    init_info = {
        "timestamp": datetime.now().isoformat(),
        "server_status": "running",
        "websocket_endpoint": "/ws",
        "device_status": device_status,
        "initialization": "completed"
    }
    
    logger.info(f"前端请求初始化UI状态: {device_status.get('device_type', 'none')} - {device_status.get('device_state', 'closed')}")
    
    return init_info

# --- 5. WebSocket 端点 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, channel: aio_pika.Channel = Depends(get_mq_channel)):
    global last_stream_common, led_states
    
    await websocket.accept()
    logger.info("WebSocket 连接已建立")
    
    # 获取exchange用于恢复设备状态
    exchange = app_state.get("mq_exchange")
    
    # 在WebSocket连接建立后，恢复LED状态
    if led_states and exchange:
        logger.info(f"恢复LED状态: {led_states}")
        for led_num_str, is_on in led_states.items():
            if is_on:  # 只恢复开启的LED
                led_num = int(led_num_str)
                if led_num in LED_COMMANDS:
                    command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
                    await send_serial_command(command, exchange)
                    logger.info(f"✅ 已恢复LED{led_num}开启状态")
    
    # 在WebSocket连接建立后，如果有之前保存的设备状态，自动恢复
    if last_stream_common and exchange:
        logger.info(f"WebSocket连接后自动恢复设备状态: {last_stream_common.hex()}")
        await send_serial_command(last_stream_common, exchange)
        
        # 记录恢复的设备类型
        device_state_info = None
        if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
            logger.info("✅ 已自动恢复示波器开启状态")
            device_state_info = {
                "type": "state_sync",
                "device": "oscilloscope", 
                "state": "opened",
                "message": "示波器状态已恢复为开启"
            }
        elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
            device_types = {0x02: "电阻档", 0x03: "通断档", 0x04: "直流电压档", 0x05: "交流电压档", 0x06: "直流电流档"}
            device_type = device_types.get(last_stream_common[0], "未知档位")
            logger.info(f"✅ 已自动恢复万用表开启状态 - {device_type}")
            
            device_types_map = {
                0x02: "resistance", 0x03: "continuity", 0x04: "dc_voltage", 
                0x05: "ac_voltage", 0x06: "dc_current"
            }
            device_state_info = {
                "type": "state_sync",
                "device": "multimeter",
                "subtype": device_types_map.get(last_stream_common[0], "unknown"),
                "state": "opened", 
                "message": f"万用表{device_type}状态已恢复为开启"
            }
        
        # 发送状态同步消息到前端
        if device_state_info:
            sync_message = json.dumps(device_state_info, ensure_ascii=False)
            try:
                await websocket.send_text(sync_message)
                logger.info(f"已发送状态同步消息到前端: {sync_message}")
            except Exception as e:
                logger.error(f"发送状态同步消息失败: {e}")
    
    # 发送LED状态同步消息到前端
    if led_states:
        led_sync_message = json.dumps({
            "type": "led_state_sync",
            "led_states": led_states,
            "message": "LED状态已恢复"
        }, ensure_ascii=False)
        try:
            await websocket.send_text(led_sync_message)
            logger.info(f"已发送LED状态同步消息到前端: {led_sync_message}")
        except Exception as e:
            logger.error(f"发送LED状态同步消息失败: {e}")
    
    # 获取对在启动时声明的固定队列的引用
    comequeue = await channel.get_queue(FROM_SERIAL_QUEUE)
    
    # 强制清空队列中的所有消息
    try:
        purged_result = await comequeue.purge()
        logger.info(f"WebSocket连接时已清空队列，message_count: {purged_result.message_count} 删除了 {purged_result.message_count} 条消息")
    except Exception as e:
        logger.warning(f"清空队列时发生错误: {e}")

    try:
        # 从共享队列中异步消费消息
        async with comequeue.iterator() as queue_iter:
            async for message in queue_iter:
                # 使用 message.process() 自动进行 ACK/NACK
                async with message.process():
                    hex_data = message.body.hex()
                    logger.info(f"输出到websocket: {hex_data}")

                    if websocket.client_state.name == "CONNECTED":
                        await websocket.send_text(hex_data)
                    else:
                        logger.info("WebSocket 已断开，停止消费消息。")
                        break
    except WebSocketDisconnect:
        logger.info("WebSocket 连接由客户端主动断开。")
    except Exception as e:
        logger.error(f"WebSocket 或 RabbitMQ 消费时发生错误: {e}")
    finally:
        logger.info("清理 WebSocket 连接资源。")
