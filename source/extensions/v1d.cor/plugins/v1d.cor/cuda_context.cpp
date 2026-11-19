// SPDX-License-Identifier: MIT
#include "cuda_context.h"

#include <cstdlib>
#include <dlfcn.h>
#include <fstream>
#include <vector>

#include <ffnvcodec/dynlink_cuda.h>
#include <ffnvcodec/dynlink_cuviddec.h>
#include <ffnvcodec/dynlink_loader.h>

namespace v1d::scrub
{

namespace
{

CudaFunctions* g_cu{};
CuvidFunctions* g_cv{};
CUcontext g_ctx{};
int g_device_index{};
CUmodule g_mod{};
CUfunction g_fill{};
CUfunction g_convert{};
CUfunction g_scale_nv12{};
CUstream g_stream{};
bool g_ready{};

bool load_fatbin(const std::string& path, std::vector<char>& out, std::string* error)
{
    std::ifstream in(path, std::ios::binary);
    if (!in)
    {
        if (error)
            *error = "cannot open fatbin: " + path;
        return false;
    }
    in.seekg(0, std::ios::end);
    const auto sz = in.tellg();
    in.seekg(0, std::ios::beg);
    out.resize(static_cast<size_t>(sz));
    in.read(out.data(), sz);
    return true;
}

} // namespace

bool cuda_driver_preload(std::string* error)
{
    const char* path = std::getenv("V1D_CUDA_LIB");
    if (!path || !path[0])
        return true;
    if (!FFNV_LOAD_FUNC(path))
    {
        if (error)
        {
            const char* why = dlerror();
            *error = std::string("cannot load CUDA driver library: ") + path +
                     (why ? std::string(" (") + why + ")" : "");
        }
        return false;
    }
    return true;
}

bool cuda_init(int device_index, const std::string& fatbin_path, std::string* error)
{
    if (g_ready)
        return true;
    if (!cuda_driver_preload(error))
        return false;
    if (cuda_load_functions(&g_cu, nullptr) != 0)
    {
        if (error)
            *error = "cuda_load_functions failed";
        return false;
    }
    if (cuvid_load_functions(&g_cv, nullptr) != 0)
    {
        if (error)
            *error = "cuvid_load_functions failed";
        cuda_free_functions(&g_cu);
        g_cu = nullptr;
        return false;
    }
    g_device_index = device_index;
    if (g_cu->cuInit(0) != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuInit failed";
        return false;
    }
    CUdevice dev{};
    if (g_cu->cuDeviceGet(&dev, device_index) != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuDeviceGet failed";
        return false;
    }
    if (g_cu->cuDevicePrimaryCtxRetain(&g_ctx, dev) != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuDevicePrimaryCtxRetain failed";
        return false;
    }
    g_cu->cuCtxPushCurrent(g_ctx);
    std::vector<char> fatbin;
    if (!load_fatbin(fatbin_path, fatbin, error))
    {
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    if (g_cu->cuModuleLoadData(&g_mod, fatbin.data()) != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuModuleLoadData failed";
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    if (g_cu->cuModuleGetFunction(&g_fill, g_mod, "v1d_fill_rgba_frame") != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuModuleGetFunction v1d_fill_rgba_frame failed";
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    if (g_cu->cuModuleGetFunction(&g_convert, g_mod, "v1d_convert_nv12_to_rgba8") != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuModuleGetFunction v1d_convert_nv12_to_rgba8 failed";
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    if (g_cu->cuModuleGetFunction(&g_scale_nv12, g_mod, "v1d_scale_nv12_box") != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuModuleGetFunction v1d_scale_nv12_box failed";
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    if (g_cu->cuStreamCreate(&g_stream, 0) != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuStreamCreate failed";
        g_cu->cuCtxPopCurrent(nullptr);
        return false;
    }
    g_cu->cuCtxPopCurrent(nullptr);
    g_ready = true;
    return true;
}

void cuda_shutdown()
{
    if (!g_ready || !g_cu)
        return;
    g_cu->cuCtxPushCurrent(g_ctx);
    if (g_stream)
        g_cu->cuStreamDestroy(g_stream);
    g_stream = nullptr;
    if (g_mod)
        g_cu->cuModuleUnload(g_mod);
    g_mod = nullptr;
    g_fill = nullptr;
    g_convert = nullptr;
    g_scale_nv12 = nullptr;
    g_cu->cuCtxPopCurrent(nullptr);
    CUdevice dev{};
    g_cu->cuDeviceGet(&dev, g_device_index);
    g_cu->cuDevicePrimaryCtxRelease(dev);
    g_ctx = nullptr;
    if (g_cv)
        cuvid_free_functions(&g_cv);
    g_cv = nullptr;
    cuda_free_functions(&g_cu);
    g_cu = nullptr;
    g_ready = false;
}

bool cuda_ready()
{
    return g_ready;
}

CudaFunctions* cuda_driver()
{
    return g_cu;
}

CuvidFunctions* cuvid_driver()
{
    return g_cv;
}

CUcontext cuda_context_handle()
{
    return g_ctx;
}

CUstream cuda_stream_handle()
{
    return g_stream;
}

bool cuda_mem_info(std::size_t* free_bytes, std::size_t* total_bytes, std::string* error)
{
    if (!g_ready)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    using tcuMemGetInfo = CUresult(CUDAAPI*)(std::size_t*, std::size_t*);
    auto mem_get_info = reinterpret_cast<tcuMemGetInfo>(FFNV_SYM_FUNC(g_cu->lib, "cuMemGetInfo"));
    if (!mem_get_info)
    {
        if (error)
            *error = "cuMemGetInfo not available";
        return false;
    }
    g_cu->cuCtxPushCurrent(g_ctx);
    size_t free_b{}, total_b{};
    const CUresult r = mem_get_info(&free_b, &total_b);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuMemGetInfo failed";
        return false;
    }
    if (free_bytes)
        *free_bytes = free_b;
    if (total_bytes)
        *total_bytes = total_b;
    return true;
}

std::uint64_t cuda_alloc_rgba(int width, int height, int* stride_out, std::string* error)
{
    if (!g_ready)
    {
        if (error)
            *error = "cuda not initialized";
        return 0;
    }
    const int stride = width * 4;
    const size_t bytes = static_cast<size_t>(stride) * static_cast<size_t>(height);
    CUdeviceptr ptr{};
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemAlloc(&ptr, bytes);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuMemAlloc failed";
        return 0;
    }
    if (stride_out)
        *stride_out = stride;
    return static_cast<std::uint64_t>(ptr);
}

void cuda_free(std::uint64_t ptr)
{
    if (!g_ready || ptr == 0)
        return;
    g_cu->cuCtxPushCurrent(g_ctx);
    g_cu->cuMemFree(static_cast<CUdeviceptr>(ptr));
    g_cu->cuCtxPopCurrent(nullptr);
}

bool cuda_fill_rgba_frame(std::uint64_t ptr, int width, int height, int stride, unsigned frame, std::string* error)
{
    if (!g_ready || !g_fill)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    CUdeviceptr devptr = static_cast<CUdeviceptr>(ptr);
    void* args[] = { &devptr, &width, &height, &stride, &frame };
    const unsigned bx = 16, by = 16;
    const unsigned gx = (static_cast<unsigned>(width) + bx - 1) / bx;
    const unsigned gy = (static_cast<unsigned>(height) + by - 1) / by;
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult lr = g_cu->cuLaunchKernel(g_fill, gx, gy, 1, bx, by, 1, 0, g_stream, args, nullptr);
    const CUresult sr = g_cu->cuStreamSynchronize(g_stream);
    g_cu->cuCtxPopCurrent(nullptr);
    if (lr != CUDA_SUCCESS || sr != CUDA_SUCCESS)
    {
        if (error)
            *error = "fill kernel launch failed";
        return false;
    }
    return true;
}

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
    std::string* error)
{
    if (!g_ready || !g_convert)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    CUdeviceptr nv12 = static_cast<CUdeviceptr>(nv12_device);
    CUdeviceptr rgba = static_cast<CUdeviceptr>(rgba_device);
    void* args[] = {
        &nv12,
        &src_pitch,
        &src_w,
        &src_h,
        &surface_h,
        &rgba,
        &dst_stride,
        &out_w,
        &out_h,
        &matrix,
        &range,
        &bit_depth,
    };
    const unsigned bx = 16, by = 16;
    const unsigned gx = (static_cast<unsigned>(out_w) + bx - 1) / bx;
    const unsigned gy = (static_cast<unsigned>(out_h) + by - 1) / by;
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult lr = g_cu->cuLaunchKernel(g_convert, gx, gy, 1, bx, by, 1, 0, g_stream, args, nullptr);
    const CUresult sr = g_cu->cuStreamSynchronize(g_stream);
    g_cu->cuCtxPopCurrent(nullptr);
    if (lr != CUDA_SUCCESS || sr != CUDA_SUCCESS)
    {
        if (error)
            *error = "convert kernel launch failed";
        return false;
    }
    return true;
}

std::uint64_t cuda_alloc_nv12(int width, int height, int* pitch_out, std::string* error)
{
    if (!g_ready)
    {
        if (error)
            *error = "cuda not initialized";
        return 0;
    }
    const int pitch = width;
    const size_t bytes = static_cast<size_t>(pitch) * static_cast<size_t>(height) * 3u / 2u;
    CUdeviceptr ptr{};
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemAlloc(&ptr, bytes);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuMemAlloc nv12 failed";
        return 0;
    }
    if (pitch_out)
        *pitch_out = pitch;
    return static_cast<std::uint64_t>(ptr);
}

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
    std::string* error)
{
    if (!g_ready || !g_scale_nv12)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    CUdeviceptr src = static_cast<CUdeviceptr>(src_nv12);
    CUdeviceptr dst = static_cast<CUdeviceptr>(dst_nv12);
    void* args[] = {
        &src,
        &src_pitch,
        &src_w,
        &src_h,
        &src_surface_h,
        &dst,
        &dst_pitch,
        &dst_w,
        &dst_h,
    };
    const unsigned bx = 16, by = 16;
    const unsigned gx = (static_cast<unsigned>(dst_w) + bx - 1) / bx;
    const unsigned gy = (static_cast<unsigned>(dst_h) + by - 1) / by;
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult lr = g_cu->cuLaunchKernel(g_scale_nv12, gx, gy, 1, bx, by, 1, 0, g_stream, args, nullptr);
    const CUresult sr = g_cu->cuStreamSynchronize(g_stream);
    g_cu->cuCtxPopCurrent(nullptr);
    if (lr != CUDA_SUCCESS || sr != CUDA_SUCCESS)
    {
        if (error)
            *error = "scale nv12 kernel launch failed";
        return false;
    }
    return true;
}

bool cuda_copy_nv12_d2d(
    std::uint64_t src_nv12,
    int src_pitch,
    int width,
    int height,
    std::uint64_t dst_nv12,
    int dst_pitch,
    std::string* error)
{
    if (!g_ready)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    const size_t y_bytes = static_cast<size_t>(src_pitch) * static_cast<size_t>(height);
    CUDA_MEMCPY2D cp_y{};
    cp_y.srcMemoryType = CU_MEMORYTYPE_DEVICE;
    cp_y.srcDevice = static_cast<CUdeviceptr>(src_nv12);
    cp_y.srcPitch = static_cast<size_t>(src_pitch);
    cp_y.dstMemoryType = CU_MEMORYTYPE_DEVICE;
    cp_y.dstDevice = static_cast<CUdeviceptr>(dst_nv12);
    cp_y.dstPitch = static_cast<size_t>(dst_pitch);
    cp_y.WidthInBytes = static_cast<size_t>(width);
    cp_y.Height = static_cast<size_t>(height);

    CUDA_MEMCPY2D cp_uv = cp_y;
    cp_uv.srcDevice = static_cast<CUdeviceptr>(src_nv12) + y_bytes;
    cp_uv.dstDevice = static_cast<CUdeviceptr>(dst_nv12) + static_cast<size_t>(dst_pitch) * static_cast<size_t>(height);
    cp_uv.Height = static_cast<size_t>(height / 2);

    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r0 = g_cu->cuMemcpy2D(&cp_y);
    const CUresult r1 = g_cu->cuMemcpy2D(&cp_uv);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r0 != CUDA_SUCCESS || r1 != CUDA_SUCCESS)
    {
        if (error)
            *error = "nv12 D2D failed";
        return false;
    }
    return true;
}

