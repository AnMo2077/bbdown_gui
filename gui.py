import customtkinter as ctk
from customtkinter import CTkMessageBox
import requests
import webbrowser
import os
import subprocess
import threading
import json
import gettext
import locale

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LANG_DIR = os.path.join(APP_DIR, "lang")

LANGUAGES = {
    "简体中文": "zh_CN",
    "English": "en_US"
}

class I18n:
    def __init__(self):
        self.current_lang = "zh_CN"
        self.translations = {}
        self._ = lambda s: s
        self.load_translations()

    def load_translations(self):
        for name, code in LANGUAGES.items():
            lang_file = os.path.join(LANG_DIR, f"{code}.json")
            if os.path.exists(lang_file):
                with open(lang_file, "r", encoding="utf-8") as f:
                    self.translations[code] = json.load(f)
            else:
                self.translations[code] = {}

        try:
            system_lang = locale.getdefaultlocale()[0]
            if system_lang == "zh_CN":
                self.current_lang = "zh_CN"
            else:
                self.current_lang = "en_US"
        except:
            self.current_lang = "zh_CN"

        self._ = lambda s: self.translations.get(self.current_lang, {}).get(s, s)

    def set_lang(self, lang_code):
        self.current_lang = lang_code
        self._ = lambda s: self.translations.get(lang_code, {}).get(s, s)

    def get_text(self, key):
        return self._(key)

i18n = I18n()

