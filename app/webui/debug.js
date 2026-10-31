/* BBDown 调试控制台 */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  let seq = 0;
  let running = false;
  let timer = null;
  let history = [];
  let cursor = -1;

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

  function append(lines) {
    const log = $('debug-log');
    if (!lines || !lines.length) return;
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    log.textContent += (log.textContent ? '\n' : '') + lines.join('\n');
    if (nearBottom) log.scrollTop = log.scrollHeight;
  }

  function showOff() {
    $('debug-wrap').hidden = true;
    $('debug-off').hidden = false;
    clearTimeout(timer);
  }

  async function poll() {
    try {
      const data = await action('debug_state', { since: seq });
      if (!data.enabled) {
        showOff();
        return;
      }
      if (data.seq < seq) {
        $('debug-log').textContent = '';
        seq = 0;
      }
      if (data.first > seq) {
        $('debug-log').textContent = '';
      }
      append(data.lines || []);
      seq = data.seq;
      running = !!data.running;
      const status = $('debug-status');
      status.textContent = running ? '运行中' : '空闲';
      status.classList.toggle('busy', running);
      $('debug-stop').disabled = !running;
    } catch (error) {
      $('debug-status').textContent = '连接失败';
    }
    timer = setTimeout(poll, 600);
  }

  async function send() {
    const input = $('debug-input');
    const command = input.value.trim();
    if (!command) return;
    history.unshift(command);
    if (history.length > 50) history.pop();
    cursor = -1;
    input.value = '';
    try {
      await action('debug_run', { command });
    } catch (error) {
      $('debug-log').textContent += `\n[error] ${error.message}`;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    $('debug-send').addEventListener('click', send);
    $('debug-input').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        send();
      } else if (event.key === 'ArrowUp') {
        if (cursor < history.length - 1) {
          cursor += 1;
          $('debug-input').value = history[cursor];
        }
        event.preventDefault();
      } else if (event.key === 'ArrowDown') {
        if (cursor > 0) {
          cursor -= 1;
          $('debug-input').value = history[cursor];
        } else {
          cursor = -1;
          $('debug-input').value = '';
        }
        event.preventDefault();
      }
    });

    $('debug-stop').addEventListener('click', () => {
      action('debug_stop').catch((error) => {
        $('debug-log').textContent += `\n[error] ${error.message}`;
      });
    });

    $('debug-clear').addEventListener('click', async () => {
      try {
        await action('debug_clear');
      } catch (error) {
        // 清空失败时仍清本地显示
      }
      $('debug-log').textContent = '';
      seq = 0;
    });

    poll();
  });
})();
