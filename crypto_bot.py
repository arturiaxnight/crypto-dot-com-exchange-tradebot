import os
import time
import hmac
import hashlib
import json
import requests
from dotenv import load_dotenv
from termcolor import colored
import numpy as np
from datetime import datetime
from colorama import init, Fore, Back, Style
import platform

# 初始化 colorama
init()

# 載入環境變數
load_dotenv()
api_key = os.getenv('CRYPTO_API_KEY')
api_secret = os.getenv('CRYPTO_API_SECRET')

def get_signature(request_data):
    """生成 API 請求所需的簽名"""
    params = request_data.get("params", {})
    if not params:
        params_str = ""
    else:
        sorted_params = sorted(params.items())
        params_str = ''.join(f"{key}{params[key]}" for key in sorted(params))
    
    sig_str = ''.join([
        request_data["method"],
        str(request_data["id"]),
        request_data["api_key"],
        params_str,
        str(request_data["nonce"])
    ])
    
    return hmac.new(
        bytes(api_secret, 'utf-8'),
        msg=bytes(sig_str, 'utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()

def get_current_price(instrument_name="CRO_USDT"):
    """獲取當前市場價格"""
    url = "https://api.crypto.com/exchange/v1/public/get-tickers"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') == 0:
            # 在所有交易對中找到 CRO_USDT
            tickers = data['result']['data']
            for ticker in tickers:
                if ticker['i'] == instrument_name:  # 'i' 是 instrument_name 的縮寫
                    print(f"找到交易對: {instrument_name}")
                    print(f"最新價格: {ticker['a']}")  # 'a' 是最新價格
                    return float(ticker['a'])
            
            print(f"未找到交易對: {instrument_name}")
            # 打印所有可用的交易對，方便調試
            print("可用的交易對:")
            for ticker in tickers[:10]:  # 只打印前10個，避免太多
                print(f"- {ticker['i']}")
            return None
        else:
            print(f"獲取價格錯誤: {data.get('message', '未知錯誤')}")
            return None
            
    except Exception as e:
        print(f"獲取價格時發生錯誤: {e}")
        print(f"完整錯誤信息: {str(e)}")
        return None

def clear_terminal():
    """清除終端機畫面"""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")
    
    # 如果上面的方法失敗，使用這個備用方法
    print('\033[H\033[J', end='')

class GridBot:
    def __init__(self, instrument_name="CRO_USDT", grid_num=1000, price_margin=0.1, investment_amount=500):
        self.instrument_name = instrument_name
        self.grid_num = grid_num
        self.price_margin = price_margin
        self.investment_amount = investment_amount
        self.current_price = None
        self.grid_prices = []
        self.orders = {}
        self.position = 0
        self.usdt_balance = investment_amount
        self.total_profit = 0
        self.trades = []
        self.grid_profit = 0
        # 新增手續費相關變數
        self.maker_fee = 0.0000  # 0%
        self.taker_fee = 0.0004  # 0.04%
        self.total_fee = 0  # 累計手續費
        self.log_file = "trade_history.log"  # 添加日誌文件路徑
        
    def calculate_grid_profit(self):
        """計算單格利潤"""
        if len(self.grid_prices) < 2:
            return 0
        grid_interval = self.grid_prices[1] - self.grid_prices[0]
        self.grid_profit = (grid_interval / self.grid_prices[0]) * 100  # 轉換為百分比
        return self.grid_profit
        
    def calculate_position_value(self, price):
        """計算持倉市值"""
        return self.position * price + self.usdt_balance
    
    def setup_grids(self):
        """設置網格價格"""
        self.current_price = get_current_price(self.instrument_name)
        if not self.current_price:
            return False
            
        price_low = self.current_price * (1 - self.price_margin)
        price_high = self.current_price * (1 + self.price_margin)
        
        # 計算單筆交易的總手續費率
        total_fee_rate = (self.maker_fee + self.taker_fee) * 100  # 轉換為百分比
        
        # 計算在當前價格範圍內，能夠保證利潤大於手續費的最大網格數
        price_range = price_high - price_low
        min_grid_profit = total_fee_rate / 100  # 最小需要的利潤率（轉回小數）
        max_grid_num = int(price_range / (self.current_price * min_grid_profit))
        
        print(f"\n=== 網格參數分析 ===")
        print(f"當前價格: {colored(self.current_price, 'yellow')} USDT")
        print(f"價格範圍: {colored(price_low, 'red')} - {colored(price_high, 'green')} USDT")
        print(f"總價格範圍: {price_range:.6f} USDT")
        print(f"總手續費率: {colored(f'{total_fee_rate:.4f}%', 'red')}")
        print(f"建議最大網格數: {colored(str(max_grid_num), 'cyan')}")
        print(f"當前設置網格數: {colored(str(self.grid_num), 'yellow')}")
        
        # 創建網格
        self.grid_prices = np.linspace(price_low, price_high, self.grid_num)
        
        # 計算當前設置的單格利潤
        grid_profit = self.calculate_grid_profit()
        
        print(f"\n=== 利潤分析 ===")
        print(f"單格利潤: {colored(f'{grid_profit:.4f}%', 'cyan')}")
        print(f"總手續費率: {colored(f'{total_fee_rate:.4f}%', 'red')}")
        
        # 檢查利潤是否足夠支付手續費
        if grid_profit <= total_fee_rate:
            print(colored("\n警告: 單格利潤小於等於總手續費率！", 'red'))
            print(colored("建議調整網格參數以增加單格利潤", 'red'))
            print(colored(f"1. 建議將網格數量設置在 {max_grid_num} 以下", 'yellow'))
            print(colored(f"2. 當前網格數 {self.grid_num} 過多", 'yellow'))
            print(colored("3. 或者增加價格範圍（當前±10%）", 'yellow'))
            
            confirm = input("\n是否仍要繼續？(y/n): ")
            if confirm.lower() != 'y':
                print("已取消網格交易")
                return False
            print("\n已確認繼續運行，請注意風險")
        else:
            print(colored(f"單格淨利潤: {grid_profit - total_fee_rate:.4f}%", 'green'))
            if self.grid_num > max_grid_num:
                print(colored(f"\n提示: 當前網格數({self.grid_num})超過建議值({max_grid_num})", 'yellow'))
                print(colored("雖然仍有利潤，但建議適當減少網格數以提高每筆交易的利潤", 'yellow'))
            
        return True
        
    def log_trade(self, trade_info):
        """記錄交易到日誌文件"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = (
            f"時間: {timestamp}\n"
            f"類型: {trade_info['type']}\n"
            f"價格: {trade_info['price']:.6f} USDT\n"
            f"數量: {trade_info['amount']:.6f} CRO\n"
            f"金額: {trade_info['value']:.2f} USDT\n"
            f"手續費: {trade_info['fee']:.6f} USDT\n"
            f"當前持倉: {self.position:.6f} CRO\n"
            f"USDT 餘額: {self.usdt_balance:.2f} USDT\n"
            f"累計利潤: {self.total_profit:.2f} USDT\n"
            f"{'-' * 50}\n"
        )
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
    def simulate_trade(self, price, is_buy):
        """模擬交易"""
        trade_amount = self.investment_amount / self.grid_num  # 每格交易金額
        
        # 計算手續費（使用 taker 費率，因為是市價單）
        fee = trade_amount * self.taker_fee
        
        if is_buy:
            # 買入時，實際獲得的 CRO 數量需要扣除手續費
            cro_amount = (trade_amount - fee) / price
            self.position += cro_amount
            self.usdt_balance -= trade_amount
            trade_type = "買入"
            color = "red"
            self.total_fee += fee
        else:
            # 賣出時，檢查是否有足夠的 CRO 可賣
            cro_amount = trade_amount / price
            if self.position < cro_amount:  # 如果持倉不足
                print(colored("錯誤：持倉不足，無法賣出", 'red'))
                return False
                
            self.position -= cro_amount
            self.usdt_balance += (trade_amount - fee)
            trade_type = "賣出"
            color = "green"
            self.total_fee += fee
        
        # 記錄交易
        trade_info = {
            "type": trade_type,
            "price": price,
            "amount": cro_amount,
            "value": trade_amount,
            "fee": fee,
            "timestamp": time.time()
        }
        self.trades.append(trade_info)
        
        # 記錄到日誌文件
        self.log_trade(trade_info)
        
        # 計算當前總資產價值
        total_value = self.calculate_position_value(price)
        # 計算當前總利潤
        self.total_profit = self.usdt_balance - self.investment_amount
        
        print(colored(f"{trade_type} CRO:", color))
        print(colored(f"價格: {price:.6f} USDT", color))
        print(colored(f"數量: {cro_amount:.6f} CRO", color))
        print(colored(f"金額: {trade_amount:.2f} USDT", color))
        print(colored(f"手續費: {fee:.6f} USDT", 'yellow'))
        print(f"當前持倉: {self.position:.6f} CRO")
        print(f"USDT 餘額: {self.usdt_balance:.2f} USDT")
        print(f"總資產價值: {total_value:.2f} USDT")
        print(f"累計手續費: {colored(f'{self.total_fee:.6f} USDT', 'red')}")
        print(f"累計利潤: {colored(f'{self.total_profit:.2f} USDT', 'yellow')}")
        
        return True

    def close_position(self, current_price):
        """平倉：將所有 CRO 轉換為 USDT"""
        if self.position > 0:
            usdt_value = self.position * current_price
            # 計算平倉手續費
            fee = usdt_value * self.taker_fee
            self.total_fee += fee
            
            print("\n=== 平倉操作 ===")
            print(colored(f"賣出全部 CRO 持倉", 'green'))
            print(f"賣出數量: {self.position:.6f} CRO")
            print(f"賣出價格: {current_price:.6f} USDT")
            print(f"獲得金額: {usdt_value:.2f} USDT")
            print(colored(f"平倉手續費: {fee:.6f} USDT", 'yellow'))
            
            # 更新餘額（扣除手續費）
            self.usdt_balance += (usdt_value - fee)
            self.position = 0
            
            # 更新總利潤
            self.total_profit = self.usdt_balance - self.investment_amount
            
            # 記錄交易
            trade_info = {
                "type": "平倉賣出",
                "price": current_price,
                "amount": self.position,
                "value": usdt_value,
                "fee": fee,
                "timestamp": time.time()
            }
            self.trades.append(trade_info)
            
            # 記錄到日誌文件
            self.log_trade(trade_info)

    def initial_grid_setup(self, current_price, upper_grid_percentage=0.3):
        """初始化網格倉位"""
        print("\n=== 初始化網格倉位 ===")
        
        # 找到當前價格在網格中的位置
        current_grid_index = np.searchsorted(self.grid_prices, current_price)
        
        # 計算要購買的上方網格數量
        total_upper_grids = len(self.grid_prices) - current_grid_index
        grids_to_buy = int(total_upper_grids * upper_grid_percentage)
        
        # 計算每格需要的資金
        per_grid_investment = self.investment_amount / self.grid_num
        total_investment_needed = grids_to_buy * per_grid_investment
        
        print(f"當前價格: {colored(current_price, 'yellow')} USDT")
        print(f"計劃購買上方網格數量: {grids_to_buy}")
        print(f"預計投入資金: {colored(f'{total_investment_needed:.2f}', 'yellow')} USDT")
        
        confirm = input("\n這個操作將會使用大約 30% 的資金購買上方網格倉位，是否繼續？(y/n): ")
        if confirm.lower() != 'y':
            print("取消初始化網格倉位")
            return
        
        # 執行購買
        for i in range(grids_to_buy):
            grid_price = self.grid_prices[current_grid_index + i]
            self.simulate_trade(grid_price, True)
            time.sleep(0.1)  # 避免打印太快
        
        print("\n初始化網格倉位完成")
        print(f"已購買 {grids_to_buy} 個網格的倉位")
        print(f"剩餘 USDT: {self.usdt_balance:.2f}")
        input("按 Enter 繼續...")

    def simulate_trading(self):
        """模擬網格交易"""
        if not self.setup_grids():
            return
            
        print("\n開始模擬網格交易...")
        print("按 Ctrl+C 停止交易")
        
        last_grid_index = None
        is_first_trade = True
        
        try:
            while True:
                clear_terminal()
                
                current_price = get_current_price(self.instrument_name)
                if not current_price:
                    time.sleep(5)
                    continue
                
                # 顯示基本信息
                print(f"\n=== 網格交易運行中 ===")
                print(f"目前執行網格區間為: {colored(f'{self.grid_prices[0]:.6f}', 'red')} - {colored(f'{self.grid_prices[-1]:.6f}', 'green')} USDT")
                print(f"當前時間: {datetime.now().strftime('%H:%M:%S')}")
                print(f"當前市價: {colored(current_price, 'yellow')} USDT")
                
                # 找到當前價格所在的網格位置
                grid_index = np.searchsorted(self.grid_prices, current_price)
                
                # 顯示當前網格的買賣單
                if grid_index > 0:  # 買單
                    buy_price = self.grid_prices[grid_index - 1]
                    print(colored(f"買單價格: {buy_price:.6f} USDT", 'red'))
                    
                if grid_index < len(self.grid_prices) - 1 and not is_first_trade:  # 賣單
                    sell_price = self.grid_prices[grid_index + 1]
                    print(colored(f"賣單價格: {sell_price:.6f} USDT", 'green'))
                
                # 如果價格跨越了網格，執行交易
                if last_grid_index is not None and grid_index != last_grid_index:
                    if is_first_trade:
                        # 第一筆交易只允許買入
                        if grid_index < last_grid_index:  # 價格下跌，執行買入
                            if self.simulate_trade(current_price, True):
                                is_first_trade = False  # 第一筆買入完成
                                print(colored("首次買入完成，開始正常網格交易", 'yellow'))
                    else:
                        # 正常網格交易
                        if grid_index > last_grid_index and self.position > 0:
                            # 價格上漲，賣出
                            self.simulate_trade(current_price, False)
                        elif grid_index < last_grid_index:
                            # 價格下跌，買入
                            self.simulate_trade(current_price, True)
                
                last_grid_index = grid_index
                
                # 顯示當前狀態
                print(f"\n=== 帳戶狀態 ===")
                print(f"當前持倉: {self.position:.6f} CRO")
                print(f"USDT 餘額: {self.usdt_balance:.2f} USDT")
                print(f"總資產價值: {self.calculate_position_value(current_price):.2f} USDT")
                print(f"累計手續費: {colored(f'{self.total_fee:.6f} USDT', 'red')}")
                print(f"累計利潤(含手續費): {colored(f'{self.total_profit:.2f} USDT', 'yellow')}")
                
                if is_first_trade:
                    print(colored("\n等待首次買入機會...", 'yellow'))
                print(f"\n交易記錄保存在: {self.log_file}")
                print("-" * 50)
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            # 平倉操作
            self.close_position(current_price)
            
            # 計算最終利潤
            final_profit = self.usdt_balance - self.investment_amount
            profit_percentage = (final_profit / self.investment_amount) * 100
            
            print("\n=== 交易統計 ===")
            print(f"總交易次數: {len(self.trades)}")
            print(f"最終持倉: {self.position:.6f} CRO")
            print(f"USDT 餘額: {self.usdt_balance:.2f} USDT")
            print(f"總資產價值: {self.calculate_position_value(current_price):.2f} USDT")
            print(f"總手續費: {colored(f'{self.total_fee:.6f} USDT', 'red')}")
            print(f"總利潤(含手續費): {colored(f'{final_profit:.2f} USDT', 'yellow')}")
            print(f"收益率: {colored(f'{profit_percentage:.2f}%', 'yellow')}")
            print("\n停止交易")

if __name__ == "__main__":
    # 創建並運行網格機器人
    bot = GridBot(instrument_name="CRO_USDT", grid_num=10, price_margin=0.01, investment_amount=500)
    bot.simulate_trading() 