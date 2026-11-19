// SPDX-License-Identifier: MIT
#include "engine.h"

#include "converter.h"
#include "cuda_context.h"
#include "scrub_error.h"

#include <chrono>
#include <cmath>
#include <cstring>
#include <thread>

namespace v1d::scrub
{

namespace
{

int even_down(int v)
{
    return v <= 0 ? 0 : (v & ~1);
}

} // namespace

Engine::Engine(int cuda_device, int cache_mb, const std::string& fatbin_path, int proxy_height, int proxy_vram_mb)
    : cuda_device_(cuda_device)
    , cache_mb_(cache_mb)
    , proxy_height_(proxy_height < 2 ? 270 : proxy_height)
    , proxy_vram_mb_(proxy_vram_mb < 1 ? 256 : proxy_vram_mb)
    , fatbin_path_(fatbin_path)
{
    proxy_store_.set_residency_budget_bytes(static_cast<std::size_t>(proxy_vram_mb_) * 1024u * 1024u);
    slot_meta_.resize(static_cast<std::size_t>(present_ring_.slot_count()));
}

Engine::~Engine()
{
    shutdown();
}

std::size_t Engine::cache_budget_bytes() const
{
    if (cache_mb_ > 0)
        return static_cast<std::size_t>(cache_mb_) * 1024u * 1024u;
    std::size_t free_b{}, total_b{};
    std::string err;
    if (cuda_mem_info(&free_b, &total_b, &err))
    {
        const std::size_t quarter = free_b / 4;
        const std::size_t cap = 2u * 1024u * 1024u * 1024u;
        return std::min(cap, quarter);
    }
    return 512u * 1024u * 1024u;
}

ColorMatrix Engine::color_matrix() const
{
    if (!clip_open_)
        return ColorMatrix::BT709;
    return index_.info().height >= 720 ? ColorMatrix::BT709 : ColorMatrix::BT601;
}

void Engine::free_latest_slot()
{
    if (latest_slot_.rgba_ptr)
        cuda_free(latest_slot_.rgba_ptr);
    latest_slot_ = {};
    latest_meta_ = {};
    latest_valid_.store(false, std::memory_order_release);
}

void Engine::ensure_latest_slot(int width, int height)
{
    if (latest_slot_.rgba_ptr && latest_meta_.width == width && latest_meta_.height == height)
        return;
    free_latest_slot();
    std::string err;
    int stride{};
    latest_slot_.rgba_ptr = cuda_alloc_rgba(width, height, &stride, &err);
    if (latest_slot_.rgba_ptr == 0)
        throw ScrubError(err.empty() ? "latest slot alloc failed" : err);
    latest_slot_.stride = stride;
    latest_meta_.width = width;
    latest_meta_.height = height;
    latest_meta_.stride = stride;
    latest_meta_.ptr = latest_slot_.rgba_ptr;
}

void Engine::refresh_latest_from_present(int slot, const PresentedFrame& meta)
{
    std::lock_guard<std::mutex> lock(latest_mu_);
    const auto& src = present_slots_[static_cast<std::size_t>(slot)];
    ensure_latest_slot(meta.width, meta.height);
    std::string err;
    if (!cuda_copy_rgba_d2d(
            src.rgba_ptr,
            src.stride,
            latest_slot_.rgba_ptr,
            latest_slot_.stride,
            meta.width,
            meta.height,
            &err))
    {
        last_error_ = err;
        latest_valid_.store(false, std::memory_order_release);
        return;
    }
    latest_meta_ = meta;
    latest_meta_.ptr = latest_slot_.rgba_ptr;
    latest_meta_.stride = latest_slot_.stride;
    latest_valid_.store(true, std::memory_order_release);
}

void Engine::free_present_slots()
{
    free_latest_slot();
    for (auto& s : present_slots_)
    {
        if (s.rgba_ptr)
            cuda_free(s.rgba_ptr);
        s = {};
    }
    present_slots_.clear();
}

void Engine::alloc_present_slots()
{
    free_present_slots();
    present_slots_.resize(static_cast<std::size_t>(present_ring_.slot_count()));
    std::string err;
    for (auto& s : present_slots_)
    {
        int stride{};
        s.rgba_ptr = cuda_alloc_rgba(out_w_, out_h_, &stride, &err);
        if (s.rgba_ptr == 0)
            throw ScrubError(err.empty() ? "present slot alloc failed" : err);
        s.stride = stride;
    }
}

void Engine::try_open_proxy_store()
{
    const std::string& path = proxy_builder_.cache_path();
    if (path.empty())
        return;
    std::string perr;
    if (proxy_store_.open_file(path, &perr))
        proxy_ready_.store(true, std::memory_order_release);
}

void Engine::stop_proxy_builder()
{
    proxy_build_stop_.store(true, std::memory_order_release);
    if (proxy_thread_.joinable())
        proxy_thread_.join();
    proxy_build_stop_.store(false, std::memory_order_release);
}

void Engine::proxy_builder_main()
{
    while (!proxy_build_stop_.load(std::memory_order_acquire))
    {
        if (!clip_open_ || scrubbing_.load(std::memory_order_acquire) || playback_.load(std::memory_order_acquire))
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(8));
            continue;
        }
        if (proxy_builder_.complete())
        {
            if (!proxy_ready_.load(std::memory_order_acquire))
                try_open_proxy_store();
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            continue;
        }

