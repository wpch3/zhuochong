/* zw32.c - Windows 平台层实现 */
#ifndef _WIN32
#error "zw32.c 只能在 Windows 目标上编译（交叉编译请用 zig cc -target x86_64-windows-gnu）"
#endif

#ifndef WINVER
#  define WINVER 0x0601
#endif
#ifndef _WIN32_WINNT
#  define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <shellapi.h>

#include "zw32.h"
#include "../core/zimg.h"

#include <math.h>

#define ZW_CLASS_NAME L"ZhuochongPetWindow"
#define ZW_TRAY_ID    1
#define ZW_MSG_TRAY   (WM_APP + 1)
#define ZW_HOTKEY_SCALE_UP   1
#define ZW_HOTKEY_SCALE_DOWN 2
#define ZW_HOTKEY_THROUGH    3

/* 菜单命令范围 */
#define ZW_CMD_EXIT        100
#define ZW_CMD_ABOUT       101
#define ZW_CMD_OPEN_CONFIG 102
#define ZW_CMD_TOP_TOGGLE  103
#define ZW_CMD_THROUGH     104
#define ZW_CMD_SCALE_UP    105
#define ZW_CMD_SCALE_DOWN  106
#define ZW_CMD_SCALE_RESET 107
#define ZW_CMD_TOOL_HAND   108
#define ZW_CMD_TOOL_HAMMER 109
#define ZW_CMD_SLEEP       110
#define ZW_CMD_WAKE        111
#define ZW_CMD_FORM_BASE   1000   /* +i */
#define ZW_CMD_OUTFIT_BASE 1100   /* +i */
#define ZW_CMD_ACTION_BASE 1200   /* +i */

struct zw32 {
    HWND        hwnd;
    zpet       *pet;
    zconfig    *conf;
    HWND        owner;        /* 隐藏的 owner 窗口（用于菜单与热键） */

    /* 渲染 */
    HDC         hdc_screen;
    HDC         hdc_mem;
    HBITMAP     hbmp;
    void       *bits;
    int         bw, bh;
    int         hit_w, hit_h;
    unsigned char *hit;       /* alpha 命中缓冲（bw*bh） */
    double      last_scale;
    int         last_frame_serial;

    /* 窗口位置 */
    int         wx, wy;
    int         pos_known;

    /* 输入 */
    int         dragging;
    POINT       drag_pt;
    int         win_origin_x, win_origin_y;
    int         mouse_inside;
    POINT       last_mouse;
    int         click_through_all;
    int         pending_click;    /* 按下后未拖动 → 抬起时算点击 */
    zpet_tool   tool;

    /* 托盘与图标 */
    NOTIFYICONDATAW nid;
    int         tray_added;
    HICON       icon;
    HICON       icon_small;

    int         quit;
    int         fps;
    int         hit_threshold;
    double      next_frame;
    char        config_dir[1024];
    char        root_dir[1024];
};

/* ------------------------------------------------------------ 工具函数 */
static zw32 *g_instance = NULL;   /* WndProc 需要（单实例） */

static void get_work_area(RECT *rc)
{
    SystemParametersInfoW(SPI_GETWORKAREA, 0, rc, 0);
}

/* 把角色脚底中心放到屏幕右下角（首次运行） */
static void default_position(zw32 *w)
{
    RECT wa;
    int fw, fh;
    get_work_area(&wa);
    zpet_frame(w->pet, &fw, &fh);
    w->wx = wa.right - fw - 24;
    w->wy = wa.bottom - fh - 4;
}

