// SPDX-License-Identifier: MIT
// ESP-IDF <nvs.h> (pamięć klucz-wartość we flashu ESP32-S3) na wirtualnej płytce: przestrzenie nazw
// i bloby; zawartość przetrwa restart i wyłączenie jak flash (środowisko przenosi ją jak FRAM).
// Używa jej generator liczb losowych stosu (Crypto/RNG.cpp, ziarno "rng"/"seed").
#pragma once

#include <stddef.h>
#include <stdint.h>

typedef int esp_err_t;
typedef uint32_t nvs_handle_t;
typedef nvs_handle_t nvs_handle;
typedef enum { NVS_READONLY, NVS_READWRITE } nvs_open_mode_t;
typedef nvs_open_mode_t nvs_open_mode;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define ESP_ERR_NVS_INVALID_LENGTH 0x110c

esp_err_t nvs_open(const char* name, nvs_open_mode_t mode, nvs_handle_t* handle);
esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out, size_t* length);
esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* value, size_t length);
esp_err_t nvs_erase_all(nvs_handle_t handle);
esp_err_t nvs_commit(nvs_handle_t handle);
void nvs_close(nvs_handle_t handle);
