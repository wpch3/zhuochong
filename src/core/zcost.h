#include <stddef.h>
#ifndef ZCOST_H
#define ZCOST_H
#ifdef __cplusplus
extern "C" {
#endif
// zcost - 成本熔断 A30/G80：硬上限、分能力配额、降级、预估、空闲降频
typedef struct zcost zcost;
zcost *zcost_load(const char *root, char *err, size_t errcap);
void zcost_free(zcost *p);
// 入账：cap_id 为 vision/voice_stt/voice_tts/text_llm 等，cny 为本次花费
int zcost_add(zcost *p, const char *cap_id, double cny);
// 检查是否熔断：1=已到顶应停，0=可继续
int zcost_tripped(zcost *p, const char *cap_id);
// 降级策略：返回应切的档位字符串（local_model/reduce_fps/...）
const char *zcost_downgrade(zcost *p);
// 预估：按当前设置估每小时花费
double zcost_estimate_hourly(zcost *p);
// 空闲是否应降频：1=是
int zcost_idle_should_downclock(zcost *p, double idle_s);
#ifdef __cplusplus
}
#endif
#endif
