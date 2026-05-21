#include "fleet_simulator.hpp"

#include <cstring>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(fleet_sim, CONFIG_LOG_DEFAULT_LEVEL);

namespace lon::fleet
{

static FleetConfig g_config;
static FleetState  g_state;
static bool        g_initialized = false;

void init_fleet(const FleetConfig& config)
{
    g_config = config;
    g_state.current_device_index  = 0;
    g_state.current_device_joined = false;
    g_initialized = true;

    LOG_INF("Fleet simulator: %u devices, join_delay=%u ms",
            g_config.num_devices, g_config.join_delay_ms);
}

const FleetConfig& get_fleet_config() { return g_config; }
const FleetState&  get_fleet_state()  { return g_state;  }

void get_current_device_credentials(uint8_t* dev_eui,
                                    uint8_t* join_eui,
                                    uint8_t* app_key)
{
    if (!g_initialized) return;

    // DevEUI = BASE + start_index + current_device_index
    // start_index offsets each board into its own slice of the fleet.
    // Matches Python register_devices.py dev_eui_from_index() logic.
    memcpy(dev_eui, g_config.base_dev_eui.data(), 8);
    uint16_t carry = g_config.start_index + g_state.current_device_index;
    for (int i = 7; i >= 0 && carry > 0; i--)
    {
        uint16_t sum = dev_eui[i] + carry;
        dev_eui[i]   = static_cast<uint8_t>(sum & 0xFF);
        carry        = sum >> 8;
    }

    memcpy(join_eui, g_config.join_eui.data(), 8);
    memcpy(app_key,  g_config.app_key.data(),  16);
}

void mark_device_joined()
{
    if (!g_initialized) return;
    g_state.current_device_joined = true;
    LOG_INF("Fleet: device %u joined (global idx %u)",
            g_state.current_device_index,
            g_config.start_index + g_state.current_device_index);
}

void advance_to_next_device()
{
    if (!g_initialized) return;

    g_state.current_device_index++;
    g_state.current_device_joined = false;

    if (g_state.current_device_index >= g_config.num_devices)
    {
        LOG_INF("Fleet: all %u devices processed", g_config.num_devices);
    }
    else
    {
        LOG_DBG("Fleet: advancing to device %u", g_state.current_device_index);
    }
}

bool is_fleet_active()
{
    return g_initialized &&
           g_config.enabled &&
           g_state.current_device_index < g_config.num_devices;
}

} // namespace lon::fleet
