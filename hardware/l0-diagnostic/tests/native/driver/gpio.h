#pragma once
using gpio_num_t=int;
constexpr int GPIO_DRIVE_CAP_0=0;
inline int gpio_set_drive_capability(gpio_num_t,int) {return 0;}
