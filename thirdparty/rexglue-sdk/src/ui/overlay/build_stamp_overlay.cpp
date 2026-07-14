/**
 * @file        ui/overlay/build_stamp_overlay.cpp
 * @brief       Always-on build-stamp watermark. See build_stamp_overlay.h.
 *
 * @copyright   Copyright (c) 2026 Project Gracemeria
 * @license     BSD 3-Clause License
 */
#include <rex/ui/overlay/build_stamp_overlay.h>
#include <rex/cvar.h>
#include <rex/version.h>
#include <imgui.h>

REXCVAR_DEFINE_BOOL(show_build_stamp, true, "UI",
                    "Draw the build-stamp watermark (short git commit hash) in the "
                    "lower-left corner. On by default; set false to hide it.");

namespace rex::ui {

BuildStampOverlay::BuildStampOverlay(ImGuiDrawer* imgui_drawer) : ImGuiDialog(imgui_drawer) {}

void BuildStampOverlay::OnDraw(ImGuiIO& io) {
  if (!REXCVAR_GET(show_build_stamp))
    return;

  const float margin = io.DisplaySize.y * 0.02f;
  const ImVec2 size = ImGui::CalcTextSize(REXGLUE_BUILD_HASH_STAMP);
  ImGui::SetNextWindowPos(ImVec2(margin, io.DisplaySize.y - size.y - margin));
  ImGui::SetNextWindowSize(ImVec2(0, 0));
  ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 1.0f, 1.0f, 0.5f));
  if (ImGui::Begin("##buildstamp", nullptr,
                   ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoBackground |
                       ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav |
                       ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_AlwaysAutoResize)) {
    ImGui::TextUnformatted(REXGLUE_BUILD_HASH_STAMP);
  }
  ImGui::End();
  ImGui::PopStyleColor();
}

}  // namespace rex::ui
