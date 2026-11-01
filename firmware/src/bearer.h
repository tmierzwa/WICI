// SPDX-License-Identifier: MIT
// No-heap numbered transport contract for D21, plus the existing Reticulum adapter
// contract. The production station still uses LegacyBearer until migration is safe.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace bearer {

constexpr size_t LEGACY_ADDRESS = 16;

using StationId = uint16_t;
using Handle = uint32_t;
using RxHandle = uint32_t;

struct ByteSpan {
    const uint8_t* data = nullptr;
    size_t size = 0;
};

struct Caps {
    uint16_t maxPayload = 0;
    uint8_t maxHops = 0;
    bool hopAck = false, e2eAck = false, airtimeClasses = false;
    bool radioSilence = false, frameFilter = false;
};

enum class Delivery : uint8_t { QUEUED, SENT, HOP_ACKED, E2E_ACKED, REJECTED, FAILED };
enum class TrafficClass : uint8_t { K0, K1, K2 };

struct LinkMeta {
    int16_t rssiDbm = 0;
    int8_t snrDb4 = 0;
    uint8_t hops = 0, bearerId = 0;
};

struct Health {
    uint16_t pending = 0;
    uint16_t parent = 0;
    uint32_t silenceDebtMs = 0;
    bool online = false, limited = false;
};

using ReceiveFn = void (*)(RxHandle, StationId, ByteSpan, const LinkMeta&, void*);
using DeliveryFn = void (*)(Handle, Delivery, void*);

struct Bearer {
    virtual ~Bearer() = default;
    virtual Caps caps() const = 0;
    // Handle 0 means rejected; no delivery event will follow. The caller owns
    // the bytes until this method returns; accepted bearers copy them to storage.
    virtual Handle send(StationId destination, ByteSpan envelope, TrafficClass traffic) = 0;
    virtual void setSilence(bool on, bool allowOneExempt) = 0;
    virtual Health health() const = 0;
    virtual void poll() = 0;
    // Required only when caps().e2eAck; after the application's durable commit.
    virtual void confirm(RxHandle rx) = 0;
    virtual void setCallbacks(ReceiveFn onReceive, DeliveryFn onDelivery, void* context) = 0;
};

struct LegacyBearer {
    virtual ~LegacyBearer() = default;
    // Interface and transport both available for outgoing traffic.
    virtual bool radioReady() = 0;
    virtual bool busy() = 0;
    // May initiate path discovery; call before marking a station intent as sent.
    virtual bool sendReady(const uint8_t to[LEGACY_ADDRESS]) = 0;
    // 0 means no packet was accepted; a nonzero handle gets a later delivery event.
    virtual uint32_t send(const uint8_t to[LEGACY_ADDRESS], const uint8_t* data,
                          size_t length, uint32_t timeoutS) = 0;
    virtual void address(uint8_t out[LEGACY_ADDRESS]) = 0;
};

}  // namespace bearer
