// SPDX-License-Identifier: MIT
#include "proxy_store.h"

#include "cuda_context.h"

namespace v1d::scrub
{

void ProxyStore::set_residency_budget_bytes(std::size_t bytes)
{
    residency_budget_ = bytes > 0 ? bytes : kDefaultResidencyBytes;
    while (residency_used_ > residency_budget_ && !lru_order_.empty())
        evict_one();
}

void ProxyStore::evict_one()
{
    if (lru_order_.empty())
        return;
    const int idx = lru_order_.front();
    lru_order_.pop_front();
    const auto it = gpu_cache_.find(idx);
    if (it == gpu_cache_.end())
        return;
    if (it->second.device_ptr)
        cuda_free(it->second.device_ptr);
    residency_used_ -= it->second.bytes;
    gpu_cache_.erase(it);
}

bool ProxyStore::open_file(const std::string& path, std::string* err)
{
    close();
    ProxyHeader h {};
    if (!proxy_read_header_file(path, &h, err))
        return false;
    try
    {
        map_.open(path);
    }
    catch (const std::exception& ex)
    {
        if (err)
            *err = ex.what();
        return false;
    }
    hdr_ = h;
    frame_data_base_ = sizeof(ProxyHeader);
    return true;
}

void ProxyStore::close()
{
    for (auto& [idx, frame] : gpu_cache_)
    {
        if (frame.device_ptr)
            cuda_free(frame.device_ptr);
    }
    gpu_cache_.clear();
    lru_order_.clear();
    residency_used_ = 0;
    map_.close();
    hdr_ = {};
    frame_data_base_ = 0;
}

std::uint64_t ProxyStore::frame_offset(int presentation_index) const
{
    if (presentation_index < 0 || presentation_index >= static_cast<int>(hdr_.frame_count))
        return 0;
    return frame_data_base_ + static_cast<std::uint64_t>(presentation_index) * hdr_.frame_bytes;
}

bool ProxyStore::ensure_gpu_cached(int presentation_index, std::string* err)
{
    if (gpu_cache_.count(presentation_index))
        return true;

    const auto off = frame_offset(presentation_index);
    const auto need = hdr_.frame_bytes;
    if (off + need > map_.size())
    {
        if (err)
            *err = "proxy frame past EOF";
        return false;
    }

    const int w = static_cast<int>(hdr_.proxy_width);
    const int h = static_cast<int>(hdr_.proxy_height);
    int pitch = 0;
    const std::uint64_t dev = cuda_alloc_nv12(w, h, &pitch, err);
    if (dev == 0)
        return false;
    const std::size_t bytes = static_cast<std::size_t>(pitch) * static_cast<size_t>(h) * 3u / 2u;

    while (residency_used_ + bytes > residency_budget_ && !lru_order_.empty())
        evict_one();

    if (!cuda_copy_nv12_from_host(map_.data() + off, static_cast<int>(need), w, h, dev, err))
    {
        cuda_free(dev);
        return false;
    }

    gpu_cache_[presentation_index] = GpuFrame{ dev, pitch, bytes };
    lru_order_.push_back(presentation_index);
    residency_used_ += bytes;
    return true;
}

void ProxyStore::prefetch_linear(int center, int direction, int count, int frame_max)
{
    if (!is_open() || direction == 0 || count <= 0 || frame_max < 0)
        return;
    for (int i = 1; i <= count; ++i)
    {
        const int idx = center + i * direction;
        if (idx < 0 || idx > frame_max)
            break;
        std::string err;
        ensure_gpu_cached(idx, &err);
    }
}

bool ProxyStore::load_frame_nv12(
    int presentation_index,
    std::uint64_t* device_ptr,
    int* pitch,
    std::uint64_t* h2d_bytes,
    std::string* err)
{
    if (!is_open() || !device_ptr)
    {
        if (err)
            *err = "proxy store not open";
        return false;
    }

    if (!ensure_gpu_cached(presentation_index, err))
        return false;

    auto& cached = gpu_cache_.at(presentation_index);
    for (auto it = lru_order_.begin(); it != lru_order_.end(); ++it)
    {
        if (*it == presentation_index)
        {
            lru_order_.erase(it);
            break;
        }
    }
    lru_order_.push_back(presentation_index);

    const int w = static_cast<int>(hdr_.proxy_width);
    const int h = static_cast<int>(hdr_.proxy_height);
    int out_pitch = 0;
    const std::uint64_t out_dev = cuda_alloc_nv12(w, h, &out_pitch, err);
    if (out_dev == 0)
        return false;

    if (!cuda_copy_nv12_d2d(cached.device_ptr, cached.pitch, w, h, out_dev, out_pitch, err))
    {
        cuda_free(out_dev);
        return false;
    }

    *device_ptr = out_dev;
    if (pitch)
        *pitch = out_pitch;
    if (h2d_bytes)
        *h2d_bytes = 0;
    return true;
}

} // namespace v1d::scrub
