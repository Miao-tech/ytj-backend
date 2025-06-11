import asyncio
import logging
import os
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

# --- 2. FastAPI 生命周期管理 (Lifespan) ---
app_state = {}

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

# --- 辅助函数和全局状态 ---
last_stream_common = None
LED_COMMANDS = {
    1: 0x10, 2: 0x11, 3: 0x12, 4: 0x13, 5: 0x14,
    6: 0x15, 7: 0x16, 8: 0x17, 9: 0x18
}

async def send_serial_command(command_bytes: bytes, exchange: aio_pika.Exchange):
    await exchange.publish(aio_pika.Message(body=command_bytes), routing_key=TO_SERIAL_ROUTING_KEY)

async def check_current_status(exchange: aio_pika.Exchange):
    global last_stream_common
    if last_stream_common is None: return
    if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]), exchange)
        logger.info("已发送关闭示波器的指令")
    elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
        await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]), exchange)
        logger.info("已发送关闭万用表的指令")

async def restore_previous_device(exchange: aio_pika.Exchange):
    global last_stream_common
    if last_stream_common:
        logger.info(f"正在恢复之前的设备状态: {last_stream_common.hex()}")
        await send_serial_command(last_stream_common, exchange)

# --- 4. API 端点 ---
@app.get("/", response_class=FileResponse)
async def read_index():
    return "app/index.html"

@app.get("/api/open_all_led")
async def open_all_led(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
        await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功发送打开所有LED灯的指令"}

@app.get("/api/close_all_led")
async def close_all_led(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
        await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功发送关闭所有LED灯的指令"}

@app.get("/api/open_led")
async def open_led(numbers: str, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
                await send_serial_command(command, exchange)
        return {"status": "success", "message": f"成功发送打开 {len(led_numbers)} 个LED灯的指令"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

@app.get("/api/close_led")
async def close_led(numbers: str, exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
                await send_serial_command(command, exchange)
        return {"status": "success", "message": f"成功发送关闭 {len(led_numbers)} 个LED灯的指令"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

@app.get("/api/open_occ")
async def open_occ(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x08, 0x00, 0x01, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开示波器"}

@app.get("/api/close_occ")
async def close_occ(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]), exchange)
    last_stream_common = None
    return {"status": "success", "message": "成功关闭示波器"}

@app.get("/api/open_resistense")
async def open_resistense(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x02, 0x00, 0x01, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-电阻档"}

@app.get("/api/open_cont")
async def open_cont(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x03, 0x00, 0x02, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-通断档"}

@app.get("/api/open_dcv")
async def open_dcv(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x04, 0x00, 0x03, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-直流电压档"}

@app.get("/api/open_acv")
async def open_acv(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x05, 0x00, 0x04, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-交流电压档"}

@app.get("/api/open_dca")
async def open_dca(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await check_current_status(exchange)
    command = bytes([0x06, 0x00, 0x05, 0xFE])
    last_stream_common = command
    await send_serial_command(command, exchange)
    return {"status": "success", "message": "成功打开万用表-直流电流档"}

@app.get("/api/close_multimeter")
async def close_multimeter(exchange: aio_pika.Exchange = Depends(get_mq_exchange)):
    global last_stream_common
    await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]), exchange)
    last_stream_common = None
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

# --- 5. WebSocket 端点 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, channel: aio_pika.Channel = Depends(get_mq_channel)):
    global last_stream_common
    
    await websocket.accept()
    logger.info("WebSocket 连接已建立")
    
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
        # 在WebSocket断开时检查设备状态，自动关闭正在运行的设备
        try:
            exchange = app_state.get("mq_exchange")
            if exchange and last_stream_common:
                if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
                    # 如果示波器正在运行，发送关闭指令
                    await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]), exchange)
                    logger.info("WebSocket断开时已自动发送关闭示波器的指令")
                    last_stream_common = None
                elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
                    # 如果万用表正在运行，发送关闭指令
                    await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]), exchange)
                    logger.info("WebSocket断开时已自动发送关闭万用表的指令")
                    last_stream_common = None
        except Exception as e:
            logger.error(f"自动关闭设备时发生错误: {e}")
        
        logger.info("清理 WebSocket 连接资源。")