        const auto should_yield = [this]() {
            return proxy_build_stop_.load(std::memory_order_acquire) || scrubbing_.load(std::memory_order_acquire) ||
                playback_.load(std::memory_order_acquire);
        };

        std::uint64_t d2h_add = 0;
        std::string step_err;
        ProxyIncrementalBuilder::StepResult result = ProxyIncrementalBuilder::StepResult::Error;
        try
        {
            result = proxy_builder_.step_one_frame(should_yield, &d2h_add, &step_err);
        }
        catch (const std::exception& ex)
        {
            last_error_ = ex.what();
            // One failed frame used to abort the process. Retrying it in a loop holds the
            // decoder and makes playback lag. Wait until this clip is closed.
            while (!proxy_build_stop_.load(std::memory_order_acquire) && clip_open_)
                std::this_thread::sleep_for(std::chrono::milliseconds(50));
            continue;
        }
        if (d2h_add)
            proxy_d2h_bytes_.fetch_add(d2h_add, std::memory_order_relaxed);
        if (!step_err.empty())
            last_error_ = step_err;

        if (result == ProxyIncrementalBuilder::StepResult::Complete)
        {
            proxy_ready_.store(true, std::memory_order_release);
            try_open_proxy_store();
            state_ = "ready";
        }
        else if (result == ProxyIncrementalBuilder::StepResult::Error)
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        else if (result == ProxyIncrementalBuilder::StepResult::Yield)
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        else if (result == ProxyIncrementalBuilder::StepResult::Progress)
            std::this_thread::sleep_for(std::chrono::milliseconds(8));
    }
}

ClipInfo Engine::open_clip(const std::string& path)
{
    std::lock_guard<std::mutex> lock(lifecycle_mu_);
    close();
    std::string err;
    if (!cuda_init(cuda_device_, fatbin_path_, &err))
        throw ScrubError(err);
    index_ = Mp4Index::open(path);
    clip_path_ = path;
    decoder_.open(index_);
    cache_.set_budget_bytes(cache_budget_bytes());
    const auto& info = index_.info();
    out_w_ = even_down(std::min(info.width, info.width));
    out_h_ = even_down(std::min(info.height, info.height));
    alloc_present_slots();
    proxy_ready_.store(false, std::memory_order_release);
    proxy_d2h_bytes_.store(0, std::memory_order_relaxed);
    proxy_h2d_bytes_.store(0, std::memory_order_relaxed);
    proxy_store_.close();
    std::string perr;
    if (!proxy_builder_.prepare(path, proxy_height_, info, &perr))
        last_error_ = perr;
    else if (proxy_builder_.complete())
    {
        proxy_ready_.store(true, std::memory_order_release);
        try_open_proxy_store();
    }
    last_scrub_target_ = -1;
    clip_open_ = true;
    state_ = proxy_builder_.complete() ? "ready" : "proxy_build";
    stop_ = false;
    worker_ = std::thread([this] { worker_main(); });
    proxy_build_stop_.store(false, std::memory_order_release);
    proxy_thread_ = std::thread([this] { proxy_builder_main(); });
    return info;
}

