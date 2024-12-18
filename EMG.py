#一维数组保存在flattened_data中
import sys
import serial
import threading
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QTextEdit, QLineEdit, QMessageBox
)
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtCore import QSize, QTimer 
import serial.tools.list_ports
import time
from PyQt5.QtChart import QChart, QChartView, QLineSeries

class CircularLight(QWidget):
    def __init__(self):
        super().__init__()
        self.color = QColor(211, 211, 211)  # 默认灰色
        self.setFixedSize(QSize(50, 50))  # 设置固定大小

    def set_color(self, color):
        """设置灯的颜色"""
        self.color = color
        self.update()  # 更新界面以重绘

    def paintEvent(self, event):
        """绘制圆形灯"""
        painter = QPainter(self)
        painter.setBrush(self.color)
        painter.drawEllipse(10, 10, 30, 30)  # 绘制圆形

class SerialPortApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.ser = None
        self.receiver_thread = None
        self.channel_states = [False] * 16  # 用于跟踪每个通道的状态
        self.data_packets = []  # List to hold collected data packets
        self.collect_data = [[], []]


    def initUI(self):
        self.setWindowTitle('串口通信')

        main_layout = QVBoxLayout()
        h_layout = QHBoxLayout()
  
 # 串口选择下拉框
        self.port_combo = QComboBox()
        self.update_ports()
        h_layout.addWidget(QLabel('选择串口:'))
        h_layout.addWidget(self.port_combo)

        self.connection_light = CircularLight()
        h_layout.addWidget(QLabel('USB'))
        h_layout.addWidget(self.connection_light)

        self.data_light = CircularLight()
        h_layout.addWidget(QLabel('BLE:'))
        h_layout.addWidget(self.data_light)
        # 设置间距和边距
        h_layout.setSpacing(20)  # 设置控件之间的间距
        h_layout.setContentsMargins(10, 10, 10, 10)  # 设置布局的边距

        # 打开按钮
        self.open_button = QPushButton('打开串口')
        self.open_button.clicked.connect(self.open_serial)
        h_layout.addWidget(self.open_button)

        # 关闭所有串口按钮
        self.close_all_button = QPushButton('关闭所有串口')
        self.close_all_button.clicked.connect(self.close_all_serials)
        h_layout.addWidget(self.close_all_button)

        # 关闭按钮
        self.close_button = QPushButton('关闭串口')
        self.close_button.clicked.connect(self.close_serial)
        h_layout.addWidget(self.close_button)

         # 测量选择下拉框
        self.measurement_combo = QComboBox()
        self.measurement_combo.addItems(['EEG测量', 'EMG测量', 'ECG测量'])
        h_layout.addWidget(QLabel('选择测量类型:'))
        h_layout.addWidget(self.measurement_combo)

         # 通道按钮
        for i in range(1, 2):
            button = QPushButton(f'Ch{i}')
            button.setCheckable(True)  # 设置为可勾选
            button.clicked.connect(lambda checked, ch=i: self.toggle_channel(ch))
            h_layout.addWidget(button)
        
        # Start/Stop 按钮
        self.start_stop_button = QPushButton('Start')
        self.start_stop_button.clicked.connect(self.toggle_measurement)
        h_layout.addWidget(self.start_stop_button)

        # 将布局应用到主窗口或父控件

        layout = QVBoxLayout()

        # 接收区域
        self.receive_area = QTextEdit()
        self.receive_area.setReadOnly(True)

         # 电池测量显示
        self.battery_label = QLabel('电池测量：')
        layout.addWidget(self.battery_label)

         # 发送区域
        self.send_input = QLineEdit()
        layout.addWidget(QLabel('发送数据 (十六进制，空格分隔):'))
        layout.addWidget(self.send_input)

         # 发送按钮  
        self.send_button = QPushButton('发送数据')
        self.send_button.clicked.connect(self.send_data)
        layout.addWidget(self.send_button)

        #绘制实时图
        self.series = QLineSeries    ()
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.createDefaultAxes()
        self.chart.setTitle("EMG时域图")
        self.chart.legend().setVisible(False)
        self.chart_view = QChartView(self.chart)

        layout.addWidget(self.chart_view)  # 将图表添加到布局中
    
        self.spectrum_series = QLineSeries()  # 新增频谱系列
        self.spectrum_chart = QChart() 
        self.spectrum_chart.addSeries(self.spectrum_series)
        self.spectrum_chart.createDefaultAxes()
        self.spectrum_chart.setTitle("频谱图")
        self.chart.legend().setVisible(False)
        self.spectrum_chart_view = QChartView(self.spectrum_chart)  # 新增频谱视图
        layout.addWidget(self.spectrum_chart_view) 

        main_layout.addLayout(h_layout)
        main_layout.addLayout(layout)
        self.setLayout(main_layout)

    def close_all_serials(self):
       """关闭所有串口并发送特定命令"""
       command = bytes([0x07, 0x00, 0x09, 0x01, 0x02, 0x03, 0x01, 0x01])
       if self.ser and self.ser.is_open:
           threading.Thread(target=self._send_data, args=(command,)).start()
           print("发送关闭所有串口命令")
           QMessageBox.information(self, "信息", "已发送关闭所有串口命令")

    def toggle_channel(self, channel):
       """切换通道状态并发送相应命令"""
       index = channel - 1
       if not (self.ser and self.ser.is_open):
           QMessageBox.warning(self, "警告", "请先打开串口")
           return

       if not self.channel_states[index]:  
           command = bytes([0x07, 0x00, 0x09, 0x01, 0x02, 0x02, 0x01, 0x00])
           threading.Thread(target=self._send_data, args=(command,)).start()
           print(f"已勾选 Ch{channel}")
           self.channel_states[index] = True
       else:  
           command = bytes([0x07, 0x00, 0x09, 0x01, 0x02, 0x04, 0x01, 0x00])
           threading.Thread(target=self._send_data, args=(command,)).start()
           print(f"已取消勾选 Ch{channel}")
           self.channel_states[index] = False
    
    def update_ports(self):
       """更新可用的串口列表"""
       self.port_combo.clear()  
       ports = serial.tools.list_ports.comports()
       for port in ports:
           self.port_combo.addItem(port.device)
    
    def open_serial(self):
       """打开选定的串口"""
       port = self.port_combo.currentText()

       if not port:
           return

       try:
           self.ser = serial.Serial(port, 9600, timeout=1)
           print(f"已连接到 {port}")
           self.receive_area.append(f"已连接到 {port}")
           self.connection_light.set_color(QColor(0, 0, 255))  

           if not self.receiver_thread or not self.receiver_thread.is_alive():
               self.receiver_thread = threading.Thread(target=self.receive_data)
               self.receiver_thread.daemon = True  
               self.receiver_thread.start()

       except serial.SerialException as e:
           print(f"无法打开串口: {e}")
           QMessageBox.critical(self, "错误", f"无法打开串口: {e}")

    def close_serial(self):
       """关闭当前打开的串口"""
       if self.ser and self.ser.is_open:
           try:
               self.ser.close()
               print("串口已关闭")
               self.receive_area.append("串口已关闭")
               self.connection_light.set_color(QColor(211, 211, 211))  
               self.data_light.set_color(QColor(211, 211, 211))  

           except Exception as e:
               print(f"关闭串口时发生错误: {e}")
               QMessageBox.critical(self, "错误", f"关闭串口时发生错误: {e}")
           finally:
               self.ser = None  

    def toggle_measurement(self):
       """切换测量状态"""
       if not (self.ser and self.ser.is_open):
           QMessageBox.warning(self, "警告", "请先打开串口")
           return

       if self.start_stop_button.text() == 'Start':
           # 重置 collect_data 以重新开始计数
           self.collect_data = [[], []]  # 清空数据
           self.data_packets = []  # 清空数据包
           self.series.clear()  # 清空图表数据
           self.chart.axisX().setRange(0, 1)  # 重置X轴范围
           self.chart.axisY().setRange(0, 1)  # 重置Y轴范围
           command = bytes([0x04, 0x00, 0x0A, 0x01, 0x02])
           threading.Thread(target=self._send_data, args=(command,)).start()
           print("开始测量")
           self.start_stop_button.setText('Stop')
       else:
           command = bytes([0x04, 0x00, 0x0B, 0x01, 0x02])
           threading.Thread(target=self._send_data, args=(command,)).start()
           print("停止测量")
           self.start_stop_button.setText('Start')

    def receive_data(self):
       """接收数据的线程函数"""
       while True:
           if (
               self.ser and 
               self.ser.is_open and 
               self.ser.in_waiting > 0
           ):  
               try:
                   data = self.ser.read(self.ser.in_waiting)  
                   hex_data = ' '.join(f'0x{byte:02X}' for byte in data)  
                   # print(f"接收到数据: {hex_data}")
                   self.receive_area.append(f"接收到数据: {hex_data}")

                   if hex_data.startswith("0x08"):
                       values = hex_data.split()
                       if len(values) >= 9:
                           battery_value_hex1 = values[-2]
                           battery_value_hex2 = values[-1]
                           battery_value_dec1 = int(battery_value_hex1, 16)
                           battery_value_dec2 = int(battery_value_hex2, 16)
                           battery_measurement = battery_value_dec1 * 256 + battery_value_dec2
                           print(f"电池测量：{battery_measurement}")
                           self.battery_label.setText(f'电池测量：{battery_measurement}')

                   if hex_data == "0xFF 0x01 0x01":
                       self.data_light.set_color(QColor(0, 255, 0))  
                   elif hex_data == "0xFF 0x01 0x02":
                       self.data_light.set_color(QColor(211, 211, 211))  

                   while len(data) >=201: 
                       packet = data[:201] 
                       data=data[201:]

                       channel_0_voltages =parse_eeg_data(packet)
 
                       if len(channel_0_voltages) <= 48:  # Ensure we have a full packet
                           self.data_packets.extend(channel_0_voltages)
                       else:
                           print("未添加不完整的数据包")
                               # Convert list of lists into a NumPy array
                       data_array = np.array(self.data_packets)
           
                # Flatten the array
                       flattened_data = data_array.flatten()
           
                       num_samples = len(flattened_data)
                       if self.start_stop_button.text() == 'Stop':
                         time_stamps = [i / 125 for i in range(num_samples)]  # 基于125Hz采样率生成时间戳
                       else:
                           time_stamps = [0]*num_samples
        
                       if not hasattr(self, 'collect_data'):
                           self.collect_data = [[], []]  # First row for time_stamps, second for flattened_data
                    
                       if len(flattened_data) > 0:  # 确保有数据可绘制
                        # Append new data to collect_data
                           self.collect_data[0].extend(time_stamps)  # Add new time_stamps
                           self.collect_data[1].extend(flattened_data)  # Add new flattened_data
                           self.save_data_to_excel()
                       #
                        # 更新图表
                       # Keep only the last 700 data points
                       if len(self.collect_data[0]) > 750:
                           self.collect_data[0] = self.collect_data[0][-750:]  # Keep last 700 time_stamps
                           self.collect_data[1] = self.collect_data[1][-750:]  # Keep last 700 flattened_data                       
                           self.series.clear()  # 清空现有数据点
                           
                           for i in range(len(self.collect_data[0])):
                               self.series.append(self.collect_data[0][i], self.collect_data[1][i])  # 添加新的数据点

                                    # 设置X轴和Y轴范围
                               self.chart.axisX().setRange(self.collect_data[0][0], self.collect_data[0][-1])  # 设置X轴范围
                               self.chart.axisY().setRange(min(self.collect_data[1]), max(self.collect_data[1]))  # 设置Y轴范围
                       
                       if len(self.collect_data[1]) > 500:
                           freq_spectrum=np.fft.fft(self.collect_data[1])
                           freq_magnitude=np.abs(freq_spectrum)[:len(freq_spectrum)//2]  
                           freq_bins=np.fft.fftfreq(len(freq_spectrum), d=1/125)[:len(freq_spectrum)//2]  

                           self.spectrum_series.clear()
                           for i in range(len(freq_bins)):
                               if freq_bins[i]>=0: 
                                   self.spectrum_series.append(freq_bins[i], freq_magnitude[i])
                                   self.spectrum_chart.axisX().setRange(0,max(freq_bins))
                                   self.spectrum_chart.axisY().setRange(0,max(freq_magnitude))
                           # 清空旧数据并添加新数据到频谱系列
                           self.spectrum_series.clear()
                           for i in range(len(freq_bins)):
                               if freq_bins[i] >= 0:  # 只绘制正频率部分
                                   self.spectrum_series.append(freq_bins[i], freq_magnitude[i])
                                   self.spectrum_chart.axisX().setRange(0, max(freq_bins))
                                   self.spectrum_chart.axisY().setRange(0, max(freq_magnitude))   
               
               except Exception as e:
                   print(f"接收数据时发生错误: {e}")

    def save_data_to_excel(self):
            """将数据保存到Excel文件"""
            #if not self.collect_data[0]:
            #     QMessageBox.warning(self, "警告", "没有数据可保存")
            #     return
                            # 创建DataFrame，包含时间戳和电压值
            df = pd.DataFrame({
                'Time (s)': self.collect_data[0],
                'Values': self.collect_data[1],
            })
            
        # Save to Excel
            df.to_excel('output.xlsx', index=False)
            print("数据已保存到 output.xlsx")
       
    def send_data(self):
       """发送数据"""
       if not (self.ser and self.ser.is_open):
           QMessageBox.warning(self,"警告","请先打开串口")
           return

       hex_string=self.send_input.text().strip()

       try:
           hex_values=[int(x ,16) for x in hex_string.split()]
          
           threading.Thread(target=self._send_data,args=(hex_values ,)).start()

           sent_hex=' '.join(f'0x{x:02X}' for x in hex_values)
           print(f"准备发送数据:{sent_hex}")

           # 清空输入框
           self.send_input.clear()

       except ValueError:
           print("输入格式错误，请输入有效的十六进制数")
           QMessageBox.warning(
               self,
               "警告",
               "输入格式错误，请输入有效的十六进制数"
           )
        
    def _send_data(self ,hex_values):
      """实际发送数据的函数"""
      try:
          if isinstance(hex_values,list):
              hex_values=bytes(hex_values)
   
          if (self.ser and 
              self.ser.is_open):
              self.ser.write(hex_values)  

              sent_hex=' '.join(f'ox{x:02X}' for x in hex_values)
              print(f"已发送数据:{sent_hex}")
              QApplication.processEvents()  

      except Exception as e:
          print(f"发送数据时发生错误:{e}")
          QMessageBox.critical(
              self,
              "错误",
              f"发送数据时发生错误:{e}"
          )

def parse_eeg_data(data):
    """解析EEG数据并返回通道电压值"""
    relevant_data=data[7:]

    packet_count = int.from_bytes(relevant_data[:2], byteorder='little')  # 反转字节顺序
    # print(f"数据包计数: {packet_count}(十进制),{packet_count:02X}(十六进制)")  # 打印为十进制格式
    
    eeg_samples=relevant_data[2:] 

    samples=np.frombuffer(eeg_samples,dtype=np.float32).reshape(-1 ,1).T 
    
    channel_0_voltages=samples[::2].tolist()  
    
    return channel_0_voltages[:48]

if __name__ == '__main__':
   app=QApplication(sys.argv)
   ex=SerialPortApp ()
   ex.resize(1000 ,800)  
   ex.show()
   sys.exit(app.exec_())