/* 从当前帧生成 HICON（保证托盘图标与角色一致，参考 BongoCat 的做法） */
static HICON icon_from_pet(zw32 *w, int size)
{
    BITMAPV5HEADER bi;
    HDC hdc;
    HBITMAP color = NULL, mask = NULL;
    void *bits = NULL;
    ICONINFO ii;
    HICON icon = NULL;
    int fw = 0, fh = 0;
    const zimg *fr = zpet_frame(w->pet, &fw, &fh);
    int x, y;

    if (!fr) return NULL;
    memset(&bi, 0, sizeof(bi));
    bi.bV5Size = sizeof(BITMAPV5HEADER);
    bi.bV5Width = size;
    bi.bV5Height = -size;
    bi.bV5Planes = 1;
    bi.bV5BitCount = 32;
    bi.bV5Compression = BI_BITFIELDS;
    bi.bV5RedMask = 0x00FF0000;
    bi.bV5GreenMask = 0x0000FF00;
    bi.bV5BlueMask = 0x000000FF;
    bi.bV5AlphaMask = 0xFF000000;
    hdc = GetDC(NULL);
    color = CreateDIBSection(hdc, (BITMAPINFO *)&bi, DIB_RGB_COLORS, &bits, NULL, 0);
    ReleaseDC(NULL, hdc);
    if (!color || !bits) { if (color) DeleteObject(color); return NULL; }
    memset(bits, 0, (size_t)size * size * 4);
    if (fr) {
        for (y = 0; y < size; ++y) {
            for (x = 0; x < size; ++x) {
                int sx = x * fw / size;
                int sy = y * fh / size;
                const uint8_t *sp = fr->px + ((size_t)sy * fw + sx) * 4;
                uint8_t *dp = (uint8_t *)bits + ((size_t)y * size + x) * 4;
                unsigned a = sp[3];
                dp[0] = (uint8_t)(sp[2] * a / 255);
                dp[1] = (uint8_t)(sp[1] * a / 255);
                dp[2] = (uint8_t)(sp[0] * a / 255);
                dp[3] = (uint8_t)a;
            }
        }
    }
    memset(&ii, 0, sizeof(ii));
    ii.fIcon = TRUE;
    ii.hbmColor = color;
    mask = CreateBitmap(size, size, 1, 1, NULL);
    ii.hbmMask = mask;
    icon = CreateIconIndirect(&ii);
    DeleteObject(color);
    DeleteObject(mask);
    return icon;
}

/* ------------------------------------------------------------ 渲染 */
static int ensure_surface(zw32 *w, int fw, int fh)
{
    BITMAPV5HEADER bi;
    HDC hdc;
    if (w->hbmp && w->bw == fw && w->bh == fh) return 0;
    if (w->hbmp) { DeleteObject(w->hbmp); w->hbmp = NULL; }
    if (w->hdc_mem) { DeleteDC(w->hdc_mem); w->hdc_mem = NULL; }
    free(w->hit);
    w->hit = (unsigned char *)z_calloc((size_t)fw * fh, 1);
    w->hit_w = fw;
    w->hit_h = fh;
    hdc = GetDC(NULL);
    memset(&bi, 0, sizeof(bi));
    bi.bV5Size = sizeof(BITMAPV5HEADER);
    bi.bV5Width = fw;
    bi.bV5Height = -fh;          /* 自上而下 */
    bi.bV5Planes = 1;
    bi.bV5BitCount = 32;
    bi.bV5Compression = BI_BITFIELDS;
    bi.bV5RedMask = 0x00FF0000;
    bi.bV5GreenMask = 0x0000FF00;
    bi.bV5BlueMask = 0x000000FF;
    bi.bV5AlphaMask = 0xFF000000;
    w->hbmp = CreateDIBSection(hdc, (BITMAPINFO *)&bi, DIB_RGB_COLORS, &w->bits, NULL, 0);
    ReleaseDC(NULL, hdc);
    if (!w->hbmp) return -1;
    w->hdc_mem = CreateCompatibleDC(NULL);
    SelectObject(w->hdc_mem, w->hbmp);
    w->bw = fw;
    w->bh = fh;
    return 0;
}

