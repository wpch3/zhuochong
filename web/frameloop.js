/* web/frameloop.js —— 测试台画面刷新的节流器（纯逻辑，可单测）
 *
 * 为什么要把这几十行单独拎出来（2026-10-16，用户反馈「眼睛/视线/脑袋跟随会轻微抽搐」）：
 *
 * 原来的刷新是 `setInterval(refresh, 100)`，每次 `new Image()` 拉一张满尺寸 PNG。
 * 查下来三件事：
 *   1. 引擎**无辜**。跟随平滑是 `k = 1 − exp(−speed·dt)`，按时间算的；
 *      实测把同一段时间用 10fps / 30fps / 60fps / 抖动帧间隔四种方式推进到同一绝对
 *      时刻，`look_x` 只差 1.4e-4（纯浮点误差）。所以任一瞬间的姿态都是对的。
 *   2. 真正的瓶颈是**搬字节**。满尺寸一帧 190 KB，10fps = 1.86 MB/s。
 *      云端预览走公网代理，这个速率撑不住，帧就只能不定时地到 —— 姿态没错，
 *      但到达时刻乱，看起来就是"一卡一跳"。
 *   3. 定时器**不管上一帧回来没有**照发不误。链路一慢，请求堆在浏览器的连接队列里，
 *      回来时一拥而上；而 `onload` 里无条件 `img.src = next.src`，
 *      谁最后回来谁上屏 —— 万一旧帧后到，画面会**倒退一下再跳回来**。
 *
 * 所以这里做三件事：
 *   · 在途保护：上一帧没回来就不发新的（天然自适应链路快慢，不堆请求）；
 *   · 丢弃迟到帧：带序号，比已上屏的还旧就扔掉，画面只许往前走；
 *   · 按**显示尺寸**要图：`<img>` 只有 320px 宽却拉 466px 的图纯属浪费带宽。
 *
 * 注意这改的是**预览通道**，不是动画本身。Windows 原生桌宠直接渲到窗口上，
 * 不走 PNG、不走网络，本来就没有这条链路。
 */
(function (root) {
  "use strict";

  /** 按实际显示宽度算要向引擎要多大的帧（/api/frame.png?s= 的取值域是 25~100 百分比）。
   *  dpr 要乘进去，否则 HiDPI 屏上会拿到一张被放大的糊图。 */
  function frameScale(dispW, frameW, dpr) {
    if (!(dispW > 0) || !(frameW > 0)) return 100;      // 还没拿到 info 时别乱猜
    var want = Math.ceil((dispW * (dpr || 1)) / frameW * 100);
    if (want < 25) return 25;
    if (want > 100) return 100;
    return want;
  }

  /** 造一个刷新循环。依赖全部注入，所以能脱离浏览器单测。
   *  cfg = { url(scale), load(url, onOk, onFail), show(url), now(), timeoutMs } */
  function makeFrameLoop(cfg) {
    var inFlight = false, inFlightAt = 0;
    var seq = 0, shown = -1, delivered = 0, dropped = 0, skipped = 0;
    var TIMEOUT = cfg.timeoutMs || 3000;

    function tick(scale) {
      var t = cfg.now();
      if (inFlight) {
        /* 还在途就什么都不做 —— 这一条就是"不堆请求"。
           但不能无限等：请求卡死（代理掐连接、标签页被挂起）时要能自己恢复，
           所以超过 TIMEOUT 就当它没了，放行下一发。 */
        if (t - inFlightAt < TIMEOUT) { skipped++; return false; }
        inFlight = false;
      }
      inFlight = true;
      inFlightAt = t;
      var mySeq = ++seq;
      var url = cfg.url(scale);
      cfg.load(url, function () {
        inFlight = false;
        /* 迟到的旧帧直接丢。不丢的话画面会倒退一帧再跳回来 ——
           姿态是时间的连续函数，倒退就是肉眼可见的"抽一下"。 */
        if (mySeq < shown) { dropped++; return; }
        shown = mySeq;
        delivered++;
        cfg.show(url);
      }, function () {
        inFlight = false;              /* 失败也要放行，否则一次 404 就永久停更 */
      });
      return true;
    }

    return {
      tick: tick,
      stats: function () {
        return { seq: seq, shown: shown, delivered: delivered,
                 dropped: dropped, skipped: skipped, inFlight: inFlight };
      }
    };
  }

  root.ZFrameLoop = { frameScale: frameScale, makeFrameLoop: makeFrameLoop };
})(typeof window !== "undefined" ? window : globalThis);
