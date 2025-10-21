import pika
import serial
import threading
import time
import sys
import os
import logging

# 日志服务
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# RabbitMQ 配置
MQ_HOST = os.getenv('MQ_HOST', 'rabbitmq-service')
MQ_PORT = int(os.getenv('MQ_PORT', 5672))
MQ_USER = os.getenv('RABBITMQ_DEFAULT_USER', 'user')
MQ_PASS = os.getenv('RABBITMQ_DEFAULT_PASS', 'password')

# RabbitMQ 连接参数优化
HEARTBEAT_INTERVAL = 300  # 心跳间隔（秒），减少到5分钟
CONNECTION_ATTEMPTS = 3   # 连接重试次数
RETRY_DELAY = 3          # 连接重试延迟（秒）

EXCHANGE_NAME = 'aio_exchange'
TO_SERIAL_ROUTING_KEY = 'to_serial_routing_key'
TO_SERIAL_QUEUE = 'to_serial_queue' 

FROM_SERIAL_ROUTING_KEY = 'from_serial_routing_key'
FROM_SERIAL_QUEUE = 'from_serial_queue' 

# 串口配置
SERIAL_PORT = "/dev/ttyMCU"  # 根据你的实际情况修改，Windows上可能是 "COM3"
SERIAL_BAUDRATE = 115200

# 工作线程函数