static void render(zw32 *w)
{
    int fw = 0, fh = 0;
    const zimg *fr = zpet_frame(w->pet, &fw, &fh);
    int fw2, fh2;
    POINT dst, src;
    SIZE size;
    BLENDFUNCTION bf;
    int x, y;
    (void)fw2; (void)fh2;

    if (!fr) return;

    /* 缩放变化时，保持角色脚底中心在屏幕上的位置不变 */
    if (w->pos_known && (fw != w->bw || fh != w->bh) && w->bw > 0 && w->bh > 0) {
        int foot_x = w->wx + w->bw / 2;
        int foot_y = w->wy + w->bh;
        w->wx = foot_x - fw / 2;
        w->wy = foot_y - fh;
    }
    if (ensure_surface(w, fw, fh) != 0) return;

    if (!w->pos_known) {
        if (w->wx == (1 << 30) || w->wy == (1 << 30)) default_position(w);
        w->pos_known = 1;
    }

    /* RGBA → BGRA 预乘，同时填命中缓冲 */
    {
        uint8_t *dst_bits = (uint8_t *)w->bits;
        for (y = 0; y < fh; ++y) {
            const uint8_t *srow = fr->px + (size_t)y * fw * 4;
            uint8_t *drow = dst_bits + (size_t)y * fw * 4;
            unsigned char *hrow = w->hit + (size_t)y * fw;
            for (x = 0; x < fw; ++x) {
                unsigned a = srow[x * 4 + 3];
                drow[x * 4 + 0] = (uint8_t)(srow[x * 4 + 2] * a / 255);
                drow[x * 4 + 1] = (uint8_t)(srow[x * 4 + 1] * a / 255);
                drow[x * 4 + 2] = (uint8_t)(srow[x * 4 + 0] * a / 255);
                drow[x * 4 + 3] = (uint8_t)a;
                hrow[x] = (unsigned char)a;
            }
        }
    }

    if (!w->hdc_screen) w->hdc_screen = GetDC(NULL);
    dst.x = w->wx; dst.y = w->wy;
    src.x = 0; src.y = 0;
    size.cx = fw; size.cy = fh;
    bf.BlendOp = AC_SRC_OVER;
    bf.BlendFlags = 0;
    bf.SourceConstantAlpha = 255;
    bf.AlphaFormat = AC_SRC_ALPHA;
    UpdateLayeredWindow(w->hwnd, w->hdc_screen, &dst, &size, w->hdc_mem, &src, 0, &bf, ULW_ALPHA);
    ReleaseDC(NULL, w->hdc_screen);
    w->hdc_screen = NULL;
    w->last_scale = zpet_scale(w->pet);
}

/* 客户区坐标命中（切到窗口坐标；返回 alpha） */
static int hit_alpha(const zw32 *w, int x, int y)
{
    if (!w->hit || x < 0 || y < 0 || x >= w->hit_w || y >= w->hit_h) return 0;
    return w->hit[(size_t)y * w->hit_w + x];
}

/* ------------------------------------------------------------ 设置持久化 */
static void save_settings(zw32 *w)
{
    zerr err;
    zerr_clear(&err);
    zpet_sync_to_config(w->pet, w->conf);
    w->conf->pet.win_x = w->wx;
    w->conf->pet.win_y = w->wy;
    w->conf->pet.click_through = w->click_through_all;
    if (zconfig_save_settings(w->conf, &err) != 0)
        ZLOGW("win", "保存 settings.json 失败: %s", err.msg);
    else
        ZLOGI("win", "已保存窗口状态 (%d,%d) 缩放 %.2f", w->wx, w->wy, w->conf->pet.scale);
}

/* ------------------------------------------------------------ 菜单 */
static void open_config_dir(zw32 *w)
{
    wchar_t wpath[1200];
    char full[1200];
    z_path_join(full, sizeof(full), w->config_dir, "");
    MultiByteToWideChar(CP_UTF8, 0, w->config_dir, -1, wpath, 1200);
    ShellExecuteW(NULL, L"open", wpath, NULL, NULL, SW_SHOWNORMAL);
}

