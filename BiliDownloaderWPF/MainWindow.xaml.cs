using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;

namespace BiliDownloaderWPF
{
    public partial class MainWindow : Window
    {
        private const string Version = "1.1";
        private const string ApiUrl = "https://api.anmoc.top/bilidown.txt";
        
        private string _ad = string.Empty;
        private string _log = string.Empty;
        private string _progVer = string.Empty;
        private string _url = string.Empty;
        
        private readonly Dictionary<string, string> _languages = new()
        {
            { "简体中文", "zh_CN" },
            { "English", "en_US" }
        };
        
        private readonly Dictionary<string, Dictionary<string, string>> _translations = new();
        private string _currentLang = "zh_CN";
        
        public MainWindow()
        {
            InitializeComponent();
            InitializeLanguages();
            VersionText.Text = $"Version: {Version}";
            LoadLanguages();
            _ = FetchRemoteDataAsync();
        }
        
        private void InitializeLanguages()
        {
            LanguageComboBox.Items.Clear();
            foreach (var lang in _languages.Keys)
            {
                LanguageComboBox.Items.Add(lang);
            }
            LanguageComboBox.SelectedIndex = 0;
        }
        
        private void LoadLanguages()
        {
            string langDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "lang");
            
            foreach (var langCode in _languages.Values)
            {
                string langFile = Path.Combine(langDir, $"{langCode}.xml");
                if (File.Exists(langFile))
                {
                    // 简化实现，使用硬编码的翻译
                    _translations[langCode] = new Dictionary<string, string>
                    {
                        { "app_title", "BiliDownloader GUI" },
                        { "login", "登录B站账号" },
                        { "download", "下载视频" },
                        { "changelog", "更新日志" },
                        { "help", "使用帮助" },
                        { "license", "开放源代码许可" },
                        { "donate", "捐赠" },
                        { "exit", "退出" },
                        { "language", "语言" },
                        { "loading_announcement", "正在获取公告..." },
                        { "network_error", "网络异常获取公告失败请检查网络后重试" },
                        { "error", "错误" },
                        { "missing_files", "缺少必要文件" },
                        { "bbdown_not_found", "找不到BBDown.exe，请确保文件放在程序目录下" },
                        { "qrcode_failed", "二维码文件生成失败，请重试" },
                        { "login_failed", "登录过程中发生错误" },
                        { "scan_qrcode", "请扫描二维码登录B站账号" },
                        { "download_video", "下载视频" },
                        { "input_url", "请输入B站视频链接" },
                        { "select_part", "请选择分P" },
                        { "download_all", "下载全部" },
                        { "download_specific", "下载特定分P" },
                        { "start_download", "开始下载" },
                        { "invalid_url", "请输入有效的视频链接" },
                        { "downloading", "下载中" },
                        { "downloading_video", "正在下载视频..." },
                        { "download_failed", "下载失败" },
                        { "download_complete", "下载完成" },
                        { "download_finished", "视频下载完成!" },
                        { "new_version", "发现新版本" },
                        { "found_version", "发现新版本" },
                        { "download_update", "下载更新" },
                        { "cancel", "取消" }
                    };
                }
            }
            
            // 英文翻译
            _translations["en_US"] = new Dictionary<string, string>
            {
                { "app_title", "BiliDownloader GUI" },
                { "login", "Login Bilibili" },
                { "download", "Download Video" },
                { "changelog", "Changelog" },
                { "help", "Help" },
                { "license", "Open Source License" },
                { "donate", "Donate" },
                { "exit", "Exit" },
                { "language", "Language" },
                { "loading_announcement", "Loading announcement..." },
                { "network_error", "Network error. Please check your connection." },
                { "error", "Error" },
                { "missing_files", "Missing required files" },
                { "bbdown_not_found", "BBDown.exe not found. Please ensure it is in the program directory." },
                { "qrcode_failed", "QR code generation failed. Please try again." },
                { "login_failed", "Login error" },
                { "scan_qrcode", "Please scan the QR code to login to Bilibili" },
                { "download_video", "Download Video" },
                { "input_url", "Enter Bilibili video URL" },
                { "select_part", "Select Part" },
                { "download_all", "Download All" },
                { "download_specific", "Download Specific Part" },
                { "start_download", "Start Download" },
                { "invalid_url", "Please enter a valid video URL" },
                { "downloading", "Downloading" },
                { "downloading_video", "Downloading video..." },
                { "download_failed", "Download failed" },
                { "download_complete", "Download Complete" },
                { "download_finished", "Video download completed!" },
                { "new_version", "New Version Found" },
                { "found_version", "Found new version" },
                { "download_update", "Download Update" },
                { "cancel", "Cancel" }
            };
        }
        
        private string GetTranslation(string key)
        {
            if (_translations.TryGetValue(_currentLang, out var langDict) && langDict.TryGetValue(key, out var value))
            {
                return value;
            }
            return key;
        }
        
        private void UpdateUI()
        {
            Title = GetTranslation("app_title");
            
            var buttons = new[]
            {
                new { Button = LoginButton, Key = "login" },
                new { Button = DownloadButton, Key = "download" },
                new { Button = ChangelogButton, Key = "changelog" },
                new { Button = HelpButton, Key = "help" },
                new { Button = LicenseButton, Key = "license" },
                new { Button = DonateButton, Key = "donate" },
                new { Button = ExitButton, Key = "exit" }
            };
            
            foreach (var item in buttons)
            {
                item.Button.Content = GetTranslation(item.Key);
            }
        }
        
