/**
 * 设备状态同步模块
 * 用于在页面加载时同步后端设备状态到前端UI
 */

class DeviceStateSync {
    constructor() {
        this.apiBase = '';
        this.websocket = null;
        this.deviceState = null;
        this.retryCount = 0;
        this.maxRetries = 5;
        
        console.log('设备状态同步模块已初始化');
    }

    /**
     * 初始化状态同步
     */
    async init() {
        try {
            // 等待页面DOM加载完成
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.startSync());
            } else {
                this.startSync();
            }
        } catch (error) {
            console.error('初始化设备状态同步失败:', error);
        }
    }

    /**
     * 开始状态同步
     */
    async startSync() {
        console.log('开始设备状态同步...');
        
        try {
            // 获取初始状态
            await this.fetchInitialState();
            
            // 应用状态到UI
            this.applyStateToUI();
            
            // 监听WebSocket消息
            this.setupWebSocketListener();
            
        } catch (error) {
            console.error('状态同步过程中发生错误:', error);
            this.retrySync();
        }
    }

    /**
     * 获取初始状态
     */
    async fetchInitialState() {
        try {
            const response = await fetch('/api/init_ui_state');
            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status}`);
            }
            
            const data = await response.json();
            this.deviceState = data.device_status;
            
            console.log('获取到设备状态:', this.deviceState);
            
        } catch (error) {
            console.error('获取初始状态失败:', error);
            throw error;
        }
    }

    /**
     * 应用状态到UI
     */
    applyStateToUI() {
        if (!this.deviceState || !this.deviceState.ui_state) {
            console.log('没有有效的设备状态，跳过UI更新');
            return;
        }

        const uiState = this.deviceState.ui_state;
        
        try {
            // 更新示波器按钮状态
            this.updateOscilloscopeButton(uiState.oscilloscope_button);
            
            // 更新万用表按钮状态
            this.updateMultimeterButtons(uiState.multimeter_buttons);
            
            console.log('UI状态已更新');
            
        } catch (error) {
            console.error('应用UI状态时发生错误:', error);
        }
    }

    /**
     * 更新示波器按钮状态
     */
    updateOscilloscopeButton(state) {
        const selectors = [
            'button[onclick*="open_occ"]',
            'button[onclick*="oscilloscope"]',
            '.oscilloscope-button',
            '[data-device="oscilloscope"]'
        ];

        for (const selector of selectors) {
            const buttons = document.querySelectorAll(selector);
            buttons.forEach(button => {
                this.updateButtonState(button, state, '示波器');
            });
        }
    }

    /**
     * 更新万用表按钮状态
     */
    updateMultimeterButtons(states) {
        const deviceMap = {
            resistance: ['resistance', 'resistense', '电阻'],
            continuity: ['continuity', 'cont', '通断'],
            dc_voltage: ['dc_voltage', 'dcv', '直流电压'],
            ac_voltage: ['ac_voltage', 'acv', '交流电压'],
            dc_current: ['dc_current', 'dca', '直流电流']
        };

        Object.entries(states).forEach(([deviceType, state]) => {
            const keywords = deviceMap[deviceType] || [deviceType];
            
            keywords.forEach(keyword => {
                const selectors = [
                    `button[onclick*="${keyword}"]`,
                    `[data-device="${keyword}"]`,
                    `.${keyword}-button`
                ];

                selectors.forEach(selector => {
                    const buttons = document.querySelectorAll(selector);
                    buttons.forEach(button => {
                        this.updateButtonState(button, state, `万用表-${deviceType}`);
                    });
                });
            });
        });
    }

    /**
     * 更新单个按钮状态
     */
    updateButtonState(button, state, deviceName) {
        if (!button) return;

        try {
            // 根据状态更新按钮样式和文本
            if (state === 'opened') {
                button.classList.add('active', 'opened');
                button.classList.remove('closed');
                
                // 尝试更新按钮文本
                if (button.textContent.includes('打开') || button.textContent.includes('开启')) {
                    button.textContent = button.textContent.replace(/打开|开启/, '关闭');
                }
                
                console.log(`已更新${deviceName}按钮为开启状态`);
                
            } else if (state === 'closed') {
                button.classList.add('closed');
                button.classList.remove('active', 'opened');
                
                // 尝试更新按钮文本
                if (button.textContent.includes('关闭')) {
                    button.textContent = button.textContent.replace('关闭', '打开');
                }
                
                console.log(`已更新${deviceName}按钮为关闭状态`);
            }
            
        } catch (error) {
            console.error(`更新${deviceName}按钮状态时发生错误:`, error);
        }
    }

    /**
     * 设置WebSocket监听器
     */
    setupWebSocketListener() {
        // 监听现有WebSocket连接的消息
        const originalWebSocket = window.WebSocket;
        const self = this;
        
        window.WebSocket = function(url, protocols) {
            const ws = new originalWebSocket(url, protocols);
            
            // 监听状态同步消息
            ws.addEventListener('message', function(event) {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'state_sync') {
                        console.log('收到状态同步消息:', data);
                        self.handleStateSyncMessage(data);
                    }
                } catch (e) {
                    // 如果不是JSON或不是状态同步消息，忽略
                }
            });
            
            return ws;
        };
    }

    /**
     * 处理状态同步消息
     */
    handleStateSyncMessage(data) {
        console.log('📡 收到状态同步消息:', data);
        
        if (data.device === 'oscilloscope' || data.device_type === 'oscilloscope') {
            this.updateOscilloscopeButton(data.state || data.device_state);
        } else if (data.device === 'multimeter') {
            const states = {
                resistance: 'closed',
                continuity: 'closed',
                dc_voltage: 'closed',
                ac_voltage: 'closed',
                dc_current: 'closed'
            };
            if (data.subtype) {
                states[data.subtype] = data.state;
            }
            this.updateMultimeterButtons(states);
        }
    }

    /**
     * 重试同步
     */
    retrySync() {
        if (this.retryCount < this.maxRetries) {
            this.retryCount++;
            console.log(`状态同步重试 (${this.retryCount}/${this.maxRetries})`);
            
            setTimeout(() => {
                this.startSync();
            }, 2000 * this.retryCount);
        } else {
            console.error('状态同步重试次数已达上限，放弃同步');
        }
    }
}

// 创建全局实例
const deviceStateSync = new DeviceStateSync();

// 页面加载时自动初始化
deviceStateSync.init();

// 导出到全局
window.DeviceStateSync = DeviceStateSync;
window.deviceStateSync = deviceStateSync; 