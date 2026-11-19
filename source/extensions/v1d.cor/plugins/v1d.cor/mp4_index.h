// SPDX-License-Identifier: MIT
#pragma once

#include "mapped_file.h"

#include <cstdint>
#include <string>
#include <vector>

namespace v1d::scrub
{

enum class VideoCodec
{
    H264,
    HEVC,
};

struct Mp4Sample
{
    int sample_idx{};
    std::int64_t pts{};
    std::int64_t dts{};
    std::uint64_t offset{};
    std::uint32_t size{};
    bool is_sync{};
};

struct ClipInfo
{
    int frames{};
    int fps_num{ 30 };
    int fps_den{ 1 };
    int width{};
    int height{};
    VideoCodec codec{ VideoCodec::H264 };
    int bit_depth{ 8 };
    int gop_max{};
    int sync_count{};
    std::uint32_t timescale{ 1 };
};

class Mp4Index
{
public:
    Mp4Index() = default;
    Mp4Index(Mp4Index&&) noexcept = default;
    Mp4Index& operator=(Mp4Index&&) noexcept = default;
    Mp4Index(const Mp4Index&) = delete;
    Mp4Index& operator=(const Mp4Index&) = delete;

    static Mp4Index open(const std::string& path);

    const MappedFile& file() const
    {
        return file_;
    }
    const ClipInfo& info() const
    {
        return info_;
    }
    const std::vector<Mp4Sample>& samples() const
    {
        return samples_;
    }
    const Mp4Sample& decode_sample(int sample_idx) const;

    int sync_at_or_before(int presentation_index) const;
    int prev_sync(int presentation_index) const;
    /** Presentation index for a displayed picture PTS, or -1 if unknown. */
    int presentation_for_pts(std::int64_t pts) const;

    std::vector<std::uint8_t> annexb_for_presentation(int presentation_index, bool prepend_parameter_sets) const;
    std::vector<std::uint8_t> annexb_for_decode_sample(int sample_idx, bool prepend_parameter_sets) const;

private:
    MappedFile file_;
    ClipInfo info_;
    std::vector<Mp4Sample> samples_;
    std::vector<Mp4Sample> decode_samples_;
    std::vector<std::uint8_t> parameter_sets_annexb_;
    int nal_length_size_{ 4 };
};

} // namespace v1d::scrub