bool cuda_copy_rgba_d2d(
    std::uint64_t src_rgba,
    int src_stride,
    std::uint64_t dst_rgba,
    int dst_stride,
    int width,
    int height,
    std::string* error)
{
    if (!g_ready || width <= 0 || height <= 0)
    {
        if (error)
            *error = "cuda_copy_rgba_d2d: bad args";
        return false;
    }
    CUDA_MEMCPY2D cp{};
    cp.srcMemoryType = CU_MEMORYTYPE_DEVICE;
    cp.srcDevice = static_cast<CUdeviceptr>(src_rgba);
    cp.srcPitch = static_cast<size_t>(src_stride);
    cp.dstMemoryType = CU_MEMORYTYPE_DEVICE;
    cp.dstDevice = static_cast<CUdeviceptr>(dst_rgba);
    cp.dstPitch = static_cast<size_t>(dst_stride);
    cp.WidthInBytes = static_cast<size_t>(width) * 4u;
    cp.Height = static_cast<size_t>(height);
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemcpy2D(&cp);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "rgba D2D failed";
        return false;
    }
    return true;
}

bool cuda_copy_rgba_from_host(
    const std::uint8_t* host_rgba,
    int host_bytes,
    std::uint64_t dst_rgba,
    int dst_stride,
    int width,
    int height,
    std::string* error)
{
    if (!g_ready || !host_rgba || width <= 0 || height <= 0 || dst_stride < width * 4)
    {
        if (error)
            *error = "cuda_copy_rgba_from_host: bad args";
        return false;
    }
    const size_t need = static_cast<size_t>(width) * 4u * static_cast<size_t>(height);
    if (static_cast<size_t>(host_bytes) < need)
    {
        if (error)
            *error = "host rgba too small";
        return false;
    }
    CUDA_MEMCPY2D cp{};
    cp.srcMemoryType = CU_MEMORYTYPE_HOST;
    cp.srcHost = host_rgba;
    cp.srcPitch = static_cast<size_t>(width) * 4u;
    cp.dstMemoryType = CU_MEMORYTYPE_DEVICE;
    cp.dstDevice = static_cast<CUdeviceptr>(dst_rgba);
    cp.dstPitch = static_cast<size_t>(dst_stride);
    cp.WidthInBytes = static_cast<size_t>(width) * 4u;
    cp.Height = static_cast<size_t>(height);
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemcpy2D(&cp);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "rgba HtoD failed";
        return false;
    }
    return true;
}

