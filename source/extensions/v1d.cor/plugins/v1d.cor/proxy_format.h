// SPDX-License-Identifier: MIT
#pragma once

#include "mp4_index.h"

#include <cstdint>
#include <string>

namespace v1d::scrub
{

constexpr std::uint32_t kProxyMagic = 0x31505631u; // '1' 'P' 'V' '1' little-endian
constexpr std::uint32_t kProxyVersion = 1u;
constexpr std::uint32_t kProxyCodecNv12 = 0u;

struct ProxySourceIdentity
{
    std::uint64_t path_hash{};
    std::uint64_t size_bytes{};
    std::int64_t mtime_ns{};
};

struct ProxyDimensions
{
    std::uint32_t source_width{};
    std::uint32_t source_height{};
    std::uint32_t proxy_width{};
    std::uint32_t proxy_height{};
};

#pragma pack(push, 1)
struct ProxyHeader
{
    std::uint32_t magic{kProxyMagic};
    std::uint32_t version{kProxyVersion};
    std::uint32_t codec{kProxyCodecNv12};
    std::uint64_t path_hash{};
    std::uint64_t source_size_bytes{};
    std::int64_t source_mtime_ns{};
    std::uint32_t source_width{};
    std::uint32_t source_height{};
    std::uint32_t proxy_width{};
    std::uint32_t proxy_height{};
    std::uint32_t frame_count{};
    std::uint64_t frame_bytes{};
    std::uint64_t index_offset{};
};
#pragma pack(pop)

static_assert(sizeof(ProxyHeader) == 72, "ProxyHeader on-disk size");

struct ProxySourceStat
{
    std::uint64_t size_bytes{};
    std::int64_t mtime_ns{};
};

/** FNV-1a 64 over UTF-8 path bytes (stable cache key component). */
std::uint64_t proxy_hash_path(const std::string& path);

bool proxy_stat_source(const std::string& path, ProxySourceStat* out, std::string* err);

ProxySourceIdentity proxy_source_identity(const std::string& path, std::string* err);

/** `${XDG_CACHE_HOME:-~/.cache}/v1d/proxy/<hex(path_hash)>_<size>_<mtime>.v1dproxy` */
std::string proxy_cache_file_path(const ProxySourceIdentity& id);

std::uint64_t proxy_nv12_frame_bytes(std::uint32_t width, std::uint32_t height);

/** header + frames * frame_bytes + frame_count * sizeof(uint64_t) index entries. */
std::uint64_t proxy_file_size_bytes(const ProxyHeader& hdr);

bool proxy_write_header(int fd, const ProxyHeader& hdr, std::string* err);

bool proxy_read_header(int fd, ProxyHeader* hdr, std::string* err);

bool proxy_read_header_file(const std::string& path, ProxyHeader* hdr, std::string* err);

/** Final path + `.building` (removed on success or failure). */
std::string proxy_cache_temp_path(const std::string& final_path);

void proxy_even_proxy_dims(int src_w, int src_h, int proxy_height, int* out_w, int* out_h);

bool proxy_header_matches_source(const ProxyHeader& hdr, const ProxySourceIdentity& id, const ClipInfo& info);

} // namespace v1d::scrub
