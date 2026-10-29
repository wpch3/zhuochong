#include <stddef.h>
#ifndef ZPERM_H
#define ZPERM_H
#ifdef __cplusplus
extern "C" {
#endif
// zperm - 统一权限模型 A29/G79
// 能力分级、独立开关、全局急停、敏感区屏蔽、审计留痕、显眼指示
typedef struct zperm zperm;
zperm *zperm_load(const char *root, char *err, size_t errcap);
void zperm_free(zperm *p);
// 检查：0=允许, -1=拒绝（关闭或急停）
int zperm_check(zperm *p, const char *cap_id);
// 急停开关
int zperm_estop_active(zperm *p);
void zperm_estop_set(zperm *p, int on);
// 敏感区是否被屏蔽：1=应屏蔽
int zperm_sensitive_hit(zperm *p, const char *title);
// 审计：写一条到 audit.log（受 record 白名单过滤）
int zperm_audit(zperm *p, const char *cap_id, const char *detail);
// 获取能力开关
int zperm_cap_enabled(zperm *p, const char *cap_id);
const char *zperm_cap_tier(zperm *p, const char *cap_id);
#ifdef __cplusplus
}
#endif
#endif
