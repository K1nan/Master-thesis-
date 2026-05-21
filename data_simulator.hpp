#pragma once

#include <cstdint>

#ifdef CONFIG_FLEET_JOIN_SIMULATOR

namespace lon::fleet
{

struct SensorReading {
    uint8_t id;
    double  value;
};

SensorReading get_data_for_device(uint16_t global_device_index);

void data_simulator_init();
void data_simulator_stop();

} // namespace lon::fleet

#endif // CONFIG_FLEET_JOIN_SIMULATOR
