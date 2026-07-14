/**
 * @file        rex/ui/present_stats.h
 * @brief       Lightweight presenter timing readouts for the debug overlay.
 *
 * @copyright   Copyright (c) 2026 Project Gracemeria
 * @license     BSD 3-Clause License
 */
#pragma once

namespace rex::ui {

// Duration (ms) of the presenter's last swap-chain frame-latency wait - how long
// painting blocked on the GPU/display being ready to accept a new frame. A high,
// steady value means GPU-bound (the display/GPU is the bottleneck); ~0 means the
// pacing/limiter is the bottleneck (CPU-side), which is the healthy case. This is
// the analog of UnleashedRecomp's "Present Wait" profiler.
double GetLastPresentWaitMs();
void SetLastPresentWaitMs(double ms);

}  // namespace rex::ui
