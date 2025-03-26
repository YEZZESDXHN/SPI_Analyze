import configparser
import csv
import numpy as np

import diskcache
from PyQt5.QtWidgets import QMainWindow
from cantools.database import load_file
from SPI_analyze_UI import Ui_MainWindow


class SPI_Message(object):
    def __init__(self, timestamp, msg_id, raw_data, data_size, decoded_data=None):
        self.timestamp = timestamp
        self.data_size = data_size
        self.msg_id = msg_id
        self.raw_data = raw_data
        self.decoded_data = decoded_data




class SPI_Messages(object):
    def __init__(self):
        self.spi_messages = []

    def add_message(self, timestamp, msg_id, raw_data, data_size, decoded_data=None):
        msg = SPI_Message(timestamp, msg_id, raw_data, data_size, decoded_data)
        self.spi_messages.append(msg)


class spi_csv(object):
    def __init__(self, csv_path, dbc_path, check_ids: list):
        self.db = None
        self.running_timestamp = []  # 记录running时间段
        self.csv_path = csv_path
        self.check_ids = check_ids
        self.spi_messages_dict = {}
        self.init_spi_messages(self.check_ids)
        self.timestamp_column_num = 2  # csv中时间戳列号
        self.data_column_num = 7  # csv中数据列号
        self.dbc_path = dbc_path
        self.load_dbc()

    def init_spi_messages(self, ids):
        """初始化self.spi_messages

        """
        for item in ids:
            self.spi_messages_dict[item] = SPI_Messages()

    def string_to_hex_list(self, hex_string):
        """将十六进制字符串转换为十六进制列表。

        Args:
          hex_string: 包含十六进制值的字符串，以空格分隔。

        Returns:
          一个包含十六进制值的列表，或者如果输入无效则返回 None。
        """
        try:
            hex_list = [int(x, 16) for x in hex_string.split()]
            return hex_list
        except ValueError:
            return None

    def time_to_microseconds(self, time_str):
        """将 m:s.ms.us 格式的时间转换为微秒。"""
        try:
            minutes, rest = time_str.split(":")
            seconds, milliseconds, microseconds = rest.split(".")
            total_microseconds = (int(minutes) * 60 + int(seconds)) * 1000000 + int(milliseconds) * 1000 + int(
                microseconds)
            return total_microseconds
        except ValueError:
            return None

    def load_spi_csv_message_data(self):
        file = open(self.csv_path, 'r')
        data = csv.reader(file)
        multi_frame = {}
        for row in data:
            try:
                raw_csv_data = self.string_to_hex_list(row[self.data_column_num])
                if raw_csv_data is not None:
                    # 获取单帧数据
                    if raw_csv_data[6] == 0 and raw_csv_data[8] in self.check_ids:
                        data_size = raw_csv_data[7]-1
                        spi_data = raw_csv_data[9:9+data_size]
                        timestamp = self.time_to_microseconds(row[self.timestamp_column_num])
                        msg_id = raw_csv_data[8]
                        try:
                            decoded_data = self.decoded_spi_message(msg_id, bytes(spi_data))
                        except Exception as e:
                            decoded_data = None
                            # print(f'decoded_spi_message error:{e}')

                        self.spi_messages_dict[raw_csv_data[8]].add_message(timestamp=timestamp, raw_data=spi_data, data_size=data_size,
                                                                   msg_id=msg_id, decoded_data=decoded_data)

                    # 获取首帧
                    if raw_csv_data[6] == 1 and raw_csv_data[12] in self.check_ids:
                        MSGID = raw_csv_data[7]
                        data_size = raw_csv_data[11]*0x1000000+raw_csv_data[10]*0x10000+raw_csv_data[9]*0x100+raw_csv_data[8]-1
                        timestamp = self.time_to_microseconds(row[self.timestamp_column_num])
                        msg_id = raw_csv_data[12]
                        # log_id = MSGID*0x100+msg_id
                        if MSGID in multi_frame:
                            del multi_frame[MSGID]
                            print(f'multi_frame has log {MSGID},will del it')
                        multi_frame[MSGID] = {"data": SPI_Message(timestamp, msg_id, raw_csv_data[13:], data_size),
                                               "received_size": 128-13,
                                               'msg_id':msg_id}

                    # 获取连续帧
                    if raw_csv_data[6] == 2:
                        MSGID = raw_csv_data[7]
                        if MSGID in multi_frame:
                            #接收完成
                            if multi_frame[MSGID]['data'].data_size <= multi_frame[MSGID]['received_size']+120:
                                multi_frame[MSGID]['data'].raw_data = multi_frame[MSGID]['data'].raw_data + raw_csv_data[8:]
                                multi_frame[MSGID]['data'].raw_data = multi_frame[MSGID]['data'].raw_data[:multi_frame[MSGID]['data'].data_size]

                                try:
                                    decoded_data = self.decoded_spi_message(multi_frame[MSGID]['data'].msg_id, bytes(multi_frame[MSGID]['data'].raw_data))
                                except Exception as e:
                                    decoded_data = None

                                self.spi_messages_dict[multi_frame[MSGID]['data'].msg_id].add_message(timestamp=multi_frame[MSGID]['data'].timestamp,
                                                                                    raw_data=multi_frame[MSGID]['data'].raw_data,
                                                                                    data_size=multi_frame[MSGID]['data'].data_size,
                                                                                    msg_id=multi_frame[MSGID]['data'].msg_id,
                                                                                    decoded_data=decoded_data)
                                del multi_frame[MSGID]
                            else:
                                multi_frame[MSGID]['received_size'] = multi_frame[MSGID]['received_size']+120
                                multi_frame[MSGID]['data'].raw_data = multi_frame[MSGID][
                                                                          'data'].raw_data + raw_csv_data[8:]
                        else:
                            pass
                            # print(f"在这之前没收到首帧,timestamp:{self.time_to_microseconds(row[self.timestamp_column_num])}")

                        # try:
                        #     decoded_data = self.decoded_spi_message(msg_id, bytes(hex))
                        # except Exception as e:
                        #     decoded_data = None
                        # self.spi_messages_dict[hex[12]].add_message(timestamp=timestamp, raw_data=hex, data_size=hex,
                        #                                             msg_id=msg_id, decoded_data=decoded_data)

            except Exception as e:
                # print(e)
                pass

    def decoded_spi_message(self, frame_id, data: bytes):
        decoded_data = self.db.decode_message(frame_id, bytes(data), decode_choices=False)
        return decoded_data

    def get_signal_change(self,msg_id,signal_name:str):
        if msg_id not in self.check_ids:
            print(f'message {hex(msg_id)} is not check,pls add to self.check_ids')
            return
        if len(self.spi_messages_dict[msg_id].spi_messages) == 0:
            print(f'message {hex(msg_id)} is no log')
            return
        signal_value = self.spi_messages_dict[msg_id].spi_messages[0].decoded_data[signal_name]
        print(f"timestamp:{self.spi_messages_dict[msg_id].spi_messages[0].timestamp}\n"
              f"MessageID:{hex(msg_id)}\n"
              f"Signal name:{signal_name}\n"
              f"value:{signal_value}\n"
              f"============================================")
        for message in self.spi_messages_dict[msg_id].spi_messages:
            if message.decoded_data == None:
                print(f'message {hex(msg_id)} 未解析')
                return
            if signal_name not in message.decoded_data:
                print(f'message {hex(msg_id)} 无信号 {signal_name}')
                return

            if message.decoded_data[signal_name] != signal_value:
                signal_value = message.decoded_data[signal_name]
                print(f"timestamp:{message.timestamp}\n"
                      f"MessageID:{hex(msg_id)}\n"
                      f"Signal name:{signal_name}\n"
                      f"value:{signal_value}\n"
                      f"============================================")

    def get_running_timestamp(self):
        timestamp_start = None
        timestamp_stop = None
        msg_id = 0x41
        signal_name = 'APP_Main_State'
        if msg_id not in self.check_ids:
            print(f'message {hex(msg_id)} is not check,pls add to self.check_ids')
            return
        if len(self.spi_messages_dict[msg_id].spi_messages) == 0:
            print(f'message {hex(msg_id)} is no log')
            return
        signal_value = 2  # running
        for message in self.spi_messages_dict[msg_id].spi_messages:
            if message.decoded_data == None:
                print(f'message {hex(msg_id)} 未解析')
                return
            if signal_name not in message.decoded_data:
                print(f'message {hex(msg_id)} 无信号 {signal_name}')
                return

            if message.decoded_data[signal_name] == signal_value:
                if timestamp_start is None:
                    timestamp_start = message.timestamp
            else:
                if timestamp_start is not None:
                    timestamp_stop = message.timestamp
                    self.running_timestamp.append([timestamp_start,timestamp_stop])
                    timestamp_start = None
                    timestamp_stop = None

        if timestamp_start is not None and timestamp_stop is None:
            timestamp_stop = self.spi_messages_dict[msg_id].spi_messages[-1].timestamp
            self.running_timestamp.append([timestamp_start, timestamp_stop])
        # print(self.running_timestamp)


    def check_message_cycle_running(self,msg_id,is_print_error_cycle,cycle_min,cycle_max):
        if len(self.running_timestamp) == 0:
            print("无法获取处于running的时间端")
            return

        if msg_id not in self.check_ids:
            print(f'message {hex(msg_id)} is not check,pls add to self.check_ids')
            return
        if len(self.spi_messages_dict[msg_id].spi_messages) == 0:
            print(f'message {hex(msg_id)} is no log')
            return

        cycle_lists = []
        for timestamp_list in self.running_timestamp:
            cycle_list = []
            timestamp_last = None
            for spi_message in self.spi_messages_dict[msg_id].spi_messages:
                if timestamp_list[0] < spi_message.timestamp < timestamp_list[1]:
                    if timestamp_last is None:
                        # first message
                        timestamp_last = spi_message.timestamp
                    else:
                        cycle = spi_message.timestamp-timestamp_last
                        cycle_list.append(cycle)
                        timestamp_last = spi_message.timestamp
                        if is_print_error_cycle:
                            if cycle < cycle_min or cycle > cycle_max:
                                print(f"cycle error,timestamp:{spi_message.timestamp},cycle:{cycle}")
            cycle_lists.append(cycle_list)

            average = np.mean(cycle_list)
            maximum = np.max(cycle_list)
            minimum = np.min(cycle_list)
            print(f'time {timestamp_list[0]} - {timestamp_list[1]}')
            print(f"平均值: {average} us")
            print(f"最大值: {maximum} us")
            print(f"最小值: {minimum} us")





    def check_signal_value(self,msg_id,signal_name:str,exp_value):
        is_signal_value_correct = True
        if msg_id not in self.check_ids:
            print(f'message {hex(msg_id)} is not check,pls add to self.check_ids')
            return
        if len(self.spi_messages_dict[msg_id].spi_messages) == 0:
            print(f'message {hex(msg_id)} is no log')
            return
        for message in self.spi_messages_dict[msg_id].spi_messages:
            if message.decoded_data == None:
                print(f'message {hex(msg_id)} 未解析')
                return
            if signal_name not in message.decoded_data:
                print(f'message {hex(msg_id)} 无信号 {signal_name}')
                return
            if message.decoded_data[signal_name] != exp_value:
                is_signal_value_correct=False
                print(f"信号异常：\n"
                      f"MessageID:{hex(msg_id)}\n"
                      f"timestamp:{message.timestamp}\n"
                      f"signal_name:{signal_name}\n"
                      f"actual value:{message.decoded_data[signal_name]},exp value:{exp_value}\n"
                      f"============================================")
        if is_signal_value_correct:
            print(f"signal {signal_name} value is correct\n"
                  f"MessageID:{hex(msg_id)}\n"
                  f"value:{message.decoded_data[signal_name]}\n"
                  f"check messages num {len(self.spi_messages_dict[msg_id].spi_messages)}\n"
                  f"============================================")


    def load_dbc(self):
        try:
            self.db = load_file(filename=self.dbc_path, cache_dir='./dbc_cache')
        except Exception as e:
            print(e)




