// SPDX-License-Identifier: MIT
#include "nvdec_decoder.h"

#include "cuda_context.h"
#include "scrub_error.h"

#include <ffnvcodec/dynlink_cuviddec.h>
#include <ffnvcodec/dynlink_loader.h>

#include <algorithm>
#include <cstring>

namespace v1d::scrub
{
namespace
{

CudaFunctions* drv_cuda()
{
    return cuda_driver();
}

CuvidFunctions* drv_cuvid()
{
    return cuvid_driver();
}

static int CUDAAPI sequence_trampoline(void* user, CUVIDEOFORMAT* fmt)
{
    return static_cast<NvdecDecoder*>(user)->handle_sequence(fmt);
}

static int CUDAAPI decode_trampoline(void* user, CUVIDPICPARAMS* pic)
{
    return static_cast<NvdecDecoder*>(user)->handle_decode(pic);
}

static int CUDAAPI display_trampoline(void* user, CUVIDPARSERDISPINFO* info)
{
    return static_cast<NvdecDecoder*>(user)->handle_display(info);
}

} // namespace

NvdecDecoder::~NvdecDecoder()
{
    close();
}

void NvdecDecoder::destroy_pipeline()
{
    if (parser_ && drv_cuvid())
    {
        drv_cuvid()->cuvidDestroyVideoParser(static_cast<CUvideoparser>(parser_));
        parser_ = nullptr;
    }
    if (decoder_ && drv_cuvid())
    {
        drv_cuvid()->cuvidDestroyDecoder(static_cast<CUvideodecoder>(decoder_));
        decoder_ = nullptr;
    }
    if (result_.device_ptr)
    {
        cuda_free(result_.device_ptr);
        result_ = {};
    }
    cont_open_ = false;
    cont_sync_ = -1;
    cont_next_di_ = 0;
    cont_last_target_ = -1;
}

void NvdecDecoder::close()
{
    destroy_pipeline();
    index_ = nullptr;
}

void NvdecDecoder::open(const Mp4Index& index)
{
    if (!cuda_ready())
        throw ScrubError("CUDA not initialized");
    close();
    index_ = &index;
    codec_ = (index.info().codec == VideoCodec::HEVC) ? cudaVideoCodec_HEVC : cudaVideoCodec_H264;

    CUVIDDECODECAPS caps{};
    caps.eCodecType = codec_;
    caps.eChromaFormat = cudaVideoChromaFormat_420;
    caps.nBitDepthMinus8 = static_cast<unsigned char>(index.info().bit_depth > 8 ? 2 : 0);
    if (!drv_cuvid() || !drv_cuvid()->cuvidGetDecoderCaps)
        throw ScrubError("cuvidGetDecoderCaps unavailable");
    drv_cuda()->cuCtxPushCurrent(cuda_context_handle());
    const CUresult caps_r = drv_cuvid()->cuvidGetDecoderCaps(&caps);
    drv_cuda()->cuCtxPopCurrent(nullptr);
    if (caps_r != CUDA_SUCCESS)
        throw ScrubError("cuvidGetDecoderCaps failed");
    if (!caps.bIsSupported)
        throw ScrubError("NVDEC does not support this stream");
    if (static_cast<unsigned>(index.info().width) > caps.nMaxWidth ||
        static_cast<unsigned>(index.info().height) > caps.nMaxHeight)
        throw ScrubError("stream exceeds NVDEC max dimensions");

}

bool NvdecDecoder::create_parser()
{
    CUVIDPARSERPARAMS pp{};
    pp.CodecType = codec_;
    pp.ulMaxNumDecodeSurfaces = 32;
    pp.ulClockRate = index_ ? index_->info().timescale : 30000;
    // 0: show a frame as soon as the parser can. 2 holds two extra pictures
    // in the display queue, so each exact seek decodes past the target.
    pp.ulMaxDisplayDelay = 0;
    pp.ulErrorThreshold = 100;
    pp.pUserData = this;
    pp.pfnSequenceCallback = sequence_trampoline;
    pp.pfnDecodePicture = decode_trampoline;
    pp.pfnDisplayPicture = display_trampoline;
    CUvideoparser parser{};
    if (drv_cuvid()->cuvidCreateVideoParser(&parser, &pp) != CUDA_SUCCESS)
        return false;
    parser_ = parser;
    return true;
}

void NvdecDecoder::feed_packet(const std::uint8_t* data, std::size_t size, std::int64_t pts, bool discontinuity)
{
    CUVIDSOURCEDATAPACKET pkt{};
    pkt.payload = data;
    pkt.payload_size = static_cast<unsigned long>(size);
    pkt.flags = CUVID_PKT_TIMESTAMP;
    pkt.timestamp = pts;
    if (discontinuity)
        pkt.flags |= CUVID_PKT_DISCONTINUITY;
    drv_cuvid()->cuvidParseVideoData(static_cast<CUvideoparser>(parser_), &pkt);
}

void NvdecDecoder::feed_eos()
{
    CUVIDSOURCEDATAPACKET pkt{};
    pkt.flags = CUVID_PKT_ENDOFSTREAM;
    drv_cuvid()->cuvidParseVideoData(static_cast<CUvideoparser>(parser_), &pkt);
}

int NvdecDecoder::handle_sequence(void* fmt_opaque)
{
    auto* fmt = static_cast<CUVIDEOFORMAT*>(fmt_opaque);
    if (decoder_)
    {
        drv_cuvid()->cuvidDestroyDecoder(static_cast<CUvideodecoder>(decoder_));
        decoder_ = nullptr;
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
    coded_width_ = static_cast<int>(ci.ulWidth);
    coded_height_ = static_cast<int>(ci.ulHeight);
    display_width_ = static_cast<int>(ci.ulTargetWidth);
    display_height_ = static_cast<int>(ci.ulTargetHeight);
    CUvideodecoder dec{};
    if (drv_cuvid()->cuvidCreateDecoder(&dec, &ci) != CUDA_SUCCESS)
        return 0;
    decoder_ = dec;
    return static_cast<int>(ci.ulNumDecodeSurfaces);
}

int NvdecDecoder::handle_decode(void* pic_opaque)
{
    auto* pic = static_cast<CUVIDPICPARAMS*>(pic_opaque);
    drv_cuda()->cuCtxPushCurrent(cuda_context_handle());
    const CUresult r = decoder_ ? drv_cuvid()->cuvidDecodePicture(static_cast<CUvideodecoder>(decoder_), pic)
                                : CUDA_ERROR_UNKNOWN;
    drv_cuda()->cuCtxPopCurrent(nullptr);
    return r == CUDA_SUCCESS ? 1 : 0;
}

int NvdecDecoder::handle_display(void* info_opaque)
{
    auto* info = static_cast<CUVIDPARSERDISPINFO*>(info_opaque);
    int pres = index_ ? index_->presentation_for_pts(static_cast<std::int64_t>(info->timestamp)) : -1;
    if (pres < 0)
        pres = display_base_ + display_serial_++;
    else
        ++display_serial_;
    if (pres != target_presentation_)
        return 1;

    drv_cuda()->cuCtxPushCurrent(cuda_context_handle());
    CUdeviceptr src{};
    unsigned src_pitch{};
    CUVIDPROCPARAMS pp{};
    pp.progressive_frame = info->progressive_frame;
    pp.second_field = info->repeat_first_field + 1;
    pp.top_field_first = info->top_field_first;
    pp.unpaired_field = (info->repeat_first_field < 0);
    const CUresult mr =
        drv_cuvid()->cuvidMapVideoFrame(
            static_cast<CUvideodecoder>(decoder_), info->picture_index, &src, &src_pitch, &pp);
    if (mr == CUDA_SUCCESS)
    {
        const int w = display_width_;
        const int h = display_height_;
        // NVDEC NV12: chroma follows luma at pitch * display height (ulTargetHeight), not coded height.
        const std::size_t nv12_bytes = static_cast<std::size_t>(src_pitch) * static_cast<std::size_t>(h * 3 / 2);
        if (!result_.device_ptr)
        {
            CUdeviceptr dst{};
            if (drv_cuda()->cuMemAlloc(&dst, nv12_bytes) == CUDA_SUCCESS)
                result_.device_ptr = static_cast<std::uint64_t>(dst);
        }
        if (result_.device_ptr)
        {
            const CUdeviceptr dst = static_cast<CUdeviceptr>(result_.device_ptr);
            CUDA_MEMCPY2D cp_y{};
            cp_y.srcMemoryType = CU_MEMORYTYPE_DEVICE;
            cp_y.srcDevice = src;
            cp_y.srcPitch = src_pitch;
            cp_y.dstMemoryType = CU_MEMORYTYPE_DEVICE;
            cp_y.dstDevice = dst;
            cp_y.dstPitch = src_pitch;
            cp_y.WidthInBytes = static_cast<std::size_t>(src_pitch);
            cp_y.Height = static_cast<std::size_t>(h);
            drv_cuda()->cuMemcpy2D(&cp_y);

            CUDA_MEMCPY2D cp_uv{};
            cp_uv.srcMemoryType = CU_MEMORYTYPE_DEVICE;
            cp_uv.srcDevice = src + static_cast<std::size_t>(src_pitch) * static_cast<std::size_t>(h);
            cp_uv.srcPitch = src_pitch;
            cp_uv.dstMemoryType = CU_MEMORYTYPE_DEVICE;
            cp_uv.dstDevice = dst + static_cast<std::size_t>(src_pitch) * static_cast<std::size_t>(h);
            cp_uv.dstPitch = src_pitch;
            cp_uv.WidthInBytes = static_cast<std::size_t>(src_pitch);
            cp_uv.Height = static_cast<std::size_t>(h / 2);
            drv_cuda()->cuMemcpy2D(&cp_uv);

            result_.width = w;
            result_.height = h;
            result_.pitch = static_cast<int>(src_pitch);
            result_.luma_surface_rows = h;
            result_.coded_height = coded_height_;
            result_.presentation_index = pres;
            got_target_ = true;
        }
        drv_cuvid()->cuvidUnmapVideoFrame(static_cast<CUvideodecoder>(decoder_), src);
    }
    drv_cuda()->cuCtxPopCurrent(nullptr);
    return 1;
}

Nv12Surface NvdecDecoder::decode_presentation_frame(int presentation_index)
{
    if (!index_)
        throw ScrubError("decoder not open");
    if (presentation_index < 0 || presentation_index >= index_->info().frames)
        throw ScrubError("presentation index out of range");

    target_presentation_ = presentation_index;
    const int sync_pres = index_->sync_at_or_before(presentation_index);
    display_base_ = sync_pres;
    const int start_decode = index_->samples()[static_cast<std::size_t>(sync_pres)].sample_idx;
    const int sample_count = index_->info().frames;
    const bool can_continue = cont_open_ && parser_ && decoder_ && cont_sync_ == sync_pres &&
                            presentation_index == cont_last_target_ + 1 && cont_next_di_ < sample_count;

    auto restart_gop = [&]() {
        destroy_pipeline();
        if (!create_parser())
            throw ScrubError("cuvidCreateVideoParser failed");
        cont_open_ = true;
        cont_sync_ = sync_pres;
        cont_next_di_ = start_decode;
        cont_last_target_ = presentation_index - 1;
        display_serial_ = 0;
        got_target_ = false;
        result_.presentation_index = -1;
    };

    auto feed_until_target = [&]() {
        bool first = cont_next_di_ == start_decode;
        drv_cuda()->cuCtxPushCurrent(cuda_context_handle());
        for (int di = cont_next_di_; di < sample_count; ++di)
        {
            feed_scratch_ = index_->annexb_for_decode_sample(di, first && di == start_decode);
            const auto& s = index_->decode_sample(di);
            feed_packet(feed_scratch_.data(), feed_scratch_.size(), s.pts, di == start_decode);
            cont_next_di_ = di + 1;
            first = false;
            if (got_target_)
                break;
        }
        if (!got_target_)
        {
            feed_eos();
            cont_open_ = false;
        }
        drv_cuda()->cuCtxPopCurrent(nullptr);
    };

    got_target_ = false;
    result_.presentation_index = -1;
    if (!can_continue)
        restart_gop();
    feed_until_target();
    // Long-GOP B-frame clips can miss the target on sequential continuation
    // (h264_1080_g30_b2 around the first reorder window). Restart that GOP once.
    if (!got_target_ && can_continue)
    {
        restart_gop();
        feed_until_target();
    }

    if (!got_target_)
        throw ScrubError("NVDEC did not output the requested frame");

    cont_last_target_ = presentation_index;
    Nv12Surface out = result_;
    result_.device_ptr = 0;
    return out;
}

} // namespace v1d::scrub
