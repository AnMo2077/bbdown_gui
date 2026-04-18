import tkinter as tk
from tkinter import messagebox
import requests
import webbrowser
import os

class BiliDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("BiliDownloader GUI")
        self.version = "1.1"
        self.setup_ui()
        self.fetch_remote_data()

    def setup_ui(self):
        # 主界面布局
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=20, pady=20)
        
        # 标题和版本信息
        tk.Label(self.main_frame, text="BiliDownloader By AnMo_C", font=("Arial", 16)).grid(row=0, column=0, columnspan=2, pady=10)
        tk.Label(self.main_frame, text=f"版本: {self.version}").grid(row=1, column=0, columnspan=2)
        
        # 公告区域
        self.ad_label = tk.Label(self.main_frame, text="正在获取公告...", wraplength=300)
        self.ad_label.grid(row=2, column=0, columnspan=2, pady=10)
        
        # 功能按钮
        tk.Button(self.main_frame, text="登录B站账号", command=self.login).grid(row=3, column=0, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="下载视频", command=self.download).grid(row=3, column=1, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="更新日志", command=self.show_log).grid(row=4, column=0, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="使用帮助", command=self.show_help).grid(row=4, column=1, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="开放源代码许可", command=self.show_license).grid(row=5, column=0, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="捐赠", command=self.donate).grid(row=5, column=1, pady=5, sticky="ew")
        tk.Button(self.main_frame, text="退出", command=self.root.quit).grid(row=7, column=0, pady=5, sticky="ew")

    def fetch_remote_data(self):
        try:
            response = requests.get("https://api.anmoc.top/bilidown.txt")
            if response.status_code == 200:
                response.encoding = 'gbk'
                data = response.text
                # 解析远程数据
                self.ad = self.parse_value(data, "ad=")
                self.log = self.parse_value(data, "log=")
                self.prog_ver = self.parse_value(data, "prog_ver=")
                self.url = self.parse_value(data, "url=")
                
                # 更新UI
                self.ad_label.config(text=self.ad)
                
                # 检查版本
                if self.version != self.prog_ver:
                    self.show_update_message()
            else:
                self.ad_label.config(text="网络异常获取公告失败请检查网络后重试")
                
            # 检查核心文件是否存在
            # 检查核心文件是否存在
            bbd_path = os.path.join(os.path.dirname(__file__), "BBDown.exe")
            curl_path = os.path.join(os.path.dirname(__file__), "curl.exe")
            if not os.path.exists(bbd_path) or not os.path.exists(curl_path):
                messagebox.showerror("错误", f"缺少必要文件:\nBBDown.exe路径: {bbd_path}\ncurl.exe路径: {curl_path}\n请确保文件放在程序目录下")
                self.root.quit()
        except Exception as e:
            self.ad_label.config(text=f"获取远程数据失败: {str(e)}")
    
    def parse_value(self, data, key):
        lines = data.splitlines()
        for line in lines:
            if line.startswith(key):
                return line[len(key):].strip()
        return ""
    
    def show_update_message(self):
        update_window = tk.Toplevel(self.root)
        update_window.title("发现新版本")
        update_window.grab_set()  # 设置为模态窗口
        update_window.transient(self.root)  # 设置为主窗口的子窗口
        
        tk.Label(update_window, text=f"发现新版本 {self.prog_ver}", font=("Arial", 12)).pack(pady=10)
        tk.Label(update_window, text=f"更新日志: {self.log}", wraplength=300).pack(pady=5)
        tk.Button(update_window, text="下载更新", command=lambda: [webbrowser.open(self.url), self.root.quit()]).pack(pady=10)
        tk.Button(update_window, text="取消", command=self.root.quit).pack(pady=5)
    
    def login(self):
        # 实现登录功能
        try:
            # 调用BBDown.exe执行登录命令
            bbd_path = os.path.join(os.path.dirname(__file__), "BBDown.exe")
            if not os.path.exists(bbd_path):
                messagebox.showerror("错误", "找不到BBDown.exe，请确保文件放在程序目录下")
                return
            
            # 执行登录命令(异步)
            import subprocess
            import threading
            
            def async_login():
                try:
                    # 设置工作目录为程序所在目录
                    os.chdir(os.path.dirname(__file__))
                    process = subprocess.Popen([bbd_path, "login"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    process.wait()
                    
                    # 检查并打开二维码图片
                    qrcode_path = os.path.join(os.path.dirname(__file__), "qrcode.png")
                    abs_path = os.path.abspath(qrcode_path)
                    
                    # 确保二维码文件已生成
                    if os.path.exists(abs_path):
                        # 使用系统默认程序打开文件
                        try:
                            os.startfile(abs_path)
                            self.root.after(0, lambda: messagebox.showinfo("登录", "请扫描二维码登录B站账号"))
                        except Exception as e:
                            print(f"系统打开失败: {str(e)}")
                            try:
                                webbrowser.open(abs_path)
                                self.root.after(0, lambda: messagebox.showinfo("登录", "请扫描二维码登录B站账号"))
                            except Exception as e:
                                print(f"备用方法失败: {str(e)}")
                                self.root.after(0, lambda: messagebox.showerror("错误", f"无法打开二维码文件: {abs_path}"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("错误", "二维码文件生成失败，请重试"))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("错误", f"登录过程中发生错误: {str(e)}"))
            
            # 启动异步登录线程
            threading.Thread(target=async_login, daemon=True).start()
        except subprocess.CalledProcessError:
            messagebox.showerror("错误", "登录命令执行失败")
        except Exception as e:
            messagebox.showerror("错误", f"登录过程中发生错误: {str(e)}")
    
    def download(self):
        # 创建下载窗口
        download_window = tk.Toplevel(self.root)
        download_window.title("下载视频")
        download_window.geometry("400x300")
        
        # 添加输入框
        tk.Label(download_window, text="请输入B站视频链接:").pack(pady=10)
        self.video_url = tk.StringVar()
        url_entry = tk.Entry(download_window, textvariable=self.video_url, width=40)
        
        # 添加右键菜单
        menu = tk.Menu(url_entry, tearoff=0)
        menu.add_command(label="粘贴", command=lambda: url_entry.event_generate('<<Paste>>'))
        url_entry.bind("<Button-3>", lambda e: menu.post(e.x_root, e.y_root))
        
        url_entry.pack()
        
        # 添加分P选择
        tk.Label(download_window, text="请选择分P:").pack(pady=5)
        self.part_selection = tk.StringVar(value="all")
        tk.Radiobutton(download_window, text="下载全部", variable=self.part_selection, value="all").pack(anchor="w")
        tk.Radiobutton(download_window, text="下载特定分P", variable=self.part_selection, value="specific").pack(anchor="w")
        
        # 添加分P范围输入
        self.start_p_frame = tk.Frame(download_window)
        self.start_p_frame.pack(anchor="w")
        tk.Label(self.start_p_frame, text="起始P:").pack(side="left")
        self.start_p = tk.StringVar()
        tk.Entry(self.start_p_frame, textvariable=self.start_p, width=5).pack(side="left")
        
        self.end_p_frame = tk.Frame(download_window)
        self.end_p_frame.pack(anchor="w")
        tk.Label(self.end_p_frame, text="结束P:").pack(side="left")
        self.end_p = tk.StringVar()
        tk.Entry(self.end_p_frame, textvariable=self.end_p, width=5).pack(side="left")
        
        # 添加确认按钮
        tk.Button(download_window, text="下载", command=self.start_download).pack(pady=15, side="bottom", anchor="center")
        
    def close_all_child_windows(self):
        """关闭所有子窗口，仅保留主窗口"""
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
                
    def start_download(self):
        # 获取视频链接并开始下载
        url = self.video_url.get()
        if url:
            try:
                # 调用BBDown.exe下载视频
                bbd_path = os.path.join(os.path.dirname(__file__), "BBDown.exe")
                if not os.path.exists(bbd_path):
                    messagebox.showerror("错误", "找不到BBDown.exe，请确保文件放在程序目录下")
                    return
                
                # 根据选择构建命令
                command = [bbd_path, url, "-aria2"]
                if self.part_selection.get() == "specific":
                    if self.start_p.get() and self.end_p.get():
                        command.extend(["-p", f"{self.start_p.get()}-{self.end_p.get()}"])
                    else:
                        part_num = simpledialog.askinteger("分P选择", "请输入要下载的分P编号:")
                        if part_num:
                            command.extend(["-p", str(part_num)])
                
                # 创建下载进度窗口
                progress_window = tk.Toplevel(self.root)
                progress_window.title("下载进度")
                progress_window.geometry("400x100")
                
                tk.Label(progress_window, text="正在下载视频...").pack(pady=10)
                progress = tk.Label(progress_window, text="0%")
                progress.pack()
                
                # 启动下载进程
                import subprocess
                process = subprocess.Popen(command, 
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE,
                                         universal_newlines=True)
                
                # 更新进度
                def update_progress():
                    output = process.stdout.readline()
                    if "%" in output:
                        progress.config(text=output.strip())
                    if process.poll() is None:
                        progress_window.after(100, update_progress)
                    else:
                        progress_window.destroy()
                        confirm_window = tk.Toplevel(self.root)
                        confirm_window.title("下载完成")
                        confirm_window.geometry("300x100")
                        tk.Label(confirm_window, text="视频下载完成！").pack(pady=10)
                        tk.Button(confirm_window, text="确定", command=lambda: [confirm_window.destroy(), self.close_all_child_windows()]).pack(pady=10)
                
                progress_window.after(100, update_progress)
                
            except Exception as e:
                messagebox.showerror("错误", f"下载失败: {str(e)}")
        else:
            messagebox.showerror("错误", "请输入有效的视频链接")
    
    def show_log(self):
        # 显示更新日志
        log_window = tk.Toplevel(self.root)
        log_window.title("更新日志")
        
        tk.Label(log_window, text=self.log, wraplength=300).pack(padx=20, pady=20)
        tk.Button(log_window, text="关闭", command=log_window.destroy).pack(pady=10)
        
    def show_license(self):
        # 显示开源许可
        webbrowser.open("https://api.anmoc.top/bilidownlicense.txt")
        
    def show_help(self):
        # 显示使用帮助
        webbrowser.open("https://api.anmoc.top/bilidownhelp.txt")
        
    def donate(self):
        # 打开捐赠页面
        webbrowser.open("https://anmoc.top/eat")

if __name__ == "__main__":
    root = tk.Tk()
    app = BiliDownloaderGUI(root)
    root.mainloop()