static void show_menu(zw32 *w, int screen_x, int screen_y)
{
    HMENU menu = CreatePopupMenu();
    HMENU forms = CreatePopupMenu();
    HMENU outfits = CreatePopupMenu();
    HMENU actions = CreatePopupMenu();
    HMENU scale = CreatePopupMenu();
    HMENU tools = CreatePopupMenu();
    int i, cmd;
    wchar_t wbuf[256];

    if (!menu) return;

    /* 形态 */
    for (i = 0; i < zpet_form_count(w->pet) && i < 16; ++i) {
        UINT flags = MF_STRING;
        MultiByteToWideChar(CP_UTF8, 0, zpet_form_name_at(w->pet, i), -1, wbuf, 256);
        if (z_streq(zpet_form_id_at(w->pet, i), zpet_form(w->pet))) flags |= MF_CHECKED;
        AppendMenuW(forms, flags, ZW_CMD_FORM_BASE + i, wbuf);
    }
    AppendMenuW(menu, MF_POPUP | MF_STRING, (UINT_PTR)forms, L"形态切换");

    /* 服装 */
    for (i = 0; i < zpet_outfit_count(w->pet) && i < 30; ++i) {
        UINT flags = MF_STRING;
        MultiByteToWideChar(CP_UTF8, 0, zpet_outfit_name_at(w->pet, i), -1, wbuf, 256);
        if (z_streq(zpet_outfit_id_at(w->pet, i), zpet_outfit(w->pet))) flags |= MF_CHECKED;
        AppendMenuW(outfits, flags, ZW_CMD_OUTFIT_BASE + i, wbuf);
    }
    if (zpet_outfit_count(w->pet) == 0)
        AppendMenuW(outfits, MF_STRING | MF_GRAYED, 0, L"(尚未添加服装)");
    AppendMenuW(menu, MF_POPUP | MF_STRING, (UINT_PTR)outfits, L"服装");

    /* 动作测试 */
    for (i = 0; i < zpet_action_count(w->pet) && i < 30; ++i) {
        MultiByteToWideChar(CP_UTF8, 0, zpet_action_id_at(w->pet, i), -1, wbuf, 256);
        AppendMenuW(actions, MF_STRING, ZW_CMD_ACTION_BASE + i, wbuf);
    }
    AppendMenuW(actions, MF_SEPARATOR, 0, NULL);
    AppendMenuW(actions, MF_STRING, ZW_CMD_SLEEP, L"睡觉（测试空闲入睡）");
    AppendMenuW(actions, MF_STRING, ZW_CMD_WAKE, L"唤醒");
    AppendMenuW(menu, MF_POPUP | MF_STRING, (UINT_PTR)actions, L"动作测试");

    /* 工具 */
    AppendMenuW(tools, MF_STRING | (w->tool == ZPET_TOOL_HAND ? MF_CHECKED : 0),
                ZW_CMD_TOOL_HAND, L"手（抚摸/摸头）");
    AppendMenuW(tools, MF_STRING | (w->tool == ZPET_TOOL_HAMMER ? MF_CHECKED : 0),
                ZW_CMD_TOOL_HAMMER, L"锤子（锤击）");
    AppendMenuW(menu, MF_POPUP | MF_STRING, (UINT_PTR)tools, L"工具");

    /* 缩放 */
    AppendMenuW(scale, MF_STRING, ZW_CMD_SCALE_UP, L"放大 (Ctrl+Alt+↑/+)");
    AppendMenuW(scale, MF_STRING, ZW_CMD_SCALE_DOWN, L"缩小 (Ctrl+Alt+↓/-)");
    AppendMenuW(scale, MF_STRING, ZW_CMD_SCALE_RESET, L"复位");
    AppendMenuW(menu, MF_POPUP | MF_STRING, (UINT_PTR)scale, L"缩放");

    AppendMenuW(menu, MF_SEPARATOR, 0, NULL);
    AppendMenuW(menu, MF_STRING | (w->click_through_all ? MF_CHECKED : 0),
                ZW_CMD_THROUGH, L"整窗鼠标穿透 (Ctrl+Alt+T)");
    AppendMenuW(menu, MF_STRING | (GetWindowLongW(w->hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST ? MF_CHECKED : 0),
                ZW_CMD_TOP_TOGGLE, L"始终置顶");
    AppendMenuW(menu, MF_STRING, ZW_CMD_OPEN_CONFIG, L"打开配置目录");
    AppendMenuW(menu, MF_STRING, ZW_CMD_ABOUT, L"关于 / 使用说明");
    AppendMenuW(menu, MF_SEPARATOR, 0, NULL);
    AppendMenuW(menu, MF_STRING, ZW_CMD_EXIT, L"退出");

    SetForegroundWindow(w->hwnd);
    cmd = (int)TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                              screen_x, screen_y, 0, w->hwnd, NULL);
    DestroyMenu(menu);

    if (cmd >= ZW_CMD_FORM_BASE && cmd < ZW_CMD_FORM_BASE + 100) {
        zdiag d;
        zdiag_init(&d);
        if (zpet_set_form(w->pet, zpet_form_id_at(w->pet, cmd - ZW_CMD_FORM_BASE), &d) != 0)
            MessageBoxW(NULL, L"该形态无法加载，详情见 logs/pet.log", L"形态切换失败", MB_OK | MB_ICONWARNING);
        else if (w->icon) {
            DestroyIcon(w->icon);
            w->icon = icon_from_pet(w, 32);
            w->nid.hIcon = w->icon;
            Shell_NotifyIconW(NIM_MODIFY, &w->nid);
        }
    } else if (cmd >= ZW_CMD_OUTFIT_BASE && cmd < ZW_CMD_OUTFIT_BASE + 100) {
        zerr e;
        zdiag d;
        zerr_clear(&e);
        zdiag_init(&d);
        if (zpet_set_outfit(w->pet, zpet_outfit_id_at(w->pet, cmd - ZW_CMD_OUTFIT_BASE), &d) != 0)
            MessageBoxW(NULL, L"该服装无法应用，详情见 logs/pet.log", L"换装失败", MB_OK | MB_ICONWARNING);
    } else if (cmd >= ZW_CMD_ACTION_BASE && cmd < ZW_CMD_ACTION_BASE + 100) {
        zpet_action_request(w->pet, zpet_action_id_at(w->pet, cmd - ZW_CMD_ACTION_BASE), "menu", 1);
    } else {
        switch (cmd) {
            case ZW_CMD_EXIT: w->quit = 1; PostQuitMessage(0); break;
            case ZW_CMD_SCALE_UP: zpet_scale_step(w->pet, +1); w->pos_known = 1; break;
            case ZW_CMD_SCALE_DOWN: zpet_scale_step(w->pet, -1); w->pos_known = 1; break;
            case ZW_CMD_SCALE_RESET: zpet_scale_reset(w->pet); w->pos_known = 1; break;
            case ZW_CMD_THROUGH: zw32_set_click_through(w, !w->click_through_all); break;
            case ZW_CMD_TOP_TOGGLE: zw32_set_topmost(w, !(GetWindowLongW(w->hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)); break;
            case ZW_CMD_TOOL_HAND: w->tool = ZPET_TOOL_HAND; zpet_set_tool(w->pet, ZPET_TOOL_HAND); break;
            case ZW_CMD_TOOL_HAMMER: w->tool = ZPET_TOOL_HAMMER; zpet_set_tool(w->pet, ZPET_TOOL_HAMMER); break;
            case ZW_CMD_SLEEP: zpet_action_request(w->pet, "sleep", "menu_sleep", 1); break;
            case ZW_CMD_WAKE: zpet_action_request(w->pet, "idle", "menu_wake", 0); break;
            case ZW_CMD_OPEN_CONFIG: open_config_dir(w); break;
            case ZW_CMD_ABOUT:
                MessageBoxW(NULL,
                            L"桌宠（C / Win32）\n\n"
                            L"• 鼠标移到角色上：摸头 / 抚摸（工具选“手”）\n"
                            L"• 工具选“锤子”再点角色：锤击反馈\n"
                            L"• 按住角色拖动可移动窗口，位置自动记住\n"
                            L"• 角色以外的区域不拦截鼠标（像素级穿透）\n"
                            L"• 托盘图标或右键角色：形态 / 服装 / 动作 / 缩放\n"
                            L"• 90 秒无键盘鼠标输入会自动睡觉，动一下鼠标就醒\n\n"
                            L"配置文件在 config/ 目录，改完重启生效。",
                            L"关于", MB_OK | MB_ICONINFORMATION);
                break;
            default: break;
        }
    }
}

/* ------------------------------------------------------------ 托盘 */
static void tray_add(zw32 *w)
{
    memset(&w->nid, 0, sizeof(w->nid));
    w->nid.cbSize = sizeof(NOTIFYICONDATAW);
    w->nid.hWnd = w->hwnd;
    w->nid.uID = ZW_TRAY_ID;
    w->nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    w->nid.uCallbackMessage = ZW_MSG_TRAY;
    w->nid.hIcon = w->icon ? w->icon : LoadIconW(NULL, (LPCWSTR)IDI_APPLICATION);
    /* 托盘提示：用宽字符写中文 */
    MultiByteToWideChar(CP_UTF8, 0, "桌宠 · 点击右键菜单", -1, w->nid.szTip,
                        (int)(sizeof(w->nid.szTip) / sizeof(wchar_t)));
    if (Shell_NotifyIconW(NIM_ADD, &w->nid)) {
        w->tray_added = 1;
        w->nid.uVersion = NOTIFYICON_VERSION_4;
        Shell_NotifyIconW(NIM_SETVERSION, &w->nid);
    } else {
        ZLOGW("tray", "托盘图标添加失败（系统限制？）");
    }
}

static void tray_remove(zw32 *w)
{
    if (w->tray_added) {
        Shell_NotifyIconW(NIM_DELETE, &w->nid);
        w->tray_added = 0;
    }
}

/* ------------------------------------------------------------ 窗口过程 */
static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    zw32 *w = g_instance;
    if (!w) return DefWindowProcW(hwnd, msg, wp, lp);

    switch (msg) {
        case WM_NCHITTEST: {
            POINT pt;
            int cx, cy;
            if (w->click_through_all) return HTTRANSPARENT;
            pt.x = GET_X_LPARAM(lp);
            pt.y = GET_Y_LPARAM(lp);
            cx = pt.x - w->wx;
            cy = pt.y - w->wy;
            if (!hit_alpha(w, cx, cy) || hit_alpha(w, cx, cy) <= w->hit_threshold)
                return HTTRANSPARENT;    /* 角色以外的区域：鼠标事件交给下面的窗口 */
            return HTCLIENT;
        }
        case WM_MOUSEMOVE: {
            int mx = GET_X_LPARAM(lp), my = GET_Y_LPARAM(lp);
            w->last_mouse.x = mx; w->last_mouse.y = my;
            if (!w->mouse_inside) {
                w->mouse_inside = 1;
                /* 悬停：进入专注状态 + 记录以唤醒 */
                zpet_notify_user_activity(w->pet, z_now_seconds());
                zpet_hover(w->pet, mx, my, 1, z_now_seconds());
                {
                    TRACKMOUSEEVENT tme;
                    tme.cbSize = sizeof(tme);
                    tme.dwFlags = TME_LEAVE;
                    tme.hwndTrack = hwnd;
                    TrackMouseEvent(&tme);
                }
            }
            zpet_hover(w->pet, mx, my, 1, z_now_seconds());
            if (w->pending_click && (wp & MK_LBUTTON)) {
                POINT p;
                GetCursorPos(&p);
                int dx = p.x - w->drag_pt.x;
                int dy = p.y - w->drag_pt.y;
                if (!w->dragging && (abs(dx) + abs(dy) > GetSystemMetrics(SM_CXDRAG))) {
                    w->dragging = 1;
                    w->pending_click = 0;
                    zpet_drag_start(w->pet, mx, my, z_now_seconds());
                }
                if (w->dragging) {
                    w->wx = w->win_origin_x + dx;
                    w->wy = w->win_origin_y + dy;
                    w->pos_known = 1;
                    return 0;
                }
            }
            return 0;
        }
        case WM_MOUSELEAVE:
            w->mouse_inside = 0;
            zpet_hover(w->pet, w->last_mouse.x, w->last_mouse.y, 0, z_now_seconds());
            return 0;
        case WM_LBUTTONDOWN: {
            POINT p;
            GetCursorPos(&p);
            SetCapture(hwnd);
            w->drag_pt = p;
            w->win_origin_x = w->wx;
            w->win_origin_y = w->wy;
            w->dragging = 0;
            w->pending_click = 1;
            return 0;
        }
        case WM_LBUTTONUP: {
            int mx = GET_X_LPARAM(lp), my = GET_Y_LPARAM(lp);
            ReleaseCapture();
            if (w->dragging) {
                POINT p;
                GetCursorPos(&p);
                int moved = abs(p.x - w->drag_pt.x) + abs(p.y - w->drag_pt.y);
                w->dragging = 0;
                if (moved > 6) {
                    zpet_drag_end(w->pet, z_now_seconds());
                    /* 松手后让角色落到屏幕内 */
                    {
                        RECT wa;
                        get_work_area(&wa);
                        if (w->wx + w->bw < wa.left + 40) w->wx = wa.left + 40 - w->bw;
                        if (w->wx > wa.right - 40) w->wx = wa.right - 40;
                        if (w->wy < wa.top) w->wy = wa.top;
                        if (w->wy > wa.bottom - 40) w->wy = wa.bottom - 40;
                    }
                    save_settings(w);
                }
                return 0;
            }
            zpet_poke(w->pet, mx, my, w->tool, z_now_seconds());
            w->pending_click = 0;
            return 0;
        }
        case WM_LBUTTONDBLCLK:
            zpet_action_request(w->pet, "happy", "double_click", 1);
            return 0;
        case WM_RBUTTONUP: {
            POINT p;
            GetCursorPos(&p);
            show_menu(w, p.x, p.y);
            return 0;
        }
        case WM_SETCURSOR: {
            POINT p;
            int cx, cy;
            GetCursorPos(&p);
            cx = p.x - w->wx;
            cy = p.y - w->wy;
            if (!hit_alpha(w, cx, cy)) {
                SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_ARROW));
                return TRUE;
            }
            if (w->tool == ZPET_TOOL_HAMMER) {
                SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_CROSS));   /* 自定义锤子光标见 assets/ui/cursors/ */
            } else if (!w->dragging) {
                SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_HAND));
            } else {
                SetCursor(LoadCursorW(NULL, (LPCWSTR)IDC_SIZEALL));
            }
            return TRUE;
        }
        case ZW_MSG_TRAY:
            switch (LOWORD(lp)) {
                case WM_LBUTTONDBLCLK: case WM_LBUTTONUP:
                    zpet_action_request(w->pet, "happy", "tray_click", 1);
                    break;
                case WM_RBUTTONUP: case WM_CONTEXTMENU: {
                    POINT p;
                    GetCursorPos(&p);
                    show_menu(w, p.x, p.y);
                    break;
                }
                default: break;
            }
            return 0;
        case WM_HOTKEY:
            if (wp == ZW_HOTKEY_SCALE_UP) { zpet_scale_step(w->pet, +1); w->pos_known = 1; }
            else if (wp == ZW_HOTKEY_SCALE_DOWN) { zpet_scale_step(w->pet, -1); w->pos_known = 1; }
            else if (wp == ZW_HOTKEY_THROUGH) { zw32_set_click_through(w, !w->click_through_all); }
            return 0;
        case WM_DESTROY:
            w->quit = 1;
            PostQuitMessage(0);
            return 0;
        default:
            break;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

