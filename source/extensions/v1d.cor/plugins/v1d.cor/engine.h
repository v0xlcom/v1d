// SPDX-License-Identifier: MIT
#pragma once

#include "converter.h"
#include "frame_cache.h"
#include "mp4_index.h"
#include "nvdec_decoder.h"
#include "present_ring.h"
#include "proxy_builder.h"
#include "proxy_store.h"

#include <atomic>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace v1d::scrub
{

struct EngineStats
{
    std::string state{ "idle" };
    std::string last_error;
    std::uint64_t requests{};
    std::uint64_t coalesced{};
    std::uint64_t aborted_runs{};
    std::uint64_t decoded_frames{};
    std::uint64_t cache_hits{};
    std::uint64_t cache_bytes{};
    std::uint64_t published{};
    std::uint64_t dropped_stale{};
    std::uint64_t hot_path_host_pixel_copies{};
    std::uint64_t debug_readbacks{};
    std::uint64_t proxy_d2h_bytes{};
    std::uint64_t proxy_h2d_bytes{};
    bool proxy_ready{ false };
    int proxy_build_frame{ 0 };
    int proxy_build_total{ 0 };
};

struct PresentedFrame
{
    std::uint64_t ptr{};
    int width{};
    int height{};
    int stride{};
    int frame{};
    std::uint32_t gen{};
    std::string tier;
    int latency_us{};
};

class Engine
{
public:
    Engine(int cuda_device, int cache_mb, const std::string& fatbin_path, int proxy_height = 270, int proxy_vram_mb = 256);
    ~Engine();

    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;

    ClipInfo open_clip(const std::string& path);
    void set_output_size(int width, int height);
    void set_scrubbing(bool scrubbing);
    void set_playback(bool playback);
    void request_frame(int presentation_index);

    std::optional<PresentedFrame> poll();
    std::optional<PresentedFrame> latest_present() const;
    bool copy_latest_rgba_to(std::uint64_t dst_ptr, int dst_stride);
    EngineStats stats() const;
    std::string debug_read_rgba(std::uint64_t device_ptr);

    void close();
    void shutdown();

private:
    struct PresentSlot
    {
        std::uint64_t rgba_ptr{};
        int stride{};
    };

    int cuda_device_{};
    int cache_mb_{};
    int proxy_height_{ 270 };
    int proxy_vram_mb_{ 256 };
    std::string fatbin_path_;
    std::string clip_path_;

    mutable std::mutex lifecycle_mu_;
    bool clip_open_{ false };
    Mp4Index index_;
    NvdecDecoder decoder_;
    FrameCache cache_;
    PresentRing present_ring_{ PresentRing::kDefaultHoldPolls };

    int out_w_{};
    int out_h_{};
    std::atomic<bool> scrubbing_{ false };
    std::atomic<bool> playback_{ false };

    std::vector<PresentSlot> present_slots_;
    std::vector<PresentedFrame> slot_meta_;

    PresentSlot latest_slot_{};
    PresentedFrame latest_meta_{};
    std::atomic<bool> latest_valid_{ false };
    mutable std::mutex latest_mu_;

    std::atomic<std::uint64_t> mailbox_{ 0 };
    std::atomic<std::uint32_t> request_gen_{ 0 };

    std::atomic<bool> stop_{ false };
    std::thread worker_;

    std::mutex decoder_mu_;
    ProxyIncrementalBuilder proxy_builder_;
    ProxyStore proxy_store_;
    std::atomic<bool> proxy_ready_{ false };
    std::atomic<std::uint64_t> proxy_d2h_bytes_{ 0 };
    std::atomic<std::uint64_t> proxy_h2d_bytes_{ 0 };
    std::atomic<bool> proxy_build_stop_{ false };
    std::thread proxy_thread_;

    std::atomic<std::uint64_t> requests_{ 0 };
    std::atomic<std::uint64_t> coalesced_{ 0 };
    std::atomic<std::uint64_t> decoded_frames_{ 0 };
    std::atomic<std::uint64_t> cache_hits_{ 0 };
    std::atomic<std::uint64_t> published_{ 0 };
    std::atomic<std::uint64_t> dropped_stale_{ 0 };
    std::atomic<std::uint64_t> debug_readbacks_{ 0 };
    std::string last_error_;
    std::string state_{ "idle" };

    void worker_main();
    void proxy_builder_main();
    void stop_proxy_builder();
    void try_open_proxy_store();
    bool publish_nv12(const Nv12Surface& nv12, int display_frame, std::uint32_t gen, const char* tier, int latency_us);
    bool publish_proxy_frame(int target, std::uint32_t gen, int latency_us);
    ColorMatrix color_matrix() const;
    std::size_t cache_budget_bytes() const;
    void free_present_slots();
    void alloc_present_slots();
    void free_latest_slot();
    void ensure_latest_slot(int width, int height);
    void refresh_latest_from_present(int slot, const PresentedFrame& meta);
    void prefetch_proxy_after_scrub(int target, int frame_max);

    int last_scrub_target_{ -1 };
};

} // namespace v1d::scrub
