// SPDX-License-Identifier: MIT
#pragma once

#include <cstdint>
#include <string>

namespace v1d::scrub
{

enum class ColorMatrix : int
{
    BT601 = 0,
    BT709 = 1,
    BT2020 = 2,
};

enum class ColorRange : int
{
    Limited = 0,
    Full = 1,
};

bool convert_nv12_to_rgba8(
    std::uint64_t nv12_device,
    int src_pitch,
    int src_w,
    int src_h,
    int surface_h,
    int bit_depth,
    std::uint64_t rgba_device,
    int dst_stride,
    int out_w,
    int out_h,
    ColorMatrix matrix,
    ColorRange range,
    std::string* error);

} // namespace v1d::scrub
