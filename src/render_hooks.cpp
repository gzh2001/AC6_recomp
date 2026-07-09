#include "render_hooks.h"
#include "d3d_hooks.h"
#include "ac6_native_graphics.h"

#include <atomic>
#include <chrono>

#include <rex/cvar.h>
#include <rex/system/kernel_state.h>

REXCVAR_DEFINE_BOOL(ac6_unlock_fps, false, "AC6", "Unlock frame rate to 60fps");
REXCVAR_DEFINE_BOOL(ac6_timing_hooks_enabled, true, "AC6",
                    "Enable AC6 timing hooks that alter the game's presentation cadence");
REXCVAR_DEFINE_BOOL(ac6_cutscene_clamp, true, "AC6",
                    "Suspend the 60fps unlock during in-engine cutscenes so they "
                    "play at native ~30fps instead of double speed");

using Clock = std::chrono::steady_clock;

namespace {

std::atomic<double> g_frame_time_ms{0.0};
std::atomic<double> g_fps{0.0};
std::atomic<uint64_t> g_frame_count{0};
Clock::time_point g_frame_start{};

// Wall-clock (steady) ms of the last in-engine cutscene tick. The cutscene
// hook (ac6CinematicTickHook) runs on the game thread; the timing hooks read
// this on the present/GPU path, hence the atomic. INT64_MIN = never ticked.
std::atomic<int64_t> g_last_cinematic_tick_ms{INT64_MIN};

// The demo-manager Exec runs every game frame while a cutscene plays (~16-33ms
// apart). A few-frame decay keeps the clamp asserted across the cutscene and
// auto-releases shortly after it ends.
constexpr int64_t kCinematicDecayMs = 100;

int64_t NowMs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
               Clock::now().time_since_epoch())
        .count();
}

bool AreTimingHooksActive() {
    return REXCVAR_GET(ac6_timing_hooks_enabled) && REXCVAR_GET(ac6_unlock_fps) &&
           !ac6::IsCinematicActive();
}

}  // namespace

namespace ac6 {

// True while the FPS-unlock timing hooks are remapping the game's cadence
// (unlock cvars on and no cutscene clamp). The physics force-step rescale keys
// off this so it stays in lockstep with the frame-delta hooks: whenever the
// delta reverts to vanilla, the force step must too.
bool TimingHooksActive() {
  return AreTimingHooksActive();
}

bool IsCinematicActive() {
    if (!REXCVAR_GET(ac6_cutscene_clamp)) {
        return false;
    }
    const int64_t last = g_last_cinematic_tick_ms.load(std::memory_order_relaxed);
    if (last == INT64_MIN) {
        return false;
    }
    return (NowMs() - last) <= kCinematicDecayMs;
}

}  // namespace ac6

bool ac6FlipIntervalHook() {
    return AreTimingHooksActive();
}

bool ac6PresentIntervalHook(PPCRegister& r10) {
    if (!AreTimingHooksActive()) {
        return false;
    }
    r10.u64 = 1;
    return true;
}

void ac6DeltaDivisorHook(PPCRegister& r29) {
    if (!AreTimingHooksActive()) {
        return;
    }
    r29.u64 = 30;
}

void ac6PresentTimingHook(PPCRegister& /*r31*/) {
    // ac6::d3d::OnFrameBoundary(); // MOVED TO GPU THREAD

    const auto now = Clock::now();
    if (g_frame_start.time_since_epoch().count() != 0) {
        const double frame_time_ms =
            std::chrono::duration<double, std::milli>(now - g_frame_start).count();
        g_frame_time_ms.store(frame_time_ms, std::memory_order_relaxed);
        g_fps.store(frame_time_ms > 0.0001 ? (1000.0 / frame_time_ms) : 0.0,
                    std::memory_order_relaxed);
        g_frame_count.fetch_add(1, std::memory_order_relaxed);
    }
    g_frame_start = now;
}

void ac6CinematicTickHook(PPCRegister& /*r3*/) {
    // A demo-manager Exec (DD: sub_82184460 / EM: sub_821856F8) ran this frame ->
    // an in-engine cutscene is playing. Stamp the time so AreTimingHooksActive()
    // suspends the 60fps unlock until the cutscene ends (the stamp goes stale a
    // few frames after the last tick), letting the frame-locked cinematic
    // Sequencer play at native ~30fps instead of double speed.
    g_last_cinematic_tick_ms.store(NowMs(), std::memory_order_relaxed);
}

namespace ac6 {

FrameStats GetFrameStats() {
    return FrameStats{g_frame_time_ms.load(std::memory_order_relaxed),
                      g_fps.load(std::memory_order_relaxed),
                      g_frame_count.load(std::memory_order_relaxed)};
}

}  // namespace ac6
