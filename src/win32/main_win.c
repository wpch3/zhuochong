/*
 * main_win.c - Windows 桌宠主程序入口
 *
 * 用法：
 *   zhuochong.exe [--config config] [--check] [--scale 0.6] [--form teen] [--outfit default]
 *   --check   只校验配置与角色包，不显示窗口（用于脚本与排错）
 *
 * 设计约束（交接文件第六节）：
 *   - 数据全部本机：日志与运行状态写在程序目录下，不联网；
 *   - 出错要能指出文件与字段，并且不崩溃。
 */
#ifndef _WIN32
#error "main_win.c 只能在 Windows 目标上编译"
#endif

#ifndef WINVER
#  define WINVER 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#include "../core/zpet.h"
#include "../core/zconfig.h"
#include "zw32.h"

#include <stdio.h>

/* 取可执行文件所在目录 */
static void exe_dir(char *out, size_t cap)
{
    wchar_t wpath[1024];
    char utf8[1024];
    DWORD n = GetModuleFileNameW(NULL, wpath, 1024);
    if (n == 0 || n >= 1024) { z_strlcpy(out, ".", cap); return; }
    /* 去掉文件名 */
    {
        wchar_t *p = wcsrchr(wpath, L'\\');
        if (p) *p = 0;
    }
    WideCharToMultiByte(CP_UTF8, 0, wpath, -1, utf8, sizeof(utf8), NULL, NULL);
    z_strlcpy(out, utf8, cap);
}

/* 查找项目根：优先 exe 目录（安装版），否则向上找 config/ 与 characters/ */
static int find_root(const char *start, char *out, size_t cap)
{
    char cur[1024];
    int depth;
    z_strlcpy(cur, start, sizeof(cur));
    for (depth = 0; depth < 4; ++depth) {
        char probe[1200];
        z_path_join(probe, sizeof(probe), cur, "config/pet.json");
        if (z_file_exists(probe)) {
            z_strlcpy(out, cur, cap);
            return 0;
        }
        z_dirname(cur);
        if (z_streq(cur, ".") || !cur[0]) break;
    }
    return -1;
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR cmdline, int show)
{
    zconfig cfg;
    zdiag diag;
    zpet *pet;
    zw32 *win;
    char config_dir[1200] = {0};
    char root[1200] = {0};
    char log_path[1200];
    int check_only = 0;
    int argc = 0;
    LPWSTR *argv;

    (void)hInst; (void)hPrev; (void)cmdline; (void)show;

    zdiag_init(&diag);
    zlog_set_level(ZLOG_INFO);

    /* 参数（宽字符命令行） */
    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    {
        int i;
        for (i = 1; i < argc; ++i) {
            char arg[256];
            WideCharToMultiByte(CP_UTF8, 0, argv[i], -1, arg, sizeof(arg), NULL, NULL);
            if (z_streq(arg, "--check")) check_only = 1;
            else if (z_streq(arg, "--config") && i + 1 < argc) {
                WideCharToMultiByte(CP_UTF8, 0, argv[i + 1], -1, config_dir, sizeof(config_dir), NULL, NULL);
                i++;
            }
        }
    }
    if (argv) LocalFree(argv);

    if (!config_dir[0]) {
        char base[1024];
        exe_dir(base, sizeof(base));
        if (find_root(base, root, sizeof(root)) != 0) {
            /* 开发期：exe 在 build/ 下，向上找 */
            z_strlcpy(root, base, sizeof(root));
        }
        z_path_join(config_dir, sizeof(config_dir), root, "config");
    } else {
        z_strlcpy(root, config_dir, sizeof(root));
        z_dirname(root);
    }
    z_mkdir_p(root);
    {
        char log_dir[1024];
        z_path_join(log_path, sizeof(log_path), root, "logs/pet.log");
        z_strlcpy(log_dir, log_path, sizeof(log_dir));
        z_dirname(log_dir);          /* 注意：z_dirname 会原地修改传入的缓冲 */
        z_mkdir_p(log_dir);
    }
    zlog_open(log_path);

    ZLOGI("boot", "桌宠 v%s 启动（root=%s）", ZC_VERSION, root);

    if (zconfig_load(&cfg, config_dir, &diag) != 0) {
        ZLOGE("boot", "配置加载存在致命错误：");
        zdiag_print(&diag, stderr);
        if (check_only) return 2;
        MessageBoxW(NULL,
                    L"配置文件有错误，已停止启动。\n详情见 logs/pet.log。\n\n"
                    L"提示：字段名与类型必须与 schemas/ 下的示例一致。",
                    L"桌宠 · 配置错误", MB_OK | MB_ICONERROR);
        return 2;
    }
    {
        zdiag d2;
        int i;
        for (i = 0; i < diag.count; ++i)   /* 非致命警告也要让用户看到 */
            if (!z_startswith(diag.items[i].msg, "字段缺失"))
                ZLOGW("config", "%s:%d %s: %s", diag.items[i].file, diag.items[i].line,
                      diag.items[i].field, diag.items[i].msg);
        zdiag_init(&d2);
        pet = zpet_create(&cfg, &d2);
        if (!pet) {
            ZLOGE("boot", "角色包加载失败：");
            zdiag_print(&d2, stderr);
            if (!check_only)
                MessageBoxW(NULL, L"角色包加载失败（缺少 rig.json 或素材）。\n详情见 logs/pet.log。",
                            L"桌宠 · 角色包错误", MB_OK | MB_ICONERROR);
            return 3;
        }
    }
    zconfig_print(&cfg, stderr);

    if (check_only) {
        ZLOGI("boot", "自检通过：配置与角色包均可加载");
        zpet_destroy(pet);
        zlog_close();
        return 0;
    }

    zlog_set_level((zlog_level)cfg.pet.log_level);
    win = zw32_create(&cfg.pet, &cfg, pet, &diag);
    if (!win) {
        ZLOGE("boot", "创建窗口失败");
        zpet_destroy(pet);
        return 4;
    }
    zw32_run(win);
    zw32_destroy(win);
    zpet_destroy(pet);
    ZLOGI("boot", "退出");
    zlog_close();
    return 0;
}
