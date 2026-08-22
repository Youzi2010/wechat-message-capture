# -*- coding: utf-8 -*-
"""
wx_probe.py - 电脑微信在线状态探针（心跳监控用，4小时一次）
================================================================================
检查三项：
  1. WeChat 进程是否在运行
  2. 微信 exe 版本是否为 4.1.7.30（升级会导致 wxauto 的 UIA 控件失效）
  3. wxauto 能否初始化并拿到登录账号（证明 wxauto 链路可用）

用法: python wx_probe.py
退出码: 0 = 全部正常; 1 = 任一项异常（输出里带「问题: ...」摘要）
"""
import os
import sys
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

EXPECTED_VERSION = '4.1.7.30'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_ps(script):
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return '', str(e), 1


def main():
    problems = []

    # 1. Weixin/WeChat 进程（微信 4.x 主进程名是 Weixin.exe，旧版是 WeChat.exe）
    out, err, rc = run_ps(
        "$p = Get-Process Weixin,WeChat -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -match 'Tencent' } | Select-Object -First 1; "
        "if ($p) { Write-Output $p.Path } else { Write-Output 'NO_PROCESS' }"
    )
    path = (out or '').strip()
    if rc != 0 or not path or path == 'NO_PROCESS':
        problems.append('微信进程未运行（电脑微信没开/被退出）')
        print('进程: FAIL (微信进程未运行)')
    else:
        print(f'进程: OK ({path})')

        # 2. 版本（取主进程文件版本，如 4.1.7.30）
        out2, err2, rc2 = run_ps(f"(Get-Item '{path}').VersionInfo.FileVersion")
        ver = (out2 or '').strip()
        if rc2 == 0 and ver:
            ok = ver.startswith(EXPECTED_VERSION)
            print(f'版本: {ver} ' + ('OK' if ok else f'⚠️ 期望 {EXPECTED_VERSION}，wxauto 可能失效'))
            if not ok:
                problems.append(f'微信版本变化: {ver}（期望 {EXPECTED_VERSION}，wxauto 可能失效，勿升级）')
        else:
            problems.append('无法读取微信 exe 版本')
            print('版本: FAIL (无法读取)')

    # 3. wxauto 初始化
    try:
        sys.path.insert(0, BASE_DIR)
        from wechat_client import WeChatClient
        c = WeChatClient(ads=True)
        print(f'wxauto: OK (登录账号: {c.nickname})')
    except Exception as e:
        problems.append(f'wxauto 初始化失败: {e}')
        print(f'wxauto: FAIL ({e})')

    if problems:
        print('问题: ' + '; '.join(problems))
        sys.exit(1)
    print('全部正常')
    sys.exit(0)


if __name__ == '__main__':
    main()
