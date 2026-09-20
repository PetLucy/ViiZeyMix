#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <pipewire/filter.h>
#include <pipewire/pipewire.h>

#include "intellipan_dsp.h"

#define CHANNEL_COUNT 2
struct channel_state {
    void *input_port;
    void *output_port;
};

struct port_data {
    uint8_t unused;
};

struct dsp_state {
    struct pw_main_loop *loop;
    struct pw_filter *filter;
    struct channel_state channels[CHANNEL_COUNT];
    struct intellipan_dsp_state dsp;
    _Atomic int gate_enabled;
    _Atomic float gate_threshold_db;
    _Atomic float gate_damping_db;
    _Atomic float gate_sidechain_hz;
    _Atomic float gate_attack_ms;
    _Atomic float gate_hold_ms;
    _Atomic float gate_release_ms;
    _Atomic float color_x;
    _Atomic float color_y;
    _Atomic float modulation_x;
    _Atomic float modulation_y;
    _Atomic float position_x;
    _Atomic float position_y;
};

static void on_process(void *userdata, struct spa_io_position *position)
{
    struct dsp_state *state = userdata;
    const uint32_t sample_count = position->clock.duration;
    const uint32_t sample_rate = position->clock.rate.denom;
    const struct intellipan_controls controls = {
        .gate_enabled = atomic_load_explicit(&state->gate_enabled, memory_order_relaxed),
        .gate_threshold_db = atomic_load_explicit(&state->gate_threshold_db, memory_order_relaxed),
        .gate_damping_db = atomic_load_explicit(&state->gate_damping_db, memory_order_relaxed),
        .gate_sidechain_hz = atomic_load_explicit(&state->gate_sidechain_hz, memory_order_relaxed),
        .gate_attack_ms = atomic_load_explicit(&state->gate_attack_ms, memory_order_relaxed),
        .gate_hold_ms = atomic_load_explicit(&state->gate_hold_ms, memory_order_relaxed),
        .gate_release_ms = atomic_load_explicit(&state->gate_release_ms, memory_order_relaxed),
        .color_x = atomic_load_explicit(&state->color_x, memory_order_relaxed),
        .color_y = atomic_load_explicit(&state->color_y, memory_order_relaxed),
        .modulation_x = atomic_load_explicit(&state->modulation_x, memory_order_relaxed),
        .modulation_y = atomic_load_explicit(&state->modulation_y, memory_order_relaxed),
        .position_x = atomic_load_explicit(&state->position_x, memory_order_relaxed),
        .position_y = atomic_load_explicit(&state->position_y, memory_order_relaxed),
    };
    float *input_left = pw_filter_get_dsp_buffer(state->channels[0].input_port, sample_count);
    float *input_right = pw_filter_get_dsp_buffer(state->channels[1].input_port, sample_count);
    float *output_left = pw_filter_get_dsp_buffer(state->channels[0].output_port, sample_count);
    float *output_right = pw_filter_get_dsp_buffer(state->channels[1].output_port, sample_count);

    intellipan_dsp_process(
        output_left,
        output_right,
        input_left,
        input_right,
        sample_count,
        sample_rate,
        &controls,
        &state->dsp);
}

static const struct pw_filter_events filter_events = {
    PW_VERSION_FILTER_EVENTS,
    .process = on_process,
};

static void quit_loop(void *userdata, int signal_number)
{
    struct dsp_state *state = userdata;
    (void)signal_number;
    pw_main_loop_quit(state->loop);
}

static void *control_thread(void *userdata)
{
    struct dsp_state *state = userdata;
    char line[160];

    while (fgets(line, sizeof(line), stdin) != NULL) {
        float x;
        float y;
        int enabled;
        float threshold;
        float damping;
        float sidechain;
        float attack;
        float hold;
        float release;
        if (sscanf(line, "gate %d %f %f %f %f %f %f", &enabled,
                &threshold, &damping, &sidechain, &attack, &hold, &release) == 7) {
            atomic_store_explicit(&state->gate_enabled, enabled != 0, memory_order_relaxed);
            atomic_store_explicit(&state->gate_threshold_db, threshold, memory_order_relaxed);
            atomic_store_explicit(&state->gate_damping_db, damping, memory_order_relaxed);
            atomic_store_explicit(&state->gate_sidechain_hz, sidechain, memory_order_relaxed);
            atomic_store_explicit(&state->gate_attack_ms, attack, memory_order_relaxed);
            atomic_store_explicit(&state->gate_hold_ms, hold, memory_order_relaxed);
            atomic_store_explicit(&state->gate_release_ms, release, memory_order_relaxed);
        } else if (sscanf(line, "color %f %f", &x, &y) == 2) {
            x = fmaxf(-1.0f, fminf(1.0f, x));
            y = fmaxf(-1.0f, fminf(1.0f, y));
            atomic_store_explicit(&state->color_x, x, memory_order_relaxed);
            atomic_store_explicit(&state->color_y, y, memory_order_relaxed);
        } else if (sscanf(line, "modulation %f %f", &x, &y) == 2) {
            x = fmaxf(-1.0f, fminf(1.0f, x));
            y = fmaxf(-1.0f, fminf(1.0f, y));
            atomic_store_explicit(&state->modulation_x, x, memory_order_relaxed);
            atomic_store_explicit(&state->modulation_y, y, memory_order_relaxed);
        } else if (sscanf(line, "position %f %f", &x, &y) == 2) {
            x = fmaxf(-1.0f, fminf(1.0f, x));
            y = fmaxf(-1.0f, fminf(1.0f, y));
            atomic_store_explicit(&state->position_x, x, memory_order_relaxed);
            atomic_store_explicit(&state->position_y, y, memory_order_relaxed);
        } else if (strncmp(line, "quit", 4) == 0) {
            break;
        }
    }

    pw_main_loop_quit(state->loop);
    return NULL;
}