void Engine::set_output_size(int width, int height)
{
    if (!clip_open_)
        return;
    const auto& info = index_.info();
    out_w_ = even_down(std::min(width, info.width));
    out_h_ = even_down(std::min(height, info.height));
    alloc_present_slots();
}

void Engine::set_scrubbing(bool scrubbing)
{
    scrubbing_.store(scrubbing, std::memory_order_release);
}

void Engine::set_playback(bool playback)
{
    playback_.store(playback, std::memory_order_release);
}

void Engine::request_frame(int presentation_index)
{
    if (!clip_open_)
        return;
    const int frames = index_.info().frames;
    if (frames <= 0)
        return;
    if (presentation_index < 0)
        presentation_index = 0;
    if (presentation_index >= frames)
        presentation_index = frames - 1;
    const std::uint32_t gen = request_gen_.fetch_add(1, std::memory_order_relaxed) + 1;
    const std::uint64_t mb = (static_cast<std::uint64_t>(gen) << 32) |
                            static_cast<std::uint32_t>(presentation_index);
    const std::uint64_t prev = mailbox_.load(std::memory_order_acquire);
    mailbox_.store(mb, std::memory_order_release);
    if (prev != 0 && prev != mb)
        coalesced_.fetch_add(1, std::memory_order_relaxed);
    mailbox_.notify_all();
    requests_.fetch_add(1, std::memory_order_relaxed);
}

bool Engine::publish_proxy_frame(int target, std::uint32_t gen, int latency_us)
{
    std::uint64_t dev = 0;
    int pitch = 0;
    std::uint64_t h2d = 0;
    std::string perr;
    if (!proxy_store_.load_frame_nv12(target, &dev, &pitch, &h2d, &perr))
    {
        last_error_ = perr;
        return false;
    }
    proxy_h2d_bytes_.fetch_add(h2d, std::memory_order_relaxed);
    const auto& hdr = proxy_store_.header();
    Nv12Surface nv12{};
    nv12.device_ptr = dev;
    nv12.width = static_cast<int>(hdr.proxy_width);
    nv12.height = static_cast<int>(hdr.proxy_height);
    nv12.pitch = pitch;
    nv12.luma_surface_rows = nv12.height;
    const bool ok = publish_nv12(nv12, target, gen, "proxy", latency_us);
    cuda_free(dev);
    return ok;
}

bool Engine::publish_nv12(
    const Nv12Surface& nv12, int display_frame, std::uint32_t gen, const char* tier, int latency_us)
{
    const auto slot_opt = present_ring_.acquire_writing();
    if (!slot_opt)
        return false;
    const int slot = *slot_opt;
    std::string err;
    if (!convert_nv12_to_rgba8(
            nv12.device_ptr,
            nv12.pitch,
            nv12.width,
            nv12.height,
            nv12.luma_surface_rows > 0 ? nv12.luma_surface_rows : nv12.height,
            index_.info().bit_depth,
            present_slots_[static_cast<std::size_t>(slot)].rgba_ptr,
            present_slots_[static_cast<std::size_t>(slot)].stride,
            out_w_,
            out_h_,
            color_matrix(),
            ColorRange::Limited,
            &err))
    {
        last_error_ = err;
        present_ring_.abandon_writing(slot);
        return false;
    }
    present_ring_.publish_ready(slot);
    PresentedFrame meta{};
    meta.ptr = present_slots_[static_cast<std::size_t>(slot)].rgba_ptr;
    meta.width = out_w_;
    meta.height = out_h_;
    meta.stride = present_slots_[static_cast<std::size_t>(slot)].stride;
    meta.frame = display_frame;
    meta.gen = gen;
    meta.tier = tier;
    meta.latency_us = latency_us;
    slot_meta_[static_cast<std::size_t>(slot)] = meta;
    refresh_latest_from_present(slot, meta);
    published_.fetch_add(1, std::memory_order_relaxed);
    return true;
}

