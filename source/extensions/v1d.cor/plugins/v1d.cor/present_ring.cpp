// SPDX-License-Identifier: MIT
#include "present_ring.h"

#include <algorithm>

namespace v1d::scrub
{

PresentRing::PresentRing(int hold_polls)
    : slot_count_(std::min(kMaxSlots, std::max(1, hold_polls) + 2))
    , hold_polls_(std::max(1, hold_polls))
{
    for (int i = 0; i < kMaxSlots; ++i)
    {
        states_[i].store(static_cast<std::uint8_t>(State::Free), std::memory_order_relaxed);
        held_polls_left_[i].store(0, std::memory_order_relaxed);
    }
}

std::optional<int> PresentRing::acquire_writing()
{
    for (int i = 0; i < slot_count_; ++i)
    {
        std::uint8_t expected = static_cast<std::uint8_t>(State::Free);
        if (states_[i].compare_exchange_strong(
                expected, static_cast<std::uint8_t>(State::Writing), std::memory_order_acq_rel, std::memory_order_acquire))
            return i;
    }
    return std::nullopt;
}

void PresentRing::publish_ready(int slot)
{
    if (slot < 0 || slot >= slot_count_)
        return;
    states_[slot].store(static_cast<std::uint8_t>(State::Ready), std::memory_order_release);
    newest_ready_.store(static_cast<std::uint32_t>(slot), std::memory_order_release);
}

void PresentRing::abandon_writing(int slot)
{
    if (slot < 0 || slot >= slot_count_)
        return;
    states_[slot].store(static_cast<std::uint8_t>(State::Free), std::memory_order_release);
}

void PresentRing::tick_held(int except_slot)
{
    for (int i = 0; i < slot_count_; ++i)
    {
        if (i == except_slot)
            continue;
        if (static_cast<State>(states_[i].load(std::memory_order_acquire)) != State::Held)
            continue;
        int left = held_polls_left_[i].load(std::memory_order_relaxed);
        if (left <= 0)
            continue;
        --left;
        held_polls_left_[i].store(left, std::memory_order_relaxed);
        if (left == 0)
            states_[i].store(static_cast<std::uint8_t>(State::Free), std::memory_order_release);
    }
}

std::optional<int> PresentRing::poll()
{
    const std::uint32_t idx = newest_ready_.load(std::memory_order_acquire);
    if (idx == UINT32_MAX || idx >= static_cast<std::uint32_t>(slot_count_))
        return std::nullopt;

    auto& st = states_[static_cast<int>(idx)];
    const auto cur = static_cast<State>(st.load(std::memory_order_acquire));
    if (cur != State::Ready)
        return std::nullopt;

    st.store(static_cast<std::uint8_t>(State::Held), std::memory_order_release);
    held_polls_left_[static_cast<int>(idx)].store(hold_polls_, std::memory_order_relaxed);
    tick_held(static_cast<int>(idx));
    return static_cast<int>(idx);
}

} // namespace v1d::scrub