int main(int argc, char **argv)
{
    const char *node_name = argc > 1 ? argv[1] : "viizeymix_intellipan";
    static const char *channel_names[CHANNEL_COUNT] = {"FL", "FR"};
    struct dsp_state state = {0};
    pthread_t controls;

    atomic_init(&state.gate_enabled, 0);
    atomic_init(&state.gate_threshold_db, -45.0f);
    atomic_init(&state.gate_damping_db, -80.0f);
    atomic_init(&state.gate_sidechain_hz, 0.0f);
    atomic_init(&state.gate_attack_ms, 10.0f);
    atomic_init(&state.gate_hold_ms, 185.0f);
    atomic_init(&state.gate_release_ms, 1100.0f);
    atomic_init(&state.color_x, 0.0f);
    atomic_init(&state.color_y, 0.0f);
    atomic_init(&state.modulation_x, 0.0f);
    atomic_init(&state.modulation_y, 0.0f);
    atomic_init(&state.position_x, 0.0f);
    atomic_init(&state.position_y, 0.0f);

    pw_init(&argc, &argv);
    state.loop = pw_main_loop_new(NULL);
    if (state.loop == NULL) {
        fprintf(stderr, "Could not create PipeWire main loop\n");
        return EXIT_FAILURE;
    }

    pw_loop_add_signal(pw_main_loop_get_loop(state.loop), SIGINT, quit_loop, &state);
    pw_loop_add_signal(pw_main_loop_get_loop(state.loop), SIGTERM, quit_loop, &state);

    state.filter = pw_filter_new_simple(
        pw_main_loop_get_loop(state.loop),
        node_name,
        pw_properties_new(
            PW_KEY_NODE_NAME, node_name,
            PW_KEY_NODE_DESCRIPTION, "ViiZeyMix Channel DSP",
            PW_KEY_MEDIA_TYPE, "Audio",
            PW_KEY_MEDIA_CATEGORY, "Filter",
            PW_KEY_MEDIA_ROLE, "DSP",
            "node.autoconnect", "false",
            "node.passive", "true",
            NULL),
        &filter_events,
        &state);
    if (state.filter == NULL) {
        fprintf(stderr, "Could not create ViiZeyMix DSP filter\n");
        pw_main_loop_destroy(state.loop);
        pw_deinit();
        return EXIT_FAILURE;
    }

    for (size_t index = 0; index < CHANNEL_COUNT; ++index) {
        char input_name[24];
        char output_name[24];
        snprintf(input_name, sizeof(input_name), "input_%s", channel_names[index]);
        snprintf(output_name, sizeof(output_name), "output_%s", channel_names[index]);

        state.channels[index].input_port = pw_filter_add_port(
            state.filter,
            PW_DIRECTION_INPUT,
            PW_FILTER_PORT_FLAG_MAP_BUFFERS,
            sizeof(struct port_data),
            pw_properties_new(
                PW_KEY_FORMAT_DSP, "32 bit float mono audio",
                PW_KEY_PORT_NAME, input_name,
                "audio.channel", channel_names[index],
                NULL),
            NULL,
            0);
        state.channels[index].output_port = pw_filter_add_port(
            state.filter,
            PW_DIRECTION_OUTPUT,
            PW_FILTER_PORT_FLAG_MAP_BUFFERS,
            sizeof(struct port_data),
            pw_properties_new(
                PW_KEY_FORMAT_DSP, "32 bit float mono audio",
                PW_KEY_PORT_NAME, output_name,
                "audio.channel", channel_names[index],
                NULL),
            NULL,
            0);
        if (state.channels[index].input_port == NULL || state.channels[index].output_port == NULL) {
            fprintf(stderr, "Could not create DSP ports\n");
            pw_filter_destroy(state.filter);
            pw_main_loop_destroy(state.loop);
            pw_deinit();
            return EXIT_FAILURE;
        }
    }

    if (pw_filter_connect(state.filter, PW_FILTER_FLAG_RT_PROCESS, NULL, 0) < 0) {
        fprintf(stderr, "Could not connect ViiZeyMix DSP filter\n");
        pw_filter_destroy(state.filter);
        pw_main_loop_destroy(state.loop);
        pw_deinit();
        return EXIT_FAILURE;
    }

    if (pthread_create(&controls, NULL, control_thread, &state) != 0) {
        fprintf(stderr, "Could not create DSP control thread\n");
        pw_filter_destroy(state.filter);
        pw_main_loop_destroy(state.loop);
        pw_deinit();
        return EXIT_FAILURE;
    }
    pthread_detach(controls);

    puts("READY");
    fflush(stdout);
    pw_main_loop_run(state.loop);

    pw_filter_destroy(state.filter);
    pw_main_loop_destroy(state.loop);
    pw_deinit();
    return EXIT_SUCCESS;
}
