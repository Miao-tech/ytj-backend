import pika
import serial
import threading
import time
import sys
import os

# --- 1. 配置信息 ---
# RabbitMQ 配置
MQ_HOST = 'rabbitmq-service'
MQ_PORT = 5672

# 从环境变量获取RabbitMQ配置
MQ_PORT = int(os.getenv('MQ_PORT', 5672))
MQ_USER = os.getenv('MQ_USER', 'user')
MQ_PASS = os.getenv('MQ_PASS', 'password')

EXCHANGE_NAME = 'aio_exchange'

# 从MQ读取消息的队列和路由键
QUEUE_FROM_MQ = 'aio_queue'
ROUTING_KEY_FROM_MQ = 'aio_key'

# 从串口读取数据后，发往MQ使用的路由键 (建议用不同的key，方便区分)
ROUTING_KEY_FROM_SERIAL = 'serial_data_key'

# 串口配置
SERIAL_PORT = "/dev/ttyACM0"  # 根据你的实际情况修改，Windows上可能是 "COM3"
SERIAL_BAUDRATE = 9600

# --- 2. 工作线程函数 ---

# 任务A: 负责从 RabbitMQ 消费消息，并写入串口
def mq_to_serial_worker(serial_port):
    """这个函数在一个独立的线程中运行"""
    try:
        # 关键：每个线程创建自己的连接和通道，保证线程安全
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=MQ_HOST, port=MQ_PORT, credentials=pika.PlainCredentials(MQ_USER, MQ_PASS)))
        channel = connection.channel()

        # 声明，确保存在
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct')
        channel.queue_declare(queue=QUEUE_FROM_MQ)
        channel.queue_bind(queue=QUEUE_FROM_MQ, exchange=EXCHANGE_NAME, routing_key=ROUTING_KEY_FROM_MQ)

        print('[MQ->SERIAL] 线程已启动，等待来自 aio_queue 的消息...')

        # 使用一个无限循环来持续轮询
        while True:
            try:
                # 尝试从队列中获取单条消息
                # auto_ack=False 表示我们需要手动确认消息
                method_frame, properties, body = channel.basic_get(queue=QUEUE_FROM_MQ, auto_ack=False)

                # 检查是否真的收到了消息
                if method_frame:
                    if serial_port and serial_port.is_open:
                        print(f" [x] 消息 {body} 写到串口")
                        ser.write(body)

                        # 关闭示波器或万用表的时候，需要清除掉缓存区的内容
                        if (body == bytes([0x07, 0x00, 0x00, 0xFE]) or body == bytes([0x01, 0x00, 0x00, 0xFE])):
                            ser.read_all()

                    # 手动确认消息，告诉 RabbitMQ 这条消息处理完了，可以删除了
                    channel.basic_ack(method_frame.delivery_tag)
                    print(" [✓] Message acknowledged.")

                # 无论有没有消费到消息，都等待1秒
                time.sleep(1)
            except KeyboardInterrupt:
                print(" [!] Interrupted by user. Exiting.")
                break
            except pika.exceptions.ConnectionClosedByBroker:
                # 如果连接因为长时间不活动而关闭，可以处理重连
                print(" [!] Connection closed by broker. Reconnecting...")
                # (这里可以添加重连逻辑)
                break
            except Exception as e:
                print(f" [!] An error occurred: {e}")
                break
    except pika.exceptions.AMQPConnectionError as e:
        print(f"[MQ->SERIAL] 无法连接到RabbitMQ: {e}. 线程退出。")
    except Exception as e:
        print(f"[MQ->SERIAL] 发生未知错误: {e}. 线程退出。")
    finally:
        if 'connection' in locals() and connection.is_open:
            connection.close()


# 任务B: 负责从串口读取数据，并发布到 RabbitMQ
def serial_to_mq_worker(serial_port):
    """这个函数在另一个独立的线程中运行"""
    try:
        # 关键：同样，创建自己独立的连接和通道
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=MQ_HOST, port=MQ_PORT, credentials=pika.PlainCredentials(MQ_USER, MQ_PASS)))
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct')

        print(f'[SERIAL->MQ] 线程已启动，正在监听串口 {SERIAL_PORT}...')

        while True:
            if serial_port and serial_port.is_open:
                if (ser.in_waiting > 0):
                    serial_data = serial_port.read(4)
                    if len(serial_data) == 4:
                        channel.basic_publish(
                            exchange=EXCHANGE_NAME,
                            routing_key=ROUTING_KEY_FROM_SERIAL,
                            body=serial_data
                        )
                        print(f"[SERIAL->MQ] 数据 {serial_data} 已作为消息发布到 RabbitMQ")
            else:
                # 如果串口出问题了，可以等待一下再重试
                print("[SERIAL->MQ] 警告: 串口未连接，等待3秒...")
                time.sleep(3)

    except pika.exceptions.AMQPConnectionError as e:
        print(f"[SERIAL->MQ] 无法连接到RabbitMQ: {e}. 线程退出。")
    except serial.SerialException as e:
        print(f"[SERIAL->MQ] 串口错误: {e}. 线程退出。")
    except Exception as e:
        print(f"[SERIAL->MQ] 发生未知错误: {e}. 线程退出。")
    finally:
        if 'connection' in locals() and connection.is_open:
            connection.close()


# --- 3. 主程序入口 ---
if __name__ == "__main__":
    # 初始化串口
    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE)
        print(f"成功打开串口 {SERIAL_PORT}")
    except Exception as e:
        print(f"致命错误: 无法打开串口 {SERIAL_PORT}: {e}")
        sys.exit(1)

    # 创建线程
    mq_consumer_thread = threading.Thread(target=mq_to_serial_worker, args=(ser,))
    serial_reader_thread = threading.Thread(target=serial_to_mq_worker, args=(ser,))

    # 设置为守护线程，这样主线程退出时它们也会被强制结束
    mq_consumer_thread.daemon = True
    serial_reader_thread.daemon = True

    # 启动线程
    mq_consumer_thread.start()
    serial_reader_thread.start()

    print("\n[MAIN] 两个工作线程已启动。程序正在运行...")
    print("[MAIN] 按下 Ctrl+C 退出程序。\n")

    # 主线程在这里保持运行，直到用户按下 Ctrl+C
    try:
        # 保持主线程存活，让守护线程工作
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] 收到 Ctrl+C，正在关闭程序...")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("[MAIN] 串口已关闭。")
        print("[MAIN] 程序退出。")
