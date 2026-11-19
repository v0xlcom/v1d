// SPDX-License-Identifier: MIT
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace v1d::scrub
{

class MappedFile
{
public:
    MappedFile() = default;
    ~MappedFile();

    MappedFile(const MappedFile&) = delete;
    MappedFile& operator=(const MappedFile&) = delete;
    MappedFile(MappedFile&& other) noexcept;
    MappedFile& operator=(MappedFile&& other) noexcept;

    void open(const std::string& path);
    void close();

    const std::uint8_t* data() const
    {
        return data_;
    }
    std::size_t size() const
    {
        return size_;
    }
    bool empty() const
    {
        return size_ == 0;
    }

private:
    std::uint8_t* data_{ nullptr };
    std::size_t size_{ 0 };
    int fd_{ -1 };
};

} // namespace v1d::scrub
