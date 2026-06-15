#pragma once

#include <memory>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#if REX_HAS_D3D12
#include <rex/graphics/d3d12/graphics_system.h>
#endif
#if REX_HAS_VULKAN
#include <rex/graphics/vulkan/graphics_system.h>
#endif

#include "ac6_native_graphics.h"
#include "ac6_native_graphics_overlay.h"
#include "generated/ac6recomp_config.h"

REXCVAR_DECLARE(std::string, ac6_graphics_backend);

class Ac6recompApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  Ac6recompApp(rex::ui::WindowedAppContext& ctx, std::string_view name, rex::PPCImageInfo ppc_info)
      : rex::ReXApp(ctx, name, ppc_info) {
    REXLOG_INFO("Ac6recompApp constructor");
  }

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    REXLOG_INFO("Ac6recompApp::Create");
    return std::unique_ptr<Ac6recompApp>(new Ac6recompApp(ctx, "ac6recomp", PPCImageConfig));
  }

 protected:
  void OnPreSetup(rex::RuntimeConfig& config) override {
    REXLOG_INFO("Ac6recompApp::OnPreSetup");
    rex::ReXApp::OnPreSetup(config);

    const std::string requested_backend = REXCVAR_GET(ac6_graphics_backend);
#if REX_HAS_VULKAN
    if (requested_backend == "vulkan" || requested_backend == "auto") {
      config.graphics =
          REX_GRAPHICS_BACKEND(rex::graphics::vulkan::VulkanGraphicsSystem);
      REXLOG_INFO("Ac6recompApp: selected Vulkan graphics backend");
      return;
    }
#endif
#if REX_HAS_D3D12
    if (requested_backend == "d3d12" || requested_backend == "auto") {
      config.graphics =
          REX_GRAPHICS_BACKEND(rex::graphics::d3d12::D3D12GraphicsSystem);
      REXLOG_INFO("Ac6recompApp: selected D3D12 graphics backend");
      return;
    }
#endif
    REXLOG_WARN("Ac6recompApp: requested graphics backend '{}' is not available in this build",
                requested_backend);
  }

  void OnPostSetup() override {
    REXLOG_INFO("Ac6recompApp::OnPostSetup");
    rex::ReXApp::OnPostSetup();

    auto* graphics_sys = runtime()->graphics_system();
    if (graphics_sys) {
        graphics_sys->SetFrameBoundaryCallback([](rex::memory::Memory* memory) {
            ::ac6::graphics::OnFrameBoundary(memory);
        });
        REXLOG_INFO("Ac6recompApp: Native frame boundary callback registered");
    }
  }

  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    REXLOG_INFO("Ac6recompApp::OnCreateDialogs");
    native_graphics_status_dialog_ =
        std::make_unique<ac6::graphics::NativeGraphicsStatusDialog>(drawer);
    native_graphics_status_dialog_->Show();
  }

 private:
  std::unique_ptr<ac6::graphics::NativeGraphicsStatusDialog> native_graphics_status_dialog_;
};

