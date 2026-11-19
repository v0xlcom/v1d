// SPDX-License-Identifier: MIT
#include "mp4_index.h"

#include "scrub_error.h"

#include <algorithm>
#include <cstring>
#include <limits>
#include <numeric>
#include <string_view>

namespace v1d::scrub
{
namespace
{

std::uint32_t read_u32(const std::uint8_t* p)
{
    return (static_cast<std::uint32_t>(p[0]) << 24) | (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) | static_cast<std::uint32_t>(p[3]);
}

std::uint64_t read_u64(const std::uint8_t* p)
{
    std::uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v = (v << 8) | p[i];
    return v;
}

std::int32_t read_i32(const std::uint8_t* p)
{
    return static_cast<std::int32_t>(read_u32(p));
}

std::int64_t read_i64(const std::uint8_t* p)
{
    return static_cast<std::int64_t>(read_u64(p));
}

std::uint16_t read_u16(const std::uint8_t* p)
{
    return (static_cast<std::uint16_t>(p[0]) << 8) | static_cast<std::uint16_t>(p[1]);
}

struct Span
{
    const std::uint8_t* data{};
    std::size_t size{};
};

Span subspan(const Span& s, std::size_t off, std::size_t len)
{
    if (off > s.size)
        throw ScrubError("atom truncated");
    if (len > s.size - off)
        throw ScrubError("atom truncated");
    return { s.data + off, len };
}

struct AtomView
{
    std::string type;
    Span payload;
    std::size_t header_size{};
};

std::vector<AtomView> parse_children(const Span& payload)
{
    std::vector<AtomView> out;
    std::size_t off = 0;
    while (off + 8 <= payload.size)
    {
        std::uint64_t sz = read_u32(payload.data + off);
        const char* typ = reinterpret_cast<const char*>(payload.data + off + 4);
        std::size_t hdr = 8;
        std::size_t start = off + 8;
        if (sz == 1)
        {
            if (off + 16 > payload.size)
                throw ScrubError("invalid extended atom size");
            sz = read_u64(payload.data + off + 8);
            hdr = 16;
            start = off + 16;
        }
        if (sz < hdr)
            throw ScrubError("invalid atom size");
        if (sz == 0)
            sz = payload.size - off;
        if (off + sz > payload.size)
            throw ScrubError("atom extends past parent");
        AtomView a;
        a.type.assign(typ, 4);
        a.header_size = hdr;
        a.payload = subspan(payload, start, static_cast<std::size_t>(sz) - hdr);
        out.push_back(a);
        off += static_cast<std::size_t>(sz);
    }
    return out;
}

const AtomView* find_child(const std::vector<AtomView>& atoms, const char* type)
{
    for (const auto& a : atoms)
        if (a.type == type)
            return &a;
    return nullptr;
}

void reject_fragmented(const Span& file)
{
    for (std::size_t i = 0; i + 4 <= file.size; ++i)
    {
        if (file.data[i + 0] == 'm' && file.data[i + 1] == 'o' && file.data[i + 2] == 'o' &&
            file.data[i + 3] == 'f')
            throw ScrubError("fragmented MP4 (moof) is not supported");
    }
}

std::vector<std::uint8_t> length_prefixed_to_annexb(const std::uint8_t* data, std::size_t size, int nal_length_size)
{
    std::vector<std::uint8_t> out;
    std::size_t off = 0;
    while (off + static_cast<std::size_t>(nal_length_size) <= size)
    {
        std::uint32_t nlen = 0;
        for (int i = 0; i < nal_length_size; ++i)
            nlen = (nlen << 8) | data[off + i];
        off += static_cast<std::size_t>(nal_length_size);
        if (nlen == 0 || off + nlen > size)
            throw ScrubError("invalid NAL length in sample");
        out.push_back(0);
        out.push_back(0);
        out.push_back(0);
        out.push_back(1);
        out.insert(out.end(), data + off, data + off + nlen);
        off += nlen;
    }
    if (off != size)
        throw ScrubError("trailing bytes in sample");
    return out;
}

class BitReader
{
public:
    BitReader(const std::uint8_t* data, std::size_t size) : data_(data), size_(size)
    {
    }