/* ------------------------------------------------------------ 生命周期 */
zw32 *zw32_create(zcfg_pet *cfg, zconfig *conf, zpet *pet, zdiag *diag)
{
    zw32 *w;
    WNDCLASSEXW wc;
    RECT wa;
    int fw = 0, fh = 0;

    (void)diag;
    if (!pet || !conf) return NULL;
    w = (zw32 *)z_calloc(1, sizeof(zw32));
    w->pet = pet;
    w->conf = conf;
    w->fps = cfg ? cfg->fps : 30;
    w->hit_threshold = cfg ? cfg->hit_alpha_threshold : 24;
    w->tool = zpet_tool_get(pet);
    w->click_through_all = cfg ? cfg->click_through : 0;
    z_strlcpy(w->config_dir, conf->config_dir, sizeof(w->config_dir));
    z_strlcpy(w->root_dir, conf->root_dir, sizeof(w->root_dir));

    SetProcessDPIAware();
    g_instance = w;

    memset(&wc, 0, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = WndProc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    wc.lpszClassName = ZW_CLASS_NAME;
    if (!RegisterClassExW(&wc)) {
        ZLOGE("win", "RegisterClassEx 失败: %lu", GetLastError());
        free(w);
        return NULL;
    }

    get_work_area(&wa);
    zpet_frame(pet, &fw, &fh);
    if (cfg && (cfg->win_x != (1 << 30) || cfg->win_y != (1 << 30))) {
        w->wx = cfg->win_x;
        w->wy = cfg->win_y;
        w->pos_known = 1;
    } else {
        w->wx = wa.right - fw - 24;
        w->wy = wa.bottom - fh - 4;
        w->pos_known = 1;
    }

    w->hwnd = CreateWindowExW(
        WS_EX_LAYERED | WS_EX_TOOLWINDOW | (cfg && cfg->always_on_top ? WS_EX_TOPMOST : 0),
        ZW_CLASS_NAME, L"桌宠", WS_POPUP,
        w->wx, w->wy, fw, fh, NULL, NULL, GetModuleHandleW(NULL), NULL);
    if (!w->hwnd) {
        ZLOGE("win", "CreateWindowEx 失败: %lu", GetLastError());
        free(w);
        g_instance = NULL;
        return NULL;
    }

    w->icon = icon_from_pet(w, 32);
    w->icon_small = icon_from_pet(w, 16);
    if (w->icon_small) w->nid.hIcon = w->icon_small;
    tray_add(w);

    RegisterHotKey(w->hwnd, ZW_HOTKEY_SCALE_UP, MOD_CONTROL | MOD_ALT, VK_ADD);
    RegisterHotKey(w->hwnd, ZW_HOTKEY_SCALE_DOWN, MOD_CONTROL | MOD_ALT, VK_SUBTRACT);
    RegisterHotKey(w->hwnd, ZW_HOTKEY_THROUGH, MOD_CONTROL | MOD_ALT, 'T');

    ShowWindow(w->hwnd, SW_SHOWNOACTIVATE);
    render(w);
    ZLOGI("win", "窗口已创建 %dx%d @ (%d,%d)，帧率 %d，穿透=%s，命中阈值 %d",
          fw, fh, w->wx, w->wy, w->fps,
          w->click_through_all ? "整窗" : "像素级", w->hit_threshold);
    return w;
}

int zw32_run(zw32 *w)
{
    MSG msg;
    double frame_dt;
    DWORD last_input_tick = 0;

    if (!w) return 1;
    frame_dt = 1.0 / (w->fps > 0 ? w->fps : 30);
    w->next_frame = z_now_seconds();

    while (!w->quit) {
        while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) { w->quit = 1; break; }
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if (w->quit) break;

        {
            double now = z_now_seconds();
            if (now >= w->next_frame) {
                w->next_frame = now + frame_dt;

                /* 空闲检测：90 秒无输入进入睡眠（交接文件第六节） */
                {
                    LASTINPUTINFO lii;
                    lii.cbSize = sizeof(lii);
                    if (GetLastInputInfo(&lii)) {
                        DWORD tick = GetTickCount();
                        DWORD idle_ms = tick - lii.dwTime;
                        if (lii.dwTime != last_input_tick) {
                            last_input_tick = lii.dwTime;
                            zpet_notify_user_activity(w->pet, now);
                        }
                        zpet_report_idle(w->pet, idle_ms / 1000.0);
                    }
                }

                zpet_tick(w->pet, now);
                render(w);
            } else {
                Sleep(1);
            }
        }
    }
    return 0;
}

