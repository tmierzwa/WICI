// SPDX-License-Identifier: MIT
// Interfejs USB węzła stanowiska wspólny dla portu (rns_node.cpp) i rdzenia (rns_node_core.cpp):
// cele ogłoszone przez komputer stanowiska, klasa pakietu w kolejce P1 i diagnostyka (UsbStatus, JSON).
// Sam stan i bufor KISS (kiss::Port) trzyma każdy stos u siebie.
#pragma once

#include <stdio.h>
#include <string.h>

#include "kiss.h"
#include "p1iface.h"
#include "rns_node.h"

namespace rnsnode {
namespace usb {

// Cele komputera stanowiska (USB_PINNED): chronione w pełnych tablicach i w klasie K1 kolejki P1. Nowy cel
// przy pełnej liście zastępuje najstarszy.
struct Destinations {
    uint8_t dest[USB_PINNED][HASH] = {};
    size_t count = 0;
    size_t next = 0;

    bool known(const uint8_t* d) const {
        if (!d) return false;
        for (size_t i = 0; i < count; ++i) {
            if (!memcmp(dest[i], d, HASH)) return true;
        }
        return false;
    }
    void remember(const uint8_t* d) {
        if (!d || known(d)) return;
        memcpy(dest[next], d, HASH);
        next = (next + 1) % USB_PINNED;
        if (count < USB_PINNED) ++count;
    }
    void clear() { *this = Destinations(); }
};

// Klasa pakietu stosu w kolejce P1 (radio.md, „Dostęp do kanału”): zapytanie o trasę stacji to ruch
// własny (K0); w węźle stanowiska pakiet od komputera (stos przetwarza pakiet z USB) albo do celu
// komputera to K1.
inline p1iface::Hint hint(bool ownRequest, bool node, bool fromUsb, const Destinations& d, const uint8_t* raw, size_t length) {
    if (ownRequest) return p1iface::Hint::OWN;
    if (node && (fromUsb || d.known(p1iface::destination(raw, length)))) return p1iface::Hint::RECEIVER;
    return p1iface::Hint::NONE;
}

inline UsbStatus status(const kiss::Port* port, const Destinations& d) {
    UsbStatus s;
    s.enabled = port != nullptr;
    if (!port) return s;
    s.open = port->open();
    s.flowControl = port->flowControl();
    s.buffered = port->buffered();
    s.pinned = d.count;
    s.counters = port->counters();
    return s;
}

// Pola JSON interfejsu USB (INFO, RNS), bez nawiasów.
inline size_t json(const UsbStatus& u, bool node, char* out, size_t size) {
    const kiss::Counters& c = u.counters;
    const int n = snprintf(out, size,
                           "\"node\":%s,\"usb_open\":%s,\"usb_flow\":%s,\"usb_buffered\":%u,\"usb_pinned\":%u,"
                           "\"usb_rns_in\":%lu,\"usb_rns_out\":%lu,\"usb_rx_drop\":%lu,\"usb_rx_large\":%lu,\"usb_tx_drop\":%lu,"
                           "\"usb_ready\":%lu,\"usb_cmds\":%lu",
                           node ? "true" : "false", u.open ? "true" : "false", u.flowControl ? "true" : "false",
                           (unsigned)u.buffered, (unsigned)u.pinned, (unsigned long)c.fromComputer, (unsigned long)c.toComputer,
                           (unsigned long)c.rxDropped, (unsigned long)c.rxTooLarge, (unsigned long)c.txDropped,
                           (unsigned long)c.ready, (unsigned long)c.commands);
    return n < 0 ? 0 : static_cast<size_t>(n);
}

}  // namespace usb
}  // namespace rnsnode