std::optional<PresentedFrame> Engine::latest_present() const
{
    if (!latest_valid_.load(std::memory_order_acquire))
        return std::nullopt;
    std::lock_guard<std::mutex> lock(latest_mu_);
    if (!latest_valid_.load(std::memory_order_relaxed))
        return std::nullopt;
    return latest_meta_;
}

bool Engine::copy_latest_rgba_to(std::uint64_t dst_ptr, int dst_stride)
{
    if (!latest_valid_.load(std::memory_order_acquire))
        return false;
    std::lock_guard<std::mutex> lock(latest_mu_);
    if (!latest_valid_.load(std::memory_order_relaxed) || !latest_slot_.rgba_ptr)
        return false;
    std::string err;
    return cuda_copy_rgba_d2d(
        latest_slot_.rgba_ptr,
        latest_slot_.stride,
        dst_ptr,
        dst_stride,
        latest_meta_.width,
        latest_meta_.height,
        &err);
}

void Engine::worker_main()
{
    std::uint64_t seen_mb = 0;
    while (!stop_.load(std::memory_order_acquire))
    {
        const std::uint64_t mb = mailbox_.load(std::memory_order_acquire);
        if (mb == 0 || mb == seen_mb)
        {
            mailbox_.wait(mb, std::memory_order_acquire);
            continue;
        }

        std::uint64_t work_mb = mb;
        while (true)
        {
            const std::uint64_t newer = mailbox_.load(std::memory_order_acquire);
            if (newer == work_mb)
                break;
            work_mb = newer;
            coalesced_.fetch_add(1, std::memory_order_relaxed);
        }
        const std::uint32_t gen = static_cast<std::uint32_t>(work_mb >> 32);
        int target = static_cast<int>(work_mb & 0xffffffffu);
        const int frames = index_.info().frames;
        if (target < 0)
            target = 0;
        if (target >= frames)
            target = frames - 1;

        const auto t0 = std::chrono::steady_clock::now();

        // Proxy while scrubbing (arrow tap/hold, ruler, play — play keeps scrubbing on).
        // Not when scrubbing is off: arrow release / stop must hit tier=exact.
        if (scrubbing_.load(std::memory_order_acquire) && proxy_ready_.load(std::memory_order_acquire) &&
            proxy_store_.is_open())
        {
            const auto t1 = std::chrono::steady_clock::now();
            const int latency_us =
                static_cast<int>(std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count());
            if (publish_proxy_frame(target, gen, latency_us))
            {
                prefetch_proxy_after_scrub(target, frames - 1);
                seen_mb = work_mb;
                continue;
            }
        }

        int decode_index = target;
        const char* tier = "exact";
        if (!playback_.load(std::memory_order_acquire) && scrubbing_.load(std::memory_order_acquire))
        {
            const int sync = index_.sync_at_or_before(target);
            if (sync != target)
            {
                decode_index = sync;
                tier = "snap";
            }
        }

        const Nv12Surface* cached = cache_.get(decode_index);
        Nv12Surface nv12{};
        bool owned = false;
        if (cached)
        {
            nv12 = *cached;
            cache_hits_.fetch_add(1, std::memory_order_relaxed);
        }
        else
        {
            try
            {
                std::lock_guard<std::mutex> dec_lock(decoder_mu_);
                nv12 = decoder_.decode_presentation_frame(decode_index);
                owned = true;
                decoded_frames_.fetch_add(1, std::memory_order_relaxed);
            }
            catch (const std::exception& ex)
            {
                last_error_ = ex.what();
                continue;
            }
        }

        if (mailbox_.load(std::memory_order_acquire) != work_mb)
        {
            dropped_stale_.fetch_add(1, std::memory_order_relaxed);
            if (owned && nv12.device_ptr)
                cuda_free(nv12.device_ptr);
            continue;
        }

        const auto t1 = std::chrono::steady_clock::now();
        const int latency_us =
            static_cast<int>(std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count());

        const int display_frame = (std::strcmp(tier, "snap") == 0) ? decode_index : target;

        if (publish_nv12(nv12, display_frame, gen, tier, latency_us))
            seen_mb = work_mb;

        if (owned && nv12.device_ptr)
            cache_.put(decode_index, std::move(nv12), target);
    }
}

