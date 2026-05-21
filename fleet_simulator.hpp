#pragma once

#include <array>
#include <cstdint>

namespace lon::fleet
{

struct FleetConfig {
    bool     enabled        = false;
    uint8_t  num_devices    = 10;
    uint16_t start_index    = 0;      // device offset for this board (0, 10, 20 …)
    uint32_t join_delay_ms  = 5000;
    std::array<uint8_t, 8>  base_dev_eui {};
    std::array<uint8_t, 8>  join_eui {};
    std::array<uint8_t, 16> app_key {};
    bool send_data_after_join = false;
};

struct FleetState {
    uint8_t current_device_index = 0;
    bool    current_device_joined = false;
};

void             init_fleet(const FleetConfig& config);
const FleetConfig& get_fleet_config();
const FleetState&  get_fleet_state();

// Fills dev_eui/join_eui/app_key for the current device index.
// Uses carry-propagating increment so EUIs match the Python deveui_generator.py.
void get_current_device_credentials(uint8_t* dev_eui,
                                    uint8_t* join_eui,
                                    uint8_t* app_key);

void mark_device_joined();
void advance_to_next_device();
bool is_fleet_active();

} // namespace lon::fleet