# 任务A: 负责从 RabbitMQ 消费消息，并写入串口
def mq_to_serial_worker(serial_port):
    """这个函数在一个独立的线程中运行"""
    retry_interval = 5
    
    # 外层循环：负责连接重试
    while True:
        connection = None
        channel = None
        
        try:
            # 连接建立重试循环
            while True:
                try:
                    logger.info(f"[MQ->SERIAL] 正在尝试连接到 RabbitMQ at {MQ_HOST}:{MQ_PORT}...")
                    connection = pika.BlockingConnection(pika.ConnectionParameters(
                        host=MQ_HOST, 
                        port=MQ_PORT, 
                        credentials=pika.PlainCredentials(MQ_USER, MQ_PASS), 
                        retry_delay=RETRY_DELAY, 
                        heartbeat=HEARTBEAT_INTERVAL
                    ))
                    channel = connection.channel()

                    # 声明，确保存在
                    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct', durable=True)
                    from_queue_args = {
                        # 'x-message-ttl': 10000,
                        # 'x-max-length': 100,
                        # 'x-overflow': 'drop-head'
                    }
                    channel.queue_declare(queue=TO_SERIAL_QUEUE, durable=True, arguments=from_queue_args)
                    channel.queue_bind(queue=TO_SERIAL_QUEUE, exchange=EXCHANGE_NAME, routing_key=TO_SERIAL_ROUTING_KEY)

                    logger.info("✅ [MQ->SERIAL] RabbitMQ 连接成功并完成设置!")
                    break
                except pika.exceptions.AMQPConnectionError as e:
                    logger.error(f"[MQ->SERIAL] RabbitMQ 连接失败: {e}. 将在 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)

            logger.info(f'[MQ->SERIAL] 线程已启动，等待来自 {TO_SERIAL_QUEUE} 的消息...')

            # 内层循环：持续轮询消息
            while True:
                try:
                    # 尝试从队列中获取单条消息
                    # auto_ack=False 表示我们需要手动确认消息
                    method_frame, properties, body = channel.basic_get(queue=TO_SERIAL_QUEUE, auto_ack=False)

                    # 检查是否真的收到了消息
                    if method_frame:
                        if serial_port and serial_port.is_open:
                            logger.info(f"[MQ->SERIAL] ✓ 消息 {body} 写到串口")
                            serial_port.write(body)

                            # 关闭示波器或万用表的时候，需要清除掉缓存区的内容
                            if (body == bytes([0x07, 0x00, 0x00, 0xFE]) or body == bytes([0x01, 0x00, 0x00, 0xFE])):
                                serial_port.read_all()

                        # 手动确认消息，告诉 RabbitMQ 这条消息处理完了，可以删除了
                        channel.basic_ack(method_frame.delivery_tag)
                    
                    # 无论有没有消费到消息，都等待1秒
                    time.sleep(1)
                    
                except KeyboardInterrupt:
                    logger.info("[MQ->SERIAL] 收到用户中断信号，退出线程")
                    return
                except (pika.exceptions.ConnectionClosedByBroker,
                        pika.exceptions.AMQPConnectionError,
                        pika.exceptions.StreamLostError) as e:
                    logger.error(f"[MQ->SERIAL] RabbitMQ 连接断开: {e}. 将尝试重新连接...")
                    break  # 跳出内层循环，重新建立连接
                except Exception as e:
                    logger.error(f"[MQ->SERIAL] 发生错误: {e}. 将尝试重新连接...")
                    os._exit(1)
                    break  # 跳出内层循环，重新建立连接

        except Exception as e:
            logger.error(f"[MQ->SERIAL] 发生未知错误: {e}. 等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
        finally:
            # 清理连接资源
            if connection and connection.is_open:
                try:
                    connection.close()
                    logger.info("[MQ->SERIAL] RabbitMQ 连接已关闭")
                except Exception as e:
                    logger.error(f"[MQ->SERIAL] 关闭连接时出错: {e}")
        
        # 在重新尝试连接前等待一段时间
        logger.info(f"[MQ->SERIAL] 将在 {retry_interval} 秒后重新尝试连接...")
        time.sleep(retry_interval)


# 任务B: 负责从串口读取数据，并发布到 RabbitMQ
def serial_to_mq_worker(serial_port):
    """这个函数在另一个独立的线程中运行"""
    retry_interval = 5
    
    # 外层循环：负责连接重试
    while True:
        connection = None
        channel = None
        
        try:
            # 连接建立重试循环
            while True:
                try:
                    logger.info(f"[SERIAL->MQ] 正在尝试连接到 RabbitMQ at {MQ_HOST}:{MQ_PORT}...")
                    connection = pika.BlockingConnection(pika.ConnectionParameters(
                        host=MQ_HOST, 
                        port=MQ_PORT, 
                        credentials=pika.PlainCredentials(MQ_USER, MQ_PASS), 
                        retry_delay=RETRY_DELAY, 
                        heartbeat=HEARTBEAT_INTERVAL
                    ))
                    channel = connection.channel()

                    # 声明，确保存在
                    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct', durable=True)
                    # 为from_serial_queue设置队列长度限制和丢弃策略
                    from_queue_args = {
                        'x-max-length': 50,      # 队列最大长度50条消息
                        'x-overflow': 'drop-head' # 当队列满时丢弃队头的旧消息
                    }
                    channel.queue_declare(queue=FROM_SERIAL_QUEUE, durable=True, arguments=from_queue_args)
                    channel.queue_bind(queue=FROM_SERIAL_QUEUE, exchange=EXCHANGE_NAME, routing_key=FROM_SERIAL_ROUTING_KEY)

                    logger.info("✅ [SERIAL->MQ] RabbitMQ 连接成功并完成设置!")
                    break
                except pika.exceptions.AMQPConnectionError as e:
                    logger.error(f"[SERIAL->MQ] RabbitMQ 连接失败: {e}. 将在 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)

            logger.info(f'[SERIAL->MQ] 线程已启动，正在监听串口 {SERIAL_PORT}...')

            # 内层循环：数据处理
            while True:
                try:
                    if serial_port and serial_port.is_open:
                        if (serial_port.in_waiting > 0):
                            serial_data = serial_port.read(4)
                            if len(serial_data) == 4:
                                channel.basic_publish(
                                    exchange=EXCHANGE_NAME,
                                    routing_key=FROM_SERIAL_ROUTING_KEY,
                                    body=serial_data
                                )
                                logger.info(f"[SERIAL->MQ] 数据 {serial_data} 已作为消息发布到 RabbitMQ")
                    else:
                        # 如果串口出问题了，可以等待一下再重试
                        logger.warning("[SERIAL->MQ] 警告: 串口未连接，等待3秒...")
                        time.sleep(3)
                    
                    # 短暂休眠避免过度占用CPU
                    time.sleep(0.1)
                    
                except KeyboardInterrupt:
                    logger.info("[SERIAL->MQ] 收到用户中断信号，退出线程")
                    return
                except (pika.exceptions.ConnectionClosedByBroker, 
                        pika.exceptions.AMQPConnectionError,
                        pika.exceptions.StreamLostError) as e:
                    logger.error(f"[SERIAL->MQ] RabbitMQ 连接断开: {e}. 将尝试重新连接...")
                    break  # 跳出内层循环，重新建立连接
                except Exception as e:
                    logger.error(f"[SERIAL->MQ] 发生错误: {e}. 将尝试重新连接...")
                    break  # 跳出内层循环，重新建立连接
                    
        except serial.SerialException as e:
            logger.error(f"[SERIAL->MQ] 串口错误: {e}. 等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
        except Exception as e:
            logger.error(f"[SERIAL->MQ] 发生未知错误: {e}. 等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
        finally:
            # 清理连接资源
            if connection and connection.is_open:
                try:
                    connection.close()
                    logger.info("[SERIAL->MQ] RabbitMQ 连接已关闭")
                except Exception as e:
                    logger.error(f"[SERIAL->MQ] 关闭连接时出错: {e}")
        
        # 在重新尝试连接前等待一段时间
        logger.info(f"[SERIAL->MQ] 将在 {retry_interval} 秒后重新尝试连接...")
        time.sleep(retry_interval)


# 主程序入口
if __name__ == "__main__":
    # 初始化串口
    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE)
        logger.info(f"成功打开串口 {SERIAL_PORT}")
    except Exception as e:
        logger.error(f"致命错误: 无法打开串口 {SERIAL_PORT}: {e}")
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

    logger.info("\n[MAIN] 两个工作线程已启动。程序正在运行...")
    logger.info("[MAIN] 按下 Ctrl+C 退出程序。\n")

    # 主线程在这里保持运行，直到用户按下 Ctrl+C
    try:
        # 保持主线程存活，让守护线程工作
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n[MAIN] 收到 Ctrl+C，正在关闭程序...")
    finally:
        if ser and ser.is_open:
            ser.close()
            logger.info("[MAIN] 串口已关闭。")
        logger.info("[MAIN] 程序退出。")
