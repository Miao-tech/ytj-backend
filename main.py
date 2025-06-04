import serial
import asyncio
import sys
from fastmcp import FastMCP
import requests


mcp = FastMCP("Start Yitiji MCP Server")

@mcp.tool()
async def open_all_led() -> str:
    """
    打开设备所有led灯
    """
    response = requests.get(f'http://127.0.0.1:8000/open_all_led')
    await asyncio.sleep(0.5)

    return f"成功打开所有led灯"


@mcp.tool()
async def close_all_led() -> str:
    """
    关闭设备所有led灯
    """
    response = requests.get(f'http://127.0.0.1:8000/close_all_led')
    await asyncio.sleep(0.5)

    return f"成功关闭所有led灯"


@mcp.tool()
async def open_led(numbers: str) -> str:
    """
    打开设备的led灯 

    args:
        numbers: 设备的编号1~9,用','分割，例如：1,3,5
    """
    response = requests.get(f'http://127.0.0.1:8000/open_led?numbers={numbers}')
    await asyncio.sleep(0.5)
    return f"打开{numbers}号led灯成功"

@mcp.tool()
async def close_led(number: int) -> str:
    """
    关闭设备的led灯 

    args:
        number: 设备的编号1~9
    """
    response = requests.get(f'http://127.0.0.1:8000/close_led?number={number}')
    await asyncio.sleep(0.5)
    return f"关闭{number}号led灯成功"



@mcp.tool()
async def open_occ() -> str:
    """
    打开设备的示波器
    """

    response = requests.get(f'http://127.0.0.1:8000/open_occ')
    await asyncio.sleep(0.5)

    return f"打开示波器成功"


@mcp.tool()
async def close_occ() -> str:
    """
    关闭设备的示波器
    """

    response = requests.get(f'http://127.0.0.1:8000/close_occ')
    await asyncio.sleep(0.5)

    return f"关闭示波器成功"

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8123)

