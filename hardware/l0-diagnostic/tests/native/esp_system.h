#pragma once
#include <stdint.h>
inline uint32_t esp_random() {return 0x12345678;}
inline int esp_reset_reason() {return 1;}
