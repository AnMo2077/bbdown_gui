using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;

namespace BiliDownloaderWPF
{
    public partial class DownloadWindow : Window
    {
        private Process _downloadProcess;
        private bool _isDownloading;
        
        public DownloadWindow()
        {
            InitializeComponent();
        }
        
        private async void StartDownloadButton_Click(object sender, RoutedEventArgs e)
        {
            string url = UrlTextBox.Text.Trim();
            if (string.IsNullOrEmpty(url))
            {
                MessageBox.Show("Please enter a valid video URL", "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
            
            string bbdPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "BBDown.exe");
            if (!File.Exists(bbdPath))
            {
                MessageBox.Show("BBDown.exe not found. Please ensure it is in the program directory.", "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }
            
            try
            {
                _isDownloading = true;
                ProgressText.Text = "Downloading...";
                StatusText.Text = "Starting download...";
                
                string arguments = $"{url} -aria2";
                
                if (SpecificPartsRadio.IsChecked == true)
                {
                    string start = StartPartTextBox.Text.Trim();
                    string end = EndPartTextBox.Text.Trim();
                    if (!string.IsNullOrEmpty(start) && !string.IsNullOrEmpty(end))
                    {
                        arguments += $" -p {start}-{end}";
                    }
                }
                
                await Task.Run(() =>
                {
                    try
                    {
                        ProcessStartInfo startInfo = new ProcessStartInfo
                        {
                            FileName = bbdPath,
                            Arguments = arguments,
                            WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            StandardOutputEncoding = Encoding.UTF8,
                            StandardErrorEncoding = Encoding.UTF8
                        };
                        
                        _downloadProcess = new Process { StartInfo = startInfo };
                        _downloadProcess.OutputDataReceived += (s, ev) =>
                        {
                            if (!string.IsNullOrEmpty(ev.Data))
                            {
                                Dispatcher.Invoke(() =>
                                {
                                    StatusText.Text += ev.Data + "\n";
                                    if (ev.Data.Contains("%"))
                                    {
                                        // Extract progress percentage
                                        string progressText = ev.Data;
                                        int percentIndex = progressText.IndexOf('%');
                                        if (percentIndex > 0)
                                        {
                                            string percentStr = progressText.Substring(0, percentIndex).Trim();
                                            if (int.TryParse(percentStr, out int percent))
                                            {
                                                ProgressBar.Value = percent;
                                            }
                                        }
                                    }
                                });
                            }
                        };
                        
                        _downloadProcess.ErrorDataReceived += (s, ev) =>
                        {
                            if (!string.IsNullOrEmpty(ev.Data))
                            {
                                Dispatcher.Invoke(() =>
                                {
                                    StatusText.Text += "Error: " + ev.Data + "\n";
                                });
                            }
                        };
                        
                        _downloadProcess.Start();
                        _downloadProcess.BeginOutputReadLine();
                        _downloadProcess.BeginErrorReadLine();
                        _downloadProcess.WaitForExit();
                        
                        Dispatcher.Invoke(() =>
                        {
                            if (_downloadProcess.ExitCode == 0)
                            {
                                ProgressText.Text = "Download completed!";
                                ProgressBar.Value = 100;
                                MessageBox.Show("Video download completed!", "Download Complete", MessageBoxButton.OK, MessageBoxImage.Information);
                            }
                            else
                            {
                                ProgressText.Text = "Download failed!";
                                MessageBox.Show("Download failed. Please check the status for details.", "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                            }
                            _isDownloading = false;
                        });
                    }
                    catch (Exception ex)
                    {
                        Dispatcher.Invoke(() =>
                        {
                            ProgressText.Text = "Error";
                            StatusText.Text += "Exception: " + ex.Message + "\n";
                            MessageBox.Show("Download failed: " + ex.Message, "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                            _isDownloading = false;
                        });
                    }
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error: " + ex.Message, "Error", MessageBoxButton.OK, MessageBoxImage.Error);
                _isDownloading = false;
            }
        }
        
        private void CancelButton_Click(object sender, RoutedEventArgs e)
        {
            if (_isDownloading && _downloadProcess != null && !_downloadProcess.HasExited)
            {
                _downloadProcess.Kill();
                _isDownloading = false;
                ProgressText.Text = "Cancelled";
                StatusText.Text += "Download cancelled by user\n";
            }
            Close();
        }
    }
}