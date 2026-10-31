"""配置管理模块 - 读写 gui_config.json，提供默认值与类型安全访问。"""
import json
import os
import sys

# 默认配置：与 BBDown 命令行参数对应
DEFAULT_CONFIG = {
    # 路径设置
    "work_dir": "",
    "output_dir": "",
    "ffmpeg_path": "",
    "aria2c_path": "",
    # 凭证
    "cookie": "",
    "access_token": "",
    # 下载引擎
    "use_aria2c": True,
    "aria2c_args": "-x16 -s16 -j16 -k5M",
    "multi_thread": True,
    # 编码与质量
    "encoding_priority": "hevc,avc,av1",
    "dfn_priority": "",
    "video_ascending": False,
    "audio_ascending": False,
    "video_only": False,
    "audio_only": False,
    # 处理选项
    "download_danmaku": False,
    "skip_mux": False,
    "skip_subtitle": False,
    "skip_cover": False,
    "skip_ai": True,
    "save_archives": False,
    # API 设置
    "use_tv_api": False,
    "use_app_api": False,
    "use_intl_api": False,
    "force_http": True,
    "allow_pcdn": False,
    # 命名
    "file_pattern": "",
    "multi_file_pattern": "",
    # 网络
    "delay_per_page": "0",
    "host": "",
    "ep_host": "",
    "area": "",
    "language": "",
    "user_agent": "",
    "upos_host": "",
    # 外观
    "appearance_mode": "System",
    "theme_color": "blue",
    "window_mode": "",
    "sidebar_collapsed": False,
    # 日志
    "log_level": "simple",
    # 开发者
    "dev_mode": False,
    # 登录检测
    "check_video_url": "",
}

def _default_config_path():
    """打包后配置与 exe 同目录，源码运行时放在项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "gui_config.json")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "gui_config.json",
    )


CONFIG_PATH = _default_config_path()


class ConfigManager:
    """加载、保存、访问配置，自动合并默认值。"""

    def __init__(self, path=None):
        self.path = path or CONFIG_PATH
        self.config = {}
        self.load()

    def load(self):
        """从磁盘加载配置，缺失的键用默认值填充。"""
        data = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {}
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        self.config = merged

    def save(self):
        """将当前配置写入磁盘。"""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def get_bool(self, key):
        return bool(self.config.get(key, False))

    def get_str(self, key):
        return str(self.config.get(key, ""))