void zw32_destroy(zw32 *w)
{
    if (!w) return;
    save_settings(w);
    tray_remove(w);
    UnregisterHotKey(w->hwnd, ZW_HOTKEY_SCALE_UP);
    UnregisterHotKey(w->hwnd, ZW_HOTKEY_SCALE_DOWN);
    UnregisterHotKey(w->hwnd, ZW_HOTKEY_THROUGH);
    if (w->hwnd) DestroyWindow(w->hwnd);
    if (w->hbmp) DeleteObject(w->hbmp);
    if (w->hdc_mem) DeleteDC(w->hdc_mem);
    if (w->hdc_screen) ReleaseDC(NULL, w->hdc_screen);
    if (w->icon) DestroyIcon(w->icon);
    if (w->icon_small) DestroyIcon(w->icon_small);
    free(w->hit);
    g_instance = NULL;
    free(w);
}

void zw32_get_window_pos(const zw32 *w, int *x, int *y, int *w_px, int *h_px)
{
    if (!w) return;
    if (x) *x = w->wx;
    if (y) *y = w->wy;
    if (w_px) *w_px = w->bw;
    if (h_px) *h_px = w->bh;
}

void zw32_set_click_through(zw32 *w, int on)
{
    if (!w) return;
    w->click_through_all = on ? 1 : 0;
    ZLOGI("win", "鼠标穿透：%s", on ? "整窗穿透（角色也不可点）" : "像素级（角色可点，空白穿透）");
    /* 让窗口立刻重新计算命中 */
    {
        POINT p;
        GetCursorPos(&p);
        SendMessageW(w->hwnd, WM_NCHITTEST, 0, MAKELPARAM(p.x, p.y));
    }
}

