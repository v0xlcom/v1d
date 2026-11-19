// SPDX-License-Identifier: MIT
// S1 NVDEC spike: ffnvcodec dynlink + libav demux (dev only, not shipped).

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavcodec/bsf.h>
#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
}

#include <ffnvcodec/dynlink_cuda.h>
#include <ffnvcodec/dynlink_cuviddec.h>
#include <ffnvcodec/dynlink_loader.h>

namespace
{

using Clock = std::chrono::steady_clock;

static CudaFunctions* g_cu{};
static CuvidFunctions* g_cv{};
static CUcontext g_ctx{};
static CUvideodecoder g_dec{};
static CUvideoparser g_parser{};
static cudaVideoCodec g_codec = cudaVideoCodec_H264;
static int g_width{};
static int g_height{};
static uint64_t g_frames_out{};
static uint64_t g_decode_cb{};
static bool g_got_frame{};

static int CUDAAPI on_seq(void*, CUVIDEOFORMAT* fmt)
{
    if (g_dec)
    {
        g_cv->cuvidDestroyDecoder(g_dec);
        g_dec = nullptr;
    }
    CUVIDDECODECREATEINFO ci{};
    ci.CodecType = fmt->codec;
    ci.ChromaFormat = fmt->chroma_format;
    ci.OutputFormat = cudaVideoSurfaceFormat_NV12;
    ci.bitDepthMinus8 = fmt->bit_depth_luma_minus8;
    ci.DeinterlaceMode = cudaVideoDeinterlaceMode_Weave;
    ci.ulNumOutputSurfaces = 4;
    ci.ulCreationFlags = cudaVideoCreate_PreferCUVID;
    ci.ulNumDecodeSurfaces =
        static_cast<unsigned int>(std::max(20, static_cast<int>(fmt->min_num_decode_surfaces) + 8));
    ci.ulWidth = fmt->coded_width;
    ci.ulHeight = fmt->coded_height;
    ci.ulMaxWidth = fmt->coded_width;
    ci.ulMaxHeight = fmt->coded_height;
    ci.ulTargetWidth = fmt->display_area.right - fmt->display_area.left;
    ci.ulTargetHeight = fmt->display_area.bottom - fmt->display_area.top;
    g_width = static_cast<int>(ci.ulTargetWidth);
    g_height = static_cast<int>(ci.ulTargetHeight);
    if (g_cv->cuvidCreateDecoder(&g_dec, &ci) != CUDA_SUCCESS)
        return 0;
    // Parser expects the number of decode surfaces, not a boolean.
    return static_cast<int>(ci.ulNumDecodeSurfaces);
}

static int CUDAAPI on_decode(void*, CUVIDPICPARAMS* pic)
{
    g_cu->cuCtxPushCurrent(g_ctx);
    const CUresult r = g_dec ? g_cv->cuvidDecodePicture(g_dec, pic) : CUDA_ERROR_UNKNOWN;
    if (r == CUDA_SUCCESS)
        ++g_decode_cb;
    g_cu->cuCtxPopCurrent(nullptr);
    return r == CUDA_SUCCESS ? 1 : 0;
}

static int CUDAAPI on_display(void*, CUVIDPARSERDISPINFO* info)
{
    g_cu->cuCtxPushCurrent(g_ctx);
    CUdeviceptr ptr{};
    unsigned pitch{};
    CUVIDPROCPARAMS pp{};
    pp.progressive_frame = info->progressive_frame;
    pp.second_field = info->repeat_first_field + 1;
    pp.top_field_first = info->top_field_first;
    pp.unpaired_field = (info->repeat_first_field < 0);
    CUresult mr = g_cv->cuvidMapVideoFrame(g_dec, info->picture_index, &ptr, &pitch, &pp);
    if (mr == CUDA_SUCCESS)
    {
        g_frames_out++;
        g_got_frame = true;
        g_cv->cuvidUnmapVideoFrame(g_dec, ptr);
    }
    g_cu->cuCtxPopCurrent(nullptr);
    return mr == CUDA_SUCCESS ? 1 : 0;
}

static void destroy_stack()
{
    if (g_parser)
    {
        g_cv->cuvidDestroyVideoParser(g_parser);
        g_parser = nullptr;
    }
    if (g_dec)
    {
        g_cv->cuvidDestroyDecoder(g_dec);
        g_dec = nullptr;
    }
}

static bool create_parser()
{
    CUVIDPARSERPARAMS pp{};
    pp.CodecType = g_codec;
    pp.ulMaxNumDecodeSurfaces = 32;
    pp.ulClockRate = 30000;
    pp.ulMaxDisplayDelay = 2;
    pp.ulErrorThreshold = 100;
    pp.pfnSequenceCallback = on_seq;
    pp.pfnDecodePicture = on_decode;
    pp.pfnDisplayPicture = on_display;
    return g_cv->cuvidCreateVideoParser(&g_parser, &pp) == CUDA_SUCCESS;
}

static void feed_packet(const uint8_t* data, size_t size, int64_t pts, bool discontinuity)
{
    CUVIDSOURCEDATAPACKET pkt{};
    pkt.payload = data;
    pkt.payload_size = static_cast<unsigned long>(size);
    pkt.flags = CUVID_PKT_TIMESTAMP;
    pkt.timestamp = pts;
    if (discontinuity)
        pkt.flags |= CUVID_PKT_DISCONTINUITY;
    g_cv->cuvidParseVideoData(g_parser, &pkt);
}

static void feed_eos()
{
    CUVIDSOURCEDATAPACKET pkt{};
    pkt.flags = CUVID_PKT_ENDOFSTREAM;
    g_cv->cuvidParseVideoData(g_parser, &pkt);
}

struct Demux
{
    AVFormatContext* fmt{};
    AVBSFContext* bsf{};
    int vstream{-1};
};

static bool demux_open(Demux& d, const char* path)
{
    if (avformat_open_input(&d.fmt, path, nullptr, nullptr) < 0)
        return false;
    if (avformat_find_stream_info(d.fmt, nullptr) < 0)
        return false;
    d.vstream = av_find_best_stream(d.fmt, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0);
    if (d.vstream < 0)
        return false;
    const char* bsf_name = (g_codec == cudaVideoCodec_HEVC) ? "hevc_mp4toannexb" : "h264_mp4toannexb";
    const AVBitStreamFilter* f = av_bsf_get_by_name(bsf_name);
    if (!f)
        return false;
    if (av_bsf_alloc(f, &d.bsf) < 0)
        return false;
    if (avcodec_parameters_copy(d.bsf->par_in, d.fmt->streams[d.vstream]->codecpar) < 0)
        return false;
    if (av_bsf_init(d.bsf) < 0)
        return false;
    return true;
}

static void demux_close(Demux& d)
{
    if (d.bsf)
        av_bsf_free(&d.bsf);
    if (d.fmt)
        avformat_close_input(&d.fmt);
}

static bool demux_next_annex(Demux& d, std::vector<uint8_t>& out, int64_t& pts, bool& key)
{
    out.clear();
    AVPacket* pkt = av_packet_alloc();
    AVPacket* filt = av_packet_alloc();
    if (!pkt || !filt)
    {
        av_packet_free(&pkt);
        av_packet_free(&filt);
        return false;
    }
    while (true)
    {
        if (av_read_frame(d.fmt, pkt) < 0)
        {
            av_packet_free(&pkt);
            av_packet_free(&filt);
            return false;
        }
        if (pkt->stream_index != d.vstream)
        {
            av_packet_unref(pkt);
            continue;
        }
        if (av_bsf_send_packet(d.bsf, pkt) < 0)
        {
            av_packet_unref(pkt);
            continue;
        }
        av_packet_unref(pkt);
        if (av_bsf_receive_packet(d.bsf, filt) < 0)
            continue;
        out.assign(filt->data, filt->data + filt->size);
        pts = filt->pts;
        key = (filt->flags & AV_PKT_FLAG_KEY) != 0;
        av_packet_unref(filt);
        av_packet_free(&pkt);
        av_packet_free(&filt);
        return true;
    }
}

static double decode_file(const char* path, int /*warmup*/)
{
    Demux demux{};
    if (!demux_open(demux, path))
        return 0.0;

    destroy_stack();
    if (!create_parser())
        return 0.0;
    g_frames_out = 0;
    g_decode_cb = 0;
    uint64_t packets = 0;
    auto t0 = Clock::now();
    std::vector<uint8_t> au;
    int64_t pts{};
    bool key{};
    int64_t ts = 0;
    while (demux_next_annex(demux, au, pts, key))
    {
        ++packets;
        feed_packet(au.data(), au.size(), ts++, false);
    }
    feed_eos();
    auto t1 = Clock::now();
    demux_close(demux);
    const double sec = std::chrono::duration<double>(t1 - t0).count();
    std::printf("packets_fed=%llu decode_cb=%llu\n", static_cast<unsigned long long>(packets),
                static_cast<unsigned long long>(g_decode_cb));
    return sec > 0 ? static_cast<double>(g_frames_out) / sec : 0.0;
}

static double single_idr_ms(const char* path)
{
    Demux demux{};
    if (!demux_open(demux, path))
        return -1.0;
    std::vector<uint8_t> au;
    int64_t pts{};
    bool key{};
    int key_index = 0;
    while (demux_next_annex(demux, au, pts, key))
    {
        if (key)
        {
            if (key_index == 1)
            {
                destroy_stack();
                if (!create_parser())
                    return -1.0;
                g_got_frame = false;
                g_frames_out = 0;
                auto t0 = Clock::now();
                feed_packet(au.data(), au.size(), pts, true);
                feed_eos();
                auto t1 = Clock::now();
                demux_close(demux);
                return g_got_frame ? std::chrono::duration<double, std::milli>(t1 - t0).count() : -1.0;
            }
            ++key_index;
        }
    }
    demux_close(demux);
    return -1.0;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: %s h264|hevc <clip.mp4>\n", argv[0]);
        return 2;
    }
    g_codec = (std::strcmp(argv[1], "hevc") == 0) ? cudaVideoCodec_HEVC : cudaVideoCodec_H264;
    const char* path = argv[2];

