// SPDX-License-Identifier: MIT
#include "proxy_builder.h"

#include "cuda_context.h"
#include "nvdec_decoder.h"
#include "proxy_format.h"
#include "scrub_error.h"

#include <chrono>
#include <cmath>
#include <cstring>
#include <exception>
#include <fcntl.h>
#include <filesystem>
#include <unistd.h>
#include <vector>

namespace v1d::scrub
{

namespace
{

bool file_size_ok(const std::string& path, std::uint64_t expected, std::string* err)
{
    std::error_code ec;
    const auto sz = std::filesystem::file_size(path, ec);
    if (ec)
        return false;
    if (sz != expected)
    {
        if (err)
            *err = "proxy file size mismatch";
        return false;
    }
    return true;
}

} // namespace

void ProxyIncrementalBuilder::reset()
{
    if (fd_ >= 0)
        ::close(fd_);
    if (!temp_path_.empty())
        ::unlink(temp_path_.c_str());
    if (dst_nv12_)
        cuda_free(dst_nv12_);
    complete_ = false;
    final_path_.clear();
    temp_path_.clear();
    fd_ = -1;
    next_frame_ = 0;
    total_frames_ = 0;
    proxy_w_ = proxy_h_ = 0;
    frame_bytes_ = 0;
    hdr_ = {};
    write_offset_ = 0;
    dst_nv12_ = 0;
    dst_pitch_ = 0;
    index_entries_.clear();
    host_frame_.clear();
    decoder_.close();
    index_ = Mp4Index();
    index_open_ = false;
}

bool ProxyIncrementalBuilder::prepare(const std::string& clip_path, int proxy_height, const ClipInfo& info, std::string* err)
{
    reset();
    if (proxy_height < 2)
        proxy_height = 270;

    std::string id_err;
    const ProxySourceIdentity id = proxy_source_identity(clip_path, &id_err);
    if (!id_err.empty())
    {
        if (err)
            *err = id_err;
        return false;
    }

    final_path_ = proxy_cache_file_path(id);
    ProxyHeader existing {};
    if (proxy_read_header_file(final_path_, &existing, nullptr))
    {
        const auto expected = proxy_file_size_bytes(existing);
        if (proxy_header_matches_source(existing, id, info) && file_size_ok(final_path_, expected, nullptr))
        {
            complete_ = true;
            next_frame_ = info.frames;
            total_frames_ = info.frames;
            return true;
        }
    }

    std::filesystem::create_directories(std::filesystem::path(final_path_).parent_path());
    temp_path_ = proxy_cache_temp_path(final_path_);
    ::unlink(temp_path_.c_str());
    fd_ = ::open(temp_path_.c_str(), O_RDWR | O_CREAT | O_TRUNC, 0644);
    if (fd_ < 0)
    {
        if (err)
            *err = std::string("open temp proxy: ") + std::strerror(errno);
        return false;
    }

    proxy_even_proxy_dims(info.width, info.height, proxy_height, &proxy_w_, &proxy_h_);
    frame_bytes_ = proxy_nv12_frame_bytes(static_cast<std::uint32_t>(proxy_w_), static_cast<std::uint32_t>(proxy_h_));
    total_frames_ = info.frames;

    hdr_.path_hash = id.path_hash;
    hdr_.source_size_bytes = id.size_bytes;
    hdr_.source_mtime_ns = id.mtime_ns;
    hdr_.source_width = static_cast<std::uint32_t>(info.width);
    hdr_.source_height = static_cast<std::uint32_t>(info.height);
    hdr_.proxy_width = static_cast<std::uint32_t>(proxy_w_);
    hdr_.proxy_height = static_cast<std::uint32_t>(proxy_h_);
    hdr_.frame_count = static_cast<std::uint32_t>(info.frames);
    hdr_.frame_bytes = frame_bytes_;
    hdr_.index_offset = sizeof(ProxyHeader) + static_cast<std::uint64_t>(info.frames) * frame_bytes_;
    write_offset_ = sizeof(ProxyHeader);

    if (!proxy_write_header(fd_, hdr_, err))
        return false;

    dst_nv12_ = cuda_alloc_nv12(proxy_w_, proxy_h_, &dst_pitch_, err);
    if (dst_nv12_ == 0)
        return false;

    try
    {
        index_ = Mp4Index::open(clip_path);
        decoder_.open(index_);
        index_open_ = true;
    }
    catch (const std::exception& ex)
    {
        if (err)
            *err = ex.what();
        return false;
    }

    index_entries_.reserve(static_cast<std::size_t>(info.frames));
    return true;
}

ProxyIncrementalBuilder::StepResult ProxyIncrementalBuilder::step_one_frame(
    const std::function<bool()>& should_yield,
    std::uint64_t* d2h_bytes_added,
    std::string* err)
{
    if (complete_)
        return StepResult::Complete;
    if (should_yield && should_yield())
        return StepResult::Yield;
    if (next_frame_ >= total_frames_)
        return StepResult::Complete;
    if (!index_open_)
    {
        if (err)
            *err = "proxy builder has no index";
        return StepResult::Error;
    }

    Nv12Surface src {};
    bool have_src = false;
    try
    {
        src = decoder_.decode_presentation_frame(next_frame_);
        have_src = true;
    }
    catch (const std::exception&)
    {
        try
        {
            decoder_.close();
            decoder_.open(index_);
            src = decoder_.decode_presentation_frame(next_frame_);
            have_src = true;
        }
        catch (const std::exception& ex)
        {
            if (err)
                *err = ex.what();
        }
    }

    if (have_src)
    {
        const int surface_h = src.luma_surface_rows > 0 ? src.luma_surface_rows : src.height;
        if (!cuda_scale_nv12_box(
                src.device_ptr,
                src.pitch,
                src.width,
                src.height,
                surface_h,
                dst_nv12_,
                dst_pitch_,
                proxy_w_,
                proxy_h_,
                err))
        {
            cuda_free(src.device_ptr);
            return StepResult::Error;
        }
        cuda_free(src.device_ptr);

        if (!cuda_copy_nv12_to_host(dst_nv12_, dst_pitch_, proxy_w_, proxy_h_, &host_frame_, err))
            return StepResult::Error;
    }
    else
        host_frame_.assign(static_cast<std::size_t>(frame_bytes_), 0);

    if (host_frame_.size() != frame_bytes_)
    {
        if (err)
            *err = "host proxy frame size mismatch";
        return StepResult::Error;
    }

    const ssize_t wn = ::pwrite(fd_, host_frame_.data(), host_frame_.size(), static_cast<off_t>(write_offset_));
    if (wn < 0 || static_cast<std::uint64_t>(wn) != frame_bytes_)
    {
        if (err)
            *err = std::string("pwrite frame: ") + std::strerror(errno);
        return StepResult::Error;
    }
    index_entries_.push_back(write_offset_);
    write_offset_ += frame_bytes_;
    if (d2h_bytes_added)
        *d2h_bytes_added += frame_bytes_;
    ++next_frame_;

    if (next_frame_ < total_frames_)
        return StepResult::Progress;

    for (const auto entry : index_entries_)
    {
        const ssize_t iw = ::pwrite(fd_, &entry, sizeof(entry), static_cast<off_t>(write_offset_));
        if (iw != static_cast<ssize_t>(sizeof(entry)))
        {
            if (err)
                *err = std::string("pwrite index: ") + std::strerror(errno);
            return StepResult::Error;
        }
        write_offset_ += sizeof(entry);
    }

    if (::fsync(fd_) != 0)
    {
        if (err)
            *err = std::string("fsync: ") + std::strerror(errno);
        return StepResult::Error;
    }
    ::close(fd_);
    fd_ = -1;

    if (::rename(temp_path_.c_str(), final_path_.c_str()) != 0)
    {
        if (err)
            *err = std::string("rename proxy: ") + std::strerror(errno);
        ::unlink(temp_path_.c_str());
        return StepResult::Error;
    }
    temp_path_.clear();
    cuda_free(dst_nv12_);
    dst_nv12_ = 0;
    complete_ = true;
    return StepResult::Complete;
}

bool build_proxy_cache(
    const std::string& clip_path,
    int proxy_height,
    int cuda_device,
    const std::string& fatbin_path,
    ProxyBuildResult* out,
    std::string* err)
{
    if (proxy_height < 2)
        proxy_height = 270;

    std::string id_err;
    const ProxySourceIdentity id = proxy_source_identity(clip_path, &id_err);
    if (!id_err.empty())
    {
        if (err)
            *err = id_err;
        return false;
    }

    const std::string final_path = proxy_cache_file_path(id);
    if (out)
        out->cache_path = final_path;

    Mp4Index index = Mp4Index::open(clip_path);
    const auto& info = index.info();

    ProxyHeader existing {};
    if (proxy_read_header_file(final_path, &existing, nullptr))
    {
        const auto expected = proxy_file_size_bytes(existing);
        if (proxy_header_matches_source(existing, id, info) && file_size_ok(final_path, expected, nullptr))
        {
            if (out)
            {
                out->rebuilt = false;
                out->bytes_written = expected;
            }
            return true;
        }
    }

    const auto t0 = std::chrono::steady_clock::now();

    if (!cuda_init(cuda_device, fatbin_path, err))
        return false;

    std::filesystem::create_directories(std::filesystem::path(final_path).parent_path());

    const std::string temp_path = proxy_cache_temp_path(final_path);
    ::unlink(temp_path.c_str());

    int fd = ::open(temp_path.c_str(), O_RDWR | O_CREAT | O_TRUNC, 0644);
    if (fd < 0)
    {
        if (err)
            *err = std::string("open temp proxy: ") + std::strerror(errno);
        return false;
    }

    int proxy_w{}, proxy_h{};
    proxy_even_proxy_dims(info.width, info.height, proxy_height, &proxy_w, &proxy_h);
    const std::uint64_t frame_bytes = proxy_nv12_frame_bytes(static_cast<std::uint32_t>(proxy_w), static_cast<std::uint32_t>(proxy_h));

    ProxyHeader hdr{};
    hdr.path_hash = id.path_hash;
    hdr.source_size_bytes = id.size_bytes;
    hdr.source_mtime_ns = id.mtime_ns;
    hdr.source_width = static_cast<std::uint32_t>(info.width);
    hdr.source_height = static_cast<std::uint32_t>(info.height);
    hdr.proxy_width = static_cast<std::uint32_t>(proxy_w);
    hdr.proxy_height = static_cast<std::uint32_t>(proxy_h);
    hdr.frame_count = static_cast<std::uint32_t>(info.frames);
    hdr.frame_bytes = frame_bytes;
    hdr.index_offset = sizeof(ProxyHeader) + static_cast<std::uint64_t>(info.frames) * frame_bytes;

    if (!proxy_write_header(fd, hdr, err))
    {
        ::close(fd);
        ::unlink(temp_path.c_str());
        return false;
    }

    NvdecDecoder decoder;

    int dst_pitch{};
    const std::uint64_t dst_nv12 = cuda_alloc_nv12(proxy_w, proxy_h, &dst_pitch, err);
    if (dst_nv12 == 0)
    {
        ::close(fd);
        ::unlink(temp_path.c_str());
        return false;
    }

    std::vector<std::uint64_t> index_entries;
    index_entries.reserve(static_cast<std::size_t>(info.frames));
    std::vector<std::uint8_t> host_frame;
    std::uint64_t offset = sizeof(ProxyHeader);

    for (int f = 0; f < info.frames; ++f)
    {
        // Fresh decoder per frame: sequential continuation fails on long-GOP B-frame
        // fixtures (e.g. h264_1080_g30_b2) around the first reorder window.
        decoder.close();
        decoder.open(index);
        Nv12Surface src = decoder.decode_presentation_frame(f);

        const int surface_h = src.luma_surface_rows > 0 ? src.luma_surface_rows : src.height;
        if (!cuda_scale_nv12_box(
                src.device_ptr,
                src.pitch,
                src.width,
                src.height,
                surface_h,
                dst_nv12,
                dst_pitch,
                proxy_w,
                proxy_h,
                err))
        {
            cuda_free(src.device_ptr);
            cuda_free(dst_nv12);
            ::close(fd);
            ::unlink(temp_path.c_str());
            return false;
        }
        cuda_free(src.device_ptr);

        if (!cuda_copy_nv12_to_host(dst_nv12, dst_pitch, proxy_w, proxy_h, &host_frame, err))
        {
            cuda_free(dst_nv12);
            ::close(fd);
            ::unlink(temp_path.c_str());
            return false;
        }

        if (host_frame.size() != frame_bytes)
        {
            if (err)
                *err = "host proxy frame size mismatch";
            cuda_free(dst_nv12);
            ::close(fd);
            ::unlink(temp_path.c_str());
            return false;
        }

        const ssize_t wn = ::pwrite(fd, host_frame.data(), host_frame.size(), static_cast<off_t>(offset));
        if (wn < 0 || static_cast<std::uint64_t>(wn) != frame_bytes)
        {
            if (err)
                *err = std::string("pwrite frame: ") + std::strerror(errno);
            cuda_free(dst_nv12);
            ::close(fd);
            ::unlink(temp_path.c_str());
            return false;
        }
        index_entries.push_back(offset);
        offset += frame_bytes;
    }

    cuda_free(dst_nv12);
    decoder.close();

    for (const auto entry : index_entries)
    {
        const ssize_t wn = ::pwrite(fd, &entry, sizeof(entry), static_cast<off_t>(offset));
        if (wn != static_cast<ssize_t>(sizeof(entry)))
        {
            if (err)
                *err = std::string("pwrite index: ") + std::strerror(errno);
            ::close(fd);
            ::unlink(temp_path.c_str());
            return false;
        }
        offset += sizeof(entry);
    }

    if (::fsync(fd) != 0)
    {
        if (err)
            *err = std::string("fsync: ") + std::strerror(errno);
        ::close(fd);
        ::unlink(temp_path.c_str());
        return false;
    }
    ::close(fd);

    if (::rename(temp_path.c_str(), final_path.c_str()) != 0)
    {
        if (err)
            *err = std::string("rename proxy: ") + std::strerror(errno);
        ::unlink(temp_path.c_str());
        return false;
    }

    const auto t1 = std::chrono::steady_clock::now();
    const double secs = std::chrono::duration<double>(t1 - t0).count();
    if (out)
    {
        out->rebuilt = true;
        out->bytes_written = proxy_file_size_bytes(hdr);
        out->build_seconds = secs;
    }
    return true;
}

} // namespace v1d::scrub
