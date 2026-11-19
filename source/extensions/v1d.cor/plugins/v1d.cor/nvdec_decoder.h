// SPDX-License-Identifier: MIT
#pragma once

#include "mp4_index.h"

#include <ffnvcodec/dynlink_cuda.h>
#include <ffnvcodec/dynlink_cuviddec.h>

#include <cstdint>
#include <unordered_map>
#include <vector>

namespace v1d::scrub
{

struct Nv12Surface
{
    std::uint64_t device_ptr{};
    int width{};
    int height{};
    int pitch{};
    int luma_surface_rows{};
    int coded_height{};
    int presentation_index{ -1 };
};

class NvdecDecoder
{
public:
    NvdecDecoder() = default;
    ~NvdecDecoder();

    NvdecDecoder(const NvdecDecoder&) = delete;
    NvdecDecoder& operator=(const NvdecDecoder&) = delete;

    void open(const Mp4Index& index);
    void close();

    Nv12Surface decode_presentation_frame(int presentation_index);

    int handle_sequence(void* fmt);
    int handle_decode(void* pic);
    int handle_display(void* info);

private:
    const Mp4Index* index_{ nullptr };
    void* decoder_{ nullptr };
    void* parser_{ nullptr };
    cudaVideoCodec codec_{ cudaVideoCodec_H264 };
    int coded_width_{};
    int coded_height_{};
    int display_width_{};
    int display_height_{};
    int target_presentation_{ -1 };
    int display_base_{ 0 };
    int display_serial_{ 0 };
    bool got_target_{ false };
    bool cont_open_{ false };
    int cont_sync_{ -1 };
    int cont_next_di_{ 0 };
    int cont_last_target_{ -1 };
    Nv12Surface result_{};
    std::vector<std::uint8_t> feed_scratch_;

    void destroy_pipeline();
    bool create_parser();
    void feed_packet(const std::uint8_t* data, std::size_t size, std::int64_t pts, bool discontinuity);
    void feed_eos();
};

} // namespace v1d::scrub