    if (cuda_load_functions(&g_cu, nullptr) != 0 || cuvid_load_functions(&g_cv, nullptr) != 0)
    {
        std::fprintf(stderr, "dynlink load failed\n");
        return 1;
    }
    if (g_cu->cuInit(0) != CUDA_SUCCESS)
        return 1;
    CUdevice dev{};
    g_cu->cuDeviceGet(&dev, 0);
    g_cu->cuDevicePrimaryCtxRetain(&g_ctx, dev);
    g_cu->cuCtxPushCurrent(g_ctx);

    CUVIDDECODECAPS caps{};
    caps.eCodecType = g_codec;
    caps.eChromaFormat = cudaVideoChromaFormat_420;
    caps.nBitDepthMinus8 = 0;
    if (g_cv->cuvidGetDecoderCaps && g_cv->cuvidGetDecoderCaps(&caps) == CUDA_SUCCESS)
        std::printf("decoder_caps supported=%d max=%ux%u mb=%u\n", caps.bIsSupported, caps.nMaxWidth,
                    caps.nMaxHeight, caps.nMaxMBCount);

    const double fps = decode_file(path, 1);
    std::printf("clip=%s sequential_fps=%.2f frames=%llu %dx%d\n", path, fps,
                static_cast<unsigned long long>(g_frames_out), g_width, g_height);

    const double idr_ms = single_idr_ms(path);
    std::printf("single_idr_first_display_ms=%.3f\n", idr_ms);

    destroy_stack();
    g_cu->cuCtxPopCurrent(nullptr);
    g_cu->cuDevicePrimaryCtxRelease(dev);
    cuda_free_functions(&g_cu);
    cuvid_free_functions(&g_cv);
    return 0;
}
