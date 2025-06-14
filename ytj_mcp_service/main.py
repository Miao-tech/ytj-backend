from fastmcp import FastMCP
import requests

mcp = FastMCP("Start Yitiji MCP Server")

# 重要提示：
# 在本地直接运行时，"http://127.0.0.1:8000" 是正确的。
# 如果你在 Docker Compose 环境中运行这个脚本，你需要将地址改为 FastAPI 服务的名称，
# 例如: YTJ_API_URL = "http://ytjweb-service:8000"


YTJ_API_URL = "http://ytjweb-service:8000"

# --- LED 控制 ---

@mcp.tool()
def open_all_led() -> str:
    """
    打开设备所有led灯
    """
    try:
        response = requests.get(f'{YTJ_API_URL}/api/open_all_led', timeout=5)
        response.raise_for_status()
        return "成功发送打开所有LED灯的指令"
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {str(e)}")
        raise Exception(f"无法连接到 ytjweb-service: {str(e)}")

@mcp.tool()
def close_all_led() -> str:
    """
    关闭设备所有led灯
    """
    response = requests.get(f'{YTJ_API_URL}/api/close_all_led')
    return "成功发送关闭所有LED灯的指令"

@mcp.tool()
def open_led(numbers: str) -> str:
    """
    打开指定的一个或多个LED灯
    args:
        numbers: 设备的编号1~9, 如果有多个，用','分割，例如： "1,3,5"
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_led?numbers={numbers}')
    return f"成功发送打开 {numbers} 号LED灯的指令"

@mcp.tool()
def close_led(numbers: str) -> str:
    """
    关闭指定的一个或多个LED灯
    args:
        numbers: 设备的编号1~9, 如果有多个，用','分割，例如： "2,4,6"
    """
    response = requests.get(f'{YTJ_API_URL}/api/close_led?numbers={numbers}')
    return f"成功发送关闭 {numbers} 号LED灯的指令"

# --- 示波器控制 ---

@mcp.tool()
def open_occ() -> str:
    """
    打开设备的示波器
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_occ')
    return "成功打开示波器"

@mcp.tool()
def close_occ() -> str:
    """
    关闭设备的示波器
    """
    response = requests.get(f'{YTJ_API_URL}/api/close_occ')
    return "成功关闭示波器"

# --- 万用表控制 ---

@mcp.tool()
def open_resistance() -> str:
    """
    打开万用表并切换到电阻档
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_resistense')
    return "成功打开万用表-电阻档"

@mcp.tool()
def open_continuity() -> str:
    """
    打开万用表并切换到通断档（蜂鸣档）
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_cont')
    return "成功打开万用表-通断档"

@mcp.tool()
def open_dc_voltage() -> str:
    """
    打开万用表并切换到直流电压档
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_dcv')
    return "成功打开万用表-直流电压档"

@mcp.tool()
def open_ac_voltage() -> str:
    """
    打开万用表并切换到交流电压档
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_acv')
    return "成功打开万用表-交流电压档"

@mcp.tool()
def open_dc_current() -> str:
    """
    打开万用表并切换到直流电流档
    """
    response = requests.get(f'{YTJ_API_URL}/api/open_dca')
    return "成功打开万用表-直流电流档"

@mcp.tool()
def close_multimeter() -> str:
    """
    关闭万用表
    """
    response = requests.get(f'{YTJ_API_URL}/api/close_multimeter')
    return "成功关闭万用表"

# --- 传感器数据获取 ---

@mcp.tool()
def get_temperature() -> str:
    """
    获取设备当前的温度数据
    """
    response = requests.get(f'{YTJ_API_URL}/api/get_temperature')
    return "成功发送温度读取指令"

@mcp.tool()
def get_gesture() -> str:
    """
    获取设备当前的手势传感器数据
    """
    response = requests.get(f'{YTJ_API_URL}/api/get_gesture')
    return "成功发送手势读取指令"

@mcp.tool()
def get_distance() -> str:
    """
    获取设备当前的测距数据
    """
    response = requests.get(f'{YTJ_API_URL}/api/get_distance')
    return "成功发送测距读取指令"

@mcp.tool()
def get_light_intensity() -> str:
    """
    获取设备当前的光照强度数据
    """
    response = requests.get(f'{YTJ_API_URL}/api/get_light')
    return "成功发送光照读取指令"

# --- 电源控制 ---

@mcp.tool()
def power_supply_on() -> str:
    """
    打开可编程电源的输出
    """
    response = requests.get(f'{YTJ_API_URL}/api/power_supply_on')
    return "电源输出已开启"

@mcp.tool()
def power_supply_off() -> str:
    """
    关闭可编程电源的输出
    """
    response = requests.get(f'{YTJ_API_URL}/api/power_supply_off')
    return "电源输出已关闭"

@mcp.tool()
def set_voltage(voltage: float) -> str:
    """
    设置可编程电源的输出电压
    args:
        voltage: 要设置的电压值，浮点数，单位是伏特(V)。例如: 5.0
    """
    response = requests.get(f'{YTJ_API_URL}/api/set_voltage?voltage={voltage}')
    return f"成功发送设置电压为 {voltage}V 的指令"

# --- 信号发生器控制 ---

@mcp.tool()
def set_waveform(waveform: str, frequency: int) -> str:
    """
    设置信号发生器的输出波形和频率
    args:
        waveform: 波形类型，可选值为 "sine" (正弦波), "square" (方波), "triangle" (三角波)
        frequency: 频率，整数，单位是赫兹(Hz)
    """
    response = requests.get(f'{YTJ_API_URL}/api/set_waveform?waveform={waveform}&frequency={frequency}')
    return f"成功设置信号发生器: {waveform}波, {frequency}Hz"

@mcp.tool()
def signal_generator_stop() -> str:
    """
    停止信号发生器的输出
    """
    response = requests.get(f'{YTJ_API_URL}/api/signal_generator_stop')
    return "信号发生器已停止"


if __name__ == "__main__":
    print(f"Agent Service 启动中...")
    print(f"将要连接的 Yitiji API 地址: {YTJ_API_URL}")
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