        private async Task FetchRemoteDataAsync()
        {
            try
            {
                using var client = new HttpClient();
                client.Timeout = TimeSpan.FromSeconds(10);
                var response = await client.GetAsync(ApiUrl);
                
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    ParseRemoteData(content);
                    AnnouncementText.Text = _ad;
                    
                    if (_progVer != Version)
                    {
                        ShowUpdateMessage();
                    }
                }
                else
                {
                    AnnouncementText.Text = GetTranslation("network_error");
                }
                
                CheckRequiredFiles();
            }
            catch (Exception ex)
            {
                AnnouncementText.Text = $"获取远程数据失败: {ex.Message}";
            }
        }
        
        private void ParseRemoteData(string content)
        {
            var lines = content.Split('\n');
            foreach (var line in lines)
            {
                if (line.StartsWith("ad="))
                    _ad = line.Substring(3).Trim();
                else if (line.StartsWith("log="))
                    _log = line.Substring(4).Trim();
                else if (line.StartsWith("prog_ver="))
                    _progVer = line.Substring(9).Trim();
                else if (line.StartsWith("url="))
                    _url = line.Substring(4).Trim();
            }
        }
        
        private void CheckRequiredFiles()
        {
            string bbdPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "BBDown.exe");
            string curlPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "curl.exe");
            
            if (!File.Exists(bbdPath) || !File.Exists(curlPath))
            {
                MessageBox.Show(
                    $"{GetTranslation("missing_files")}\nBBDown.exe: {bbdPath}\ncurl.exe: {curlPath}",
                    GetTranslation("error"),
                    MessageBoxButton.OK,
                    MessageBoxImage.Error
                );
                Application.Current.Shutdown();
            }
        }
        
        private void ShowUpdateMessage()
        {
            var result = MessageBox.Show(
                $"{GetTranslation("found_version")} {_progVer}\n{GetTranslation("changelog")}: {_log}",
                GetTranslation("new_version"),
                MessageBoxButton.YesNo,
                MessageBoxImage.Information
            );
            
            if (result == MessageBoxResult.Yes)
            {
                Process.Start(new ProcessStartInfo(_url) { UseShellExecute = true });
                Application.Current.Shutdown();
            }
        }
        
        private void LoginButton_Click(object sender, RoutedEventArgs e)
        {
            string bbdPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "BBDown.exe");
            if (!File.Exists(bbdPath))
            {
                MessageBox.Show(GetTranslation("bbdown_not_found"), GetTranslation("error"), MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
            
            Task.Run(() =>
            {
                try
                {
                    ProcessStartInfo startInfo = new ProcessStartInfo
                    {
                        FileName = bbdPath,
                        Arguments = "login",
                        WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true
                    };
                    
                    using Process process = Process.Start(startInfo);
                    process.WaitForExit();
                    
                    string qrcodePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "qrcode.png");
                    if (File.Exists(qrcodePath))
                    {
                        Dispatcher.Invoke(() =>
                        {
                            Process.Start(new ProcessStartInfo(qrcodePath) { UseShellExecute = true });
                            MessageBox.Show(GetTranslation("scan_qrcode"), GetTranslation("login"), MessageBoxButton.OK, MessageBoxImage.Information);
                        });
                    }
                    else
                    {
                        Dispatcher.Invoke(() =>
                        {
                            MessageBox.Show(GetTranslation("qrcode_failed"), GetTranslation("error"), MessageBoxButton.OK, MessageBoxImage.Error);
                        });
                    }
                }
                catch (Exception ex)
                {
                    Dispatcher.Invoke(() =>
                    {
                        MessageBox.Show($"{GetTranslation("login_failed")}: {ex.Message}", GetTranslation("error"), MessageBoxButton.OK, MessageBoxImage.Error);
                    });
                }
            });
        }
        
        private void DownloadButton_Click(object sender, RoutedEventArgs e)
        {
            DownloadWindow downloadWindow = new DownloadWindow();
            downloadWindow.ShowDialog();
        }
        
        private void ChangelogButton_Click(object sender, RoutedEventArgs e)
        {
            if (!string.IsNullOrEmpty(_log))
            {
                MessageBox.Show(_log, GetTranslation("changelog"), MessageBoxButton.OK, MessageBoxImage.Information);
            }
            else
            {
                MessageBox.Show("No changelog available", GetTranslation("changelog"), MessageBoxButton.OK, MessageBoxImage.Information);
            }
        }
        
        private void HelpButton_Click(object sender, RoutedEventArgs e)
        {
            Process.Start(new ProcessStartInfo("https://api.anmoc.top/bilidownhelp.txt") { UseShellExecute = true });
        }
        
        private void LicenseButton_Click(object sender, RoutedEventArgs e)
        {
            Process.Start(new ProcessStartInfo("https://api.anmoc.top/bilidownlicense.txt") { UseShellExecute = true });
        }
        
        private void DonateButton_Click(object sender, RoutedEventArgs e)
        {
            Process.Start(new ProcessStartInfo("https://anmoc.top/eat") { UseShellExecute = true });
        }
        
        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            Application.Current.Shutdown();
        }
        
        private void LanguageComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (LanguageComboBox.SelectedItem is string selectedLang)
            {
                _currentLang = _languages[selectedLang];
                UpdateUI();
            }
        }
    }
}