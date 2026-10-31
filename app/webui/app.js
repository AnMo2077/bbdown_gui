/* BiliDownloader 2.0 — 前端逻辑（无框架、无外部依赖） */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const state = {
    version: '2.0',
    publisher: 'AnMo_C',
    defaultDir: '',
    config: {},
    appearance: { mode: 'System', color: 'blue' },
    account: { logged_in: false, mid: '', hint: '未登录' },
    running: false,
    progress: 0,
    history: [],
    announce: {},
    coreFiles: [],
    seq: 0,
    result: '',
    lastOutput: '',
    lastOutputDir: '',
    forcedShown: false,
    optionalShown: false,
    loginQr: '',
    loginStatus: 'idle',
  };

  const PAGE_META = {
    home: { title: 'BiliDownloader', sub: 'By {publisher} · v{version}' },
    download: { title: '下载', sub: '粘贴链接，选择分 P 与清晰度' },
    login: { title: '登录', sub: '扫码登录 B 站账号' },
    settings: { title: '设置', sub: '下载、网络与外观' },
    about: { title: '关于', sub: '版本与组件信息' },
  };

  const MEMBER_ICONS = {
    大会员: '<svg viewBox="0 0 24 24"><path d="M4 5l3 8 5-6 5 6 3-8v14H4V5zm2 12h12v2H6v-2z"/></svg>',
    普通用户: '<svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-4.4 0-8 2.2-8 5v1h16v-1c0-2.8-3.6-5-8-5z"/></svg>',
    未登录: '<svg viewBox="0 0 24 24"><path d="M12 2 1 21h22L12 2zm1 15h-2v-2h2v2zm0-4h-2V9h2v4z"/></svg>',
    default: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>',
  };

  const SETTINGS_BINDINGS = [
    { id: 'work-dir', key: 'work_dir', type: 'text' },
    { id: 'output-dir', key: 'output_dir', type: 'text' },
    { id: 'ffmpeg-path', key: 'ffmpeg_path', type: 'text' },
    { id: 'aria2c-path', key: 'aria2c_path', type: 'text' },
    { id: 'use-aria2c', key: 'use_aria2c', type: 'bool' },
    { id: 'multi-thread', key: 'multi_thread', type: 'bool' },
    { id: 'save-archives', key: 'save_archives', type: 'bool' },
    { id: 'force-http', key: 'force_http', type: 'bool' },
    { id: 'allow-pcdn', key: 'allow_pcdn', type: 'bool' },
    { id: 'aria2c-args', key: 'aria2c_args', type: 'text' },
    { id: 'delay-per-page', key: 'delay_per_page', type: 'text' },
    { id: 'dfn-priority', key: 'dfn_priority', type: 'text' },
    { id: 'file-pattern', key: 'file_pattern', type: 'text' },
    { id: 'multi-file-pattern', key: 'multi_file_pattern', type: 'text' },
    { id: 'video-ascending', key: 'video_ascending', type: 'bool' },
    { id: 'audio-ascending', key: 'audio_ascending', type: 'bool' },
    { id: 'download-danmaku', key: 'download_danmaku', type: 'bool' },
    { id: 'skip-mux', key: 'skip_mux', type: 'bool' },
    { id: 'skip-subtitle', key: 'skip_subtitle', type: 'bool' },
    { id: 'skip-cover', key: 'skip_cover', type: 'bool' },
    { id: 'skip-ai', key: 'skip_ai', type: 'bool' },
    { id: 'use-tv-api', key: 'use_tv_api', type: 'bool' },
    { id: 'use-app-api', key: 'use_app_api', type: 'bool' },
    { id: 'use-intl-api', key: 'use_intl_api', type: 'bool' },
    { id: 'host', key: 'host', type: 'text' },
    { id: 'ep-host', key: 'ep_host', type: 'text' },
    { id: 'area', key: 'area', type: 'text' },
    { id: 'language', key: 'language', type: 'text' },
    { id: 'user-agent', key: 'user_agent', type: 'text' },
    { id: 'upos-host', key: 'upos_host', type: 'text' },
    { id: 'cookie', key: 'cookie', type: 'text' },
    { id: 'access-token', key: 'access_token', type: 'text' },
    { id: 'theme-color', key: 'theme_color', type: 'text' },
    { id: 'window-mode', key: 'window_mode', type: 'text' },
    { id: 'log-level', key: 'log_level', type: 'text' },
  ];

  // ---------------------------------------------------------------- //
  //  基础
  // ---------------------------------------------------------------- //
  async function action(name, payload = {}) {
    const response = await fetch('/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: name, ...payload }),
    });
    const data = await response.json().catch(() => ({ ok: false, error: '服务返回异常' }));
    if (!data.ok) throw new Error(data.error || '操作失败');
    return data;
  }

  function toast(message, kind = 'info') {
    const node = document.createElement('div');
    node.className = 'toast' + (kind === 'error' ? ' error' : '');
    node.textContent = message;
    $('toast-root').appendChild(node);
    setTimeout(() => {
      node.style.opacity = '0';
      node.style.transition = 'opacity .18s';
      setTimeout(() => node.remove(), 200);
    }, kind === 'error' ? 4200 : 2600);
  }

  function confirmAction(text, okLabel = '确定') {
    return new Promise((resolve) => {
      const modal = $('confirm-modal');
      $('confirm-text').textContent = text;
      $('confirm-ok').textContent = okLabel;
      modal.hidden = false;
      const done = (value) => {
        modal.hidden = true;
        $('confirm-ok').onclick = null;
        $('confirm-cancel').onclick = null;
        resolve(value);
      };
      $('confirm-ok').onclick = () => done(true);
      $('confirm-cancel').onclick = () => done(false);
    });
  }

  function openDebugWindow() {
    const win = window.open('/debug.html', 'bbdown-debug', 'width=1000,height=720');
    if (!win) {
      toast('调试窗口被浏览器拦截，请允许弹窗后点“打开调试窗口”', 'error');
    }
    return win;
  }

  function openUrl(url) {
    if (!url) return Promise.resolve();
    return action('open_url', { url }).catch((error) => toast(error.message, 'error'));
  }

  // ---------------------------------------------------------------- //
  //  主题 / 导航
  // ---------------------------------------------------------------- //
  const media = window.matchMedia('(prefers-color-scheme: dark)');

  function effectiveTheme() {
    const mode = state.appearance.mode || 'System';
    if (mode === 'Light') return 'light';
    if (mode === 'Dark') return 'dark';
    return media.matches ? 'dark' : 'light';
  }

  function applyAppearance(appearance) {
    if (appearance) state.appearance = appearance;
    document.documentElement.dataset.theme = effectiveTheme();
    document.documentElement.dataset.accent = state.appearance.color || 'blue';
    const select = $('appearance-mode');
    if (select) select.value = state.appearance.mode || 'System';
    syncCustomSelects();
  }

  function applySidebar(collapsed) {
    document.body.classList.toggle('sidebar-collapsed', !!collapsed);
    const button = $('sidebar-toggle');
    if (button) {
      const title = collapsed ? '展开侧栏' : '收起侧栏';
      button.title = title;
      button.setAttribute('aria-label', title);
      button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
  }

  media.addEventListener('change', () => {
    if ((state.appearance.mode || 'System') === 'System') applyAppearance();
  });

  window.addEventListener('resize', () => moveNavIndicator(false));

  let pendingLeavePage = null;

  let navIndicatorReady = false;

  function moveNavIndicator(animate = true) {
    const nav = document.querySelector('.nav');
    const indicator = $('nav-indicator');
    const active = nav ? nav.querySelector('.nav-item.active') : null;
    if (!nav || !indicator || !active) return;
    const navRect = nav.getBoundingClientRect();
    const rect = active.getBoundingClientRect();
    const x = rect.left - navRect.left + 5;
    const y = rect.top - navRect.top + (rect.height - 18) / 2;
    const transform = `translate(${x}px, ${y}px)`;
    const useAnimation = animate && navIndicatorReady;
    if (!useAnimation) {
      indicator.style.transition = 'none';
    }
    indicator.style.transform = transform;
    indicator.hidden = false;
    if (!useAnimation) {
      void indicator.offsetWidth;
      indicator.style.transition = '';
    }
    navIndicatorReady = true;
  }

  function showPage(name, force = false) {
    if (!PAGE_META[name]) name = 'home';
    const current = document.querySelector('.page.active')?.id.replace('page-', '') || 'home';
    if (!force && current === 'settings' && name !== 'settings' && !$('settings-dirty').hidden) {
      pendingLeavePage = name;
      $('leave-modal').hidden = false;
      return;
    }
    const meta = PAGE_META[name];
    $('page-title').textContent = meta.title;
    $('page-sub').textContent = meta.sub
      .replace('{publisher}', state.publisher)
      .replace('{version}', state.version);
    $('status-page').textContent = meta.title === 'BiliDownloader' ? '首页' : meta.title;

    document.querySelectorAll('.nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.page === name);
    });
    document.querySelectorAll('.page').forEach((page) => {
      page.classList.toggle('active', page.id === `page-${name}`);
    });
    document.querySelector('.pages').scrollTop = 0;
    if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);

    if (name === 'login') refreshLogin(true);
    if (name === 'settings') requestAnimationFrame(() => {
      moveSettingsIndicator(false);
      updateSettingsNav();
    });
    moveNavIndicator();
  }

  let settingsScrollTimer = 0;
  let settingsNavLockUntil = 0;
  let settingsNavReady = false;

  function moveSettingsIndicator(animate = true) {
    const nav = $('settings-nav');
    const indicator = $('settings-nav-indicator');
    if (!nav || !indicator) return;
    const active = nav.querySelector('.settings-nav-item.active');
    if (!active) return;
    const y = active.offsetTop + (active.offsetHeight - 18) / 2;
    const useAnimation = animate && settingsNavReady;
    if (!useAnimation) indicator.style.transition = 'none';
    indicator.style.transform = `translateY(${y}px)`;
    indicator.hidden = false;
    if (!useAnimation) {
      void indicator.offsetWidth;
      indicator.style.transition = '';
    }
    settingsNavReady = true;
  }

  function setSettingsNavActive(id, animate = true) {
    document.querySelectorAll('.settings-nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.target === id);
    });
    moveSettingsIndicator(animate);
  }

  function updateSettingsNav() {
    if (performance.now() < settingsNavLockUntil) return;
    const page = $('page-settings');
    if (!page || !page.classList.contains('active')) return;
    const pages = document.querySelector('.pages');
    const cards = [...page.querySelectorAll('.settings-content .card[id]')];
    if (!cards.length) return;
    const line = pages.getBoundingClientRect().top + 28;
    let current = cards[0];
    cards.forEach((card) => {
      if (card.getBoundingClientRect().top <= line) current = card;
    });
    if (pages.scrollTop + pages.clientHeight >= pages.scrollHeight - 8) {
      current = cards[cards.length - 1];
    }
    setSettingsNavActive(current.id, true);
  }

  // ---------------------------------------------------------------- //
  //  渲染
  // ---------------------------------------------------------------- //
  function renderCoreFiles() {
    const files = state.coreFiles || [];
    const build = (target, roomy) => {
      target.textContent = '';
      if (!files.length) {
        const li = document.createElement('li');
        li.className = 'missing';
        li.textContent = '未获取到状态';
        target.appendChild(li);
        return;
      }
      for (const file of files) {
        const li = document.createElement('li');
        li.className = file.ok ? 'ok' : 'missing';
        const dot = document.createElement('span');
        dot.className = 'dot';
        const name = document.createElement('span');
        name.textContent = file.name;
        li.append(dot, name);
        if (roomy) {
          const size = document.createElement('span');
          size.className = 'file-size';
          size.textContent = file.ok ? formatSize(file.size) : '缺失';
          li.appendChild(size);
        }
        target.appendChild(li);
      }
    };
    build($('core-list'), false);
    build($('core-files-card'), true);
  }

  function formatSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${bytes} B`;
  }

  function renderAnnounce() {
    const info = state.announce || {};
    const hasData = !!info.fetched;

    $('announce-ad').textContent = hasData || info.error
      ? (info.ad || '暂无公告')
      : '正在获取公告…';
    const note = $('announce-note');
    if (info.error) {
      note.hidden = false;
      note.textContent = `公告获取失败：${info.error}`;
    } else {
      note.hidden = true;
    }

    const text = $('update-text');
    text.textContent = '';
    if (!hasData && !info.error) {
      text.textContent = '正在检查版本…';
    } else if (info.error && !hasData) {
      text.textContent = '版本检查失败，请稍后重试。';
    } else if (info.update) {
      text.append('发现新版本 ');
      const version = document.createElement('b');
      version.style.color = 'var(--accent)';
      version.textContent = info.latest || info.ver || '';
      text.append(version, '，可下载更新。');
    } else {
      text.textContent = `已是最新版本 v${state.version}。`;
    }

    // 更新日志常驻显示：即使已是最新版本，也可以回看当前版本改了什么
    const hasLog = !!(info.log && info.log.trim());
    $('update-log-wrap').hidden = !hasLog;
    if (hasLog) {
      $('update-log').textContent = info.log.trim();
      $('update-log-toggle').setAttribute('aria-expanded', 'false');
      $('update-log-toggle').innerHTML = '<span class="chevron">›</span> 展开查看更新日志';
      $('update-log').hidden = true;
    }

    const canDownload = !!(info.update && info.url);
    $('update-download').hidden = !canDownload;

    if (info.must_update && !state.forcedShown) {
      state.forcedShown = true;
      showForcedUpdate();
    } else if (info.update && !info.must_update && !state.optionalShown) {
      showOptionalUpdate();
    }
  }

  function showOptionalUpdate() {
    const info = state.announce || {};
    state.optionalShown = true;
    $('optional-current').textContent = `v${state.version}`;
    $('optional-latest').textContent = `v${info.latest || info.ver || ''}`;
    const log = (info.log || '').trim();
    $('optional-log').textContent = log;
    $('optional-log').hidden = !log;
    $('optional-update-modal').hidden = false;
    $('optional-download').onclick = async () => {
      if (info.url) {
        await openUrl(info.url);
      } else {
        toast('更新地址缺失，请联系作者', 'error');
      }
    };
  }

  function hideOptionalUpdate() {
    $('optional-update-modal').hidden = true;
  }

  function showForcedUpdate() {
    const info = state.announce || {};
    $('modal-current').textContent = `v${state.version}`;
    $('modal-latest').textContent = `v${info.latest || info.ver || ''}`;
    $('modal-log').textContent = (info.log || '暂无更新说明').trim();
    $('update-modal').hidden = false;
    $('modal-update').onclick = async () => {
      if (info.url) {
        await openUrl(info.url);
        $('modal-update').textContent = '已打开下载页';
        $('modal-update').disabled = true;
      } else {
        toast('更新地址缺失，请联系作者', 'error');
      }
    };
    $('modal-quit').onclick = async () => {
      try {
        await action('quit');
      } catch (error) {
        // 退出时连接关闭属正常
      }
      document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font-family:Segoe UI,sans-serif;opacity:.7">程序已退出，可关闭此窗口。</div>';
    };
  }

  function renderQrArea() {
    const box = document.querySelector('.qr-box');
    const img = $('login-qr');
    const placeholder = $('qr-placeholder');
    const panel = $('qr-status');
    const account = state.account || {};
    const probe = state.probe || {};
    const loggedIn = !!account.logged_in;

    if (state.loginQr) {
      img.src = state.loginQr;
      img.hidden = false;
      placeholder.hidden = true;
      panel.hidden = true;
      box.classList.remove('has-status');
      box.classList.add('has-qr');
    } else {
      img.hidden = true;
      box.classList.remove('has-qr', 'has-status');
      if (loggedIn) {
        panel.hidden = false;
        placeholder.hidden = true;
        box.classList.add('has-status');
        const membership = probe.status === 'done' ? (probe.membership || '') : '';
        const tone = membership === '大会员' ? 'vip'
          : membership === '未登录' ? 'none'
            : membership === '普通用户' ? 'normal' : '';
        const icon = $('qr-status-icon');
        icon.className = 'member-icon ' + tone;
        icon.innerHTML = MEMBER_ICONS[membership] || MEMBER_ICONS.default;
        $('qr-status-badge').textContent = probe.status === 'checking' ? '已登录' : (membership || '已登录');
        $('qr-status-sub').textContent = probe.status === 'checking'
          ? '正在检测会员等级…'
          : (probe.max_label ? `最高画质 ${probe.max_label}` : '');
        $('qr-status-uid').textContent = account.mid ? `UID ${account.mid}` : '';
      } else {
        panel.hidden = true;
        placeholder.hidden = false;
        placeholder.textContent = state.loginStatus === 'waiting'
          ? '正在获取二维码…'
          : '点击右侧“获取二维码”';
      }
    }

    const button = $('login-refresh');
    button.textContent = state.loginQr ? '刷新二维码' : (loggedIn ? '重新登录' : '获取二维码');
  }

  function renderAccount() {
    const account = state.account || {};
    const probe = state.probe || {};
    const online = !!account.logged_in;
    $('brand-sub').textContent = `v${state.version} · By ${state.publisher}`;
    $('status-version').textContent = `v${state.version}`;
    $('about-version').textContent = `v${state.version}`;

    let text = online ? (account.mid ? `已登录（UID ${account.mid}）` : '已登录') : '未登录';
    if (online) {
      if (probe.status === 'checking') {
        text += ' · 正在检测会员等级…';
      } else if (probe.status === 'done') {
        text += ` · ${probe.membership || '未知'}`;
        if (probe.max_label) text += `（最高 ${probe.max_label}）`;
      }
    }
    const status = $('login-status');
    status.textContent = text;
    status.classList.toggle(
      'ok',
      online && (probe.status !== 'done' || probe.membership !== '未登录')
    );
    renderQrArea();
  }

  function renderSettings() {
    const config = state.config || {};
    for (const binding of SETTINGS_BINDINGS) {
      const element = $(binding.id);
      if (!element) continue;
      if (binding.type === 'bool') element.checked = !!config[binding.key];
      else element.value = config[binding.key] == null ? '' : String(config[binding.key]);
    }
    $('appearance-mode').value = config.appearance_mode || 'System';
    $('encoding-select').value = config.encoding_priority || 'hevc,avc,av1';
    $('window-mode').value = config.window_mode || 'edge';
    $('video-only-switch').checked = !!config.video_only;
    $('audio-only-switch').checked = !!config.audio_only;
    syncCustomSelects();
  }

  function renderDownloadState() {
    $('start-button').disabled = state.running;
    $('stop-button').disabled = !state.running;
    $('open-output').hidden = state.running || !(state.lastOutput || state.lastOutputDir);

    const percent = Math.max(0, Math.min(100, Number(state.progress) || 0));
    $('progress-bar').style.width = `${percent}%`;
    $('progress').setAttribute('aria-valuenow', String(percent));
    $('progress-text').textContent = state.running
      ? `正在下载 · ${percent}%`
      : (state.result || (percent >= 100 ? '已完成' : '等待开始'));
  }

  function appendLog(lines) {
    const output = $('log-output');
    if (!lines || !lines.length) return;
    const nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 40;
    output.textContent += (output.textContent ? '\n' : '') + lines.join('\n');
    if (nearBottom) output.scrollTop = output.scrollHeight;
  }

  // ---------------------------------------------------------------- //
  //  状态同步
  // ---------------------------------------------------------------- //
  function applyState(data) {
    state.version = data.version || state.version;
    state.publisher = data.publisher || state.publisher;
    state.defaultDir = data.default_dir || state.defaultDir;
    state.config = data.config || {};
    state.appearance = data.appearance || state.appearance;
    state.account = data.account || state.account;
    state.probe = data.probe || state.probe || {};
    state.running = !!data.running;
    state.progress = data.progress || 0;
    state.history = data.history || [];
    state.announce = data.announce || {};
    state.coreFiles = data.core_files || [];
    state.result = data.last_result || '';
    state.lastOutput = data.last_output || '';
    state.lastOutputDir = data.last_output_dir || '';

    applyAppearance();
    applySidebar(!!state.config.sidebar_collapsed);
    renderAccount();
    renderCoreFiles();
    renderAnnounce();
    if ($('settings-dirty').hidden) renderSettings();
    renderDownloadState();
    showPage(document.querySelector('.page.active')?.id.replace('page-', '') || 'home', true);
    scheduleProbePoll();
    syncCustomSelects();
  }

  let probeTimer = null;

  function scheduleProbePoll() {
    clearTimeout(probeTimer);
    if ((state.probe || {}).status !== 'checking') return;
    probeTimer = setTimeout(async () => {
      await refreshState();
      scheduleProbePoll();
    }, 1200);
  }

  async function refreshState() {
    try {
      applyState(await action('state'));
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  // ---------------------------------------------------------------- //
  //  轮询
  // ---------------------------------------------------------------- //
  let wasRunning = false;

  async function poll() {
    try {
      const data = await action('status', { since: state.seq });
      if (data.seq < state.seq) {
        $('log-output').textContent = '';
        state.seq = 0;
      }
      if (data.first > state.seq) $('log-output').textContent = '';
      appendLog(data.lines || []);
      state.seq = data.seq;
      state.progress = data.progress || 0;
      state.result = data.result || state.result;
      state.lastOutput = data.last_output || '';
      state.lastOutputDir = data.last_output_dir || '';

      const running = !!data.running;
      if (running !== state.running) {
        state.running = running;
        renderDownloadState();
        if (running) {
          wasRunning = true;
        } else if (wasRunning) {
          wasRunning = false;
          const ok = (data.result || '').includes('完成');
          if (data.result) toast(data.result, ok ? 'info' : 'error');
          await refreshState();
        }
      } else {
        renderDownloadState();
      }
    } catch (error) {
      // 服务退出时忽略
    }
    setTimeout(poll, state.running ? 450 : 1400);
  }

  // ---------------------------------------------------------------- //
  //  下载
  // ---------------------------------------------------------------- //
  function currentUrl() {
    return ($('url-input').value || '').trim();
  }

  async function startDownload(url) {
    if (state.running) return toast('已有下载任务在运行', 'error');
    if (!url) {
      toast('请先填写视频地址', 'error');
      $('url-input').focus();
      return;
    }

    const mode = $('part-mode').value;
    let page = '';
    if (mode === 'specific') page = ($('page-range').value || '').trim();
    else if (mode === 'last') page = 'LAST';
    if (mode === 'specific' && !page) return toast('请输入分 P 编号或范围', 'error');

    try {
      await action('start_download', {
        url,
        page,
        quality: $('quality-select').value,
        video_only: $('video-only-switch').checked,
        audio_only: $('audio-only-switch').checked,
      });
      $('log-output').textContent = '';
      state.seq = 0;
      state.progress = 0;
      state.result = '';
      state.running = true;
      wasRunning = true;
      renderDownloadState();
      toast('已开始下载');
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  // ---------------------------------------------------------------- //
  //  登录
  // ---------------------------------------------------------------- //
  let loginTimer = null;

  function renderLogin(data) {
    state.loginStatus = data.status || 'idle';
    if (data.status === 'success' || data.status === 'failed') {
      state.loginQr = '';
    } else {
      state.loginQr = data.qr || '';
    }
    if (data.probe) state.probe = data.probe;
    if (data.account) state.account = data.account;
    $('login-message').textContent = data.message || '';
    renderAccount();
    renderQrArea();

    if (data.status === 'success') {
      clearTimeout(loginTimer);
      $('login-refresh').disabled = false;
      toast('登录成功');
    } else if (data.status === 'failed') {
      clearTimeout(loginTimer);
      $('login-refresh').disabled = false;
    }
  }

  async function refreshLogin(initial = false) {
    try {
      const data = await action('login_status');
      renderLogin(data);
      clearTimeout(loginTimer);
      if (data.status === 'waiting' || data.status === 'scanned') {
        loginTimer = setTimeout(() => refreshLogin(false), 1200);
      }
    } catch (error) {
      if (!initial) toast(error.message, 'error');
    }
  }

  // ---------------------------------------------------------------- //
  //  设置
  // ---------------------------------------------------------------- //
  function collectSettings() {
    const patch = {};
    for (const binding of SETTINGS_BINDINGS) {
      const element = $(binding.id);
      if (!element) continue;
      patch[binding.key] = binding.type === 'bool' ? element.checked : element.value;
    }
    patch.video_only = $('video-only-switch').checked;
    patch.audio_only = $('audio-only-switch').checked;
    patch.appearance_mode = $('appearance-mode').value;
    return patch;
  }

  function markDirty() { $('settings-dirty').hidden = false; }
  function resetDirty() { $('settings-dirty').hidden = true; }

  async function saveSettings() {
    try {
      const result = await action('save_config', { patch: collectSettings() });
      state.config = result.config;
      applyAppearance(result.appearance);
      renderSettings();
      resetDirty();
      toast('设置已保存');
      return true;
    } catch (error) {
      toast(error.message, 'error');
      return false;
    }
  }

  // ---------------------------------------------------------------- //
  //  WinUI 风格下拉
  // ---------------------------------------------------------------- //
  const customSelects = [];

  function enhanceAllSelects() {
    document.querySelectorAll('select').forEach(enhanceSelect);
    const pagesEl = document.querySelector('.pages');
    if (pagesEl) {
      pagesEl.addEventListener('scroll', () => {
        customSelects.forEach((entry) => entry.close());
      }, { passive: true });
    }
  }

  function syncCustomSelects() {
    customSelects.forEach((entry) => entry.sync());
  }

  function enhanceSelect(select) {
    if (select.dataset.enhanced === '1') return;
    select.dataset.enhanced = '1';

    const wrap = document.createElement('div');
    wrap.className = 'select';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add('select-native');
    select.tabIndex = -1;

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');

    const label = document.createElement('span');
    label.className = 'select-value';

    const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('viewBox', '0 0 24 24');
    chevron.setAttribute('class', 'select-chevron');
    const chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chevronPath.setAttribute('d', 'M7 10l5 5 5-5z');
    chevronPath.setAttribute('fill', 'currentColor');
    chevron.appendChild(chevronPath);
    trigger.append(label, chevron);
    wrap.appendChild(trigger);

    const menu = document.createElement('div');
    menu.className = 'select-menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;
    document.body.appendChild(menu);

    let open = false;
    let index = -1;

    function sync() {
      const option = select.options[select.selectedIndex] || select.options[0];
      label.textContent = option ? option.textContent : '';
      [...menu.children].forEach((item, i) => {
        const selected = i === select.selectedIndex;
        item.classList.toggle('selected', selected);
        item.setAttribute('aria-selected', selected ? 'true' : 'false');
      });
    }

    function highlight() {
      [...menu.children].forEach((item, i) => item.classList.toggle('focus', i === index));
      const current = menu.children[index];
      if (current) current.scrollIntoView({ block: 'nearest' });
    }

    function build() {
      menu.innerHTML = '';
      [...select.options].forEach((option, i) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'select-option';
        item.setAttribute('role', 'option');
        const text = document.createElement('span');
        text.textContent = option.textContent;
        const check = document.createElement('span');
        check.className = 'select-check';
        check.textContent = '✓';
        item.append(text, check);
        item.addEventListener('click', (event) => {
          event.stopPropagation();
          choose(i);
        });
        item.addEventListener('mouseenter', () => {
          index = i;
          highlight();
        });
        menu.appendChild(item);
      });
      sync();
    }

    function choose(i) {
      if (i < 0 || i >= select.options.length) return;
      select.selectedIndex = i;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      sync();
      close();
      trigger.focus();
    }

    function position() {
      const rect = trigger.getBoundingClientRect();
      menu.style.visibility = 'hidden';
      menu.hidden = false;
      const width = Math.min(Math.max(rect.width, 200), window.innerWidth - 16);
      menu.style.width = `${width}px`;
      const height = menu.offsetHeight;
      const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
      let top = rect.bottom + 4;
      if (top + height > window.innerHeight - 8) {
        top = Math.max(8, rect.top - height - 4);
      }
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      menu.style.visibility = '';
    }

    function openMenu() {
      customSelects.forEach((entry) => {
        if (entry !== state) entry.close();
      });
      build();
      open = true;
      index = select.selectedIndex >= 0 ? select.selectedIndex : 0;
      trigger.setAttribute('aria-expanded', 'true');
      menu.hidden = false;
      position();
      highlight();
    }

    function close() {
      if (!open) return;
      open = false;
      menu.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
    }

    trigger.addEventListener('click', (event) => {
      event.stopPropagation();
      if (open) close();
      else openMenu();
    });

    trigger.addEventListener('keydown', (event) => {
      if (!open) {
        if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
          event.preventDefault();
          openMenu();
        }
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        index = (index + step + menu.children.length) % menu.children.length;
        highlight();
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        choose(index);
      } else if (event.key === 'Tab') {
        close();
      }
    });

    select.addEventListener('change', sync);

    const state = { trigger, menu, close, sync, get open() { return open; } };
    customSelects.push(state);
    build();
  }

  document.addEventListener('click', (event) => {
    customSelects.forEach((entry) => {
      if (entry.open && !entry.menu.contains(event.target) && !entry.trigger.contains(event.target)) {
        entry.close();
      }
    });
  });
  window.addEventListener('resize', () => customSelects.forEach((entry) => entry.close()));

  // ---------------------------------------------------------------- //
  //  事件
  // ---------------------------------------------------------------- //
  function bind() {
    document.querySelectorAll('.nav-item').forEach((item) => {
      const label = item.querySelector('span');
      if (label) item.title = label.textContent;
      item.addEventListener('click', () => showPage(item.dataset.page));
    });

    $('sidebar-toggle').addEventListener('click', async () => {
      const collapsed = !document.body.classList.contains('sidebar-collapsed');
      applySidebar(collapsed);
      requestAnimationFrame(() => moveNavIndicator(false));
      setTimeout(() => moveNavIndicator(false), 240);
      state.config.sidebar_collapsed = collapsed;
      try {
        const result = await action('save_config', { patch: { sidebar_collapsed: collapsed } });
        state.config = result.config;
      } catch (error) {
        toast(error.message, 'error');
      }
    });

    $('settings-nav').addEventListener('click', (event) => {
      const item = event.target.closest('.settings-nav-item');
      if (!item) return;
      const target = document.getElementById(item.dataset.target);
      if (!target) return;
      const pages = document.querySelector('.pages');
      const top = pages.scrollTop + target.getBoundingClientRect().top - pages.getBoundingClientRect().top - 12;
      settingsNavLockUntil = performance.now() + 1200;
      pages.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
      setSettingsNavActive(item.dataset.target, true);
    });

    const pagesEl = document.querySelector('.pages');
    pagesEl.addEventListener('scroll', () => {
      clearTimeout(settingsScrollTimer);
      settingsScrollTimer = setTimeout(updateSettingsNav, 90);
    }, { passive: true });
    pagesEl.addEventListener('scrollend', () => {
      settingsNavLockUntil = 0;
      updateSettingsNav();
    }, { passive: true });

    $('appearance-mode').addEventListener('change', async (event) => {
      const mode = event.target.value;
      applyAppearance({ mode, color: state.appearance.color });
      try {
        const result = await action('save_config', { patch: { appearance_mode: mode } });
        state.config = result.config;
      } catch (error) {
        toast(error.message, 'error');
      }
    });

    $('theme-color').addEventListener('change', markDirty);

    // 首页
    $('quick-download').addEventListener('click', () => showPage('download'));
    $('quick-login').addEventListener('click', () => showPage('login'));
    $('update-download').addEventListener('click', () => openUrl(state.announce.url));
    $('update-log-toggle').addEventListener('click', () => {
      const button = $('update-log-toggle');
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      button.innerHTML = expanded
        ? '<span class="chevron">›</span> 展开查看更新日志'
        : '<span class="chevron">›</span> 收起更新日志';
      $('update-log').hidden = expanded;
    });

    // 下载
    $('paste-button').addEventListener('click', async () => {
      try {
        const data = await action('clipboard');
        const text = (data.text || '').trim();
        if (!text) return toast('剪贴板是空的', 'error');
        $('url-input').value = text.split('\n')[0].trim();
      } catch (error) {
        toast(error.message, 'error');
      }
    });
    $('clear-url').addEventListener('click', () => {
      $('url-input').value = '';
      $('url-input').focus();
    });
    $('url-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') startDownload(currentUrl());
    });
    $('start-button').addEventListener('click', () => startDownload(currentUrl()));
    $('stop-button').addEventListener('click', async () => {
      try {
        await action('stop_download');
        toast('正在停止…');
      } catch (error) {
        toast(error.message, 'error');
      }
    });
    $('open-output').addEventListener('click', async () => {
      try {
        const result = await action('open_output');
        toast(result.message || '已打开');
      } catch (error) {
        toast(error.message, 'error');
      }
    });
    $('part-mode').addEventListener('change', (event) => {
      $('page-range-field').hidden = event.target.value !== 'specific';
    });
    $('encoding-select').addEventListener('change', (event) => {
      action('save_config', { patch: { encoding_priority: event.target.value } })
        .then((result) => { state.config = result.config; })
        .catch((error) => toast(error.message, 'error'));
    });
    $('clear-log').addEventListener('click', () => { $('log-output').textContent = ''; });

    const syncModes = (source) => {
      if (source === 'video' && $('video-only-switch').checked) $('audio-only-switch').checked = false;
      if (source === 'audio' && $('audio-only-switch').checked) $('video-only-switch').checked = false;
    };
    $('video-only-switch').addEventListener('change', () => syncModes('video'));
    $('audio-only-switch').addEventListener('change', () => syncModes('audio'));

    // 登录
    $('login-refresh').addEventListener('click', async () => {
      $('login-refresh').disabled = true;
      $('login-message').textContent = '正在获取二维码…';
      try {
        const data = await action('login_start');
        renderLogin(data);
        clearTimeout(loginTimer);
        loginTimer = setTimeout(() => refreshLogin(false), 1200);
      } catch (error) {
        $('login-refresh').disabled = false;
        toast(error.message, 'error');
      }
    });
    $('login-qr').addEventListener('click', () => {
      const src = $('login-qr').src;
      if (!src) return;
      $('qr-zoom-img').src = src;
      $('qr-zoom').hidden = false;
    });
    $('qr-zoom').addEventListener('click', () => { $('qr-zoom').hidden = true; });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      if (!$('qr-zoom').hidden) $('qr-zoom').hidden = true;
      if (!$('license-modal').hidden) $('license-modal').hidden = true;
      if (!$('optional-update-modal').hidden) hideOptionalUpdate();
    });

    $('login-check').addEventListener('click', async () => {
      const button = $('login-check');
      const box = $('login-check-result');
      button.disabled = true;
      box.hidden = true;
      $('login-check-qualities').hidden = true;
      $('login-log-hint').hidden = true;
      $('login-message').textContent = '正在用 ss1177 检测登录状态…';
      try {
        const data = await action('login_check');
        const ok = !!data.logged_in;
        state.probe = data;
        if (ok) {
          const bits = [`登录状态正常${data.account ? '：' + data.account : ''}`];
          if (data.membership) bits.push(data.membership);
          if (data.max_label) bits.push(`最高 ${data.max_label}`);
          $('login-message').textContent = bits.join(' · ');
        } else {
          $('login-message').textContent = '未登录或凭证已失效（ss1177 仍可解析，但无法下载会员内容）';
        }
        $('login-status').textContent = ok ? (data.account || '已登录') : '未登录';
        $('login-status').classList.toggle('ok', ok);

        const qualities = data.qualities || [];
        const chips = $('login-check-qualities');
        chips.innerHTML = '';
        qualities.forEach((quality) => {
          const chip = document.createElement('span');
          chip.className = 'quality-chip';
          chip.textContent = quality;
          chips.appendChild(chip);
        });
        chips.hidden = !qualities.length;

        const detailed = (state.config.log_level || 'simple') === 'detail';
        box.textContent = data.detail || '无输出';
        box.hidden = !detailed;
        $('login-log-hint').hidden = detailed;
        if (!data.parsed) toast('解析未完成，请检查网络', 'error');
      } catch (error) {
        $('login-message').textContent = '';
        toast(error.message, 'error');
      } finally {
        button.disabled = false;
      }
    });

    $('login-logout').addEventListener('click', async () => {
      if (!state.account.logged_in) return toast('当前未登录');
      if (!(await confirmAction('退出登录会删除本机的 BBDown.data 凭证，确定继续？', '退出登录'))) return;
      try {
        const data = await action('logout');
        state.account = data.account;
        state.probe = { status: 'idle' };
        state.loginQr = '';
        state.loginStatus = 'idle';
        renderAccount();
        toast('已退出登录');
      } catch (error) {
        toast(error.message, 'error');
      }
    });

    // 设置
    SETTINGS_BINDINGS.forEach((binding) => {
      const element = $(binding.id);
      if (!element) return;
      element.addEventListener('change', markDirty);
      if (binding.type === 'text') element.addEventListener('input', markDirty);
    });
    $('video-only-switch').addEventListener('change', markDirty);
    $('audio-only-switch').addEventListener('change', markDirty);
    $('save-settings').addEventListener('click', saveSettings);
    $('open-debug').addEventListener('click', async () => {
      try {
        await action('debug_enable');
        openDebugWindow();
      } catch (error) {
        toast(error.message, 'error');
      }
    });
    $('leave-cancel').addEventListener('click', () => {
      $('leave-modal').hidden = true;
      pendingLeavePage = null;
    });
    $('leave-discard').addEventListener('click', () => {
      $('leave-modal').hidden = true;
      resetDirty();
      renderSettings();
      const target = pendingLeavePage;
      pendingLeavePage = null;
      if (target) showPage(target, true);
    });
    $('leave-save').addEventListener('click', async () => {
      const target = pendingLeavePage;
      $('leave-save').disabled = true;
      const saved = await saveSettings();
      $('leave-save').disabled = false;
      if (!saved) return;
      $('leave-modal').hidden = true;
      pendingLeavePage = null;
      if (target) showPage(target, true);
    });
    $('reset-settings').addEventListener('click', async () => {
      if (!(await confirmAction('将把所有设置恢复为默认值，确定继续？', '恢复默认'))) return;
      try {
        const result = await action('reset_config');
        state.config = result.config;
        applyAppearance(result.appearance);
        applySidebar(!!state.config.sidebar_collapsed);
        renderSettings();
        resetDirty();
        toast('已恢复默认设置');
      } catch (error) {
        toast(error.message, 'error');
      }
    });

    $('pick-work-dir').addEventListener('click', async () => {
      try {
        const data = await action('pick_dir', { kind: 'dir' });
        if (data.path) { $('work-dir').value = data.path; markDirty(); }
      } catch (error) { toast(error.message, 'error'); }
    });
    $('pick-output-dir').addEventListener('click', async () => {
      try {
        const data = await action('pick_dir', { kind: 'dir' });
        if (data.path) { $('output-dir').value = data.path; markDirty(); }
      } catch (error) { toast(error.message, 'error'); }
    });
    $('pick-ffmpeg').addEventListener('click', async () => {
      try {
        const data = await action('pick_dir', { kind: 'ffmpeg' });
        if (data.path) { $('ffmpeg-path').value = data.path; markDirty(); }
      } catch (error) { toast(error.message, 'error'); }
    });
    $('pick-aria2c').addEventListener('click', async () => {
      try {
        const data = await action('pick_dir', { kind: 'aria2c' });
        if (data.path) { $('aria2c-path').value = data.path; markDirty(); }
      } catch (error) { toast(error.message, 'error'); }
    });
    $('open-work-dir').addEventListener('click', async () => {
      const path = $('work-dir').value.trim() || state.config.work_dir || state.defaultDir || '';
      if (!path) return toast('尚未设置下载目录', 'error');
      try {
        await action('open_path', { path });
      } catch (error) { toast(error.message, 'error'); }
    });

    // 关于
    document.querySelectorAll('[data-url]').forEach((button) => {
      button.addEventListener('click', () => openUrl(button.dataset.url));
    });
    $('open-license').addEventListener('click', async () => {
      const modal = $('license-modal');
      const text = $('license-text');
      text.textContent = '正在获取许可文本…';
      modal.hidden = false;
      try {
        const data = await action('license');
        text.textContent = (data.text || '').trim() || '（许可文本为空）';
      } catch (error) {
        text.textContent = '获取失败：' + error.message;
      }
    });
    $('license-close').addEventListener('click', () => { $('license-modal').hidden = true; });
    $('license-modal').addEventListener('click', (event) => {
      if (event.target === $('license-modal')) $('license-modal').hidden = true;
    });

    $('optional-later').addEventListener('click', hideOptionalUpdate);
    $('optional-update-close').addEventListener('click', hideOptionalUpdate);
    $('optional-update-modal').addEventListener('click', (event) => {
      if (event.target === $('optional-update-modal')) hideOptionalUpdate();
    });

    $('check-update').addEventListener('click', async () => {
      $('check-update').disabled = true;
      try {
        const data = await action('check_update');
        state.announce = data.announce;
        renderAnnounce();
        const info = data.announce || {};
        if (info.must_update) showForcedUpdate();
        else if (info.update) showOptionalUpdate();
        else toast('已是最新版本');
        $('about-update-hint').textContent = info.fetched ? '公告已更新' : (info.error || '');
      } catch (error) {
        toast(error.message, 'error');
      } finally {
        $('check-update').disabled = false;
      }
    });
    $('quit-button').addEventListener('click', async () => {
      if (!(await confirmAction('确定退出 BiliDownloader？', '退出'))) return;
      try {
        await action('quit');
      } catch (error) {
        // 退出时连接关闭属正常
      }
      document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font-family:Segoe UI,sans-serif;opacity:.7">程序已退出，可关闭此窗口。</div>';
    });

    window.addEventListener('beforeunload', (event) => {
      if ($('settings-dirty').hidden) return;
      event.preventDefault();
      event.returnValue = '';
    });

    window.addEventListener('keydown', (event) => {
      if (!event.ctrlKey || event.altKey) return;
      const map = { 1: 'home', 2: 'download', 3: 'login', 4: 'settings', 5: 'about' };
      if (map[event.key]) {
        event.preventDefault();
        showPage(map[event.key]);
      }
    });
  }

  // ---------------------------------------------------------------- //
  //  启动
  // ---------------------------------------------------------------- //
  function setSplash(text) {
    const element = $('splash-status');
    if (element) element.textContent = text;
  }

  function hideSplash() {
    const splash = $('splash');
    if (!splash) return;
    splash.classList.add('hide');
    setTimeout(() => { splash.hidden = true; }, 400);
  }

  async function waitForAnnounce(maxMs = 9000) {
    const started = Date.now();
    while (Date.now() - started < maxMs) {
      const info = state.announce || {};
      if (info.fetched || info.error) return;
      await new Promise((resolve) => setTimeout(resolve, 400));
      try {
        await refreshState();
      } catch (error) {
        return;
      }
    }
  }

  async function init() {
    enhanceAllSelects();
    bind();
    const started = Date.now();
    const initialHash = (location.hash || '').replace('#', '');

    setSplash('正在连接本地服务…');
    let ready = true;
    try {
      await refreshState();
    } catch (error) {
      ready = false;
      toast('无法连接本地服务：' + error.message, 'error');
    }

    if (ready) {
      setSplash('正在获取公告与版本信息…');
      await waitForAnnounce(9000);
    }

    const elapsed = Date.now() - started;
    if (elapsed < 900) {
      await new Promise((resolve) => setTimeout(resolve, 900 - elapsed));
    }

    const info = state.announce || {};
    setSplash(info.error ? '网络不可用，进入离线界面…' : '准备就绪，正在进入…');
    await new Promise((resolve) => setTimeout(resolve, 220));
    hideSplash();

    if (PAGE_META[initialHash]) showPage(initialHash);
    window.addEventListener('hashchange', () => {
      const page = (location.hash || '').replace('#', '');
      if (PAGE_META[page]) showPage(page);
    });
    poll();

    if (!state.announce.fetched && !state.announce.error) {
      setTimeout(() => { refreshState().catch(() => {}); }, 3000);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
