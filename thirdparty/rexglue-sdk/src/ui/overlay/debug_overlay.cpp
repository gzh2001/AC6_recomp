/**
 * @file        ui/overlay/debug_overlay.cpp
 *
 * @brief       Debug overlay implementation. See debug_overlay.h for details.
 *
 * @copyright   Copyright (c) 2026 Tom Clay <tomc@tctechstuff.com>
 *              All rights reserved.
 *
 * @license     BSD 3-Clause License
 *              See LICENSE file in the project root for full license text.
 */
#include <rex/ui/overlay/debug_overlay.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/present_stats.h>
#include <rex/version.h>
#include <imgui.h>

#include <algorithm>
#include <cstdio>

namespace rex::ui {

DebugOverlayDialog::DebugOverlayDialog(ImGuiDrawer* imgui_drawer, FrameStatsProvider stats_provider)
    : ImGuiDialog(imgui_drawer), stats_provider_(std::move(stats_provider)) {
  RegisterBind("bind_debug_overlay", "F3", "Toggle debug overlay", [this] { ToggleVisible(); });
}

DebugOverlayDialog::~DebugOverlayDialog() {
  UnregisterBind("bind_debug_overlay");
}

void DebugOverlayDialog::OnDraw(ImGuiIO& io) {
  if (!visible_)
    return;

  // --- Sample this host frame --------------------------------------------
  const double host_ms = io.DeltaTime * 1000.0;

  FrameStats stats;
  bool have_guest = false;
  if (stats_provider_) {
    stats = stats_provider_();
    have_guest = stats.frame_count > 0;
  }

  // Counter spread metric: track guest frametime extremes per ACTUAL guest frame.
  if (have_guest && stats.frame_count != last_guest_frame_count_) {
    last_guest_frame_count_ = stats.frame_count;
    window_guest_ms_min_ = (std::min)(window_guest_ms_min_, stats.frame_time_ms);
    window_guest_ms_max_ = (std::max)(window_guest_ms_max_, stats.frame_time_ms);
  }

  // Push graph samples at a FIXED TIME interval (kGraphSampleSeconds), not per
  // frame, so both graphs scroll at a consistent rate regardless of fps. Each
  // sample carries the max frametime since the last sample (spikes preserved).
  graph_host_ms_max_ = (std::max)(graph_host_ms_max_, float(host_ms));
  if (have_guest) {
    graph_guest_ms_max_ = (std::max)(graph_guest_ms_max_, float(stats.frame_time_ms));
  }
  graph_sample_accum_s_ += io.DeltaTime;
  if (graph_sample_accum_s_ >= kGraphSampleSeconds) {
    bool first = true;
    while (graph_sample_accum_s_ >= kGraphSampleSeconds) {
      graph_sample_accum_s_ -= kGraphSampleSeconds;
      // First push uses the accumulated max; extra pushes (a frame longer than
      // several sample intervals - a hitch) repeat the current frametime so the
      // graph fills the gap at the right time width instead of dropping to zero.
      host_ms_history_[host_history_pos_] = first ? graph_host_ms_max_ : float(host_ms);
      host_history_pos_ = (host_history_pos_ + 1) % kHistory;
      guest_ms_history_[guest_history_pos_] =
          first ? graph_guest_ms_max_ : (have_guest ? float(stats.frame_time_ms) : 0.0f);
      guest_history_pos_ = (guest_history_pos_ + 1) % kHistory;
      first = false;
    }
    graph_host_ms_max_ = 0.0f;
    graph_guest_ms_max_ = 0.0f;
  }

  // --- Throttled counters (averaged over kCounterRefreshSeconds) ----------
  counter_window_s_ += io.DeltaTime;
  ++host_frames_in_window_;
  if (counter_window_s_ >= kCounterRefreshSeconds) {
    disp_host_fps_ = host_frames_in_window_ / counter_window_s_;
    disp_host_ms_ = disp_host_fps_ > 0.0 ? 1000.0 / disp_host_fps_ : 0.0;
    if (have_guest) {
      const double guest_frames = double(stats.frame_count - guest_frames_at_window_start_);
      disp_guest_fps_ = guest_frames / counter_window_s_;
      disp_guest_ms_ = disp_guest_fps_ > 0.0 ? 1000.0 / disp_guest_fps_ : 0.0;
      disp_guest_ms_min_ = window_guest_ms_min_ < 1.0e8 ? window_guest_ms_min_ : 0.0;
      disp_guest_ms_max_ = window_guest_ms_max_;
    }
    counter_window_s_ = 0.0;
    host_frames_in_window_ = 0;
    guest_frames_at_window_start_ = have_guest ? stats.frame_count : 0;
    window_guest_ms_min_ = 1.0e9;
    window_guest_ms_max_ = 0.0;
  }

  // --- Draw ---------------------------------------------------------------
  ImGui::SetNextWindowPos(ImVec2(10, 10), ImGuiCond_FirstUseEver);
  ImGui::SetNextWindowSize(ImVec2(320, 0), ImGuiCond_FirstUseEver);
  ImGui::SetNextWindowBgAlpha(0.55f);
  if (ImGui::Begin("Frame timing##overlay", nullptr, ImGuiWindowFlags_NoCollapse)) {
    ImGui::Text("Host:  %6.1f FPS   %5.2f ms", disp_host_fps_, disp_host_ms_);
    // Host = the presenter's paint/present rate = what an external tool like RTSS
    // measures. It is DECOUPLED from the guest game rate below (the presenter
    // paints on the UI thread at ~monitor refresh), so Host >> Guest is expected
    // and is why RTSS reads the present rate, not the game fps. Present-wait = how
    // long paint blocked on the GPU/display (high = GPU-bound; ~0 = pacing-bound).
    ImGui::SameLine();
    ImGui::TextDisabled("  wait %.2f ms", GetLastPresentWaitMs());
    if (have_guest) {
      ImGui::Text("Guest: %6.1f FPS   %5.2f ms", disp_guest_fps_, disp_guest_ms_);
      // Spread over the window is the numeric shake metric: a wide min/max at a
      // steady average fps is exactly the uneven-pacing / aircraft-shake signal.
      ImGui::TextDisabled("guest ft  min %.2f  max %.2f  spread %.2f ms", disp_guest_ms_min_,
                          disp_guest_ms_max_, disp_guest_ms_max_ - disp_guest_ms_min_);
    }

    ImGui::Separator();

    // Both graphs share a fixed 0-40ms scale so host vs guest jaggedness is
    // directly comparable. Flat host + jagged guest == sim-dt jitter (the shake
    // is in the game's timing, not the presenter); jagged both == real delivery
    // unevenness (look at the pacing/limiter).
    char overlay[48];
    std::snprintf(overlay, sizeof(overlay), "host   %.2f ms (now)", host_ms);
    ImGui::PlotLines("##host_ft", host_ms_history_, kHistory, host_history_pos_, overlay, 0.0f,
                     40.0f, ImVec2(0, 55));
    if (have_guest) {
      std::snprintf(overlay, sizeof(overlay), "guest  %.2f ms (now)", stats.frame_time_ms);
      ImGui::PlotLines("##guest_ft", guest_ms_history_, kHistory, guest_history_pos_, overlay,
                       0.0f, 40.0f, ImVec2(0, 55));
    }
    ImGui::TextDisabled("graphs 0-40 ms, ~%.0fs window (max/%.0fms) | counters avg %.1fs",
                        kHistory * kGraphSampleSeconds, kGraphSampleSeconds * 1000.0,
                        kCounterRefreshSeconds);
  }
  ImGui::End();
}

}  // namespace rex::ui
