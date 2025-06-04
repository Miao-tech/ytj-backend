from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import serial
import time
import asyncio
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 定义允许的源列表
# 你的前端运行在 http://192.168.3.30:3000
origins = [
        "http://localhost:3000",      # <-- 新增这个，根据错误信息
        "http://192.168.35.157:3000", # <-- 保留这个，以防你有时也用 IP 访问前端
        "http://127.0.0.1:3000",    # <-- 建议也加上，localhost 有时会解析为它
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许访问的源列表
    allow_credentials=True, # 根据你的需求设置。如果前端请求需要携带 cookies 或 Authorization header，则设为 True。
                           # 如果设为 True，allow_origins 不能设为 ["*"]。
    allow_methods=["*"],    # 允许所有方法 (GET, POST, PUT, DELETE, OPTIONS 等)
                            # 或者具体指定: ["GET", "POST", "PUT", "DELETE"]
    allow_headers=["*"],    # 允许所有头部
                            # 或者具体指定: ["Content-Type", "Authorization", "X-Custom-Header"]
)

# 假设的串口配置，实际使用时请根据硬件调整
SERIAL_PORT = "/dev/ttyACM0"
SERIAL_BAUDRATE = 9600

# 最后打开的流式指令
last_stream_common = None


# 尝试初始化串口连接
try:
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE)
except Exception as e:
    print(f"无法打开串口: {e}")
    ser = None

@app.get("/", response_class=HTMLResponse)
async def get():
    """返回主页面"""
    with open("index.html", "r") as file:
        html = file.read()
    return html



@app.get("/open_all_led", response_class=HTMLResponse)
async def open_all_led():
    action = bytes([0x10, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x11, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x12, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x13, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x14, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x15, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x16, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x17, 0x00, 0x01, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x18, 0x00, 0x01, 0xFE])
    ser.write(action)
    print("成功打开所有led灯")
    await asyncio.sleep(0.1)

    # ser.close()
    return "成功打开所有led灯"


@app.get("/close_all_led", response_class=HTMLResponse)
async def close_all_led():
    action = bytes([0x10, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x11, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x12, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x13, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x14, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x15, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x16, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x17, 0x00, 0x00, 0xFE])
    ser.write(action)
    await asyncio.sleep(0.1)

    action = bytes([0x18, 0x00, 0x00, 0xFE])
    ser.write(action)
    print("成功关闭所有led灯")
    await asyncio.sleep(0.1)

    # ser.close()
    return "成功关闭所有led灯"

@app.get("/open_led", response_class=HTMLResponse)
async def open_led(numbers: str):
    numbers = numbers.split(',')
    for number in numbers:
        number = int(number)
        if (number == 1):
            action = bytes([0x10, 0x00, 0x01, 0xFE])
        elif (number == 2):
            action = bytes([0x11, 0x00, 0x01, 0xFE])
        elif (number == 3):
            action = bytes([0x12, 0x00, 0x01, 0xFE])
        elif (number == 4):
            action = bytes([0x13, 0x00, 0x01, 0xFE])
        elif (number == 5):
            action = bytes([0x14, 0x00, 0x01, 0xFE])
        elif (number == 6):
            action = bytes([0x15, 0x00, 0x01, 0xFE])
        elif (number == 7):
            action = bytes([0x16, 0x00, 0x01, 0xFE])
        elif (number == 8):
            action = bytes([0x17, 0x00, 0x01, 0xFE])
        elif (number == 9):
            action = bytes([0x18, 0x00, 0x01, 0xFE])

        ser.write(action)
        await asyncio.sleep(0.1)

    return f"成功打开{len(numbers)}个led灯"

@app.get("/close_led", response_class=HTMLResponse)
async def close_led(numbers: list[int]):
    for number in numbers:
        if (number == 1):
            action = bytes([0x10, 0x00, 0x00, 0xFE])
        elif (number == 2):
            action = bytes([0x11, 0x00, 0x00, 0xFE])
        elif (number == 3):
            action = bytes([0x12, 0x00, 0x00, 0xFE])
        elif (number == 4):
            action = bytes([0x13, 0x00, 0x00, 0xFE])
        elif (number == 5):
            action = bytes([0x14, 0x00, 0x00, 0xFE])
        elif (number == 6):
            action = bytes([0x15, 0x00, 0x00, 0xFE])
        elif (number == 7):
            action = bytes([0x16, 0x00, 0x00, 0xFE])
        elif (number == 8):
            action = bytes([0x17, 0x00, 0x00, 0xFE])
        elif (number == 9):
            action = bytes([0x18, 0x00, 0x00, 0xFE])

        ser.write(action)
        await asyncio.sleep(0.1)

    return f"成功关闭{len(numbers)}个led灯"


# 判断当前流式档位并且关闭
async def checkCurrentStatus():
    # 如果当前示波器正在开启状态, 则需要帮关一下
    if last_stream_common is not None and last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        # 示波器正在占用，请先关闭示波器
        action = bytes([0x07, 0x00, 0x00, 0xFE])
        ser.write(action)
        await asyncio.sleep(0.1)
        ser.read_all()
        print("成功关闭示波器")
    elif last_stream_common is not None and last_stream_common[0] in [0x02, 0x03, 0x04, 0x05, 0x06]:
        # 万用表正在占用，请先关闭万用表
        action = bytes([0x01, 0x00, 0x00, 0xFE])
        ser.write(action)
        await asyncio.sleep(0.1)
        ser.read_all()
        print("成功关闭万用表")