    bool read_bit()
    {
        if (bit_ >= size_ * 8)
            return false;
        const std::size_t byte = bit_ / 8;
        const int shift = 7 - static_cast<int>(bit_ % 8);
        ++bit_;
        return (data_[byte] >> shift) & 1;
    }

    std::uint32_t read_bits(int count)
    {
        std::uint32_t v = 0;
        for (int i = 0; i < count; ++i)
            v = (v << 1) | (read_bit() ? 1u : 0u);
        return v;
    }

    std::uint32_t read_ue()
    {
        int zeros = 0;
        while (!read_bit())
            ++zeros;
        if (zeros == 0)
            return 0;
        return (1u << zeros) - 1u + read_bits(zeros);
    }

private:
    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t bit_{};
};

std::vector<std::uint8_t> nal_payload_to_rbsp(const std::uint8_t* nal, std::size_t len)
{
    std::vector<std::uint8_t> rbsp;
    for (std::size_t i = 1; i < len; ++i)
    {
        if (i + 2 < len && nal[i] == 0 && nal[i + 1] == 0 && nal[i + 2] == 3)
        {
            rbsp.push_back(0);
            rbsp.push_back(0);
            i += 2;
        }
        else
            rbsp.push_back(nal[i]);
    }
    return rbsp;
}

void reject_h264_non_420(const Span& avcC)
{
    if (avcC.size < 7)
        return;
    const int num_sps = avcC.data[5] & 0x1f;
    if (num_sps < 1)
        return;
    std::size_t off = 6;
    if (off + 2 > avcC.size)
        return;
    const std::uint16_t len = read_u16(avcC.data + off);
    off += 2;
    if (off + len > avcC.size)
        return;
    const std::uint8_t* nal = avcC.data + off;
    if ((nal[0] & 0x1f) != 7)
        return;
    const auto rbsp = nal_payload_to_rbsp(nal, len);
    if (rbsp.empty())
        return;
    BitReader br(rbsp.data(), rbsp.size());
    const std::uint32_t profile_idc = br.read_bits(8);
    br.read_bits(8);
    br.read_bits(8);
    br.read_ue();
    static const int kProfilesWithChroma[] = { 100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135 };
    bool need_chroma = false;
    for (int p : kProfilesWithChroma)
    {
        if (static_cast<int>(profile_idc) == p)
            need_chroma = true;
    }
    if (!need_chroma)
        return;
    const std::uint32_t chroma = br.read_ue();
    if (chroma != 1)
        throw ScrubError("chroma format must be 4:2:0");
}

void append_avcc_parameter_sets(std::vector<std::uint8_t>& out, const Span& avcC)
{
    if (avcC.size < 7)
        throw ScrubError("avcC too small");
    const int nal_len = (avcC.data[4] & 3) + 1;
    if (nal_len < 3 || nal_len > 4)
        throw ScrubError("unsupported NAL length size in avcC");
    const int num_sps = avcC.data[5] & 0x1f;
    std::size_t off = 6;
    for (int i = 0; i < num_sps; ++i)
    {
        if (off + 2 > avcC.size)
            throw ScrubError("avcC SPS truncated");
        const std::uint16_t len = read_u16(avcC.data + off);
        off += 2;
        if (off + len > avcC.size)
            throw ScrubError("avcC SPS truncated");
        out.push_back(0);
        out.push_back(0);
        out.push_back(0);
        out.push_back(1);
        out.insert(out.end(), avcC.data + off, avcC.data + off + len);
        off += len;
    }
    if (off >= avcC.size)
        throw ScrubError("avcC missing PPS count");
    const int num_pps = avcC.data[off++];
    for (int i = 0; i < num_pps; ++i)
    {
        if (off + 2 > avcC.size)
            throw ScrubError("avcC PPS truncated");
        const std::uint16_t len = read_u16(avcC.data + off);
        off += 2;
        if (off + len > avcC.size)
            throw ScrubError("avcC PPS truncated");
        out.push_back(0);
        out.push_back(0);
        out.push_back(0);
        out.push_back(1);
        out.insert(out.end(), avcC.data + off, avcC.data + off + len);
        off += len;
    }
}

void append_hvcc_parameter_sets(std::vector<std::uint8_t>& out, const Span& hvcC)
{
    if (hvcC.size < 23)
        throw ScrubError("hvcC too small");
    const int num_arrays = hvcC.data[22];
    std::size_t off = 23;
    for (int a = 0; a < num_arrays; ++a)
    {
        if (off + 3 > hvcC.size)
            throw ScrubError("hvcC array truncated");
        const int nal_type = hvcC.data[off] & 0x3f;
        (void)nal_type;
        const int num_nals = read_u16(hvcC.data + off + 1);
        off += 3;
        for (int n = 0; n < num_nals; ++n)
        {
            if (off + 2 > hvcC.size)
                throw ScrubError("hvcC NAL truncated");
            const std::uint16_t len = read_u16(hvcC.data + off);
            off += 2;
            if (off + len > hvcC.size)
                throw ScrubError("hvcC NAL truncated");
            out.push_back(0);
            out.push_back(0);
            out.push_back(0);
            out.push_back(1);
            out.insert(out.end(), hvcC.data + off, hvcC.data + off + len);
            off += len;
        }
    }
}

struct RawSample
{
    int sample_idx{};
    std::int64_t dts{};
    std::int64_t pts{};
    std::uint64_t offset{};
    std::uint32_t size{};
    bool is_sync{};
};

} // namespace

Mp4Index Mp4Index::open(const std::string& path)
{
    Mp4Index idx;
    idx.file_.open(path);
    const Span file{ idx.file_.data(), idx.file_.size() };
    reject_fragmented(file);

    Span moov_payload;
    for (std::size_t off = 0; off + 8 <= file.size;)
    {
        std::uint64_t sz = read_u32(file.data + off);
        const char* typ = reinterpret_cast<const char*>(file.data + off + 4);
        std::size_t hdr = 8;
        std::size_t start = off + 8;
        if (sz == 1)
        {
            sz = read_u64(file.data + off + 8);
            hdr = 16;
            start = off + 16;
        }
        if (sz < hdr)
            throw ScrubError("invalid top-level atom");
        if (sz == 0)
            sz = file.size - off;
        if (off + sz > file.size)
            throw ScrubError("truncated MP4");
        if (std::strncmp(typ, "moov", 4) == 0)
            moov_payload = subspan(file, start, static_cast<std::size_t>(sz) - hdr);
        off += static_cast<std::size_t>(sz);
    }
    if (moov_payload.data == nullptr)
        throw ScrubError("moov atom not found");

    const auto moov_children = parse_children(moov_payload);
    const AtomView* video_trak = nullptr;
    for (const auto& trak : moov_children)
    {
        if (trak.type != "trak")
            continue;
        const auto trak_children = parse_children(trak.payload);
        const AtomView* mdia = find_child(trak_children, "mdia");
        if (!mdia)
            continue;
        const auto mdia_children = parse_children(mdia->payload);
        const AtomView* hdlr = find_child(mdia_children, "hdlr");
        if (!hdlr || hdlr->payload.size < 12)
            continue;
        const char* handler = reinterpret_cast<const char*>(hdlr->payload.data + 8);
        if (std::strncmp(handler, "vide", 4) != 0)
            continue;
        video_trak = &trak;
        break;
    }
    if (!video_trak)
        throw ScrubError("no video track found");

    const auto trak_children = parse_children(video_trak->payload);
    const AtomView* edts = find_child(trak_children, "edts");
    if (edts)
    {
        const auto edts_children = parse_children(edts->payload);
        const AtomView* elst = find_child(edts_children, "elst");
        if (elst && elst->payload.size >= 8)
        {
            const int version = elst->payload.data[0];
            const std::uint32_t count = read_u32(elst->payload.data + 4);
            if (count > 1)
                throw ScrubError("elst with more than one edit is not supported");
            if (count == 1)
            {
                std::size_t ent_off = 8;
                std::int64_t segment_duration{};
                std::int64_t media_time{};
                if (version == 0)
                {
                    if (elst->payload.size < ent_off + 12)
                        throw ScrubError("elst truncated");
                    segment_duration = read_u32(elst->payload.data + ent_off);
                    media_time = read_i32(elst->payload.data + ent_off + 4);
                }
                else
                {
                    if (elst->payload.size < ent_off + 20)
                        throw ScrubError("elst truncated");
                    segment_duration = read_i64(elst->payload.data + ent_off);
                    media_time = read_i64(elst->payload.data + ent_off + 8);
                }
                // Single leading edit (offset or dwell) is allowed; multi-edit timelines are not.
                (void)segment_duration;
                (void)media_time;
            }
        }
    }

    const AtomView* mdia = find_child(trak_children, "mdia");
    if (!mdia)
        throw ScrubError("mdia missing");
    const auto mdia_children = parse_children(mdia->payload);
    const AtomView* mdhd = find_child(mdia_children, "mdhd");
    const AtomView* minf = find_child(mdia_children, "minf");
    if (!mdhd || !minf)
        throw ScrubError("mdhd or minf missing");

    std::uint32_t timescale = 1;
    if (mdhd->payload.size >= 12)
    {
        const int version = mdhd->payload.data[0];
        if (version == 0)
            timescale = read_u32(mdhd->payload.data + 12);
        else if (mdhd->payload.size >= 28)
            timescale = read_u32(mdhd->payload.data + 20);
    }
    if (timescale == 0)
        throw ScrubError("invalid mdhd timescale");

    const auto minf_children = parse_children(minf->payload);
    const AtomView* stbl = find_child(minf_children, "stbl");
    if (!stbl)
        throw ScrubError("stbl missing");
    const auto stbl_children = parse_children(stbl->payload);
    const AtomView* stsd = find_child(stbl_children, "stsd");
    const AtomView* stts = find_child(stbl_children, "stts");
    const AtomView* stss = find_child(stbl_children, "stss");
    const AtomView* ctts = find_child(stbl_children, "ctts");
    const AtomView* stsz = find_child(stbl_children, "stsz");
    const AtomView* stsc = find_child(stbl_children, "stsc");
    const AtomView* stco = find_child(stbl_children, "stco");
    const AtomView* co64 = find_child(stbl_children, "co64");
    if (!stsd || !stts || !stsz || !stsc || (!stco && !co64))
        throw ScrubError("required stbl atom missing");

    if (stsd->payload.size < 8)
        throw ScrubError("stsd too small");
    const std::uint32_t entry_count = read_u32(stsd->payload.data + 4);
    if (entry_count < 1)
        throw ScrubError("stsd has no entries");
    const Span entry = subspan(stsd->payload, 8, stsd->payload.size - 8);
    if (entry.size < 8)
        throw ScrubError("sample entry too small");
    const char* entry_type = reinterpret_cast<const char*>(entry.data + 4);
    Span codec_config;
    VideoCodec codec{};
    int bit_depth = 8;
    if (std::strncmp(entry_type, "avc1", 4) == 0 || std::strncmp(entry_type, "avc3", 4) == 0)
    {
        codec = VideoCodec::H264;
        if (entry.size < 86)
            throw ScrubError("avc1 sample entry too small");
        idx.info_.width = read_u16(entry.data + 32);
        idx.info_.height = read_u16(entry.data + 34);
        const auto entry_children = parse_children(subspan(entry, 86, entry.size - 86));
        const AtomView* avcC = find_child(entry_children, "avcC");
        if (!avcC)
            throw ScrubError("avcC missing");
        codec_config = avcC->payload;
        idx.nal_length_size_ = (codec_config.data[4] & 3) + 1;
        reject_h264_non_420(codec_config);
        append_avcc_parameter_sets(idx.parameter_sets_annexb_, codec_config);
    }
    else if (std::strncmp(entry_type, "vp09", 4) == 0 || std::strncmp(entry_type, "vp08", 4) == 0)
        throw ScrubError("VP9 is not supported");
    else if (std::strncmp(entry_type, "hvc1", 4) == 0 || std::strncmp(entry_type, "hev1", 4) == 0)
    {
        codec = VideoCodec::HEVC;
        if (entry.size < 86)
            throw ScrubError("hvc1 sample entry too small");
        idx.info_.width = read_u16(entry.data + 32);
        idx.info_.height = read_u16(entry.data + 34);
        const auto entry_children = parse_children(subspan(entry, 86, entry.size - 86));
        const AtomView* hvcC = find_child(entry_children, "hvcC");
        if (!hvcC)
            throw ScrubError("hvcC missing");
        codec_config = hvcC->payload;
        if (codec_config.size >= 13)
        {
            const int profile_idc = codec_config.data[1] & 0x1f;
            const int luma_minus8 = (codec_config.data[21] >> 3) & 0x1f;
            if (profile_idc == 2)
                bit_depth = 10;
            else if (luma_minus8 == 2)
                bit_depth = 10;
            else
                bit_depth = 8;
        }
        idx.nal_length_size_ = 4;
        append_hvcc_parameter_sets(idx.parameter_sets_annexb_, codec_config);
    }
    else
        throw ScrubError("codec not supported (expected H.264 or HEVC)");

    if (bit_depth != 8 && bit_depth != 10)
        throw ScrubError("bit depth must be 8 or 10");

    // stts -> dts
    if (stts->payload.size < 8)
        throw ScrubError("stts too small");
    const std::uint32_t stts_count = read_u32(stts->payload.data + 4);
    std::vector<std::int64_t> dts_list;
    dts_list.reserve(4096);
    std::int64_t t = 0;
    std::size_t stts_off = 8;
    for (std::uint32_t i = 0; i < stts_count; ++i)
    {
        if (stts_off + 8 > stts->payload.size)
            throw ScrubError("stts truncated");
        const std::uint32_t sample_count = read_u32(stts->payload.data + stts_off);
        const std::uint32_t sample_delta = read_u32(stts->payload.data + stts_off + 4);
        stts_off += 8;
        for (std::uint32_t s = 0; s < sample_count; ++s)
        {
            dts_list.push_back(t);
            t += sample_delta;
        }
    }
    const int sample_count = static_cast<int>(dts_list.size());
    if (sample_count == 0)
        throw ScrubError("no video samples");

    std::vector<std::int64_t> pts_list(dts_list.size());
    for (std::size_t i = 0; i < dts_list.size(); ++i)
        pts_list[i] = dts_list[i];
    if (ctts)
    {
        if (ctts->payload.size < 8)
            throw ScrubError("ctts too small");
        const int version = ctts->payload.data[0];
        const std::uint32_t ctts_count = read_u32(ctts->payload.data + 4);
        std::size_t c_off = 8;
        std::size_t si = 0;
        for (std::uint32_t i = 0; i < ctts_count; ++i)
        {
            if (c_off + 8 > ctts->payload.size)
                throw ScrubError("ctts truncated");
            const std::uint32_t sc = read_u32(ctts->payload.data + c_off);
            std::int64_t off = 0;
            if (version == 0)
                off = read_i32(ctts->payload.data + c_off + 4);
            else
                off = read_i64(ctts->payload.data + c_off + 4);
            c_off += 8;
            for (std::uint32_t s = 0; s < sc; ++s)
            {
                if (si >= pts_list.size())
                    throw ScrubError("ctts sample overflow");
                pts_list[si] = dts_list[si] + off;
                ++si;
            }
        }
    }

    std::vector<std::uint32_t> sizes(sample_count);
    if (stsz->payload.size < 12)
        throw ScrubError("stsz too small");
    const std::uint32_t default_size = read_u32(stsz->payload.data + 4);
    const std::uint32_t sz_count = read_u32(stsz->payload.data + 8);
    if (sz_count != static_cast<std::uint32_t>(sample_count))
        throw ScrubError("stsz count mismatch");
    if (default_size != 0)
    {
        for (int i = 0; i < sample_count; ++i)
            sizes[i] = default_size;
    }
    else
    {
        std::size_t off = 12;
        for (int i = 0; i < sample_count; ++i)
        {
            if (off + 4 > stsz->payload.size)
                throw ScrubError("stsz truncated");
            sizes[i] = read_u32(stsz->payload.data + off);
            off += 4;
        }
    }

    std::vector<std::uint8_t> sync_flags(sample_count, 0);
    if (stss)
    {
        if (stss->payload.size < 8)
            throw ScrubError("stss too small");
        const std::uint32_t sync_count = read_u32(stss->payload.data + 4);
        std::size_t off = 8;
        for (std::uint32_t i = 0; i < sync_count; ++i)
        {
            if (off + 4 > stss->payload.size)
                throw ScrubError("stss truncated");
            const std::uint32_t idx1 = read_u32(stss->payload.data + off);
            off += 4;
            if (idx1 == 0 || idx1 > static_cast<std::uint32_t>(sample_count))
                throw ScrubError("stss index out of range");
            sync_flags[idx1 - 1] = 1;
        }
    }
    else
    {
        for (int i = 0; i < sample_count; ++i)
            sync_flags[i] = 1;
    }

    // stsc + stco/co64 -> offsets
    if (stsc->payload.size < 8)
        throw ScrubError("stsc too small");
    const std::uint32_t stsc_count = read_u32(stsc->payload.data + 4);
    struct StscEntry
    {
        std::uint32_t first_chunk;
        std::uint32_t samples_per_chunk;
    };
    std::vector<StscEntry> stsc_entries;
    std::size_t sc_off = 8;
    for (std::uint32_t i = 0; i < stsc_count; ++i)
    {
        if (sc_off + 12 > stsc->payload.size)
            throw ScrubError("stsc truncated");
        StscEntry e;
        e.first_chunk = read_u32(stsc->payload.data + sc_off);
        e.samples_per_chunk = read_u32(stsc->payload.data + sc_off + 4);
        sc_off += 12;
        stsc_entries.push_back(e);
    }
    if (stsc_entries.empty())
        throw ScrubError("stsc empty");

    std::vector<std::uint64_t> chunk_offsets;
    if (stco)
    {
        if (stco->payload.size < 8)
            throw ScrubError("stco too small");
        const std::uint32_t chunk_count = read_u32(stco->payload.data + 4);
        std::size_t off = 8;
        for (std::uint32_t c = 0; c < chunk_count; ++c)
        {
            if (off + 4 > stco->payload.size)
                throw ScrubError("stco truncated");
            chunk_offsets.push_back(read_u32(stco->payload.data + off));
            off += 4;
        }
    }
    else
    {
        if (co64->payload.size < 8)
            throw ScrubError("co64 too small");
        const std::uint32_t chunk_count = read_u32(co64->payload.data + 4);
        std::size_t off = 8;
        for (std::uint32_t c = 0; c < chunk_count; ++c)
        {
            if (off + 8 > co64->payload.size)
                throw ScrubError("co64 truncated");
            chunk_offsets.push_back(read_u64(co64->payload.data + off));
            off += 8;
        }
    }

    auto samples_per_chunk_for = [&](std::uint32_t chunk_index_1based) {
        for (std::size_t i = 0; i < stsc_entries.size(); ++i)
        {
            const std::uint32_t first = stsc_entries[i].first_chunk;
            const std::uint32_t next_first =
                (i + 1 < stsc_entries.size()) ? stsc_entries[i + 1].first_chunk : std::numeric_limits<std::uint32_t>::max();
            if (chunk_index_1based >= first && chunk_index_1based < next_first)
                return stsc_entries[i].samples_per_chunk;
        }
        return stsc_entries.back().samples_per_chunk;
    };

    std::vector<RawSample> raw(sample_count);
    int sample_idx = 0;
    for (std::size_t chunk_i = 0; chunk_i < chunk_offsets.size(); ++chunk_i)
    {
        const std::uint32_t chunk_no = static_cast<std::uint32_t>(chunk_i + 1);
        const std::uint32_t spc = samples_per_chunk_for(chunk_no);
        std::uint64_t pos = chunk_offsets[chunk_i];
        for (std::uint32_t s = 0; s < spc && sample_idx < sample_count; ++s, ++sample_idx)
        {
            raw[sample_idx].sample_idx = sample_idx;
            raw[sample_idx].dts = dts_list[sample_idx];
            raw[sample_idx].pts = pts_list[sample_idx];
            raw[sample_idx].offset = pos;
            raw[sample_idx].size = sizes[sample_idx];
            raw[sample_idx].is_sync = sync_flags[sample_idx] != 0;
            pos += sizes[sample_idx];
        }
    }
    if (sample_idx != sample_count)
        throw ScrubError("sample offset table does not cover all samples");

    std::vector<int> pres_order(sample_count);
    for (int i = 0; i < sample_count; ++i)
        pres_order[i] = i;
    std::stable_sort(pres_order.begin(), pres_order.end(), [&](int a, int b) {
        if (raw[a].pts != raw[b].pts)
            return raw[a].pts < raw[b].pts;
        return raw[a].dts < raw[b].dts;
    });

    idx.decode_samples_.resize(sample_count);
    for (int si = 0; si < sample_count; ++si)
    {
        idx.decode_samples_[si] = Mp4Sample{
            si,
            raw[si].pts,
            raw[si].dts,
            raw[si].offset,
            raw[si].size,
            raw[si].is_sync,
        };
    }

    idx.samples_.resize(sample_count);
    for (int pres = 0; pres < sample_count; ++pres)
    {
        const int si = pres_order[pres];
        idx.samples_[pres] = idx.decode_samples_[si];
    }

    int sync_count = 0;
    int gop_max = 0;
    int since_sync = 0;
    for (int pres = 0; pres < sample_count; ++pres)
    {
        if (idx.samples_[pres].is_sync)
        {
            ++sync_count;
            gop_max = std::max(gop_max, since_sync);
            since_sync = 0;
        }
        else
            ++since_sync;
    }
    gop_max = std::max(gop_max, since_sync);

    std::uint32_t tick = 0;
    if (stts_count > 0 && stts->payload.size >= 16)
        tick = read_u32(stts->payload.data + 12);
    if (tick == 0)
        tick = 1;

    idx.info_.frames = sample_count;
    idx.info_.width = idx.info_.width;
    idx.info_.height = idx.info_.height;
    idx.info_.codec = codec;
    idx.info_.bit_depth = bit_depth;
    idx.info_.sync_count = sync_count;
    idx.info_.gop_max = gop_max;
    idx.info_.timescale = timescale;
    idx.info_.fps_num = static_cast<int>(timescale);
    idx.info_.fps_den = static_cast<int>(tick);
    const int g = std::gcd(idx.info_.fps_num, idx.info_.fps_den);
    idx.info_.fps_num /= g;
    idx.info_.fps_den /= g;

    return idx;
}

const Mp4Sample& Mp4Index::decode_sample(int sample_idx) const
{
    if (sample_idx < 0 || sample_idx >= static_cast<int>(decode_samples_.size()))
        throw ScrubError("decode sample index out of range");
    return decode_samples_[sample_idx];
}

int Mp4Index::sync_at_or_before(int presentation_index) const
{
    if (presentation_index < 0 || presentation_index >= static_cast<int>(samples_.size()))
        throw ScrubError("presentation index out of range");
    for (int i = presentation_index; i >= 0; --i)
        if (samples_[i].is_sync)
            return i;
    return 0;
}

int Mp4Index::prev_sync(int presentation_index) const
{
    const int cur = sync_at_or_before(presentation_index);
    if (cur <= 0)
        return 0;
    for (int i = cur - 1; i >= 0; --i)
        if (samples_[i].is_sync)
            return i;
    return 0;
}

int Mp4Index::presentation_for_pts(std::int64_t pts) const
{
    for (int pres = 0; pres < static_cast<int>(samples_.size()); ++pres)
    {
        if (samples_[pres].pts == pts)
            return pres;
    }
    return -1;
}

std::vector<std::uint8_t> Mp4Index::annexb_for_decode_sample(int sample_idx, bool prepend_parameter_sets) const
{
    const Mp4Sample& s = decode_sample(sample_idx);
    if (s.offset + s.size > file_.size())
        throw ScrubError("sample extends past file");
    auto au = length_prefixed_to_annexb(file_.data() + s.offset, s.size, nal_length_size_);
    if (prepend_parameter_sets && !parameter_sets_annexb_.empty())
    {
        std::vector<std::uint8_t> out;
        out.reserve(parameter_sets_annexb_.size() + au.size());
        out.insert(out.end(), parameter_sets_annexb_.begin(), parameter_sets_annexb_.end());
        out.insert(out.end(), au.begin(), au.end());
        return out;
    }
    return au;
}

std::vector<std::uint8_t> Mp4Index::annexb_for_presentation(int presentation_index, bool prepend_parameter_sets) const
{
    if (presentation_index < 0 || presentation_index >= static_cast<int>(samples_.size()))
        throw ScrubError("presentation index out of range");
    return annexb_for_decode_sample(samples_[presentation_index].sample_idx, prepend_parameter_sets);
}

} // namespace v1d::scrub
