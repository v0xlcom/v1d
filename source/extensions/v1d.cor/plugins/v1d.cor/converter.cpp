// SPDX-License-Identifier: MIT
#include "converter.h"

#include "cuda_context.h"

namespace v1d::scrub
{

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
    std::string* error)
{
    return cuda_convert_nv12_to_rgba8(
        nv12_device,
        src_pitch,
        src_w,
        src_h,
        surface_h,
        bit_depth,
        rgba_device,
        dst_stride,
        out_w,
        out_h,
        static_cast<int>(matrix),
        static_cast<int>(range),
        error);
}

} // namespace v1d::scrub