bool cuda_copy_nv12_from_host(
    const std::uint8_t* host_nv12,
    int host_bytes,
    int width,
    int height,
    std::uint64_t nv12_device,
    std::string* error)
{
    if (!g_ready || !host_nv12)
    {
        if (error)
            *error = "cuda_copy_nv12_from_host: bad args";
        return false;
    }
    const int pitch = width;
    const size_t need = static_cast<size_t>(pitch) * static_cast<size_t>(height) * 3u / 2u;
    if (static_cast<size_t>(host_bytes) < need)
    {
        if (error)
            *error = "host nv12 too small";
        return false;
    }
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemcpyHtoD(static_cast<CUdeviceptr>(nv12_device), host_nv12, need);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "nv12 HtoD failed";
        return false;
    }
    return true;
}

bool cuda_copy_nv12_to_host(
    std::uint64_t nv12_device,
    int pitch,
    int width,
    int height,
    std::vector<std::uint8_t>* out,
    std::string* error)
{
    if (!g_ready || !out)
    {
        if (error)
            *error = "cuda_copy_nv12_to_host: bad args";
        return false;
    }
    const size_t bytes = static_cast<size_t>(pitch) * static_cast<size_t>(height) * 3u / 2u;
    out->resize(bytes);
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemcpyDtoH(out->data(), static_cast<CUdeviceptr>(nv12_device), bytes);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "nv12 DtoH failed";
        return false;
    }
    return true;
}

