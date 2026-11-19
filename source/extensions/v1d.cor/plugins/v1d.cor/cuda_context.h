// SPDX-License-Identifier: MIT
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include <ffnvcodec/dynlink_cuda.h>
#include <ffnvcodec/dynlink_cuviddec.h>
#include <ffnvcodec/dynlink_loader.h>

namespace v1d::scrub
{

bool cuda_init(int device_index, const std::string& fatbin_path, std::string* error);
void cuda_shutdown();
bool cuda_ready();
CudaFunctions* cuda_driver();
CuvidFunctions* cuvid_driver();
CUcontext cuda_context_handle();
CUstream cuda_stream_handle();
bool cuda_mem_info(std::size_t* free_bytes, std::size_t* total_bytes, std::string* error);
std::uint64_t cuda_alloc_rgba(int width, int height, int* stride_out, std::string* error);
void cuda_free(std::uint64_t ptr);
bool cuda_fill_rgba_frame(std::uint64_t ptr, int width, int height, int stride, unsigned frame, std::string* error);

bool cuda_convert_nv12_to_rgba8(
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
    int matrix,
    int range,
    std::string* error);

bool cuda_read_rgba_device(std::uint64_t rgba_device, int width, int height, int stride, std::string* out_bytes, std::string* error);

bool cuda_copy_rgba_d2d(
    std::uint64_t src_rgba,
    int src_stride,
    std::uint64_t dst_rgba,
    int dst_stride,
    int width,
    int height,
    std::string* error);

bool cuda_copy_rgba_from_host(
    const std::uint8_t* host_rgba,
    int host_bytes,
    std::uint64_t dst_rgba,
    int dst_stride,
    int width,
    int height,
    std::string* error);

std::uint64_t cuda_alloc_nv12(int width, int height, int* pitch_out, std::string* error);

bool cuda_scale_nv12_box(
    std::uint64_t src_nv12,
    int src_pitch,
    int src_w,
    int src_h,
    int src_surface_h,
    std::uint64_t dst_nv12,
    int dst_pitch,
    int dst_w,
    int dst_h,
    std::string* error);

bool cuda_copy_nv12_d2d(
    std::uint64_t src_nv12,
    int src_pitch,
    int width,
    int height,
    std::uint64_t dst_nv12,
    int dst_pitch,
    std::string* error);

bool cuda_copy_nv12_from_host(
    const std::uint8_t* host_nv12,
    int host_bytes,
    int width,
    int height,
    std::uint64_t nv12_device,
    std::string* error);

bool cuda_copy_nv12_to_host(
    std::uint64_t nv12_device,
    int pitch,
    int width,
    int height,
    std::vector<std::uint8_t>* out,
    std::string* error);

bool cuda_peek_nv12(
    std::uint64_t nv12_device,
    int pitch,
    int luma_rows,
    int x,
    int y,
    std::uint8_t* y_out,
    std::uint8_t* u_out,
    std::uint8_t* v_out,
    std::string* error);

} // namespace v1d::scrub
