// SPDX-License-Identifier: MIT
#include "frame_cache.h"

#include "cuda_context.h"

#include <algorithm>
#include <cmath>

namespace v1d::scrub
{

void FrameCache::set_budget_bytes(std::size_t bytes)
{
    budget_bytes_ = bytes;
    while (used_bytes_ > budget_bytes_ && !entries_.empty())
        evict_one(0);
}

std::size_t FrameCache::surface_bytes(const Nv12Surface& s)
{
    if (!s.device_ptr || s.pitch <= 0 || s.height <= 0)
        return 0;
    const int luma_rows = s.luma_surface_rows > 0 ? s.luma_surface_rows : s.height;
    return static_cast<std::size_t>(s.pitch) * static_cast<std::size_t>(luma_rows * 3 / 2);
}

bool FrameCache::contains(int presentation_index) const
{
    return entries_.find(presentation_index) != entries_.end();
}

const Nv12Surface* FrameCache::get(int presentation_index) const
{
    const auto it = entries_.find(presentation_index);
    if (it == entries_.end())
        return nullptr;
    return &it->second.surface;
}

void FrameCache::evict_one(int evict_target)
{
    if (entries_.empty())
        return;
    int best_key = entries_.begin()->first;
    int best_dist = std::abs(best_key - evict_target);
    for (const auto& kv : entries_)
    {
        const int d = std::abs(kv.first - evict_target);
        if (d > best_dist)
        {
            best_dist = d;
            best_key = kv.first;
        }
    }
    const auto it = entries_.find(best_key);
    if (it == entries_.end())
        return;
    if (it->second.surface.device_ptr)
        cuda_free(it->second.surface.device_ptr);
    used_bytes_ -= surface_bytes(it->second.surface);
    entries_.erase(it);
}

void FrameCache::put(int presentation_index, Nv12Surface surface, int evict_target)
{
    if (!surface.device_ptr)
        return;
    auto it = entries_.find(presentation_index);
    if (it != entries_.end())
    {
        used_bytes_ -= surface_bytes(it->second.surface);
        if (it->second.surface.device_ptr)
            cuda_free(it->second.surface.device_ptr);
        entries_.erase(it);
    }
    const std::size_t need = surface_bytes(surface);
    while (used_bytes_ + need > budget_bytes_ && !entries_.empty())
        evict_one(evict_target);
    entries_[presentation_index] = Entry{ surface };
    used_bytes_ += need;
}

void FrameCache::clear()
{
    for (auto& kv : entries_)
    {
        if (kv.second.surface.device_ptr)
            cuda_free(kv.second.surface.device_ptr);
    }
    entries_.clear();
    used_bytes_ = 0;
}

} // namespace v1d::scrub
