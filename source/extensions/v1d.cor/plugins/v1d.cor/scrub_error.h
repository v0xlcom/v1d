// SPDX-License-Identifier: MIT
#pragma once

#include <stdexcept>
#include <string>

namespace v1d::scrub
{

class ScrubError : public std::runtime_error
{
public:
    explicit ScrubError(const std::string& message) : std::runtime_error(message)
    {
    }
};

} // namespace v1d::scrub
