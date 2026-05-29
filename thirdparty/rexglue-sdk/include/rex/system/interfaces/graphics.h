/**
 * @file        system/interfaces/graphics.h
 * @brief       Abstract graphics system interface for dependency injection
 *
 * @copyright   Copyright (c) 2026 Tom Clay <tomc@tctechstuff.com>
 *              All rights reserved.
 *
 * @license     BSD 3-Clause License
 *              See LICENSE file in the project root for full license text.
 */

#pragma once

#include <array>
#include <functional>

#include <rex/system/xtypes.h>

// Forward declarations
namespace rex::memory {
class Memory;
}
namespace rex::runtime {
class FunctionDispatcher;
}
namespace rex::ui {
class WindowedAppContext;
class GraphicsProvider;
class Presenter;
}
namespace rex::system {
class KernelState;
}

namespace rex::system {

struct GraphicsSwapSubmission {
  uint32_t frontbuffer_virtual_address = 0;
  uint32_t frontbuffer_physical_address = 0;
  uint32_t frontbuffer_width = 0;
  uint32_t frontbuffer_height = 0;
  uint32_t texture_format = 0;
  uint32_t color_space = 0;
  std::array<uint32_t, 6> texture_fetch = {};
};

class IGraphicsSystem {
 public:
  virtual ~IGraphicsSystem() = default;

  // Build the provider + presenter. Safe to call standalone (without a
  // Runtime) to stand up a window + ImGui for an installer. Idempotent.
  // Must be called before SetupGuestGpu if presentation is desired: some
  // backends (e.g. Vulkan) bake swapchain support into the provider, and
  // a headless provider from SetupGuestGpu cannot be upgraded in place.
  virtual X_STATUS SetupPresentation(ui::WindowedAppContext* app_context) = 0;

  // Wire the GPU into the guest address space: MMIO, command processor,
  // vsync worker. Needs the Runtime's dispatcher + kernel state. If
  // SetupPresentation has not been called, a headless provider is built.
  virtual X_STATUS SetupGuestGpu(runtime::FunctionDispatcher* function_dispatcher,
                                 KernelState* kernel_state) = 0;

  virtual bool has_presentation() const = 0;

  // One-shot convenience for callers that don't care about the split.
  X_STATUS Setup(runtime::FunctionDispatcher* function_dispatcher, KernelState* kernel_state,
                 ui::WindowedAppContext* app_context, bool with_presentation) {
    if (with_presentation && !has_presentation()) {
      X_STATUS status = SetupPresentation(app_context);
      if (XFAILED(status)) {
        return status;
      }
    }
    return SetupGuestGpu(function_dispatcher, kernel_state);
  }

  virtual void Shutdown() = 0;
  virtual ui::GraphicsProvider* provider() const = 0;
  virtual ui::Presenter* presenter() const = 0;
  virtual void InitializeRingBuffer(uint32_t ptr, uint32_t size_log2) = 0;
  virtual void EnableReadPointerWriteBack(uint32_t ptr, uint32_t block_size_log2) = 0;
  virtual void SetInterruptCallback(uint32_t callback, uint32_t user_data) = 0;
  virtual void SetFrameBoundaryCallback(std::function<void(rex::memory::Memory*)> callback) = 0;
  virtual bool HandleVideoSwap(const GraphicsSwapSubmission& submission) = 0;
};

}  // namespace rex::system
