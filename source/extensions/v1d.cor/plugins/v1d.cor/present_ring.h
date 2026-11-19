// SPDX-License-Identifier: MIT
#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <optional>

namespace v1d::scrub
{

class PresentRing
{
public:
    static constexpr int kMaxSlots = 8;
    static constexpr int kDefaultHoldPolls = 2;

    explicit PresentRing(int hold_polls = kDefaultHoldPolls);

    int slot_count() const { return slot_count_; }

    std::optional<int> acquire_writing();
    void publish_ready(int slot);
    void abandon_writing(int slot);
    std::optional<int> poll();

private:
    enum class State : std::uint8_t
    {
        Free = 0,
        Writing = 1,
        Ready = 2,
        Held = 3,
    };

    int slot_count_{};
    int hold_polls_{};
    std::array<std::atomic<std::uint8_t>, kMaxSlots> states_{};
    std::array<std::atomic<int>, kMaxSlots> held_polls_left_{};
    std::atomic<std::uint32_t> newest_ready_{ UINT32_MAX };

    void tick_held(int except_slot);
};

} // namespace v1d::scrub
