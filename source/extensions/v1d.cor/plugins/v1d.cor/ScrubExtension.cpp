// SPDX-License-Identifier: MIT
#define CARB_EXPORTS

#include <carb/PluginUtils.h>
#include <omni/ext/IExt.h>

const struct carb::PluginImplDesc pluginImplDesc = { "v1d.cor.plugin", "v1d cor engine shell", "MIT",
                                                     carb::PluginHotReload::eDisabled, "dev" };

namespace v1d::scrub
{

class ScrubExtensionPlugin : public omni::ext::IExt
{
public:
    void onStartup(const char* /*extId*/) override {}
    void onShutdown() override {}
};

} // namespace v1d::scrub

CARB_PLUGIN_IMPL(pluginImplDesc, v1d::scrub::ScrubExtensionPlugin)

void fillInterface(v1d::scrub::ScrubExtensionPlugin&)
{
}
