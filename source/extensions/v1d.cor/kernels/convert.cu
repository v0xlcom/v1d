// SPDX-License-Identifier: MIT

#include <cstdint>

namespace
{

__device__ inline float clampf(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

__device__ inline float sample_plane_8(const uint8_t* plane, int pitch, int w, int h, float fx, float fy)
{
    fx = clampf(fx, 0.f, static_cast<float>(w - 1));
    fy = clampf(fy, 0.f, static_cast<float>(h - 1));
    const int x0 = static_cast<int>(fx);
    const int y0 = static_cast<int>(fy);
    const int x1 = x0 < w - 1 ? x0 + 1 : x0;
    const int y1 = y0 < h - 1 ? y0 + 1 : y0;
    const float tx = fx - static_cast<float>(x0);
    const float ty = fy - static_cast<float>(y0);
    const float v00 = plane[y0 * pitch + x0];
    const float v10 = plane[y0 * pitch + x1];
    const float v01 = plane[y1 * pitch + x0];
    const float v11 = plane[y1 * pitch + x1];
    const float v0 = v00 + (v10 - v00) * tx;
    const float v1 = v01 + (v11 - v01) * tx;
    return v0 + (v1 - v0) * ty;
}

__device__ inline float sample_nv12_uv_8(const uint8_t* uv_plane, int pitch, int uv_w, int uv_h, float ux, float uy, int ch)
{
    ux = clampf(ux, 0.f, static_cast<float>(uv_w - 1));
    uy = clampf(uy, 0.f, static_cast<float>(uv_h - 1));
    const int x0 = static_cast<int>(ux);
    const int y0 = static_cast<int>(uy);
    const int x1 = x0 < uv_w - 1 ? x0 + 1 : x0;
    const int y1 = y0 < uv_h - 1 ? y0 + 1 : y0;
    const float tx = ux - static_cast<float>(x0);
    const float ty = uy - static_cast<float>(y0);
    const auto at = [&](int x, int y) { return static_cast<float>(uv_plane[y * pitch + x * 2 + ch]); };
    const float v00 = at(x0, y0);
    const float v10 = at(x1, y0);
    const float v01 = at(x0, y1);
    const float v11 = at(x1, y1);
    const float v0 = v00 + (v10 - v00) * tx;
    const float v1 = v01 + (v11 - v01) * tx;
    return v0 + (v1 - v0) * ty;
}

__device__ inline float sample_plane_10(const uint16_t* plane, int pitch_elems, int w, int h, float fx, float fy)
{
    fx = clampf(fx, 0.f, static_cast<float>(w - 1));
    fy = clampf(fy, 0.f, static_cast<float>(h - 1));
    const int x0 = static_cast<int>(fx);
    const int y0 = static_cast<int>(fy);
    const int x1 = x0 < w - 1 ? x0 + 1 : x0;
    const int y1 = y0 < h - 1 ? y0 + 1 : y0;
    const float tx = fx - static_cast<float>(x0);
    const float ty = fy - static_cast<float>(y0);
    const auto at = [&](int x, int y) { return static_cast<float>(plane[y * pitch_elems + x] >> 6); };
    const float v00 = at(x0, y0);
    const float v10 = at(x1, y0);
    const float v01 = at(x0, y1);
    const float v11 = at(x1, y1);
    const float v0 = v00 + (v10 - v00) * tx;
    const float v1 = v01 + (v11 - v01) * tx;
    return v0 + (v1 - v0) * ty;
}

__device__ inline void yuv_to_rgb(float y, float u, float v, int matrix, int range, float& r, float& g, float& b)
{
    float yn, cb, cr;
    if (range == 0)
    {
        yn = (y - 16.f) * (1.f / 219.f);
        cb = (u - 128.f) * (1.f / 224.f);
        cr = (v - 128.f) * (1.f / 224.f);
    }
    else
    {
        yn = y * (1.f / 255.f);
        cb = (u - 128.f) * (1.f / 255.f);
        cr = (v - 128.f) * (1.f / 255.f);
    }

    float rf, gf, bf;
    if (matrix == 0)
    {
        rf = yn + 1.402f * cr;
        gf = yn - 0.344136f * cb - 0.714136f * cr;
        bf = yn + 1.772f * cb;
    }
    else if (matrix == 2)
    {
        rf = yn + 1.4746f * cr;
        gf = yn - 0.16455f * cb - 0.57135f * cr;
        bf = yn + 1.8814f * cb;
    }
    else
    {
        rf = yn + 1.5748f * cr;
        gf = yn - 0.187324f * cb - 0.468124f * cr;
        bf = yn + 1.8556f * cb;
    }
    r = rf * 255.f;
    g = gf * 255.f;
    b = bf * 255.f;
}

__device__ inline void sample_yuv(
    const uint8_t* nv12,
    int src_pitch,
    int src_w,
    int src_h,
    int surface_h,
    int bit_depth,
    float src_x,
    float src_y,
    float& y,
    float& u,
    float& v)
{
    if (bit_depth == 10)
    {
        const uint16_t* y_plane = reinterpret_cast<const uint16_t*>(nv12);
        const int y_pitch = src_pitch / 2;
        y = sample_plane_10(y_plane, y_pitch, src_w, src_h, src_x, src_y);
        const uint16_t* uv_plane = reinterpret_cast<const uint16_t*>(nv12 + static_cast<std::size_t>(src_pitch) * surface_h);
        const int uv_w = src_w / 2;
        const int uv_h = src_h / 2;
        const int uv_pitch = src_pitch / 2;
        const float ux = src_x * 0.5f;
        const float uy = src_y * 0.5f;
        u = sample_plane_10(uv_plane, uv_pitch, uv_w, uv_h, ux, uy);
        v = sample_plane_10(uv_plane + 1, uv_pitch, uv_w, uv_h, ux, uy);
    }
    else
    {
        const uint8_t* y_plane = nv12;
        y = sample_plane_8(y_plane, src_pitch, src_w, src_h, src_x, src_y);
        const uint8_t* uv_plane = nv12 + static_cast<std::size_t>(src_pitch) * surface_h;
        const int uv_w = src_w / 2;
        const int uv_h = src_h / 2;
        const float ux = src_x * 0.5f;
        const float uy = src_y * 0.5f;
        u = sample_nv12_uv_8(uv_plane, src_pitch, uv_w, uv_h, ux, uy, 0);
        v = sample_nv12_uv_8(uv_plane, src_pitch, uv_w, uv_h, ux, uy, 1);
    }
}

__device__ inline void box_yuv(
    const uint8_t* nv12,
    int src_pitch,
    int src_w,
    int src_h,
    int surface_h,
    int bit_depth,
    float x0,
    float y0,
    float x1,
    float y1,
    float& y,
    float& u,
    float& v)
{
    const int ix0 = static_cast<int>(floorf(x0));
    const int iy0 = static_cast<int>(floorf(y0));
    const int ix1 = static_cast<int>(ceilf(x1));
    const int iy1 = static_cast<int>(ceilf(y1));
    float sy = 0.f, su = 0.f, sv = 0.f;
    int n = 0;
    for (int sy_i = iy0; sy_i < iy1; ++sy_i)
    {
        for (int sx_i = ix0; sx_i < ix1; ++sx_i)
        {
            float ty, tu, tv;
            sample_yuv(nv12, src_pitch, src_w, src_h, surface_h, bit_depth, static_cast<float>(sx_i), static_cast<float>(sy_i), ty, tu, tv);
            sy += ty;
            su += tu;
            sv += tv;
            ++n;
        }
    }
    if (n > 0)
    {
        const float inv = 1.f / static_cast<float>(n);
        y = sy * inv;
        u = su * inv;
        v = sv * inv;
    }
    else
    {
        sample_yuv(nv12, src_pitch, src_w, src_h, surface_h, bit_depth, x0, y0, y, u, v);
    }
}

} // namespace

extern "C" __global__ void v1d_scale_nv12_box(
    const uint8_t* src,
    int src_pitch,
    int src_w,
    int src_h,
    int src_surface_h,
    uint8_t* dst,
    int dst_pitch,
    int dst_w,
    int dst_h)
{
    const int x = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    const int y = static_cast<int>(blockIdx.y * blockDim.y + threadIdx.y);
    if (x >= dst_w || y >= dst_h)
        return;

    const float scale_x = static_cast<float>(src_w) / static_cast<float>(dst_w);
    const float scale_y = static_cast<float>(src_h) / static_cast<float>(dst_h);
    const float x0 = static_cast<float>(x) * scale_x;
    const float y0 = static_cast<float>(y) * scale_y;
    const float x1 = static_cast<float>(x + 1) * scale_x;
    const float y1 = static_cast<float>(y + 1) * scale_y;

    float Y, U, V;
    box_yuv(src, src_pitch, src_w, src_h, src_surface_h, 8, x0, y0, x1, y1, Y, U, V);

    uint8_t* y_plane = dst;
    y_plane[y * dst_pitch + x] = static_cast<uint8_t>(clampf(Y, 0.f, 255.f));

    if ((x & 1) == 0 && (y & 1) == 0)
    {
        const int ux = x / 2;
        const int uy = y / 2;
        uint8_t* uv = dst + static_cast<std::size_t>(dst_pitch) * static_cast<std::size_t>(dst_h);
        uint8_t* px = uv + uy * dst_pitch + ux * 2;
        px[0] = static_cast<uint8_t>(clampf(U, 0.f, 255.f));
        px[1] = static_cast<uint8_t>(clampf(V, 0.f, 255.f));
    }
}

extern "C" __global__ void v1d_fill_rgba_frame(uint8_t* rgba, int width, int height, int stride, unsigned frame)
{
    const int x = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    const int y = static_cast<int>(blockIdx.y * blockDim.y + threadIdx.y);
    if (x >= width || y >= height)
        return;
    uint8_t* px = rgba + y * stride + x * 4;
    const uint8_t v = static_cast<uint8_t>((frame + x + y) & 0xff);
    px[0] = v;
    px[1] = static_cast<uint8_t>((v + 64) & 0xff);
    px[2] = static_cast<uint8_t>((v + 128) & 0xff);
    px[3] = 255;
}

extern "C" __global__ void v1d_convert_nv12_to_rgba8(
    uint8_t* nv12,
    int src_pitch,
    int src_w,
    int src_h,
    int surface_h,
    uint8_t* rgba,
    int dst_stride,
    int out_w,
    int out_h,
    int matrix,
    int range,
    int bit_depth)
{
    const int x = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    const int y = static_cast<int>(blockIdx.y * blockDim.y + threadIdx.y);
    if (x >= out_w || y >= out_h)
        return;

    const float scale_x = static_cast<float>(src_w) / static_cast<float>(out_w);
    const float scale_y = static_cast<float>(src_h) / static_cast<float>(out_h);
    const float cx = (static_cast<float>(x) + 0.5f) * scale_x - 0.5f;
    const float cy = (static_cast<float>(y) + 0.5f) * scale_y - 0.5f;

    float Y, U, V;
    if (scale_x > 2.f || scale_y > 2.f)
    {
        const float x0 = static_cast<float>(x) * scale_x;
        const float y0 = static_cast<float>(y) * scale_y;
        const float x1 = static_cast<float>(x + 1) * scale_x;
        const float y1 = static_cast<float>(y + 1) * scale_y;
        box_yuv(nv12, src_pitch, src_w, src_h, surface_h, bit_depth, x0, y0, x1, y1, Y, U, V);
    }
    else
    {
        sample_yuv(nv12, src_pitch, src_w, src_h, surface_h, bit_depth, cx, cy, Y, U, V);
    }

    float r, g, b;
    yuv_to_rgb(Y, U, V, matrix, range, r, g, b);
    uint8_t* px = rgba + y * dst_stride + x * 4;
    px[0] = static_cast<uint8_t>(clampf(r, 0.f, 255.f));
    px[1] = static_cast<uint8_t>(clampf(g, 0.f, 255.f));
    px[2] = static_cast<uint8_t>(clampf(b, 0.f, 255.f));
    px[3] = 255;
}
