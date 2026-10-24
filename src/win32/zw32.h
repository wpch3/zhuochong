/*
 * zw32.h - Windows 平台层（分层透明窗口 / 托盘 / 输入）
 *
 * 结论来自参考项目（交接文件第二节）：
 *   - vladelaina/BongoCat 的思路：分层窗口 + 像素级“鼠标穿透开/关”开关；
 *   - QCYTSN/ds-local-pet 的思路：优先级状态机、空闲检测、托盘交互；
 *   - LorisYounger/VPet 的思路：拖动、点击反应、缩放与托盘菜单。
 * 具体实现为本项目原创，未复制任何参考项目代码。
 */
#ifndef ZW32_H
#define ZW32_H

#include "../core/zpet.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct zw32 zw32;

/* 创建一个桌宠窗口（不显示）。失败返回 NULL 并把原因写进 diag。 */
zw32 *zw32_create(zcfg_pet *cfg, zconfig *conf, zpet *pet, zdiag *diag);
/* 显示窗口并进入消息循环；返回退出码。 */
int   zw32_run(zw32 *w);
void  zw32_destroy(zw32 *w);

/* 当前窗口位置（用于退出时保存）；-1 表示尚未定位 */
void  zw32_get_window_pos(const zw32 *w, int *x, int *y, int *w_px, int *h_px);
/* 鼠标穿透总开关（整窗穿透，托盘菜单用） */
void  zw32_set_click_through(zw32 *w, int on);
int   zw32_click_through(const zw32 *w);
void  zw32_set_topmost(zw32 *w, int on);
int   zw32_topmost(const zw32 *w);
/* 重新按当前角色帧生成托盘图标（缩放/换形态后调用保持一致） */
void  zw32_refresh_tray_icon(zw32 *w);
void  zw32_set_tool(zw32 *w, zpet_tool t);

#ifdef __cplusplus
}
#endif
#endif /* ZW32_H */