void Engine::prefetch_proxy_after_scrub(int target, int frame_max)
{
    if (!scrubbing_.load(std::memory_order_acquire) || !proxy_ready_.load(std::memory_order_acquire) ||
        !proxy_store_.is_open())
        return;
    int direction = 1;
    if (last_scrub_target_ >= 0)
    {
        const int diff = target - last_scrub_target_;
        if (diff < 0)
            direction = -1;
        else if (diff == 0)
        {
            proxy_store_.prefetch_linear(target, 1, 8, frame_max);
            proxy_store_.prefetch_linear(target, -1, 8, frame_max);
            return;
        }
    }
    last_scrub_target_ = target;
    proxy_store_.prefetch_linear(target, direction, 8, frame_max);
}

std::optional<PresentedFrame> Engine::poll()
{
    const auto slot = present_ring_.poll();
    if (!slot)
        return std::nullopt;
    return slot_meta_[static_cast<std::size_t>(*slot)];
}

EngineStats Engine::stats() const
{
    EngineStats s;
    s.state = state_;
    s.last_error = last_error_;
    s.requests = requests_.load(std::memory_order_relaxed);
    s.coalesced = coalesced_.load(std::memory_order_relaxed);
    s.decoded_frames = decoded_frames_.load(std::memory_order_relaxed);
    s.cache_hits = cache_hits_.load(std::memory_order_relaxed);
    s.cache_bytes = cache_.used_bytes();
    s.published = published_.load(std::memory_order_relaxed);
    s.dropped_stale = dropped_stale_.load(std::memory_order_relaxed);
    s.hot_path_host_pixel_copies = 0;
    s.debug_readbacks = debug_readbacks_.load(std::memory_order_relaxed);
    s.proxy_d2h_bytes = proxy_d2h_bytes_.load(std::memory_order_relaxed);
    s.proxy_h2d_bytes = proxy_h2d_bytes_.load(std::memory_order_relaxed);
    s.proxy_ready = proxy_ready_.load(std::memory_order_relaxed);
    s.proxy_build_frame = proxy_builder_.progress_frame();
    s.proxy_build_total = proxy_builder_.total_frames();
    return s;
}

std::string Engine::debug_read_rgba(std::uint64_t device_ptr)
{
    debug_readbacks_.fetch_add(1, std::memory_order_relaxed);
    std::string pixels;
    std::string err;
    for (const auto& slot : present_slots_)
    {
        if (slot.rgba_ptr == device_ptr)
        {
            if (!cuda_read_rgba_device(device_ptr, out_w_, out_h_, slot.stride, &pixels, &err))
                throw ScrubError(err);
            return pixels;
        }
    }
    if (latest_slot_.rgba_ptr == device_ptr)
    {
        if (!cuda_read_rgba_device(
                device_ptr, latest_meta_.width, latest_meta_.height, latest_slot_.stride, &pixels, &err))
            throw ScrubError(err);
        return pixels;
    }
    throw ScrubError("unknown present ptr");
}

void Engine::close()
{
    stop_proxy_builder();
    stop_ = true;
    mailbox_.fetch_add(1, std::memory_order_release);
    mailbox_.notify_all();
    if (worker_.joinable())
        worker_.join();
    proxy_store_.close();
    proxy_builder_.reset();
    proxy_ready_.store(false, std::memory_order_release);
    decoder_.close();
    cache_.clear();
    free_present_slots();
    index_ = Mp4Index{};
    clip_open_ = false;
    mailbox_.store(0, std::memory_order_release);
    stop_ = false;
    state_ = "idle";
}

void Engine::shutdown()
{
    std::lock_guard<std::mutex> lock(lifecycle_mu_);
    close();
    if (cuda_ready())
        cuda_shutdown();
}

} // namespace v1d::scrub
