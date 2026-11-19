// SPDX-License-Identifier: MIT
#include "mapped_file.h"

#include "scrub_error.h"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace v1d::scrub
{

MappedFile::~MappedFile()
{
    close();
}

MappedFile::MappedFile(MappedFile&& other) noexcept
    : data_(other.data_), size_(other.size_), fd_(other.fd_)
{
    other.data_ = nullptr;
    other.size_ = 0;
    other.fd_ = -1;
}

MappedFile& MappedFile::operator=(MappedFile&& other) noexcept
{
    if (this != &other)
    {
        close();
        data_ = other.data_;
        size_ = other.size_;
        fd_ = other.fd_;
        other.data_ = nullptr;
        other.size_ = 0;
        other.fd_ = -1;
    }
    return *this;
}

void MappedFile::open(const std::string& path)
{
    close();
    const int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0)
        throw ScrubError("cannot open file: " + path);
    struct stat st{};
    if (::fstat(fd, &st) != 0)
    {
        ::close(fd);
        throw ScrubError("cannot stat file: " + path);
    }
    if (st.st_size <= 0)
    {
        ::close(fd);
        throw ScrubError("empty file: " + path);
    }
    void* map = ::mmap(nullptr, static_cast<std::size_t>(st.st_size), PROT_READ, MAP_PRIVATE, fd, 0);
    if (map == MAP_FAILED)
    {
        ::close(fd);
        throw ScrubError("mmap failed: " + path);
    }
    fd_ = fd;
    data_ = static_cast<std::uint8_t*>(map);
    size_ = static_cast<std::size_t>(st.st_size);
}

void MappedFile::close()
{
    if (data_ && size_)
    {
        ::munmap(data_, size_);
        data_ = nullptr;
        size_ = 0;
    }
    if (fd_ >= 0)
    {
        ::close(fd_);
        fd_ = -1;
    }
}

} // namespace v1d::scrub