def initialize_cache(cache_dir='./dbc_cache'):
    """正确初始化缓存目录"""

    # 初始化缓存
    with diskcache.Cache(cache_dir) as cache:
        # 写入测试数据确保缓存正常工作
        cache.set("test_key", "test_value")

        # 验证缓存工作正常
        if cache.get("test_key") == "test_value":
            print("Cache initialized successfully")
            return True
    return False


class MainWindows(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.csv_path = None
        self.dbc_path = None
        self.check_ids = None
        self.spi_csv_data = None
        self.check_signal_value_list = []
        self.get_signal_change_list = []
        self.check_message_cycle_running_list = []



def load_config(filename):
    """
    Loads configuration from an INI file and returns the configuration data.

    Args:
        filename (str): The name of the INI file to load.

    Returns:
        dict: A dictionary containing the configuration data, where keys are section names
              and values are lists of tuples representing the configuration values.
    """
    config = configparser.ConfigParser(allow_no_value=True)
    config.read(filename)

    config_data = {}
    for section in config.sections():
        config_data[section] = []
        for value in config[section]:
            if value is not None:
                config_data[section].append(tuple(value.split(', ')))

    return config_data

if __name__ == "__main__":
    # config = load_config('config.ini')
    # check_ids = []
    # for _id in config['check_ids'][0]:
    #     check_ids.append(int(_id, 16))
    # print(check_ids)

    # initialize_cache(cache_dir='./dbc_cache')
    eyeq_spi = spi_csv(csv_path="C:/Workspace/EyeQ_data/EQ_VISION.csv",
                       dbc_path='Core_Application_Message_protocol.dbc',
                       check_ids=[0x41, 0x63, 0x6a, 0x6b, 0x5a, 0xd8, 0xd2, 0xa2])
    eyeq_spi.load_spi_csv_message_data()

    # eyeq_spi.check_signal_value(msg_id=0x41, signal_name='APP_Main_State', exp_value=2)
    # eyeq_spi.get_signal_change(msg_id=0x41, signal_name='APP_Main_State')
    eyeq_spi.get_running_timestamp()
    eyeq_spi.check_message_cycle_running(msg_id=0x41,is_print_error_cycle=True,cycle_min=10000,cycle_max=40000)