class BiliDownloaderGUI:
    def __init__(self, root):
        self.root = root
        self.version = "1.1"
        self.ad = ""
        self.log = ""
        self.prog_ver = ""
        self.url = ""
        self.setup_ui()
        self.fetch_remote_data()

    def setup_ui(self):
        self.root.title(i18n.get_text("app_title"))
        self.root.geometry("500x450")
        self.root.resizable(False, False)

        main_frame = ctk.CTkFrame(self.root, corner_radius=15)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_label = ctk.CTkLabel(main_frame, text="BiliDownloader By AnMo_C",
                                    font=ctk.CTkFont(size=20, weight="bold"))
        title_label.pack(pady=(10, 5))

        version_label = ctk.CTkLabel(main_frame, text=f"{i18n.get_text('version')}: {self.version}",
                                      text_color="gray")
        version_label.pack(pady=(0, 10))

        self.ad_label = ctk.CTkLabel(main_frame, text=i18n.get_text("loading_announcement"),
                                       wraplength=400, height=60)
        self.ad_label.pack(pady=10, padx=10)

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(pady=10)

        buttons = [
            (i18n.get_text("login"), self.login),
            (i18n.get_text("download"), self.download),
            (i18n.get_text("changelog"), self.show_log),
            (i18n.get_text("help"), self.show_help),
            (i18n.get_text("license"), self.show_license),
            (i18n.get_text("donate"), self.donate),
        ]

        for i, (text, cmd) in enumerate(buttons):
            row = i // 2
            col = i % 2
            btn = ctk.CTkButton(btn_frame, text=text, command=cmd, width=180, height=40)
            btn.grid(row=row, column=col, padx=10, pady=5)

        self.lang_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.lang_frame.pack(side="bottom", pady=(20, 0))

        self.lang_label = ctk.CTkLabel(self.lang_frame, text=i18n.get_text("language") + ":")
        self.lang_label.pack(side="left", padx=5)

        self.lang_var = ctk.StringVar(value=list(LANGUAGES.keys())[0])
        lang_menu = ctk.CTkOptionMenu(self.lang_frame, values=list(LANGUAGES.keys()),
                                       variable=self.lang_var, command=self.change_language,
                                       width=120)
        lang_menu.pack(side="left", padx=5)

        exit_btn = ctk.CTkButton(main_frame, text=i18n.get_text("exit"),
                                  command=self.root.quit, fg_color="red", hover_color="darkred",
                                  width=180, height=40)
        exit_btn.pack(pady=20)

    def change_language(self, lang_name):
        lang_code = LANGUAGES.get(lang_name, "zh_CN")
        i18n.set_lang(lang_code)
        self.refresh_ui()

    def refresh_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.setup_ui()
        self.ad_label.config(text=self.ad)

    def fetch_remote_data(self):
        try:
            response = requests.get("https://api.nzs233.xyz/bilidown.txt", timeout=10)
            if response.status_code == 200:
                response.encoding = 'gbk'
                data = response.text
                self.ad = self.parse_value(data, "ad=")
                self.log = self.parse_value(data, "log=")
                self.prog_ver = self.parse_value(data, "prog_ver=")
                self.url = self.parse_value(data, "url=")

                self.ad_label.configure(text=self.ad)

                if self.version != self.prog_ver:
                    self.show_update_message()
            else:
                self.ad_label.configure(text=i18n.get_text("network_error"))

            bbd_path = os.path.join(APP_DIR, "BBDown.exe")
            curl_path = os.path.join(APP_DIR, "curl.exe")
            if not os.path.exists(bbd_path) or not os.path.exists(curl_path):
                CTkMessageBox(title=i18n.get_text("error"),
                              message=f"{i18n.get_text('missing_files')}\nBBDown.exe: {bbd_path}\ncurl.exe: {curl_path}",
                              icon="cancel")
                self.root.quit()
        except Exception as e:
            self.ad_label.configure(text=f"{i18n.get_text('fetch_failed')}: {str(e)}")

    def parse_value(self, data, key):
        for line in data.splitlines():
            if line.startswith(key):
                return line[len(key):].strip()
        return ""

    def show_update_message(self):
        win = ctk.CTkToplevel(self.root)
        win.title(i18n.get_text("new_version"))
        win.geometry("350x200")
        win.grab_set()

        ctk.CTkLabel(win, text=f"{i18n.get_text('found_version')} {self.prog_ver}",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=15)
        ctk.CTkLabel(win, text=f"{i18n.get_text('changelog')}: {self.log}", wraplength=300).pack(pady=10)

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text=i18n.get_text("download_update"),
                      command=lambda: [webbrowser.open(self.url), self.root.quit()]).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text=i18n.get_text("cancel"), command=self.root.quit,
                      fg_color="gray").pack(side="left", padx=5)

    def login(self):
        bbd_path = os.path.join(APP_DIR, "BBDown.exe")
        if not os.path.exists(bbd_path):
            CTkMessageBox(title=i18n.get_text("error"), message=i18n.get_text("bbdown_not_found"), icon="cancel")
            return

        def async_login():
            try:
                os.chdir(APP_DIR)
                process = subprocess.Popen([bbd_path, "login"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                process.wait()

                qrcode_path = os.path.join(APP_DIR, "qrcode.png")
                abs_path = os.path.abspath(qrcode_path)

                if os.path.exists(abs_path):
                    try:
                        os.startfile(abs_path)
                        self.root.after(0, lambda: CTkMessageBox(title=i18n.get_text("login"),
                                                                   message=i18n.get_text("scan_qrcode"), icon="info"))
                    except Exception:
                        webbrowser.open(abs_path)
                        self.root.after(0, lambda: CTkMessageBox(title=i18n.get_text("login"),
                                                                   message=i18n.get_text("scan_qrcode"), icon="info"))
                else:
                    self.root.after(0, lambda: CTkMessageBox(title=i18n.get_text("error"),
                                                               message=i18n.get_text("qrcode_failed"), icon="cancel"))
            except Exception as e:
                self.root.after(0, lambda: CTkMessageBox(title=i18n.get_text("error"),
                                                           message=f"{i18n.get_text('login_failed')}: {str(e)}", icon="cancel"))

        threading.Thread(target=async_login, daemon=True).start()

    def download(self):
        win = ctk.CTkToplevel(self.root)
        win.title(i18n.get_text("download_video"))
        win.geometry("450x350")

        ctk.CTkLabel(win, text=i18n.get_text("input_url"), font=ctk.CTkFont(weight="bold")).pack(pady=10)

        self.video_url = ctk.CTkEntry(win, width=350, placeholder_text="https://www.bilibili.com/video/BV...")
        self.video_url.pack(pady=5)

        ctk.CTkLabel(win, text=i18n.get_text("select_part"), font=ctk.CTkFont(weight="bold")).pack(pady=(15, 5))

        self.part_selection = ctk.StringVar(value="all")
        ctk.CTkRadioButton(win, text=i18n.get_text("download_all"), variable=self.part_selection,
                           value="all").pack(anchor="w", padx=50)
        ctk.CTkRadioButton(win, text=i18n.get_text("download_specific"), variable=self.part_selection,
                           value="specific").pack(anchor="w", padx=50)

        range_frame = ctk.CTkFrame(win, fg_color="transparent")
        range_frame.pack(pady=10)

        self.start_p = ctk.CTkEntry(range_frame, width=80, placeholder_text="1")
        self.start_p.pack(side="left", padx=5)
        ctk.CTkLabel(range_frame, text="-").pack(side="left")
        self.end_p = ctk.CTkEntry(range_frame, width=80, placeholder_text="10")
        self.end_p.pack(side="left", padx=5)

        ctk.CTkButton(win, text=i18n.get_text("start_download"), command=lambda: self.start_download(win),
                      width=200, height=40).pack(pady=20)

    def start_download(self, win):
        url = self.video_url.get()
        if not url:
            CTkMessageBox(title=i18n.get_text("error"), message=i18n.get_text("invalid_url"), icon="cancel")
            return

        bbd_path = os.path.join(APP_DIR, "BBDown.exe")
        if not os.path.exists(bbd_path):
            CTkMessageBox(title=i18n.get_text("error"), message=i18n.get_text("bbdown_not_found"), icon="cancel")
            return

        command = [bbd_path, url, "-aria2"]
        if self.part_selection.get() == "specific":
            start = self.start_p.get()
            end = self.end_p.get()
            if start and end:
                command.extend(["-p", f"{start}-{end}"])

        progress_win = ctk.CTkToplevel(self.root)
        progress_win.title(i18n.get_text("downloading"))
        progress_win.geometry("400x120")
        progress_win.grab_set()

        ctk.CTkLabel(progress_win, text=i18n.get_text("downloading_video")).pack(pady=10)
        self.progress_label = ctk.CTkLabel(progress_win, text="0%")
        self.progress_label.pack()

        def async_download():
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            universal_newlines=True, cwd=APP_DIR)
                for line in iter(process.stdout.readline, ''):
                    if line:
                        self.root.after(0, lambda l=line: self.progress_label.configure(text=l.strip()))
                    if process.poll() is not None:
                        break

                self.root.after(0, lambda: [progress_win.destroy(), self.show_download_complete()])
            except Exception as e:
                self.root.after(0, lambda: [progress_win.destroy(),
                                             CTkMessageBox(title=i18n.get_text("error"),
                                                           message=f"{i18n.get_text('download_failed')}: {str(e)}", icon="cancel")])

        threading.Thread(target=async_download, daemon=True).start()

    def show_download_complete(self):
        complete_win = ctk.CTkToplevel(self.root)
        complete_win.title(i18n.get_text("download_complete"))
        complete_win.geometry("300x100")
        complete_win.grab_set()

        ctk.CTkLabel(complete_win, text=i18n.get_text("download_finished")).pack(pady=20)
        ctk.CTkButton(complete_win, text="OK", command=complete_win.destroy, width=100).pack()

    def show_log(self):
        win = ctk.CTkToplevel(self.root)
        win.title(i18n.get_text("changelog"))
        win.geometry("400x300")

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(scroll, text=self.log, wraplength=350).pack()

    def show_license(self):
        webbrowser.open("https://api.nzs233.xyz/bilidownlicense.txt")

    def show_help(self):
        webbrowser.open("https://api.nzs233.xyz/bilidownhelp.txt")

    def donate(self):
        webbrowser.open("https://nzs233.xyz/eat")

if __name__ == "__main__":
    root = ctk.CTk()
    app = BiliDownloaderGUI(root)
    root.mainloop()