// SPDX-License-Identifier: MIT
#pragma once

#include "nvdec_decoder.h"

#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace v1d::scrub
{

class FrameCache
{
public:
    void set_budget_bytes(std::size_t bytes);
    std::size_t budget_bytes() const { return budget_bytes_; }
    std::size_t used_bytes() const { return used_bytes_; }

    bool contains(int presentation_index) const;
    const Nv12Surface* get(int presentation_index) const;

    void put(int presentation_index, Nv12Surface surface, int evict_target);
    void clear();

private:
    struct Entry
    {
        Nv12Surface surface{};
    };

    std::size_t budget_bytes_{};
    std::size_t used_bytes_{};
    std::unordered_map<int, Entry> entries_;

    static std::size_t surface_bytes(const Nv12Surface& s);
    void evict_one(int evict_target);
};

} // namespace v1d::scrub
