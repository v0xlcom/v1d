// SPDX-License-Identifier: MIT
#pragma once

#include "mapped_file.h"
#include "proxy_format.h"

#include <cstdint>
#include <deque>
#include <string>
#include <unordered_map>

namespace v1d::scrub
{

class ProxyStore
{
public:
    static constexpr std::size_t kDefaultResidencyBytes = 256u * 1024u * 1024u;

    void set_residency_budget_bytes(std::size_t bytes);

    bool open_file(const std::string& path, std::string* err = nullptr);
    void close();

    bool is_open() const
    {
        return !map_.empty();
    }

    const ProxyHeader& header() const
    {
        return hdr_;
    }

    std::size_t residency_used_bytes() const
    {
        return residency_used_;
    }

    /** Upload one proxy NV12 frame to a new device allocation (caller frees). */
    bool load_frame_nv12(int presentation_index, std::uint64_t* device_ptr, int* pitch, std::uint64_t* h2d_bytes, std::string* err);

    /** Warm GPU LRU for shuttle scrub (PLAN_04); ignores errors. */
    void prefetch_linear(int center, int direction, int count, int frame_max);

private:
    struct GpuFrame
    {
        std::uint64_t device_ptr{};
        int pitch{};
        std::size_t bytes{};
    };

    MappedFile map_;
    ProxyHeader hdr_{};
    std::uint64_t frame_data_base_{};
    std::size_t residency_budget_{ kDefaultResidencyBytes };
    std::size_t residency_used_{};
    std::unordered_map<int, GpuFrame> gpu_cache_;
    std::deque<int> lru_order_;

    std::uint64_t frame_offset(int presentation_index) const;
    void evict_one();
    bool ensure_gpu_cached(int presentation_index, std::string* err);
};

} // namespace v1d::scrub
