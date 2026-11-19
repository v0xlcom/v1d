// SPDX-License-Identifier: MIT
#include "proxy_format.h"

#include <cmath>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace v1d::scrub
{

namespace
{

std::uint64_t fnv1a64(const void* data, std::size_t len)
{
    const auto* p = static_cast<const std::uint8_t*>(data);
    std::uint64_t h = 14695981039346656037ull;
    for (std::size_t i = 0; i < len; ++i) {
        h ^= p[i];
        h *= 1099511628211ull;
    }
    return h;
}

std::string cache_root_dir()
{
    const char* xdg = std::getenv("XDG_CACHE_HOME");
    if (xdg && xdg[0] != '\0')
        return std::string(xdg) + "/v1d/proxy";
    const char* home = std::getenv("HOME");
    if (home && home[0] != '\0')
        return std::string(home) + "/.cache/v1d/proxy";
    return "/tmp/v1d/proxy";
}

bool write_all(int fd, const void* data, std::size_t len, std::string* err)
{
    const auto* p = static_cast<const std::uint8_t*>(data);
    std::size_t off = 0;
    while (off < len) {
        const ssize_t n = ::write(fd, p + off, len - off);
        if (n < 0) {
            if (err)
                *err = std::string("write: ") + std::strerror(errno);
            return false;
        }
        off += static_cast<std::size_t>(n);
    }
    return true;
}

bool read_all(int fd, void* data, std::size_t len, std::string* err)
{
    auto* p = static_cast<std::uint8_t*>(data);
    std::size_t off = 0;
    while (off < len) {
        const ssize_t n = ::read(fd, p + off, len - off);
        if (n < 0) {
            if (err)
                *err = std::string("read: ") + std::strerror(errno);
            return false;
        }
        if (n == 0) {
            if (err)
                *err = "read: unexpected EOF";
            return false;
        }
        off += static_cast<std::size_t>(n);
    }
    return true;
}

} // namespace

std::uint64_t proxy_hash_path(const std::string& path)
{
    return fnv1a64(path.data(), path.size());
}

bool proxy_stat_source(const std::string& path, ProxySourceStat* out, std::string* err)
{
    if (!out) {
        if (err)
            *err = "null out";
        return false;
    }
    struct stat st {};
    if (::stat(path.c_str(), &st) != 0) {
        if (err)
            *err = std::string("stat: ") + std::strerror(errno);
        return false;
    }
    out->size_bytes = static_cast<std::uint64_t>(st.st_size);
#if defined(st_mtime_nsec)
    out->mtime_ns = static_cast<std::int64_t>(st.st_mtim.tv_sec) * 1000000000ll
        + static_cast<std::int64_t>(st.st_mtim.tv_nsec);
#else
    out->mtime_ns = static_cast<std::int64_t>(st.st_mtime) * 1000000000ll;
#endif
    return true;
}

ProxySourceIdentity proxy_source_identity(const std::string& path, std::string* err)
{
    ProxySourceStat st {};
    if (!proxy_stat_source(path, &st, err))
        return {};
    ProxySourceIdentity id;
    id.path_hash = proxy_hash_path(path);
    id.size_bytes = st.size_bytes;
    id.mtime_ns = st.mtime_ns;
    return id;
}

std::string proxy_cache_file_path(const ProxySourceIdentity& id)
{
    std::ostringstream name;
    name << std::hex << id.path_hash << '_' << std::dec << id.size_bytes << '_' << id.mtime_ns
         << ".v1dproxy";
    return (std::filesystem::path(cache_root_dir()) / name.str()).string();
}

std::uint64_t proxy_nv12_frame_bytes(std::uint32_t width, std::uint32_t height)
{
    const auto w = static_cast<std::uint64_t>(width);
    const auto h = static_cast<std::uint64_t>(height);
    return w * h + w * ((h + 1u) / 2u);
}

std::uint64_t proxy_file_size_bytes(const ProxyHeader& hdr)
{
    const auto frames = static_cast<std::uint64_t>(hdr.frame_count);
    const auto index_bytes = frames * sizeof(std::uint64_t);
    return sizeof(ProxyHeader) + frames * hdr.frame_bytes + index_bytes;
}

bool proxy_write_header(int fd, const ProxyHeader& hdr, std::string* err)
{
    if (hdr.magic != kProxyMagic || hdr.version != kProxyVersion) {
        if (err)
            *err = "invalid proxy header constants";
        return false;
    }
    return write_all(fd, &hdr, sizeof(hdr), err);
}

bool proxy_read_header_file(const std::string& path, ProxyHeader* hdr, std::string* err)
{
    const int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0)
    {
        if (err)
            *err = std::string("open: ") + std::strerror(errno);
        return false;
    }
    const bool ok = proxy_read_header(fd, hdr, err);
    ::close(fd);
    return ok;
}

std::string proxy_cache_temp_path(const std::string& final_path)
{
    return final_path + ".building";
}

void proxy_even_proxy_dims(int src_w, int src_h, int proxy_height, int* out_w, int* out_h)
{
    int h = proxy_height;
    if (h < 2)
        h = 2;
    if (h & 1)
        --h;
    int w = static_cast<int>(std::lround(static_cast<double>(src_w) * static_cast<double>(h) / static_cast<double>(src_h)));
    if (w < 2)
        w = 2;
    w &= ~1;
    if (out_w)
        *out_w = w;
    if (out_h)
        *out_h = h;
}

bool proxy_header_matches_source(const ProxyHeader& hdr, const ProxySourceIdentity& id, const ClipInfo& info)
{
    return hdr.path_hash == id.path_hash && hdr.source_size_bytes == id.size_bytes &&
           hdr.source_mtime_ns == id.mtime_ns && hdr.source_width == static_cast<std::uint32_t>(info.width) &&
           hdr.source_height == static_cast<std::uint32_t>(info.height) &&
           hdr.frame_count == static_cast<std::uint32_t>(info.frames);
}

bool proxy_read_header(int fd, ProxyHeader* hdr, std::string* err)
{
    if (!hdr) {
        if (err)
            *err = "null hdr";
        return false;
    }
    if (!read_all(fd, hdr, sizeof(*hdr), err))
        return false;
    if (hdr->magic != kProxyMagic) {
        if (err)
            *err = "bad proxy magic";
        return false;
    }
    if (hdr->version != kProxyVersion) {
        if (err)
            *err = "unsupported proxy version";
        return false;
    }
    return true;
}

} // namespace v1d::scrub
