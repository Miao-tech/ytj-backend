from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import serial
import asyncio
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 定义允许的源列表
origins = [
    "http://localhost:3000",
    "http://192.168.3.11:3000",
    "http://192.168.3.30:3000",  # 添加你的新IP
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 串口配置
SERIAL_PORT = "/dev/ttyACM0"
SERIAL_BAUDRATE = 9600

# 最后打开的流式指令
last_stream_common = None

# LED映射表，避免重复代码
LED_COMMANDS = {
    1: 0x10, 2: 0x11, 3: 0x12, 4: 0x13, 5: 0x14,
    6: 0x15, 7: 0x16, 8: 0x17, 9: 0x18
}

# 尝试初始化串口连接
try:
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE)
except Exception as e:
    print(f"无法打开串口: {e}")
    ser = None

# 辅助函数：发送串口命令
async def send_serial_command(command_bytes, delay=0.1):
    """发送串口命令的统一函数"""
    if ser:
        ser.write(command_bytes)
        await asyncio.sleep(delay)

@app.get("/", response_class=HTMLResponse)
async def get():
    """返回主页面"""
    try:
        with open("index.html", "r") as file:
            html = file.read()
        return html
    except FileNotFoundError:
        return "<h1>Index.html not found</h1>"

@app.get("/api/open_all_led")
async def open_all_led():
    """打开所有LED灯"""
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
        await send_serial_command(command)
    
    print("成功打开所有led灯")
    return {"status": "success", "message": "成功打开所有led灯"}

@app.get("/api/close_all_led")
async def close_all_led():
    """关闭所有LED灯"""
    for led_num in range(1, 10):
        command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
        await send_serial_command(command)
    
    print("成功关闭所有led灯")
    return {"status": "success", "message": "成功关闭所有led灯"}

@app.get("/api/open_led")
async def open_led(numbers: str):
    """打开指定的LED灯"""
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        opened_count = 0
        
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x01, 0xFE])
                await send_serial_command(command)
                opened_count += 1
        
        return {"status": "success", "message": f"成功打开{opened_count}个led灯"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

@app.get("/api/close_led")
async def close_led(numbers: str):
    """关闭指定的LED灯"""
    try:
        led_numbers = [int(num.strip()) for num in numbers.split(',')]
        closed_count = 0
        
        for led_num in led_numbers:
            if led_num in LED_COMMANDS:
                command = bytes([LED_COMMANDS[led_num], 0x00, 0x00, 0xFE])
                await send_serial_command(command)
                closed_count += 1
        
        return {"status": "success", "message": f"成功关闭{closed_count}个led灯"}
    except Exception as e:
        return {"status": "error", "message": f"操作失败: {str(e)}"}

# 判断当前流式档位并且关闭
async def check_current_status():
    """检查并关闭当前活跃的流式设备"""
    global last_stream_common
    
    if last_stream_common is None:
        return
    
    if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        # 关闭示波器
        await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]))
        if ser:
            ser.read_all()
        print("成功关闭示波器")
    elif last_stream_common and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
        # 关闭万用表
        await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]))
        if ser:
            ser.read_all()
        print("成功关闭万用表")

