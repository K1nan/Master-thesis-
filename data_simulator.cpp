#include "data_simulator.hpp"

#ifdef CONFIG_FLEET_JOIN_SIMULATOR

#include "fleet_simulator.hpp"
#include "msg.hpp"
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/random/random.h>

LOG_MODULE_REGISTER(data_sim, CONFIG_LOG_DEFAULT_LEVEL);

namespace lon::fleet
{

// ── Sensor slot table ─────────────────────────────────────────────────────────
// 10 generic slots: {id, period_ms, val_min, val_max, current}
// IDs and ranges come from the node specification. No semantic names used.

struct Slot {
    uint8_t  id;
    uint32_t period_ms;
    double   val_min;
    double   val_max;
    double   current;
};

static Slot slots[] = {
    {  0,  1800000,  34.0,  42.0,  38.0 },
    {  1,  1800000,  34.0,  42.0,  37.5 },
    {  2,  1800000,  34.0,  42.0,  39.0 },
    {  3,  1800000,   6.8,   7.8,   7.2 },
    {  4,    60000,  33.0,  43.0,  38.5 },
    {  5,    60000,  55.0,  75.0,  65.0 },
    {  6,    60000,   0.5,   5.0,   2.0 },
    {  7,    60000,   0.1,   2.0,   0.8 },
    {  8,   300000,  -5.0,  35.0,  18.0 },
    {  9,   300000,   0.0, 100.0,  40.0 },
};

static constexpr uint8_t NUM_SLOTS = sizeof(slots) / sizeof(slots[0]);

// ── Node patterns ─────────────────────────────────────────────────────────────
// Each node type uses 2 slots. 5 patterns cover all 10 slots.
// global_device_index % NUM_PATTERNS selects which pattern the device uses.

struct NodePattern {
    uint8_t slot_a;
    uint8_t slot_b;
};

static constexpr NodePattern PATTERNS[] = {
    { 0, 1 },   // pattern 0 → slots 0, 1
    { 2, 3 },   // pattern 1 → slots 2, 3
    { 4, 5 },   // pattern 2 → slots 4, 5
    { 6, 7 },   // pattern 3 → slots 6, 7
    { 8, 9 },   // pattern 4 → slots 8, 9
};

static constexpr uint8_t NUM_PATTERNS = sizeof(PATTERNS) / sizeof(PATTERNS[0]);

// ── Periodic timers ───────────────────────────────────────────────────────────

static struct k_timer slot_timers[NUM_SLOTS];
static bool running = false;

static double random_walk(double current, double min_val, double max_val)
{
    double range = max_val - min_val;
    double step  = ((static_cast<double>(sys_rand16_get()) / 65535.0) - 0.5)
                   * range * 0.04;
    double next  = current + step;
    if (next < min_val) next = min_val;
    if (next > max_val) next = max_val;
    return next;
}

static void send_slot(Slot& s)
{
    s.current = random_walk(s.current, s.val_min, s.val_max);
    Events::SENSOR_DATA d = { .id = s.id, .data = s.current, .alert = false };
    int ret = lon::send_lora_event(Events::Lora(d), K_NO_WAIT);
    if (ret != 0) {
        LOG_WRN("data_sim: queue full, dropped slot id=%u", s.id);
    } else {
        LOG_DBG("data_sim: slot=%u val=%.2f", s.id, s.current);
    }
}

#define MAKE_CB(i) \
    static void slot_cb_##i(struct k_timer*) { if (running) send_slot(slots[i]); }

MAKE_CB(0) MAKE_CB(1) MAKE_CB(2) MAKE_CB(3) MAKE_CB(4)
MAKE_CB(5) MAKE_CB(6) MAKE_CB(7) MAKE_CB(8) MAKE_CB(9)

static void (*const slot_cbs[NUM_SLOTS])(struct k_timer*) = {
    slot_cb_0, slot_cb_1, slot_cb_2, slot_cb_3, slot_cb_4,
    slot_cb_5, slot_cb_6, slot_cb_7, slot_cb_8, slot_cb_9,
};

// ── Public API ────────────────────────────────────────────────────────────────

SensorReading get_data_for_device(uint16_t global_device_index)
{
    const NodePattern& p = PATTERNS[global_device_index % NUM_PATTERNS];
    uint8_t slot_idx = (global_device_index / NUM_PATTERNS) % 2 == 0
                       ? p.slot_a : p.slot_b;
    Slot& s = slots[slot_idx];
    s.current = random_walk(s.current, s.val_min, s.val_max);
    return { s.id, s.current };
}

void data_simulator_init()
{
    LOG_INF("data_sim: starting %u slots", NUM_SLOTS);
    running = true;
    for (uint8_t i = 0; i < NUM_SLOTS; i++) {
        k_timer_init(&slot_timers[i], slot_cbs[i], nullptr);
        k_timer_start(&slot_timers[i],
                      K_MSEC(static_cast<uint32_t>(i) * 3000u),
                      K_MSEC(slots[i].period_ms));
    }
}

void data_simulator_stop()
{
    if (!running) return;
    running = false;
    for (uint8_t i = 0; i < NUM_SLOTS; i++) {
        k_timer_stop(&slot_timers[i]);
    }
    LOG_INF("data_sim: stopped");
}

} // namespace lon::fleet

#endif // CONFIG_FLEET_JOIN_SIMULATOR
