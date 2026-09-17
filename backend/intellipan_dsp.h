#ifndef VIIZEYMIX_INTELLIPAN_DSP_H
#define VIIZEYMIX_INTELLIPAN_DSP_H

#include <stdint.h>

#define IP_COLOR_REVERB_SAMPLES 4096
#define IP_MOD_DELAY_SAMPLES 8192
#define IP_POSITION_DELAY_SAMPLES 512
#define IP_ROOM_DELAY_SAMPLES 8192

struct intellipan_controls {
    float color_x;
    float color_y;
    float modulation_x;
    float modulation_y;
    float position_x;
    float position_y;
};

struct intellipan_channel_state {
    float color_low_state;
    float color_high_lp_state;
    float color_delay[IP_COLOR_REVERB_SAMPLES];
    uint32_t color_delay_pos;

    float modulation_delay[IP_MOD_DELAY_SAMPLES];
    uint32_t modulation_delay_pos;
    float modulation_feedback_sample;
    float phaser_state[4];

    float position_delay[IP_POSITION_DELAY_SAMPLES];
    float room_delay[IP_ROOM_DELAY_SAMPLES];
    float head_shadow_state;
};

struct intellipan_dsp_state {
    struct intellipan_channel_state channels[2];
    uint32_t position_delay_pos;
    uint32_t room_delay_pos;
    float modulation_phase;
};

int intellipan_controls_active(const struct intellipan_controls *controls);

void intellipan_dsp_process(
    float *output_left,
    float *output_right,
    const float *input_left,
    const float *input_right,
    uint32_t sample_count,
    uint32_t sample_rate,
    const struct intellipan_controls *controls,
    struct intellipan_dsp_state *state);

#endif
