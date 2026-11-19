// SPDX-License-Identifier: MIT
#pragma once

#include "mp4_index.h"
#include "nvdec_decoder.h"
#include "proxy_format.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <vector>

namespace v1d::scrub
{

struct ProxyBuildResult
{
    std::string cache_path;
    bool rebuilt{ false };
    std::uint64_t bytes_written{ 0 };
    double build_seconds{ 0.0 };
};

/** Synchronous proxy build (C11 / tests). Skips work when a valid cache file exists. */
bool build_proxy_cache(
    const std::string& clip_path,
    int proxy_height,
    int cuda_device,
    const std::string& fatbin_path,
    ProxyBuildResult* out,
    std::string* err);

/** Background-friendly incremental builder (one presentation frame per successful step). */
class ProxyIncrementalBuilder
{
public:
    enum class StepResult
    {
        Complete,
        Progress,
        Yield,
        Error,
    };

    void reset();

    /** Returns true when no build needed (cache hit) or build session started. */
    bool prepare(const std::string& clip_path, int proxy_height, const ClipInfo& info, std::string* err);

    bool complete() const
    {
        return complete_;
    }

    const std::string& cache_path() const
    {
        return final_path_;
    }

    int progress_frame() const
    {
        return next_frame_;
    }

    int total_frames() const
    {
        return total_frames_;
    }

    StepResult step_one_frame(
        const std::function<bool()>& should_yield,
        std::uint64_t* d2h_bytes_added,
        std::string* err);

private:
    bool complete_{ false };
    bool index_open_{ false };
    Mp4Index index_;
    NvdecDecoder decoder_;
    std::string final_path_;
    std::string temp_path_;
    int fd_{ -1 };
    int next_frame_{ 0 };
    int total_frames_{ 0 };
    int proxy_w_{};
    int proxy_h_{};
    std::uint64_t frame_bytes_{};
    ProxyHeader hdr_{};
    std::uint64_t write_offset_{};
    std::uint64_t dst_nv12_{};
    int dst_pitch_{};
    std::vector<std::uint64_t> index_entries_;
    std::vector<std::uint8_t> host_frame_;
};

} // namespace v1d::scrub