@app.get("/open_occ", response_class=HTMLResponse)
async def open_occ():
    global last_stream_common

    await checkCurrentStatus()

    ser.read_all()
    action = bytes([0x08, 0x00, 0x01, 0xFE])
    last_stream_common = action
    ser.write(action)

    return f"成功打开示波器"



@app.get("/close_occ", response_class=HTMLResponse)
async def close_occ():
    global last_stream_common

    action = bytes([0x07, 0x00, 0x00, 0xFE])
    ser.write(action)
    last_stream_common = None

    return f"成功关闭示波器"





@app.get("/open_resistense", response_class=HTMLResponse)
async def open_resistense():
    global last_stream_common

    await checkCurrentStatus()

    action = bytes([0x02, 0x00, 0x01, 0xFE])
    last_stream_common = action
    ser.write(action)

    return f"成功打开万用表-电阻档"



@app.get("/open_beep", response_class=HTMLResponse)
async def open_beep():
    global last_stream_common

    await checkCurrentStatus()

    action = bytes([0x03, 0x00, 0x02, 0xFE])
    last_stream_common = action
    ser.write(action)

    return f"成功打开万用表-通断万用表"


@app.get("/close_wanyongbiao", response_class=HTMLResponse)
async def close_resistense():
    global last_stream_common

    action = bytes([0x01, 0x00, 0x00, 0xFE])
    ser.write(action)
    last_stream_common = None

    return f"成功关闭万用表"



@app.get("/open_tempature", response_class=HTMLResponse)
async def open_tempature():
    # ---------------------------------------------
    # 关闭显波器
    # action = bytes([0x07, 0x00, 0x00, 0xFE])
    # ser.write(action)
    # ser.read_all()
    # await asyncio.sleep(0.1)
    # =============================================

    # ---------------------------------------------
    # 发送读取温度指令
    action = bytes([0x0B, 0x00, 0x01, 0xFE])
    # last_stream_common = action
    ser.write(action)

    # tempature = ""
    # humidty = ""

    # while True:
    #     serdata = ser.read(4)
    #     if serdata[0] == 11:
    #         tempature = str(serdata[1])
    #         humidty = str(serdata[2])
    #         # print("温度0:" + str(serdata[0]))
    #         print("温度:" + tempature)
    #         print("湿度:" + humidty)
    #         # print("湿度3:" + str(serdata[3]))
    #         print("*" * 70)
    #         break
    # =============================================

    # ---------------------------------------------
    # 如果在获取温度前示波器是打开状态，就重新打开示波器信号
    if  last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        action = bytes([0x08, 0x00, 0x01, 0xFE])
        ser.write(action)
    # 如果在获取温度前万用表电阻档位是打开状态，就重新打开万用表
    elif last_stream_common == bytes([0x02, 0x00, 0x01, 0xFE]):
        action = bytes([0x02, 0x00, 0x01, 0xFE])
        ser.write(action)
    # await asyncio.sleep(0.1)
    # =============================================

    return f"成功打开温度计"


@app.get("/get_distance", response_class=HTMLResponse)
async def get_distance():
    # ---------------------------------------------
    # 发送读取红外测距指令
    action = bytes([0x0C, 0x00, 0x01, 0xFE])
    # last_stream_common = action
    ser.write(action)

    # ---------------------------------------------
    # 如果在获取温度前示波器是打开状态，就重新打开示波器信号
    if  last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        action = bytes([0x08, 0x00, 0x01, 0xFE])
        ser.write(action)
    # 如果在获取温度前万用表电阻档位是打开状态，就重新打开万用表
    elif last_stream_common == bytes([0x02, 0x00, 0x01, 0xFE]):
        action = bytes([0x02, 0x00, 0x01, 0xFE])
        ser.write(action)
    # await asyncio.sleep(0.1)
    # =============================================

    return f"成功获取测距值"

@app.get("/get_light", response_class=HTMLResponse)
async def get_light():
    # ---------------------------------------------
    # 发送读取红外测距指令
    action = bytes([0x0E, 0x00, 0x01, 0xFE])
    # last_stream_common = action
    ser.write(action)

    # ---------------------------------------------
    # 如果在获取温度前示波器是打开状态，就重新打开示波器信号
    if  last_stream_common == bytes([0x08, 0x00, 0x01, 0xFE]):
        action = bytes([0x08, 0x00, 0x01, 0xFE])
        ser.write(action)
    # 如果在获取温度前万用表电阻档位是打开状态，就重新打开万用表
    elif last_stream_common == bytes([0x02, 0x00, 0x01, 0xFE]):
        action = bytes([0x02, 0x00, 0x01, 0xFE])
        ser.write(action)
    # await asyncio.sleep(0.1)
    # =============================================

    return f"成功获取光照值"


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点，用于接收串口数据并发送到前端"""
    await websocket.accept()
    try:
        while True:
            # await websocket.accept()             # 修正：将read改为accept
            # data = await websocket.receive_text()  # 接收前端发送的文本数据
            # print(f"Received: {data}")             # 打印收到的信息

            await asyncio.sleep(0.01)
            if ser and ser.in_waiting > 0:
                serdata = ser.read(4)
                # print(serdata)
                # print("Clock tick")
                await websocket.send_text(serdata.hex())  # 将二进制数据转换为十六进制字符串发送

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