@app.get("/api/open_occ")
async def open_occ():
    """打开示波器"""
    global last_stream_common
    
    await check_current_status()
    
    if ser:
        ser.read_all()
    
    command = bytes([0x08, 0x00, 0x01, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开示波器"}

@app.get("/api/close_occ")
async def close_occ():
    """关闭示波器"""
    global last_stream_common
    
    await send_serial_command(bytes([0x07, 0x00, 0x00, 0xFE]))
    last_stream_common = None
    
    return {"status": "success", "message": "成功关闭示波器"}

@app.get("/api/open_resistense")
async def open_resistense():
    """打开万用表-电阻档"""
    global last_stream_common
    
    await check_current_status()
    
    command = bytes([0x02, 0x00, 0x01, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开万用表-电阻档"}

@app.get("/api/open_cont")
async def open_cont():
    """打开万用表-通断档"""
    global last_stream_common
    
    await check_current_status()
    
    command = bytes([0x03, 0x00, 0x02, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开万用表-通断档"}

@app.get("/api/open_dcv")
async def open_dcv():
    """打开万用表-直流电压"""
    global last_stream_common
    
    await check_current_status()
    
    command = bytes([0x04, 0x00, 0x03, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开万用表-直流电压档"}

@app.get("/api/open_acv")
async def open_dcv():
    """打开万用表-交流电压"""
    global last_stream_common
    
    await check_current_status()
    
    command = bytes([0x05, 0x00, 0x04, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开万用表-交流电压档"}

@app.get("/api/open_dca")
async def open_dcv():
    """打开万用表-直流电流"""
    global last_stream_common
    
    await check_current_status()
    
    command = bytes([0x06, 0x00, 0x05, 0xFE])
    last_stream_common = command
    await send_serial_command(command)
    
    return {"status": "success", "message": "成功打开万用表-直流电流档"}


@app.get("/api/close_multimeter")
async def close_multimeter():
    """关闭万用表"""
    global last_stream_common
    
    await send_serial_command(bytes([0x01, 0x00, 0x00, 0xFE]))
    last_stream_common = None
    
    return {"status": "success", "message": "成功关闭万用表"}

async def restore_previous_device():
    """恢复之前打开的设备"""
    global last_stream_common
    
    if last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        # 重新打开示波器
        await send_serial_command(bytes([0x08, 0x00, 0x01, 0xFE]))
    elif last_stream_common == bytes([0x02, 0x00, 0x01, 0xFE]):
        # 重新打开万用表电阻档
        await send_serial_command(bytes([0x02, 0x00, 0x01, 0xFE]))

@app.get("/api/get_temperature")
async def get_temperature():
    """获取温度数据"""
    # 发送读取温度指令
    await send_serial_command(bytes([0x0B, 0x00, 0x01, 0xFE]))
    
    # 恢复之前的设备状态
    await restore_previous_device()
    
    return {"status": "success", "message": "成功发送温度读取指令"}

@app.get("/api/get_distance")
async def get_distance():
    """获取测距数据"""
    # 发送读取测距指令
    await send_serial_command(bytes([0x0C, 0x00, 0x01, 0xFE]))
    
    # 恢复之前的设备状态
    await restore_previous_device()
    
    return {"status": "success", "message": "成功发送测距读取指令"}

@app.get("/api/get_light")
async def get_light():
    """获取光照数据"""
    # 发送读取光照指令
    await send_serial_command(bytes([0x0E, 0x00, 0x01, 0xFE]))
    
    # 恢复之前的设备状态
    await restore_previous_device()
    
    return {"status": "success", "message": "成功发送光照读取指令"}


# 电源控制接口
@app.get("/api/power_supply_on")
async def power_supply_on():
    """打开电源输出"""
    # await send_serial_command(bytes([0x20, 0x00, 0x01, 0xFE]))
    return {"status": "success", "message": "电源输出已开启"}

@app.get("/api/power_supply_off")
async def power_supply_off():
    """关闭电源输出"""
    # await send_serial_command(bytes([0x21, 0x00, 0x00, 0xFE]))
    return {"status": "success", "message": "电源输出已关闭"}

@app.get("/api/set_voltage")
async def set_voltage(voltage: float):
    """设置输出电压"""
    if not (0 <= voltage <= 10.1):
        return {"status": "error", "message": "电压超出范围 (0-12V)"}
    command = None
    if voltage == 0.1:
        command = bytes([0x09, 0x00, 0x01, 0xFE])
    elif voltage == 1.0:
        command = bytes([0x09, 0x00, 0x64, 0xFE])
    elif voltage == 10.0:
        command = bytes([0x09, 0x03, 0xe8, 0xFE])
    elif voltage == 10.1:
        command = bytes([0x09, 0x03, 0xe9, 0xFE])
    print(command)
    await send_serial_command(command)
    return {"status": "success", "message": f"电压设置为 {voltage}V"}

# 信号发生器控制接口
@app.get("/api/set_waveform")
async def set_waveform(waveform: str, frequency: int):
    """设置波形和频率"""
    # 波形类型编码
    waveform_codes = {"sine": 0x01, "square": 0x02, "triangle": 0x03}
    waveform_code = waveform_codes.get(waveform, 0x01)
    
    # 频率转换为字节（假设使用2字节表示频率）
    freq_codes = {1: 0x01, 100: 0x64}
    freq = freq_codes.get(frequency, 0x01)
    command = bytes([0x30, waveform_code, freq, 0xFE])
    print(command)
    # 假设0x30是设置波形和频率的命令
    await send_serial_command(command)
    
    return {"status": "success", "message": f"信号发生器设置: {waveform}波, {frequency}Hz"}

@app.get("/api/signal_generator_stop")
async def signal_generator_stop():
    """停止信号发生器"""
    # 假设0x31是停止信号发生器命令
    # await send_serial_command(bytes([0x31, 0x00, 0x00, 0x00, 0xFE]))
    return {"status": "success", "message": "信号发生器已停止"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点，用于接收串口数据并发送到前端"""
    await websocket.accept()
    print("WebSocket连接已建立")
    is_connected = True
    try:
        while is_connected:
            await asyncio.sleep(0.01)
            # 检查WebSocket连接状态
            if websocket.client_state.name != "CONNECTED":
                print("WebSocket连接状态异常，准备退出")
                break
            if ser and ser.in_waiting > 0:
                try:
                    serdata = ser.read(4)
                    if len(serdata) == 4:  # 确保读取到完整的4字节数据
                        hex_data = serdata.hex()
                        # 再次检查连接状态后再发送
                        if websocket.client_state.name == "CONNECTED":
                            await websocket.send_text(hex_data)
                        else:
                            print("WebSocket已断开，停止发送数据")
                            break
                        # await websocket.send_text(hex_data)
                        # print(f"发送数据: {hex_data}")
                except serial.SerialException as e:
                    print(f"串口错误: {e}")
                    await asyncio.sleep(0.1)  # 串口错误时稍作延迟
                except Exception as e:
                    print(f"发送数据错误: {e}")
                    break  # 发送错误时退出循环
                    
    except WebSocketDisconnect:
        print("WebSocket连接已断开")
        is_connected = False
    except Exception as e:
        print(f"WebSocket错误: {e}")
        is_connected = False
    finally:
        print("清理WebSocket连接资源")
        is_connected = False