int zw32_click_through(const zw32 *w) { return w ? w->click_through_all : 0; }

void zw32_set_topmost(zw32 *w, int on)
{
    LONG ex;
    if (!w) return;
    ex = GetWindowLongW(w->hwnd, GWL_EXSTYLE);
    if (on) ex |= WS_EX_TOPMOST; else ex &= ~WS_EX_TOPMOST;
    SetWindowLongW(w->hwnd, GWL_EXSTYLE, ex);
    SetWindowPos(w->hwnd, on ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
}

int zw32_topmost(const zw32 *w)
{
    if (!w) return 0;
    return (GetWindowLongW(w->hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST) ? 1 : 0;
}

void zw32_refresh_tray_icon(zw32 *w)
{
    if (!w || !w->tray_added) return;
    if (w->icon) DestroyIcon(w->icon);
    w->icon = icon_from_pet(w, 32);
    if (w->icon) {
        w->nid.hIcon = w->icon;
        Shell_NotifyIconW(NIM_MODIFY, &w->nid);
    }
}

void zw32_set_tool(zw32 *w, zpet_tool t)
{
    if (!w) return;
    w->tool = t;
    zpet_set_tool(w->pet, t);
    ZLOGI("win", "工具切换：%s", t == ZPET_TOOL_HAMMER ? "锤子" : "手");
}
