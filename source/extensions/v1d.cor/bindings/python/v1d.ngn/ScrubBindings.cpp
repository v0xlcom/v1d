// SPDX-License-Identifier: MIT
#include <carb/BindingsPythonUtils.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <chrono>

#include "../../../plugins/v1d.cor/converter.h"
#include "../../../plugins/v1d.cor/cuda_context.h"
#include "../../../plugins/v1d.cor/engine.h"
#include "../../../plugins/v1d.cor/mp4_index.h"
#include "../../../plugins/v1d.cor/nvdec_decoder.h"
#include "../../../plugins/v1d.cor/proxy_builder.h"
#include "../../../plugins/v1d.cor/proxy_format.h"

CARB_BINDINGS("v1d.cor.python")

namespace py = pybind11;

PYBIND11_MODULE(_scrub, m)
{
    m.doc() = "v1d GPU scrub engine";
    m.attr("__version__") = "0.0.1";

    m.def(
        "cuda_init",
        [](int device, const std::string& fatbin_path) {
            std::string err;
            if (!v1d::scrub::cuda_init(device, fatbin_path, &err))
                throw std::runtime_error(err);
        },
        py::arg("device") = 0,
        py::arg("fatbin_path"));

    m.def("cuda_shutdown", []() { v1d::scrub::cuda_shutdown(); });

    m.def("cuda_mem_info", []() {
        std::size_t free_b{}, total_b{};
        std::string err;
        if (!v1d::scrub::cuda_mem_info(&free_b, &total_b, &err))
            throw std::runtime_error(err);
        return py::make_tuple(free_b, total_b);
    });

    m.def(
        "cuda_alloc_rgba",
        [](int width, int height) {
            int stride{};
            std::string err;
            const auto ptr = v1d::scrub::cuda_alloc_rgba(width, height, &stride, &err);
            if (ptr == 0)
                throw std::runtime_error(err);
            return py::make_tuple(ptr, stride);
        },
        py::arg("width"),
        py::arg("height"));

    m.def("cuda_free", [](std::uint64_t ptr) { v1d::scrub::cuda_free(ptr); }, py::arg("ptr"));

    m.def(
        "cuda_read_rgba",
        [](std::uint64_t ptr, int width, int height, int stride) {
            std::string pixels;
            std::string err;
            {
                py::gil_scoped_release release;
                if (!v1d::scrub::cuda_read_rgba_device(ptr, width, height, stride, &pixels, &err))
                    throw std::runtime_error(err);
            }
            return py::bytes(pixels);
        },
        py::arg("ptr"),
        py::arg("width"),
        py::arg("height"),
        py::arg("stride"));

    m.def(
        "cuda_write_rgba",
        [](std::uint64_t ptr, int width, int height, int stride, py::bytes rgba) {
            std::string err;
            const std::string buf(rgba);
            {
                py::gil_scoped_release release;
                if (!v1d::scrub::cuda_copy_rgba_from_host(
                        reinterpret_cast<const std::uint8_t*>(buf.data()),
                        static_cast<int>(buf.size()),
                        ptr,
                        stride,
                        width,
                        height,
                        &err))
                    throw std::runtime_error(err);
            }
        },
        py::arg("ptr"),
        py::arg("width"),
        py::arg("height"),
        py::arg("stride"),
        py::arg("rgba"));

    m.def(
        "cuda_fill_rgba_frame",
        [](std::uint64_t ptr, int width, int height, int stride, unsigned frame) {
            std::string err;
            if (!v1d::scrub::cuda_fill_rgba_frame(ptr, width, height, stride, frame, &err))
                throw std::runtime_error(err);
        },
        py::arg("ptr"),
        py::arg("width"),
        py::arg("height"),
        py::arg("stride"),
        py::arg("frame"));

    m.def(
        "probe_clip",
        [](const std::string& path) {
            const auto idx = v1d::scrub::Mp4Index::open(path);
            const auto& info = idx.info();
            py::dict d;
            d["frames"] = info.frames;
            d["fps_num"] = info.fps_num;
            d["fps_den"] = info.fps_den;
            d["width"] = info.width;
            d["height"] = info.height;
            d["codec"] = (info.codec == v1d::scrub::VideoCodec::H264) ? "h264" : "hevc";
            d["bit_depth"] = info.bit_depth;
            d["gop_max"] = info.gop_max;
            d["sync_count"] = info.sync_count;
            return d;
        },
        py::arg("path"));

    m.def(
        "annexb_decode_sample",
        [](const std::string& path, int sample_idx, bool prepend_ps) {
            const auto index = v1d::scrub::Mp4Index::open(path);
            const auto v = index.annexb_for_decode_sample(sample_idx, prepend_ps);
            return py::bytes(reinterpret_cast<const char*>(v.data()), static_cast<py::ssize_t>(v.size()));
        },
        py::arg("path"),
        py::arg("sample_idx"),
        py::arg("prepend_ps") = true);

    m.def(
        "nvdec_decode_frame",
        [](const std::string& path, int presentation_index, int cuda_device, const std::string& fatbin_path) {
            std::string err;
            if (!v1d::scrub::cuda_init(cuda_device, fatbin_path, &err))
                throw std::runtime_error(err);
            const auto index = v1d::scrub::Mp4Index::open(path);
            v1d::scrub::NvdecDecoder dec;
            dec.open(index);
            const auto surf = dec.decode_presentation_frame(presentation_index);
            dec.close();
            py::dict d;
            d["device_ptr"] = surf.device_ptr;
            d["width"] = surf.width;
            d["height"] = surf.height;
            d["pitch"] = surf.pitch;
            d["luma_rows"] = surf.luma_surface_rows > 0 ? surf.luma_surface_rows : surf.height;
            d["coded_height"] = surf.coded_height > 0 ? surf.coded_height : surf.height;
            d["presentation_index"] = surf.presentation_index;
            return d;
        },
        py::arg("path"),
        py::arg("presentation_index"),
        py::arg("cuda_device") = 0,
        py::arg("fatbin_path"));

    m.def(
        "nvdec_convert_frame_rgba",
        [](const std::string& path,
           int presentation_index,
           int out_w,
           int out_h,
           int cuda_device,
           const std::string& fatbin_path,
           const std::string& matrix,
           bool full_range) {
            std::string err;
            if (!v1d::scrub::cuda_init(cuda_device, fatbin_path, &err))
                throw std::runtime_error(err);
            const auto index = v1d::scrub::Mp4Index::open(path);
            v1d::scrub::NvdecDecoder dec;
            dec.open(index);
            const auto surf = dec.decode_presentation_frame(presentation_index);
            dec.close();
            const auto& info = index.info();
            v1d::scrub::ColorMatrix cm = v1d::scrub::ColorMatrix::BT709;
            if (matrix == "bt601")
                cm = v1d::scrub::ColorMatrix::BT601;
            else if (matrix == "bt2020")
                cm = v1d::scrub::ColorMatrix::BT2020;
            const auto range =
                full_range ? v1d::scrub::ColorRange::Full : v1d::scrub::ColorRange::Limited;
            int rgba_stride{};
            const auto rgba_ptr =
                v1d::scrub::cuda_alloc_rgba(out_w, out_h, &rgba_stride, &err);
            if (rgba_ptr == 0)
                throw std::runtime_error(err);
            if (!v1d::scrub::convert_nv12_to_rgba8(
                    surf.device_ptr,
                    surf.pitch,
                    surf.width,
                    surf.height,
                    surf.luma_surface_rows > 0 ? surf.luma_surface_rows : surf.height,
                    info.bit_depth,
                    rgba_ptr,
                    rgba_stride,
                    out_w,
                    out_h,
                    cm,
                    range,
                    &err))
            {
                v1d::scrub::cuda_free(rgba_ptr);
                v1d::scrub::cuda_free(surf.device_ptr);
                throw std::runtime_error(err);
            }
            v1d::scrub::cuda_free(surf.device_ptr);
            std::string pixels;
            if (!v1d::scrub::cuda_read_rgba_device(rgba_ptr, out_w, out_h, rgba_stride, &pixels, &err))
            {
                v1d::scrub::cuda_free(rgba_ptr);
                throw std::runtime_error(err);
            }
            v1d::scrub::cuda_free(rgba_ptr);
            return py::bytes(pixels);
        },
        py::arg("path"),
        py::arg("presentation_index"),
        py::arg("out_w"),
        py::arg("out_h"),
        py::arg("cuda_device") = 0,
        py::arg("fatbin_path"),
        py::arg("matrix") = "bt709",
        py::arg("full_range") = false);

    m.def(
        "peek_nv12",
        [](std::uint64_t nv12_device, int pitch, int luma_rows, int x, int y) {
            std::uint8_t yv{}, u{}, v{};
            std::string err;
            if (!v1d::scrub::cuda_peek_nv12(nv12_device, pitch, luma_rows, x, y, &yv, &u, &v, &err))
                throw std::runtime_error(err);
            return py::make_tuple(static_cast<int>(yv), static_cast<int>(u), static_cast<int>(v));
        },
        py::arg("nv12_device"),
        py::arg("pitch"),
        py::arg("luma_rows"),
        py::arg("x"),
        py::arg("y"));

    m.def(
        "cuda_peek_bytes",
        [](std::uint64_t device_ptr, std::size_t byte_offset, std::size_t size) {
            std::string err;
            if (!v1d::scrub::cuda_ready())
                throw std::runtime_error("cuda not initialized");
            std::string buf(size, '\0');
            auto* cu = v1d::scrub::cuda_driver();
            cu->cuCtxPushCurrent(v1d::scrub::cuda_context_handle());
            const CUresult r = cu->cuMemcpyDtoH(
                buf.data(), static_cast<CUdeviceptr>(device_ptr + byte_offset), size);
            cu->cuCtxPopCurrent(nullptr);
            if (r != CUDA_SUCCESS)
                throw std::runtime_error("cuda_peek_bytes failed");
            return py::bytes(buf);
        },
        py::arg("device_ptr"),
        py::arg("byte_offset"),
        py::arg("size"));

    m.def(
        "_engine_new",
        [](int cuda_device, int cache_mb, const std::string& fatbin_path, int proxy_height, int proxy_vram_mb) {
            return reinterpret_cast<std::uintptr_t>(
                new v1d::scrub::Engine(cuda_device, cache_mb, fatbin_path, proxy_height, proxy_vram_mb));
        },
        py::arg("cuda_device") = 0,
        py::arg("cache_mb") = 0,
        py::arg("fatbin_path"),
        py::arg("proxy_height") = 270,
        py::arg("proxy_vram_mb") = 256);
    m.def(
        "_engine_delete",
        [](std::uintptr_t handle) {
            delete reinterpret_cast<v1d::scrub::Engine*>(handle);
        },
        py::arg("handle"));
    m.def(
        "_engine_open_clip",
        [](std::uintptr_t handle, const std::string& path) {
            auto* engine = reinterpret_cast<v1d::scrub::Engine*>(handle);
            v1d::scrub::ClipInfo info{};
            {
                py::gil_scoped_release release;
                info = engine->open_clip(path);
            }
            py::dict d;
            d["frames"] = info.frames;
            d["fps_num"] = info.fps_num;
            d["fps_den"] = info.fps_den;
            d["width"] = info.width;
            d["height"] = info.height;
            d["codec"] = (info.codec == v1d::scrub::VideoCodec::H264) ? "h264" : "hevc";
            d["bit_depth"] = info.bit_depth;
            d["gop_max"] = info.gop_max;
            d["sync_count"] = info.sync_count;
            return d;
        },
        py::arg("handle"),
        py::arg("path"));
    m.def(
        "_engine_set_output_size",
        [](std::uintptr_t handle, int w, int h) {
            reinterpret_cast<v1d::scrub::Engine*>(handle)->set_output_size(w, h);
        },
        py::arg("handle"),
        py::arg("width"),
        py::arg("height"));
    m.def(
        "_engine_set_scrubbing",
        [](std::uintptr_t handle, bool scrubbing) {
            reinterpret_cast<v1d::scrub::Engine*>(handle)->set_scrubbing(scrubbing);
        },
        py::arg("handle"),
        py::arg("scrubbing"));
    m.def(
        "_engine_set_playback",
        [](std::uintptr_t handle, bool playback) {
            reinterpret_cast<v1d::scrub::Engine*>(handle)->set_playback(playback);
        },
        py::arg("handle"),
        py::arg("playback"));
    m.def(
        "_engine_request_frame",
        [](std::uintptr_t handle, int index) {
            reinterpret_cast<v1d::scrub::Engine*>(handle)->request_frame(index);
        },
        py::arg("handle"),
        py::arg("presentation_index"));
    m.def(
        "_engine_poll",
        [](std::uintptr_t handle) -> py::object {
            const auto frame = reinterpret_cast<v1d::scrub::Engine*>(handle)->poll();
            if (!frame)
                return py::none();
            py::dict d;
            d["ptr"] = frame->ptr;
            d["width"] = frame->width;
            d["height"] = frame->height;
            d["stride"] = frame->stride;
            d["frame"] = frame->frame;
            d["gen"] = frame->gen;
            d["tier"] = frame->tier;
            d["latency_us"] = frame->latency_us;
            return d;
        },
        py::arg("handle"));
    m.def(
        "_engine_latest_present",
        [](std::uintptr_t handle) -> py::object {
            const auto frame = reinterpret_cast<v1d::scrub::Engine*>(handle)->latest_present();
            if (!frame)
                return py::none();
            py::dict d;
            d["ptr"] = frame->ptr;
            d["width"] = frame->width;
            d["height"] = frame->height;
            d["stride"] = frame->stride;
            d["frame"] = frame->frame;
            d["gen"] = frame->gen;
            d["tier"] = frame->tier;
            d["latency_us"] = frame->latency_us;
            return d;
        },
        py::arg("handle"));
    m.def(
        "_engine_copy_latest_rgba",
        [](std::uintptr_t handle, std::uint64_t dst_ptr, int dst_stride) {
            return reinterpret_cast<v1d::scrub::Engine*>(handle)->copy_latest_rgba_to(dst_ptr, dst_stride);
        },
        py::arg("handle"),
        py::arg("dst_ptr"),
        py::arg("dst_stride"));
    m.def(
        "_engine_stats",
        [](std::uintptr_t handle) {
            const auto s = reinterpret_cast<v1d::scrub::Engine*>(handle)->stats();
            py::dict d;
            d["state"] = s.state;
            d["last_error"] = s.last_error;
            d["requests"] = s.requests;
            d["coalesced"] = s.coalesced;
            d["aborted_runs"] = s.aborted_runs;
            d["decoded_frames"] = s.decoded_frames;
            d["cache_hits"] = s.cache_hits;
            d["cache_bytes"] = s.cache_bytes;
            d["published"] = s.published;
            d["dropped_stale"] = s.dropped_stale;
            d["hot_path_host_pixel_copies"] = s.hot_path_host_pixel_copies;
            d["debug_readbacks"] = s.debug_readbacks;
            d["proxy_d2h_bytes"] = s.proxy_d2h_bytes;
            d["proxy_h2d_bytes"] = s.proxy_h2d_bytes;
            d["proxy_ready"] = s.proxy_ready;
            d["proxy_build_frame"] = s.proxy_build_frame;
            d["proxy_build_total"] = s.proxy_build_total;
            d["lat_us_p50"] = 0;
            d["lat_us_p95"] = 0;
            d["decode_fps"] = 0.0;
            static std::uint64_t cached_free = 0;
            static std::chrono::steady_clock::time_point last{};
            const auto now = std::chrono::steady_clock::now();
            if (last.time_since_epoch().count() == 0 ||
                now - last >= std::chrono::seconds(1))
            {
                last = now;
                std::size_t free_b{}, total_b{};
                std::string mem_err;
                if (v1d::scrub::cuda_mem_info(&free_b, &total_b, &mem_err))
                    cached_free = free_b;
            }
            d["vram_free_bytes"] = cached_free;
            return d;
        },
        py::arg("handle"));
    m.def(
        "_engine_debug_read_rgba",
        [](std::uintptr_t handle, std::uint64_t ptr) {
            std::string bytes;
            {
                py::gil_scoped_release release;
                bytes = reinterpret_cast<v1d::scrub::Engine*>(handle)->debug_read_rgba(ptr);
            }
            return py::bytes(bytes);
        },
        py::arg("handle"),
        py::arg("ptr"));
    m.def(
        "_engine_close",
        [](std::uintptr_t handle) {
            py::gil_scoped_release release;
            reinterpret_cast<v1d::scrub::Engine*>(handle)->close();
        },
        py::arg("handle"));
    m.def(
        "_engine_shutdown",
        [](std::uintptr_t handle) {
            py::gil_scoped_release release;
            reinterpret_cast<v1d::scrub::Engine*>(handle)->shutdown();
        },
        py::arg("handle"));

    m.def(
        "proxy_cache_path",
        [](const std::string& source_path) {
            std::string err;
            const auto id = v1d::scrub::proxy_source_identity(source_path, &err);
            if (!err.empty())
                throw std::runtime_error(err);
            return v1d::scrub::proxy_cache_file_path(id);
        },
        py::arg("source_path"));

    m.def(
        "proxy_nv12_frame_bytes",
        [](int width, int height) {
            return v1d::scrub::proxy_nv12_frame_bytes(
                static_cast<std::uint32_t>(width), static_cast<std::uint32_t>(height));
        },
        py::arg("width"),
        py::arg("height"));

    m.def(
        "proxy_file_size_bytes",
        [](int frame_count, std::uint64_t frame_bytes) {
            v1d::scrub::ProxyHeader hdr;
            hdr.frame_count = static_cast<std::uint32_t>(frame_count);
            hdr.frame_bytes = frame_bytes;
            return v1d::scrub::proxy_file_size_bytes(hdr);
        },
        py::arg("frame_count"),
        py::arg("frame_bytes"));

    m.def(
        "proxy_build_cache",
        [](const std::string& clip_path, int proxy_height, int cuda_device, const std::string& fatbin_path) {
            v1d::scrub::ProxyBuildResult result;
            std::string err;
            if (!v1d::scrub::build_proxy_cache(clip_path, proxy_height, cuda_device, fatbin_path, &result, &err))
                throw std::runtime_error(err);
            py::dict d;
            d["cache_path"] = result.cache_path;
            d["rebuilt"] = result.rebuilt;
            d["bytes_written"] = result.bytes_written;
            d["build_seconds"] = result.build_seconds;
            return d;
        },
        py::arg("clip_path"),
        py::arg("proxy_height") = 270,
        py::arg("cuda_device") = 0,
        py::arg("fatbin_path"));
}