bool cuda_peek_nv12(
    std::uint64_t nv12_device,
    int pitch,
    int luma_rows,
    int x,
    int y,
    std::uint8_t* y_out,
    std::uint8_t* u_out,
    std::uint8_t* v_out,
    std::string* error)
{
    if (!g_ready || !y_out || !u_out || !v_out)
    {
        if (error)
            *error = "cuda_peek_nv12: bad args";
        return false;
    }
    const CUdeviceptr base = static_cast<CUdeviceptr>(nv12_device);
    const CUdeviceptr y_ptr = base + static_cast<std::size_t>(y) * static_cast<std::size_t>(pitch) + static_cast<std::size_t>(x);
    const int ux = x / 2;
    const int uy = y / 2;
    const CUdeviceptr uv_ptr =
        base + static_cast<std::size_t>(luma_rows) * static_cast<std::size_t>(pitch) + static_cast<std::size_t>(uy) * static_cast<std::size_t>(pitch) +
        static_cast<std::size_t>(ux) * 2;
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r0 = g_cu->cuMemcpyDtoH(y_out, y_ptr, 1);
    std::uint8_t uv[2]{};
    const CUresult r1 = g_cu->cuMemcpyDtoH(uv, uv_ptr, 2);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r0 != CUDA_SUCCESS || r1 != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuda_peek_nv12 memcpy failed";
        return false;
    }
    *u_out = uv[0];
    *v_out = uv[1];
    return true;
}

bool cuda_read_rgba_device(
    std::uint64_t rgba_device, int width, int height, int stride, std::string* out_bytes, std::string* error)
{
    if (!g_ready)
    {
        if (error)
            *error = "cuda not initialized";
        return false;
    }
    if (!out_bytes)
    {
        if (error)
            *error = "out_bytes is null";
        return false;
    }
    const size_t bytes = static_cast<size_t>(stride) * static_cast<size_t>(height);
    out_bytes->resize(bytes);
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_cu->cuMemcpyDtoH(out_bytes->data(), static_cast<CUdeviceptr>(rgba_device), bytes);
    g_cu->cuCtxPopCurrent(nullptr);
    if (r != CUDA_SUCCESS)
    {
        if (error)
            *error = "cuMemcpyDtoH failed";
        return false;
    }
    return true;
}

} // namespace v1d::scrub
